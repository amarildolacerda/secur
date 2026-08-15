# Pesquisa: Monitoramentos desejáveis em condomínios e áreas de alta circulação

> **Data:** 2026-08-15
> **Objetivo:** ampliar a matriz de situações monitoráveis do Secur com casos desejáveis em condomínios, shoppings, rodoviárias/terminais e lojas movimentadas.
> **Fontes:** sindiconet, emive, revistadoscondominios, ultralytics (crowd management), axis (retail loss prevention), IDC Retail Insights, PMC/NIH (escalator safety), IEEE (parking lot security), hackster/PMC (abandoned luggage), notícias BR (Rodoviária de Curitiba).

---

## 1. Condomínios residenciais (BR)

- **Câmeras em áreas comuns e de circulação** são tema de lei (PL 4204/2025) — monitoramento de áreas comuns vira obrigação.
- **Furtos na portaria:** entregadores flagrados furtando celular/encomenda deixada no balcão (casos reais e recorrentes).
- **Furto/invasão na garagem:** furtos de veículos e pertences; sistemas atuais vão além de gravar — detectam movimento suspeito.
- **Guardas de encomendas:** recomendação de lockers para portaria virtual; câmera + notificação de entrega/retirada é desejável.
- **Invasão por falha na portaria virtual:** dupla entra por falha e furta — detecção de "pessoa não autorizada em área privativa" já cobre (intruder_detected).

**Desejos-chave:** monitorar portaria (furtos de encomenda), garagem (movimento suspeito, veículo parado), áreas comuns (aglomeração em salão de festas/piscina), elevador (porta aberta, pessoa caída).

---

## 2. Shopping centers

- **Crowd monitoring** é o caso nº1 (Ultralytics, Lumana, Horizon, Mercity):
  - Densidade/aglomeração em áreas comuns, entradas, corredores;
  - **Heat maps** de concentração;
  - **Capacidade excedida** → alerta;
  - **Fluxo** (entrada/saída) e filas.
- **Alertas de aglomeração incomum** ("unusual gatherings") que podem indicar risco.
- **Prevenção de perdas (retail):** furtos, self-checkout fraud, carrinho empurrado sem pagamento (cart pushout).
- **Segurança:** pichação/vandalismo, veículo suspeito no estacionamento, pessoa caída.

**Desejos-chave:** aglomeração/densidade, filas (tempo de espera), fluxo de pessoas, heat maps, furtos (loitering perto de prateleiras), bagagem/objeto abandonado.

---

## 3. Rodoviárias / terminais / transporte público

- **Câmeras reduzem ocorrências** (Rodoviária de Curitiba: queda significativa com monitoramento).
- **Abandoned luggage/bag** é caso de uso clássico (aeroportos, estações) — objeto parado > threshold de tempo sem dono → alerta (potencial ameaça).
- **Escalator/escalada safety** (PMC/NIH, VisionPlatform): quedas, entupimento de roupa/objeto, aglomeração, comportamento anormal nos degraus.
- **Elevador:** queda de passageiro (fall detection em elevador), porta presa, superlotação.
- **Plataformas:** contagem de pessoas, alerta de superlotação (London Underground).
- **Fluxo e filas:** throughput e tempo de espera estimado (QUT research, airports/malls).

**Desejos-chave:** bagagem abandonada, queda em escada/elevador, superlotação de plataforma, filas, fluxo de passageiros.

---

## 4. Lojas movimentadas / varejo

- **Loss prevention** (Axis, IDC): furtos, self-checkout fraud, mis-scan, cart pushout, loitering, vandalismo.
- **Footfall analytics:** contagem de visitantes (96% acurácia), heat maps de tráfego, hot spots.
- **Queue management:** monitora caixas, estima filas, alerta para abrir mais caixas (IDC: staffing alerts antes de virar problema).
- **Shelf monitoring:** reposição, out-of-stock.
- **Análise de comportamento do cliente:** padrões de movimento, otimização de layout.

**Desejos-chave:** contagem/fluxo, filas de caixa, furtos (loitering, comportamento suspeito), abandono de carrinho/produto, heat maps.

---

## 5. Síntese — situações adicionais para o roadmap

| Situação | Ambiente principal | Fonte | Nível funil | Providência padrão |
|---|---|---|---|---|
| **Bagagem/objeto abandonado** (sem dono > threshold) | rodoviária, shopping, aeroporto, condomínio | visão (stationary + owner association) | N3 | alertar (área crítica); informar |
| **Aglomeração/densidade** (capacidade excedida) | shopping, terminal, salão de festas, piscina | visão (contagem/densidade) | N3 | alertar |
| **Filas (tempo de espera)** | loja, caixa, portaria, guichê | visão (contagem + throughput) | N3 | informar (operacional); alertar se muito longa |
| **Fluxo/contagem de pessoas** (footfall) | loja, shopping, terminal | visão (counting) | N2/N3 | informar (analytics) |
| **Queda em escada/elevador** | terminal, shopping, condomínio | visão (fall + localização) | N3 | perigo eminente |
| **Superlotação de elevador** | condomínio, shopping | visão (contagem) | N3 | informar; alertar se risco |
| **Furto na portaria / encomenda** | condomínio | visão (loitering + zona portaria) | N3 | alertar |
| **Movimento suspeito na garagem** (loitering perto de veículos, mexer no veículo) | condomínio, shopping | visão (loitering + veículo) | N3 | alertar |
| **Veículo parado/obstruindo** (já no roadmap) | garagem, shopping, rua | visão (stationary + zona) | N3 | alertar |
| **Vandalismo/pichação** (já no roadmap) | shopping, condomínio, terminal | visão (stationary + zona) | N3 | alertar |
| **Carrinho abandonado em circulação** (já no roadmap) | shopping, condomínio | visão (stationary + zona) | N3 | informar; alertar se bloqueia rota |
| **Self-checkout/caixa fraud** | loja | visão (área de caixa) + POS | N3 | alertar (prevenção de perdas) |
| **Fogo/fumaça, alagamento, porta aberta** (já no roadmap) | todos | visão + sensores | N2-N4 | perigo/alertar |

---

## 6. Implicações de arquitetura

- **A maioria dessas situações reusa o funil N0-N4 existente** — só muda o *analisador* na central (N2/N3): contagem, densidade, stationary+owner, fall em contexto de escada, etc. A borda (N0-N1) continua pescando movimento/ROI igual.
- **Sensores continuam como candidatos já confirmados** (N4 direto).
- **Analytics (footfall, filas, heat maps)** são casos de uso *operacionais* — mesma infraestrutura, saída para dashboard/BI em vez de alerta de segurança. Isso amplia o público do Secur (operação + segurança).
- **Bagagem abandonada** exige *associação objeto-dono* (owner association) — um avanço além do stationary simples; é o caso mais complexo (N3).
- **Contagem/densidade** em áreas de alta circulação pode precisar de modelo dedicado (YOLO já conta pessoas; densidade por grid).

> Conclusão: o Secur como plataforma cobre condomínios e alta circulação com o **mesmo funil**, adicionando *analisadores* (N2/N3) e *saídas analíticas* — sem mudar a arquitetura de borda/central.
