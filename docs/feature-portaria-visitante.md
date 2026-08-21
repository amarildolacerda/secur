# Recurso: Notificação de visita/entrega na portaria

> **Data:** 2026-08-15
> **Status:** Avaliado — recomendado como alto valor, médio custo (reusa muito do que já existe)

## O recurso

Quando alguém chega à portaria para fazer uma **visita** ou **entrega** em uma unidade, o sistema detecta automaticamente (por visão), e o **app notifica o morador** sobre a ocorrência — indicando a **entrada** e depois a **saída** do domínio.

Sera que o morador poderia receber uma mensagem no telegram ?

```
[Pessoa/veículo chega à portaria]
        │  (visão: N0-N1 borda → N2-N4 central)
        ▼
[Detecção: pessoa/veículo na zona "portaria"]
        │  (identidade: morador? visitante? entregador?)
        ▼
[Notificação ao morador: "Alguém chegou para você"]
        │  (app/PWA · Telegram · WhatsApp)
        ▼
[Entrada registrada] → [Permanência] → [Saída registrada]
        │                                    │
        └── "Visitante saiu do domínio" ─────┘
```

## Demanda de mercado (pesquisa)

Mercado **ativo e validado** no Brasil — concorrentes que notificam morador:

| Solução | Modelo | Diferencial |
|---|---|---|
| **Chegou** (deliwise) | porteiro registra em 8s → morador avisado no WhatsApp | registro manual |
| **e-Condomínio** | porteiro registra → WhatsApp automático | registro manual |
| **Condomínio Entregas** (app) | notificações de encomenda + QR code de retirada | registro manual |
| **Zibox** | aviso automático no WhatsApp (até 3 moradores) | integra com lockers |
| **Portaria Já** | registro de encomendas + notificações | registro manual |

**Dor recorrente:** *"a notificação do app do condomínio passa despercebida e o pacote fica esquecido na portaria"* — e o processo manual (papel, WhatsApp do condomínio) consome tempo do porteiro e depende dele.

**O diferencial do Tucuxi:** **zero registro manual** — a visão detecta a chegada, identifica a pessoa/veículo e notifica automaticamente. Nenhum concorrente pesquisado faz isso por visão.

## O que o Tucuxi já tem (reuso)

| Capacidade | Onde existe hoje | Uso no recurso |
|---|---|---|
| **Zonas com classificação** | `zones` (pública/segurança/privativa) + schedule | definir zona "portaria" |
| **Detecção de pessoas/veículos** | `detector.py` (ONNX/YOLO) | identificar chegada (pessoa, carro, moto) |
| **Reconhecimento de identidade** | `identity.py` (embeddings, cosine_similarity) | distinguir morador / visitante / entregador |
| **Direção (entrando/saindo)** | `behavior.py` `check_direction_crossing` (`direction_line`) | marcar **entrada** e **saída** do domínio |
| **Tracking** | `tracking.py` (IoUTracker) | seguir a pessoa do portão à unidade |
| **Notificações** | `notifications.py` + Telegram/MQTT/HA | entregar o aviso ao morador |
| **Sensores/automação** | MQTT/HA | opcional: travar/liberar acesso, integração com portaria |

## O que precisa ser construído

1. **Cadastro morador ↔ unidade** — tabela de moradores (nome, unidade, contato/canal de notificação). O Tucuxi já tem `identities`; falta o vínculo com unidade + canal.
2. **Zona "portaria" + linha de entrada/saída** — configurar zona e `direction_line` no portão (já suportado, é config).
3. **Evento de chegada** — quando pessoa/veículo entra na zona portaria vindo de fora:
   - detecta identidade (conhecido? visitante? entregador? veículo?)
   - cria evento `visitor_arrived` (com snapshot)
   - notifica morador(es) vinculado(s) — por unidade de destino? por todos?
4. **Vínculo visitante → unidade** (o ponto de design mais importante):
   - **Opção A (automática):** rastrear o visitante do portão até a unidade que ele visita (tracking + reconhecimento do morador que recebe) — notifica a unidade correta.
   - **Opção B (semi-auto):** o visitante/entregador informa a unidade num painel/intercom; sistema cruza com a visão.
   - **Opção C (simples):** notifica todos os moradores que "chegou alguém na portaria" com snapshot (sem saber a unidade) — menor precisão, maior simplicidade.
5. **Evento de saída** — quando a pessoa/veículo cruza a linha de saída → `visitor_departed` + notificação de fechamento.
6. **Canal de notificação** — app/PWA (Web Push, já no roadmap), Telegram (já existe), WhatsApp (via gateway externo tipo Z-API/Evolution).

## Encadeamento no funil N0-N4

| Nível | Função |
|---|---|
| N0-N1 (borda) | movimento na zona portaria → candidato (pesca) |
| N2 (central) | detecção rápida: pessoa/veículo na portaria |
| N3 (central) | identidade (morador/visitante/entregador) + tracking + direção (entrada/saída) + vínculo com unidade |
| N4 (central) | decisão de notificação: quem avisar, em que nível (info: visita/entrega) e roteamento |

## Providência e notificação

| Evento | Providência | Notificação ao morador |
|---|---|---|
| `visitor_arrived` | **informar** (ou alertar se não reconhecido) | "Uma visita/entrega chegou à portaria" + snapshot |
| `visitor_departed` | **informar** | "O visitante saiu do domínio" + hora |
| `visitor_duration` (opcional) | informar | "Visitante na unidade X há 30 min" (se configurado) |
| Desconhecido persistente na portaria | **alertar** | já coberto por `intruder_detected`/`unknown_detected` |

## Valor para o usuário

- **Morador:** nunca mais perde entrega; sabe quando a visita chegou e saiu — segurança e conveniência.
- **Portaria/gestão:** menos trabalho manual (sem papel/WhatsApp manual), registro automático de entrada/saída (auditoria, LGPD).
- **Diferencial competitivo:** ninguém no mercado pesquisado faz detecção automática por visão — é o encaixe perfeito da plataforma.

## Custo de implementação (estimativa)

- **Médio** — reusa ~70% (zonas, identidade, direção, tracking, notificações).
- Partes novas: cadastro morador↔unidade↔canal, eventos de chegada/saída, vínculo visitante→unidade (Opção A é a mais complexa; C é a mais rápida).
- Encadeia com o roadmap atual: PWA/push (notificação), identidade (já existe), direção (já existe).

## Recomendação

**Implementar como módulo da Fase C/plataforma** (após central de análise), começando pela **Opção C (notificação geral com snapshot)** para entrega rápida, evoluindo para **Opção A (vínculo automático por tracking)**.

Adicionar ao roadmap como item de alta prioridade no bloco "Condomínio".
