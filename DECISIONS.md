# Architectural & Implementation Decisions

Record of choices made where the specification was silent, following the prompt requirements:
`Date | Decision | Reason | Alternatives Considered`

---

## 2026-11-01: Initial Architecture & Tech Stack Confirmation
- **Decision**: Adopt PostgreSQL 16 + PostGIS 3.4, Python 3.12 with FastAPI, and React + Vite + TypeScript for the frontend, with Valhalla and Photon as self-hosted services via Docker Compose.
- **Reason**: Mandated strictly by the project context and prompt to guarantee 100% free, open-source stack with reproducible local setups.
- **Alternatives Considered**: Paid APIs (Google Maps, Mappls, TollGuru) — strictly rejected per non-negotiables.

## 2026-11-01: Parallel Workstream Strategy
- **Decision**: Separate the pure pass and toll calculation engine (`api/app/engine/`) from the database and frontend layers, allowing parallel subagent development.
- **Reason**: The pass engine is specified as a pure function without network or database dependencies; it can be implemented and fully unit-tested while database migrations and frontend scaffolding proceed independently.
- **Alternatives Considered**: Monolithic sequential development (slower, blocks UI and engine testing until DB is live).
