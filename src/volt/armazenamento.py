"""Onde o pipeline guarda e lê seus arquivos.

As etapas só conhecem "chaves" (ex.: carga_horaria/data=2026-11-24/carga.parquet)
e pedem ao armazenamento para ler ou gravar. Assim a mesma etapa roda com uma
pasta local ou, mais tarde, com um bucket do S3.
"""

import io
import os
from datetime import date
from pathlib import Path
from typing import Protocol

import boto3
import pandas as pd
from botocore.exceptions import ClientError


def chave_carga(dia: date) -> str:
    return f"carga_horaria/data={dia}/carga.parquet"


def chave_previsao(data_alvo: date) -> str:
    return f"previsoes/data_alvo={data_alvo}/previsao.parquet"


class Armazenamento(Protocol):
    """O que toda forma de guardar arquivos precisa saber fazer."""

    def existe(self, chave: str) -> bool: ...

    def ler_parquet(self, chave: str) -> pd.DataFrame:
        """Chave ausente levanta FileNotFoundError, em qualquer implementação."""
        ...

    def gravar_parquet(self, df: pd.DataFrame, chave: str) -> str: ...


class ArmazenamentoLocal:
    """Guarda os arquivos numa pasta do disco."""

    def __init__(self, base: Path):
        self.base = base

    def existe(self, chave: str) -> bool:
        return (self.base / chave).is_file()  # pasta não conta, como no S3

    def ler_parquet(self, chave: str) -> pd.DataFrame:
        # partitioning=None: sem isso, o pyarrow 24 cria uma coluna a partir da pasta data=...
        return pd.read_parquet(self.base / chave, partitioning=None)

    def gravar_parquet(self, df: pd.DataFrame, chave: str) -> str:
        """Grava num .tmp e renomeia: ou existe o arquivo completo, ou nenhum."""
        caminho = self.base / chave
        caminho.parent.mkdir(parents=True, exist_ok=True)
        temporario = caminho.with_suffix(".tmp")
        try:
            df.to_parquet(temporario, index=False)
            os.replace(temporario, caminho)
        finally:
            temporario.unlink(missing_ok=True)  # se falhou no meio, não deixa lixo
        return str(caminho)


class ArmazenamentoS3:
    """Guarda os arquivos num bucket do S3 (a chave vira o nome do objeto)."""

    def __init__(self, bucket: str, cliente=None):
        self.bucket = bucket
        # criado aqui, nunca na importação do módulo: os testes preparam o ambiente antes
        self.cliente = cliente or boto3.client("s3")

    def existe(self, chave: str) -> bool:
        try:
            self.cliente.head_object(Bucket=self.bucket, Key=chave)
        except ClientError as erro:
            if erro.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
                return False
            raise  # 403, bucket inexistente etc. não podem virar "não existe"
        return True

    def ler_parquet(self, chave: str) -> pd.DataFrame:
        try:
            resposta = self.cliente.get_object(Bucket=self.bucket, Key=chave)
        except ClientError as erro:
            if erro.response["Error"]["Code"] in ("404", "NoSuchKey"):
                raise FileNotFoundError(f"s3://{self.bucket}/{chave}") from erro
            raise
        return pd.read_parquet(io.BytesIO(resposta["Body"].read()))

    def gravar_parquet(self, df: pd.DataFrame, chave: str) -> str:
        conteudo = io.BytesIO()
        df.to_parquet(conteudo, index=False)
        self.cliente.put_object(Bucket=self.bucket, Key=chave, Body=conteudo.getvalue())
        return f"s3://{self.bucket}/{chave}"


def abrir_armazenamento(destino: str | None = None) -> Armazenamento:
    """Usa o destino dado, senão a variável VOLT_DADOS, senão a pasta "data".

    Um destino "s3://bucket" usa o S3; qualquer outro valor é uma pasta local.
    """
    destino = destino or os.environ.get("VOLT_DADOS") or "data"  # vazia também cai no padrão
    if destino.startswith("s3://"):
        bucket = destino.removeprefix("s3://").strip("/")
        if not bucket:
            raise ValueError(f"destino S3 sem nome de bucket: {destino!r}")
        return ArmazenamentoS3(bucket)
    return ArmazenamentoLocal(Path(destino))
