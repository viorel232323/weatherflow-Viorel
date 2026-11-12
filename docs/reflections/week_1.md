## What I built

- A reproducible project: virtual environment, pinned `requirements.txt` (checked on a fresh clone),
  `.gitignore` that keeps `.venv/`, `data/`, `.env` and `*.db` out of Git.
- A reading of the reference WeatherFlow repo: component table, E/T/L diagram and a critique with five
  problems backed by file and line evidence.
- `extract.py`, which lands raw Open-Meteo JSON for 5 UK cities in `data/raw/<date>/`, with UTC
  timestamps, a 10-second timeout and per-city error handling.
- `notebooks/01_explore.ipynb` (profiling, chart, 6 findings) and `docs/data_dictionary.md`.
- `etl_v1.py`: one command runs extract → transform → load into SQLite, and re-running gives the same
  row count. Three business queries in `sql/week1_queries.sql`.

## What went well

- Re-running the pipeline is safe, and I can prove it: two runs in a row both leave 240 rows with
  240 distinct `(city, observed_at)` keys.
- Every row can be traced back to its raw file through `ingested_at_utc`.

## What was hard, and how I solved it

1. **HTTPS failed on my PC.** `requests` raised `CERTIFICATE_VERIFY_FAILED` because my antivirus
   re-signs HTTPS traffic. The fix was `truststore`, which makes Python use the Windows certificate
   store, so verification stays on. `verify=False` would have hidden the problem and removed the
   protection.
2. **`requirements.txt` would only have worked on Windows.** `pip freeze` pinned `pywinpty`, which
   does not exist on Mac or Linux. I added the marker `; sys_platform == "win32"`.
3. **The notebook ran on the wrong Python.** Calling `jupyter` without activating `.venv` picked up
   Anaconda's Jupyter, so the notebook used pandas 2.2 instead of the pinned 3.1. Now the first cell
   prints the Python path and pandas version.
4. **The second ETL run crashed** with `UNIQUE constraint failed`. The primary key did its job, and the
   transaction rolled back so no half-loaded data was left. `INSERT OR REPLACE` made the load idempotent.

## What surprised me

- The forecast for the same hour changed between two runs ten minutes apart (Edinburgh, 12:00 today,
  wind 19.1 → 19.8 km/h). "Keep the latest" is a real rule, not a formality.
- Open-Meteo snaps coordinates to its model grid, so the latitude and longitude it returns are not the
  ones I sent.
- The reference project commits an API key in plain text in at least six files, and its Airflow DAG
  cannot even be imported.

