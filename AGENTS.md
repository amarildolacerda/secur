# AGENTS

Este documento descreve agentes e padrões recomendados para o projeto Secur.

## Objetivo
Fornecer orientações claras sobre como dividir tarefas entre agentes de projeto quando se trabalha em automação, desenvolvimento e validação.

## Agentes sugeridos

### 1. Agente de especificação
- Responsável por documentar requisitos, casos de uso e arquitetura.
- Deve focar em clareza, escopo do MVP e diferenciação entre desenvolvimento em Linux e deploy no Raspberry Pi.
- Deve acompanhar alterações no `SPEC.md` e `README.md`.

### 2. Agente de implementação
- Responsável por criar a estrutura do projeto em Python e componentes principais.
- Deve priorizar modularidade, testes e compatibilidade com Linux e Raspberry Pi.
- Deve gerar códigos de captura de vídeo, inferência com IA, persistência e backend web.

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

## Melhorias futuras

- Incluir um agente de integração com automação residencial.
- Incluir um agente de desempenho para otimização em Raspberry Pi.
- Incluir um agente de deploy para preparar instalação e configuração em Linux/Pi.
