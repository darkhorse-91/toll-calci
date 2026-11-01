# Implementation prompt

Give this prompt to a coding LLM together with this doc's first tab (the build context), downloaded as Markdown. Copy everything inside the box below.

```markdown
# Task: build the India Toll Price MVP

You are a senior full-stack engineer. Build the India Toll Price MVP exactly as described in the build context document attached to this prompt ("India Toll Price MVP - LLM Build Context"). That document is the single source of truth for the product, domain rules, database schema, API contract, UI and build order. This prompt tells you how to work, which tools to use, and what to deliver.

Read the whole build context document before writing any code. If this prompt and the document ever disagree, the document wins on product and domain rules; this prompt wins on tooling and process.

## 1. What you are building, in one paragraph

A web app where a user enters a start, a destination, a vehicle class, one-way or return, and whether they hold a FASTag annual pass. It returns up to three routes (usual, lowest toll, toll-free). For each route it shows the exact toll at every toll point in travel order, the total with and without the annual pass, which points the pass covers and why it does not cover the others, how many pass trips the journey uses, and three or four facts about the road from last year's public data. Everything runs on free and open-source software and free public data.

## 2. Non-negotiable rules

1. Toll amounts are exact. Every rupee comes from an APPROVED row in the `rate` table valid on the travel date. Never estimate, interpolate, hard-code or ask a model for a toll.
2. Rules are data. Pass price, trip limit, eligible classes, which operators accept the pass, and trips per charging point live in tables. No such value appears as a literal in application code.
3. Money is `numeric` in PostgreSQL and `decimal.Decimal` in Python. Never use floats for money. Round to whole rupees only when building the API response (round half up).
4. Use the database schema from the build context verbatim as the first migration. Change it only through new migrations, and record why in DECISIONS.md.
5. Store nothing about users: no accounts, no trip history, no vehicle numbers, no precise coordinates in logs (2 decimals at most).
6. Free and open-source only. Do not add Google Maps, Mappls, TollGuru or any paid API.
7. The pass engine is pure: no database, network, clock or randomness inside it. Everything it needs is passed in.
8. Never weaken, skip or delete a test to make the build pass. Fix the code, or record the problem in DECISIONS.md and stop to ask.

## 3. Locked tech stack

Use exactly this. Pick specific library versions yourself, pin them, and prefer releases at least a few weeks old.

| Layer | Technology |
| --- | --- |
| Frontend | TypeScript, React, Vite; MapLibre GL JS via react-map-gl; `pmtiles` protocol for the Protomaps file; Vitest for unit tests; Playwright for end-to-end tests |
| Map tiles | Protomaps PMTiles extract (India for production, a small region for dev), served as a static file |
| API | Python 3.12, FastAPI, Pydantic v2 (models with `extra="forbid"`), psycopg 3 with a connection pool, httpx (async) for Valhalla and Photon |
| Pass and toll engine | Plain Python package inside the API repo, type-checked with mypy in strict mode |
| Data jobs | Python 3.12: httpx or Playwright to fetch, pdfplumber or Camelot for PDF tables, rapidfuzz for plaza name matching |
| Admin review | Server-rendered pages inside the FastAPI app (Jinja2), HTTP basic auth using `ADMIN_PASSWORD` |
| Database | PostgreSQL 16 + PostGIS 3 with `btree_gist`; plain-SQL migrations run by a small migration tool (for example dbmate) |
| Routing | Valhalla, self-hosted, built from an OpenStreetMap extract |
| Place search | Photon, self-hosted, with an India search index |
| Caching | In-process TTL cache for Valhalla route results only (for example cachetools). No Redis in the MVP |
| Lint and format | ruff (lint + format) and mypy for Python; ESLint, Prettier and `tsc --noEmit` for TypeScript |
| Tests | pytest, with a real PostGIS database in a container (testcontainers or the Compose `db` service); never mock the database for toll tests |
| Local and production runtime | Docker Compose: `db`, `valhalla`, `photon`, `api`, `web`, plus a reverse proxy (Caddy) for TLS in production |
| CI | GitHub Actions: lint, type-check, all tests, golden journeys, build images |
| Later, not now | Astro for pre-built route pages; Redis; Kubernetes. Do not build these |

## 4. How to work

1. Start by writing `PLAN.md`: map every step of the build context's "Build order" to concrete tasks, files and tests. Keep it updated as you go, ticking tasks off.
2. Work one build step at a time, in order. Do not start a step until the previous step's "Done when" checks pass.
3. Commit in small, logical units with clear messages (`feat:`, `fix:`, `test:`, `docs:`, `chore:`).
4. When the specification is silent, choose the simplest option that keeps tolls exact, write it in `DECISIONS.md` (date, decision, reason, alternatives) and continue. Stop and ask only when a choice would change a toll amount or a pass outcome.
5. External sites (NHAI TIS, IHMCL, state authority sites) must not be hammered. Use recorded fixture files for all tests and development. Live scraping runs only from the scheduled jobs, with a descriptive user agent and at least 2 seconds between requests.
6. If a source is unreachable or its format is unclear, build the parser against the fixture you have, mark the gap in DECISIONS.md, and move on.
7. At the end of each step, report: what you built, files changed, how you verified it (commands and results), and open issues.

## 5. Build steps and deliverables

Follow the build context's "Build order". Below is what each step must produce in this stack.

### Step 1 - Foundation
- Repository layout as in the build context's "Repository, conventions and testing" section, plus `PLAN.md`, `DECISIONS.md` and `.env.example`.
- `docker-compose.yml` with `db` (PostGIS 16), `valhalla`, `photon`, `api`, `web`. Health checks on every service. One command (`make up` or `docker compose up`) brings everything up.
- For development, build Valhalla and Photon from a small regional OSM extract (one state or zone) so builds take minutes, not hours. Make the extract URL a single variable so switching to all of India is a config change.
- `db/migrations/001_schema.sql` = the schema from the build context, verbatim. Seed data in `db/seed/`: a handful of plazas, one closed section with three interchanges, rates either side of 1 April, and sample statistics. Use real coordinates on a real road inside your dev extract so Valhalla routes through them.
- Database tests reproducing every check listed under "Database schema".

### Step 2 - Engine
- `api/app/engine/` with typed dataclasses or Pydantic models for: charging point with rate, pass input, vehicle input, point result, route result.
- Functions: order and merge points, apply journey type (return fare or two one-way fares), apply pass rules in travel order, compute totals and break-even journeys.
- Unit tests covering at least every case listed in the build context's testing section, plus: return journey on a closed section, pass with no `trips_left` given, `RATE_MISSING` point, and a rate exactly on its `effective_from` and `effective_to` dates.

### Step 3 - Quote API
- `GET /v1/places` and `POST /v1/quote` exactly as specified, plus `GET /healthz` (process up) and `GET /readyz` (database, Valhalla and Photon reachable).
- Valhalla client: request `auto` costing with the three variants in the quote algorithm; 5 second timeout; one retry on connection errors; decode the encoded shape (precision 6) to GeoJSON.
- Call the SQL functions `plazas_on_route`, `closed_sections_on_route` and `rate_for`; never re-implement them in Python.
- Error envelope and codes exactly as specified. OpenAPI docs served at `/docs`.
- One structured JSON log line per quote: request id, route count, point count, rate version, Valhalla and database timings.
- Contract tests for every endpoint and error code.

### Step 4 - Web app
- Single page: form, map, quote card, all pass box variants and all states from the build context's "Web app" section.
- Form state in the URL query string; all user-facing text in `web/src/strings.en.json`.
- Map: Protomaps file via the `pmtiles` protocol, route lines, toll point markers (filled = charged, outlined = covered by the pass), "© OpenStreetMap contributors" attribution.
- Accessibility: keyboard use, visible focus, WCAG AA contrast, amounts readable by screen readers, reduced motion respected. Works on a 360 px wide screen.
- Playwright test: fill the form, get a quote, check the total and the pass box render.

### Step 5 - Real NH data
- `jobs/tis_scrape.py` and `jobs/gazette_parse.py` following the job rules in "Data sources and jobs" (raw file saved first, checksum, `PENDING` rates, review on change over 10%).
- Admin pages: list pending rates with old vs new amount and source link; approve or reject singly or in bulk; approving closes the previous rate in the same transaction. List unmatched plazas.
- `golden/journeys.csv` with at least 20 hand-checked journeys, and a test that runs them all.

### Steps 6 to 10
- Implement as described in the build order: all vehicle classes and return journeys; lowest-toll and toll-free routes with de-duplication; closed sections for state roads (UP first); IHMCL statistics, name matching and insights; then all-India data and a deployment that meets the p95 target.

## 6. Quality gates (every step, enforced in CI)

- `ruff check`, `ruff format --check`, `mypy` (strict on `app/engine`), ESLint, Prettier, `tsc --noEmit` all clean.
- All unit, database, contract and end-to-end tests pass.
- Golden journeys match to the rupee. A mismatch fails CI and must block rate approval.
- Engine test coverage at least 95% of lines; overall API coverage at least 80%.
- No secrets in the repository; configuration only through environment variables (`DATABASE_URL`, `VALHALLA_URL`, `PHOTON_URL`, `ADMIN_PASSWORD`).
- `docker compose up` from a clean checkout works, and the README's steps are correct.

## 7. Definition of done for the MVP

- Every "Done when" check in the build order passes.
- A quote for a mixed NH + state expressway journey shows correct totals, `STATE_ROAD` on the state section and the right trips used.
- p95 quote latency under 1.5 seconds on the deployed stack, measured with a load test.
- Monthly IHMCL statistics load end to end and route facts appear only when there is enough data.
- PLAN.md is fully ticked and DECISIONS.md lists every choice made where the spec was silent.

## 8. When implementation is complete: write three documents

Once the definition of done is met, and only then, write these three documents in `docs/`. Base every statement on the code and on measurements you actually ran; mark anything estimated as an estimate. Use plain English, short sections, tables for comparisons and Mermaid diagrams for flows and architecture.

### docs/IMPLEMENTATION.md - how it was built
- As-built architecture diagram, and every place it differs from the build context, with the reason.
- Module and folder map: what lives where and what each part is responsible for.
- The life of one quote, step by step, with the file and function that handles each step.
- How the domain rules are stored as data and how to change each one (pass price, eligible classes, operator pass acceptance, trip units).
- The pass engine: inputs, outputs, the order rules are applied, and worked examples.
- Data jobs: each job, its schedule, inputs, outputs, failure handling and how review works.
- Testing: what each test layer covers, how to run it, coverage figures, and how to add a golden journey.
- Known limitations and a summary of DECISIONS.md.

### docs/DEPLOYMENT.md - how to run it in production
- Prerequisites and the target environment (one server in an Indian cloud region, about 16 GB RAM); exact sizing you tested.
- Step-by-step first deployment from a bare server: install, configure, start, verify.
- Building and refreshing the OpenStreetMap-derived artefacts (Valhalla tiles, Photon index, Protomaps file): commands, time and disk needed, and how to swap them in without downtime.
- Configuration and secrets: every environment variable, its purpose and an example.
- Database: migrations on deploy, nightly backups, restore procedure (tested), and retention.
- TLS and the reverse proxy, domain setup, and security headers.
- Scheduled jobs: where they run, schedules, logs, and how to rerun one.
- Monitoring and alerts: health endpoints, what to alert on (API errors, latency, a scrape finding under 95% of last run's plazas, pending rates waiting more than 3 days).
- Release and rollback procedure.
- The 1 April runbook: what to watch, how to review and approve the new rates quickly, and how to verify with golden journeys.
- Running costs per month for the tested setup.

### docs/SCALABILITY.md - how far it goes and how to grow it
- Measured capacity: load-test method and tool (k6 or Locust), traffic mix, and results (requests per second at p50, p95 and p99 latency, CPU and memory per service). No unmeasured numbers.
- The bottlenecks, in the order they will hit (expect Valhalla CPU and memory first), with evidence.
- A staged growth path with the trigger for each stage, for example: bigger server; separate Valhalla and Photon servers; several stateless API instances behind a load balancer with Redis for the route cache; a database read replica; a CDN for the web app and the Protomaps file; Astro route pages for search traffic; and when, if ever, Kubernetes is worth it.
- Data growth: table sizes now and projected per year (rates, statistics), and when partitioning or archiving is needed.
- Cost per 1,000 quotes at each stage.
- Service level objectives to adopt (availability, p95 latency, rate freshness after 1 April) and how to measure them.
- Risks to scale beyond software: scraping limits, manual state data curation, and review workload.

When all three documents are written, give a final report: what was delivered, how to run it, test and load-test results, open issues, and recommended next steps.
```
