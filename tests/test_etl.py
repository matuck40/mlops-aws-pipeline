from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from volt.etl import DiaInvalidoError, caminho_carga, ler_csv_ons, rodar_etl, validar_dia

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


def test_caminho_carga(tmp_path):
    esperado = tmp_path / "carga_horaria" / "data=2026-11-24" / "carga.parquet"
    assert caminho_carga(tmp_path, date(2026, 11, 24)) == esperado


def test_rodar_etl_grava_24_linhas(tmp_path):
    caminho = rodar_etl(date(2026, 11, 24), tmp_path, fetch=fetch_falso)
    assert caminho == caminho_carga(tmp_path, date(2026, 11, 24))
    gravado = pd.read_parquet(caminho)
    assert list(gravado.columns) == ["timestamp", "carga_mw"]
    assert len(gravado) == 24


def test_rodar_etl_idempotente(tmp_path):
    rodar_etl(date(2026, 11, 24), tmp_path, fetch=fetch_falso)
    caminho = rodar_etl(date(2026, 11, 24), tmp_path, fetch=fetch_falso)
    assert len(pd.read_parquet(caminho)) == 24


def test_rodar_etl_dia_nao_publicado_nao_grava(tmp_path):
    with pytest.raises(DiaInvalidoError):
        rodar_etl(date(2026, 11, 25), tmp_path, fetch=fetch_falso)
    assert not caminho_carga(tmp_path, date(2026, 11, 25)).exists()


def test_rodar_etl_usa_ano_do_dia(tmp_path):
    anos_pedidos = []

    def fetch_espiao(ano: int) -> str:
        anos_pedidos.append(ano)
        return FIXTURE.read_text()

    with pytest.raises(DiaInvalidoError):  # a fixture não tem 31/12/2025
        rodar_etl(date(2025, 12, 31), tmp_path, fetch=fetch_espiao)
    assert anos_pedidos == [2025]


def test_rodar_etl_ano_ainda_nao_publicado(tmp_path):
    import requests

    def fetch_404(ano: int) -> str:
        resposta = requests.Response()
        resposta.status_code = 404
        raise requests.HTTPError(response=resposta)

    with pytest.raises(DiaInvalidoError, match="ainda não publicado"):
        rodar_etl(date(2027, 1, 1), tmp_path, fetch=fetch_404)
    assert not (tmp_path / "carga_horaria").exists()


def test_rodar_etl_falha_na_gravacao_nao_deixa_lixo(tmp_path, monkeypatch):
    def grava_pela_metade(self, caminho, **kwargs):
        Path(caminho).write_text("meio arquivo")
        raise OSError("disco cheio")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", grava_pela_metade)
    with pytest.raises(OSError):
        rodar_etl(date(2026, 11, 24), tmp_path, fetch=fetch_falso)
    pasta = caminho_carga(tmp_path, date(2026, 11, 24)).parent
    assert list(pasta.iterdir()) == []
