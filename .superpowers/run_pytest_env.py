from pathlib import Path
import os, subprocess, sys

env = os.environ.copy()
env_file = Path('c:/git/tucuxi/.env')
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip()

proc = subprocess.run(['py', '-3', '-m', 'pytest', '-q'], env=env)
sys.exit(proc.returncode)
