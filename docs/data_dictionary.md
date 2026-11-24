# Data dictionary: hourly weather for five UK cities

## About this data

| Item | Value |
|------|-------|
| Source | Open-Meteo Forecast API, `https://api.open-meteo.com/v1/forecast` (docs: https://open-meteo.com/en/docs) |
| Request | `hourly=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,wind_speed_10m,weather_code`, `past_days=1`, `forecast_days=1`, `timezone=Europe/London` |
| Cities | London, Manchester, Birmingham, Edinburgh, Cardiff (coordinates from the Open-Meteo Geocoding API, stored in `extract.py`) |
| Licence | Open-Meteo data is licensed under **CC BY 4.0**: reuse is allowed with attribution to Open-Meteo.com. The free API itself is for non-commercial use; commercial use needs an API subscription. |
| Refresh frequency | Week 1: each time `extract.py` or `etl_v1.py` is run (planned hourly). Open-Meteo updates its data as new weather-model runs arrive, several times a day. |
| Coverage per run | 48 hours per city (yesterday 00:00 to today 23:00, local time), so 5 × 48 = 240 rows per run |
| **Grain** | **One row per city per hour** |
| Natural key | `(city, time)` |
| Time zone | All times are Europe/London local time (GMT in winter, BST = UTC+1 in summer) |
| Raw files | `data/raw/<YYYY-MM-DD>/<city>_<YYYYMMDDTHHMMSS>.json`, date and timestamp in UTC, never edited |

## Flattened table (`flatten()` output)

One row per element of the parallel lists under `hourly`, plus the city and the grid-cell coordinates.
Units come from `hourly_units` in each response.

| Column | Type | Unit | Description | Example | Nullable? | Source |
|--------|------|------|-------------|---------|-----------|--------|
| time | text in the raw data; converted to datetime in the transform | Europe/London local time, ISO 8601 `YYYY-MM-DDTHH:MM` | The hour the values are valid for. Instant variables are measured at this moment; `precipitation` is the total for the hour that **ends** here. | 2026-11-11T00:00 | No | Open-Meteo `hourly.time` |
| temperature_2m | float | °C | Air temperature 2 m above ground | 9.0 | Yes | Open-Meteo `hourly.temperature_2m` |
| relative_humidity_2m | integer | % (0–100) | Relative humidity 2 m above ground | 94 | Yes | Open-Meteo `hourly.relative_humidity_2m` |
| apparent_temperature | float | °C | "Feels like" temperature, combining air temperature, wind chill, humidity and sunshine | 6.9 | Yes | Open-Meteo `hourly.apparent_temperature` |
| precipitation | float | mm | Total rain, showers and snow in the preceding hour | 0.1 | Yes | Open-Meteo `hourly.precipitation` |
| wind_speed_10m | float | km/h | Wind speed 10 m above ground | 11.5 | Yes | Open-Meteo `hourly.wind_speed_10m` |
| weather_code | integer | WMO code | Weather condition as a WMO code, e.g. 0 = clear sky, 3 = overcast, 51 = light drizzle, 61 = slight rain, 95 = thunderstorm. Full table in the Open-Meteo docs and in `notebooks/01_explore.ipynb`. | 51 | Yes | Open-Meteo `hourly.weather_code` |
| city | text | none | City name as listed in `extract.py` (the key, together with `time`) | London | No | Added by `flatten()` |
| latitude | float | decimal degrees (WGS 84) | Latitude of the model **grid cell** Open-Meteo used. It is close to, but not equal to, the requested coordinate. | 51.51147 | No | Open-Meteo `latitude` (top level) |
| longitude | float | decimal degrees (WGS 84) | Longitude of the model grid cell Open-Meteo used | -0.13078308 | No | Open-Meteo `longitude` (top level) |

The exploration notebook also adds `source_file` (text, the raw file a row came from) to trace duplicates.
It is not part of the pipeline's output.

## Loaded table: `weather_hourly` in `weather.db`

Written by `etl_v1.py`. Same grain: one row per city per hour. Primary key `(city, observed_at)`.
Column names carry their unit, so nobody has to guess whether a number is °C or °F, km/h or mph.

| Column | SQLite type | Unit | Description | Example | Nullable? | Source column |
|--------|-------------|------|-------------|---------|-----------|---------------|
| city | TEXT | none | City name. Part of the primary key. | London | No | `city` |
| observed_at | TEXT | Europe/London local time, `YYYY-MM-DDTHH:MM` | Hour the values are valid for. Part of the primary key. Includes forecast hours later than the run time. | 2026-11-11T00:00 | No | `time` |
| temperature_c | REAL | °C | Air temperature 2 m above ground | 9.0 | Yes | `temperature_2m` |
| feels_like_c | REAL | °C | Apparent ("feels like") temperature | 6.9 | Yes | `apparent_temperature` |
| humidity_pct | INTEGER | % | Relative humidity 2 m above ground | 94 | Yes | `relative_humidity_2m` |
| precipitation_mm | REAL | mm | Rain, showers and snow in the preceding hour | 0.1 | Yes | `precipitation` |
| wind_speed_kmh | REAL | km/h | Wind speed 10 m above ground | 11.5 | Yes | `wind_speed_10m` |
| weather_code | INTEGER | WMO code | Weather condition code | 51 | Yes | `weather_code` |
| ingested_at_utc | TEXT | UTC, ISO 8601 `YYYY-MM-DDTHH:MM:SSZ` | When the pipeline run that last wrote this row started. It matches the timestamp in that run's raw file names, so each row can be traced to its raw file. | 2026-11-12T10:38:18Z | No | Added by `transform()` |

`latitude` and `longitude` are not loaded in Week 1. They describe the model grid cell and are the
same for every row of a city.

## Response fields not loaded

`generationtime_ms`, `utc_offset_seconds`, `timezone`, `timezone_abbreviation`, `elevation` (metres) and
`hourly_units` are kept in the raw files but not copied into the table. `timezone` and `utc_offset_seconds`
are the only record of which time zone `time` is in, which is one reason the raw files are kept.

## Processed table: `data/processed/weather_hourly/`

One row per city per hour. All times are stored in UTC; London time is derived from UTC.

| Column | Type | Unit | Description / rule |
|---|---|---|---|
| `city` | text | | City name from `config.yaml` |
| `observed_at_utc` | timestamp (UTC) | | The hour the reading is for; the main time key |
| `observed_at_local` | timestamp (Europe/London) | | The same moment in UK time (GMT in winter, BST in summer) |
| `temperature_c` | float | °C | Air temperature at 2 m |
| `feels_like_c` | float | °C | Apparent ("feels like") temperature |
| `humidity_pct` | integer | % | Relative humidity at 2 m |
| `precipitation_mm` | float | mm | Rain plus snow in the hour |
| `wind_speed_kmh` | float | km/h | Wind speed at 10 m |
| `weather_code` | integer | | WMO weather code from the API |
| `is_day` | integer | 0/1 | The API's daylight flag |
| `weather_description` | text | | From `reference/wmo_codes.csv`; `unknown` if the code is not listed |
| `weather_category` | text | | `clear`, `cloudy`, `fog`, `drizzle`, `rain`, `snow`, `storm` or `unknown` |
| `temperature_f` | float | °F | `temperature_c × 9/5 + 32` |
| `wind_speed_ms` | float | m/s | `wind_speed_kmh ÷ 3.6`, rounded to 2 decimals |
| `beaufort_scale` | integer | 0–12 | WMO lower bounds in m/s: 1 from 0.3, 2 from 1.6, 3 from 3.4, 4 from 5.5, 5 from 8.0, 6 from 10.8, 7 from 13.9, 8 from 17.2, 9 from 20.8, 10 from 24.5, 11 from 28.5, 12 from 32.7. A value exactly on a bound gets the higher force |
| `is_daylight` | boolean | | True when `is_day = 1` |
| `outdoor_work_risk` | text | | Checked in order. **high:** Beaufort ≥ 7, or category `storm`/`snow`, or precipitation ≥ 4 mm. **medium:** Beaufort ≥ 5, or precipitation ≥ 1 mm, or temperature ≤ 0 °C. Otherwise **low** |
| `source` | text | | `open_meteo_forecast` (from `run`) or `open_meteo_archive` (from `backfill`); part of the row's key |
| `ingested_at_utc` | timestamp (UTC) | | When the pipeline ran |