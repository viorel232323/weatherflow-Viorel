# WeatherFlow: hourly weather pipeline for five UK cities

**Author:** Viorel Grozea  LSA Data Engineering Internship, November 2026

## Goal

A regional events company plans outdoor work in five UK cities: London, Manchester,
Birmingham, Edinburgh and Cardiff. Its planners need hourly weather they can trust,
refreshed automatically, with a dashboard that flags risky conditions. This project
builds that pipeline step by step. One command pulls live weather for the
five cities from the free Open-Meteo API, saves the raw responses unchanged, cleans
them, and loads them into a SQLite database that can be queried with SQL.

## How to set up

You need Python 3.11 or newer and Git.

1. Clone the repository and go into it:

   ```sh
   git clone https://github.com/viorel232323/weatherflow-Viorel.git
   cd weatherflow-viorel
   ```

2. Create and activate a virtual environment:

   ```sh
   python -m venv .venv
   # Windows PowerShell:  .venv\Scripts\Activate.ps1
   # Mac/Linux:           source .venv/bin/activate
   ```

   If PowerShell blocks the activate script, run
   `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or use Git Bash.

3. Install the pinned dependencies:

   ```sh
   pip install -r requirements.txt
   ```

No API key is needed: Open-Meteo is free for non-commercial use.

## How to run the pipeline

With the virtual environment active, from the repo root:

```sh
python etl_v1.py
```

This one command:

1. **Extracts:** calls Open-Meteo for each city  and saves each
   response, unchanged, to `data/raw/<YYYY-MM-DD>/<city>_<YYYYMMDDTHHMMSS>.json`
2. **Transforms:** flattens the JSON into one row per city per hour, converts `time` to a datetime,
   renames columns to `snake_case` with units, adds `ingested_at_utc` and drops duplicates.
3. **Loads:** writes the rows into the table `weather_hourly` in `weather.db` (SQLite), using
   `INSERT OR REPLACE` on the primary key `(city, observed_at)`.

Example output:

```
WeatherFlow ETL v1  run at 2026-11-12 10:38:18 UTC
[1/3] Extract
  OK      London      48 hourly records -> data\raw\2026-11-12\london_20261112T103818.json
  OK      Manchester  48 hourly records -> data\raw\2026-11-12\manchester_20261112T103818.json
  OK      Birmingham  48 hourly records -> data\raw\2026-11-12\birmingham_20261112T103818.json
  OK      Edinburgh   48 hourly records -> data\raw\2026-11-12\edinburgh_20261112T103818.json
  OK      Cardiff     48 hourly records -> data\raw\2026-11-12\cardiff_20261112T103818.json
Extract finished: 5 of 5 cities landed.
[2/3] Transform
  240 rows after cleaning (5 cities)
[3/3] Load
Loaded 240 rows into weather.db, table weather_hourly

Rows per city now in the table:
      city  rows       first_hour        last_hour
Birmingham    48 2026-11-11T00:00 2026-11-12T23:00
   Cardiff    48 2026-11-11T00:00 2026-11-12T23:00
 Edinburgh    48 2026-11-11T00:00 2026-11-12T23:00
    London    48 2026-11-11T00:00 2026-11-12T23:00
Manchester    48 2026-11-11T00:00 2026-11-12T23:00

```

Options:

```sh
python etl_v1.py --cities London Cardiff   # only some cities
python etl_v1.py --db test.db              # a different database file
python extract.py                          # extract only: land raw JSON, no database
```

**Re-running is safe.** Running the pipeline twice in a row gives the same row count, because a row
for an existing `(city, observed_at)` replaces the old one. The count only grows when a new day comes
into the 48-hour window, by 24 rows per city. If one city fails (for example a network error), the
others are still extracted and loaded, and the error is printed with the API's reason.

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
