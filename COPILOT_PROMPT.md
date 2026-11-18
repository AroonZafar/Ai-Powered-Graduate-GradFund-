# Prompt for VS Code Copilot (Agent mode)

How to use: open the `gradfund` folder in VS Code, switch Copilot Chat to **Agent** mode, and paste the
"MASTER CONTEXT" once. Then paste **one phase at a time**, and only move on when its tests pass.
Do not paste everything as a single request.

---

## MASTER CONTEXT (paste first)

You are a senior software architect and full-stack engineer building a commercial SaaS product.
Read `README.md` and inspect the whole repository before changing anything. Extend the existing
architecture; do not rewrite working code. Never overwrite or delete working functionality without a
technical reason you explain.

### Product
"GradFund": an AI-assisted platform that helps international students find **funded master's programs**
(RA / TA / GA / tuition waivers / scholarships), shortlist suitable professors, and prepare honest,
personalized application emails and CVs. Core promise: tell students *before they invest time* when a
program or professor is a poor fit.

### Decisions already made (do not change without asking)
1. Users: students from any undergraduate background applying to master's programs in AI, cybersecurity,
   CS and data science. Each student chooses **funded_only** or **open_to_unfunded**. PhD is a separate future pathway.
2. **Program discovery comes before professor discovery.** Flow: Program -> eligibility/funding check -> Professor -> documents.
3. **No real-time web research per user.** All program/faculty data comes from a curated, scheduled,
   human-reviewed database. Start with 10-15 carefully verified universities. Accuracy beats size.
4. **Every known fact needs a source URL and a verified date.** Unknown stays "unknown". Funding is shown
   as evidence levels (confirmed / unverified / unknown), never "guaranteed".
5. Records enter as drafts and go live only after a named human reviewer approves them.
6. The student always reviews and approves every email. No bulk "send all". Daily send cap. Gmail starts
   with **drafts**; direct send comes later (needs Google OAuth verification).
7. Generated CVs/emails may only reorganize facts the student provided. Never invent publications, skills,
   grades, professors, papers, labs or funding.

### Existing code (Phase 1, done, 90 passing tests)
`backend/` (Python, Flask, pydantic, PyJWT, SQLite dev DB, SQL migrations in `backend/migrations/`):
auth (scrypt + JWT + throttling + account deletion), student profile, program schema + source-required
importer + review/publish CLI, program list/detail API, and the pure eligibility engine
(`app/eligibility/engine.py`) with blockers/warnings/info and cost/deadline/staleness checks.
Not done: faculty, CV parsing, AI generation, tracker, Gmail, frontend, Postgres.

### Engineering rules
- Clean, modular, production-quality code; separate frontend, backend, DB, AI services and integrations.
- Validate every request; consistent error shape; pagination/filtering/sorting; rate limiting.
- Versioned migrations; foreign keys, indexes, constraints; user-level data isolation (user id comes only from the token).
- Secrets only from environment variables. Never log documents, tokens, passwords or emails.
- Treat uploaded files and web pages as untrusted input (prompt-injection protection).
- Use structured LLM output, retrieval-grounded generation, and **validate generated text against stored facts**.
- Track token usage, cost and failed generations. Keep prompts modular and version-controlled.
- No mock data, no hardcoded sample responses, no TODO placeholders for important features.
- Never claim an integration works unless you actually ran it. Never silently swallow errors.
- Work incrementally. After each phase: run the full test suite, fix failures, confirm existing tests still pass.
- End every phase with a report: features done, files changed, DB changes, tests run + results,
  open issues, credentials/actions I must provide, next phase.

Acknowledge by summarizing the repo state in 10 lines, then wait for Phase 0.

---

## PHASE 0: Move to production-grade foundations
- Replace SQLite with **PostgreSQL** (SQLAlchemy 2.x + Alembic, or keep raw SQL with a proper driver; choose and justify).
  Port both existing migrations; use `timestamptz`, `uuid`, and real enums/CHECKs. Run the whole test suite against Postgres (docker compose).
- Add Dockerfile + docker-compose (api, postgres, redis). Add gunicorn. Move the rate limiter to Redis.
- Add refresh tokens with rotation and server-side revocation; httpOnly cookie option.
- Add CI (GitHub Actions) running tests and a linter (ruff).
Acceptance: all existing tests pass on Postgres; `docker compose up` serves the API.

## PHASE 1: Frontend (Next.js + TypeScript)
Pages: sign up / log in, profile (funding mode, GPA with scale, English test, GRE, budget), program discovery
list with filters/sort/pagination and fit badges (good / caveats / poor), program detail page showing every
finding, estimated cost, deadlines and **a source link + "last verified" date next to every fact**, and
a "report wrong info" button.
Requirements: polished and consistent design system (tokens, typography, spacing), loading/empty/error/success
states, accessibility (keyboard, labels, contrast), responsive. Empty catalogue must show a clear empty state, not fake data.
Add Playwright tests for sign-up -> profile -> program list.
Acceptance: a new user can register, complete a profile, see programs and understand why each is or is not a fit.

## PHASE 2: Faculty module
- Tables: `faculty` (linked to program/department), `faculty_research_areas`, `faculty_publications`
  (from OpenAlex / Semantic Scholar / DBLP APIs with stored source URL + fetched date), `faculty_funding_signals`
  (e.g. NSF award data), each with source URL + verified date and the same draft -> reviewed -> published workflow.
- Per-professor facts: supervises master's students (yes/no/unknown with source), accepting students, lab URL,
  publicly listed contact email **with source**.
- Extend the eligibility engine with professor-level checks (PhD-only supervisor, department-assigned
  assistantships, "do not contact faculty" policy, no recent publications).
- Background ingestion jobs (queue + scheduler) that refresh publications, with failure handling and rate limits for external APIs.
- API + UI: professors inside a program, with evidence labels and recent papers.
Acceptance: tests for each rule, API-failure tests, and no professor shown without a source.

## PHASE 3: CV upload and parsing
- Upload PDF/DOCX (size/type limits, content sniffing, no executables, virus-scan hook). Store **encrypted at rest**
  (envelope encryption, key from env/KMS). Never log contents.
- Extract text, then structured fields (education, projects, skills, experience, publications) with an LLM using a
  strict JSON schema; the student must review and correct the parsed result before it is saved.
- Prompt-injection defense: treat CV text as data, strip/flag instruction-like content, never give the model tool access.
- Data deletion endpoint removes files and parsed data.
Acceptance: adversarial CV samples (hidden "ignore previous instructions", fake credentials) are handled; tests included.

## PHASE 4: Personalized CV + email generation (the AI core)
- Inputs: student's reviewed profile + **retrieved** professor facts (papers, research areas) only.
- Output: structured JSON (email subject/body, tailored CV sections, list of facts used with their IDs).
- **Validation step:** every named paper, lab, professor and student achievement in the output must match stored data;
  otherwise the generation fails and is retried or flagged. A single fabricated claim = failure.
- Diff view: show the student what changed versus their original CV.
- Evaluation suite: fixed test profiles + professors; assert zero fabrication, correct names, length limits.
- Track tokens, cost per generation, failures. Prompts stored as versioned files. Provider behind an interface; API key from env.
- Warn when the email would be generic (no specific paper referenced).
Acceptance: evaluation suite passes; generation is blocked when required facts are missing.

## PHASE 5: Review, send, tracker
- Student reviews/edits each email and CV before use; export to PDF/DOCX or copy.
- Gmail OAuth with minimal scope to **create drafts**; tokens encrypted; revoke/disconnect option.
  (Direct send and reply detection need Google OAuth verification: implement behind a feature flag, document the process.)
- Tracker: outreach status per professor, duplicate-send prevention, follow-up reminders (7-10 days), daily cap, deadlines calendar.
Acceptance: cannot email the same professor twice without an explicit override; cap enforced; tokens never exposed to the client.

## PHASE 6: Hardening and launch
Security review (OWASP top 10, dependency audit, authz tests for every endpoint), privacy policy/terms pages,
"no guarantee of funding or admission" notice, monitoring and error tracking, backups, load test, admin
review UI for the data-publishing workflow, and a data-freshness job that flags records older than N days.

---

## Things I must do myself (ask me when you reach them)
- Provide the LLM API key, Google OAuth client credentials, and database/secret values via environment variables.
- Choose the first 10-15 universities and collect their program data **from official pages** into the import JSON
  format (see `backend/tests/conftest.py::program_payload`). Never generate this data.
