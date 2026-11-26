"""Datas no fuso do Brasil. A Lambda roda em UTC, então 'hoje' precisa ser convertido."""

from collections.abc import Callable
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("America/Sao_Paulo")


def hoje_brasilia(agora: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> date:
    """Data atual em Brasília. `agora` deve devolver um datetime com fuso (injetável em testes)."""
    return agora().astimezone(FUSO).date()
