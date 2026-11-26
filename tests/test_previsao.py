from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from volt.armazenamento import ArmazenamentoLocal, chave_carga, chave_previsao
from volt.etl import rodar_etl
from volt.previsao import main, naive_sazonal, rodar_previsao

FIXTURE = Path(__file__).parent / "fixtures" / "ons_amostra.csv"


@pytest.fixture
def base(tmp_path):
    """Armazenamento com o histórico da fixture: 17 a 24/11/2026."""
    dados = ArmazenamentoLocal(tmp_path)
    texto = FIXTURE.read_text()
    for i in range(8):
        rodar_etl(date(2026, 11, 17) + timedelta(days=i), dados, fetch=lambda ano: texto)
    return dados


def test_naive_copia_semana_anterior(base):
    previsao = naive_sazonal(base, date(2026, 11, 25))
    referencia = base.ler_parquet(chave_carga(date(2026, 11, 18)))
    assert previsao["previsto_mw"].tolist() == referencia["carga_mw"].tolist()
    assert (previsao["versao_modelo"] == "naive_sazonal").all()


def test_naive_timestamps_do_alvo(base):
    previsao = naive_sazonal(base, date(2026, 11, 25))
    esperado = pd.date_range("2026-11-25 00:00", "2026-11-25 23:00", freq="h")
    assert previsao["timestamp"].tolist() == esperado.tolist()


def test_naive_sem_referencia(base):
    assert len(naive_sazonal(base, date(2026, 11, 30))) == 24  # referência 23/11 existe
    with pytest.raises(FileNotFoundError, match="2026-11-28"):
        naive_sazonal(base, date(2026, 12, 5))  # referência 28/11 não existe


def test_rodar_previsao_idempotente(base):
    rodar_previsao(date(2026, 11, 25), base)
    destino = rodar_previsao(date(2026, 11, 25), base)
    assert destino == str(base.base / chave_previsao(date(2026, 11, 25)))
    gravado = base.ler_parquet(chave_previsao(date(2026, 11, 25)))
    assert list(gravado.columns) == ["timestamp", "previsto_mw", "versao_modelo"]
    assert len(gravado) == 24


def test_cli_usa_volt_dados(base, monkeypatch):
    monkeypatch.setenv("VOLT_DADOS", str(base.base))
    main(["2026-11-25"])
    assert base.existe(chave_previsao(date(2026, 11, 25)))
