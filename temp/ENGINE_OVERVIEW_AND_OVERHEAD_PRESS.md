# 3DCoach Engine Overview (Meeting Notes)

This document explains how the **JSON-driven exercise engine** works end-to-end (facts + rules + rep counter), and then walks through the real `overhead_press.json` definition field-by-field.

It is written for an engine dev teammate who wants to:
- Understand the runtime pipeline (per-frame)
- Know where the logic lives in code
- Add / tune a new exercise JSON safely

---

## 1) Big picture: what runs every frame?

At a high level, the client processes each camera frame like this:

1. **Select exercise** via manifest/catalog
	 - Catalog loader: `client/src/data/exercises.js`
	 - Definitions live in: `client/public/engine/exercises/*.json`

2. **Ensure exercise definition is loaded**
	 - The workout controller fetches and caches the JSON in `ExerciseValidationEngine`.

3. **Validation (rules engine)** (optional per exercise)
	 - Compute facts from pose landmarks (JSON facts DAG)
	 - Run JSON rules (`json-rules-engine`)
	 - Return the best failing event as a message (highest priority)

4. **Rep counter (dynamic rep engine)** (optional per exercise)
	 - Gate the frame (guardrail)
	 - Compute **rep progress** $p\in[0..1]$ from JSON expressions
	 - Smooth $p$ with EMA
	 - Run a small state machine (WAIT_BOTTOM → DOWN → UP → DOWN)
	 - On full cycle completion (top→bottom), emit a `repEvent` and (maybe) increment reps

5. **Feedback selection**
	 - Stage prompts (`messages.stage_down` / `messages.stage_up`) are the default.
	 - Validation messages can override stage prompts only while still waiting to start.

The wiring for steps (3–5) is in `client/src/modules/workout/workoutController.js`.

---

## 2) Components in code

### A) Validation (facts + rules)

**Code:** `client/src/engine/engine.js`

Key ideas:
- Exercise JSON may define:
	- `facts` (schemaVersion 1): a DAG of expressions
	- `rules`: json-rules-engine rules
	- `messages`: messageId → user-facing text
- `ExerciseValidationEngine.loadFromUrl(id, url)`:
	- Fetches JSON
	- Compiles rules into a `json-rules-engine` `Engine`
	- Compiles facts into a fast function via `compileFacts()`

**Facts compiler:** `client/src/engine/factsCompiler.js`

Facts are computed in a dependency-safe order:
- The compiler topologically sorts fact dependencies (`fact: "otherFact"`).
- Each fact expression supports:
	- literals: numbers/strings/booleans
	- `{ const }`, `{ ref: "thresholds.foo" }`, `{ fact: "someFact" }`, `{ lm: "LEFT_WRIST" }`
	- ops:
		- boolean: `and`, `or`, `not`
		- compare: `eq`, `lt`, `lte`, `gt`, `gte`
		- math: `add`, `sub`, `mul`, `div`, `abs`, `clamp`, `clamp01`
		- pose helpers: `allVisible`, `avgCoord`, `absDiffCoord`, `angleDeg`, `angleDeg3d`
		- a special helper: `pressProgress01` (legacy-compatible overhead press progress)

**Rules execution model (important detail):**
- `validate(poseLandmarks, exerciseDef)` is *synchronous* and returns the **last** computed result.
- Actual rule evaluation runs async (queued) to avoid blocking rendering.
- While the first evaluation is pending, the returned debug reason is `pending_rules_eval`.

**Rule output selection:**
- Multiple rules can fail at once.
- The engine picks the highest priority failing event.

### B) Rep counter (dynamic)

**Code:** `client/src/modules/rep/dynamicRepEngine.js`

If an exercise JSON defines `repCounter`, the workout uses the dynamic rep engine.

Key ideas:
- `repCounter.progress` is a JSON expression that evaluates to a raw scalar.
- A mapping converts raw to normalized progress $p\in[0..1]$.
	- Current mapping: `invertAngleRange`
- Progress is smoothed via EMA:
	- `repCounter.smoothing.emaAlpha` (defaults if missing)

**Frame gating (guardrail):**
- The rep engine has its own `gateFrame()` which checks required landmarks visibility.
- If gating fails, the rep engine resets state and returns a “move back visible” message.

**State machine (full cycle):**
Internal states:
- `WAIT_BOTTOM` (reported to UI as `WAITING`)
- `DOWN`
- `UP`

Transitions (simplified):
- `WAIT_BOTTOM → DOWN` when at bottom
- `DOWN → UP` when at top
- `UP → DOWN` when at bottom again
	- This is the moment a rep finishes (top→bottom)

**Start-of-rep detection:**
- When in `DOWN`, a rep “starts” once leaving bottom with upward motion:
	- `progress > leaveBottomProgress` AND `progressVel > minUpVel`

**Quality accumulation (per rep):**
While a rep is active, the engine accumulates:
- Range of motion extremes reached (top/bottom)
- Timing (total rep time, lowering time)
- Stability signals (sway, sync left/right, jerk)
- Rules violations (if validation result is bad)

At the end of the rep, it classifies the rep into:
- **accepted** (counted)
- **warned** (counted + coaching message)
- **rejected** (not counted + coaching message)

### C) Feedback precedence (coaching text)

**Code:** `client/src/modules/rep/dynamicRepEngine.js`

Per-frame coaching message is chosen like this:
- Stage prompt is default:
	- `messages.stage_down` while state is `DOWN`
	- `messages.stage_up` while state is `UP`
- Validation message can override only while *still waiting to start*:
	- override allowed only when internal `repState === "WAIT_BOTTOM"`

This is what prevents the confusing “UP” stage prompt from being replaced by form warnings mid-rep.

---

## 3) How exercise JSON maps to runtime behavior

A schema v1 exercise definition typically contains:

- `schemaVersion` / `id`
- `guardrail`
- `thresholds`
- `repCounter` (Stage-2 dynamic rep counting)
- `facts` (schema v1 facts DAG)
- `rules` (json-rules-engine)
- `messages`

The real example is: `client/public/engine/exercises/overhead_press.json`.

---

## 4) Overhead press walkthrough (the real file)

File: `client/public/engine/exercises/overhead_press.json`

### A) Identity

- `schemaVersion: 1`
	- Enables schema-v1 facts compilation in `ExerciseValidationEngine`.
- `id: "overhead_press"`
	- Used as the cache key for the loaded definition.

### B) Guardrail

```json
"guardrail": {
	"required": ["LEFT_SHOULDER", "RIGHT_SHOULDER", "LEFT_ELBOW", "RIGHT_ELBOW", "LEFT_WRIST", "RIGHT_WRIST"],
	"frameRequired": ["LEFT_SHOULDER", "RIGHT_SHOULDER", "LEFT_ELBOW", "RIGHT_ELBOW", "LEFT_WRIST", "RIGHT_WRIST"],
	"minVisibility": 0.5
}
```

Used in two places:
- **Validation engine**: short-circuits rules evaluation if required landmarks are not visible.
- **Rep engine**: hard-gates rep progress + rep state if required landmarks are not visible.

Practical effect:
- If shoulders/elbows/wrists aren’t visible enough, the app shows “move back … visible” and stops counting.

### C) Thresholds

```json
"thresholds": {
	"maxShoulderLevelDiff": 0.08,
	"maxHipLevelDiff": 0.08,
	"maxArmSyncDiffDeg": 22,
	"maxWristElbowXDiff": 0.08,
	"shoulderBand": 0.2,
	"minOverheadLift": 0.1,
	"repElbowAngleBottomDeg": 95,
	"repElbowAngleTopDeg": 170,
	"repProgressTopRaw": 0,
	"repProgressBottomRaw": 1,
	"minStartProgress": 0.4,
	"minFinishProgress": 0.78
}
```

How they’re used:
- **Facts** read these values via `{ "ref": "thresholds.xxx" }`.
- **Rep counter** reads elbow ROM bounds and computes normalized progress.
- The rule thresholds for press progress use `0.4` and `0.78` (legacy ladder), but note:
	- Those thresholds are currently hard-coded in the rules themselves (values `0.4` and `0.78`).
	- The `thresholds.minStartProgress` / `minFinishProgress` are present for readability/future tuning.

### D) Rep counter (Stage-2, JSON driven)

```json
"repCounter": {
	"mode": "full_cycle",
	"progress": { "op": "sub", "a": {"const": 1}, "b": { "op": "avg", "args": [ ... ] },
		"map": { "type": "invertAngleRange", "topAngleMaxDegRef": "thresholds.repProgressTopRaw", "bottomAngleMinDegRef": "thresholds.repProgressBottomRaw" }
	},
	"progressSides": { "left": { ... }, "right": { ... } },
	"smoothing": { "emaAlpha": 0.30 },
	"start": { "leaveBottomProgress": 0.22, "minUpVel": 0.00025 },
	"extremes": { "topProgressMin": 0.8, "bottomProgressMax": 0.18 },
	"quality": { "warnBadFraction": 0.15, "rejectBadFraction": 0.30, "minRepMs": 1500, "minDownMs": 600, "maxRepMs": 9000, "syncDelta": 0.20, "maxSwayRatio": 0.14, "maxProgressVelAbs": 0.006 }
}
```

What this means:

1) **Progress is a hybrid signal**
- It averages:
	- Wrist height progress relative to shoulders (`avgShoulderY - avgWristY`, normalized by `shoulderBand`)
	- Elbow extension progress (angle from bottom→top range)

2) **Normalization to [0..1]**
- The definition stores the averaged value as `raw = 1 - avg(...)` so it can be fed into the existing `invertAngleRange` mapping with a `topRaw=0`, `bottomRaw=1`.

3) **Smoothing**
- `emaAlpha: 0.30` reduces jitter.

4) **State machine + rep counting**
- A rep is counted only after a full cycle (top reached, then return to bottom).

5) **Quality**
- A rep can be rejected for:
	- incomplete ROM
	- too fast / uncontrolled lowering
	- too many bad frames (bad fraction)
- A rep can be accepted but warned if there’s a notable amount of bad frames.

### E) Facts (schema v1)

Facts are a computed feature layer. Example:

- `bothArmsVisible` uses `allVisible` and `guardrail.minVisibility`.
- `torsoOk` is built from shoulder/hip alignment and only requires hips if they are visible.
- `pressProgressT` uses the special `pressProgress01` helper.

Important implementation detail:
- Facts are computed in dependency order (toposorted). If you create a cycle (A depends on B and B depends on A), compilation throws.

### F) Messages

The JSON contains a `messages` dictionary.

It serves two consumers:
- **Rules engine**: rules refer to message keys via `event.params.messageId`.
- **Rep engine**: uses `messages.stage_down` and `messages.stage_up` as the stage prompts.

### G) Rules (json-rules-engine)

Overhead press rules are prioritized (1000 highest):
- 1000: both arms visible
- 900: torso upright/level
- 800: arms in sync
- 700: wrists over elbows
- 600: press progress start (t < 0.4)
- 500: press progress finish (t < 0.78)

The “best” failing rule (highest priority) becomes the current validation message.

---

## 5) Where this connects to UI + rep counting

The workout loop uses the dynamic path when `dynamicDef.repCounter` exists:

- Load definition info from the catalog: `client/src/data/exercises.js`
- Ensure loaded into the validation cache: `ensureExerciseDefinitionLoaded()`
- Per frame:
	- `validationEngine.validate(poseLm, dynamicDef)` (rules)
	- `repEngine.update({ poseLm, exerciseDef: dynamicDef, validationResult })` (rep + stage)
	- `ui.setFeedback(...)`
	- If `repEvent.accepted`, increment reps

---

## 6) If you need to explain this in one sentence

We compute facts from pose landmarks, run JSON rules to validate form, compute a smoothed progress value to drive a tiny state machine that counts full-cycle reps, and we prioritize stage prompts during a rep so coaching stays consistent.