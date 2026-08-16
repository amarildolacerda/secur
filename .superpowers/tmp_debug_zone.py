from src.app import create_app
import json
app = create_app()
client = app.test_client()
payload = json.dumps({"name": "Entrada", "classification": "pública"})
res = client.post('/zones', data=payload, content_type='application/json')
print('status', res.status_code)
print('data', res.get_data(as_text=True))
