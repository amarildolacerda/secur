=== TASK 5: Wire recognition into CameraWorker ===

**Files:**
- Modify: `secur/main.py`
- Test: `tests/test_main_identity.py`

**Interfaces:**
- Consumes: `IdentityRecognizer` (Task 3), `decide_event` (Task 3), `RECOGNITION_LABELS` (Task 3), `AlertService.send` new signature (Task 4).
- Produces: worker emits `identity_recognized` / `intruder_detected` / `unknown_detected` events with identity & category fields.

## Tests (write to `tests/test_main_identity.py` verbatim)
```python
import numpy as np
from secur.main import decide_worker_event


def test_decide_worker_event_known():
    dets = [{"label": "person", "bbox": {"x": 0, "y": 0, "w": 5, "h": 5}, "confidence": 0.9}]
    ident = {"identity_id": 1, "name": "João", "known": True, "method": "face", "confidence": 0.9}
    event_type, details, identity_name, known, _label, category = decide_worker_event(dets, ident, "privativa", "Cam1", "person")
    assert event_type == "identity_recognized"
    assert identity_name == "João" and known is True and category == "person"


def test_decide_worker_event_intruder():
    dets = [{"label": "person", "bbox": {"x": 0, "y": 0, "w": 5, "h": 5}, "confidence": 0.9}]
    ident = {"identity_id": None, "name": "unknown", "known": False, "method": "reid", "confidence": 0.3}
    event_type, details, identity_name, known, _label, category = decide_worker_event(dets, ident, "privativa", "Cam1", "person")
    assert event_type == "intruder_detected"
```

## Implementation (edit `secur/main.py` verbatim)

1. Add a top-level import after the existing imports block (near the other `from .X import` lines):
```python
from .identity import IdentityRecognizer, decide_event, RECOGNITION_LABELS
```

2. Add a free function (e.g., after `format_detections`):
```python
def decide_worker_event(detections, identity_info, zone_classification, camera_name, label=None):
    if identity_info is not None:
        decision = decide_event(identity_info, zone_classification, camera_name, label)
        if decision is not None:
            return decision
    if detections:
        return ("snapshot_info", format_detections(detections), None, None, None, None)
    return ("motion_detected", f"Movimento detectado na câmera {camera_name}", None, None, None, None)
```

3. Update `CameraWorker.__init__` to accept the recognizer (add the parameter, keep `...` for the rest of the existing body):
```python
def __init__(self, camera, storage, alerts, object_detector, identity_recognizer=None):
    self.camera = camera
    self.storage = storage
    self.alerts = alerts
    self.object_detector = object_detector
    self.identity_recognizer = identity_recognizer
    ...
```

4. Inside `run()`, REPLACE the existing detection→event block (currently ~lines 84-93 that call `self.object_detector.detect(frame)` and then branch on `detections` to set `event_type`/`details` and call `add_event`/`alerts.send`) with:
```python
detections = self.object_detector.detect(frame)
identity_info = None
identity_label = None
if detections and self.identity_recognizer is not None:
    for det in detections:
        if det["label"] in RECOGNITION_LABELS:
            bbox = det["bbox"]
            x, y, w, h = bbox["x"], bbox["y"], bbox["w"], bbox["h"]
            crop = frame[y:y + h, x:x + w]
            if crop.size > 0:
                identity_info = self.identity_recognizer.recognize(crop, det["label"])
                identity_label = det["label"]
                break

event_type, details, identity_name, known, _label, category = decide_worker_event(
    detections, identity_info, zone_classification, self.camera["name"], identity_label
)

self.storage.add_event(self.camera["id"], zone_name, event_type, details)
self.alerts.send(
    self.camera["id"], zone_name, event_type, details, zone_classification,
    identity=identity_name, known=known, category=category,
    recognition_method=identity_info.get("method") if identity_info else None,
)
```
IMPORTANT: `zone_name` and `zone_classification` already exist earlier in `run()` — keep them; only replace the detection/event block. Do NOT remove the motion-detection/`no_motion` logic that precedes it.

5. Update `CameraManager.__init__` to accept and store the recognizer:
```python
def __init__(self, storage, alerts, object_detector, identity_recognizer=None):
    ...
    self.identity_recognizer = identity_recognizer
```
And in `monitor_cameras`, change the worker creation to:
```python
worker = CameraWorker(camera, self.storage, self.alerts, self.object_detector, self.identity_recognizer)
```

6. In `main()`, build the recognizer and pass it (add `from .identity import build_recognizer` and the two lines — note `build_recognizer` may also be reachable via the top import; import it once):
```python
identity_recognizer = build_recognizer(storage)
camera_manager = CameraManager(storage, alerts, object_detector, identity_recognizer)
```

Steps:
1. Write `tests/test_main_identity.py` verbatim from the Tests block.
2. Run `python -m pytest tests/test_main_identity.py -v` → expect FAIL (`ImportError: cannot import name 'decide_worker_event'`).
3. Apply the 6 edits above to `secur/main.py` (preserve all unrelated code in `run()` and `monitor_cameras`).
4. Run `python -m pytest tests/test_main_identity.py -v` → expect PASS.
5. Commit ONLY those two files: `git add secur/main.py tests/test_main_identity.py && git commit -m "feat(main): wire IdentityRecognizer into CameraWorker event decision"`

GLOBAL CONSTRAINTS: Event-driven; recognizer is optional (None = old behavior). `decide_worker_event` returns a 6-tuple. Per AGENTS.md integrate via `dev` branch (already on it). Python 3.14; tests `python -m pytest`.