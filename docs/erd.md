# WeatherFlow data model (star schema)

## Grain
**`fact_weather_hourly`: one row per city, per hour, per source.**
Primary key: `(city_id, observed_at_utc, source)`.

## Diagram
```mermaid
erDiagram
    dim_city ||--o{ fact_weather_hourly : "city_id"
    dim_date ||--o{ fact_weather_hourly : "date_id"
    dim_city {
        INTEGER city_id PK
        TEXT city_name "unique (natural key)"
        TEXT country
        REAL latitude
        REAL longitude
    }
    dim_date {
        INTEGER date_id PK "YYYYMMDD"
        TEXT full_date
        INTEGER year
        INTEGER month
        TEXT month_name
        INTEGER day
        INTEGER day_of_week "1 = Monday"
        TEXT day_name
        INTEGER is_weekend
    }
    fact_weather_hourly {
        INTEGER city_id PK, FK
        TEXT observed_at_utc PK
        TEXT source PK
        INTEGER date_id FK "London date"
        TEXT observed_at_local
        INTEGER hour_local
        REAL temperature_c
        REAL feels_like_c
        REAL temperature_f
        INTEGER humidity_pct
        REAL precipitation_mm
        REAL wind_speed_kmh
        REAL wind_speed_ms
        INTEGER beaufort_scale
        INTEGER weather_code
        TEXT weather_description
        TEXT weather_category
        INTEGER is_daylight
        TEXT outdoor_work_risk "low, medium or high"
        TEXT ingested_at_utc
    }
```

## Design decisions
- **`city_id` is a surrogate key** assigned by the database; `city_name` stays unique as the natural key. Cities are upserted from `config.yaml`, so adding a city needs no code change.
- **`date_id` is the London (local) date** (`YYYYMMDD`), because the business plans by UK calendar day. 23:30 UTC on 30 June is 1 July in London.
- **`source` is part of the key**, so a second weather source  can store the same city and hour without clashing.
- **The load is idempotent and atomic:** facts are upserted with `INSERT ... ON CONFLICT ... DO UPDATE`, and dimensions and facts are written in one transaction. Foreign keys are enforced with `PRAGMA foreign_keys = ON`.