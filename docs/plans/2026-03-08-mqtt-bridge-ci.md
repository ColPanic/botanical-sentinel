# mqtt-bridge CI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a GitHub Actions workflow that lints and tests the mqtt_bridge Python package
on every PR and push to main that touches `server/**`.

**Architecture:** Single workflow file mirroring the existing CI convention — path-filtered
triggers, SHA-pinned actions, uv for venv + install, ruff for lint/format, pytest for tests.
No external services needed (unit tests only).

**Tech Stack:** GitHub Actions, Python 3.13, uv, ruff, pytest

---

### Task 1: Create the mqtt-bridge CI workflow

**Files:**
- Create: `.github/workflows/mqtt-bridge.yml`

**Step 1: Create the workflow file**

```yaml
name: mqtt-bridge

on:
  pull_request:
    paths:
      - 'server/**'
      - '.github/workflows/mqtt-bridge.yml'
  push:
    branches: [main]
    paths:
      - 'server/**'
      - '.github/workflows/mqtt-bridge.yml'

jobs:
  build:
    runs-on: ubuntu-24.04
    permissions:
      contents: read
    defaults:
      run:
        working-directory: server/mqtt_bridge

    steps:
      - uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5  # v4
        with:
          persist-credentials: false

      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065  # v5
        with:
          python-version: '3.13'

      - name: Install uv
        run: pip install uv==0.7.2

      - name: Install dependencies
        run: uv venv --python 3.13 && uv pip install -e ".[dev]"

      - name: Lint
        run: uv run ruff check .

      - name: Format check
        run: uv run ruff format --check .

      - name: Test
        run: uv run pytest -q
```

**Step 2: Pin uv version**

Check the current stable uv version:

```bash
pip index versions uv 2>/dev/null | head -1
```

Or use: https://github.com/astral-sh/uv/releases/latest

Use whatever the current stable release is. The plan uses `0.7.2` as a placeholder —
replace with the actual latest stable version.

**Step 3: Validate YAML syntax**

```bash
actionlint .github/workflows/mqtt-bridge.yml
```

Expected: no output (clean).

**Step 4: Commit**

```bash
git add .github/workflows/mqtt-bridge.yml
git commit -m "ci: add mqtt-bridge lint and test workflow"
```
