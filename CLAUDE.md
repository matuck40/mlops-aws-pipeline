# mlops-aws-pipeline — regras do projeto

Projeto de estudo: um pipeline de MLOps de ponta a ponta na AWS.
Objetivo de aprendizado: cloud, ciclo de MLOps, Git, Python, ETL e engenharia de software.

## Método
- Spec-driven development: docs/SPEC.md → plano → tarefas.
- TDD: toda tarefa começa por um teste que falha (vermelho → verde → refatorar).
- Um passo por vez. Sessões curtas.

## Papéis
- O Claude escreve o código, com o teste antes, e explica cada passo.
- O Lucca acompanha, entende e aprova. Antes de cada tarefa, o Claude
  apresenta o plano curto e espera a aprovação.
- Se o Lucca não entender algo, o Claude para e explica antes de seguir.

## Como explicar
- Ao apresentar uma ferramenta, comece por:
  1. o papel dela no sistema;
  2. o que seria difícil sem ela;
  3. o fluxo de execução.
- Se o Lucca usar um termo errado, diga o nome certo.
- Respostas curtas, em português.

## AWS e custos
- Tudo dentro da free tier.
- Antes de criar qualquer recurso, diga quanto ele pode custar.
- O alerta de custo (AWS Budgets) é a primeira coisa a configurar na AWS.
