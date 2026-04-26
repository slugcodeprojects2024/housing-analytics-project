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
