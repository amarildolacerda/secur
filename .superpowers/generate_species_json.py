import json
from pathlib import Path

# import repo root so src package can be loaded
import sys
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root))

from src.identity import RECOGNITION_LABELS

OUT = Path(repo_root) / "data" / "species.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

species_vals = sorted(set(RECOGNITION_LABELS.values()))
label_map = {"person": "Pessoa", "animal": "Animal", "vehicle": "Veículo"}

payload = {"species": [{"value": s, "label": label_map.get(s, s.capitalize())} for s in species_vals]}

with OUT.open("w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=2)

print(f"Wrote {OUT}")
