# Recurso: Controle de Acesso e Gestão de Usuários

> **Data:** 2026-08-19
> **Status:** Especificado — pronto para implementação

## O problema

O Secur não tem nenhuma autenticação/autorização. Todas as rotas Flask (`/cameras`, `/zones`, `/events`, `/settings`) são abertas — qualquer pessoa na rede local (ou exposta) pode acessar, configurar e deletar tudo. Em um cenário de condomínio com 80 câmeras, isso é inaceitável:

- Qualquer morador pode deletar câmeras ou alterar configurações
- Não há rastro de quem fez o quê (auditoria)
- Não há distinção entre quem monitora e quem configura

A pesquisa de usuários confirma: o Frigate NVR tem issue #6614 "Authorisation Roles" como um dos mais votados, e "view-only mode" (#3539) é demanda recorrente.

## O que o Secur já tem

| Capacidade | Onde existe hoje | Reuso no recurso |
|---|---|---|
| SQLite + tabelas | `storage.py` (EventStorage) | Adicionar tabelas `users`, `user_sessions`, `role_permissions` |
| Flask | `app.py` (create_app) | Adicionar `before_request` hook + rotas de auth |
| Templates HTML | `templates/dashboard.html`, `identities.html` | Criar `login.html`, `setup.html`, `permissions.html`, `users.html` |
| Config via env | `config.py` | Adicionar `SESSION_TTL_HOURS`, `MAX_LOGIN_ATTEMPTS` |
| werkzeug | Já embutido no Flask | `generate_password_hash` / `check_password_hash` (sem dependência nova) |

## O que precisa ser construído

### 1. Modelo de dados

```sql
-- Usuários do sistema
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin','chefe_seguranca','vigilante','viewer')),
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL,
    last_login TEXT,
    active INTEGER NOT NULL DEFAULT 1
);

-- Sessões de browser (tokens de login)
CREATE TABLE user_sessions (
    id TEXT PRIMARY KEY,              -- token aleatório (32 bytes hex)
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    ip_address TEXT
);

-- Permissões configuráveis por role
CREATE TABLE role_permissions (
    role TEXT NOT NULL,
    permission TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (role, permission)
);

-- API keys para acesso programático (HA, MQTT bridge)
CREATE TABLE api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_hash TEXT NOT NULL UNIQUE,    -- hash da chave, não a chave em texto
    name TEXT NOT NULL,               -- label legível ("Home Assistant", "MQTT Bridge")
    permissions TEXT,                 -- JSON: lista de permissões (None = todas)
    created_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL,
    last_used TEXT,
    active INTEGER NOT NULL DEFAULT 1
);

-- Log de auditoria (quem fez o quê)
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    api_key_id INTEGER REFERENCES api_keys(id),
    action TEXT NOT NULL,             -- "create_camera", "delete_event", "login", etc.
    target_type TEXT,                 -- "camera", "event", "user", "setting", etc.
    target_id TEXT,                   -- ID do alvo (string para flexibilidade)
    details TEXT,                     -- JSON: payload relevante
    ip_address TEXT,
    created_at TEXT NOT NULL
);
```

### 2. Acesso a câmeras por viewer

Em cenários de condomínio com até 80 câmeras, um viewer (morador) pode ter acesso restrito a câmeras específicas. A regra é:

- **Viewer sem câmeras associadas** (`user_cameras` vazio): vê **todas** as câmeras (compatível com uso residencial simples)
- **Viewer com câmeras associadas**: vê **apenas** as câmeras na lista `user_cameras`
- **Admin/chefe_seguranca/vigilante**: sempre veem **todas** as câmeras (sem restrição)

Tabela `user_cameras`:
```sql
CREATE TABLE user_cameras (
    user_id INTEGER NOT NULL REFERENCES users(id),
    camera_id INTEGER NOT NULL REFERENCES cameras(id),
    PRIMARY KEY (user_id, camera_id)
);
```

Isso permite que o síndico/chefe atribua uma lista de câmeras ao morador. Se a lista estiver vazia, o morador vê tudo (padrão). Se tiver ao menos uma entrada, o acesso fica restrito.

Endpoints novos:
- `PUT /api/users/<id>/cameras` — define a lista de câmeras do viewer `{"camera_ids": [1, 3, 5]}`
- `GET /api/users/<id>/cameras` — lista as câmeras atribuídas ao viewer

Impacto nos endpoints existentes:
- `GET /cameras`, `GET /api/dashboard`, `GET /camera/<id>/snapshot`, `GET /camera/<id>/thumbnails`, `GET /camera/<id>/clips` — filtrados automaticamente quando o usuário é viewer com câmeras associadas

### 3. Hierarquia de usuários

```
admin (síndico)
├── pode criar → chefe_seguranca
│                 ├── pode criar → vigilante
│                 └── pode criar → viewer (morador)
│
└── pode criar → qualquer role diretamente
```

Regras de gerenciamento:
- **Admin** gerencia todos os usuários
- **Chefe de segurança** gerencia apenas os usuários que ele mesmo criou (`created_by`)
- **Vigilante** e **viewer** não gerenciam ninguém
- Ninguém pode desativar a si mesmo
- Proteção: não deletar/desativar o último admin ativo
- Só `admin` pode criar outro `admin` ou `chefe_seguranca`

> **Nota importante:** a hierarquia controla quem **cria usuários**, não quem **define permissões**. O chefe_seguranca pode criar vigilantes e viewers, mas não pode alterar o que cada role pode fazer. Para que um vigilante ganhe uma nova permissão (ex.: `create_users`), o **admin** precisa ativar essa permissão na matriz de permissões em `/permissions`. Essa separação espelha a realidade do condomínio: o síndico define as regras (quem pode fazer o quê), e o chefe de segurança monta a equipe dentro dessas regras.

### 3. Permissões configuráveis

Em vez de hardcoded, as permissões ficam numa tabela configurável pelo admin via UI.

#### Permissões disponíveis

| Chave | Descrição |
|-------|-----------|
| `view_live` | Ver câmeras ao vivo |
| `view_events` | Ver histórico de eventos |
| `view_clips` | Ver clipes de vídeo |
| `view_snapshots` | Ver snapshots/thumbnails |
| `view_dashboard` | Acessar dashboard |
| `dismiss_event` | Dispensar/acknowledge evento |
| `retain_event` | Retener evento (proteger de prune) |
| `delete_event` | Deletar evento |
| `prune_events` | Podar eventos antigos |
| `arm_disarm` | Armar/desarmar câmeras e zonas |
| `manage_cameras` | Adicionar/editar/deletar câmeras |
| `manage_zones` | Adicionar/editar/deletar zonas |
| `manage_identities` | Gerenciar identidades (faces) |
| `manage_notifications` | Configurar notificações/routing |
| `manage_settings` | Alterar configurações gerais |
| `manage_retention` | Configurar política de retenção |
| `manage_users` | Gerenciar todos os usuários |
| `create_users` | Criar novos usuários |
| `view_users` | Listar usuários |
| `manage_permissions` | Configurar permissões por role |
| `view_audit_log` | Ver log de auditoria |

#### Defaults por role

| Permissão | admin | chefe_seguranca | vigilante | viewer |
|-----------|-------|-----------------|-----------|--------|
| `view_live` | ✅ | ✅ | ✅ | ✅ |
| `view_events` | ✅ | ✅ | ✅ | ✅ |
| `view_clips` | ✅ | ✅ | ✅ | ✅ |
| `view_snapshots` | ✅ | ✅ | ✅ | ✅ |
| `view_dashboard` | ✅ | ✅ | ✅ | ✅ |
| `dismiss_event` | ✅ | ✅ | ✅ | ❌ |
| `retain_event` | ✅ | ✅ | ✅ | ❌ |
| `delete_event` | ✅ | ❌ | ❌ | ❌ |
| `prune_events` | ✅ | ❌ | ❌ | ❌ |
| `arm_disarm` | ✅ | ✅ | ✅ | ❌ |
| `manage_cameras` | ✅ | ❌ | ❌ | ❌ |
| `manage_zones` | ✅ | ❌ | ❌ | ❌ |
| `manage_identities` | ✅ | ❌ | ❌ | ❌ |
| `manage_notifications` | ✅ | ❌ | ❌ | ❌ |
| `manage_settings` | ✅ | ❌ | ❌ | ❌ |
| `manage_retention` | ✅ | ❌ | ❌ | ❌ |
| `manage_users` | ✅ | ❌ | ❌ | ❌ |
| `create_users` | ✅ | ✅ | ❌ | ❌ |
| `view_users` | ✅ | ✅ | ❌ | ❌ |
| `manage_permissions` | ✅ | ❌ | ❌ | ❌ |
| `view_audit_log` | ✅ | ✅ | ❌ | ❌ |

> A permissão `manage_users` do chefe_seguranca é substituída por `create_users` — ele cria usuários mas não edita/deleta os de outros.

### 4. Autenticação

#### Browser (session-based)

- Token de sessão via cookie `HttpOnly`, `SameSite=Strict`
- TTL configurável (default 24h, via `SESSION_TTL_HOURS`)
- Senhas com PBKDF2-SHA256 via `werkzeug.security` (já embutido no Flask)
- Rate limiting no login: máx 5 tentativas/min por IP, lockout de 5min após 5 falhas
- Sessões persistidas no SQLite (revogáveis)

#### API Keys (para integrações)

- Chaves de 48 caracteres (hex), hash armazenado no DB
- Cada chave pode ter permissões restritas (JSON array)
- Uso via header: `Authorization: Bearer <api_key>`
- Rate limiting por chave
- Visível apenas no momento da criação (nunca recuperável)

### 5. Fluxos

#### First-run setup

```
1. Sistema inicia → não existe nenhum usuário na tabela users
2. Qualquer request → redireciona para GET /setup
3. GET /setup → formulário: username, password, confirmação
4. POST /setup → cria primeiro admin → redireciona para /
5. A partir daí, /setup retorna 403 (já configurado)
```

#### Login

```
1. GET /login → formulário de login
2. POST /api/auth/login → {username, password}
3. Valida credenciais → cria sessão → Set-Cookie: session_token=...
4. Redireciona para /
5. Falha → retorna erro, incrementa contador de tentativas
6. 5 falhas → lockout 5 minutos (resposta 429)
```

#### Logout

```
1. POST /api/auth/logout
2. Remove sessão do DB
3. Clear-Cookie: session_token
4. Redireciona para /login
```

#### Verificação de acesso (before_request)

```
1. Request chega
2. Se endpoint é público (health, login, setup, static) → prossegue
3. Extrai token do cookie OU header Authorization
4. Valida sessão/API key no DB
5. Carrega permissões do role do usuário
6. Anexa user + permissions ao request
7. Se inválido → 401 Unauthorized
```

#### Verificação de permissão (decorator)

```python
@app.route("/cameras", methods=["POST"])
@require_permission("manage_cameras")
def add_camera():
    ...
```

Se o usuário não tem a permissão → 403 Forbidden.

### 6. Rotas da API

#### Autenticação

| Rota | Método | Permissão | Descrição |
|------|--------|-----------|-----------|
| `/setup` | GET | público (só se 0 usuários) | Formulário de primeiro admin |
| `/setup` | POST | público (só se 0 usuários) | Criar primeiro admin |
| `/login` | GET | público | Formulário de login |
| `/api/auth/login` | POST | público | Autenticar e criar sessão |
| `/api/auth/logout` | POST | autenticado | Encerrar sessão |
| `/api/auth/me` | GET | autenticado | Dados do usuário logado + permissões |

#### Usuários

| Rota | Método | Permissão | Descrição |
|------|--------|-----------|-----------|
| `/users` | GET | `view_users` | Página HTML de gestão |
| `/api/users` | GET | `view_users` | Lista usuários (admin: todos, chefe: seus) |
| `/api/users` | POST | `create_users` | Criar usuário |
| `/api/users/<id>` | PUT | `manage_users` | Editar usuário (admin) ou próprios criados (chefe) |
| `/api/users/<id>` | DELETE | `manage_users` | Deletar usuário (com proteção último admin) |
| `/api/users/<id>/password` | PUT | admin ou próprio usuário | Resetar senha |

#### Permissões

| Rota | Método | Permissão | Descrição |
|------|--------|-----------|-----------|
| `/permissions` | GET | `manage_permissions` | Página HTML da matriz |
| `/api/permissions` | GET | `manage_permissions` | Retorna todas as permissões por role |
| `/api/permissions` | PUT | `manage_permissions` | Atualiza permissões de um role |
| `/api/permissions/definitions` | GET | autenticado | Lista de permissões disponíveis (labels) |

#### API Keys

| Rota | Método | Permissão | Descrição |
|------|--------|-----------|-----------|
| `/api/api-keys` | GET | `manage_users` | Lista API keys (sem expor chave) |
| `/api/api-keys` | POST | `manage_users` | Criar API key (retorna chave uma vez) |
| `/api/api-keys/<id>` | DELETE | `manage_users` | Revogar API key |

#### Auditoria

| Rota | Método | Permissão | Descrição |
|------|--------|-----------|-----------|
| `/audit` | GET | `view_audit_log` | Página HTML do log |
| `/api/audit` | GET | `view_audit_log` | Lista registros (filtro por user, ação, data) |

#### Rotas existentes protegidas

| Rota | Permissão mínima |
|------|------------------|
| `GET /`, `/api/dashboard`, `/status`, `/api/system-status` | `view_dashboard` |
| `GET /events`, `/api/events` | `view_events` |
| `GET /cameras` | `view_live` |
| `GET /camera/<id>/snapshot` | `view_live` |
| `GET /camera/<id>/thumbnails` | `view_snapshots` |
| `GET /camera/<id>/clips` | `view_clips` |
| `POST /cameras`, `PUT/DELETE /cameras/<id>` | `manage_cameras` |
| `POST /zones`, `PUT/DELETE /zones/<id>` | `manage_zones` |
| `POST /identities`, `DELETE /identities/<id>` | `manage_identities` |
| `PUT /api/settings` | `manage_settings` |
| `PUT /api/notifications/routing` | `manage_notifications` |
| `POST /api/events/prune` | `prune_events` |
| `PUT /api/events/<id>/retain` | `retain_event` |
| `DELETE /events/<id>` (se implementado) | `delete_event` |
| `PUT /api/ingest` | API key válida |
| `/health`, `/docs` | público |

### 7. Segurança

- **Password hashing:** PBKDF2-SHA256, 600k iterações (werkzeug default)
- **Rate limiting:** max 5 tentativas/min por IP no login, lockout 5min
- **Cookie:** `HttpOnly`, `SameSite=Strict`, `Secure` (se HTTPS)
- **CSRF:** SameSite=Strict previne a maioria; tokens CSRF opcionais para formulários HTML
- **API keys:** hash SHA-256 armazenado, chave original visível apenas na criação
- **Último admin:** proteção contra desativação/deletion do último admin ativo
- **Autodesativação:** bloqueada (ninguém desativa a si mesmo)
- **Auditoria:** todas as ações de escrita logadas com user, ação, target, timestamp, IP

### 8. Arquivos a criar/modificar

| Arquivo | Ação | Descrição |
|---------|------|-----------|
| `src/auth.py` | **Criar** | Módulo de autenticação: decorators, hash, validação, rate limiting, cache de permissões |
| `src/storage.py` | Modificar | Adicionar tabelas `users`, `user_sessions`, `role_permissions`, `api_keys`, `audit_log` + métodos CRUD |
| `src/app.py` | Modificar | Adicionar `before_request` hook, rotas de auth/usuarios/permissoes/apikeys/auditoria |
| `src/config.py` | Modificar | Adicionar `SESSION_TTL_HOURS`, `MAX_LOGIN_ATTEMPTS`, `LOCKOUT_MINUTES` |
| `src/templates/login.html` | **Criar** | Tela de login |
| `src/templates/setup.html` | **Criar** | Tela de primeiro setup |
| `src/templates/users.html` | **Criar** | Gestão de usuários |
| `src/templates/permissions.html` | **Criar** | Matriz de permissões |
| `src/templates/audit.html` | **Criar** | Log de auditoria |
| `src/templates/dashboard.html` | Modificar | Header com nome do usuário + botão logout |

### 9. Dependências

**Nenhuma dependência nova.** Tudo usa:
- `werkzeug.security` (hashing) — já embutido no Flask
- `secrets` (tokens) — stdlib do Python
- `hashlib` (API keys) — stdlib do Python
- SQLite (sessions, permissions, audit) — já usado

### 10. Decisões de design

| Decisão | Opção escolhida | Motivação |
|---------|----------------|-----------|
| Autenticação browser | Session cookies | App local, sem JWT complexity, revogável |
| Autenticação API | API keys (Bearer) | HA/MQTT precisam de acesso programático sem browser |
| Permissões | Tabela configurável | Flexível por condomínio, sem hardcoded |
| Cache de permissões | In-memory com invalidação | Evita 1 query por request; invalida no PUT |
| Senhas | PBKDF2-SHA256 (werkzeug) | Sem dependência nova, adequate security |
| Rate limiting | In-memory counter | Simples, suficiente para app single-node |

### 11. Casos de uso do condomínio

| Cenário | Role | Ação |
|---------|------|------|
| Síndico configura o sistema | admin | CRUD câmeras, zonas, settings, cria chefe_seguranca |
| Síndico cadastra o chefe de segurança | admin | POST /api/users {role: "chefe_seguranca"} |
| Chefe cadastra vigias | chefe_seguranca | POST /api/users {role: "vigilante"} |
| Chefe cadastra moradores | chefe_seguranca | POST /api/users {role: "viewer"} |
| Vigilante monitora 24h | vigilante | Ver câmeras, dismiss eventos, arm/disarm |
| Morador verifica suas câmeras | viewer | Somente visualização |
| Síndico quer que vigias configurem notificações | admin | PUT /api/permissions {role: "vigilante", perm: "manage_notifications", enabled: true} |
| Home Assistant consulta eventos | API key | GET /events com Bearer token |

### 12. Roadmap de implementação

1. **Fase 1 — Core auth:** tabelas no DB, `src/auth.py`, login.html, setup.html, before_request hook, proteção de rotas existentes
2. **Fase 2 — User management:** rotas CRUD de usuários, users.html, hierarquia created_by
3. **Fase 3 — Permissões:** tabela role_permissions, permissions.html, decorator `@require_permission`
4. **Fase 4 — API keys + Auditoria:** tabela api_keys, audit_log, rotas correspondentes
5. **Fase 5 — Polish:** rate limiting, lockout, header no dashboard, testes

### 13. Riscos e mitigações

| Risco | Impacto | Mitigação |
|-------|---------|-----------|
| Lockout acidental do último admin | Alto | Proteção: não permite desativar/deletar último admin |
| Perda de sessão (DB corrompido) | Médio | Sessões são descartáveis; usuário faz login novamente |
| Performance do before_request | Baixo | Cache em memória; SQLite leve; 1 query a cada 5s por user |
| Compatibilidade comHA/MQTT | Médio | API keys como alternativa ao session cookie |
| Race condition no rate limiting | Baixo | In-memory counter é suficiente para single-node |
