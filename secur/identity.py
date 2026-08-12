import logging
import numpy as np
from typing import Callable, Dict, List, Optional
import os

from .config import IDENTITY_ENABLED, IDENTITY_MATCH_THRESHOLD
from .storage import EventStorage

logger = logging.getLogger(__name__)

# Detection label -> identity category
RECOGNITION_LABELS: Dict[str, str] = {
    "person": "person",
    "cat": "animal",
    "dog": "animal",
    "bird": "animal",
    "horse": "animal",
    "sheep": "animal",
    "cow": "animal",
    "car": "vehicle",
    "truck": "vehicle",
    "bus": "vehicle",
    "motorcycle": "vehicle",
    "bicycle": "vehicle",
}


def cosine_similarity(a, b) -> float:
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


class IdentityRecognizer:
    def __init__(
        self,
        storage: EventStorage,
        face_embedder: Optional[Callable[[np.ndarray], Optional[np.ndarray]]] = None,
        reid_embedder: Optional[Callable[[np.ndarray], Optional[np.ndarray]]] = None,
        threshold: float = IDENTITY_MATCH_THRESHOLD,
        enabled: bool = IDENTITY_ENABLED,
    ):
        self.storage = storage
        self.face_embedder = face_embedder
        self.reid_embedder = reid_embedder
        self.threshold = threshold
        self.enabled = enabled
        self._cache: Optional[Dict[str, list]] = None

    def enroll(self, name: str, species: str, images: List[np.ndarray]) -> int:
        if species not in ("person", "animal"):
            raise ValueError("species deve ser 'person' ou 'animal'")
        if not images:
            raise ValueError("ao menos uma imagem de referência é obrigatória")
        embeddings = []
        for img in images:
            emb, _method = self._embed(img, species)
            if emb is not None:
                embeddings.append(emb)
        if not embeddings:
            raise ValueError("nenhum rosto/aparência detectável nas imagens fornecidas")
        mean_emb = np.mean(embeddings, axis=0).astype(np.float32)
        norm = np.linalg.norm(mean_emb)
        if norm > 0:
            mean_emb = mean_emb / norm
        emb_path = self.storage.save_identity_embedding(name, mean_emb)
        identity_id = self.storage.add_identity(name, species, emb_path)
        self._refresh_cache()
        return identity_id

    def recognize(self, crop: np.ndarray, label: str) -> Optional[dict]:
        if not self.enabled:
            return None
        species = RECOGNITION_LABELS.get(label)
        if species is None:
            return None
        emb, method = self._embed(crop, species)
        if emb is None:
            return {"identity_id": None, "name": "unknown", "known": False, "method": None, "confidence": 0.0}
        if self._cache is None:
            self._refresh_cache()
        best_id, best_name, best_score = None, "unknown", -1.0
        for ident_id, ident_name, known_emb in self._cache.get(species, []):
            score = cosine_similarity(emb, known_emb)
            if score > best_score:
                best_score, best_id, best_name = score, ident_id, ident_name
        if best_id is not None and best_score >= self.threshold:
            return {"identity_id": best_id, "name": best_name, "known": True, "method": method, "confidence": best_score}
        return {"identity_id": None, "name": "unknown", "known": False, "method": method, "confidence": best_score}

    def remove_identity(self, identity_id: int) -> bool:
        result = self.storage.remove_identity(identity_id)
        self._refresh_cache()
        return result

    def list_identities(self) -> List[dict]:
        return self.storage.list_identities()

    def _refresh_cache(self):
        self._cache = {}
        for ident in self.storage.list_identities():
            emb = self.storage.load_identity_embedding(ident["id"])
            if emb is None:
                continue
            norm = np.linalg.norm(emb)
            if norm > 0:
                emb = emb / norm
            self._cache.setdefault(ident["species"], []).append((ident["id"], ident["name"], emb))

    def _embed(self, image: np.ndarray, species: str):
        if species == "person" and self.face_embedder is not None:
            emb = self.face_embedder(image)
            if emb is not None:
                return emb, "face"
        if self.reid_embedder is not None:
            emb = self.reid_embedder(image)
            if emb is not None:
                return emb, "reid"
        return None, None


def decide_event(identity_info, zone_classification, camera_name, label=None):
    category = RECOGNITION_LABELS.get(label, "object")
    if identity_info is None:
        return None
    if identity_info.get("known"):
        return (
            "identity_recognized",
            f"Pessoa/animal conhecido(a): {identity_info['name']} (câmera {camera_name})",
            identity_info["name"],
            True,
            label,
            category,
        )
    if zone_classification in ("privativa", "segurança"):
        return (
            "intruder_detected",
            f"Desconhecido em zona {zone_classification}: câmera {camera_name}",
            label,
            False,
            label,
            category,
        )
    return (
        "unknown_detected",
        f"Não reconhecido ({label}) na câmera {camera_name}",
        label,
        False,
        label,
        category,
    )


def make_onnx_embedder(model_path: str, input_size=(112, 112), face_detect: bool = False) -> Callable:
    import cv2
    net = cv2.dnn.readNetFromONNX(model_path)
    face_cascade = None
    if face_detect:
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

    def embed(image: np.ndarray):
        if image is None or image.size == 0:
            return None
        inp = image
        if face_detect and face_cascade is not None:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.1, 4)
            if len(faces) == 0:
                return None
            x, y, w, h = faces[0]
            inp = image[y:y + h, x:x + w]
        blob = cv2.dnn.blobFromImage(inp, 1.0 / 127.5, input_size, (127.5, 127.5, 127.5), swapRB=True)
        net.setInput(blob)
        vec = np.array(net.forward(), dtype=np.float32).flatten()
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    return embed


def build_recognizer(storage: EventStorage, face_embedder=None, reid_embedder=None) -> IdentityRecognizer:
    from .config import IDENTITY_FACE_MODEL_PATH, IDENTITY_REID_MODEL_PATH, IDENTITY_MATCH_THRESHOLD, IDENTITY_ENABLED
    face = face_embedder
    reid = reid_embedder
    if face is None and IDENTITY_FACE_MODEL_PATH and os.path.exists(IDENTITY_FACE_MODEL_PATH):
        face = make_onnx_embedder(IDENTITY_FACE_MODEL_PATH, face_detect=True)
    if reid is None and IDENTITY_REID_MODEL_PATH and os.path.exists(IDENTITY_REID_MODEL_PATH):
        reid = make_onnx_embedder(IDENTITY_REID_MODEL_PATH)
    return IdentityRecognizer(storage, face, reid, IDENTITY_MATCH_THRESHOLD, IDENTITY_ENABLED)
