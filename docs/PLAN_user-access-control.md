# Plano de Implementação: Controle de Acesso e Gestão de Usuários

> **Data:** 2026-08-19
> **Especificação:** [SPEC_user-access-control.md](SPEC_user-access-control.md)
> **Status:** Planejado
> **Prioridade:** Alta
> **Fase atual:** —

---

## Fase 1 — Core Auth

> Entrega: sistema funcional com login, sessão e proteção básica de rotas.

- [ ] Criar tabelas `users` e `user_sessions` no `storage.py` + métodos CRUD básicos (`add_user`, `get_user_by_username`, `create_session`, `validate_session`, `delete_session`)
- [ ] Criar `src/auth.py` com decorators `require_auth`, `require_permission` + funções de hash de senhas (`hash_password`, `verify_password`) + cache de permissões em memória
- [ ] Criar `templates/login.html` (formulário de login) e `templates/setup.html` (first-run: criação do primeiro admin)
- [ ] Adicionar `before_request` hook no `app.py` + rotas de auth (`POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`, `GET/POST /setup`)
- [ ] Proteger todas as rotas existentes com decorators de permissão (`@require_permission("manage_cameras")`, etc.)
- [ ] Rodar testes existentes e garantir que nada quebrou

## Fase 2 — User Management

> Entrega: gestão de usuários com hierarquia (admin → chefe_seguranca → vigilante → viewer).

- [ ] Criar campos `role` e `created_by` na tabela `users` + validação de hierarchy
- [ ] Criar rotas CRUD de usuários (`GET/POST /api/users`, `PUT/DELETE /api/users/<id>`, `PUT /api/users/<id>/password`) com regras de hierarquia
- [ ] Criar `templates/users.html` com UI de gestão (admin vê todos, chefe vê os seus)
- [ ] Implementar proteções: último admin não pode ser desativado/deletado, autodesativação bloqueada, chefe só cria/gerencia seus próprios

## Fase 3 — Permissões

> Entrega: permissões configuráveis por role via UI admin.

- [ ] Criar tabela `role_permissions` + defaults por role no `storage.py` + métodos CRUD
- [ ] Criar `templates/permissions.html` com matriz roles × permissões (toggles)
- [ ] Implementar cache em memória de permissões com invalidação no PUT (`reload_permissions_cache()`)

## Fase 4 — API Keys + Auditoria

> Entrega: acesso programático (HA/MQTT) e trilha de auditoria.

- [ ] Criar tabelas `api_keys` e `audit_log` no `storage.py` + métodos CRUD
- [ ] Criar rotas de API keys (`GET/POST /api/api-keys`, `DELETE /api/api-keys/<id>`) e de auditoria (`GET /api/audit`)
- [ ] Criar `templates/audit.html` com filtros por usuário, ação e data

## Fase 5 — Polish

> Entrega: production-ready com segurança, UX e documentação.

- [ ] Implementar rate limiting (max 5 tentativas/min por IP) e lockout (5min após 5 falhas)
- [ ] Adicionar header com nome do usuário + botão logout no `templates/dashboard.html`
- [ ] Atualizar `SPEC.md` e `docs/roadmap.md` incluindo o feature como implementado
- [ ] Escrever testes unitários do módulo `src/auth.py` (session, permissions, hierarchy, rate limiting, API keys)
