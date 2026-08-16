# Pesquisa: Desejos de usuários em segurança com câmeras

> **Data:** 2026-08-15
> **Objetivo:** embasar a priorização do roadmap (seção "Recursos candidatos") com desejos reais de usuários.
> **Fontes:** GitHub (issues/discussions do Frigate NVR), Reddit (r/homesecurity, r/selfhosted, r/frigate_nvr, r/reolinkcam, r/homeassistant), Home Assistant community, artigos (CNET, ACM), mercado brasileiro de condomínios.

---

## 1. Menos falsos alarmes (a maior dor de todas)

- Pesquisa acadêmica (ACM, 2025): *"Camera, Action, False Alert! Tackling the Flood of False Alerts"* — sistemas disparam notificações para eventos irrelevantes (sombras em movimento, veículos passando, folhas caindo).
- CNET: *"I Thought I'd Hate AI in Home Security"* — a IA que filtra falsos alarmes é o que mais mudou a percepção do usuário.
- Reddit r/homesecurity: sistemas sem distinção pessoa/veículo geram muitos falsos alarmes.
- Fornecedores (Lumana, etc.) afirmam cortar até 90% dos falsos alarmes com filtro por IA.

**Implicação:** filtros de objeto por score (min_score/threshold com mediana), máscaras de filtro por classe (bottom-center) e objetos estacionários são os recursos de maior valor percebido.

---

## 2. Gravação 24/7 + pré-gravação (pre-roll) + timeline com scrub

- Reddit r/homesecurity: *"Any decent NVR will record 24/7... if it can't record 24/7 I wouldn't even call it an NVR"*.
- Reolink/Ring vendem "10s pre-recording" como recurso-chave — usuários querem o contexto ANTES do evento.
- Novo UI do Frigate 0.14 (timeline scrubbing) muito elogiado.

**Implicação:** gravação contínua com retenção em camadas + pre-roll é alta demanda; o Secur hoje grava só por evento.

---

## 3. App móvel / push notifications com snapshot

- Discussion mais quente do Frigate (#4002, 33 comentários + 76 respostas): app iOS nativo.
- Pedidos: live view, push com snapshot/clip, PTZ control, video scrubbing, "touch-native UI não intimidante".
- Simplicidade para não-técnicos (pais, familiares) é recorrente.

**Implicação:** PWA + notificações Web Push é o caminho de menor custo; Telegram já cobre parte.

---

## 4. Gestão de eventos e revisão

- Issues mais votadas do Frigate:
  - "[UI] Screen to solve 'why was this review item created'" (#11399)
  - "Multiselect to remove events" (#2063)
  - "Delete a button / delete all events" (#2223)
  - "[FR] 'View Only' Web UI" (#3539)
  - "Authorisation Roles" (#6614)

**Implicação:** UI de revisão simplificada + ações em lote + modo visualização (view-only) são desejos claros.

---

## 5. Armazenamento flexível

- "Retention by Available Disk Space" (#994, 31 👍): *"quero dizer ao sistema 'use até 3TB'"*.
- "Ability to specify multiple storage locations" (#6557, aberto): disco local + NAS, etc.

**Implicação:** retenção por limite de espaço em disco + múltiplos locais de armazenamento são diferenciais baratos e muito pedidos.

---

## 6. Armar/desarmar câmeras e zonas dinamicamente

- "ARMED and UNARMED configurations for cameras" (#15570)
- "Ability to toggle zone / mask dynamically" (#3621)
- "Ability to dynamically disable/enable individual cameras" (#1911)

**Implicação:** toggle por câmera/zone + horários (ex.: desarmar quando estou em casa).

---

## 7. PTZ / autotracking + áudio bidirecional (doorbell)

- Autotracking é desejado, mas usuários reclamam de compatibilidade ONVIF (Reddit: "só funciona bem com Dahua"; discussion #23344 sobre provider externo).
- "Two-way audio support" (#2515) — recorrente em doorbells.

**Implicação:** manter como backlog, documentando suporte ONVIF como valor futuro.

---

## 8. Detecção/classificação de áudio

- "Audio Classification via Tensorflow Lite" (#1869) — fechado no Frigate, CPU-leve.
- Audio detectors: sirene, alarme, vidro quebrando.

**Implicação:** viável no Raspberry Pi; vale adicionar ao roadmap.

---

## 9. Privacidade 100% local / sem nuvem (diferencial do Secur)

- r/selfhosted: *"you couldn't pay me to use google/amazon/cloud"*.
- Privacy Guides: open-source verificável é recurso crítico para segurança/privacidade.

**Implicação:** o Secur já tem badge "100% local" + modo privacidade — reforçar na comunicação (README, docs) é diferencial real.

---

## 10. Contexto Brasil — condomínios e portaria

- Mercado BR forte: app do morador, portaria remota, liberar acesso pelo celular, ver câmera na hora, reconhecimento facial em condomínio.
- Exemplos: Raio Portaria, Pronto Portaria Virtual, V-Guard, Kravi.

**Implicação:** caminho BR = notificações inteligentes para síndico/morador + integração com portaria remota (o Secur já tem identidade + MQTT + HA).

---

## Síntese para o roadmap

### Promover para alta prioridade (já listados em média)
- Gravação contínua 24/7 com retenção em camadas (+ pre-roll)
- PWA / app mobile com push

### Adicionar ao roadmap
- Retenção por espaço em disco + múltiplos locais de armazenamento
- Armar/desarmar câmera/zona por horário
- Detecção de áudio (confirmada)
- UI de revisão simplificada ("por que este evento?") + ações em lote (multiselect/delete)
- Permissões/roles (modo view-only)
- Pré-gravação (pre-roll) explícita
- Integração com portaria remota / app do morador (contexto BR)

### Confirmados (já em alta prioridade)
- Filtros de score, máscaras por classe, objetos estacionários
- Privacidade/local (diferencial)
