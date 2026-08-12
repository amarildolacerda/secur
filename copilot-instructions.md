# GitHub Copilot Instructions

Este arquivo orienta o comportamento do GitHub Copilot ao sugerir código para o projeto Secur.

## Objetivo

- Sugerir soluções simples, modulares e compatíveis com Linux para desenvolvimento inicial.
- Priorizar código que possa ser portado para Raspberry Pi na fase de deploy final.
- Manter o foco em captura de vídeo, inferência de IA, regras de alerta e dashboard leve.

## Diretrizes principais

- Prefira Python 3.11+ e bibliotecas amplamente suportadas (`OpenCV`, `Flask`, `FastAPI`, `SQLite`).
- Evite dependências pesadas desnecessárias no começo.
- Mantenha a arquitetura modular:
  - captura de stream
  - pré-processamento de frames
  - inferência de IA
  - regras de alerta
  - persistência de eventos
  - interface web
- Escreva código legível, com nomes claros e documentação mínima quando necessário.

## Foco do projeto

- Desenvolvimento inicial em Linux.
- Deploy final planejado para Raspberry Pi 4.
- Suporte a câmeras IP com RTSP/HTTP.
- Regras configuráveis de zona e horário.
- Alertas via Telegram nesta fase inicial.

## Código sugerido

- Evite soluções que dependam de GPU exclusiva.
- Prefira modelos YOLO leves ou TensorFlow Lite.
- Use SQLite para persistência no MVP.
- Mantenha o backend simples e sem dependências desnecessárias.

## Revisão de sugestões

- Verifique se as sugestões respeitam o `SPEC.md`.
- Atualize `README.md` e documentação quando novas funcionalidades forem adicionadas.
- Considere criar testes básicos para fluxos importantes.

## Padrões de qualidade

- Código Python deve ser idiomático e compatível com ferramentas de lint.
- Mantenha separação de responsabilidades em módulos ou classes.
- Prefira soluções que facilitem futura migração para Raspberry Pi.
