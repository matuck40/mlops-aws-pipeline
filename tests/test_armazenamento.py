from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from botocore.exceptions import ClientError

from volt.armazenamento import (
    ArmazenamentoLocal,
    ArmazenamentoS3,
    abrir_armazenamento,
    chave_carga,
    chave_previsao,
)


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


@pytest.fixture(params=["local", "s3"])
def dados(request, tmp_path):
    """As duas implementações de Armazenamento: os testes de contrato rodam nas duas."""
    if request.param == "local":
        return ArmazenamentoLocal(tmp_path)
    request.getfixturevalue("s3_falso")  # liga o S3 de mentira antes de criar o cliente
    return ArmazenamentoS3(request.getfixturevalue("bucket"))


def test_grava_e_le(dados, df):
    dados.gravar_parquet(df, "pasta/arquivo.parquet")
    pd.testing.assert_frame_equal(dados.ler_parquet("pasta/arquivo.parquet"), df)


def test_existe(dados, df):
    assert not dados.existe("pasta/arquivo.parquet")
    dados.gravar_parquet(df, "pasta/arquivo.parquet")
    assert dados.existe("pasta/arquivo.parquet")


def test_le_sem_coluna_da_pasta(dados, df):
    # o pyarrow 24 criaria uma coluna "data" a partir do nome da pasta data=2026-11-24
    chave = chave_carga(date(2026, 11, 24))
    dados.gravar_parquet(df, chave)
    assert list(dados.ler_parquet(chave).columns) == ["timestamp", "carga_mw"]


def test_ler_chave_ausente_da_file_not_found(dados):
    with pytest.raises(FileNotFoundError):
        dados.ler_parquet("nao/existe.parquet")


def test_pasta_nao_conta_como_arquivo(dados, df):
    dados.gravar_parquet(df, "carga_horaria/arquivo.parquet")
    assert not dados.existe("carga_horaria")


def test_local_grava_devolve_o_caminho(tmp_path, df):
    destino = ArmazenamentoLocal(tmp_path).gravar_parquet(df, "pasta/arquivo.parquet")
    assert destino == str(tmp_path / "pasta" / "arquivo.parquet")


def test_local_falha_nao_deixa_lixo(tmp_path, df, monkeypatch):
    def grava_pela_metade(self, caminho, **kwargs):
        Path(caminho).write_text("meio arquivo")
        raise OSError("disco cheio")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", grava_pela_metade)
    dados = ArmazenamentoLocal(tmp_path)
    with pytest.raises(OSError):
        dados.gravar_parquet(df, "pasta/arquivo.parquet")
    assert list((tmp_path / "pasta").iterdir()) == []


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


def test_abrir_armazenamento_variavel_vazia_usa_padrao(monkeypatch):
    monkeypatch.setenv("VOLT_DADOS", "")
    assert abrir_armazenamento().base == Path("data")


# --- S3 (com moto) ---


def test_s3_grava_devolve_uri(s3_falso, bucket, df):
    destino = ArmazenamentoS3(bucket).gravar_parquet(df, "pasta/arquivo.parquet")
    assert destino == f"s3://{bucket}/pasta/arquivo.parquet"


def test_s3_chave_no_lugar_certo(s3_falso, bucket, df):
    ArmazenamentoS3(bucket).gravar_parquet(df, chave_carga(date(2026, 11, 24)))
    listagem = s3_falso.list_objects_v2(Bucket=bucket)
    assert [o["Key"] for o in listagem["Contents"]] == ["carga_horaria/data=2026-11-24/carga.parquet"]


def test_s3_erro_diferente_de_404_nao_vira_false(s3_falso):
    with pytest.raises(ClientError):
        ArmazenamentoS3("bucket-que-nao-existe").existe("qualquer.parquet")


def test_abrir_armazenamento_s3(s3_falso):  # a fixture isola região e credenciais do ambiente
    dados = abrir_armazenamento("s3://meu-bucket")
    assert isinstance(dados, ArmazenamentoS3)
    assert dados.bucket == "meu-bucket"


def test_abrir_armazenamento_s3_pela_variavel(s3_falso, monkeypatch):
    monkeypatch.setenv("VOLT_DADOS", "s3://meu-bucket")
    assert abrir_armazenamento().bucket == "meu-bucket"


@pytest.mark.parametrize("destino", ["s3://", "s3:///"])
def test_abrir_armazenamento_s3_sem_bucket(destino):
    with pytest.raises(ValueError, match="bucket"):
        abrir_armazenamento(destino)
