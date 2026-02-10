# AI Exercise Authoring Guide (Data‑Driven Only)

Audience: an AI agent that **adds new exercises** by editing **data only** (JSON + manifest). The agent must **not change engine code**.

This guide explains:
- How to add a new exercise so it appears in the UI
- How the runtime consumes exercise JSON
- The exact JSON structure and the supported expression operations
- A heavily annotated example

---

## 0) Hard constraints (read first)

### You MAY change (data-only)
- Add a new exercise JSON file in this folder: `client/public/engine/exercises/`
- Add an entry in `client/public/engine/exercises/manifest.json`
- Tune numbers/strings inside the new JSON (thresholds/messages)

### You MUST NOT change
- Anything in `client/src/**` (engine/runtime code)
- Any expression `op` semantics or add new `op` names (not possible without code)
- Create or modify documentation/guide files as part of “adding an exercise”
  - This guide and other docs are written/maintained by humans.

### Design principle
If you cannot express an exercise using the existing `op`s and existing repCounter logic, **do not attempt to hack it**. Pick a simpler progress signal or defer the exercise.

---

## 1) How the app discovers exercises

The UI loads an exercise catalog from:
- `client/public/engine/exercises/manifest.json`

Each entry in `manifest.json` contains (typical):
- `id`: the app-level exercise id (used by routing/selection)
- `slug`: URL slug `/<lang>/<slug>`
- `name`, `nameAr`, `hint`, `hintAr`: display strings
- `definitionKey`: the JSON filename (without `.json`) to load from this folder

Important mapping:
- `definitionKey: "my_exercise"` → loads `client/public/engine/exercises/my_exercise.json`
- Inside that JSON, set **`"id": "my_exercise"`**.

Why this matters:
- The validation engine caches by `exerciseDef.id`.
- The manifest selects which file to fetch.

---

## 2) Runtime pipeline (what consumes the JSON)

Per frame (simplified):
1) Load `definitionKey.json` once (cached)
2) If `rules[]` exists:
   - Compute `facts` (schema v1)
   - Run `rules` (json-rules-engine)
   - Produce a validation result `{ ok, message, violations, debug }`
3) If `repCounter` exists:
   - Gate the frame using `guardrail`
   - Compute progress $p\in[0..1]$ using `repCounter.progress`
   - Smooth progress with EMA
   - Run a state machine to detect a full-cycle rep
   - Emit `repEvent` (accepted/warned/rejected)
4) Feedback:
   - During movement: default feedback is rep stage prompts (`messages.stage_down` / `messages.stage_up`)
   - Validation messages can override only while the engine is still “waiting to start”

---

## 3) Exercise JSON: required top-level structure

A real exercise file is a normal JSON object (comments are not a JSON feature).

Minimum working exercise (dynamic rep counter + rules) typically includes:
- `schemaVersion: 1`
- `id: "<definitionKey>"`
- `guardrail`
- `thresholds`
- `repCounter`
- `facts`
- `messages`
- `rules`

Notes:
- Extra keys like `comment__foo` are allowed (engine ignores unknown keys). This repo already uses `comment__...` in real files.

---

## 4) `guardrail` (frame gating)

Purpose: prevent noisy/out-of-frame landmarks from driving rules or rep counting.

Shape:
```json
"guardrail": {
  "required": ["LEFT_SHOULDER", "LEFT_ELBOW", "LEFT_WRIST"],
  "frameRequired": ["LEFT_SHOULDER", "LEFT_ELBOW", "LEFT_WRIST"],
  "minVisibility": 0.55
}
```

Rules of thumb:
- Use `frameRequired` to list the landmarks needed to evaluate the exercise safely.
- Use a slightly lower `minVisibility` (e.g. 0.5–0.6) for real-world tolerance.

---

## 5) `thresholds` (put all tunables here)

Best practice: keep all numeric tuning constants in `thresholds` and reference them via `{ "ref": "thresholds.key" }`.

This makes the definition:
- easier to tune
- easier for an AI agent to modify safely
- avoids magic numbers spread through expressions

---

## 6) Rep counter (data-driven rep counting)

The rep counter is defined in:
- `repCounter` (interpreted by `client/src/modules/rep/dynamicRepEngine.js`)

### 6.1 Required fields

```json
"repCounter": {
  "version": 1,
  "mode": "full_cycle",
  "progress": { ... },
  "smoothing": { "emaAlpha": 0.30 },
  "start": { "leaveBottomProgress": 0.22, "minUpVel": 0.00025 },
  "extremes": { "topProgressMin": 0.85, "bottomProgressMax": 0.15 },
  "quality": { ... }
}
```

### 6.2 Progress (most important)

Progress is a scalar $p\in[0..1]$:
- $p\approx 0$ at bottom
- $p\approx 1$ at top

The engine computes:
- `raw = eval(repCounter.progress)`
- then if `progress.map` exists it maps raw → progress
- then applies EMA smoothing

**Current supported mapping**
- `invertAngleRange`
  - Reads two refs: `topAngleMaxDegRef` and `bottomAngleMinDegRef`
  - Then uses: $p = clamp01((bottom - raw) / (bottom - top))$

Despite the name, raw does not have to be an “angle”. It’s just a scalar.

### 6.3 Start / state machine / end

State machine concepts:
- WAITING (internally `WAIT_BOTTOM`): don’t start until we have a stable bottom
- DOWN: user is in the “go up” phase
- UP: user reached top; now lowering

A rep is counted only on a **full cycle**: bottom → top → bottom.

### 6.4 Quality (accept/warn/reject)

Quality is computed from:
- ROM extremes reached
- tempo (too fast, drop too fast)
- sway (torso drifting)
- left/right sync (if `progressSides` is provided)
- jerk (instant velocity too high)
- rules violations (if validation says bad)

Outcome:
- accepted: rep counts
- warned: rep counts but a coaching message may be emitted
- rejected: rep does not count

---

## 7) Facts (schema v1)

Facts are a **named feature layer** computed from pose landmarks.

Facts are defined in:
- `facts` (interpreted by `client/src/engine/factsCompiler.js`)

Important:
- Facts can reference other facts, so the facts graph must be a **DAG** (no cycles).
- Facts can reference thresholds/guardrail via `{ "ref": "thresholds.x" }`.

### 7.1 Supported fact expression primitives

A fact expression can be:
- literal: number / boolean / string
- `{ "const": ... }`
- `{ "ref": "thresholds.someKey" }` (reads from the exercise JSON)
- `{ "fact": "otherFact" }` (dependency)
- `{ "lm": "LEFT_WRIST" }` (returns a landmark object)

### 7.2 Supported fact `op`s (authoritative)

From `client/src/engine/factsCompiler.js`:
- Boolean: `and`, `or`, `not`
- Compare: `eq`, `lt`, `lte`, `gt`, `gte`
- Math: `add`, `sub`, `mul`, `div`, `abs`, `clamp`, `clamp01`
- Pose helpers:
  - `allVisible` (landmarks + minVisibility)
  - `avgCoord` (axis + landmarks)
  - `absDiffCoord` (axis + a/b landmarks)
  - `angleDeg` (2D)
  - `angleDeg3d` (3D)
  - `pressProgress01` (legacy overhead-press helper)

If you need an operation that is not in this list, you cannot implement it without engine changes (which are forbidden).

---

## 8) Rules (json-rules-engine)

Rules are used to choose the “most important” coaching message.

Rules live in:
- `rules[]` (compiled by `ExerciseValidationEngine`)

Each rule typically includes:
- `priority`: higher wins
- `conditions`: references facts by name
- `event.params.messageId`: must exist in `messages`

Example pattern:
```json
{
  "name": "Torso upright",
  "priority": 900,
  "conditions": {
    "all": [
      { "fact": "bothArmsVisible", "operator": "equal", "value": true },
      { "fact": "torsoOk", "operator": "equal", "value": false }
    ]
  },
  "event": {
    "type": "stand_tall_level",
    "params": { "ok": false, "messageId": "stand_tall_level", "priority": 900 }
  }
}
```

Guidelines:
- Put hard blockers at higher priority (visibility/pose gating).
- Put subtle coaching at lower priority.

---

## 9) `messages` (UI + TTS strings)

`messages` is a dictionary: `messageId -> string`.

Required for rep-stage prompts:
- `messages.stage_down`
- `messages.stage_up`

Validation rules also typically reference:
- `messages.<messageId>` used by `event.params.messageId`

Important behavior in this repo:
- TTS uses `lang.L(message)`.
  - If `message` is an i18n key, it should translate.
  - If it is plain English text, it usually passes through unchanged.

Therefore, it is safe to use either:
- i18n keys (preferred if you already have them), or
- plain English strings (acceptable for PoC)

---

## 10) Supported repCounter expression `op`s (authoritative)

Rep counter expressions are evaluated by `client/src/modules/rep/dynamicRepEngine.js`.

Supported repCounter expression forms:
- `{ "const": 1 }`
- `{ "ref": "thresholds.someKey" }`
- `{ "op": "...", ... }`

Supported repCounter `op`s:
- `angleDeg2d` (a/b/c landmarks)
- `coord` (landmark + axis)
- `abs`
- `add`, `sub`, `mul`, `div`
- `clamp`
- `absDiffCoord`
- `avgCoord`
- `avg`

If you choose an `op` outside this list, progress will become `NaN` and rep counting will fail.

---

## 11) Step-by-step: add a new exercise (data-only)

### Step 1 — Choose ids (do not skip)

Pick two ids:
- `manifestExerciseId`: `manifest.exercises[].id`
- `definitionKey`: `manifest.exercises[].definitionKey` (also JSON filename base)

Rule:
- `definitionKey` MUST equal the JSON `id` and the filename.

Example:
- `id: "squat"`
- `definitionKey: "squat_poc_v1"`
- file: `squat_poc_v1.json`
- inside file: `"id": "squat_poc_v1"`

### Step 2 — Copy an existing exercise JSON as a starting point

Good starting points:
- `overhead_press.json` (hybrid progress + posture rules)
- `bicep_curl_both.json` (simple both-arms progress)

### Step 3 — Update `id` and keep schemaVersion

- Keep: `"schemaVersion": 1`
- Set: `"id": "<definitionKey>"`

### Step 4 — Define guardrail

Choose required landmarks that your progress/facts need.

### Step 5 — Define progress + mapping

Start simple:
- Use one clear measurement (like an elbow angle) and `invertAngleRange`.
- Add hybrid signals only after the simple version works.

### Step 6 — Add facts + rules

Minimum rules set:
1) visibility gating
2) one or two key form checks

### Step 7 — Add required messages

At minimum:
- `stage_down`, `stage_up`
- any `messageId` referenced by rules

### Step 8 — Add to manifest

Add a new object to `manifest.json` exercises list:
- Make sure `definitionKey` matches your filename.
- Choose a unique slug.

### Step 9 — Test

When running the app:
- Ensure the exercise loads (no “Loading exercise definition...” loop)
- Progress bar moves smoothly
- Reps count only on full cycle
- Breaking form triggers the expected rule message

---

## 12) Annotated example (field-by-field)

Use these as authoritative references (do not copy them verbatim unless you also update ids/keys carefully):
- Real runtime example: `overhead_press.json`
- Documentation-only fully annotated structure: `overhead_press_structure_guide_example_v1.json`

### 12.1 Quick field explanation checklist

Top level:
- `schemaVersion`: enables schema-v1 facts compilation
- `id`: must match `definitionKey` and filename
- `guardrail`: frame gating for visibility
- `thresholds`: all tunable constants
- `repCounter`: rep logic + quality
- `facts`: computed features
- `messages`: message dictionary used by rules and rep stages
- `rules`: prioritised validations

### 12.2 “Commented JSON” technique

JSON does not support `//` comments. In this repo, we use either:
- `comment__...` keys inside real JSON (safe; engine ignores unknown keys)
- `__comment_...` keys in documentation-only files (do not load at runtime)

Recommended:
- For real exercise JSON: use `comment__...` keys sparingly.
- Do not create new “guide/example” files when adding a new exercise. Only add the real exercise JSON + manifest entry.

---

## 13) Common failure modes (and fixes)

- **Exercise never appears in UI**
  - Not added to `manifest.json`, or manifest failed to load.

- **UI shows “Loading exercise definition...” forever**
  - `definitionKey` points to a missing JSON file, or JSON is invalid.

- **Rules never trigger / always says unsupported**
  - `rules[]` missing or empty.
  - Facts compilation failed due to cycles/missing dependencies.

- **Progress bar stuck at 0 / NaN**
  - repCounter uses unsupported `op`.
  - required landmarks for progress are not visible; guardrail is gating.
  - mapping refs point to missing threshold keys.

- **Reps count randomly**
  - guardrail too permissive OR progress too noisy.
  - reduce noise: add EMA smoothing, adjust start thresholds, increase extremes.

---

## 14) AI agent checklist (for every new exercise)

Before finishing, confirm:
- [ ] Added `manifest.json` entry with unique `id` and `slug`
- [ ] `definitionKey` matches filename and JSON `id`
- [ ] `schemaVersion` is `1`
- [ ] `guardrail.required` covers every landmark used in progress/facts
- [ ] `messages.stage_down` and `messages.stage_up` exist
- [ ] Every rule `messageId` exists in `messages`
- [ ] repCounter uses only supported repCounter `op`s
- [ ] facts use only supported facts `op`s and have no cycles

