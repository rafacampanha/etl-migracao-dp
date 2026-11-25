"""Gera uma base FICTÍCIA no layout de origem (inspirado nas tabelas SRA/SRD de um ERP),
incluindo problemas de propósito (CPF inválido, duplicado, campo vazio) para o ETL tratar."""
from __future__ import annotations

import random
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
NOMES = ["ANA", "BRUNO", "CARLA", "DANIEL", "ELISA", "FABIO", "GABRIELA", "HUGO", "ISABELA", "JOAO", "LARISSA", "MARCOS", "NATALIA", "OTAVIO", "PAULA", "RAFAEL", "SABRINA", "TIAGO", "VANESSA", "WAGNER"]
SOBRENOMES = ["SILVA", "SOUZA", "OLIVEIRA", "SANTOS", "PEREIRA", "COSTA", "RODRIGUES", "ALMEIDA", "NASCIMENTO", "LIMA", "ARAUJO", "RIBEIRO"]


def cpf_valido(rng: random.Random) -> str:
    base = [rng.randint(0, 9) for _ in range(9)]
    for _ in range(2):
        soma = sum(d * p for d, p in zip(base, range(len(base) + 1, 1, -1)))
        base.append(0 if soma % 11 < 2 else 11 - soma % 11)
    return "".join(map(str, base))


def gerar(n: int = 60, seed: int = 42) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = random.Random(seed)
    func = []
    for i in range(1, n + 1):
        sit = rng.choices([" ", "A", "F", "D"], weights=[80, 5, 7, 8])[0]
        adm = f"{rng.randint(2012, 2025)}{rng.randint(1, 12):02d}{rng.randint(1, 28):02d}"
        func.append({
            "RA_FILIAL": "01", "RA_MAT": f"{i:06d}",
            "RA_NOME": f"{rng.choice(NOMES)}  {rng.choice(SOBRENOMES)} {rng.choice(SOBRENOMES)}".lower() if i % 9 == 0 else f"{rng.choice(NOMES)} {rng.choice(SOBRENOMES)} {rng.choice(SOBRENOMES)}",
            "RA_CIC": cpf_valido(rng),
            "RA_NASC": f"{rng.randint(1965, 2004)}{rng.randint(1, 12):02d}{rng.randint(1, 28):02d}",
            "RA_ADMISSA": adm,
            "RA_DEMISSA": f"{rng.randint(int(adm[:4]) + 1, 2026)}0115" if sit == "D" else "",
            "RA_SITFOLH": sit,
            "RA_CC": rng.choice(["1001", "1002", "2001", "2002"]),
            "RA_CODFUNC": rng.choice(["00001", "00002", "00003", "00004", "00005"]),
            "RA_SALARIO": round(rng.uniform(1800, 9500), 2),
        })
    sra = pd.DataFrame(func)
    # problemas propositais
    sra.loc[4, "RA_CIC"] = "12345678900"          # CPF inválido
    sra.loc[10, "RA_CC"] = "9999"                  # centro de custo sem de-para
    sra = pd.concat([sra, sra.iloc[[7]]], ignore_index=True)  # matrícula duplicada

    movs = []
    for _, f in sra.drop_duplicates("RA_MAT").iterrows():
        for comp in ["202608", "202609", "202610"]:
            sal = f["RA_SALARIO"]
            movs += [{"RD_MAT": f["RA_MAT"], "RD_DATARQ": comp, "RD_PD": "101", "RD_VALOR": sal},
                     {"RD_MAT": f["RA_MAT"], "RD_DATARQ": comp, "RD_PD": "401", "RD_VALOR": round(sal * 0.09, 2)}]
            if rng.random() < 0.3:
                movs.append({"RD_MAT": f["RA_MAT"], "RD_DATARQ": comp, "RD_PD": "105", "RD_VALOR": round(rng.uniform(80, 600), 2)})
    srd = pd.DataFrame(movs)
    srd.loc[3, "RD_PD"] = "999"                    # verba sem de-para
    return sra, srd


if __name__ == "__main__":
    (RAIZ / "dados" / "origem").mkdir(parents=True, exist_ok=True)
    sra, srd = gerar()
    sra.to_csv(RAIZ / "dados" / "origem" / "SRA_funcionarios.csv", index=False, sep=";")
    srd.to_csv(RAIZ / "dados" / "origem" / "SRD_movimentos.csv", index=False, sep=";")
    print(f"{len(sra)} funcionários e {len(srd)} movimentos fictícios gerados em dados/origem/")
