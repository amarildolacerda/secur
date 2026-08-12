"""Capture one frame from the default webcam and POST it to the Secur `/identities` endpoint.
Usage: py scripts/capture_and_enroll.py "Name" species http://localhost:8000

Requires: opencv-python, requests
"""
import sys
import cv2
import base64
import requests
import json

name = sys.argv[1] if len(sys.argv) > 1 else "Nome"
species = sys.argv[2] if len(sys.argv) > 2 else "person"
server = sys.argv[3] if len(sys.argv) > 3 else "http://localhost:8000"

cap = cv2.VideoCapture(0)
if not cap.isOpened():
    raise SystemExit("Falha ao abrir a câmera. Verifique se está conectada e liberada.")

ret, frame = cap.read()
cap.release()
if not ret or frame is None:
    raise SystemExit("Falha ao capturar frame da câmera")

success, buf = cv2.imencode('.jpg', frame)
if not success:
    raise SystemExit('Falha ao codificar a imagem')

b64 = base64.b64encode(buf.tobytes()).decode('ascii')

payload = {"name": name, "species": species, "images": [b64]}

try:
    r = requests.post(f"{server}/identities", json=payload, timeout=10)
    print(r.status_code)
    try:
        print(r.json())
    except Exception:
        print(r.text)
except Exception as e:
    print('Erro ao conectar com o servidor:', e)
