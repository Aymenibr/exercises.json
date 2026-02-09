from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional

import cv2
import numpy as np

try:
    import mediapipe as mp
except ImportError as exc:  # pragma: no cover - runtime guard
    raise RuntimeError(
        "mediapipe is required for pose extraction. Install with `pip install mediapipe opencv-python`."
    ) from exc


@dataclass
class Landmark:
    """Normalized landmark returned by MediaPipe Pose."""

    x: float
    y: float
    z: float
    visibility: float


@dataclass
class PoseDetectionResult:
    """Container for a single image pose detection."""

    landmarks: List[Landmark]
    visibility_avg: float
    width: int
    height: int
    image_bgr: Optional[np.ndarray]
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and len(self.landmarks) > 0


def _to_landmarks(mediapipe_landmarks) -> List[Landmark]:
    return [
        Landmark(lm.x, lm.y, lm.z, lm.visibility)
        for lm in mediapipe_landmarks.landmark
    ]


def detect_pose(
    image_path: str,
    static_image_mode: bool = True,
    model_complexity: int = 1,
    min_detection_confidence: float = 0.5,
    min_tracking_confidence: float = 0.5,
) -> PoseDetectionResult:
    """
    Run MediaPipe Pose on a single image and return normalized landmarks.

    Args:
        image_path: Path to image file.
        static_image_mode: If True, runs in single-image mode.
        model_complexity: 0/1/2 per MediaPipe.
        min_detection_confidence: Threshold for detection.
        min_tracking_confidence: Threshold for tracking (unused for static images but kept for parity).
    """
    if not os.path.exists(image_path):
        return PoseDetectionResult([], 0.0, 0, 0, None, f"Image not found: {image_path}")

    image_bgr = cv2.imread(image_path)
    if image_bgr is None:
        return PoseDetectionResult([], 0.0, 0, 0, None, f"Unable to read image: {image_path}")

    height, width = image_bgr.shape[:2]
    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)

    with mp.solutions.pose.Pose(
        static_image_mode=static_image_mode,
        model_complexity=model_complexity,
        min_detection_confidence=min_detection_confidence,
        min_tracking_confidence=min_tracking_confidence,
    ) as pose:
        results = pose.process(image_rgb)

    if not results.pose_landmarks:
        return PoseDetectionResult([], 0.0, width, height, image_bgr, "Pose landmarks not detected")

    landmarks = _to_landmarks(results.pose_landmarks)
    visibility_avg = float(np.mean([lm.visibility for lm in landmarks]))

    return PoseDetectionResult(
        landmarks=landmarks,
        visibility_avg=visibility_avg,
        width=width,
        height=height,
        image_bgr=image_bgr,
    )

