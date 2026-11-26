import logging
from datetime import date, timedelta
from pathlib import Path

import pytest

from volt import lambda_diario
from volt.armazenamento import ArmazenamentoS3, chave_carga, chave_previsao
from volt.etl import rodar_etl
from volt.lambda_diario import rodar_diario

FIXTURE = Path(__file__).parent / "fixtures" / "ons_amostra.csv"
HOJE = date(2026, 11, 25)  # ontem = 24 (na fixture), amanhã = 26 (usa a carga do dia 19)


def fetch_ok(ano):
    return FIXTURE.read_text()


def fetch_quebrado(ano):
    raise ConnectionError("ONS fora do ar")


@pytest.fixture
def dados(s3_falso, bucket):
    """Armazenamento no S3 falso, já com a carga de 19/11 (base da previsão de 26/11)."""
    dados = ArmazenamentoS3(bucket)
    rodar_etl(date(2026, 11, 19), dados, fetch=fetch_ok)
    return dados


def test_diario_grava_carga_e_previsao(dados, bucket):
    resultado = rodar_diario(dados, HOJE, fetch=fetch_ok)

    assert resultado == {
        "carga": f"s3://{bucket}/{chave_carga(date(2026, 11, 24))}",
        "previsao": f"s3://{bucket}/{chave_previsao(date(2026, 11, 26))}",
    }
    assert dados.existe(chave_carga(date(2026, 11, 24)))
    assert len(dados.ler_parquet(chave_previsao(date(2026, 11, 26)))) == 24


def test_diario_previsao_roda_mesmo_se_etl_falhar(dados):
    with pytest.raises(RuntimeError):
        rodar_diario(dados, HOJE, fetch=fetch_quebrado)

    assert not dados.existe(chave_carga(date(2026, 11, 24)))
    assert dados.existe(chave_previsao(date(2026, 11, 26)))


def test_diario_falha_no_final_se_algo_falhou(s3_falso, bucket):
    dados = ArmazenamentoS3(bucket)  # sem histórico: a previsão falha; o ETL funciona

    with pytest.raises(RuntimeError, match="previsao") as info:
        rodar_diario(dados, HOJE, fetch=fetch_ok)

    assert "carga:" not in str(info.value)  # só a previsão falhou
    assert dados.existe(chave_carga(date(2026, 11, 24)))  # o ETL rodou e gravou
    assert info.value.__cause__ is not None


def test_diario_resume_as_duas_falhas(s3_falso, bucket):
    dados = ArmazenamentoS3(bucket)

    with pytest.raises(RuntimeError) as info:
        rodar_diario(dados, HOJE, fetch=fetch_quebrado)

    assert "carga:" in str(info.value) and "previsao:" in str(info.value)
    assert isinstance(info.value.__cause__, ConnectionError)  # encadeia o primeiro erro


def test_handler_usa_volt_dados_e_relogio(dados, bucket, monkeypatch):
    monkeypatch.setenv("VOLT_DADOS", f"s3://{bucket}")
    monkeypatch.setattr(lambda_diario, "hoje_brasilia", lambda: HOJE)
    monkeypatch.setattr(lambda_diario, "baixar_ano", fetch_ok)

    resultado = lambda_diario.handler({}, None)

    assert resultado["previsao"].endswith(chave_previsao(date(2026, 11, 26)))
    assert dados.existe(chave_carga(HOJE - timedelta(days=1)))


def test_handler_registra_versao_do_boto3_datas_e_resultado(dados, bucket, monkeypatch, caplog):
    import boto3

    monkeypatch.setenv("VOLT_DADOS", f"s3://{bucket}")
    monkeypatch.setattr(lambda_diario, "hoje_brasilia", lambda: HOJE)
    monkeypatch.setattr(lambda_diario, "baixar_ano", fetch_ok)

    with caplog.at_level(logging.INFO, logger="volt.lambda_diario"):
        lambda_diario.handler({}, None)

    texto = caplog.text
    assert boto3.__version__ in texto
    assert "2026-11-24" in texto and "2026-11-26" in texto  # ontem e amanhã
    assert "carga" in texto and "previsao" in texto  # o resultado final
