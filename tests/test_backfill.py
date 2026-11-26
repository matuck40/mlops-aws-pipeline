from datetime import date
from pathlib import Path

import pytest

from volt import backfill
from volt.armazenamento import ArmazenamentoLocal, ArmazenamentoS3, chave_carga
from volt.backfill import rodar_backfill

FIXTURE = Path(__file__).parent / "fixtures" / "ons_amostra.csv"


class FetchFalso:
    """Devolve o CSV da amostra para qualquer ano e conta as chamadas."""

    def __init__(self, texto: str | None = None):
        self.texto = texto if texto is not None else FIXTURE.read_text()
        self.anos: list[int] = []

    def __call__(self, ano: int) -> str:
        self.anos.append(ano)
        return self.texto


@pytest.fixture
def dados(tmp_path):
    return ArmazenamentoLocal(tmp_path)


def test_backfill_baixa_cada_ano_uma_vez(dados):
    fetch = FetchFalso()
    # cruza a virada de ano; 27 dias em 2026 não estão na amostra e falham, sem problema
    rodar_backfill(date(2025, 12, 20), date(2026, 1, 10), dados, fetch=fetch)
    assert fetch.anos == [2025, 2026]


def test_backfill_grava_dias_validos_e_devolve_os_que_faltam(dados):
    falhas = rodar_backfill(date(2026, 11, 22), date(2026, 11, 26), dados, fetch=FetchFalso())
    assert falhas == [date(2026, 11, 25), date(2026, 11, 26)]
    for dia in (date(2026, 11, 22), date(2026, 11, 23), date(2026, 11, 24)):
        assert len(dados.ler_parquet(chave_carga(dia))) == 24
    assert not dados.existe(chave_carga(date(2026, 11, 25)))


def test_backfill_continua_apos_dia_invalido(dados):
    # apaga a última hora de 2026-11-20: o dia fica com 23 linhas
    linhas = FIXTURE.read_text().splitlines(keepends=True)
    estragado = "".join(
        l for l in linhas if not ("SE;" in l and "2026-11-20 23:00:00" in l)
    )
    falhas = rodar_backfill(
        date(2026, 11, 19), date(2026, 11, 21), dados, fetch=FetchFalso(estragado)
    )
    assert falhas == [date(2026, 11, 20)]
    assert dados.existe(chave_carga(date(2026, 11, 19)))
    assert dados.existe(chave_carga(date(2026, 11, 21)))
    assert not dados.existe(chave_carga(date(2026, 11, 20)))


def test_backfill_inicio_depois_do_fim(dados):
    fetch = FetchFalso()
    with pytest.raises(ValueError, match="início"):
        rodar_backfill(date(2026, 11, 24), date(2026, 11, 23), dados, fetch=fetch)
    assert fetch.anos == []


def test_backfill_ano_nao_publicado_conta_todos_os_dias_como_falha(dados):
    import requests

    def fetch(ano):
        resposta = requests.Response()
        resposta.status_code = 404
        raise requests.HTTPError(response=resposta)

    falhas = rodar_backfill(date(2027, 1, 1), date(2027, 1, 3), dados, fetch=fetch)
    assert falhas == [date(2027, 1, 1), date(2027, 1, 2), date(2027, 1, 3)]


def test_backfill_erro_de_rede_propaga(dados):
    def fetch(ano):
        raise ConnectionError("sem rede")

    with pytest.raises(ConnectionError):
        rodar_backfill(date(2026, 11, 20), date(2026, 11, 21), dados, fetch=fetch)


def test_backfill_no_s3(s3_falso, bucket):
    dados = ArmazenamentoS3(bucket)
    falhas = rodar_backfill(date(2026, 11, 17), date(2026, 11, 24), dados, fetch=FetchFalso())
    assert falhas == []
    chaves = [o["Key"] for o in s3_falso.list_objects_v2(Bucket=bucket)["Contents"]]
    assert sorted(chaves) == [chave_carga(date(2026, 11, d)) for d in range(17, 25)]


def test_cli_grava_e_sai_com_zero(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("VOLT_DADOS", str(tmp_path))
    monkeypatch.setattr(backfill, "baixar_ano", FetchFalso())
    backfill.main(["2026-11-22", "2026-11-24"])
    assert "3 dias gravados" in capsys.readouterr().out
    assert (tmp_path / chave_carga(date(2026, 11, 22))).is_file()


def test_cli_sai_com_erro_se_algum_dia_falhou(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("VOLT_DADOS", str(tmp_path))
    monkeypatch.setattr(backfill, "baixar_ano", FetchFalso())
    with pytest.raises(SystemExit) as saida:
        backfill.main(["2026-11-24", "2026-11-25"])
    assert saida.value.code == 1
    saida_texto = capsys.readouterr().out
    assert "1 dias gravados" in saida_texto
    assert "2026-11-25" in saida_texto
