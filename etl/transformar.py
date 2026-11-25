"""ETL de migração de dados do Departamento Pessoal: origem (ERP antigo) -> layout de importação do ERP novo.

Uso:
    python -m etl.transformar
Saídas em dados/destino/: funcionarios.csv, movimentos.csv, rejeitados.csv e relatorio_validacao.md
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
MAP = RAIZ / "mapeamentos"
SITUACAO = {"": "ATIVO", "A": "AFASTADO", "F": "FERIAS", "D": "DESLIGADO"}


def cpf_ok(cpf: str) -> bool:
    d = re.sub(r"\D", "", str(cpf)).zfill(11)
    if len(d) != 11 or d == d[0] * 11:
        return False
    for n in (9, 10):
        soma = sum(int(d[i]) * (n + 1 - i) for i in range(n))
        if int(d[n]) != (0 if soma % 11 < 2 else 11 - soma % 11):
            return False
    return True


def formatar_cpf(cpf: str) -> str:
    d = re.sub(r"\D", "", str(cpf)).zfill(11)
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


def data_br(aaaammdd) -> str:
    s = str(aaaammdd).strip()
    if not s or s.lower() == "nan":
        return ""
    return pd.to_datetime(s, format="%Y%m%d").strftime("%d/%m/%Y")


def transformar_funcionarios(sra: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    sra = sra.fillna("").astype(str)
    cc = pd.read_csv(MAP / "centros_custo.csv", dtype=str).set_index("cc_origem")["cc_destino"]
    cargos = pd.read_csv(MAP / "cargos.csv", dtype=str).set_index("cargo_origem")["cargo_destino"]

    out = pd.DataFrame({
        "filial": sra["RA_FILIAL"].str.strip(),
        "matricula": sra["RA_MAT"].str.strip().str.zfill(6),
        "nome": sra["RA_NOME"].str.upper().str.split().str.join(" "),
        "cpf": sra["RA_CIC"].map(formatar_cpf),
        "data_nascimento": sra["RA_NASC"].map(data_br),
        "data_admissao": sra["RA_ADMISSA"].map(data_br),
        "data_demissao": sra["RA_DEMISSA"].map(data_br),
        "situacao": sra["RA_SITFOLH"].str.strip().map(SITUACAO),
        "centro_custo": sra["RA_CC"].map(cc),
        "cargo": sra["RA_CODFUNC"].str.zfill(5).map(cargos),
        "salario": pd.to_numeric(sra["RA_SALARIO"], errors="coerce").round(2),
    })

    motivos = pd.Series("", index=out.index)
    motivos[~sra["RA_CIC"].map(cpf_ok)] += "CPF inválido; "
    motivos[out["centro_custo"].isna()] += "centro de custo sem de-para; "
    motivos[out["cargo"].isna()] += "cargo sem de-para; "
    motivos[out["situacao"].isna()] += "situação desconhecida; "
    motivos[out.duplicated("matricula", keep="first")] += "matrícula duplicada; "

    rejeitados = out[motivos != ""].assign(motivo=motivos[motivos != ""].str.rstrip("; "))
    return out[motivos == ""].reset_index(drop=True), rejeitados.reset_index(drop=True)


def transformar_movimentos(srd: pd.DataFrame, matriculas_validas: set[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    srd = srd.astype({"RD_MAT": str, "RD_PD": str, "RD_DATARQ": str})
    verbas = pd.read_csv(MAP / "verbas.csv", dtype=str).set_index("verba_origem")
    out = pd.DataFrame({
        "matricula": srd["RD_MAT"].str.zfill(6),
        "competencia": srd["RD_DATARQ"].str[4:] + "/" + srd["RD_DATARQ"].str[:4],
        "verba": srd["RD_PD"].map(verbas["verba_destino"]),
        "tipo": srd["RD_PD"].map(verbas["tipo"]),
        "valor": pd.to_numeric(srd["RD_VALOR"], errors="coerce").round(2),
        "verba_origem": srd["RD_PD"],
    })
    motivo = pd.Series("", index=out.index)
    motivo[out["verba"].isna()] += "verba sem de-para; "
    motivo[~out["matricula"].isin(matriculas_validas)] += "funcionário rejeitado; "
    rej = out[motivo != ""].assign(motivo=motivo[motivo != ""].str.rstrip("; "))
    return out[motivo == ""].drop(columns="verba_origem").reset_index(drop=True), rej.reset_index(drop=True)


def brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def relatorio(sra, srd, func, rej_f, mov, rej_m) -> str:
    total_origem = pd.to_numeric(srd["RD_VALOR"]).sum()
    total_migrado = mov["valor"].sum() + rej_m["valor"].sum()
    linhas = [
        "# Relatório de validação da migração (dados fictícios)\n",
        "| Item | Origem | Migrado | Rejeitado |", "|---|---|---|---|",
        f"| Funcionários | {len(sra)} | {len(func)} | {len(rej_f)} |",
        f"| Movimentos | {len(srd)} | {len(mov)} | {len(rej_m)} |",
        (f"\n**Conciliação de valores:** origem {brl(total_origem)} · migrado + rejeitado {brl(total_migrado)} · "
        f"{'✅ confere' if abs(total_origem - total_migrado) < 0.01 else '❌ diferença'}\n"),
        "## Totais por competência e tipo (migrados)\n",
        mov.pivot_table(index="competencia", columns="tipo", values="valor", aggfunc="sum").round(2).to_markdown(floatfmt=",.2f"),
        "\n## Funcionários rejeitados\n",
        rej_f[["matricula", "nome", "motivo"]].to_markdown(index=False) if len(rej_f) else "Nenhum.",
        "\n## Movimentos rejeitados (resumo)\n",
        rej_m.groupby("motivo").size().rename("qtd").to_frame().to_markdown() if len(rej_m) else "Nenhum.",
    ]
    return "\n".join(linhas)


def main() -> None:
    origem, destino = RAIZ / "dados" / "origem", RAIZ / "dados" / "destino"
    destino.mkdir(parents=True, exist_ok=True)
    sra = pd.read_csv(origem / "SRA_funcionarios.csv", sep=";", dtype=str, keep_default_na=False)
    srd = pd.read_csv(origem / "SRD_movimentos.csv", sep=";", dtype=str)
    func, rej_f = transformar_funcionarios(sra)
    mov, rej_m = transformar_movimentos(srd, set(func["matricula"]))
    func.to_csv(destino / "funcionarios.csv", index=False, sep=";", encoding="utf-8-sig")
    mov.to_csv(destino / "movimentos.csv", index=False, sep=";", encoding="utf-8-sig")
    pd.concat([rej_f.assign(tabela="funcionarios"), rej_m.assign(tabela="movimentos")]).to_csv(
        destino / "rejeitados.csv", index=False, sep=";", encoding="utf-8-sig")
    rel = relatorio(sra, srd, func, rej_f, mov, rej_m)
    (destino / "relatorio_validacao.md").write_text(rel, encoding="utf-8")
    print(rel)


if __name__ == "__main__":
    main()
