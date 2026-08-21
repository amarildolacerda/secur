# Design Review: Página de Usuários — Tucuxi Monitor

> **Data:** 2026-08-19
> **Status:** Aguardando review do designer
> **Solicitante:** Equipe de desenvolvimento
> **Página:** `/` → Manutenção → Usuários (seção `users-management` no dashboard)

---

## Contexto

O Tucuxi Monitor é um sistema de vigilância inteligente com dashboard web (Flask + HTML/JS vanilla). A página de gestão de usuários foi implementada como seção dentro do dashboard principal, seguindo o style guide existente (`.opencode/skills/style/SKILL.md`).

**Pedimos que o designer analise a página e estabeleça um padrão visual consistente** para esta e futuras páginas de gestão (permissões, auditoria, etc).

---

## O que existe hoje

### Estrutura da seção "Usuários"

```
┌─────────────────────────────────────────────────────┐
│ Gestão de Usuários                    [+ Criar]     │
│ Crie, edite e gerencie usuários e suas permissões.  │
├─────────────────────────────────────────────────────┤
│ ┌─ Formulário (toggle) ──────────────────────────┐  │
│ │ Usuário    │ Senha        │ Role    │ [Criar]  │  │
│ │ [input]    │ [input]      │ [select]│ [Cancel] │  │
│ └─────────────────────────────────────────────────┘  │
│                                                      │
│ ┌─ Card Usuário ─────────────────────────────────┐   │
│ │ 👤 admin (você)                                │   │
│ │ [Admin (Síndico)] · Ativo                      │   │
│ │                              [Câmeras] [Desativ]│   │
│ └─────────────────────────────────────────────────┘  │
│ ┌─ Card Usuário ─────────────────────────────────┐   │
│ │ 👤 joao                                         │   │
│ │ [Morador (Viewer)] · Ativo                     │   │
│ │                              [Câmeras] [Desativ]│   │
│ └─────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### Estilo atual (CSS variables do projeto)

```css
:root {
  --bg: #f4f4f4;
  --surface: #ffffff;
  --surface-2: #f9fafb;
  --text: #1f2937;
  --muted: #6b7280;
  --muted-subtle: #9ca3af;
  --primary: #5e6ad2;
  --border: #e5e7eb;
  --success: #16a34a;
  --danger: #dc2626;
  --warn: #f59e0b;
  --info: #2563eb;
  --radius: 12px;
  --radius-sm: 8px;
}
```

### Padrões existentes no dashboard

- **Painéis**: `background: var(--surface)`, `border: 1px solid var(--border)`, `border-radius: var(--radius)`
- **Cards**: grid com `gap: 12px`, `padding: 16px`
- **Tabelas**: `thead th` com `var(--surface-2)`, `0.75rem`, uppercase
- **Botões**: `button-primary` (ações), `button-secondary` (cancelar), `button-mini` (tabelas)
- **Forms**: `label` com `var(--muted-subtle)`, `input/select` com `border-radius: var(--radius-sm)`

---

## Pedimos ao designer

### 1. Análise da página atual

- A estrutura de cards está adequada para listar usuários?
- O formulário de criação está posicionado corretamente?
- Os botões de ação (Câmeras, Desativar) estão no lugar certo?
- A hierarquia visual (título → subtítulo → formulário → lista) faz sentido?

### 2. Padrão a estabelecer

Criar um **padrão visual reutilizável** para páginas de gestão no dashboard:

- **Listagem de itens** (usuários, câmeras, zonas, etc.) — cards ou tabela?
- **Formulário de criação** — inline (toggle), modal, ou seção separada?
- **Ações por item** — botões inline, dropdown, ou ícones?
- **Empty state** — como mostrar "nenhum item"?
- **Feedback** — mensagens de sucesso/erro的位置 e estilo
- **Responsivo** — comportamento em telas pequenas

### 3. Referências visuais

O dashboard já tem estes padrões que podem servir de referência:

| Página | Padrão atual | Observação |
|--------|-------------|------------|
| Câmeras | Tabela com botões inline | `button-mini` por linha |
| Zonas | Tabela com botões inline | Mesmo padrão de câmeras |
| Identidades | Tabela com botões inline | Adiciona thumbnail |
| Retenção | Formulário com toggles | Sliders/inputs inline |
| Notificações | Tabela com toggles | `perm-toggle` switches |
| **Usuários** | **Cards** | **Única página que usa cards** |

> **Observação:** A página de usuários é a **única** que usa cards em vez de tabela. Padronizar se cards ou tabela é melhor para este caso.

### 4. Entregáveis esperados

1. **Wireframe** da página de usuários padronizada
2. **Definição do padrão** (cards vs tabela, formulário, ações)
3. **CSS classes** ou variáveis novas necessárias (se houver)
4. **Guia de aplicação** para as outras páginas (permissões, auditoria)

### 5. Restrições

- **Tema claro** (não escuro)
- **CSS variables** existentes devem ser reutilizadas
- **JavaScript vanilla** (sem frameworks CSS)
- **Compatível** com layout existente (sidebar 200px + main)
- **Responsivo** (sidebar colapsa em 700px)

---

## Arquivos relevantes

| Arquivo | Descrição |
|---------|-----------|
| `.opencode/skills/style/SKILL.md` | Style guide completo do dashboard |
| `src/templates/dashboard.html` | Template principal (seções inline) |
| `src/static/style.css` | CSS global (2050+ linhas) |
| `src/static/dashboard.js` | JS do dashboard (3190+ linhas) |
| `src/templates/users.html` | Página standalone de usuários (referência) |

---

## Contato

Qualquer dúvida, entrar em contato com a equipe de desenvolvimento.
