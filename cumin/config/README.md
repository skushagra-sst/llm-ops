# Versioned reference snapshots

`v1/plans.snapshot.json` copies the default plan values from
`src/models/plan.py` at source commit `8f7cb81604ee724b60145aa28e5083cff07e7916`.
The summarize prompt is in `../prompts/v1/summarize.snapshot.json`.

These are documentation snapshots, NOT runtime configuration. They are not
loaded by the application. DB-backed PlanStore edits can differ from defaults.
Changing runtime loading or behavior needs owner approval. Increment the
snapshot version when recording changed defaults or prompt wording.
