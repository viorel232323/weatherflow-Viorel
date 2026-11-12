# Reference architecture: WeatherFlow-DataEngineering

How data flows from the weather APIs to the dashboard in the reference repo, based on reading the code.
Each stage is labelled **E** (extract), **T** (transform) or **L** (load). "Serve" is the read side that
uses the loaded data. A PNG version of the same diagram is in
[reference_architecture.png](reference_architecture.png).

```mermaid
flowchart LR
  subgraph SRC["Sources"]
    WA["WeatherAPI"]
    OW["OpenWeatherMap"]
    SIM["Simulated stations"]
  end

  subgraph STREAM["Streaming path: weather-producer and weather-consumer containers"]
    ING["E  scripts/weather_api.py<br/>calls the APIs for 5 cities"]
    PROD["E  Kafka producer<br/>simple_producer.py, every 5 min"]
    TOPIC[("Kafka topic<br/>weather-raw-data")]
    CONS["T  Kafka consumer<br/>simple_consumer.py<br/>adds °F, heat index, timestamp"]
  end

  subgraph BATCH["Batch path: Airflow DAG weather_flow_pipeline, hourly"]
    FETCH["E  fetch_weather_data task"]
    PROCPY["T  process_weather_data.py<br/>pandas, not Spark"]
    REP["L  generate_reports.py<br/>CSV, HTML, PNG reports"]
  end

  RAW[("E  Raw zone<br/>data/raw/*.json")]
  SPARK["T  Spark job<br/>spark/scripts/weather_processor.py<br/>batch, local[*]"]
  PROC[("L  Processed zone<br/>data/processed/*.json, *.parquet")]
  DASH["Serve  Dash/Flask dashboard<br/>dashboard/app.py, port 8051"]
  PG[("PostgreSQL<br/>Airflow metadata only")]

  WA --> ING
  OW --> ING
  SIM --> ING
  ING --> RAW
  ING --> PROD --> TOPIC --> CONS --> PROC
  WA --> FETCH
  OW --> FETCH
  FETCH --> RAW
  RAW --> PROCPY --> PROC
  RAW --> SPARK --> PROC
  TOPIC -. "streaming mode is<br/>commented out" .-> SPARK
  PROC --> REP
  PROC --> DASH
  BATCH -. "DAG state" .- PG
```

## Reading the diagram

| Label | Stage | In this repo |
|-------|-------|--------------|
| **E** | Extract | `weather_api.py` calls the APIs and lands each response as a raw JSON file; the producer also pushes it onto Kafka. |
| **T** | Transform | Three separate transforms: the Kafka consumer, the Spark batch job and the pandas script run by Airflow. |
| **L** | Load | Results are written as files to the processed zone; reports are written from there. No weather data reaches a database. |
| Serve | Read side | The Dash dashboard reads the processed JSON files directly. |

Docker Compose packages every box above as one of 10 containers.

Two things stand out once it is drawn. First, there are three transform paths that do much the same work,
and nothing says which one is the source of truth. Second, the Kafka branch only feeds JSON files on disk,
which the batch path writes too, so the streaming layer adds no capability for an hourly feed.
