import os
from pathlib import Path
import sys

root = Path('C:/git')
ha = root / '.ha_token'
tg = root / '.telegramBot_token'
chat = root / 'telegram_chat_id.txt'
env = os.environ.copy()
if ha.exists():
    env['HOME_ASSISTANT_TOKEN'] = ha.read_text().strip()
if tg.exists():
    env['TELEGRAM_BOT_TOKEN'] = tg.read_text().strip()
if chat.exists():
    env['TELEGRAM_CHAT_ID'] = chat.read_text().strip()

os.execvpe('py', ['py', '-3', '-m', 'pytest', '-q'], env)
