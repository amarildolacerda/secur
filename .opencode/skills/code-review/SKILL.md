---
name: code-review
description: >-
  Code review guide for the Secur project. Use when reviewing pull requests,
  evaluating code changes, or providing feedback on implementations.
  Covers alignment with SPEC.md, functionality, architecture, quality,
  performance, security, and testing.
---

# Code Review — Secur Project

Guia para revisão de código no projeto Secur. Serve para revisores humanos e agentes automatizados.

## Objetivo

Garantir que alterações estejam alinhadas com `SPEC.md` e `README.md`, mantendo qualidade, segurança, performance e portabilidade.

## Princípios

- Verifique se a alteração atende aos requisitos do projeto
- Prefira soluções simples e modulares
- Mantenha o código legível e bem documentado
- Confirme que existem testes adequados
- Avalie impacto em performance e recursos (Raspberry Pi)
- Verifique dependências e compatibilidade com Linux e Raspberry Pi

## Checklist

### Alinhamento com especificação
- A mudança está de acordo com o `SPEC.md`?
- O `README.md` ou a documentação requer atualização?
- A implementação respeita o roadmap e o escopo do MVP?

### Funcionalidade
- O código resolve o problema esperado?
- O comportamento cobre casos de uso principais e falhas esperadas?
- Há tratamento adequado de erros e falhas de entrada?

### Arquitetura e design
- O código é modular e bem separado por responsabilidades?
- Há acoplamento excessivo entre componentes?
- As abstrações fazem sentido para captura de vídeo, IA, persistência e alertas?

### Qualidade de código
- Estilo consistente com Python e boas práticas
- Nomes claros para variáveis, funções e classes
- Sem duplicação desnecessária
- Comentários e docstrings onde necessário

### Performance e recursos
- Uso de CPU/RAM considerado para Linux e Raspberry Pi?
- Otimizações para captura de múltiplos streams e inferência de IA?
- Sem loops pesados ou operações bloqueantes sem necessidade?

### Segurança e confiabilidade
- Validação de entrada e tratamento de valores inesperados?
- Sem exposição de credenciais ou dados sensíveis?
- Tratamento de falhas de rede, perda de conexão e reinicializações?

### Testes e documentação
- Testes ou casos de validação adicionados?
- Testes cobrem cenários relevantes e bordas?
- Documentação do novo comportamento atualizada?

## Revisão por área

### Python e IA
- Dependências de ML justificadas?
- Uso de modelos com fallback para ambientes sem GPU?
- Cargas de inferência moduladas e limitáveis?

### Captura de vídeo / câmeras IP
- Suporte a RTSP/HTTP e reconexão automática?
- Tratamento de falhas de stream e timeouts?
- Pré-processamento de frames eficiente?

### Dashboard e backend
- APIs bem definidas e documentadas?
- Rotas seguras e validação de parâmetros?
- Experiência de uso e histórico de eventos OK?

### Alertas e integrações
- Handlers de alerta (Telegram, MQTT, Home Assistant) tratam erros?
- Classificação de zona usada corretamente para severidade?
- Timeouts configurados para não bloquear o sistema?

## Como usar

1. Compare as alterações com `SPEC.md` e `README.md`
2. Aplique o checklist para cada PR ou conjunto de mudanças
3. Faça perguntas quando a implementação divergir do projeto
4. Registre comentários claros e acionáveis

## Exemplos de comentários

- "Essa função faz mais de uma coisa; sugiro separar captura e inferência."
- "O tratamento de reconexão não cobre desconexão prolongada."
- "Considere usar classe de configuração central para evitar strings duplicadas."
- "Esse módulo precisa de testes de unidade para o fluxo de eventos e alertas."
