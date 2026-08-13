import os
from pathlib import Path
import sys
import pytest

root = Path('C:/git')
ha = root / '.ha_token'
tg = root / '.telegramBot_token'
chat = root / 'telegram_chat_id.txt'
if ha.exists():
    os.environ['HOME_ASSISTANT_TOKEN'] = ha.read_text().strip()
if tg.exists():
    os.environ['TELEGRAM_BOT_TOKEN'] = tg.read_text().strip()
if chat.exists():
    os.environ['TELEGRAM_CHAT_ID'] = chat.read_text().strip()

# Run pytest
sys.exit(pytest.main(['-q']))
