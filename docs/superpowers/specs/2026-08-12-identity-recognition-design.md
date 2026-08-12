# Design: Reconhecimento de Identidade (Pessoas/Animais Permitidos vs Intrusos)

## 1. Objetivo

Adicionar ao Secur a capacidade de identificar **quem** é a pessoa ou animal detectada,
distinguindo indivíduos **permitidos (conhecidos)** de **desconhecidos (potenciais invasores)**
que devem gerar alerta. O recurso é offline, event-driven e compatível com Raspberry Pi 4.

Decisões já validadas com o usuário:

- **Mecanismo**: híbrido — reconhecimento facial para pessoas (com re-ID por aparência como fallback)
  e re-ID por aparência para animais (rosto de animal é incerto).
- **Aprendizado (enroll)**: supervisionado — o usuário cadastra explicitamente, no dashboard,
  as identidades permitidas (nome + fotos de referência).
- **Lógica de alerta**:
  - Conhecido = nunca alerta (permitido em qualquer zona).
  - Desconhecido em zona privativa/segurança = `intruder_detected` (alerta alta).
  - Desconhecido em zona pública = `unknown_person` (notificação leve, sem disparo no Home Assistant).
- **Casamento (matching)**: embeddings + similaridade de cosseno com threshold configurável.

## 2. Arquitetura

Novo módulo `secur/identity.py` com a classe `IdentityRecognizer`, encaixado no
`CameraWorker` **após** a detecção de objetos (`secur/main.py`). O reconhecimento é
**event-driven**: só roda quando há movimento + detecção de pessoa/animal, reaproveitando
os workers threaded existentes. Nada de processos ou serviços extras.

```
movimento (MotionDetector)
   -> detecção de objetos (ObjectDetector)        [já existe]
   -> para cada crop de pessoa/animal:
        recognize(crop, label)  ->  IdentityRecognizer  [NOVO]
   -> decisão de alerta conforme identidade + zona
```

## 3. Componentes

### 3.1 `IdentityRecognizer` (`secur/identity.py`)
- `enroll(name: str, species: str, images: List[np.ndarray]) -> int`
  - Calcula embedding(s) de referência e persiste (metadados no SQLite + arquivo `.npy`).
  - Retorna `identity_id` ou levanta erro se nenhuma face/aparência for detectável.
- `recognize(crop, label: str) -> dict`
  - Pessoa: tenta embedding facial → match entre pessoas conhecidas (threshold);
    sem match, tenta re-ID → match; senão `unknown`.
  - Animal: embedding re-ID → match entre animais conhecidos; senão `unknown`.
  - Retorna `{"identity_id", "name", "known": bool, "method": "face"|"reid", "confidence": float}`.
- `remove_identity(identity_id) -> bool`
- `list_identities() -> List[dict]`

### 3.2 Storage (`secur/storage.py`)
Nova tabela:

```sql
CREATE TABLE IF NOT EXISTS known_identities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    species TEXT NOT NULL DEFAULT 'person',   -- 'person' | 'animal'
    created_at TEXT NOT NULL,
    embedding_path TEXT NOT NULL
);
```

- Embeddings salvos como arquivos `.npy` em `IDENTITY_EMBEDDINGS_DIR` (padrão `data/identities/`).
- Métodos: `add_identity`, `list_identities`, `get_identity`, `remove_identity`.

### 3.3 API (`secur/app.py`)
- `POST /identities` — enroll (nome, espécie, lista de imagens base64 ou upload).
- `GET /identities` — lista identidades conhecidas.
- `DELETE /identities/<id>` — remove identidade.

### 3.4 Alertas (`secur/alerts.py`)
- O payload ganha os campos `identity` (nome ou `"unknown"`), `known` (bool) e
  `recognition_method` (`"face"` | `"reid"` | `None`).
- `snapshot_info` continua sem disparar alerta (apenas informação).
- Novos event types: `identity_recognized` (conhecido, info), `intruder_detected`
  (desconhecido em zona privativa/segurança), `unknown_person` (desconhecido em zona pública).

### 3.5 Dashboard
Nova página "Identidades" para gerenciar conhecidos: upload de fotos de referência,
listar, excluir. Segue o padrão visual do dashboard existente (ESP-NOW Hub pattern).

## 4. Fluxo de dados (detalhado)

Em `CameraWorker.run()` (`secur/main.py`), após `object_detector.detect(frame)`:

1. Para cada detecção com `label` em conjunto de interesse (`person`, `cat`, `dog`, etc.):
   - Recorta o bounding box do frame.
   - Chama `identity_recognizer.recognize(crop, label)`.
2. Decide alerta:
   - `known == True` → `identity_recognized` (registra evento, **sem** alerta HA).
   - `known == False` e zona em `(privativa, segurança)` → `intruder_detected` (alerta alta: Telegram + MQTT + HA).
   - `known == False` e zona `pública` → `unknown_person` (notificação leve: Telegram apenas, sem HA).
   - Sem reconhecimento (modelos ausentes) → comportamento atual (só classe).

A classificação da zona já é resolvida no worker (`zone_classification`).

## 5. Tratamento de erros

- **Modelos de identidade não carregados**: `recognize` retorna `None`; sistema comporta-se
  como hoje (só classificação de objeto, sem identidade). Nenhum alerta falso.
- **Rosto não detectável / baixa confiança**: marca como `unknown` e tenta fallback re-ID.
- **Enroll sem face/aparência detectável**: retorna erro 400 à API; não cadastra embedding vazio.
- **Falha ao salvar embedding**: loga exceção, não quebra o worker.

## 6. Configuração (novas env vars em `secur/config.py`)

| Var | Padrão | Descrição |
|-----|--------|-----------|
| `IDENTITY_ENABLED` | `false` | Ativa reconhecimento de identidade (off no Pi por padrão). |
| `IDENTITY_FACE_MODEL_PATH` | `""` | Caminho do modelo ONNX de face embedding (ex.: MobileFaceNet/SFace). |
| `IDENTITY_REID_MODEL_PATH` | `""` | Caminho do modelo ONNX de re-ID leve (aparência). |
| `IDENTITY_MATCH_THRESHOLD` | `0.6` | Limiar de similaridade de cosseno para casar identidade. |
| `IDENTITY_EMBEDDINGS_DIR` | `data/identities` | Diretório dos arquivos `.npy` de embedding. |

## 7. Performance (Raspberry Pi)

- **Event-driven**: reconhecimento só roda com movimento + detecção (igual ao pipeline atual).
- **Modelos leves**: face embedding via MobileFaceNet/SFace (ONNX); re-ID via modelo leve (ex.: OSNet tiny).
- **Lazy-load**: modelos carregados no primeiro uso, não na inicialização.
- **Flag `IDENTITY_ENABLED`**: desligado por padrão; liga quando os modelos estiverem disponíveis.
- Crops pequenos (bbox) reduzem custo de inferência.

## 8. Testes

- **Unit** (`tests/test_identity.py`):
  - Cálculo de embedding retorna vetor normalizado.
  - Lógica de similaridade de cosseno + threshold (match / no-match).
  - `enroll` / `remove_identity` / `list_identities` contra SQLite temporário.
  - Fallback face→re-ID quando rosto ausente.
- **Integração** (`tests/test_identity_integration.py`):
  - Detector fake → `recognize` → mapeamento correto de decisão de alerta
    (conhecido / intruso / desconhecido em pública).
- **CI**: modelos mockados (stubs que retornam embeddings determinísticos) para evitar
  download de modelos pesados.

## 9. Documentação

Atualizar `SPEC.md` e `README.md`:
- Nova seção "Reconhecimento de Identidade" (objetivo, fluxo, exemplos de uso).
- Endpoints `/identities` documentados.
- Env vars de identidade na seção de configuração.
- Roadmap: marcar item de "treinamentos customizados / identidade" como em progresso.

## 10. Fora de escopo (YAGNI)

- Aprendizado não-supervisionado / clustering automático (futuro, abordagem híbrida C).
- Permissões por zona por indivíduo (futuro, abordagem C de alerta).
- Integração com nuvem para backup de embeddings.
- Reconhecimento facial de animais como primário (usamos re-ID para animais).
