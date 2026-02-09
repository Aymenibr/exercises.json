from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

try:
    import mediapipe as mp
    from ..metrics import Biomechanics
    from ..pose_detector import Landmark
except ImportError:  # pragma: no cover - allow running as script
    import mediapipe as mp
    from metrics import Biomechanics
    from pose_detector import Landmark


DEFAULT_TOLERANCES = {"angle_deg": 15, "ratio_pct": 0.15}


def build_logic_payload(
    exercise_name: str,
    start_bio: Biomechanics,
    end_bio: Biomechanics,
    rep_logic: str = "start -> end",
    tolerance: Dict[str, float] | None = None,
    start_landmarks: Optional[List[Landmark]] = None,
    end_landmarks: Optional[List[Landmark]] = None,
    include_coco: bool = False,
) -> Dict[str, Any]:
    def lm_to_dict(lm: Landmark) -> Dict[str, float]:
        return {"x": lm.x, "y": lm.y, "z": lm.z, "visibility": lm.visibility}

    def landmarks_block(landmarks: Optional[List[Landmark]]):
        if landmarks is None:
            return None
        names = [pl.name.lower() for pl in mp.solutions.pose.PoseLandmark]
        return {
            "ordered_names": names,
            "points": [lm_to_dict(lm) for lm in landmarks],
        }

    def to_coco_keypoints(landmarks: Optional[List[Landmark]]):
        if landmarks is None:
            return None
        idx_map = [
            mp.solutions.pose.PoseLandmark.NOSE.value,
            mp.solutions.pose.PoseLandmark.LEFT_EYE.value,
            mp.solutions.pose.PoseLandmark.RIGHT_EYE.value,
            mp.solutions.pose.PoseLandmark.LEFT_EAR.value,
            mp.solutions.pose.PoseLandmark.RIGHT_EAR.value,
            mp.solutions.pose.PoseLandmark.LEFT_SHOULDER.value,
            mp.solutions.pose.PoseLandmark.RIGHT_SHOULDER.value,
            mp.solutions.pose.PoseLandmark.LEFT_ELBOW.value,
            mp.solutions.pose.PoseLandmark.RIGHT_ELBOW.value,
            mp.solutions.pose.PoseLandmark.LEFT_WRIST.value,
            mp.solutions.pose.PoseLandmark.RIGHT_WRIST.value,
            mp.solutions.pose.PoseLandmark.LEFT_HIP.value,
            mp.solutions.pose.PoseLandmark.RIGHT_HIP.value,
            mp.solutions.pose.PoseLandmark.LEFT_KNEE.value,
            mp.solutions.pose.PoseLandmark.RIGHT_KNEE.value,
            mp.solutions.pose.PoseLandmark.LEFT_ANKLE.value,
            mp.solutions.pose.PoseLandmark.RIGHT_ANKLE.value,
        ]
        keypoints = []
        for idx in idx_map:
            lm = landmarks[idx]
            keypoints.extend([lm.x, lm.y, lm.visibility])
        return keypoints

    payload = {
        "exercise": exercise_name,
        "states": {
            "start": {
                "angles": start_bio.angles,
                "ratios": start_bio.ratios,
                "orientation": start_bio.orientation,
            },
            "end": {
                "angles": end_bio.angles,
                "ratios": end_bio.ratios,
                "orientation": end_bio.orientation,
            },
        },
        "rep_logic": rep_logic,
        "tolerance": tolerance or DEFAULT_TOLERANCES,
    }
    if start_landmarks is not None:
        payload["states"]["start"]["landmarks"] = landmarks_block(start_landmarks)
    if end_landmarks is not None:
        payload["states"]["end"]["landmarks"] = landmarks_block(end_landmarks)
    if include_coco:
        payload["coco"] = {
            "start_keypoints": to_coco_keypoints(start_landmarks),
            "end_keypoints": to_coco_keypoints(end_landmarks),
            "format": "coco-17-[x,y,visibility]*17 (normalized)",
        }
    return payload


def _maybe_validate(payload: Dict[str, Any], schema_path: str) -> None:
    """Validate payload against JSON schema if jsonschema is available."""
    if not os.path.exists(schema_path):
        return
    try:
        import jsonschema
    except ImportError:
        return

    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)
    jsonschema.validate(instance=payload, schema=schema)


def write_logic_json(payload: Dict[str, Any], output_path: str, schema_path: str | None = None) -> None:
    if schema_path:
        _maybe_validate(payload, schema_path)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
