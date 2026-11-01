# India Toll Price & FASTag Pass MVP — Implementation Review Report

**Date:** 2026-11-01  
**Target Codebase:** `/Users/darkhorse/Projects/toll-calci`  
**Overall Grade:** **B+ (Solid MVP with Gaps)**

---

## 1. Executive Summary

The **India Toll Price & FASTag Pass MVP** is an exceptionally well-structured project that faithfully delivers on the core architectural invariants:
- **Pure domain engine**: Zero I/O, no database/clock dependencies, pure deterministic FIFO pass consumption, and break-even calculations.
- **Strict schema fidelity**: `db/migrations/001_schema.sql` is a 1-to-1 match with the specification, including `btree_gist` exclusion constraints to prevent overlapping rate periods, spatial geography indexes, and bearing-based cross-road filtering.
- **Decimal arithmetic**: The calculation engine adheres to `Decimal` math.
- **Privacy by design**: Clamping lat/lon to 2 decimals in logs with zero user tracking.

However, several deviations, missing modules, and implementation gaps must be resolved before production readiness:
1. **Routing Strategy**: The spec requires 3 distinct Valhalla route requests (`USUAL` via `use_tolls=1.0`, `LOWEST_TOLL` via `use_tolls=0.1`, and `TOLL_FREE` via `use_tolls=0`), plus route deduplication. The current API only performs a single Valhalla call with `alternates=1` and artificially renames index 0 and 1.
2. **Rounding Method**: In `main.py`, amounts are cast to float and rounded with Python's built-in `round()` (banker's rounding) instead of the spec-mandated `ROUND_HALF_UP` on `Decimal`.
3. **Missing Return Rate Fallback**: Missing `RETURN_24H` rates do not fall back to 2× `ONE_WAY`.
4. **Tile Server**: MapLibre uses public `tile.openstreetmap.org` raster tiles instead of self-hosted Protomaps PMTiles as required by the production spec.
5. **Missing Scheduled Jobs**: `gazette_parse.py`, `state_rates.py`, and `osm_refresh.sh` are missing.

---

## 2. Requirements Compliance Matrix

| Requirement / Component | Status | Detailed Finding |
| :--- | :---: | :--- |
| **Exact Tolls from APPROVED Rates** | ✅ | Implemented in `rate_for` SQL function; unapproved/unverified rates return `RATE_MISSING`. |
| **Rules as Data** | ⚠️ | Pass product table exists, but eligibility is hardcoded as `vehicle_class == CAR_JEEP_VAN` in `calculator.py:21` instead of dynamically querying `pass_product_vehicle_class`. |
| **Decimal Precision & Rounding** | ⚠️ | Engine uses `Decimal`, but `main.py:517` converts to float and uses Python `round()` (banker's round) instead of `Decimal.quantize(..., rounding=ROUND_HALF_UP)`. |
| **Schema Verbatim Compliance** | ✅ | Matches `001_schema.sql` verbatim with full spatial indexes, constraints, and stored procedures. |
| **Zero User Telemetry** | ✅ | Coordinates clamped to 2 decimal places in structured quote logging; no user profiling. |
| **100% Free & Open-Source Stack** | ⚠️ | Stack is FOSS, but `Map.tsx` points to public `tile.openstreetmap.org` raster tiles contrary to production spec prohibiting public tile servers. |
| **Pure Calculation Engine** | ✅ | `calculator.py` is completely pure with 0 external I/O or network dependencies. |
| **Six Vehicle Classes** | ✅ | All 6 standard NHAI classes implemented across models, DB enums, and UI. |
| **Three Route Variants (USUAL / LOWEST / FREE)** | ❌ | `main.py:243-255` only makes 1 Valhalla query with `alternates=1` rather than 3 separate requests with distinct `use_tolls` penalties. |
| **Route Deduplication** | ❌ | Spec-required filtering of routes with duplicate toll points / totals or empty toll-free fallback is missing. |
| **Valhalla Route Caching** | ❌ | `cachetools` is listed in `requirements.txt` but never imported or utilized in `valhalla.py`. |
| **RETURN_24H Fallback** | ❌ | If `RETURN_24H` rate is absent, the system flags `RATE_MISSING` instead of calculating 2× `ONE_WAY`. |
| **Restricted Geocoding to India** | ⚠️ | `photon.py` lacks country filter or India bounding box parameter in query calls. |
| **Readiness Probes (`/readyz`)** | ⚠️ | `main.py:122-136` only tests DB connectivity, omitting Valhalla and Photon health checks. |
| **Admin Review Dashboard** | ✅ | HTTP Basic Auth with timing-safe comparison, diff inspection, and atomic rate closure. |
| **Pipeline Jobs (`gazette_parse`, `state_rates`, `osm_refresh`)** | ❌ | Missing from `jobs/`. Only `tis_scrape.py` and `ihmcl_stats.py` are present. |
| **Insights & Indian Notation** | ✅ | Correctly formats Lakhs and Crores with 2 significant figures. |
| **Frontend UI & Visual Milestone Design** | ✅ | Responsive to 360px, supports URL query syncing, and displays all pass box status states. |
| **Accessibility (WCAG AA)** | ⚠️ | Keyboard navigation and focus states exist, but currency amounts lack explicit `aria-label="rupees X"` tags. |
| **CORS Configuration** | ❌ | `.env` has `CORS_ORIGINS`, but `CORSMiddleware` is not added to FastAPI in `main.py`. |
| **CI / CD Pipeline** | ❌ | No `.github/workflows/` or equivalent automated test runner pipeline file. |

---

## 3. Architecture & Code Quality Deep-Dive

### Engine & Models (`api/app/engine/`)
- **Strengths**: Strict Pydantic models with `ConfigDict(extra="forbid")`. Clean separation of journey pricing, pass quota deductions, and break-even journey math.
- **Gaps**: `calculator.py` checks vehicle eligibility directly via hardcoded enum rather than evaluating rules passed in from `pass_product_vehicle_class`.

### API Layer (`api/app/main.py`)
- **Strengths**: Solid error envelopes (`INVALID_INPUT`, `NO_ROUTE`, `UPSTREAM_UNAVAILABLE`), comprehensive logging with coordinate truncation.
- **Gaps**: 
  - Float conversion before rounding (`round(float(pt.amount_inr))`).
  - No route deduplication or multi-penalty routing.
  - Missing CORS middleware.

### Database (`db/migrations/001_schema.sql` & `db/seed/seed.sql`)
- **Strengths**: Flawless PostGIS functions (`plazas_on_route` with 30° route-bearing tolerance, `closed_sections_on_route`). Correct `btree_gist` non-overlapping validity exclusion.
- **Gaps**: None in schema. Seed data covers UP corridor accurately.

### Data Pipelines (`jobs/`)
- **Strengths**: `polite_http.py` enforces 2s delays; `source_doc.py` uses SHA-256 deduplication; `ihmcl_stats.py` uses RapidFuzz `token_sort_ratio` for fuzzy name matching.
- **Gaps**: `tis_scrape.py` only implements record ingestion logic, not full web crawler/HTML extraction. Missing `gazette_parse.py` and `state_rates.py`.

### Frontend (`web/src/`)
- **Strengths**: Clean React 18 + TypeScript, centralized UI strings (`strings.en.json`), URL state synchronization.
- **Gaps**:
  - `Map.tsx` does not utilize `hoveredPoint` or interactive scroll-to-card callbacks.
  - Uses OSM raster tiles rather than vector PMTiles.
  - Nginx web container lacks upstream reverse proxy configuration for `/v1/`.

---

## 4. Categorized Issues & Risks

### 🔴 Critical (Blocks Production)
1. **Three-Route Multi-Valhalla Engine**: Update `main.py` to query Valhalla 3 times with `use_tolls` (1.0, 0.1, 0.0) and implement route deduplication.
2. **Precision Rounding Bug**: Replace `round(float(...))` with `int(val.quantize(Decimal('1'), rounding=ROUND_HALF_UP))` across all pricing handlers.
3. **RETURN_24H Fallback**: Handle missing 24h return rates by falling back to 2× single journey rate.
4. **Tile Server Production Violation**: Switch `Map.tsx` to self-hosted Protomaps PMTiles or configured vector tiles.

### 🟡 Important (Fix Before Launch)
5. **CORS Middleware**: Add `CORSMiddleware` to FastAPI using `CORS_ORIGINS`.
6. **Full `/readyz` Check**: Include network health pings to Valhalla and Photon alongside Postgres.
7. **Async Admin DB**: Replace blocking synchronous `psycopg.connect()` in `admin.py` with the async connection pool.
8. **Valhalla In-Memory TTL Cache**: Wire up `cachetools.TTLCache` in `valhalla.py`.
9. **Dynamic Pass Eligibility**: Query `pass_product_vehicle_class` table rather than hardcoding `CAR_JEEP_VAN`.
10. **Country Filter in Geocoder**: Restrict Photon geocoding queries with India bounding box / country code `in`.
11. **CI Workflow**: Create GitHub Actions workflow for linting, typing, pytest, and golden tests.

### 🟢 Minor / Nice-to-Have
12. **Screen Reader `aria-label`**: Add formatted spoken text (`rupees 3,075`) to UI price nodes.
13. **Map Marker Interactivity**: Connect `hoveredPoint` to scroll list items into view.
14. **Container Nginx Config**: Provide proxy rules in `web/Dockerfile` so the UI container routes `/v1` requests to `api:8000`.
15. **Documentation Alignment**: Remove references to nonexistent `annual_pass_rule` table in docs.

