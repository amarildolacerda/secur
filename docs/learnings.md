# Aprendizados (Lessons Learned)

Registro de problemas encontrados e suas soluções, para não repetir erros e preservar decisões de arquitetura.

---

## 2026-08-17 — Prune não deve apagar evento não analisado (risco p/ automação)

### Problema
O `prune_events` (limpeza automática de `events`) poderia deletar eventos que ainda
não tinham sido analisados pelo `AlertRuleEngine`, incluindo `no_motion` que alimenta
a automação (Home Assistant / MQTT). Se o evento sumisse antes da notificação, a
automação perderia o gatilho.

### Causa raiz (entendimento do fluxo)
- Eventos só entram no banco via `AlertRuleEngine._handle` → `storage.add_event`
  (`alert_rules.py:23`). Antes disso, o evento vive só na fila em memória (`event_bus`)
  e o prune (que opera só no DB) não o alcança.
- `add_event` grava com `disposition NULL` e `dropped` vindo da triagem N1.
- A notificação da automação ocorre em `alerts.send` (`alert_rules.py:55`), que é
  **síncrona** (`alerts.py`: HA via `requests.post` linha 200; MQTT via `publish.single`
  linhas 120-136). Só DEPOIS, em `update_event_level` (`alert_rules.py:63`), o
  `disposition` é definido.
- Logo, entre `add_event` e `update_event_level` o evento está "em voo":
  `disposition NULL` **e** `dropped = 0`.
- Armadilha: eventos **dropados** (`dropped = 1`, ruído da N1) também ficam com
  `disposition NULL` (o `AlertRuleEngine` retorna cedo em `alert_rules.py:28` sem
  setar disposition), mas JÁ foram triados e devem ser podados.

### Solução
Em `src/storage.py`, o helper `_collect_and_delete_event_ids` (usado por todo o
`prune_events`, por tipo e por idade máxima) recebeu a guarda:

```sql
AND (disposition IS NOT NULL OR dropped = 1)
```

Ou seja: só deleta evento já analisado (`disposition` definido) ou já triado como
ruído (`dropped = 1`). Evento em voo (`disposition NULL` E `dropped = 0`) nunca é
selecionado. Isso fecha a janela: a automação é sempre notificada antes do evento
ficar elegível para deleção.

### Ressalvas / modo de falha
- **Acúmulo em erro de análise (seguro):** se `_handle` lançar exceção *após*
  `add_event` mas *antes* de `update_event_level`, o evento fica `disposition NULL,
  dropped 0` e o guard o protege para sempre (nunca podado). Em operação normal não
  ocorre; só em erro recorrente na análise. É o lado seguro (reter > apagar).
  Se virar problema real, adicionar "timeout de análise" (podar `disposition NULL`
  com `timestamp` muito antigo) — mas isso reintroduz risco minúsculo de apagar não analisado.
- **`no_motion` some rápido:** retenção `EVENT_PRUNE_NO_MOTION_DAYS=0` → apagado no
  próximo prune (≤120s) após notificação. Se a automação HA reconsultar o evento na
  API/DB depois do webhook, pode dar 404. Normalmente o HA age sobre o payload do
  webhook (já traz `thumbnail_path`/`details`), então raramente é problema. Se
  precisar de tolerância a reconsulta, subir essa retenção para horas/dias.

### Verificação
O `pytest` não roda neste ambiente (`src/__init__` importa `main` → `cv2` ausente).
Validou-se o código real com script standalone que faz stub de `numpy`/`src.config`
e importa `src/storage.py` via `importlib`, rodando 3 cenários:
1. by-type + max-age, retido preservado;
2. em voo protegido; dropado + analisado podados;
3. `no_motion` protegido até `disposition` ser setado, depois podado.
Todos passaram. Testes em `tests/test_storage.py`: `test_prune_events_by_type_and_max_age`,
`test_prune_events_max_age_backstop` (marcam eventos como analisados) e
`test_prune_events_skips_unanalyzed` (novo).

### Onde mora a regra
- `src/storage.py` → `prune_events` / `_collect_and_delete_event_ids` (guarda SQL).
- `src/alert_rules.py` → ordem `add_event` (23) → `alerts.send` (55) → `update_event_level` (63).
- `description.md` → seção "Política de Prune", item 4 (Garantia de análise).
