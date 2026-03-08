# Web CI Design

## Goal

Add a GitHub Actions workflow that type-checks and builds the SvelteKit frontend on every
PR and push to main that touches `web/**`.

## Workflow

**File:** `.github/workflows/web.yml`

**Triggers:**
- `pull_request` on paths `web/**`, `.github/workflows/web.yml`
- `push` to `main` on the same paths

**Runner:** `ubuntu-24.04`

**Steps:**
1. `actions/checkout` (SHA-pinned)
2. `actions/setup-node` — Node 22 LTS, npm cache enabled
3. `npm ci` — clean install from `web/package-lock.json`
4. `npm run check` — `svelte-kit sync && svelte-check --tsconfig ./tsconfig.json`
5. `npm run build` — `vite build`

**Caching:** `actions/setup-node` built-in npm cache keyed on `web/package-lock.json`

**Constraints:**
- All actions pinned to full SHA with version comment (matches repo convention)
- `permissions: contents: read` (least privilege)
- Working directory set to `web/` for npm steps
- No linting step — oxlint not yet installed in the project
