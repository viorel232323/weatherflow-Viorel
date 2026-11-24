# WeatherFlow: hourly weather pipeline for five UK cities

**Author:** Viorel Grozea  LSA Data Engineering Internship, November 2026

## Goal

A regional events company plans outdoor work in five UK cities: London, Manchester,
Birmingham, Edinburgh and Cardiff. Its planners need hourly weather they can trust,
refreshed automatically, with a dashboard that flags risky conditions. This project
builds that pipeline step by step. One command pulls live weather for the
five cities from the free Open-Meteo API, saves the raw responses unchanged, cleans
them, and loads them into a SQLite database that can be queried with SQL.

## Install the dependencies and the package:

   ```sh
   pip install -r requirements-dev.txt
   pip install -e .        # required: makes the src/ package importable
   ```

## How to run the pipeline

With the virtual environment active, from any folder:

```sh
python -m weatherflow run                     # incremental: only the new hours, plus the forecast
python -m weatherflow backfill --days 30      # history: the 30 days ending 5 days ago
python -m weatherflow backfill --start-date 2026-10-01 --end-date 2026-10-07
```

**`run` (incremental).** For each city it reads a **watermark**: the latest hour already loaded that
has actually happened (`observed_at_utc <= now`, so loaded forecast hours don't count). It then asks the
forecast API for the hours from **2 hours before** the earliest watermark up to 23:00 today, so new hours
are added and the forecast is refreshed. The 2-hour overlap catches late corrections, and the upsert makes
the overlap harmless. With an empty database it falls back to `past_days: 1` (yesterday 00:00 onwards).

**`backfill` (history).** Uses the Open-Meteo **archive** API, which runs about 5 days behind real time,
so by default it ends 5 days ago. It asks for 7 days per request per city (with a 1 s pause), saves every
chunk unchanged, and loads the rows with `source = open_meteo_archive`.

Both commands use the **same** transform -> validate -> load code. Every response is saved unchanged to
`data/raw/<YYYY-MM-DD>/`, rows go to `data/weather.db`, and every step is logged to the screen and to
`logs/pipeline.log`, including the requested hours and how many rows were **new vs updated**.

- **Settings** (API URLs, cities, paths, retries, overlap, chunk size) live in `config.yaml`, not in the code.
- **Retries:** timeouts, connection errors and 5xx answers are retried after 1 s, 2 s and 4 s;
  4xx answers are not retried.
- **Data quality:** every city must have every requested hour (`days × 24` for a backfill), or nothing is loaded.
- **Exit code:** `0` on success, `1` if a city or a blocking check fails, so a scheduler can see failures.
- **Re-running is safe:** rows are upserted on `(city, observed_at_utc, source)`, so a re-run updates rows
  instead of adding them.

| Evidence (24 Nov 2026) | Result |
|---|---|
| `backfill --days 30`, run twice | 3,600 rows (30 days × 24 h × 5 cities): 3,600 new, then 0 new and 3,600 updated |
| `run` after the previous day's load | requested 23 Nov 21:00 to 24 Nov 23:00 (27 h per city): 120 new, 15 updated |
| `run` again a minute later | requested 24 Nov 10:00 to 23:00 (14 h per city): 0 new, 70 updated |

`etl_v1.py` kept for history.

## How to run the tests

```sh
python -m pytest                                        # 99 tests, about 3 seconds
python -m pytest --cov=src --cov-report=term-missing    # the same, plus coverage
```

The tests never call the real API and never touch `data/`. The API is faked with `monkeypatch`,
and every file and database is written to a temporary folder (`tmp_path`).

| File | What it proves |
|---|---|
| `tests/test_transform.py` | unit conversions, the WMO lookup, Beaufort and outdoor-work-risk boundaries |
| `tests/test_validate.py` | bad rows are quarantined with a reason; duplicates or missing hours block the load |
| `tests/test_extract.py` | 5xx and timeouts are retried after 1 s, 2 s, 4 s; 4xx is not; one failing city doesn't stop the others |
| `tests/test_load.py` | loading twice keeps 240 rows; a failed load saves nothing (one transaction) |
| `tests/test_pipeline.py` | end to end: a good run returns 0 and loads 240 rows; bad data returns 1 and loads nothing |
| `tests/test_config_and_cli.py` | a broken `config.yaml` names the missing key; the command returns the pipeline's exit code | 
| `tests/test_incremental_and_backfill.py` | the watermark ignores future forecast hours; the window starts 2 h earlier; a 30-day backfill loads 3,600 rows twice with no change |

**Coverage:** 99% of `src/weatherflow` (99 tests).

## How to query the data

```sh
python run_sql.py                 # runs sql/week1_queries.sql and prints each result as a table
python -m sqlite3 weather.db "SELECT city, COUNT(*) FROM weather_hourly GROUP BY city;"
```

`python -m sqlite3` is SQLite's shell built into Python 3.12+, so the separate `sqlite3` tool is not
needed. Any SQLite client (DataGrip, DB Browser for SQLite) can also open `weather.db`.

## Project layout

```
weatherflow-viorel/
├── README.md
├── .gitignore
├── requirements.txt
├── extract.py            E: call Open-Meteo, land raw JSON 
├── transform_utils.py    flatten(): nested JSON -> tidy table, shared by the notebook and the ETL
├── etl_v1.py             E -> T -> L into SQLite in one command 
├── run_sql.py            prints the results of a .sql file as tables
├── data/                 raw JSON (created by the pipeline, ignored by Git)
├── weather.db            SQLite database (created by the pipeline, ignored by Git)
├── docs/
│   ├── reference_architecture.md / .png   diagram of the reference project, E/T/L labelled
│   ├── reference_critique.md              component table and critique
│   ├── data_dictionary.md                 every column, units and grain
│   ├── figures/temperature_by_city.png    chart from the exploration notebook
│   └── reflections/week_1.md              weekly reflection
├── notebooks/
│   └── 01_explore.ipynb  profiling of the raw data and 6 findings 
└── sql/
    └── week1_queries.sql 3 commented business queries and a duplicate check
```

## Troubleshooting

- **`CERTIFICATE_VERIFY_FAILED` when calling the API.** Some antivirus tools
  and company proxies. `extract.py` calls
  `truststore.inject_into_ssl()` so Python uses the operating system's certificate store, which
  already trusts that certificate. Verification stays on.
- **The notebook shows an old pandas version.** Start Jupyter from the activated `.venv`
  (`jupyter lab` or `jupyter nbconvert ...`), or pick the `.venv` interpreter in VS Code. The first
  cell prints the Python path and pandas version so you can check.

## Data source and licence

Weather data by [Open-Meteo.com](https://open-meteo.com/), licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
