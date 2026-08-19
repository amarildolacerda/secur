# AGENTS

Este documento descreve agentes e padrões recomendados para o projeto Secur.

## Objetivo
Fornecer orientações claras sobre como dividir tarefas entre agentes de projeto quando se trabalha em automação, desenvolvimento e validação.

## Agentes sugeridos

### 1. Agente de especificação
- Responsável por documentar requisitos, casos de uso e arquitetura.
- Deve focar em clareza, escopo do MVP e diferenciação entre desenvolvimento em Linux e deploy no Raspberry Pi.
- Deve acompanhar alterações no `SPEC.md` e `README.md`.
- Para melhorar os SPEC, fazer pesquisa para indicar melhorias ou recursos que poderiam melhorar a socitalação apresentando como opção para incluisão no scopo;
- Sempre que precisar tomar uma decisão sobre ordem de execução, primeiro analisar valor para usuario, ações que reduzem custos e deixam valor perseptivel para usuário tem maior relevância;

### 2. Agente de implementação
- Responsável por criar a estrutura do projeto em Python e componentes principais.
- Deve priorizar modularidade, testes e compatibilidade com Linux e Raspberry Pi.
- Deve gerar códigos de captura de vídeo, inferência com IA, persistência e backend web.
- Usar subagents para implemenação;
- separar paginas para reduzir tempo de carga do dashboard;

### 3. Agente de testes e validação
- Responsável por escrever e rodar testes automatizados.
- Deve validar fluxo de captura de stream, detecção de movimento, inferência de IA e alertas.
- Deve sugerir casos de teste para diferentes tipos de câmeras, zonas de interesse e regras de segurança.

## Regras gerais para agentes do projeto

1. Sempre trabalhe com base no spec e no roadmap.
2. Mantenha o desenvolvimento incremental:
   - primeiro Linux local,
   - depois Raspberry Pi.
3. Priorize a reutilização de código e a modularidade.
4. Documente decisões importantes e dependências.
5. Garanta que qualquer mudança de arquitetura seja refletida em `SPEC.md` e `README.md`.
6. Evite dependências pesadas no início; use versões leves e compatíveis.

## Fluxo de branches e release

- Código deve ser integrado em `dev` via pull request.
- Não aplique alterações de código diretamente em `main`.
- Para mover mudanças para produção, crie uma nova versão com tag baseada em `main`.
- Use o formato de tag `v0.0.0` para a primeira versão e incremente conforme necessário.
- Apenas a branch `main` deve conter código já liberado para produção.

## Como aplicar no projeto

- Use o agente de especificação para planejar a próxima etapa antes de começar a codificar.
- Use o agente de implementação para criar módulos independentes: captura, IA, alertas, dashboard.
- Use o agente de testes para validar cada módulo individualmente e o fluxo integrado.
- Use o agente de revisão de código para validar aderência ao spec, qualidade e cobertura de testes.

## 4. Agente de revisão de código
- Responsável por revisar mudanças de código e pull requests.
- Deve avaliar alinhamento com `SPEC.md`, `README.md` e padrões de projeto.
- Deve checar qualidade de código, testes, documentação, performance e portabilidade.
- Deve sugerir melhorias claras e acionáveis.

## Padrões relevantes para Secur

- Dividir a lógica de captura de câmeras e inferência de IA em componentes separados.
- Adotar um simples pipeline de processamento: captura → detecção de movimento → inferência → regras → alerta.
- Priorizar compatibilidade local e operação offline.
- Projetar a arquitetura para suportar até 8 câmeras no futuro.

## Retroalimentar conhecimento
- Quando encontra solução para um problema, documentar o problema e como resolver;
- Se um recurso novo for requerido, avaliar o que já existe pesquisando na web para propor melhores práticas na implementação e focar no "valor" para o usuário;
- Avaliar riscos, aqueles ligados a pessoas, cultura e legislação antes de implementar
  
## Documentação de especificações e planos

- Specs e planos de features ficam na pasta `/docs`.
- Arquivos de especificação iniciam por `SPEC_` (ex.: `SPEC_user-access-control.md`).
- Arquivos de plano de implementação iniciam por `PLAN_` (ex.: `PLAN_user-access-control.md`).
- O nome do arquivo deve ser descritivo, em kebab-case, refletindo o feature.
- Cada spec deve incluir: problema, o que já existe, o que construir, modelo de dados, rotas, segurança, riscos e roadmap de implementação.
- Cada plano deve incluir no cabeçalho:
  - **Status:** Planejado | Em andamento | Executado | Pausado | Cancelado
  - **Prioridade:** Crítica | Alta | Média | Baixa
  - **Fase atual:** fase em execução (ou "—" se ainda não iniciado)
- Cada plano deve incluir no corpo: fases numeradas com tarefas checklistadas, entregável por fase.

## Melhorias futuras

- Incluir um agente de integração com automação residencial.
- Incluir um agente de desempenho para otimização em Raspberry Pi.
- Incluir um agente de deploy para preparar instalação e configuração em Linux/Pi.
