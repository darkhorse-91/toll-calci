-- =====================================================================
-- India Toll Price MVP - Development & Test Seed Data
-- Region: Uttar Pradesh Corridor (NH-27 and Agra-Lucknow Expressway)
-- =====================================================================

-- 1. Source Documents (Evidence / Provenance)
INSERT INTO source_document (id, doc_type, url, sha256, reviewed_by, reviewed_at) VALUES
 (1, 'TIS_PAGE', 'https://tis.nhai.gov.in/TollInformation?TollFeeId=101', 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', 'admin', now()),
 (2, 'STATE_SITE', 'https://upeida.up.gov.in/en/page/agra-lucknow-expressway-toll-rates', 'ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb', 'admin', now()),
 (3, 'IHMCL_REPORT', 'https://ihmcl.co.in/etc-reports/2026-03.pdf', '3e23e8160039594a33894f6564e1b1348bbd7a0088d42c4acb73eeaed59c009d', 'admin', now())
ON CONFLICT (url, sha256) DO NOTHING;

-- 2. Roads
INSERT INTO road (id, ref, name, road_type) VALUES
 (1, 'NH-27', 'Lucknow - Kanpur - Jhansi Highway', 'NH'),
 (2, 'ALE', 'Agra-Lucknow Expressway', 'STATE_EXPRESSWAY'),
 (3, 'SH-25', 'Crossing State Highway 25', 'SH')
ON CONFLICT (id) DO NOTHING;

-- 3. Operators: Operator mapping for class names
INSERT INTO operator_vehicle_class (operator_id, operator_class_name, vehicle_class_id)
SELECT o.id, 'Car/Jeep/Van', 1 FROM operator o WHERE o.code IN ('NHAI', 'UPEIDA')
ON CONFLICT DO NOTHING;

INSERT INTO operator_vehicle_class (operator_id, operator_class_name, vehicle_class_id)
SELECT o.id, 'LCV/Mini Bus', 2 FROM operator o WHERE o.code IN ('NHAI', 'UPEIDA')
ON CONFLICT DO NOTHING;

INSERT INTO operator_vehicle_class (operator_id, operator_class_name, vehicle_class_id)
SELECT o.id, 'Truck/Bus 2 Axle', 3 FROM operator o WHERE o.code IN ('NHAI', 'UPEIDA')
ON CONFLICT DO NOTHING;

-- 4. Charging Points:
-- Plaza 1: Nawabganj Toll Plaza on NH-27 (Eastbound/Westbound approx 90 deg bearing)
-- Plaza 2: Barajod Toll Plaza on NH-27 (approx 100 deg bearing)
-- Plaza 3: Crossing Plaza on SH-25 (Perpendicular bearing 0 deg / North-South, should be skipped if East-West route)
-- Closed Section 1: Agra-Lucknow Expressway (UPEIDA)
INSERT INTO charging_point (id, kind, operator_id, road_id, name, state, tis_plaza_id, geom, road_bearing_deg, trip_units, is_mlff, status, source_document_id) VALUES
 (101, 'PLAZA', 1, 1, 'Nawabganj Toll Plaza', 'Uttar Pradesh', 'TIS_UP_101', ST_SetSRID(ST_MakePoint(80.6015, 26.6340), 4326), 90.0, 1, false, 'ACTIVE', 1),
 (102, 'PLAZA', 1, 1, 'Barajod Toll Plaza', 'Uttar Pradesh', 'TIS_UP_102', ST_SetSRID(ST_MakePoint(79.9500, 26.4150), 4326), 100.0, 1, false, 'ACTIVE', 1),
 (103, 'PLAZA', 1, 3, 'Perpendicular Crossing Plaza', 'Uttar Pradesh', 'TIS_UP_103', ST_SetSRID(ST_MakePoint(80.3000, 26.5000), 4326), 0.0, 1, false, 'ACTIVE', 1),
 (201, 'CLOSED_SECTION', 3, 2, 'Agra-Lucknow Expressway', 'Uttar Pradesh', NULL, NULL, NULL, 1, false, 'ACTIVE', 2)
ON CONFLICT (id) DO NOTHING;

-- 5. Interchanges for Agra-Lucknow Expressway (Closed section)
INSERT INTO interchange (id, charging_point_id, name, chainage_km, geom, can_enter, can_exit) VALUES
 (301, 201, 'Mohan Road Interchange (Lucknow)', 0.000, ST_SetSRID(ST_MakePoint(80.7710, 26.8320), 4326), true, true),
 (302, 201, 'Kannauj Interchange', 125.000, ST_SetSRID(ST_MakePoint(79.8800, 27.0500), 4326), true, true),
 (303, 201, 'Agra Interchange', 302.000, ST_SetSRID(ST_MakePoint(78.1000, 27.1500), 4326), true, true)
ON CONFLICT (id) DO NOTHING;

-- 6. Rates
-- Nawabganj Plaza Rates (One Way & Return, across 1 April 2026 date boundary)
-- Rates prior to 1 April 2026:
INSERT INTO rate (charging_point_id, entry_interchange_id, exit_interchange_id, vehicle_class_id, journey, amount_inr, effective_from, effective_to, status, source_document_id) VALUES
 (101, NULL, NULL, 1, 'ONE_WAY', 95.00, '2025-04-01', '2026-03-31', 'APPROVED', 1),
 (101, NULL, NULL, 1, 'RETURN_24H', 140.00, '2025-04-01', '2026-03-31', 'APPROVED', 1);

-- Rates starting 1 April 2026:
INSERT INTO rate (charging_point_id, entry_interchange_id, exit_interchange_id, vehicle_class_id, journey, amount_inr, effective_from, effective_to, status, source_document_id) VALUES
 (101, NULL, NULL, 1, 'ONE_WAY', 100.00, '2026-04-01', NULL, 'APPROVED', 1),
 (101, NULL, NULL, 1, 'RETURN_24H', 150.00, '2026-04-01', NULL, 'APPROVED', 1),
 (102, NULL, NULL, 1, 'ONE_WAY', 120.00, '2026-04-01', NULL, 'APPROVED', 1),
 (102, NULL, NULL, 1, 'RETURN_24H', 180.00, '2026-04-01', NULL, 'APPROVED', 1);

-- Rates for other vehicle classes at Nawabganj (FY 2026-27):
INSERT INTO rate (charging_point_id, entry_interchange_id, exit_interchange_id, vehicle_class_id, journey, amount_inr, effective_from, effective_to, status, source_document_id) VALUES
 (101, NULL, NULL, 2, 'ONE_WAY', 160.00, '2026-04-01', NULL, 'APPROVED', 1),
 (101, NULL, NULL, 3, 'ONE_WAY', 335.00, '2026-04-01', NULL, 'APPROVED', 1),
 (101, NULL, NULL, 4, 'ONE_WAY', 365.00, '2026-04-01', NULL, 'APPROVED', 1),
 (101, NULL, NULL, 5, 'ONE_WAY', 525.00, '2026-04-01', NULL, 'APPROVED', 1),
 (101, NULL, NULL, 6, 'ONE_WAY', 640.00, '2026-04-01', NULL, 'APPROVED', 1);

-- Agra-Lucknow Expressway OD Matrix Rates (UPEIDA)
INSERT INTO rate (charging_point_id, entry_interchange_id, exit_interchange_id, vehicle_class_id, journey, amount_inr, effective_from, effective_to, status, source_document_id) VALUES
 (201, 301, 302, 1, 'ONE_WAY', 270.00, '2026-04-01', NULL, 'APPROVED', 2),
 (201, 302, 303, 1, 'ONE_WAY', 385.00, '2026-04-01', NULL, 'APPROVED', 2),
 (201, 301, 303, 1, 'ONE_WAY', 655.00, '2026-04-01', NULL, 'APPROVED', 2),
 (201, 303, 301, 1, 'ONE_WAY', 655.00, '2026-04-01', NULL, 'APPROVED', 2);

-- 7. IHMCL Statistics & Aliases
INSERT INTO stats_plaza_alias (source_name, reported_name, state, charging_point_id, match_confidence) VALUES
 ('IHMCL', 'NAWABGANJ FP', 'Uttar Pradesh', 101, 0.98),
 ('IHMCL', 'BARAJOD FP', 'Uttar Pradesh', 102, 0.95);

-- 12 months of monthly statistics for FY 2025-26
INSERT INTO plaza_monthly_stats (charging_point_id, month, vehicle_class_id, fastag_txn_count, fastag_value_inr, source_document_id)
SELECT 101, ('2025-04-01'::date + (n || ' months')::interval)::date, 1, 950000, 90250000.00, 3
FROM generate_series(0, 11) n;

INSERT INTO plaza_monthly_pass_stats (charging_point_id, month, annual_pass_txn_count, source_document_id)
SELECT 101, ('2025-04-01'::date + (n || ' months')::interval)::date, 190000, 3
FROM generate_series(0, 11) n;

-- Refresh Materialized View
REFRESH MATERIALIZED VIEW plaza_fy_stats;
