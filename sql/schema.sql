-- WeatherFlow star schema (SQLite).
-- Grain of the fact table: one row per city, per hour, per source.

CREATE TABLE IF NOT EXISTS dim_city (
    city_id    INTEGER PRIMARY KEY,
    city_name  TEXT    NOT NULL UNIQUE,
    country    TEXT    NOT NULL,
    latitude   REAL    NOT NULL,
    longitude  REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_date (
    date_id     INTEGER PRIMARY KEY,                                 -- YYYYMMDD, e.g. 20261123
    full_date   TEXT    NOT NULL UNIQUE,                             -- 2026-11-23
    year        INTEGER NOT NULL,
    month       INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    month_name  TEXT    NOT NULL,
    day         INTEGER NOT NULL CHECK (day BETWEEN 1 AND 31),
    day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 1 AND 7), -- 1 = Monday
    day_name    TEXT    NOT NULL,
    is_weekend  INTEGER NOT NULL CHECK (is_weekend IN (0, 1))
);

CREATE TABLE IF NOT EXISTS fact_weather_hourly (
    city_id             INTEGER NOT NULL REFERENCES dim_city (city_id),
    date_id             INTEGER NOT NULL REFERENCES dim_date (date_id),
    observed_at_utc     TEXT    NOT NULL,
    observed_at_local   TEXT    NOT NULL,
    hour_local          INTEGER NOT NULL CHECK (hour_local BETWEEN 0 AND 23),
    temperature_c       REAL,
    feels_like_c        REAL,
    temperature_f       REAL,
    humidity_pct        INTEGER,
    precipitation_mm    REAL,
    wind_speed_kmh      REAL,
    wind_speed_ms       REAL,
    beaufort_scale      INTEGER CHECK (beaufort_scale BETWEEN 0 AND 12),
    weather_code        INTEGER,
    weather_description TEXT,
    weather_category    TEXT,
    is_daylight         INTEGER CHECK (is_daylight IN (0, 1)),
    outdoor_work_risk   TEXT    NOT NULL CHECK (outdoor_work_risk IN ('low', 'medium', 'high')),
    source              TEXT    NOT NULL,
    ingested_at_utc     TEXT    NOT NULL,
    PRIMARY KEY (city_id, observed_at_utc, source)
);