import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from volt.api import criar_app
from volt.armazenamento import ArmazenamentoLocal
from volt.etl import rodar_etl
from volt.previsao import rodar_previsao

FIXTURE = Path(__file__).parent / "fixtures" / "ons_amostra.csv"


@pytest.fixture
def base(tmp_path):
    """Histórico de 17 a 24/11 e a previsão de 25/11 já gravada."""
    dados = ArmazenamentoLocal(tmp_path)
    texto = FIXTURE.read_text()
    for i in range(8):
        rodar_etl(date(2026, 11, 17) + timedelta(days=i), dados, fetch=lambda ano: texto)
    rodar_previsao(date(2026, 11, 25), dados)
    return dados


@pytest.fixture
def cliente(base):
    return TestClient(criar_app(base, hoje=lambda: date(2026, 11, 24)))


def test_health(cliente):
    resposta = cliente.get("/health")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}


def test_previsao_200_com_24_itens(cliente):
    resposta = cliente.get("/previsao", params={"data": "2026-11-25"})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["data"] == "2026-11-25"
    assert corpo["versao_modelo"] == "naive_sazonal"
    assert len(corpo["previsoes"]) == 24
    assert corpo["previsoes"][0]["hora"] == "00:00"
    assert corpo["previsoes"][23]["hora"] == "23:00"
    assert all(item["previsto_mw"] > 0 for item in corpo["previsoes"])


def test_previsao_padrao_amanha(cliente):
    # "hoje" falso = 24/11, então sem parâmetro a API deve ler 25/11
    resposta = cliente.get("/previsao")
    assert resposta.status_code == 200
    assert resposta.json()["data"] == "2026-11-25"


def test_previsao_404_sem_arquivo(cliente):
    resposta = cliente.get("/previsao", params={"data": "2026-11-26"})
    assert resposta.status_code == 404


@pytest.mark.parametrize("data", ["amanha", "2026-13-01"])
def test_previsao_400_data_invalida(cliente, data):
    resposta = cliente.get("/previsao", params={"data": data})
    assert resposta.status_code == 400
    assert "AAAA-MM-DD" in resposta.json()["detail"]


def test_api_nao_importa_etl():
    # processo novo: neste aqui o etl já foi importado pelos outros testes
    codigo = "import sys, volt.api; print('volt.etl' in sys.modules, 'requests' in sys.modules)"
    saida = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, check=True)
    assert saida.stdout.strip() == "False False"


def test_api_nao_cria_app_na_importacao():
    # a Lambda importa volt.api; um `app` global abriria um segundo armazenamento sem uso
    codigo = "import volt.api; print(hasattr(volt.api, 'app'), hasattr(volt.api, 'criar_app_padrao'))"
    saida = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, check=True)
    assert saida.stdout.strip() == "False True"
