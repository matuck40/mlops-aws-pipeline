"""Backfill: carrega um período de dias no armazenamento, baixando cada ano uma só vez."""

import argparse
import sys
from collections.abc import Callable
from datetime import date, timedelta

import pandas as pd

from volt.armazenamento import Armazenamento, abrir_armazenamento, chave_carga
from volt.etl import DiaInvalidoError, baixar_ano, buscar_ano, ler_csv_ons, validar_dia


def rodar_backfill(
    inicio: date,
    fim: date,
    dados: Armazenamento,
    fetch: Callable[[int], str] = baixar_ano,
) -> list[date]:
    """Grava cada dia válido de inicio a fim (inclusive); devolve os dias que falharam.

    Um dia inválido não interrompe o resto. Erros de rede ou de armazenamento
    sobem normalmente: o backfill é idempotente, então basta rodar de novo.
    """
    if inicio > fim:
        raise ValueError(f"início {inicio} é depois do fim {fim}")

    dias = [inicio + timedelta(days=n) for n in range((fim - inicio).days + 1)]
    falhas: list[date] = []
    tabela_do_ano: dict[int, pd.DataFrame | None] = {}  # None = ano não publicado

    for dia in dias:
        if dia.year not in tabela_do_ano:  # um download (e uma leitura) por ano
            try:
                tabela_do_ano[dia.year] = ler_csv_ons(buscar_ano(dia.year, fetch))
            except DiaInvalidoError:
                tabela_do_ano[dia.year] = None
        tabela = tabela_do_ano[dia.year]
        if tabela is None:
            falhas.append(dia)
            continue
        try:
            do_dia = validar_dia(tabela, dia)
        except DiaInvalidoError:
            falhas.append(dia)
            continue
        dados.gravar_parquet(do_dia, chave_carga(dia))
    return sorted(falhas)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Backfill da carga horária do ONS (SE/CO)")
    parser.add_argument("inicio", type=date.fromisoformat, help="primeiro dia, AAAA-MM-DD")
    parser.add_argument("fim", type=date.fromisoformat, help="último dia (inclusive), AAAA-MM-DD")
    args = parser.parse_args(argv)

    falhas = rodar_backfill(args.inicio, args.fim, abrir_armazenamento(), fetch=baixar_ano)
    total = (args.fim - args.inicio).days + 1
    print(f"{total - len(falhas)} dias gravados")
    if falhas:
        print(f"{len(falhas)} dias falharam: {', '.join(map(str, falhas))}")
        sys.exit(1)


if __name__ == "__main__":
    main()
