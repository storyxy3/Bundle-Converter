"""Game profiles (tools/converter/profiles/<game>.json): the facts the converter needs about a game, kept out of code."""
import json
from pathlib import Path

PROFILE_DIR = Path(__file__).resolve().parents[1] / "profiles"


def load(game):
    path = PROFILE_DIR / f"{game}.json"
    if not path.exists():
        raise SystemExit(f"no profile {path}; known: {sorted(p.stem for p in PROFILE_DIR.glob('*.json'))}")
    return json.loads(path.read_text())


def expand_sides(entries, sides=("Left", "Right")):
    """Entries whose strings contain {S} become one entry per side."""
    out = []
    for e in entries:
        if any("{S}" in str(v) for v in e.values()):
            for s in sides:
                out.append({k: v.replace("{S}", s) if isinstance(v, str) else v for k, v in e.items()})
        else:
            out.append(e)
    return out
