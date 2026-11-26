from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from volt.armazenamento import ArmazenamentoLocal, chave_carga
from volt.etl import DiaInvalidoError, ler_csv_ons, rodar_etl, validar_dia

FIXTURE = Path(__file__).parent / "fixtures" / "ons_amostra.csv"


@pytest.fixture
def df():
    return ler_csv_ons(FIXTURE.read_text())


def test_ler_filtra_subsistema(df):
    # a amostra tem SE e N; só o SE deve sobrar: 8 dias x 24 horas
    assert list(df.columns) == ["timestamp", "carga_mw"]
    assert len(df) == 8 * 24


def test_ler_converte_tipos(df):
    assert pd.api.types.is_datetime64_any_dtype(df["timestamp"])
    assert pd.api.types.is_float_dtype(df["carga_mw"])
    assert df["timestamp"].is_monotonic_increasing


def test_validar_dia_ok(df):
    dia = validar_dia(df, date(2026, 11, 24))
    assert len(dia) == 24
    assert (dia["timestamp"].dt.date == date(2026, 11, 24)).all()


def test_validar_dia_ausente(df):
    with pytest.raises(DiaInvalidoError, match="ainda não publicado"):
        validar_dia(df, date(2026, 11, 25))


def test_validar_dia_hora_faltando(df):
    sem_uma_hora = df.drop(df.index[-1])
    with pytest.raises(DiaInvalidoError):
        validar_dia(sem_uma_hora, date(2026, 11, 24))


def test_validar_dia_hora_repetida(df):
    # 24 linhas, mas a hora 22 aparece duas vezes e a 23 some
    df.loc[df.index[-1], "timestamp"] = pd.Timestamp("2026-11-24 22:00")
    with pytest.raises(DiaInvalidoError, match="faltando: \\[23\\].*repetidas: \\[22\\]"):
        validar_dia(df, date(2026, 11, 24))


def test_valor_estragado_afeta_so_o_proprio_dia():
    texto = FIXTURE.read_text().replace(
        "SE;SUDESTE/CENTRO-OESTE;2026-11-17 05:00:00;", "SE;SUDESTE/CENTRO-OESTE;2026-11-17 05:00:00;n/d#", 1
    )
    df = ler_csv_ons(texto)
    assert len(validar_dia(df, date(2026, 11, 24))) == 24
    with pytest.raises(DiaInvalidoError):
        validar_dia(df, date(2026, 11, 17))


def test_validar_carga_nao_positiva(df):
    df.loc[df.index[-1], "carga_mw"] = 0.0
    with pytest.raises(DiaInvalidoError):
        validar_dia(df, date(2026, 11, 24))


def test_validar_carga_nula(df):
    df.loc[df.index[-1], "carga_mw"] = float("nan")
    with pytest.raises(DiaInvalidoError):
        validar_dia(df, date(2026, 11, 24))


# --- Tarefa 3: buscar, gravar e rodar um dia ---


def fetch_falso(ano: int) -> str:
    return FIXTURE.read_text()


@pytest.fixture
def dados(tmp_path):
    return ArmazenamentoLocal(tmp_path)


def test_rodar_etl_grava_24_linhas(dados):
    destino = rodar_etl(date(2026, 11, 24), dados, fetch=fetch_falso)
    assert destino == str(dados.base / chave_carga(date(2026, 11, 24)))
    gravado = dados.ler_parquet(chave_carga(date(2026, 11, 24)))
    assert list(gravado.columns) == ["timestamp", "carga_mw"]
    assert len(gravado) == 24


def test_rodar_etl_idempotente(dados):
    rodar_etl(date(2026, 11, 24), dados, fetch=fetch_falso)
    rodar_etl(date(2026, 11, 24), dados, fetch=fetch_falso)
    assert len(dados.ler_parquet(chave_carga(date(2026, 11, 24)))) == 24


def test_rodar_etl_dia_nao_publicado_nao_grava(dados):
    with pytest.raises(DiaInvalidoError):
        rodar_etl(date(2026, 11, 25), dados, fetch=fetch_falso)
    assert not dados.existe(chave_carga(date(2026, 11, 25)))


def test_rodar_etl_usa_ano_do_dia(dados):
    anos_pedidos = []

    def fetch_espiao(ano: int) -> str:
        anos_pedidos.append(ano)
        return FIXTURE.read_text()

    with pytest.raises(DiaInvalidoError):  # a fixture não tem 31/12/2025
        rodar_etl(date(2025, 12, 31), dados, fetch=fetch_espiao)
    assert anos_pedidos == [2025]


def test_rodar_etl_ano_ainda_nao_publicado(dados):
    import requests

    def fetch_404(ano: int) -> str:
        resposta = requests.Response()
        resposta.status_code = 404
        raise requests.HTTPError(response=resposta)

    with pytest.raises(DiaInvalidoError, match="ainda não publicado"):
        rodar_etl(date(2027, 1, 1), dados, fetch=fetch_404)
    assert not (dados.base / "carga_horaria").exists()
