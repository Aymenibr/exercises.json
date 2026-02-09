from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict

ROOT = Path(__file__).resolve().parent.parent
EXERCISES_DIR = ROOT / "exercises"
OUTPUT_DIR = ROOT / "exercises-json-only"


def sanitize_name(name: str) -> str:
    """Create a filesystem-friendly filename like 'pushup.json'."""
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
    return f"{cleaned}.json" if cleaned else "exercise.json"


def merge_exercise(ex_dir: Path) -> None:
    exercise_meta_path = ex_dir / "exercise.json"
    logic_path = ex_dir / "exercise.logic.json"
    if not exercise_meta_path.exists() or not logic_path.exists():
        return

    with exercise_meta_path.open("r", encoding="utf-8") as f:
        meta = json.load(f)
    with logic_path.open("r", encoding="utf-8") as f:
        logic = json.load(f)

    output = {
        "metadata": meta,
        "logic": logic,
    }

    name_source = meta.get("name") if isinstance(meta, dict) else None
    filename = sanitize_name(name_source or ex_dir.name)

    OUTPUT_DIR.mkdir(exist_ok=True)
    out_path = OUTPUT_DIR / filename
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"Wrote {out_path}")


def main():
    if not EXERCISES_DIR.exists():
        raise SystemExit(f"Exercises directory not found at {EXERCISES_DIR}")

    for ex_dir in sorted(EXERCISES_DIR.iterdir()):
        if ex_dir.is_dir():
            merge_exercise(ex_dir)


if __name__ == "__main__":
    main()
