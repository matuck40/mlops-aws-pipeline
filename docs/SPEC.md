# SPEC — Previsão de carga horária (Volt)

Status: rascunho · 2026-11-25

## Objetivo
Prever todo dia as 24 horas de carga de energia do dia seguinte no subsistema
Sudeste/Centro-Oeste, para a Volt (comercializadora fictícia), com um pipeline
automático na AWS free tier que monitora o próprio erro e se retreina quando piora.

## Contexto do problema
A Volt decide quanta energia comprar para cada hora de amanhã. Prever acima é
comprar demais; prever abaixo é comprar caro de última hora. Os dados vêm do
portal de dados abertos do ONS (curva de carga horária).

## Fora de escopo
- Outras regiões (S, NE, N).
- Front-end ou painel visual.
- Deep learning (LSTM, redes neurais).
- Dados de clima como feature.
- Alta disponibilidade, autenticação na API, múltiplos ambientes (dev/prod).
- SageMaker, EC2, RDS ou qualquer servidor ligado 24h.

## Restrições
- Tudo na free tier da AWS. Custo de cada recurso informado antes de criá-lo.
- Dia 1 na AWS: alerta de custo no AWS Budgets, antes de qualquer outro recurso.
- Apenas serviços serverless: EventBridge Scheduler, Lambda, S3, API Gateway, SNS.
- Código em Python, com testes em pytest; TDD em toda tarefa.
- Construção em fatia vertical (walking skeleton): primeiro ponta a ponta
  mínimo, depois aprofundar.

## Fluxo diário
EventBridge → ETL → Previsão → Monitor → (se houver drift) Treino.
A API só lê previsões já salvas.

## Etapas

### 0. Alerta de custo
- Entrada: conta AWS.
- Saída: orçamento no AWS Budgets com alerta por e-mail.
- Pronto quando: alerta configurado para gasto real e previsto acima de US$ 1,
  sem descontar créditos; orçamento listado com status OK no AWS Budgets
  (o Budgets não envia e-mail de confirmação para destinatário direto).

### 1. ETL diário para S3
- Entrada: curva de carga horária do ONS, subsistema SE/CO, dia D-1.
- Saída: dados/carga_horaria/data=AAAA-MM-DD/carga.parquet
  (colunas: timestamp em horário de Brasília, carga_mw).
- Pronto quando:
  - cada dia gravado tem exatamente 24 linhas, horas únicas e consecutivas;
  - sem valores nulos e carga_mw > 0;
  - rodar duas vezes o mesmo dia não duplica dados (idempotente);
  - se o ONS ainda não publicou o dia, falha com erro claro e não grava nada parcial;
  - existe uma carga inicial (backfill) de 3 anos de histórico.

### 2. Treino com versão e métrica
- Entrada: histórico em dados/ até uma data de corte.
- Saída: modelos/vN/ com o modelo e metricas.json (MAPE do modelo e dos
  baselines, período dos dados, versão do código); treino registrado no MLflow.
- Modelo: LightGBM. Features: carga na mesma hora 2 e 7 dias antes, hora,
  dia da semana, feriado.
- Baselines: naive (último dia disponível), naive sazonal (mesma hora 7 dias
  antes) e regressão linear.
- Pronto quando:
  - divisão treino/teste é temporal (teste = período mais recente, sem embaralhar);
  - nenhuma feature usa dado posterior ao momento da previsão (teste de vazamento);
  - MAPE do LightGBM no teste < MAPE de cada baseline;
  - mesmos dados e mesma seed geram o mesmo MAPE (reprodutível).

### 3. Previsão diária (lote)
- Entrada: modelo campeão + dados até D-1.
- Saída: previsoes/data_alvo=D+1/previsao.parquet
  (colunas: timestamp, previsto_mw, versao_modelo).
- Pronto quando: 24 valores positivos, versão do modelo registrada,
  rodar duas vezes não duplica.

### 4. Deploy como API
- Entrada: GET /previsao?data=AAAA-MM-DD (padrão: amanhã); GET /health.
- Saída: JSON com 24 previsões e a versão do modelo.
- Pronto quando:
  - data com previsão → 200 com 24 itens;
  - data sem previsão → 404; data inválida → 400;
  - API não roda o modelo, só lê previsoes/;
  - limite de requisições (throttling) configurado no API Gateway.

### 5. Monitoramento e retreino
- Entrada: previsoes/ e dados/.
- Saída: metricas/ com MAPE diário e MAPE móvel de 7 dias; e-mail (SNS) em drift.
- Pronto quando:
  - o MAPE calculado bate com um caso de teste de resultado conhecido;
  - drift dispara se o MAPE móvel de 7 dias > 1,5 × MAPE de teste do campeão,
    ou se ficar pior que o naive sazonal na mesma janela;
  - com menos de 7 dias de previsões, não dispara;
  - em drift: envia e-mail e chama o treino de um desafiante;
  - desafiante (mesmo código, dados mais novos, treinado sem os últimos 14 dias)
    só vira campeão se tiver MAPE menor que o campeão nesses 14 dias.

### 6. CI no GitHub
- Entrada: push ou pull request.
- Saída: check verde ou vermelho no GitHub.
- Pronto quando:
  - GitHub Actions roda o pytest em todo push e PR;
  - os testes não acessam a AWS real (usam mocks);
  - a main é protegida: PR com teste falhando não pode ser mergeado.

## Decisões em aberto
- Previsão para as outras 3 regiões.
- Dados de clima como feature.
- Painel em Streamlit.
- Ambientes dev/prod separados.
- Modo sombra (shadow mode) para o desafiante.
- Fator 1,5× do gatilho de drift: ajustar com dados reais.
- Atraso de publicação do ONS e horário do agendamento diário.
- Usar a previsão oficial do ONS como referência extra, se houver em base horária.
- Onde o MLflow guarda o histórico quando o treino roda na Lambda.
- Empacotamento da Lambda quando entrar o LightGBM (a camada AWS SDK for pandas
  pode não bastar; talvez imagem de container).

## Decisões tomadas
- 2026-11-26 — Recursos criados com AWS SAM (infraestrutura como código), não pelo console.
- 2026-11-26 — Região us-east-2: é a região principal da conta (o modelo novo de conta nega serviços regionais fora dela); mesmo preço da us-east-1 e os dados do ONS são públicos.
- 2026-11-26 — Na fatia 2, pandas e pyarrow vêm da camada gerenciada AWS SDK for pandas.
- Tamanho do período de teste.
