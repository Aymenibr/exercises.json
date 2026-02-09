from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import mediapipe as mp

try:
    from .pose_detector import Landmark
except ImportError:  # pragma: no cover - support running as a script
    from pose_detector import Landmark

PL = mp.solutions.pose.PoseLandmark


@dataclass
class Biomechanics:
    angles: Dict[str, float]
    ratios: Dict[str, float]
    orientation: Dict[str, float]
    visibility_avg: float


def _to_point(lm: Landmark) -> np.ndarray:
    return np.array([lm.x, lm.y, lm.z], dtype=float)


def _angle(p1: np.ndarray, p2: np.ndarray, p3: np.ndarray) -> float:
    """
    Angle at p2 formed by p1->p2 and p3->p2, in degrees.
    """
    v1 = p1 - p2
    v2 = p3 - p2
    denom = np.linalg.norm(v1) * np.linalg.norm(v2)
    if denom == 0:
        return float("nan")
    cos_theta = np.clip(np.dot(v1, v2) / denom, -1.0, 1.0)
    return float(np.degrees(np.arccos(cos_theta)))


def _distance(p1: np.ndarray, p2: np.ndarray) -> float:
    return float(np.linalg.norm(p1 - p2))


def _line_angle_deg(p1: np.ndarray, p2: np.ndarray) -> float:
    """Angle of vector p1->p2 relative to +x axis."""
    v = p2 - p1
    return float(np.degrees(np.arctan2(v[1], v[0])))


def compute_biomechanics(landmarks: List[Landmark]) -> Biomechanics:
    """
    Compute joint angles, limb ratios, torso orientation, and visibility.
    Landmarks are expected to be MediaPipe normalized coordinates.
    """
    def pt(name: PL) -> np.ndarray:
        return _to_point(landmarks[name.value])

    # Comprehensive joint angles (middle point of each triplet)
    TRIPLETS = {
        # Upper body
        "shoulder_left": (PL.LEFT_ELBOW, PL.LEFT_SHOULDER, PL.LEFT_HIP),
        "shoulder_right": (PL.RIGHT_ELBOW, PL.RIGHT_SHOULDER, PL.RIGHT_HIP),
        "elbow_left": (PL.LEFT_SHOULDER, PL.LEFT_ELBOW, PL.LEFT_WRIST),
        "elbow_right": (PL.RIGHT_SHOULDER, PL.RIGHT_ELBOW, PL.RIGHT_WRIST),
        "wrist_left": (PL.LEFT_ELBOW, PL.LEFT_WRIST, PL.LEFT_INDEX),
        "wrist_right": (PL.RIGHT_ELBOW, PL.RIGHT_WRIST, PL.RIGHT_INDEX),
        "neck_left": (PL.LEFT_HIP, PL.LEFT_SHOULDER, PL.NOSE),
        "neck_right": (PL.RIGHT_HIP, PL.RIGHT_SHOULDER, PL.NOSE),
        # Torso / spine approximations
        "torso_left": (PL.LEFT_KNEE, PL.LEFT_HIP, PL.LEFT_SHOULDER),
        "torso_right": (PL.RIGHT_KNEE, PL.RIGHT_HIP, PL.RIGHT_SHOULDER),
        # Lower body
        "hip_left": (PL.LEFT_SHOULDER, PL.LEFT_HIP, PL.LEFT_KNEE),
        "hip_right": (PL.RIGHT_SHOULDER, PL.RIGHT_HIP, PL.RIGHT_KNEE),
        "knee_left": (PL.LEFT_HIP, PL.LEFT_KNEE, PL.LEFT_ANKLE),
        "knee_right": (PL.RIGHT_HIP, PL.RIGHT_KNEE, PL.RIGHT_ANKLE),
        "ankle_left": (PL.LEFT_KNEE, PL.LEFT_ANKLE, PL.LEFT_FOOT_INDEX),
        "ankle_right": (PL.RIGHT_KNEE, PL.RIGHT_ANKLE, PL.RIGHT_FOOT_INDEX),
    }

    angles = {
        name: _angle(pt(a), pt(b), pt(c)) for name, (a, b, c) in TRIPLETS.items()
    }

    # Limb ratios (dimensionless)
    ratios = {
        "forearm_upperarm_left": _distance(pt(PL.LEFT_ELBOW), pt(PL.LEFT_WRIST))
        / max(_distance(pt(PL.LEFT_SHOULDER), pt(PL.LEFT_ELBOW)), 1e-6),
        "forearm_upperarm_right": _distance(pt(PL.RIGHT_ELBOW), pt(PL.RIGHT_WRIST))
        / max(_distance(pt(PL.RIGHT_SHOULDER), pt(PL.RIGHT_ELBOW)), 1e-6),
        "shin_thigh_left": _distance(pt(PL.LEFT_KNEE), pt(PL.LEFT_ANKLE))
        / max(_distance(pt(PL.LEFT_HIP), pt(PL.LEFT_KNEE)), 1e-6),
        "shin_thigh_right": _distance(pt(PL.RIGHT_KNEE), pt(PL.RIGHT_ANKLE))
        / max(_distance(pt(PL.RIGHT_HIP), pt(PL.RIGHT_KNEE)), 1e-6),
    }

    mid_shoulder = (pt(PL.LEFT_SHOULDER) + pt(PL.RIGHT_SHOULDER)) / 2
    mid_hip = (pt(PL.LEFT_HIP) + pt(PL.RIGHT_HIP)) / 2
    torso_vec = mid_shoulder - mid_hip
    vertical_vec = np.array([0.0, -1.0, 0.0])
    torso_tilt_deg = _angle(mid_hip + vertical_vec, mid_hip, mid_shoulder)

    shoulder_line_deg = abs(_line_angle_deg(pt(PL.LEFT_SHOULDER), pt(PL.RIGHT_SHOULDER)))
    hip_line_deg = abs(_line_angle_deg(pt(PL.LEFT_HIP), pt(PL.RIGHT_HIP)))
    hip_shoulder_alignment = abs(shoulder_line_deg - hip_line_deg)

    orientation = {
        "torso_tilt_deg": torso_tilt_deg,
        "hip_shoulder_alignment_deg": hip_shoulder_alignment,
    }

    visibility_avg = float(
        np.mean([lm.visibility for lm in landmarks])
    )

    # Round for stable JSON output
    angles = {k: round(v, 2) for k, v in angles.items()}
    ratios = {k: round(v, 3) for k, v in ratios.items()}
    orientation = {k: round(v, 2) for k, v in orientation.items()}

    return Biomechanics(
        angles=angles,
        ratios=ratios,
        orientation=orientation,
        visibility_avg=round(visibility_avg, 3),
    )
