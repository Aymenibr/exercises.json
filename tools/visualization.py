from __future__ import annotations

from typing import Optional

import cv2
import matplotlib

# Use non-interactive backend for headless environments
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mediapipe as mp

try:
    from .metrics import Biomechanics
    from .pose_detector import Landmark, PoseDetectionResult
    from .validators import ValidationResult
except ImportError:  # pragma: no cover
    from metrics import Biomechanics
    from pose_detector import Landmark, PoseDetectionResult
    from validators import ValidationResult


def _draw_skeleton(image_bgr, landmarks, width: int, height: int):
    """Draw a simple skeleton overlay using normalized landmarks."""
    overlay = image_bgr.copy()
    connections = mp.solutions.pose.POSE_CONNECTIONS

    def to_px(lm: Landmark):
        return int(lm.x * width), int(lm.y * height)

    for idx1, idx2 in connections:
        lm1, lm2 = landmarks[idx1], landmarks[idx2]
        if lm1.visibility < 0.4 or lm2.visibility < 0.4:
            continue
        x1, y1 = to_px(lm1)
        x2, y2 = to_px(lm2)
        cv2.line(overlay, (x1, y1), (x2, y2), (0, 255, 0), 2)

    for lm in landmarks:
        if lm.visibility < 0.4:
            continue
        x, y = to_px(lm)
        cv2.circle(overlay, (x, y), 3, (255, 0, 0), -1)

    return overlay


def render_verification_view(
    start: PoseDetectionResult,
    start_bio: Biomechanics,
    start_val: ValidationResult,
    end: PoseDetectionResult,
    end_bio: Biomechanics,
    end_val: ValidationResult,
    output_path: Optional[str] = None,
    show: bool = False,
):
    """Create a 4-panel verification plot and optionally save/show it."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))

    # Start pose visualization
    start_overlay = _draw_skeleton(start.image_bgr, start.landmarks, start.width, start.height)
    axes[0, 0].imshow(cv2.cvtColor(start_overlay, cv2.COLOR_BGR2RGB))
    axes[0, 0].axis("off")
    axes[0, 0].set_title("Start pose")

    # End pose visualization
    end_overlay = _draw_skeleton(end.image_bgr, end.landmarks, end.width, end.height)
    axes[0, 1].imshow(cv2.cvtColor(end_overlay, cv2.COLOR_BGR2RGB))
    axes[0, 1].axis("off")
    axes[0, 1].set_title("End pose")

    # Metrics panel
    metrics_lines = ["Joint Angles (°):"]
    for key in sorted(start_bio.angles.keys()):
        metrics_lines.append(
            f"{key:16s} start={start_bio.angles[key]:6.1f} end={end_bio.angles[key]:6.1f}"
        )
    metrics_lines.append("")
    metrics_lines.append("Limb Ratios:")
    for key in sorted(start_bio.ratios.keys()):
        metrics_lines.append(
            f"{key:16s} start={start_bio.ratios[key]:6.3f} end={end_bio.ratios[key]:6.3f}"
        )
    metrics_lines.append("")
    metrics_lines.append("Orientation (°):")
    for key in sorted(start_bio.orientation.keys()):
        metrics_lines.append(
            f"{key:16s} start={start_bio.orientation[key]:6.1f} end={end_bio.orientation[key]:6.1f}"
        )
    metrics_lines.append("")
    metrics_lines.append(
        f"Visibility avg start={start_bio.visibility_avg:.3f} end={end_bio.visibility_avg:.3f}"
    )
    axes[1, 0].axis("off")
    axes[1, 0].text(0, 1, "\n".join(metrics_lines), va="top", family="monospace")
    axes[1, 0].set_title("Biomechanical metrics")

    # Validation summary
    axes[1, 1].axis("off")
    val_lines = ["Validation:"]
    val_lines.append(f"Start: {'PASS' if start_val.ok else 'FAIL'}")
    if not start_val.ok:
        val_lines += [f"- {iss.message}" for iss in start_val.issues]
    val_lines.append("")
    val_lines.append(f"End: {'PASS' if end_val.ok else 'FAIL'}")
    if not end_val.ok:
        val_lines += [f"- {iss.message}" for iss in end_val.issues]

    color = "green" if start_val.ok and end_val.ok else "red"
    axes[1, 1].text(0, 1, "\n".join(val_lines), va="top", family="monospace", color=color)
    axes[1, 1].set_title("Confidence / validation")

    fig.tight_layout()

    if output_path:
        fig.savefig(output_path, dpi=150)
    if show:
        plt.show()
    plt.close(fig)

    return output_path
