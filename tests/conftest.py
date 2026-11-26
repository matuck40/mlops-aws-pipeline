import boto3
import pytest
from moto import mock_aws

BUCKET = "bucket-de-teste"
REGIAO = "us-east-2"


@pytest.fixture(autouse=True)
def sem_volt_dados(monkeypatch):
    """Nenhum teste herda um VOLT_DADOS (talvez s3://) do terminal de quem roda."""
    monkeypatch.delenv("VOLT_DADOS", raising=False)


@pytest.fixture
def bucket():
    return BUCKET


@pytest.fixture
def s3_falso(monkeypatch):
    """S3 de mentira (moto) com o bucket de teste criado; devolve um cliente boto3.

    As credenciais falsas e a região são definidas ANTES de ligar o mock_aws,
    para o teste nunca falar com a AWS de verdade nem com a internet.
    """
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGIAO)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    with mock_aws():
        cliente = boto3.client("s3")
        cliente.create_bucket(
            Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGIAO}
        )
        yield cliente
