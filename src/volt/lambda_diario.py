"""Lambda diária: ETL de ontem + previsão de amanhã (fuso de Brasília)."""

import logging
from datetime import date, timedelta

from volt.armazenamento import Armazenamento, abrir_armazenamento
from volt.etl import baixar_ano, rodar_etl
from volt.previsao import rodar_previsao
from volt.tempo import hoje_brasilia

logger = logging.getLogger(__name__)


def rodar_diario(dados: Armazenamento, hoje: date, fetch=baixar_ano) -> dict:
    """Roda o ETL de ontem e a previsão de amanhã; as duas rodam mesmo se uma falhar.

    Cada etapa é isolada: o erro é registrado no log e só levantado no final.
    """
    ontem = hoje - timedelta(days=1)
    amanha = hoje + timedelta(days=1)
    etapas = {
        "carga": lambda: rodar_etl(ontem, dados, fetch=fetch),
        "previsao": lambda: rodar_previsao(amanha, dados),
    }

    resultado: dict[str, str] = {}
    erros: dict[str, Exception] = {}
    for nome, executar in etapas.items():
        try:
            resultado[nome] = executar()
        except Exception as erro:
            logger.exception("etapa %s falhou", nome)
            erros[nome] = erro

    if erros:
        resumo = "; ".join(f"{nome}: {erro}" for nome, erro in erros.items())
        raise RuntimeError(f"etapas com falha: {resumo}") from next(iter(erros.values()))
    return resultado


def handler(event, context) -> dict:
    """Ponto de entrada da Lambda. O armazenamento é criado aqui, não na importação."""
    return rodar_diario(abrir_armazenamento(), hoje_brasilia(), fetch=baixar_ano)
