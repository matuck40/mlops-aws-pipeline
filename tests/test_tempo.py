from datetime import date, datetime, timezone

from volt.tempo import hoje_brasilia


def test_hoje_brasilia_perto_da_meia_noite():
    # 01:30 UTC de 27/11 ainda é 22:30 de 26/11 em Brasília (UTC-3)
    agora = lambda: datetime(2026, 11, 27, 1, 30, tzinfo=timezone.utc)
    assert hoje_brasilia(agora) == date(2026, 11, 26)


def test_hoje_brasilia_mesmo_dia_que_utc():
    # 15:00 UTC = 12:00 em Brasília: as datas coincidem (prova a conversão, não um deslocamento fixo)
    agora = lambda: datetime(2026, 11, 27, 15, 0, tzinfo=timezone.utc)
    assert hoje_brasilia(agora) == date(2026, 11, 27)


def test_hoje_brasilia_padrao_devolve_data():
    assert isinstance(hoje_brasilia(), date)
