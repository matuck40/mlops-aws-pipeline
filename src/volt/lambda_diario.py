"""Lambda diária: ETL de ontem + previsão de amanhã (fuso de Brasília)."""

import logging
from datetime import date, timedelta

from volt.armazenamento import Armazenamento, abrir_armazenamento
from volt.etl import baixar_ano, rodar_etl
from volt.previsao import rodar_previsao
from volt.tempo import hoje_brasilia

logger = logging.getLogger(__name__)
# Na Lambda o logger raiz está em WARNING e já tem um handler: só ajustamos o nível
# deste módulo (sem basicConfig/handler novo, para não duplicar as linhas no CloudWatch).
logger.setLevel(logging.INFO)


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
    import boto3  # já vem no runtime da Lambda; a versão é registrada para comparar com o pin local

    hoje = hoje_brasilia()
    logger.info("boto3 %s", boto3.__version__)
    logger.info("rodando: ontem=%s amanha=%s", hoje - timedelta(days=1), hoje + timedelta(days=1))
    resultado = rodar_diario(abrir_armazenamento(), hoje, fetch=baixar_ano)
    logger.info("resultado: %s", resultado)
    return resultado
