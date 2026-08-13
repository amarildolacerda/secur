import sys
from pathlib import Path
import base64
import json
import cv2
import numpy as np
# Ensure repo root is importable
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))
from secur.app import create_app
from secur.identity import IdentityRecognizer

# stub embedder: returns a fixed normalized vector
def make_stub(vec):
    v = np.array(vec, dtype=np.float32)
    v = v / np.linalg.norm(v)
    return lambda img: v

app = create_app()
# recognizer factory returns an IdentityRecognizer with stub embedders
app.recognizer_factory = lambda storage: IdentityRecognizer(storage, face_embedder=make_stub([1,0,0]), reid_embedder=make_stub([1,0,0]), threshold=0.6, enabled=True)
client = app.test_client()

# create a sample image (white square)
img = np.ones((100,100,3), dtype=np.uint8) * 255
success, buf = cv2.imencode('.jpg', img)
if not success:
    raise SystemExit('Failed to encode test image')
img_b64 = base64.b64encode(buf.tobytes()).decode('ascii')

payload = {"name": "João", "species": "person", "images": [img_b64]}
resp = client.post('/identities', data=json.dumps(payload), content_type='application/json')
print('POST /identities ->', resp.status_code, resp.get_data(as_text=True))

resp2 = client.get('/identities')
print('GET /identities ->', resp2.status_code, resp2.get_data(as_text=True))
