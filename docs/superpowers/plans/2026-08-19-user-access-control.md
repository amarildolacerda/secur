# User Access Control — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sistema completo de autenticação/autorização com 4 roles (admin, chefe_seguranca, vigilante, viewer), 21 permissões configuráveis, hierarquia de gerenciamento por created_by, API keys para integrações e log de auditoria.

**Architecture:** Módulo `src/auth.py` com decorators Flask, sessões via cookies HttpOnly + API keys via Bearer header, permissões configuráveis em tabela SQLite com cache em memória, rate limiting in-memory. Tabelas: `users`, `user_sessions`, `role_permissions`, `api_keys`, `audit_log`. Templates: `login.html`, `setup.html`, `users.html`, `permissions.html`.

**Tech Stack:** Python 3.11+, Flask (werkzeug.security para hash), SQLite, JavaScript vanilla (dashboard).

> **Spec:** [2026-08-19-user-access-control-design.md](../specs/2026-08-19-user-access-control-design.md)
> **Status:** Executado

---

## Fase 1 — Core Auth ✅

> Entrega: sistema funcional com login, sessão e proteção básica de rotas.

- [x] Criar tabelas `users` e `user_sessions` no `storage.py` + métodos CRUD básicos (`add_user`, `get_user_by_username`, `create_session`, `validate_session`, `delete_session`)
- [x] Criar `src/auth.py` com decorators `require_auth`, `require_permission` + funções de hash de senhas (`hash_password`, `verify_password`) + cache de permissões em memória
- [x] Criar `templates/login.html` (formulário de login) e `templates/setup.html` (first-run: criação do primeiro admin)
- [x] Adicionar `before_request` hook no `app.py` + rotas de auth (`POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`, `GET/POST /setup`)
- [x] Proteger todas as rotas existentes com decorators de permissão (`@require_permission("manage_cameras")`, etc.)
- [x] Rodar testes existentes e garantir que nada quebrou (250 passed, 2 skipped)

## Fase 2 — User Management ✅

> Entrega: gestão de usuários com hierarquia (admin → chefe_seguranca → vigilante → viewer) + controle de acesso a câmeras por viewer.

- [x] Criar campos `role` e `created_by` na tabela `users` + validação de hierarchy
- [x] Criar rotas CRUD de usuários (`GET/POST /api/users`, `PUT/DELETE /api/users/<id>`) com regras de hierarquia
- [x] Criar `templates/users.html` com UI de gestão (admin vê todos, chefe vê os seus)
- [x] Implementar proteções: último admin não pode ser desativado/deletado, autodesativação bloqueada, chefe só cria/gerencia seus próprios
- [x] Criar tabela `user_cameras` (user_id → camera_id) + CRUD (`set_user_cameras`, `get_user_cameras`, `user_camera_ids`)
- [x] Criar rotas `GET/PUT /api/users/<id>/cameras` para atribuir câmeras ao viewer
- [x] Filtrar endpoints de câmeras por acesso do viewer: `GET /cameras`, `GET /api/dashboard`, `GET /camera/<id>/snapshot`, `GET /camera/<id>/thumbnails`, `GET /camera/<id>/clips`, `GET /events`
- [x] UI de atribuição de câmeras no `users.html` (checkbox list por viewer)

## Fase 3 — Permissões ✅

> Entrega: permissões configuráveis por role via UI admin.

- [x] Criar tabela `role_permissions` + defaults por role no `storage.py` + métodos CRUD
- [x] Criar `templates/permissions.html` com matriz roles × permissões (toggles)
- [x] Implementar cache em memória de permissões com invalidação no PUT (`invalidate_permission_cache()`)

## Fase 4 — API Keys + Auditoria ✅

> Entrega: acesso programático (HA/MQTT) e trilha de auditoria.

- [x] Criar tabelas `api_keys` e `audit_log` no `storage.py` + métodos CRUD
- [x] Criar rotas de API keys (`GET/POST /api/api-keys`, `DELETE /api/api-keys/<id>`) e de auditoria (`GET /api/audit`)
- [x] Criar `templates/audit.html` com filtros por usuário, ação e data

## Fase 5 — Polish ✅

> Entrega: production-ready com segurança, UX e documentação.

- [x] Implementar rate limiting (max 5 tentativas/min por IP) e lockout (5min após 5 falhas)
- [x] Adicionar header com nome do usuário + botão logout no `templates/dashboard.html`
- [x] Atualizar `SPEC.md` e `docs/roadmap.md` incluindo o feature como implementado
- [x] Escrever testes unitários do módulo `src/auth.py` (30 testes: sessions, permissions, hierarchy, rate limiting, API integration)
