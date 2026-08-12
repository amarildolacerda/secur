import cv2
import numpy as np
import base64
import requests
import sys

server = sys.argv[1] if len(sys.argv)>1 else 'http://localhost:8000'
name = sys.argv[2] if len(sys.argv)>2 else 'Sample'
species = sys.argv[3] if len(sys.argv)>3 else 'person'

# create a simple colored image
img = np.zeros((120,160,3), dtype=np.uint8)
img[:] = (20,120,220)  # BGR
success, buf = cv2.imencode('.jpg', img)
if not success:
    print('failed to encode')
    sys.exit(1)

b64 = base64.b64encode(buf.tobytes()).decode('ascii')
payload = {'name': name, 'species': species, 'images': [b64]}

r = requests.post(f'{server}/identities', json=payload, timeout=10)
print('POST', r.status_code, r.text)

r2 = requests.get(f'{server}/identities', timeout=5)
print('LIST', r2.status_code, r2.text)

# if thumbnail_url available, fetch it
import json
try:
    arr = r2.json()
    for it in arr:
        if it.get('thumbnail_url'):
            t = requests.get(server + it['thumbnail_url'], timeout=5)
            print('THUMB', it['id'], t.status_code, 'len=', len(t.content))
            break
except Exception as e:
    print('err', e)
