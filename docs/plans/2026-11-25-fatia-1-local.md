# Fatia 1 — Pipeline local (sem AWS) — Plano de implementação

> **Para agentes:** use superpowers:executing-plans (ou subagent-driven-development) para executar tarefa por tarefa. Passos em checkbox (`- [ ]`).

**Objetivo:** no PC, baixar a carga horária do ONS, prever amanhã com o naive sazonal e servir a previsão por uma API, com testes rodando no GitHub Actions.

**Arquitetura:** pacote Python `volt` com um módulo por responsabilidade: `etl` (busca e limpa), `previsao` (gera as 24 horas) e `api` (só lê). Tudo grava e lê numa pasta local `data/`, com a mesma estrutura de pastas que o S3 terá na fatia 2. A troca para a AWS muda só onde se lê e grava.

**Stack:** Python 3.12, uv, pandas, pyarrow, requests, FastAPI, uvicorn, pytest, httpx (cliente de teste do FastAPI).

**Spec:** `docs/SPEC.md` (etapas 1, 3, 4 e 6, em versão mínima).

## Dependências

| Nome | Tipo | Papel | Etapa |
|---|---|---|---|
| uv | ferramenta | cria o ambiente virtual e trava as versões | todas |
| pandas | biblioteca | lê o CSV, filtra e organiza as tabelas | ETL, previsão |
| pyarrow | biblioteca | grava e lê arquivos Parquet (o pandas usa por baixo) | ETL, previsão, API |
| requests | biblioteca | baixa o CSV do ONS pela internet | ETL |
| FastAPI | framework | define os endpoints da API | API |
| uvicorn | ferramenta (servidor) | recebe as requisições HTTP e entrega ao FastAPI | API |
| pytest | ferramenta (testes) | roda os testes | todas |
| httpx | biblioteca | faz requisições falsas à API nos testes | API (testes) |
| GitHub Actions | serviço | roda o pytest a cada push e PR | CI |

## Restrições globais

- Fonte: `https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/curva-carga-ho/CURVA_CARGA_{ano}.csv`, separador `;`, colunas `id_subsistema;nom_subsistema;din_instante;val_cargaenergiahomwmed`.
- Só o subsistema `SE` (Sudeste/Centro-Oeste).
- Timestamps em horário de Brasília, sem fuso no dado (naive).
- Caminhos: `data/carga_horaria/data=AAAA-MM-DD/carga.parquet` e `data/previsoes/data_alvo=AAAA-MM-DD/previsao.parquet`.
- Testes nunca acessam a internet: a busca HTTP é injetada (função `fetch`) e substituída nos testes.
- `data/` não vai para o Git.
- Fluxo Git: uma branch por tarefa → PR → CI verde + revisão por subagente → merge na `main`. Commits em Conventional Commits.

## Foco de revisão

1. **Virada de ano:** em 01/01, o ETL do dia 31/12 precisa buscar o arquivo do ano anterior (o ano vem do `dia`, não de hoje).
2. **Dia ainda não publicado:** o ETL falha com erro claro e não grava nada.
3. **Histórico incompleto:** a previsão para D+1 precisa do dia D-6. Se ele faltar, falha com erro claro, sem previsão parcial.
4. **Data inválida na API:** `?data=amanha` responde 400 (o FastAPI responderia 422 por padrão se o parâmetro fosse do tipo `date`).
5. **Rodar duas vezes:** ETL e previsão sobrescrevem o arquivo do dia, sem duplicar linhas.

---

### Task 1: Esqueleto do projeto + CI

**Branch:** `chore/esqueleto-ci`

**Arquivos:**
- Criar: `pyproject.toml` (via `uv init --package --name volt`), `src/volt/__init__.py`, `.gitignore`, `.github/workflows/ci.yml`, `tests/test_smoke.py`

- [ ] **Passo 1:** `uv init --package --name volt --python 3.12`; `uv add pandas pyarrow requests fastapi uvicorn`; `uv add --dev pytest httpx`.
- [ ] **Passo 2: teste que falha:** `tests/test_smoke.py::test_pacote_importa`, com `import volt` e `assert volt.__version__ == "0.1.0"`.
- [ ] **Passo 3:** `uv run pytest -v`. Esperado: FAIL (`__version__` não existe).
- [ ] **Passo 4:** `__version__ = "0.1.0"` em `src/volt/__init__.py`.
- [ ] **Passo 5:** `uv run pytest -v`. Esperado: 1 passed.
- [ ] **Passo 6:** `.gitignore` com `data/`, `.venv/`, `__pycache__/`, `.pytest_cache/`.
- [ ] **Passo 7:** `ci.yml`: em `push` e `pull_request`, `ubuntu-latest`, `astral-sh/setup-uv`, `uv sync --locked`, `uv run pytest -v`.
- [ ] **Passo 8:** commit, push da branch, abrir PR com `gh pr create`. Esperado: check do CI verde no PR.
- [ ] **Passo 9:** proteger a `main` (exigir o check do CI antes do merge) com `gh api` → merge.

### Task 2: ETL — ler e validar o CSV do ONS

**Branch:** `feat/etl-parse`

**Arquivos:**
- Criar: `src/volt/etl.py`, `tests/test_etl.py`, `tests/fixtures/ons_amostra.csv` (recorte real de 2026-11-17 a 2026-11-24: todas as linhas `SE` + as linhas `N` dos mesmos dias, para testar o filtro)

**Interfaces produzidas:**
- `ler_csv_ons(texto: str, subsistema: str = "SE") -> pd.DataFrame`: colunas `timestamp` (datetime64) e `carga_mw` (float), ordenado por `timestamp`.
- `validar_dia(df: pd.DataFrame, dia: date) -> pd.DataFrame`: devolve só as linhas do `dia`; levanta `DiaInvalidoError` se não houver exatamente 24 horas únicas (0 a 23), houver nulo ou `carga_mw <= 0`.
- `class DiaInvalidoError(ValueError)`

**Testes (`tests/test_etl.py`):**
- `test_ler_filtra_subsistema`: só sobram linhas SE; 8 dias × 24 = 192 linhas.
- `test_ler_converte_tipos`: `timestamp` é datetime e `carga_mw` é float.
- `test_validar_dia_ok`: `validar_dia(df, date(2026,11,24))` devolve 24 linhas.
- `test_validar_dia_ausente`: `date(2026,11,25)` → `DiaInvalidoError`.
- `test_validar_dia_hora_faltando`: tira uma linha → `DiaInvalidoError`.
- `test_validar_carga_nao_positiva`: troca um valor por 0 → `DiaInvalidoError`.

- [ ] Escrever os testes → rodar e ver falhar → implementar → rodar e ver passar → commit → PR → CI verde → revisão → merge.

### Task 3: ETL — buscar, gravar e rodar um dia

**Branch:** `feat/etl-run`

**Interfaces:**
- Consome: `ler_csv_ons`, `validar_dia`.
- Produz:
  - `baixar_ano(ano: int) -> str`: GET na URL da fonte com `timeout=30`, `raise_for_status()`. Não tem teste unitário (é a borda com a internet).
  - `caminho_carga(base: Path, dia: date) -> Path`: devolve `base/"carga_horaria"/f"data={dia}"/"carga.parquet"`.
  - `rodar_etl(dia: date, base: Path, fetch: Callable[[int], str] = baixar_ano) -> Path`: busca o ano de `dia`, lê, valida e grava (sobrescrevendo). Devolve o caminho.
  - CLI: `uv run python -m volt.etl 2026-11-24 [--base data]`.

**Testes:**
- `test_rodar_etl_grava_24_linhas` (fetch falso devolve a fixture; `tmp_path`).
- `test_rodar_etl_idempotente`: roda 2×, ainda 24 linhas.
- `test_rodar_etl_dia_nao_publicado_nao_grava`: `date(2026,11,25)` → `DiaInvalidoError`, e o arquivo não existe.
- `test_rodar_etl_usa_ano_do_dia`: o fetch falso registra o ano pedido; `dia=date(2025,12,31)` → pediu 2025.

- [ ] Ciclo TDD → commit → PR → CI → revisão → merge.

### Task 4: Previsão com o naive sazonal

**Branch:** `feat/previsao-naive`

**Arquivos:** criar `src/volt/previsao.py`, `tests/test_previsao.py`

**Interfaces:**
- Consome: `caminho_carga`, `rodar_etl` (nos testes, para montar o histórico a partir da fixture).
- Produz:
  - `naive_sazonal(base: Path, data_alvo: date) -> pd.DataFrame`: lê o dia `data_alvo - 7 dias` e devolve 24 linhas com `timestamp` (as horas de `data_alvo`), `previsto_mw` e `versao_modelo = "naive_sazonal"`. Levanta `FileNotFoundError` com mensagem clara se o dia de referência faltar.
  - `caminho_previsao(base: Path, data_alvo: date) -> Path`: `base/"previsoes"/f"data_alvo={data_alvo}"/"previsao.parquet"`.
  - `rodar_previsao(data_alvo: date, base: Path) -> Path`: grava, sobrescrevendo.
  - CLI: `uv run python -m volt.previsao 2026-11-26 [--base data]`.

**Testes:**
- `test_naive_copia_semana_anterior`: com o histórico da fixture, alvo 2026-11-25 → `previsto_mw` igual a `carga_mw` de 2026-11-18, hora a hora.
- `test_naive_timestamps_do_alvo`: as 24 horas são de 2026-11-25, de 00:00 a 23:00.
- `test_naive_sem_referencia`: alvo 2026-11-30 (referência 23/11 existe) passa; alvo 2026-12-05 (referência 28/11 não existe) → `FileNotFoundError`.
- `test_rodar_previsao_idempotente`: 2× → 24 linhas.

- [ ] Ciclo TDD → commit → PR → CI → revisão → merge.

### Task 5: API que só lê previsões

**Branch:** `feat/api`

**Arquivos:** criar `src/volt/api.py`, `tests/test_api.py`

**Interfaces:**
- Consome: `caminho_previsao`.
- Produz: `criar_app(base: Path, hoje: Callable[[], date] = date.today) -> FastAPI` (a injeção de `hoje` permite testar o "padrão: amanhã").
  - `GET /health` → `200 {"status": "ok"}`
  - `GET /previsao?data=AAAA-MM-DD` (`data: str | None`; vazio = `hoje() + 1 dia`) → `200 {"data": "...", "versao_modelo": "...", "previsoes": [{"hora": "00:00", "previsto_mw": float}, ... 24 itens]}`; sem arquivo → 404; data que não é `AAAA-MM-DD` válida → 400.
  - `app = criar_app(Path(os.environ.get("VOLT_DATA_DIR", "data")))` para o uvicorn.

**Testes (com `fastapi.testclient.TestClient`):**
- `test_health`
- `test_previsao_200_com_24_itens`
- `test_previsao_padrao_amanha` (`hoje` falso = 2026-11-24 → lê 2026-11-25)
- `test_previsao_404_sem_arquivo`
- `test_previsao_400_data_invalida` (`?data=amanha` e `?data=2026-13-01`)

- [ ] Ciclo TDD → commit → PR → CI → revisão → merge.

### Task 6: Ponta a ponta de verdade + README

**Branch:** `docs/fatia-1`

- [ ] Rodar o ETL de 2026-11-18 a 2026-11-24 (dados reais) e a previsão de 2026-11-25. Subir a API com `uv run uvicorn volt.api:app` e rodar `curl localhost:8000/previsao?data=2026-11-25`. Esperado: 24 valores. Colar a saída no PR.
- [ ] Atualizar o README: o que já funciona, como rodar (os 3 comandos) e o desenho do fluxo.
- [ ] Commit → PR → merge. Fatia 1 concluída.
