# Design Review: Página de Usuários e Padrão de Páginas de Gestão

> **Data:** 2026-08-19
> **Status:** Revisado — pronto para implementação
> **Escopo:** Seção `users-management` do dashboard + padrão reutilizável para páginas de gestão (permissões, auditoria, futuras)
> **Base:** `docs/superpowers/specs/2026-08-19-users-page-design-review.md`

---

## 1. Contexto

A seção "Usuários" é a única página de gestão do dashboard que usa **cards** em vez de **tabela**. As demais sete (câmeras, zonas, identidades, retenção, notificações, permissões, auditoria) usam tabela. Esta revisão responde às perguntas do brief, decide o padrão reutilizável e entrega o guia de aplicação.

Arquivos analisados:

| Arquivo | Papel na análise |
|---------|------------------|
| `src/templates/dashboard.html` (linhas 436–458) | Seção `users-management` atual |
| `src/templates/users.html` | Página standalone (referência) |
| `src/static/dashboard.js` (linhas 2722–2839) | Lógica da seção usuários |
| `src/static/style.css` | Classes existentes: `.panel`, tabelas, `.form-row`, `.form-message`, `.empty-state`, `.badge` |
| `src/templates/audit.html`, `permissions.html` | Padrões das demais páginas de gestão |

---

## 2. Análise da página atual

### 2.1 A estrutura de cards é adequada para listar usuários?

**Parcialmente, mas a tabela é a escolha certa aqui.**

- Cards funcionam bem para listas curtas (2–10 usuários de um condomínio) e dão peso visual ao badge de role.
- Porém a página é a **única** fora do padrão: 7 de 8 páginas de gestão usam tabela. A inconsistência é um custo de UX real — o usuário precisa reaprender o formato a cada seção.
- Os dados de usuário são tabulares por natureza: nome, role, status, data de criação, ações. Não há conteúdo rico (imagem, preview) que justifique card.
- Tabela escala melhor: com até 8 câmeras planejadas, o número de usuários cresce (síndico, chefe, vigilantes, moradores). Tabela escaneia melhor que pilha de cards.
- A tabela já tem todos os primitivos prontos: `thead th` (uppercase, `--surface-2`), `tbody td`, `.table-actions`, `.button-mini`, `.table-responsive` para mobile.

**Decisão: tabela.** O padrão `.user-card-inline` deixa de ser usado (ver seção 6 — remoção).

### 2.2 O formulário de criação está posicionado corretamente?

**Sim, a posição está certa; o layout interno não.**

- Botão "+ Criar usuário" no canto direito do `panel-header` segue o padrão de "Adicionar câmera", "Adicionar zona" e "Cadastrar identidade". Correto.
- Formulário em toggle (abre abaixo do header, empurra a lista) é leve e mantém contexto. Para 3 campos, é melhor que modal.
- **Problema:** o form usa um único `.form-row` (que no CSS global é `flex-direction: column`) — os 3 campos empilham verticalmente, ocupando altura desnecessária. A página standalone `users.html` resolve isso sobrescrevendo `.form-row` com `display:flex` horizontal dentro de um `<style>` local — o que conflita com o CSS global e duplica código.
- **Problema:** estilos inline no markup (`style="display:none;margin-bottom:1rem;"`, `style="color:var(--danger);font-size:.85rem;"`) violam o style guide, que manda usar classes.

**Decisão:** manter o toggle, mas com classe própria `.inline-form` e linha horizontal `.form-row-inline` que quebra em telas pequenas (ver seção 5).

### 2.3 Os botões de ação (Câmeras, Desativar) estão no lugar certo?

**Posição certa, comportamento incompleto.**

- Botões `button-mini` à direita da linha seguem o padrão de câmeras/zonas. Correto.
- "Câmeras" aparece só para `viewer` — regra de negócio atual, ok. Sugestão: mostrar para qualquer role não-admin quando houver restrição de câmera no futuro.
- "Desativar/Ativar" não tem `confirm()` nem feedback de sucesso/erro — a ação acontece em silêncio. O style guide manda confirmar antes de ações destrutivas; desativar é reversível, mas o feedback é obrigatório.
- Não existe variante de botão para ações destrutivas (`Excluir`). Para o futuro, propor `.button-danger` (seção 5).

**Decisão:** manter botões inline `button-mini` (padrão do projeto), adicionar feedback e confirm.

### 2.4 A hierarquia visual (título → subtítulo → formulário → lista) faz sentido?

**Sim.** A ordem header (título + subtítulo + CTA) → formulário (toggle) → lista é a mesma das demais seções e deve ser mantida. Ajustes:

- Mensagem de erro do form deve usar `.form-message.error` (existe) em vez de estilo inline.
- Não há mensagem de sucesso após criar usuário — o form apenas fecha. Adicionar `.form-message` de sucesso com `role="status"` (padrão já usado em retenção).
- O botão toggle precisa de `aria-expanded`/`aria-controls` (padrão já usado no toggle de configurações, `dashboard.html` linha 384).

---

## 3. Padrão estabelecido para páginas de gestão

| Decisão | Padrão | Justificativa |
|---------|--------|---------------|
| **Listagem** | **Tabela** (`.table-responsive` + `thead th` padrão) | 7 de 8 páginas já usam; dados tabulares; escala; mobile grátis via overflow-x |
| **Formulário de criação** | **Inline (toggle)** para forms curtos (≤4 campos); **dialog** para forms complexos | Usuário tem 3 campos — toggle é mais leve que modal. Câmera/zona/identidade (JSON, canvas, upload) continuam em dialog. Regra documentada para páginas futuras |
| **Ações por item** | **Botões inline `button-mini`** (máx. 2–3); dropdown só se passar de 3 ações | Padrão já usado em câmeras/zonas. Dropdown esconde ações e adiciona código sem ganho com poucos botões |
| **Empty state** | Linha única centrada na tabela (`.table-empty`): "Nenhum usuário cadastrado" + dica | O CTA de criação já está no header; rich empty state (`.empty-state`) fica para páginas de conteúdo (overview, eventos) |
| **Feedback** | `.form-message` (sucesso, verde) e `.form-message.error` (vermelho), abaixo do form/ações, com `role="status"`/`aria-live` | Classes já existem; padroniza o que hoje é estilo inline espalhado |
| **Responsivo** | Tabela com scroll horizontal (`.table-responsive`); form inline quebra em coluna (<480px); sidebar colapsa em 700px (já existente) | Sem CSS novo por página |

### Tabela de padrões atualizada

| Página | Padrão atual | Após padronização |
|--------|-------------|-------------------|
| Câmeras | Tabela + dialog | Mantém |
| Zonas | Tabela + dialog | Mantém |
| Identidades | Tabela + dialog | Mantém |
| Retenção | Tabela + inline | Mantém |
| Notificações | Tabela + toggles | Mantém |
| **Usuários** | **Cards + inline toggle** | **Tabela + inline toggle** |
| Permissões | Tabela + toggles | Mantém (padronizar feedback com `.form-message`) |
| Auditoria | Tabela + filtros | Mantém (padronizar filtro e empty state) |

---

## 4. Wireframe — página de usuários padronizada

```
┌──────────────────────────────────────────────────────────────────────┐
│ Gestão de Usuários                                        [+ Criar usuário]
│ Crie, edite e gerencie usuários e suas permissões de acesso.         │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─ .inline-form (oculto por padrão; abre ao clicar no botão) ──────┐│
│  │  Usuário          Senha            Role          [Criar] [Cancelar]││
│  │  [input]          [input]          [select]                       ││
│  │  ───────────────────────────────────────────────────────────────  ││
│  │  <span class="form-message error" role="alert"> (erro)            ││
│  └───────────────────────────────────────────────────────────────────┘│
│                                                                      │
│  ┌─ .table-responsive ──────────────────────────────────────────────┐│
│  │  USUÁRIO   │ ROLE               │ STATUS    │ CRIADO EM │ AÇÕES   ││
│  │  admin     │ [Admin (Síndico)]  │ ● Ativo   │ 12/05/2026│ —       ││
│  │  joao      │ [Morador (Viewer)] │ ● Ativo   │ 01/06/2026│ [Câmeras]││
│  │            │                    │           │           │ [Desativar]│
│  │  maria     │ [Vigilante]        │ ● Inativo │ 20/06/2026│ [Ativar] ││
│  │            │                    │           │           │          ││
│  │  (se vazio: <tr class="table-empty"><td colspan="5">              ││
│  │   Nenhum usuário cadastrado. Clique em "Criar usuário".</td></tr>) ││
│  └───────────────────────────────────────────────────────────────────┘│
│                                                                      │
│  <span class="form-message" role="status"> Usuário criado com sucesso │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘

Colunas: Usuário | Role | Status | Criado em | Ações
- Status usa .badge.on / .badge.off (já existem) em vez de texto puro
- Role usa .badge-role + variantes (já existem)
- "Câmeras" condicional (role viewer, não é o próprio usuário)
- "Desativar/Ativar" condicional (não é o próprio usuário, não é o último admin)
- Ações com .button-secondary.button-mini (padrão câmeras/zonas)
```

### Comportamento no mobile (≤700px / ≤480px)

- Tabela rola horizontalmente via `.table-responsive` (sem quebra de layout).
- Form inline: `.form-row-inline` quebra em coluna (<480px), campos em largura total.
- Botões de ação permanecem legíveis (`button-mini` tem padding suficiente para toque).

---

## 5. Novas classes CSS (todas reutilizam variáveis existentes, tema claro)

```css
/* ── Padrão de páginas de gestão ── */

/* Formulário de criação inline (toggle) */
.inline-form {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
  margin-bottom: 16px;
}

/* Linha horizontal de campos (forms curtos) */
.form-row-inline {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: flex-end;
}
.form-row-inline > div {
  flex: 1 1 160px;
  min-width: 0;
}
.form-row-inline .form-actions {
  flex: 0 0 auto;
}

/* Linha vazia de tabela (empty state) */
.table-empty td {
  text-align: center;
  color: var(--muted);
  padding: 24px 12px;
  font-size: 0.85rem;
}

/* Botão para ações destrutivas (futuro: excluir usuário, etc.) */
.button-danger {
  padding: 8px 14px;
  border-radius: var(--radius-sm);
  border: none;
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 500;
  background: var(--danger);
  color: #fff;
  transition: filter 0.12s;
}
.button-danger:hover { filter: brightness(1.1); }
.button-danger.button-mini { padding: 4px 10px; font-size: 0.78rem; }
```

> Nota: `color: #fff` nos botões segue o padrão já existente de `.button-primary`.

### Remoções

- `.user-card-inline` e dependentes (`.user-card-inline .user-info` etc.) em `style.css` (linhas 260–271) — ficam órfãos com a migração para tabela.
- Estilos inline do markup da seção usuários (grid, form, mensagem de erro) — substituídos pelas classes acima.

---

## 6. Guia de aplicação para páginas futuras (permissões, auditoria, etc.)

### Checklist para qualquer página de gestão

1. **Header**: `.panel-header` com `h2` (título), `p` (subtítulo) e CTA à direita (`button-primary`).
2. **Listagem**: tabela dentro de `.table-responsive`; `thead th` com `var(--surface-2)`, `0.75rem`, uppercase; ações em `.table-actions` com `button-secondary.button-mini`.
3. **Formulário**:
   - ≤4 campos simples → `.inline-form` + `.form-row-inline` (toggle, com `aria-expanded`/`aria-controls` no botão).
   - Form complexo (JSON, canvas, upload, preview) → dialog (`.dialog-overlay` + `.dialog-card`), padrão câmeras/zonas/identidades.
4. **Empty state**: `<tr class="table-empty"><td colspan="N">Mensagem</td></tr>`.
5. **Feedback**: `.form-message` para sucesso (verde) e `.form-message.error` para erro, sempre com `role="status"` (sucesso) ou `role="alert"` (erro). Nada de estilo inline.
6. **Ações destrutivas**: `confirm()` antes (style guide) + `.button-danger` quando for exclusão.
7. **Responsivo**: nada além de `.table-responsive` e do form que quebra em coluna.

### Ajustes pontuais nas páginas existentes

| Página | Ajuste |
|--------|--------|
| Permissões | Trocar `#perm-status` (estilo inline) por `.form-message`; manter tabela + toggles |
| Auditoria | Trocar o `select` de filtro (estilo inline) por `.chip-select` (existe); usar `.table-empty` para "Nenhum registro" |
| Identidades | Já conforme; manter |

### Página standalone `users.html`

- Duplica a seção do dashboard com CSS próprio em `<style>` (inclusive sobrescreve `.form-row`, conflitando com o global).
- Recomendação: remover ou converter para usar as mesmas classes (`.inline-form`, `.form-row-inline`), sem `<style>` local. O dashboard é a versão canônica.

---

## 7. Observações finais

- **Cards não são proibidos** — continuam válidos para páginas de conteúdo/overview (tiles de câmera, eventos). A regra vale para **listas de gestão (CRUD)**: tabela.
- A migração de usuários para tabela é de baixo risco: `_loadUsers` já monta HTML por linha; muda o container de `#users-grid` (div) para `tbody` e o template de cada item.
- O toggle de criação já funciona; a mudança é de markup/CSS (classes) e de feedback, não de lógica.
- Aproveitar para adicionar `aria-expanded`/`aria-controls` no `btn-create-user` (acessibilidade, padrão já usado no toggle de configurações).