-- =====================================================================
-- India Toll Price MVP - database schema (PostgreSQL 16 + PostGIS 3)
-- Free-stack design: toll price, annual pass coverage, route insights.
-- Nothing about users is stored.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS btree_gist;   -- for non-overlapping rate periods

-- ---------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------
CREATE TYPE operator_level   AS ENUM ('CENTRAL', 'STATE', 'PRIVATE');
CREATE TYPE road_type        AS ENUM ('NH', 'NE', 'SH', 'STATE_EXPRESSWAY', 'BRIDGE', 'OTHER');
CREATE TYPE point_kind       AS ENUM ('PLAZA', 'CLOSED_SECTION');
CREATE TYPE point_status     AS ENUM ('ACTIVE', 'SUSPENDED', 'TOLL_FREE');
CREATE TYPE journey_type     AS ENUM ('ONE_WAY', 'RETURN_24H');
CREATE TYPE review_status    AS ENUM ('PENDING', 'APPROVED', 'REJECTED');
CREATE TYPE source_doc_type  AS ENUM ('TIS_PAGE', 'GAZETTE', 'STATE_SITE', 'IHMCL_REPORT', 'DATA_GOV_IN', 'MANUAL');

-- ---------------------------------------------------------------------
-- Provenance: every rate and statistic points to the document it came from
-- ---------------------------------------------------------------------
CREATE TABLE source_document (
    id            bigserial PRIMARY KEY,
    doc_type      source_doc_type NOT NULL,
    url           text            NOT NULL,
    fetched_at    timestamptz     NOT NULL DEFAULT now(),
    sha256        char(64)        NOT NULL,
    reviewed_by   text,
    reviewed_at   timestamptz,
    UNIQUE (url, sha256)
);

-- ---------------------------------------------------------------------
-- Who runs the road, and whether the FASTag annual pass is accepted there
-- ---------------------------------------------------------------------
CREATE TABLE operator (
    id             smallserial    PRIMARY KEY,
    code           text           NOT NULL UNIQUE,      -- 'NHAI', 'MORTH', 'UPEIDA', 'MSRDC' ...
    name           text           NOT NULL,
    level          operator_level NOT NULL,
    pass_accepted  boolean        NOT NULL DEFAULT false,
    website        text
);

-- ---------------------------------------------------------------------
-- Vehicle classes: one canonical list, plus each operator's own names
-- ---------------------------------------------------------------------
CREATE TABLE vehicle_class (
    id           smallint PRIMARY KEY,
    code         text     NOT NULL UNIQUE,   -- CAR_JEEP_VAN, LCV, BUS_TRUCK_2AXLE, AXLE_3, AXLE_4_6, AXLE_7_PLUS
    name         text     NOT NULL,
    sort_order   smallint NOT NULL
);

CREATE TABLE operator_vehicle_class (
    operator_id          smallint NOT NULL REFERENCES operator(id),
    operator_class_name  text     NOT NULL,          -- as printed in that operator's notices
    vehicle_class_id     smallint NOT NULL REFERENCES vehicle_class(id),
    PRIMARY KEY (operator_id, operator_class_name)
);

-- ---------------------------------------------------------------------
-- Roads and charging points (a plaza, or a closed section priced entry-to-exit)
-- ---------------------------------------------------------------------
CREATE TABLE road (
    id         serial    PRIMARY KEY,
    ref        text,                     -- 'NH-48', 'Agra-Lucknow Expressway'
    name       text      NOT NULL,
    road_type  road_type NOT NULL
);

CREATE TABLE charging_point (
    id                  serial        PRIMARY KEY,
    kind                point_kind    NOT NULL,
    operator_id         smallint      NOT NULL REFERENCES operator(id),
    road_id             integer       REFERENCES road(id),
    name                text          NOT NULL,
    state               text          NOT NULL,
    tis_plaza_id        text          UNIQUE,          -- NHAI TIS id, when there is one
    geom                geometry(Point, 4326),         -- plazas only
    road_bearing_deg    numeric(5,1)  CHECK (road_bearing_deg >= 0 AND road_bearing_deg < 180),
    trip_units          smallint      NOT NULL DEFAULT 1,   -- annual-pass trips per passage (plaza crossing or entry-exit pair)
    is_mlff             boolean       NOT NULL DEFAULT false,
    status              point_status  NOT NULL DEFAULT 'ACTIVE',
    source_document_id  bigint        REFERENCES source_document(id),
    CONSTRAINT plaza_has_location CHECK (kind <> 'PLAZA' OR geom IS NOT NULL)
);

-- Spatial index on geography so ST_DWithin(..., metres) can use it
CREATE INDEX charging_point_geog_idx ON charging_point USING gist ((geom::geography));
CREATE INDEX charging_point_operator_idx ON charging_point (operator_id);

-- Entry and exit points of a closed section
CREATE TABLE interchange (
    id                 serial      PRIMARY KEY,
    charging_point_id  integer     NOT NULL REFERENCES charging_point(id) ON DELETE CASCADE,
    name               text        NOT NULL,
    chainage_km        numeric(7,3) NOT NULL,
    geom               geometry(Point, 4326) NOT NULL,
    can_enter          boolean     NOT NULL DEFAULT true,
    can_exit           boolean     NOT NULL DEFAULT true,
    UNIQUE (charging_point_id, name)
);
CREATE INDEX interchange_geog_idx ON interchange USING gist ((geom::geography));

-- ---------------------------------------------------------------------
-- Rates: versioned by date, reviewed before use
--   Plaza rows: entry/exit interchange are NULL.
--   Closed-section rows: both set (an origin-destination matrix).
-- ---------------------------------------------------------------------
CREATE TABLE rate (
    id                    bigserial     PRIMARY KEY,
    charging_point_id     integer       NOT NULL REFERENCES charging_point(id),
    entry_interchange_id  integer       REFERENCES interchange(id),
    exit_interchange_id   integer       REFERENCES interchange(id),
    vehicle_class_id      smallint      NOT NULL REFERENCES vehicle_class(id),
    journey               journey_type  NOT NULL,
    amount_inr            numeric(10,2) NOT NULL CHECK (amount_inr >= 0),
    effective_from        date          NOT NULL,
    effective_to          date,                                   -- NULL = still in force
    valid_during          daterange     GENERATED ALWAYS AS (daterange(effective_from, effective_to, '[]')) STORED,
    status                review_status NOT NULL DEFAULT 'PENDING',
    source_document_id    bigint        NOT NULL REFERENCES source_document(id),
    CONSTRAINT od_pair_complete CHECK ((entry_interchange_id IS NULL) = (exit_interchange_id IS NULL)),
    CONSTRAINT period_order     CHECK (effective_to IS NULL OR effective_to >= effective_from),
    -- No two approved rates for the same point/pair/class/journey may overlap in time
    CONSTRAINT no_overlapping_approved_rates EXCLUDE USING gist (
        charging_point_id                    WITH =,
        (coalesce(entry_interchange_id, 0))  WITH =,
        (coalesce(exit_interchange_id, 0))   WITH =,
        vehicle_class_id                     WITH =,
        journey                              WITH =,
        valid_during                         WITH &&
    ) WHERE (status = 'APPROVED')
);
CREATE INDEX rate_lookup_idx ON rate (charging_point_id, vehicle_class_id, journey) WHERE status = 'APPROVED';

-- ---------------------------------------------------------------------
-- FASTag annual pass, per financial year
-- ---------------------------------------------------------------------
CREATE TABLE pass_product (
    id                       smallserial   PRIMARY KEY,
    code                     text          NOT NULL,          -- 'FASTAG_ANNUAL'
    financial_year           text          NOT NULL,          -- 'FY2026-27'
    price_inr                numeric(10,2) NOT NULL,
    max_trips                integer       NOT NULL,
    validity_days            integer       NOT NULL,
    requires_non_commercial  boolean       NOT NULL DEFAULT true,
    on_sale_from             date          NOT NULL,
    on_sale_to               date,
    source_document_id       bigint        REFERENCES source_document(id),
    UNIQUE (code, financial_year)
);

CREATE TABLE pass_product_vehicle_class (
    pass_product_id   smallint NOT NULL REFERENCES pass_product(id) ON DELETE CASCADE,
    vehicle_class_id  smallint NOT NULL REFERENCES vehicle_class(id),
    PRIMARY KEY (pass_product_id, vehicle_class_id)
);

-- ---------------------------------------------------------------------
-- Route insights: monthly figures from IHMCL reports, rolled up per FY
-- ---------------------------------------------------------------------
-- Names as printed in each report, mapped once to our charging points
CREATE TABLE stats_plaza_alias (
    source_name        text    NOT NULL,     -- 'IHMCL'
    reported_name      text    NOT NULL,
    state              text    NOT NULL,
    charging_point_id  integer REFERENCES charging_point(id),   -- NULL until matched
    match_confidence   numeric(4,3),
    PRIMARY KEY (source_name, reported_name, state)
);

CREATE TABLE plaza_monthly_stats (
    charging_point_id   integer   NOT NULL REFERENCES charging_point(id),
    month               date      NOT NULL CHECK (extract(day FROM month) = 1),
    vehicle_class_id    smallint  NOT NULL REFERENCES vehicle_class(id),
    fastag_txn_count    bigint    NOT NULL CHECK (fastag_txn_count >= 0),
    fastag_value_inr    numeric(16,2) NOT NULL CHECK (fastag_value_inr >= 0),
    source_document_id  bigint    NOT NULL REFERENCES source_document(id),
    PRIMARY KEY (charging_point_id, month, vehicle_class_id)
);

CREATE TABLE plaza_monthly_pass_stats (
    charging_point_id   integer   NOT NULL REFERENCES charging_point(id),
    month               date      NOT NULL CHECK (extract(day FROM month) = 1),
    annual_pass_txn_count bigint  NOT NULL CHECK (annual_pass_txn_count >= 0),
    source_document_id  bigint    NOT NULL REFERENCES source_document(id),
    PRIMARY KEY (charging_point_id, month)
);

-- Financial year label for a month: April-March
CREATE FUNCTION fy_label(d date) RETURNS text LANGUAGE sql IMMUTABLE AS $$
    SELECT 'FY' || (CASE WHEN extract(month FROM d) >= 4 THEN extract(year FROM d) ELSE extract(year FROM d) - 1 END)::int
           || '-' || lpad(((CASE WHEN extract(month FROM d) >= 4 THEN extract(year FROM d) ELSE extract(year FROM d) - 1 END)::int % 100 + 1)::text, 2, '0')
$$;

-- What the quote reads; refresh after each monthly load
CREATE MATERIALIZED VIEW plaza_fy_stats AS
WITH fastag AS (
    SELECT s.charging_point_id,
           fy_label(s.month)                                               AS financial_year,
           count(DISTINCT s.month)                                         AS months_reported,
           sum(s.fastag_txn_count)                                         AS fastag_txn_count,
           sum(s.fastag_value_inr)                                         AS fastag_value_inr,
           sum(s.fastag_txn_count) FILTER (WHERE vc.code = 'CAR_JEEP_VAN') AS car_txn_count
    FROM plaza_monthly_stats s
    JOIN vehicle_class vc ON vc.id = s.vehicle_class_id
    GROUP BY s.charging_point_id, fy_label(s.month)
),
pass AS (
    SELECT charging_point_id, fy_label(month) AS financial_year,
           sum(annual_pass_txn_count) AS annual_pass_txn_count
    FROM plaza_monthly_pass_stats
    GROUP BY charging_point_id, fy_label(month)
)
SELECT f.*, p.annual_pass_txn_count
FROM fastag f
LEFT JOIN pass p USING (charging_point_id, financial_year);

CREATE UNIQUE INDEX plaza_fy_stats_pk ON plaza_fy_stats (charging_point_id, financial_year);

-- =====================================================================
-- Queries used by the quote API
-- =====================================================================

-- 1. Plazas on a route, in travel order.
--    $1 = route LineString (GeoJSON, WGS84) from Valhalla.
--    Within 50 m of the route, and the road at the plaza runs roughly the
--    same way as the route (within 30 degrees, either direction).
CREATE FUNCTION plazas_on_route(route_geojson text, buffer_m double precision DEFAULT 50)
RETURNS TABLE (charging_point_id integer, position_on_route double precision)
LANGUAGE sql STABLE AS $$
    WITH r AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(route_geojson), 4326) AS g),
    hits AS (
        SELECT cp.id, cp.road_bearing_deg,
               ST_LineLocatePoint(r.g, cp.geom) AS pos, r.g
        FROM charging_point cp, r
        WHERE cp.kind = 'PLAZA' AND cp.status = 'ACTIVE'
          AND ST_DWithin(cp.geom::geography, r.g::geography, buffer_m)
    )
    SELECT id, pos
    FROM hits
    WHERE road_bearing_deg IS NULL
       OR abs(mod((degrees(ST_Azimuth(
                ST_LineInterpolatePoint(g, greatest(pos - 0.0005, 0)),
                ST_LineInterpolatePoint(g, least(pos + 0.0005, 1))))::numeric
             - road_bearing_deg + 360), 180)) NOT BETWEEN 30 AND 150
    ORDER BY pos
$$;

-- 2. Closed sections on a route: first interchange entered, last one exited.
CREATE FUNCTION closed_sections_on_route(route_geojson text, buffer_m double precision DEFAULT 100)
RETURNS TABLE (charging_point_id integer, entry_interchange_id integer,
               exit_interchange_id integer, position_on_route double precision)
LANGUAGE sql STABLE AS $$
    WITH r AS (SELECT ST_SetSRID(ST_GeomFromGeoJSON(route_geojson), 4326) AS g),
    hits AS (
        SELECT i.charging_point_id, i.id, i.can_enter, i.can_exit,
               ST_LineLocatePoint(r.g, i.geom) AS pos
        FROM interchange i
        JOIN charging_point cp ON cp.id = i.charging_point_id AND cp.status = 'ACTIVE'
        CROSS JOIN r
        WHERE ST_DWithin(i.geom::geography, r.g::geography, buffer_m)
    ),
    ends AS (
        SELECT charging_point_id,
               (array_agg(id ORDER BY pos)      FILTER (WHERE can_enter))[1] AS entry_id,
               (array_agg(id ORDER BY pos DESC) FILTER (WHERE can_exit))[1]  AS exit_id,
               min(pos) AS pos
        FROM hits
        GROUP BY charging_point_id
    )
    SELECT charging_point_id, entry_id, exit_id, pos
    FROM ends
    WHERE entry_id IS NOT NULL AND exit_id IS NOT NULL AND entry_id <> exit_id
    ORDER BY pos
$$;

-- 3. Rate for one point on the travel date, with pass acceptance.
CREATE FUNCTION rate_for(p_point integer, p_entry integer, p_exit integer,
                         p_class smallint, p_journey journey_type, p_date date)
RETURNS TABLE (amount_inr numeric, pass_accepted boolean, trip_units smallint, rate_id bigint)
LANGUAGE sql STABLE AS $$
    SELECT r.amount_inr, o.pass_accepted, cp.trip_units, r.id
    FROM rate r
    JOIN charging_point cp ON cp.id = r.charging_point_id
    JOIN operator o        ON o.id  = cp.operator_id
    WHERE r.charging_point_id = p_point
      AND coalesce(r.entry_interchange_id, 0) = coalesce(p_entry, 0)
      AND coalesce(r.exit_interchange_id, 0)  = coalesce(p_exit, 0)
      AND r.vehicle_class_id = p_class
      AND r.journey = p_journey
      AND r.status = 'APPROVED'
      AND r.valid_during @> p_date
$$;

-- =====================================================================
-- Reference data
-- =====================================================================
INSERT INTO vehicle_class (id, code, name, sort_order) VALUES
 (1, 'CAR_JEEP_VAN',    'Car / jeep / van / LMV',            1),
 (2, 'LCV',             'LCV / LGV / minibus',               2),
 (3, 'BUS_TRUCK_2AXLE', 'Bus / truck (2 axle)',              3),
 (4, 'AXLE_3',          '3-axle commercial vehicle',         4),
 (5, 'AXLE_4_6',        'HCM / EME / MAV (4 to 6 axle)',     5),
 (6, 'AXLE_7_PLUS',     'Oversized vehicle (7 or more axle)',6)
ON CONFLICT (id) DO NOTHING;

INSERT INTO operator (code, name, level, pass_accepted, website) VALUES
 ('NHAI',   'National Highways Authority of India',                      'CENTRAL', true,  'https://nhai.gov.in'),
 ('MORTH',  'Ministry of Road Transport and Highways',                   'CENTRAL', true,  'https://morth.nic.in'),
 ('UPEIDA', 'Uttar Pradesh Expressways Industrial Development Authority','STATE',   false, 'https://upeida.up.gov.in'),
 ('YEIDA',  'Yamuna Expressway Industrial Development Authority',        'STATE',   false, NULL),
 ('MSRDC',  'Maharashtra State Road Development Corporation',            'STATE',   false, 'https://msrdc.in')
ON CONFLICT (code) DO NOTHING;

INSERT INTO pass_product (code, financial_year, price_inr, max_trips, validity_days, requires_non_commercial, on_sale_from, on_sale_to) VALUES
 ('FASTAG_ANNUAL', 'FY2025-26', 3000, 200, 365, true, '2025-08-15', '2026-03-31'),
 ('FASTAG_ANNUAL', 'FY2026-27', 3075, 200, 365, true, '2026-04-01', '2027-03-31')
ON CONFLICT (code, financial_year) DO NOTHING;

INSERT INTO pass_product_vehicle_class (pass_product_id, vehicle_class_id)
SELECT id, 1 FROM pass_product
ON CONFLICT DO NOTHING;
