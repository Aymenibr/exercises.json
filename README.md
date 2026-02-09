# Exercise Logic Builder

Generate `exercise.logic.json` files from reference images using MediaPipe Pose. Designed for elderly-safe, enterprise healthcare use-cases (≥95% rep detection correctness target).

## Repository Layout
- `exercises/<ExerciseName>/images/{0,1}.jpg|png` – start/end reference images
- `exercises/<ExerciseName>/exercise.json` – metadata (name, muscles, etc.)
- `tools/` – pose extraction, metrics, validation, visualization, and CLI
- `tools/exercise_logic_builder/schema/exercise.logic.schema.json` – output schema

## Quickstart
```bash
pip install -r requirements.txt
python tools/build_exercise_logic.py --exercise-dir exercises/Pushups --auto-approve
```

Batch mode over all exercises:
```bash
python tools/build_exercise_logic.py --root exercises --auto-approve --limit 20
```

Flags:
- `--auto-approve`  Skip prompt when validation passes
- `--force`         Write JSON even if validation fails (not recommended)
- `--show`          Display the 4-panel verification UI
- `--no-figure`     Skip saving `verification.png`
- `--tolerance-angle` / `--tolerance-ratio` Override default tolerances (15°, 0.15)

## Pipeline
1. **Pose extraction**: MediaPipe Pose on `0` and `1` reference images.
2. **Biomechanics**: Joint angles (elbow/knee/hip/shoulder), limb ratios (forearm/upper-arm, shin/thigh), torso orientation (tilt, hip/shoulder alignment), visibility scores.
3. **Validation**: Visibility ≥0.6, physiological angle ranges, left/right symmetry (≤15° diff), realistic torso orientation.
4. **Verification UI**: Four-panel plot with start/end overlays, metrics, and validation status saved as `verification.png`.
5. **User confirmation**: JSON saved only after validation + approval (or `--auto-approve`).

## Output
`exercise.logic.json` written into each exercise directory, shaped by `exercise.logic.schema.json`:
```json
{
  "exercise": "Pushups",
  "states": { "start": { "angles": {}, "ratios": {}, "orientation": {} },
              "end":   { "angles": {}, "ratios": {}, "orientation": {} } },
  "rep_logic": "start -> end",
  "tolerance": { "angle_deg": 15, "ratio_pct": 0.15 }
}
```

## Notes
- Images can be `.png`, `.jpg`, or `.jpeg` and may live directly in the exercise folder or under `images/`.
- The validator is tuned for elderly safety; tighten/loosen limits via CLI tolerances if needed.
- If `jsonschema` is installed, outputs are schema-validated before writing.
