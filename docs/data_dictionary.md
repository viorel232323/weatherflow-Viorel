# Data dictionary: hourly weather for five UK cities

## About this data

| Item | Value |
|------|-------|
| Source | Open-Meteo Forecast API, `https://api.open-meteo.com/v1/forecast` (docs: https://open-meteo.com/en/docs) |
| Request | `hourly=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,wind_speed_10m,weather_code`, `past_days=1`, `forecast_days=1`, `timezone=Europe/London` |
| Cities | London, Manchester, Birmingham, Edinburgh, Cardiff (coordinates from the Open-Meteo Geocoding API, stored in `extract.py`) |
| Licence | Open-Meteo data is licensed under **CC BY 4.0**: free to use, including commercially, with attribution to Open-Meteo.com |
| Refresh frequency | Week 1: each time `extract.py` or `etl_v1.py` is run (planned hourly from Week 3). Open-Meteo updates its data as new weather-model runs arrive, several times a day. |
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

## Response fields not loaded

`generationtime_ms`, `utc_offset_seconds`, `timezone`, `timezone_abbreviation`, `elevation` (metres) and
`hourly_units` are kept in the raw files but not copied into the table. `timezone` and `utc_offset_seconds`
are the only record of which time zone `time` is in, which is one reason the raw files are kept.
