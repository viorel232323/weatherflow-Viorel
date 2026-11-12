# Reference project critique: WeatherFlow-DataEngineering

**Repo studied:** https://github.com/SyedRoshanAli/WeatherFlow-DataEngineering (branch `main`, last push 31 May 2025)
**Read:** `README.md`, `IMPLEMENTATION.md`, `weather_flow/docs/architecture.txt`, `docker/docker-compose.yml`,
the Airflow DAG, the Kafka producer and consumer, the Spark job, `scripts/config.py`, `scripts/weather_api.py`,
the dashboard and the tests. I read the code and did not run the project.

Architecture diagram: [reference_architecture.md](reference_architecture.md)

## Component table

| Component | Tool used | What it does in this project | Batch or streaming? |
|-----------|-----------|------------------------------|---------------------|
| Data source | WeatherAPI, OpenWeatherMap (plus a weather-station simulator) | REST APIs that return the current weather for one city per call. `scripts/weather_api.py` calls them for New York, London, Tokyo, Berlin and Mexico City and saves each response as JSON. | Batch (polled on a timer) |
| Message broker | Kafka (with Zookeeper and the Kafdrop UI) | `kafka/scripts/simple_producer.py` fetches all cities every 5 minutes and publishes each reading to the topic `weather-raw-data`. `simple_consumer.py` reads the topic, adds °F, a heat index and a processed timestamp, and writes one JSON file per message to `data/processed/`. | Streaming |
| Processing | Spark (PySpark) | `spark/scripts/weather_processor.py` reads the JSON files, adds derived metrics (heat index, weather severity) and writes Parquet and JSON. It runs with `local[*]`, not on the `spark-master` container, and its streaming function is commented out in `main()`. | Batch (streaming code is disabled) |
| Orchestration | Airflow | DAG `weather_flow_pipeline` runs every hour: create folders → fetch weather → wait for raw files → process with **pandas** (not Spark) → generate reports → delete files older than 30 days. Retries once after 5 minutes. | Batch (hourly) |
| Storage | Files on a Docker volume (JSON, CSV, Parquet) in raw and processed zones; PostgreSQL 13 | The "data lake" is plain folders: `data/raw/` and `data/processed/`. PostgreSQL only stores Airflow's own metadata, so no weather data goes into a database. | Batch |
| Serving | Dash on Flask (`dashboard/app.py`, port 8051), plus a separate Streamlit app (`streamlit_dashboard.py`, port 8501) | The dashboard finds processed JSON files with `glob`, loads them with pandas and draws Plotly charts. Users can add a city from the UI. | Batch (reads files when the page refreshes) |
| Packaging | Docker Compose | `docker/docker-compose.yml` starts 10 containers: zookeeper, kafka, spark-master, spark-worker, airflow, weather-producer, weather-consumer, kafka-ui, dashboard and postgres. | Not applicable |

## Critique

**What the design does well.** Each stage has its own folder (`kafka/`, `spark/`, `airflow/`, `dashboard/`), so
it is easy to find the code for each tool. Raw and processed data are kept apart, and raw file names carry
source, city and timestamp (`weatherapi_london_20250516_203717.json`). The DAG has retries and a 30-day clean-up
task, and a single `docker-compose up` starts the whole stack.

**Problems and risks.**

1. **A secret is committed in plain text.** A live WeatherAPI key appears four times in `README.md`, in
   `IMPLEMENTATION.md`, in `docker-compose.yml` (line 129), in `streamlit_dashboard.py` (line 368) and as the
   fallback default in `scripts/weather_api.py` (line 27). A `.env.template` exists, so the authors knew the
   right pattern but did not use it. The key should be revoked and read only from an untracked `.env` file.
2. **The documentation disagrees with itself and with the code.** The README calls the dashboard Flask,
   `IMPLEMENTATION.md` says Dash/Flask, and the README also launches Streamlit on port 8501. `config.py` names
   the topic `weather-raw` and lists 10 cities, but the producer uses `weather-raw-data` and 5 cities. The README
   tree puts raw data in `data/`, but the files sit in `airflow/dags/data/raw/`.
3. **The orchestrator cannot load.** `weather_pipeline_dag.py` passes `python_callable=fetch_weather_data`, but
   only `fetch_weather_data_wrapper` is defined, so the DAG fails with a `NameError`. A byte-identical
   `weather_pipeline_dag_updated.py` reuses the same `dag_id`.
4. **Data is committed to Git.** `.gitignore` lists `data/raw/`, which only matches a top-level folder, so 194
   raw and processed data files under `weather_flow/` went into the repo.
5. **Nobody would know if it broke.** `email_on_failure` is `False`, API calls have no `timeout`, and there
   are no data quality checks. The tests cover `utils.py` and the simulator only, with nothing for Kafka,
   Spark, the DAG or the dashboard.

**Essential vs overkill for a 5-city hourly feed.** Five cities × 24 hours is 120 rows a day, which pandas
handles in milliseconds. *Essential:* API extraction with raw landing, a tested transform, a real database,
a scheduler, a simple dashboard and alerts. *Overkill:* Kafka and Spark. Kafka exists for high-volume event
streams with many consumers, and Spark for data too big for one machine. The weather changes hourly, so
polling every 5 minutes adds duplicates, not freshness. The project shows this itself: Spark runs locally,
streaming is commented out and the DAG says "Process data with Python instead of Spark". Docker is worth
keeping so the project runs anywhere, but with three containers rather than ten.
