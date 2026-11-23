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
python -m weatherflow run
```

This one command extracts the last day plus the next day of hourly weather (in UTC) for the five
cities in `config.yaml`, saves each response unchanged to `data/raw/<YYYY-MM-DD>/`, cleans it,
and loads it into `data/weather.db`. Every step is logged to the screen and to `logs/pipeline.log`.

- **Settings** (API URLs, cities, paths, retries) live in `config.yaml`, not in the code.
- **Retries:** timeouts, connection errors and 5xx answers are retried after 1 s, 2 s and 4 s;
  4xx answers are not retried.
- **Exit code:** `0` when every city loads, `1` if any city fails, so a scheduler can see failures.
- **Re-running is safe:** a row for an existing `(city, observed_at_utc)` replaces the old one,
  so running twice gives the same row count.

`etl_v1.py` is the Week 1 version, kept for history.

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
