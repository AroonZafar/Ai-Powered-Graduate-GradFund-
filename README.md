# GradFund: Graduate Program Discovery & Funding-Fit Platform

Helps international students find master's programs they can actually afford, and tells them
*before they invest time* when a program is a poor fit (non-thesis, no master's funding,
department-assigned assistantships, "do not contact faculty" policies, unaffordable cost).

## Status: Phase 1 (backend core)

| Area | State |
|---|---|
| Auth (register/login/JWT, throttling, account deletion) | Implemented, tested |
| Student profile (funded-only / open-to-unfunded, GPA, tests, budget) | Implemented, tested |
| Graduate Program Discovery (schema, source-required importer, human review/publish, list/detail API) | Implemented, tested |
| Eligibility / fit engine | Implemented, tested |
| Faculty/professor module, CV parsing, CV + email generation, tracker, Gmail | **Not started** |
| Frontend | **Not started** (needs Next.js install; package installs were unavailable) |
| PostgreSQL | **Not tested**: dev/tests use SQLite; migrations use portable constraints but have never run on Postgres |

## Run it

```bash
cd backend
pip install -r requirements-dev.txt
export SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
python3 -m app.cli migrate
python3 -m pytest -q
python3 -c "from app import create_app; create_app().run(port=5000)"   # dev server only
```

## Data policy (no fabricated data)

The database ships **empty**. Program records enter only through:

1. `python -m app.cli import-programs FILE.json`: validates every record first; if any fails,
   nothing is imported. Every known fact needs a `sources` entry (`url` + `verified_on`).
   Facts marked `unknown` need no source. Imported records are **drafts**.
2. A human compares each draft with its official pages, then
   `python -m app.cli publish-program <id> --reviewer "Name"`. Publishing re-checks provenance
   and is also enforced by a database constraint (published rows must have a reviewer).
3. Re-importing changed content sends a program back to draft; identical content is a no-op.

See `backend/tests/conftest.py::program_payload` for the record format (synthetic test fixture).

## API (all under `/api/v1`, JSON, Bearer token)

| Method | Path | Notes |
|---|---|---|
| POST | `/auth/register`, `/auth/login` | Throttled; identical errors for unknown email / wrong password |
| DELETE | `/account` | Requires password; cascades all user data |
| GET/PUT | `/profile` | User id comes from the token only |
| GET | `/programs` | Filters: `field, program_type, verdict, q`; `sort=fit\|university\|deadline\|cost`; `page, per_page<=50` |
| GET | `/programs/<id>` | Includes fit findings, costs, per-field sources |

## Known limitations (deliberate, to be addressed in later phases)

- Rate limiter is in-memory per process; use Redis before running multiple workers.
- Access tokens only: no refresh tokens or server-side revocation (deleted accounts are rejected).
- GPA conversion to a 4.0 scale is linear and approximate; the UI must say so.
- The Flask dev server is for local use; production needs a WSGI server and TLS termination.
