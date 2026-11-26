from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from volt.armazenamento import ArmazenamentoLocal, abrir_armazenamento, chave_carga, chave_previsao


@pytest.fixture
def df():
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-11-24 00:00", periods=3, freq="h"),
            "carga_mw": [100.0, 110.0, 120.0],
        }
    )


def test_chaves():
    assert chave_carga(date(2026, 11, 24)) == "carga_horaria/data=2026-11-24/carga.parquet"
    assert chave_previsao(date(2026, 11, 25)) == "previsoes/data_alvo=2026-11-25/previsao.parquet"


def test_local_grava_e_le(tmp_path, df):
    dados = ArmazenamentoLocal(tmp_path)
    destino = dados.gravar_parquet(df, "pasta/arquivo.parquet")
    assert destino == str(tmp_path / "pasta" / "arquivo.parquet")
    pd.testing.assert_frame_equal(dados.ler_parquet("pasta/arquivo.parquet"), df)


def test_local_existe(tmp_path, df):
    dados = ArmazenamentoLocal(tmp_path)
    assert not dados.existe("pasta/arquivo.parquet")
    dados.gravar_parquet(df, "pasta/arquivo.parquet")
    assert dados.existe("pasta/arquivo.parquet")


def test_local_falha_nao_deixa_lixo(tmp_path, df, monkeypatch):
    def grava_pela_metade(self, caminho, **kwargs):
        Path(caminho).write_text("meio arquivo")
        raise OSError("disco cheio")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", grava_pela_metade)
    dados = ArmazenamentoLocal(tmp_path)
    with pytest.raises(OSError):
        dados.gravar_parquet(df, "pasta/arquivo.parquet")
    assert list((tmp_path / "pasta").iterdir()) == []


def test_local_le_sem_coluna_da_pasta(tmp_path, df):
    # o pyarrow 24 criaria uma coluna "data" a partir do nome da pasta data=2026-11-24
    dados = ArmazenamentoLocal(tmp_path)
    chave = chave_carga(date(2026, 11, 24))
    dados.gravar_parquet(df, chave)
    assert list(dados.ler_parquet(chave).columns) == ["timestamp", "carga_mw"]


def test_abrir_armazenamento_local_padrao(monkeypatch):
    monkeypatch.delenv("VOLT_DADOS", raising=False)
    dados = abrir_armazenamento()
    assert isinstance(dados, ArmazenamentoLocal)
    assert dados.base == Path("data")


def test_abrir_armazenamento_usa_variavel(monkeypatch, tmp_path):
    monkeypatch.setenv("VOLT_DADOS", str(tmp_path))
    assert abrir_armazenamento().base == tmp_path


def test_abrir_armazenamento_destino_explicito_vence_variavel(monkeypatch, tmp_path):
    monkeypatch.setenv("VOLT_DADOS", "outra_pasta")
    assert abrir_armazenamento(str(tmp_path)).base == tmp_path


def test_local_ler_chave_ausente_da_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        ArmazenamentoLocal(tmp_path).ler_parquet("nao/existe.parquet")


def test_local_pasta_nao_conta_como_arquivo(tmp_path):
    (tmp_path / "carga_horaria").mkdir()
    assert not ArmazenamentoLocal(tmp_path).existe("carga_horaria")


def test_abrir_armazenamento_variavel_vazia_usa_padrao(monkeypatch):
    monkeypatch.setenv("VOLT_DADOS", "")
    assert abrir_armazenamento().base == Path("data")
