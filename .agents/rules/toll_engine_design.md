# India Toll Price MVP — System & Domain Guardrails

## Core Philosophy & Guardrails
- **Toll Price First**: The interface provides three primary answers: exact toll, annual pass coverage/impact, and key road facts. Avoid clutter.
- **Accuracy is the Brand**: All rates must be traceable to official gazette notices or NHAI TIS records. If a state road has not been curated yet, mark it as "not yet available" rather than silently omitting it or guessing.
- **Always Show the Reason**: When the FASTag annual pass does not apply, explicitly indicate why using canonical reason codes:
  - `NOT_ELIGIBLE`: Vehicle class not permitted (only non-commercial CAR/JEEP/VAN allowed).
  - `STATE_ROAD`: Operator does not accept NHAI pass (e.g., UPEIDA, MSRDC, Atal Setu).
  - `TRIPS_USED_UP`: Annual pass quota depleted during travel.

## Tech Stack & Architecture
- **Web App**: Static frontend with MapLibre GL for rendering routes and toll points.
- **Map Tiles**: Protomaps (India PMTiles served from object storage).
- **Geocoding & Autocomplete**: Self-hosted Photon (OSM India).
- **Routing Engine**: Valhalla on OSM India (providing `USUAL`, `LOWEST_TOLL`, and `TOLL_FREE` routes).
- **Backend Service**: Monolithic Quote API & Toll Engine (Python or Go).
- **Database**: PostgreSQL with PostGIS extension for spatial queries (50m route buffer with carriageway directionality verification).
- **Data-Driven Rules**: All toll plaza rates, vehicle mappings, and pass configurations must exist in the database, allowing policy updates without code deployment.

## Toll & Pass Business Invariants
- **Charging Points**:
  - Open/Point-based plazas: Fee paid at the plaza point.
  - Closed sections (expressways): Fee calculated per entry–exit interchange pair.
- **Annual Pass Invariants (FY 2026–27)**:
  - Rate: ₹3,075 for 1 year or 200 trips, whichever comes first.
  - Eligibility: Non-commercial cars, jeeps, and vans only.
  - Acceptance: NHAI / MoRTH points only (`pass_accepted = true`). State toll roads = `false`.
  - Trip Consumption:
    - 1 plaza crossing = 1 trip.
    - Return trip via same plaza = 2 trips.
    - Closed section (entry + exit pair) = 1 trip.
    - Points are consumed in sequential travel order until `trips_left` reaches 0. Subsequent points are charged at full rate with `TRIPS_USED_UP`.
  - Break-Even Analysis: If user has no pass, calculate `break_even_trips = ₹3,075 / (toll_without_pass - toll_with_pass)`.

## API Contracts & Conventions
- `POST /v1/quote`: Accepts `from`, `to`, `vehicle_class`, `commercial`, `journey` (`ONE_WAY` | `RETURN_24H`), `travel_date`, and optional `annual_pass` status.
- Route alternatives: Up to three routes (`USUAL`, `LOWEST_TOLL`, `TOLL_FREE`).
- Insight rules: Sum pre-aggregated plaza facts (traffic crossings, FASTag collections, pass usage ratio) using official IHMCL data sources.
