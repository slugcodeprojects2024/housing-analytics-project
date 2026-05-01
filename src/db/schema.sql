-- Housing Analytics database schema

CREATE TABLE IF NOT EXISTS geographies (
    geography_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    geo_code       TEXT NOT NULL,
    geo_type       TEXT NOT NULL,
    name           TEXT NOT NULL,
    state          TEXT,
    county         TEXT,
    metro          TEXT,
    latitude       REAL,
    longitude      REAL,
    UNIQUE(geo_code, geo_type)
);

CREATE INDEX IF NOT EXISTS idx_geo_state ON geographies(state);
CREATE INDEX IF NOT EXISTS idx_geo_type  ON geographies(geo_type);

CREATE TABLE IF NOT EXISTS housing_metrics (
    geography_id   INTEGER NOT NULL,
    metric_date    DATE NOT NULL,
    metric_type    TEXT NOT NULL,
    value          REAL,
    PRIMARY KEY (geography_id, metric_date, metric_type),
    FOREIGN KEY (geography_id) REFERENCES geographies(geography_id)
);

CREATE INDEX IF NOT EXISTS idx_hm_date    ON housing_metrics(metric_date);
CREATE INDEX IF NOT EXISTS idx_hm_metric  ON housing_metrics(metric_type);

CREATE TABLE IF NOT EXISTS macro_indicators (
    indicator      TEXT NOT NULL,
    obs_date       DATE NOT NULL,
    value          REAL,
    PRIMARY KEY (indicator, obs_date)
);

CREATE TABLE IF NOT EXISTS derived_metrics (
    geography_id   INTEGER NOT NULL,
    metric_date    DATE NOT NULL,
    metric_name    TEXT NOT NULL,
    value          REAL,
    PRIMARY KEY (geography_id, metric_date, metric_name),
    FOREIGN KEY (geography_id) REFERENCES geographies(geography_id)
);

CREATE TABLE IF NOT EXISTS load_log (
    load_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    source         TEXT NOT NULL,
    loaded_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    row_count      INTEGER,
    notes          TEXT
);

-- BLS occupational wage data by metro area
CREATE TABLE IF NOT EXISTS metro_wages (
    area_code      TEXT NOT NULL,       -- BLS MSA code e.g. '41940'
    area_name      TEXT NOT NULL,       -- BLS MSA name e.g. 'San Jose-Sunnyvale-Santa Clara, CA'
    occ_code       TEXT NOT NULL,       -- SOC code e.g. '15-1252'
    occ_title      TEXT NOT NULL,       -- e.g. 'Software Developers'
    total_employed INTEGER,
    median_wage    REAL,                -- Annual median wage
    mean_wage      REAL,                -- Annual mean wage
    pct10_wage     REAL,
    pct25_wage     REAL,
    pct75_wage     REAL,
    pct90_wage     REAL,
    data_year      INTEGER NOT NULL,
    PRIMARY KEY (area_code, occ_code, data_year)
);

CREATE INDEX IF NOT EXISTS idx_mw_occ ON metro_wages(occ_code);
CREATE INDEX IF NOT EXISTS idx_mw_area ON metro_wages(area_code);

-- Crosswalk between BLS metro names and Zillow metro names
CREATE TABLE IF NOT EXISTS metro_crosswalk (
    bls_area_code  TEXT NOT NULL,
    bls_area_name  TEXT NOT NULL,
    zillow_metro   TEXT,                -- matching geo_code from geographies where geo_type='metro'
    match_quality  TEXT,                -- 'exact', 'fuzzy', 'manual', 'unmatched'
    PRIMARY KEY (bls_area_code)
);
