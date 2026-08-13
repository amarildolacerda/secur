---
name: style
description: >-
  Secur Dashboard Style Guide — Use when styling the Secur web dashboard.
  Covers CSS variables, sidebar, cards, tables, buttons, forms, dialogs,
  footer, responsive layout, and component patterns.
---

# Secur Dashboard — Style Guide

## Paleta de Cores (CSS Variables)

```css
:root {
  --bg: #f4f4f4;              /* canvas fundo da página */
  --surface: #ffffff;          /* surface-1: cartões, sidebar */
  --surface-2: #f9fafb;       /* surface-2: thead, hover states */
  --text: #1f2937;            /* ink: texto principal */
  --muted: #6b7280;           /* ink-muted: texto secundário */
  --muted-subtle: #9ca3af;    /* ink-subtle: labels, meta, headers */
  --primary: #5e6ad2;         /* lavender-blue destaque */
  --primary-strong: #828fff;
  --primary-focus: #eef0ff;   /* fundo de items ativos/hover */
  --border: #e5e7eb;          /* hairline */
  --border-strong: #d1d5db;
  --success: #16a34a;         /* verde online/ligado */
  --danger: #dc2626;          /* vermelho offline/desligado */
  --warn: #f59e0b;            /* amarelo alerta */
  --info: #2563eb;            /* azul informação */
  --radius: 12px;
  --radius-sm: 8px;
  --radius-pill: 9999px;
}
```

> Tema claro, minimalista. Cards brancos com bordas suaves, sem sombras.

## Layout

### Estrutura geral
```
body (flex, 100vh)
├── .sidebar (fixed, 200px, left)
│   ├── .logo
│   ├── nav (links + nav-group)
│   └── .footer-nav (fixed bottom)
├── .main (margin-left: 200px, max-width: 960px)
│   └── #page (flex column, gap 16px)
│       ├── .panel (overview)
│       ├── .panel (camera-management)
│       └── ...
└── .app-footer (fixed bottom, left: 200px)
```

### Sidebar (`.sidebar`)
- `position: fixed`, `width: 200px`, `height: 100vh`
- `background: var(--surface)`, `border-right: 1px solid var(--border)`
- `padding: 24px 0`
- Footer fixo no fundo com `position: fixed, bottom: 0`

### Main (`.main`)
- `margin-left: 200px`, `flex: 1`, `max-width: 960px`
- `padding: 24px`, `padding-bottom: 60px` (espaço pro footer)

### Footer principal (`.app-footer`)
- `position: fixed`, `bottom: 0`, `left: 200px`, `right: 0`
- `background: var(--surface)`, `border-top: 1px solid var(--border)`
- `padding: 8px 24px`, `font-size: 0.78rem`

## Componentes

### Logo (`.logo`)
- Padding `0 20px 20px`, border-bottom
- `h1`: `1rem`, weight `700`, cor `var(--primary)`
- `span`: `0.75rem`, cor `var(--muted)`

### Nav Links (`.nav-link`)
- Flex row, `gap: 10px`, `padding: 12px 20px`
- `font-size: 0.85rem`, weight `500`, cor `var(--muted)`
- `border-left: 3px solid transparent`
- `.active`: cor `var(--primary)`, bg `var(--primary-focus)`, border-left azul
- `.icon`: `width: 20px`, `font-size: 1.1rem`

### Nav Group (colapsável)
- `.nav-group-head`: mesmo estilo dos nav links
- `.chev`: seta para baixo, rotaciona com `.collapsed`
- `.nav-group-list`: `padding-left: 44px`, links menores (`0.78rem`)
- `.dot`: `7px` círculo colorido

### Painel (`.panel`)
- `background: var(--surface)`, `border: 1px solid var(--border)`
- `border-radius: var(--radius)`, `padding: 20px`
- `.panel-header`: flex space-between
- `h2`: `0.95rem`, weight `600`, cor `var(--primary)`

### Summary Cards (`.grid` + `.card`)
- Grid: `repeat(auto-fill, minmax(200px, 1fr))`, `gap: 12px`
- Card: `border: 1px solid var(--border)`, `border-radius: var(--radius)`, `padding: 16px`
- `h3`: `0.75rem`, uppercase, letter-spacing, cor `var(--muted-subtle)`
- `.summary-value`: `1.02rem`, weight `600`

### Tables
- `thead th`: `0.75rem`, uppercase, letter-spacing, bg `var(--surface-2)`
- `tbody td`: `0.85rem`, border-bottom `1px solid var(--border)`
- `.table-actions`: flex, gap `6px`

### Botões
- `.button-primary`: bg `var(--primary)`, cor `#fff`, radius `var(--radius-sm)`
- `.button-secondary`: bg `var(--border)`, cor `var(--text)`
- `.button-mini`: `padding: 4px 10px`, `font-size: 0.78rem`
- `.button-close`: `34px` quadrado, border, radius

### Forms
- `.form-row`: flex column, gap `5px`
- `label`: `0.8rem`, uppercase, cor `var(--muted-subtle)`
- `input/select`: border, radius `var(--radius-sm)`, `padding: 10px 12px`
- Focus: border `var(--primary)`, box-shadow `rgba(94,106,210,0.12)`

### Dialog (Modal)
- `.dialog-overlay`: fixed, inset 0, bg `rgba(31,41,55,0.5)`
- `.dialog-card`: `max-width: 500px`, bg white, border, radius, padding `24px`

### Camera Cards
- `.camera-badge`: pill, bg `var(--primary)`, cor `#fff`
- `.camera-source`: `overflow: hidden`, `text-overflow: ellipsis`, `white-space: nowrap`
- `.camera-preview`: `width: 100%`, radius `var(--radius-sm)`

### Badges
- `.badge.on`: bg `rgba(22,163,74,0.12)`, cor `var(--success)`
- `.badge.off`: bg `rgba(220,38,38,0.12)`, cor `var(--danger)`

## Responsivo (max-width: 700px)

- Sidebar colapsa para `60px` (só ícones)
- Textos do logo e nav são escondidos (`display: none`)
- Main: `margin-left: 60px`
- Footer: `left: 60px`
- Nav group items escondidos

## Padrões

### Ícones da sidebar
Usar emojis Unicode como ícones:
- 📷 Visão geral
- 🔍 Status
- 📋 Eventos
- ⚙ Manutenção

### Confirmação de exclusão
Sempre usar `confirm()` antes de DELETE:
```js
if (!confirm('Tem certeza que deseja excluir?')) return;
```

### Overflow de texto longo
Para URLs ou textos que podem estourar o card:
```css
overflow: hidden;
text-overflow: ellipsis;
white-space: nowrap;
```
