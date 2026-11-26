from datetime import date, timedelta
from pathlib import Path

from volt.armazenamento import ArmazenamentoS3, chave_carga, chave_previsao
from volt.etl import rodar_etl
from volt.previsao import rodar_previsao

FIXTURE = Path(__file__).parent / "fixtures" / "ons_amostra.csv"


def test_etl_e_previsao_no_s3(s3_falso, bucket):
    dados = ArmazenamentoS3(bucket)
    texto = FIXTURE.read_text()
    for i in range(8):  # histórico de 17 a 24/11/2026
        rodar_etl(date(2026, 11, 17) + timedelta(days=i), dados, fetch=lambda ano: texto)
    assert dados.existe(chave_carga(date(2026, 11, 24)))

    destino = rodar_previsao(date(2026, 11, 25), dados)

    assert destino == f"s3://{bucket}/{chave_previsao(date(2026, 11, 25))}"
    previsao = dados.ler_parquet(chave_previsao(date(2026, 11, 25)))
    assert len(previsao) == 24
    assert (previsao["versao_modelo"] == "naive_sazonal").all()
