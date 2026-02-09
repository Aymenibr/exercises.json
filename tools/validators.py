from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import mediapipe as mp

try:
    from .metrics import Biomechanics
    from .pose_detector import Landmark
except ImportError:  # pragma: no cover
    from metrics import Biomechanics
    from pose_detector import Landmark

PL = mp.solutions.pose.PoseLandmark


@dataclass
class ValidationIssue:
    message: str


@dataclass
class ValidationResult:
    ok: bool
    issues: List[ValidationIssue] = field(default_factory=list)

    def summary(self) -> str:
        if self.ok:
            return "PASS"
        return "; ".join(issue.message for issue in self.issues)


VISIBILITY_THRESHOLD = 0.6
SYMMETRY_TOLERANCE_DEG = 15.0

# Reasonable physiological ranges (elderly-safe defaults)
ANGLE_RANGES = {
    "elbow": (10.0, 175.0),
    "knee": (20.0, 170.0),
    "hip": (20.0, 170.0),
    "shoulder": (20.0, 170.0),
}

TORSO_TILT_MAX_DEG = 45.0
HIP_SHOULDER_ALIGNMENT_MAX_DEG = 20.0


def validate_pose(bio: Biomechanics, landmarks: List[Landmark]) -> ValidationResult:
    issues: List[ValidationIssue] = []

    # Visibility per required landmark
    required_points = [
        PL.LEFT_SHOULDER,
        PL.RIGHT_SHOULDER,
        PL.LEFT_ELBOW,
        PL.RIGHT_ELBOW,
        PL.LEFT_WRIST,
        PL.RIGHT_WRIST,
        PL.LEFT_HIP,
        PL.RIGHT_HIP,
        PL.LEFT_KNEE,
        PL.RIGHT_KNEE,
        PL.LEFT_ANKLE,
        PL.RIGHT_ANKLE,
    ]
    low_visibility = [
        (pl.name, landmarks[pl.value].visibility)
        for pl in required_points
        if landmarks[pl.value].visibility < VISIBILITY_THRESHOLD
    ]
    if low_visibility:
        labels = ", ".join(f"{name}({vis:.2f})" for name, vis in low_visibility)
        issues.append(
            ValidationIssue(
                f"Visibility below {VISIBILITY_THRESHOLD}: {labels}"
            )
        )

    # Angle ranges
    ranges = [
        ("elbow_left", "elbow"),
        ("elbow_right", "elbow"),
        ("knee_left", "knee"),
        ("knee_right", "knee"),
        ("hip_left", "hip"),
        ("hip_right", "hip"),
        ("shoulder_left", "shoulder"),
        ("shoulder_right", "shoulder"),
    ]
    for key, group in ranges:
        lo, hi = ANGLE_RANGES[group]
        val = bio.angles.get(key, float("nan"))
        if val != val or val < lo or val > hi:
            issues.append(
                ValidationIssue(f"{key} angle {val:.1f}° out of range [{lo}, {hi}]")
            )

    # Left/right symmetry
    pairs = [
        ("elbow_left", "elbow_right"),
        ("knee_left", "knee_right"),
        ("hip_left", "hip_right"),
        ("shoulder_left", "shoulder_right"),
    ]
    for left, right in pairs:
        l_val, r_val = bio.angles[left], bio.angles[right]
        if abs(l_val - r_val) > SYMMETRY_TOLERANCE_DEG:
            issues.append(
                ValidationIssue(
                    f"Symmetry: {left} vs {right} differ by {abs(l_val - r_val):.1f}° (>{SYMMETRY_TOLERANCE_DEG}°)"
                )
            )

    # Torso realism
    if bio.orientation["torso_tilt_deg"] > TORSO_TILT_MAX_DEG:
        issues.append(
            ValidationIssue(
                f"Torso tilt {bio.orientation['torso_tilt_deg']:.1f}° exceeds {TORSO_TILT_MAX_DEG}°"
            )
        )
    if bio.orientation["hip_shoulder_alignment_deg"] > HIP_SHOULDER_ALIGNMENT_MAX_DEG:
        issues.append(
            ValidationIssue(
                f"Hip/shoulder alignment {bio.orientation['hip_shoulder_alignment_deg']:.1f}° exceeds {HIP_SHOULDER_ALIGNMENT_MAX_DEG}°"
            )
        )

    return ValidationResult(ok=len(issues) == 0, issues=issues)
