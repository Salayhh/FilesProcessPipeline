---
name: files-process-pipeline
description: "Use when an agent needs to run, inspect, retry, or archive the FilesProcessPipeline document-processing CLI in this repository."
---

# FilesProcessPipeline Agent Skill

## Overview

Use the existing Python CLI to process PDF, Word, PowerPoint, image, and HTML inputs through MinerU, optional sanitize, Kimi, and render stages. Do not reimplement pipeline logic inside the agent; call the repository CLI and inspect its outputs.

## Safety Rules

- Do not print `.env`, API tokens, or full environment variables.
- Do not move, delete, or clear `input/`.
- Do not run the full external API pipeline unless the user explicitly asks to process files and input/config checks pass.
- Ask for explicit user confirmation before `archive`; it moves `runs/{run_id}/` to `data/{run_id}/`.
- Prefer `failed` and `retry-failed` for recovery instead of starting a new run when a manifest already exists.

## Orientation

Work from the repository root. Confirm the pipeline exists by checking for:

```text
pipeline.py
files_pipeline/cli.py
files_pipeline/config.py
```

Before running external stages, confirm `.env` exists and check only whether required keys are present, not their values:

```bash
test -f .env && echo ".env present" || echo ".env missing"
python3 -c 'from files_pipeline.config import Settings; s=Settings.from_env(); print("missing_required_keys=", s.missing_required_keys()); print("input_dir=", s.input_dir); print("output_format=", s.output_format); print("sanitize_enabled=", s.sanitize_enabled)'
```

Check input files without modifying them:

```bash
find input -type f
```

## CLI Commands

Run the complete pipeline only when requested:

```bash
python3 pipeline.py
python3 -m files_pipeline.cli run --input input
python3 -m files_pipeline.cli run --input input --run-id demo
```

Run stages separately for debugging or controlled recovery:

```bash
python3 -m files_pipeline.cli parse --input input --run-id demo
python3 -m files_pipeline.cli sanitize --run-id demo
python3 -m files_pipeline.cli organize --run-id demo
python3 -m files_pipeline.cli render --run-id demo
```

Inspect and recover failures:

```bash
python3 -m files_pipeline.cli failed --run-id demo
python3 -m files_pipeline.cli retry-failed --run-id demo
```

Archive only after explicit confirmation:

```bash
python3 -m files_pipeline.cli archive --run-id demo
```

## Outputs and Manifest

Use `runs/{run_id}/manifest.json` as the source of truth for stage status, document status, output paths, errors, and token usage. Final rendered files are under `runs/{run_id}/final/`; copied image assets are under `runs/{run_id}/assets/` unless `ASSETS_DIR` is configured.

When reporting results to the user, include:

- `run_id`
- manifest status
- final output paths
- failed document count and latest error, if any
- whether external APIs were called

## Validation

For code or skill changes, prefer tests that do not call MinerU or Kimi:

```bash
python3 -m unittest discover -s tests
```

Validate this skill structure after edits:

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" .codex/skills/files-process-pipeline
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" .agents/skills/files-process-pipeline
```
