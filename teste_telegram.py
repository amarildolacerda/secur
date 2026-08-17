import os
import requests
from pathlib import Path

# Token lido do arquivo de token em C:\git (mesmo mecanismo do run_with_tokens.py)
# ou da variável de ambiente TELEGRAM_BOT_TOKEN. Nunca hardcode o token no código.
def _load_token():
    # Resolve o arquivo de token em Windows (C:/git) e WSL (/mnt/c/git)
    candidates = [Path("C:/git/.telegramBot_token"), Path("/mnt/c/git/.telegramBot_token")]
    for token_file in candidates:
        if token_file.exists():
            return token_file.read_text().strip()
    return os.getenv("TELEGRAM_BOT_TOKEN", "")

TOKEN = _load_token()
if not TOKEN:
    raise SystemExit("Token não encontrado. Configure C:/git/.telegramBot_token ou a env TELEGRAM_BOT_TOKEN.")

BASE_URL = f"https://api.telegram.org/bot{TOKEN}"


def get_updates():
    """Obtém as últimas mensagens enviadas ao bot"""
    url = f"{BASE_URL}/getUpdates"
    resp = requests.get(url)
    data = resp.json()
    print("Resposta completa:", data)

    if "result" in data and len(data["result"]) > 0:
        chat_id = data["result"][-1]["message"]["chat"]["id"]
        print("Seu chat_id é:", chat_id)
        return chat_id
    else:
        print("Nenhuma mensagem encontrada. Envie algo para o bot primeiro.")
        return None


def send_message(chat_id, text):
    """Envia uma mensagem para o chat_id informado"""
    url = f"{BASE_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    resp = requests.post(url, data=payload)
    print("Resposta do envio:", resp.json())


if __name__ == "__main__":
    # Primeiro, pega o chat_id das últimas mensagens
    chat_id = get_updates()
    if chat_id:
        # Agora envia uma mensagem usando o chat_id correto
        send_message(chat_id, "Agora sim, mensagem com chat_id válido!")