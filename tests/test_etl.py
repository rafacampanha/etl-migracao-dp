import pandas as pd
import pytest

from etl.gerar_dados_ficticios import gerar
from etl.transformar import (
    cpf_ok,
    data_br,
    formatar_cpf,
    transformar_funcionarios,
    transformar_movimentos,
)


@pytest.mark.parametrize("cpf,ok", [("529.982.247-25", True), ("12345678900", False), ("11111111111", False)])
def test_cpf_ok(cpf, ok):
    assert cpf_ok(cpf) is ok


def test_formatacoes():
    assert formatar_cpf("52998224725") == "529.982.247-25"
    assert data_br("20260115") == "15/01/2026"
    assert data_br("") == ""


@pytest.fixture(scope="module")
def resultado():
    sra, srd = gerar()
    sra = sra.astype(str)
    func, rej_f = transformar_funcionarios(sra)
    mov, rej_m = transformar_movimentos(srd, set(func["matricula"]))
    return sra, srd, func, rej_f, mov, rej_m


def test_rejeita_problemas_plantados(resultado):
    _, _, func, rej_f, _, _ = resultado
    motivos = " ".join(rej_f["motivo"])
    assert "CPF inválido" in motivos and "centro de custo sem de-para" in motivos and "matrícula duplicada" in motivos
    assert func["matricula"].is_unique


def test_nome_padronizado(resultado):
    _, _, func, *_ = resultado
    assert (func["nome"] == func["nome"].str.upper()).all()
    assert not func["nome"].str.contains("  ").any()


def test_conciliacao_de_valores(resultado):
    _, srd, _, _, mov, rej_m = resultado
    assert mov["valor"].sum() + rej_m["valor"].sum() == pytest.approx(pd.to_numeric(srd["RD_VALOR"]).sum())
    assert "verba sem de-para" in " ".join(rej_m["motivo"])
