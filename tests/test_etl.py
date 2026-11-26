from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from volt.etl import DiaInvalidoError, ler_csv_ons, validar_dia

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
    with pytest.raises(DiaInvalidoError):
        validar_dia(df, date(2026, 11, 25))


def test_validar_dia_hora_faltando(df):
    sem_uma_hora = df.drop(df.index[-1])
    with pytest.raises(DiaInvalidoError):
        validar_dia(sem_uma_hora, date(2026, 11, 24))


def test_validar_carga_nao_positiva(df):
    df.loc[df.index[-1], "carga_mw"] = 0.0
    with pytest.raises(DiaInvalidoError):
        validar_dia(df, date(2026, 11, 24))


def test_validar_carga_nula(df):
    df.loc[df.index[-1], "carga_mw"] = float("nan")
    with pytest.raises(DiaInvalidoError):
        validar_dia(df, date(2026, 11, 24))
