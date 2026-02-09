from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Iterable, Optional, Tuple

import concurrent.futures as futures

from metrics import compute_biomechanics
from pose_detector import detect_pose
from validators import validate_pose
from visualization import render_verification_view
from exercise_logic_builder.serializer import (
    build_logic_payload,
    write_logic_json,
    DEFAULT_TOLERANCES,
)
from ui_confirm import prompt_accept_with_ui


def _read_exercise_name(ex_dir: Path) -> str:
    meta_path = ex_dir / "exercise.json"
    if meta_path.exists():
        try:
            with meta_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("name") or ex_dir.name
        except Exception:
            return ex_dir.name
    return ex_dir.name


def _find_image(ex_dir: Path, stem: str) -> Optional[Path]:
    """Locate image named `<stem>.(png|jpg|jpeg)` in images/ or root."""
    candidates = []
    for ext in ("png", "jpg", "jpeg"):
        candidates.append(ex_dir / "images" / f"{stem}.{ext}")
        candidates.append(ex_dir / f"{stem}.{ext}")
    for path in candidates:
        if path.exists():
            return path
    return None


def _load_reference_images(ex_dir: Path) -> Tuple[Path, Path]:
    start = _find_image(ex_dir, "0")
    end = _find_image(ex_dir, "1")
    if not start or not end:
        missing = []
        if not start:
            missing.append("0.(png|jpg)")
        if not end:
            missing.append("1.(png|jpg)")
        raise FileNotFoundError(f"Missing reference images: {', '.join(missing)} in {ex_dir}")
    return start, end


def _process_pose(image_path: Path):
    detection = detect_pose(str(image_path))
    if not detection.ok:
        raise RuntimeError(f"{image_path}: {detection.error}")
    bio = compute_biomechanics(detection.landmarks)
    val = validate_pose(bio, detection.landmarks)
    return detection, bio, val


def _prompt_accept_cli(exercise_name: str, start_ok: bool, end_ok: bool) -> bool:
    if not sys.stdin.isatty():
        return False
    reply = input(
        f"[{exercise_name}] Accept validated poses? (start {'OK' if start_ok else 'FAIL'}, "
        f"end {'OK' if end_ok else 'FAIL'}) [y/N]: "
    ).strip().lower()
    return reply in {"y", "yes"}


def process_exercise(
    ex_dir: Path,
    *,
    auto_approve: bool = False,
    force: bool = False,
    show: bool = False,
    save_figure: bool = True,
    tolerance_angle: float = DEFAULT_TOLERANCES["angle_deg"],
    tolerance_ratio: float = DEFAULT_TOLERANCES["ratio_pct"],
    schema_path: Optional[Path] = Path("tools/exercise_logic_builder/schema/exercise.logic.schema.json"),
    use_ui: bool = False,
    include_coco: bool = False,
) -> bool:
    exercise_name = _read_exercise_name(ex_dir)
    start_img, end_img = _load_reference_images(ex_dir)

    print(f"[{exercise_name}] Processing...")
    start_detection, start_bio, start_val = _process_pose(start_img)
    end_detection, end_bio, end_val = _process_pose(end_img)

    figure_path = None
    if save_figure or use_ui:
        figure_path = ex_dir / "verification.png"
        render_verification_view(
            start_detection,
            start_bio,
            start_val,
            end_detection,
            end_bio,
            end_val,
            output_path=str(figure_path),
            show=show,
        )
        print(f"[{exercise_name}] Verification view saved to {figure_path}")

    if not start_val.ok or not end_val.ok:
        print(f"[{exercise_name}] Validation failed. See verification for details.")
        if not force and not use_ui:
            return False

    approved = False
    if auto_approve:
        approved = True
    elif use_ui and figure_path:
        validation_text = _build_validation_text(start_val, end_val)
        approved = prompt_accept_with_ui(exercise_name, str(figure_path), validation_text)
    else:
        approved = _prompt_accept_cli(exercise_name, start_val.ok, end_val.ok)

    if not approved:
        print(f"[{exercise_name}] Rejected; skipping JSON generation.")
        return False

    payload = build_logic_payload(
        exercise_name,
        start_bio,
        end_bio,
        tolerance={"angle_deg": tolerance_angle, "ratio_pct": tolerance_ratio},
        start_landmarks=start_detection.landmarks,
        end_landmarks=end_detection.landmarks,
        include_coco=include_coco,
    )
    output_path = ex_dir / "exercise.logic.json"
    write_logic_json(payload, str(output_path), schema_path=str(schema_path) if schema_path else None)
    print(f"[{exercise_name}] Saved {output_path}")
    return True


def iter_exercises(root: Path) -> Iterable[Path]:
    for path in sorted(root.iterdir()):
        if path.is_dir():
            yield path


def _build_validation_text(start_val, end_val) -> str:
    lines = ["Validation summary:"]
    lines.append(f"Start: {'PASS' if start_val.ok else 'FAIL'}")
    if not start_val.ok:
        lines += [f"- {iss.message}" for iss in start_val.issues]
    lines.append("")
    lines.append(f"End: {'PASS' if end_val.ok else 'FAIL'}")
    if not end_val.ok:
        lines += [f"- {iss.message}" for iss in end_val.issues]
    return "\n".join(lines)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate exercise.logic.json from reference images using MediaPipe Pose."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--exercise-dir", type=Path, help="Single exercise directory to process")
    group.add_argument(
        "--root",
        type=Path,
        help="Root folder containing many exercise directories (batch mode)",
    )
    parser.add_argument("--auto-approve", action="store_true", help="Skip prompt if validation passes")
    parser.add_argument("--force", action="store_true", help="Allow generation even if validation fails")
    parser.add_argument("--show", action="store_true", help="Show verification UI (blocks)")
    parser.add_argument("--no-figure", action="store_true", help="Do not save verification.png")
    parser.add_argument("--tolerance-angle", type=float, default=DEFAULT_TOLERANCES["angle_deg"])
    parser.add_argument("--tolerance-ratio", type=float, default=DEFAULT_TOLERANCES["ratio_pct"])
    parser.add_argument("--limit", type=int, default=None, help="Limit number of exercises in batch mode")
    parser.add_argument("--ui", action="store_true", help="Show confirmation UI per exercise with Accept/Reject")
    parser.add_argument("--include-coco", action="store_true", help="Include coco-17 keypoints and raw landmarks in JSON")
    parser.add_argument("--workers", type=int, default=1, help="Parallel workers for batch mode")
    return parser.parse_args()


def _worker_task(
    path: str,
    auto_approve: bool,
    force: bool,
    no_figure: bool,
    tolerance_angle: float,
    tolerance_ratio: float,
    include_coco: bool,
):
    try:
        return process_exercise(
            Path(path),
            auto_approve=auto_approve,
            force=force,
            show=False,
            save_figure=not no_figure,
            tolerance_angle=tolerance_angle,
            tolerance_ratio=tolerance_ratio,
            use_ui=False,
            include_coco=include_coco,
        )
    except Exception as exc:  # pragma: no cover
        print(f"[{Path(path).name}] ERROR: {exc}")
        return False


def main():
    args = parse_args()

    if args.exercise_dir:
        process_exercise(
            args.exercise_dir,
            auto_approve=args.auto_approve,
            force=args.force,
            show=args.show,
            save_figure=not args.no_figure or args.ui,
            tolerance_angle=args.tolerance_angle,
            tolerance_ratio=args.tolerance_ratio,
            use_ui=args.ui,
            include_coco=args.include_coco,
        )
        return

    # Batch mode
    exercises = list(iter_exercises(args.root))
    if args.limit:
        exercises = exercises[: args.limit]

    if args.workers and args.workers > 1 and not args.ui:
        # Parallel, UI disabled for safety
        with futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
            list(
                pool.map(
                    _worker_task,
                    [str(p) for p in exercises],
                    [args.auto_approve] * len(exercises),
                    [args.force] * len(exercises),
                    [args.no_figure] * len(exercises),
                    [args.tolerance_angle] * len(exercises),
                    [args.tolerance_ratio] * len(exercises),
                    [args.include_coco] * len(exercises),
                )
            )
    else:
        processed = 0
        for ex_dir in exercises:
            try:
                success = process_exercise(
                    ex_dir,
                    auto_approve=args.auto_approve,
                    force=args.force,
                    show=args.show,
                    save_figure=not args.no_figure or args.ui,
                    tolerance_angle=args.tolerance_angle,
                    tolerance_ratio=args.tolerance_ratio,
                    use_ui=args.ui,
                    include_coco=args.include_coco,
                )
                if success:
                    processed += 1
            except Exception as exc:  # pragma: no cover - runtime guard
                print(f"[{ex_dir.name}] ERROR: {exc}")
                continue


if __name__ == "__main__":
    main()
