import importlib
import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

from volt.armazenamento import ArmazenamentoS3
from volt.etl import rodar_etl
from volt.previsao import rodar_previsao

# O Mangum chama asyncio.get_event_loop() sem loop ativo (aviso interno dele, inofensivo na Lambda)
pytestmark = pytest.mark.filterwarnings("ignore:There is no current event loop:DeprecationWarning")

FIXTURE = Path(__file__).parent / "fixtures" / "ons_amostra.csv"


def evento(caminho: str, query: str = "") -> dict:
    """Evento falso no formato do API Gateway HTTP API (payload 2.0)."""
    return {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": caminho,
        "rawQueryString": query,
        "headers": {"host": "exemplo.execute-api.us-east-2.amazonaws.com"},
        "requestContext": {
            "http": {
                "method": "GET",
                "path": caminho,
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
                "userAgent": "pytest",
            },
            "stage": "$default",
        },
        "isBase64Encoded": False,
    }


@pytest.fixture
def lambda_api(s3_falso, bucket, monkeypatch):
    """Módulo lambda_api importado DENTRO do S3 falso (ele abre o armazenamento ao importar)."""
    dados = ArmazenamentoS3(bucket)
    texto = FIXTURE.read_text()
    for i in range(8):
        rodar_etl(date(2026, 11, 17) + timedelta(days=i), dados, fetch=lambda ano: texto)
    rodar_previsao(date(2026, 11, 25), dados)

    monkeypatch.setenv("VOLT_DADOS", f"s3://{bucket}")
    sys.modules.pop("volt.lambda_api", None)
    modulo = importlib.import_module("volt.lambda_api")
    yield modulo
    sys.modules.pop("volt.lambda_api", None)


def test_api_lambda_200(lambda_api):
    resposta = lambda_api.handler(evento("/previsao", "data=2026-11-25"), None)

    assert resposta["statusCode"] == 200
    corpo = json.loads(resposta["body"])
    assert corpo["data"] == "2026-11-25"
    assert len(corpo["previsoes"]) == 24


def test_api_lambda_404(lambda_api):
    resposta = lambda_api.handler(evento("/previsao", "data=2030-01-01"), None)
    assert resposta["statusCode"] == 404


def test_api_lambda_400(lambda_api):
    resposta = lambda_api.handler(evento("/previsao", "data=banana"), None)
    assert resposta["statusCode"] == 400


def test_api_lambda_health(lambda_api):
    resposta = lambda_api.handler(evento("/health"), None)
    assert resposta["statusCode"] == 200


def test_lambda_api_nao_importa_etl(tmp_path):
    # processo novo e VOLT_DADOS local: não precisa de AWS
    codigo = "import sys, volt.lambda_api; print('volt.etl' in sys.modules, 'requests' in sys.modules)"
    saida = subprocess.run(
        [sys.executable, "-c", codigo],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "VOLT_DADOS": str(tmp_path)},
    )
    assert saida.stdout.strip() == "False False"
