from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

EX_SRC = Path("exercises-json-only")
OUT_DIR = Path("engine-exercises")
MANIFEST_PATH = OUT_DIR / "manifest.json"
SIGNAL_MAP_PATH = Path("tools/signal_map.json")

# Landmark triplets for angleDeg2d
JOINT_LM = {
    "elbow": (["LEFT_SHOULDER", "LEFT_ELBOW", "LEFT_WRIST"], ["RIGHT_SHOULDER", "RIGHT_ELBOW", "RIGHT_WRIST"]),
    "knee": (["LEFT_HIP", "LEFT_KNEE", "LEFT_ANKLE"], ["RIGHT_HIP", "RIGHT_KNEE", "RIGHT_ANKLE"]),
    "hip": (["LEFT_SHOULDER", "LEFT_HIP", "LEFT_KNEE"], ["RIGHT_SHOULDER", "RIGHT_HIP", "RIGHT_KNEE"]),
    "shoulder": (["LEFT_ELBOW", "LEFT_SHOULDER", "LEFT_HIP"], ["RIGHT_ELBOW", "RIGHT_SHOULDER", "RIGHT_HIP"]),
    "ankle": (["LEFT_KNEE", "LEFT_ANKLE", "LEFT_FOOT_INDEX"], ["RIGHT_KNEE", "RIGHT_ANKLE", "RIGHT_FOOT_INDEX"]),
    # wrist_height uses coord not angle, handled separately
}

ANGLE_KEYS = {
    "elbow": ("elbow_left", "elbow_right"),
    "knee": ("knee_left", "knee_right"),
    "hip": ("hip_left", "hip_right"),
    "shoulder": ("shoulder_left", "shoulder_right"),
    "ankle": ("ankle_left", "ankle_right"),
}

def load_signal_overrides() -> Dict[str, str]:
    if SIGNAL_MAP_PATH.exists():
        data = json.loads(SIGNAL_MAP_PATH.read_text(encoding="utf-8"))
        return {k.lower(): v for k, v in data.get("overrides", {}).items()}
    return {}


def heuristic_signal(name: str) -> str:
    n = name.lower()
    if any(k in n for k in ["squat", "lunge", "deadlift", "step", "split", "jerk", "snatch", "clean"]):
        return "knee"
    if any(k in n for k in ["bridge", "plank", "hip", "glute", "thrust"]):
        return "hip"
    if any(k in n for k in ["curl", "press", "push", "dip", "extension"]):
        return "elbow"
    if any(k in n for k in ["raise", "fly", "row", "pull", "lift"]):
        return "shoulder"
    return "elbow"


def sanitize(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower() or "exercise"


def derive_angles(logic: dict, signal: str) -> Tuple[float, float]:
    keys = ANGLE_KEYS.get(signal)
    if not keys:
        return (60.0, 170.0)
    start = logic["states"]["start"]["angles"]
    end = logic["states"]["end"]["angles"]
    vals = [start.get(keys[0]), start.get(keys[1]), end.get(keys[0]), end.get(keys[1])]
    vals = [v for v in vals if isinstance(v, (int, float))]
    if not vals:
        return (60.0, 170.0)
    return (min(vals), max(vals))


def build_guardrail(signal: str) -> dict:
    if signal == "wrist_height":
        req = ["LEFT_SHOULDER", "RIGHT_SHOULDER", "LEFT_WRIST", "RIGHT_WRIST"]
    else:
        left, right = JOINT_LM.get(signal, JOINT_LM["elbow"])
        req = list(set(left + right))
    return {
        "required": req,
        "frameRequired": req,
        "minVisibility": 0.55,
    }


def progress_expr(signal: str, top: float, bottom: float) -> dict:
    if signal == "wrist_height":
        return {
            "op": "sub",
            "a": {"const": 1},
            "b": {
                "op": "clamp",
                "value": {
                    "op": "div",
                    "a": {
                        "op": "sub",
                        "a": {"op": "avgCoord", "axis": "y", "landmarks": ["LEFT_SHOULDER", "RIGHT_SHOULDER"]},
                        "b": {"op": "avgCoord", "axis": "y", "landmarks": ["LEFT_WRIST", "RIGHT_WRIST"]},
                    },
                    "b": {"const": 0.25},
                },
                "min": {"const": 0},
                "max": {"const": 1},
            },
            "map": {
                "type": "invertAngleRange",
                "topAngleMaxDegRef": "thresholds.repProgressTopRaw",
                "bottomAngleMinDegRef": "thresholds.repProgressBottomRaw",
            },
        }
    # angle-based
    left, right = JOINT_LM.get(signal, JOINT_LM["elbow"])
    return {
        "op": "sub",
        "a": {"const": 1},
        "b": {
            "op": "avg",
            "args": [
                {
                    "op": "clamp",
                    "value": {
                        "op": "div",
                        "a": {
                            "op": "sub",
                            "a": {"op": "angleDeg2d", "a": left[0], "b": left[1], "c": left[2]},
                            "b": {"ref": "thresholds.repAngleBottomDeg"},
                        },
                        "b": {
                            "op": "sub",
                            "a": {"ref": "thresholds.repAngleTopDeg"},
                            "b": {"ref": "thresholds.repAngleBottomDeg"},
                        },
                    },
                    "min": {"const": 0},
                    "max": {"const": 1},
                },
                {
                    "op": "clamp",
                    "value": {
                        "op": "div",
                        "a": {
                            "op": "sub",
                            "a": {"op": "angleDeg2d", "a": right[0], "b": right[1], "c": right[2]},
                            "b": {"ref": "thresholds.repAngleBottomDeg"},
                        },
                        "b": {
                            "op": "sub",
                            "a": {"ref": "thresholds.repAngleTopDeg"},
                            "b": {"ref": "thresholds.repAngleBottomDeg"},
                        },
                    },
                    "min": {"const": 0},
                    "max": {"const": 1},
                },
            ],
        },
        "map": {
            "type": "invertAngleRange",
            "topAngleMaxDegRef": "thresholds.repProgressTopRaw",
            "bottomAngleMinDegRef": "thresholds.repProgressBottomRaw",
        },
    }


def build_exercise(meta: dict, logic: dict, signal: str) -> dict:
    top, bottom = derive_angles(logic, signal)
    if top == bottom:
        top, bottom = (bottom - 30.0, bottom + 30.0)

    ex_name = meta.get("name") or meta.get("id") or "exercise"
    guardrail = build_guardrail(signal)

    thresholds = {
        "repAngleTopDeg": float(top),
        "repAngleBottomDeg": float(bottom),
        "repProgressTopRaw": 0,
        "repProgressBottomRaw": 1,
        "maxArmSyncDiffDeg": 25,
    }

    rep_counter = {
        "version": 1,
        "mode": "full_cycle",
        "progress": progress_expr(signal, top, bottom),
        "smoothing": {"emaAlpha": 0.30},
        "start": {"leaveBottomProgress": 0.22, "minUpVel": 0.00025},
        "extremes": {"topProgressMin": 0.8, "bottomProgressMax": 0.18},
        "quality": {
            "warnBadFraction": 0.15,
            "rejectBadFraction": 0.30,
            "minRepMs": 1500,
            "minDownMs": 600,
            "maxRepMs": 9000,
            "syncDelta": 0.20,
            "maxSwayRatio": 0.14,
            "maxProgressVelAbs": 0.006,
        },
    }

    facts = {
        "bothVisible": {
            "op": "allVisible",
            "landmarks": guardrail["required"],
            "minVisibility": {"ref": "guardrail.minVisibility"},
        }
    }

    messages = {
        "no_pose": "No pose detected.",
        "move_back_visible": "Move back so required landmarks are visible.",
        "stage_down": "Move to top position.",
        "stage_up": "Return to start position.",
        "good": "Good rep.",
    }

    rules = [
        {
            "name": "Required visible",
            "priority": 1000,
            "conditions": {"all": [{"fact": "bothVisible", "operator": "equal", "value": False}]},
            "event": {"type": "move_back_visible", "params": {"ok": False, "messageId": "move_back_visible", "priority": 1000}},
        }
    ]

    return {
        "schemaVersion": 1,
        "id": sanitize(ex_name),
        "guardrail": guardrail,
        "thresholds": thresholds,
        "repCounter": rep_counter,
        "facts": facts,
        "messages": messages,
        "rules": rules,
        "comment__auto_generated": f"Generated from exercises-json-only; signal={signal}",
    }


def main():
    overrides = load_signal_overrides()
    OUT_DIR.mkdir(exist_ok=True)
    manifest_entries = []

    for json_path in sorted(EX_SRC.glob("*.json")):
        data = json.loads(json_path.read_text(encoding="utf-8"))
        meta = data.get("metadata", {})
        logic = data.get("logic", {})
        ex_name = meta.get("name") or json_path.stem
        signal = overrides.get(json_path.stem.lower(), heuristic_signal(ex_name))

        ex_def = build_exercise(meta, logic, signal)
        fname = sanitize(ex_name) + ".json"
        (OUT_DIR / fname).write_text(json.dumps(ex_def, indent=2), encoding="utf-8")

        instr = meta.get("instructions")
        hint = instr[0] if isinstance(instr, list) and instr else ""
        manifest_entries.append(
            {
                "id": sanitize(ex_name),
                "slug": sanitize(ex_name).replace("_", "-"),
                "name": meta.get("name", ex_name),
                "hint": hint,
                "definitionKey": sanitize(ex_name),
            }
        )
        print(f"Wrote {OUT_DIR / fname} (signal={signal})")

    manifest = {"version": 1, "defaultExerciseId": manifest_entries[0]["id"] if manifest_entries else "", "exercises": manifest_entries}
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote manifest {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
