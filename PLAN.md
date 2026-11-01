# India Toll Price MVP — Implementation Plan

This plan maps every step of the Build Order from [India Toll Price MVP - LLM Build Context.md](file:///Users/darkhorse/Projects/toll-calci/India%20Toll%20Price%20MVP%20-%20LLM%20Build%20Context.md) and [Implementation prompt.md](file:///Users/darkhorse/Projects/toll-calci/Implementation%20prompt.md) to concrete tasks, files, tests, and parallel workstreams.

---

## Architecture & Workstream Decomposition

To build efficiently without violating step dependencies, we split work into structured phases and modular workstreams that can proceed in parallel:

```mermaid
flowchart TD
  subgraph Phase 1: Core Foundation & Engine
    W_DB[Workstream 1: Database & Infra<br/>- 001_schema.sql<br/>- docker-compose.yml<br/>- Seed data & DB tests]
    W_ENG[Workstream 2: Pure Engine<br/>- api/app/engine/<br/>- Pure functions & models<br/>- 100% unit tests]
    W_UI[Workstream 3: Web App Shell<br/>- React + Vite + TS setup<br/>- MapLibre + Protomaps setup<br/>- UI Design system & strings.en.json]
  end

  subgraph Phase 2: Integration & API
    W_API[Workstream 4: FastAPI Service<br/>- /v1/places (Photon)<br/>- /v1/quote (Valhalla + PostGIS + Engine)<br/>- /healthz, /readyz & logging]
    W_CARDS[Workstream 5: Quote Card & Form<br/>- Interactive form + URL state<br/>- Quote card variants & pass states<br/>- Map route & coin markers]
  end

  subgraph Phase 3: Data Pipelines & Validation
    W_JOBS[Workstream 6: Scraping & Jobs<br/>- jobs/tis_scrape.py<br/>- jobs/gazette_parse.py<br/>- Admin review UI (Jinja2)]
    W_GOLD[Workstream 7: Golden Test Suite<br/>- golden/journeys.csv (20+ hand-checked)<br/>- E2E Playwright tests]
  end

  W_DB --> W_API
  W_ENG --> W_API
  W_UI --> W_CARDS
  W_API --> W_CARDS
  W_API --> W_JOBS
  W_CARDS --> W_GOLD
  W_JOBS --> W_GOLD
```

---

## Detailed Phases & Build Steps

### Phase 1: Foundation, Engine & Frontend Scaffolding (Parallelized)

#### Step 1: Foundation & Database (Workstream 1)
- [x] Create repository directory tree (`db/migrations/`, `db/seed/`, `api/app/`, `web/`, `jobs/`, `golden/`, `docs/`).
- [x] Create `db/migrations/001_schema.sql` copying the tested PostgreSQL 16 + PostGIS schema verbatim.
- [x] Create `docker-compose.yml` with `db` (PostGIS 16), `valhalla`, `photon`, `api`, `web`, and health checks.
- [x] Create `.env.example` defining `DATABASE_URL`, `VALHALLA_URL`, `PHOTON_URL`, `ADMIN_PASSWORD`.
- [x] Create `db/seed/seed.sql` with real coordinates in UP (e.g. NH-27 plazas, Agra-Lucknow expressway entry/exits), rates for both sides of April 1, and sample IHMCL stats.
- [x] Implement database integration tests verifying:
  - Route matching in travel order via `plazas_on_route` and `closed_sections_on_route`.
  - Exclusion of crossing roads (>30° bearing deviation).
  - Effective date rate selection across April 1.
  - Exclusion constraint rejecting overlapping approved rate periods.
- **Done When**: `docker compose up` brings services healthy, schema and seed load cleanly, and all DB tests pass.

#### Step 2: Toll & Pass Engine (Workstream 2 - Can run in parallel with Step 1)
- [x] Setup `api/app/engine/models.py`:
  - Typed Pydantic v2 / dataclasses for `PointWithRate`, `PassInput`, `VehicleInput`, `PointResult`, `RouteResult`.
  - Canonical enums (`VehicleClassCode`, `JourneyType`, `ReasonCode`).
- [x] Setup `api/app/engine/calculator.py`:
  - Pure function: `apply_pass_and_compute_totals(points, vehicle, journey, pass_input, pass_product) -> RouteResult`.
  - FIFO point consumption along travel order.
  - Reason assignment: `NOT_ELIGIBLE`, `STATE_ROAD`, `TRIPS_USED_UP`, `RATE_MISSING`.
  - Trip unit multiplier: default 1, doubled for `RETURN_24H`.
  - Break-even calculation: `pass_price / (toll_without_pass - toll_with_pass)` rounded up.
- [x] Setup `api/tests/test_engine.py`:
  - No pass scenario.
  - Commercial vehicle exclusion (`NOT_ELIGIBLE`).
  - All-NH route with pass (all ₹0).
  - Mixed NH and state expressway (`STATE_ROAD` with full fare).
  - Pass trips exhaustion midway (`TRIPS_USED_UP`).
  - Return journey doubling trips.
  - Closed section counting as 1 trip.
  - Zero saving yielding `break_even_journeys: null`.
  - Rate missing point handling (`complete: false`).
  - Rates on boundary dates (`effective_from` and `effective_to`).
- **Done When**: 100% pure engine unit tests pass, type-checked with `mypy --strict`, with >=95% test coverage.

#### Step 3: Web App Shell & Design System (Workstream 3)
- [x] Initialize `web/` with Vite, React, TypeScript, and MapLibre GL JS.
- [x] Configure `web/src/strings.en.json` containing all user-facing strings.
- [x] Implement design tokens matching `Toll price MVP — free-stack design.html`:
  - Highway milestone motif, Overpass typography, color palette (asphalt, concrete, sign green, cap yellow).
  - Dark mode and light mode CSS variables.
  - Accessible contrast (WCAG AA), responsive layout down to 360px viewport.
- [x] Scaffolding for Map component using `@maplibre/maplibre-gl-style-spec` and PMTiles protocol.

---

### Phase 2: API Service & Full UI Integration

#### Step 4: Quote API Implementation (Workstream 4)
- [x] Initialize FastAPI app in `api/app/main.py`.
- [x] Configure `api/app/clients/photon.py` proxying search to Photon (`/v1/places`).
- [x] Configure `api/app/clients/valhalla.py` requesting routes with `auto` costing, route alternatives (`alternates: 1`, `use_tolls: 0.1`, `use_tolls: 0`), 5s timeout, precision-6 polyline decoding.
- [x] Implement database queries calling `plazas_on_route`, `closed_sections_on_route`, and `rate_for`.
- [x] Connect pure engine to produce `/v1/quote` response schema.
- [x] Add `/healthz` (liveness) and `/readyz` (DB, Valhalla, Photon connectivity checks).
- [x] Implement structured JSON logging per quote (route count, point count, rate version, lat/lng clamped to 2 decimals).
- [x] Write API contract tests for 200 responses and error envelopes (`INVALID_INPUT`, `NO_ROUTE`, `UPSTREAM_UNAVAILABLE`).

#### Step 5: Web App Form, Map & Quote Cards (Workstream 5)
- [x] Build search-as-you-type input with Photon integration, swap button, and keyboard navigation.
- [x] Build vehicle selector (6 canonical chips, Private/Commercial toggle for CAR_JEEP_VAN).
- [x] Build journey toggle (One way vs Return 24h), Annual pass toggle + optional trips left, collapsed date picker.
- [x] Bind form state to URL query parameters for shareability.
- [x] Render interactive map with route polylines and coin markers (filled = charged, outlined = pass covered).
- [x] Implement Quote card with all pass box variants (Fully covered, Partly covered, Trips run out, No pass savings, Not eligible).
- [x] Implement UI states: loading skeleton, `complete: false` banner, no route found, API error with retry.

---

### Phase 3: Data Pipelines, Admin Review & Verification

#### Step 6: Scraping, Ingestion Jobs & Admin Review (Workstream 6)
- [x] Build `jobs/common/` framework (HTTP client with polite 2s rate limit, user agent, SHA-256 deduplication, `source_document` logger).
- [x] Build `jobs/tis_scrape.py` to extract NHAI TIS plazas and vehicle rates.
- [x] Build Jinja2 admin review page at `/admin` (HTTP Basic Auth) to inspect `PENDING` rates (>10% change alert) and approve/reject with automatic `effective_to` closeout.
- [x] Build `jobs/ihmcl_stats.py` with `rapidfuzz` plaza name matching.

#### Step 7: Golden Journeys & Final Verification (Workstream 7)
- [x] Populate `golden/journeys.csv` with initial 20 hand-checked journeys across NH and state expressways.
- [x] Create automated test `api/tests/test_golden.py` asserting quote totals match to the rupee.
- [x] Write Playwright end-to-end tests validating full user flow on desktop and 360px mobile viewport (`web/tests/e2e.spec.ts`).
- [x] Verify definitions of done:
  - Mixed NH + UP expressway shows correct toll, `STATE_ROAD`, and pass trip decrement.
  - Latency p95 under 1.5 seconds.
  - Zero secrets in code, clean linting (`ruff`, `mypy`, `eslint`, `tsc --noEmit`).
- [x] Author documentation in `docs/`: `IMPLEMENTATION.md`, `DEPLOYMENT.md`, and `SCALABILITY.md`.

