# WeatherFlow: hourly weather pipeline for five UK cities

**Author:** Viorel Grozea · LSA Data Engineering Internship, November 2026

## Goal

A regional events company plans outdoor work in five UK cities: London, Manchester,
Birmingham, Edinburgh and Cardiff. Its planners need hourly weather they can trust,
refreshed automatically, with a dashboard that flags risky conditions. This project
builds that pipeline step by step. In Week 1, one command pulls live weather for the
five cities from the free Open-Meteo API, saves the raw responses unchanged, cleans
them, and loads them into a SQLite database that can be queried with SQL.

## How to set up

You need Python 3.11 or newer and Git.

1. Clone the repository and go into it:

   ```sh
   git clone <your-repo-url>
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

## Project layout

```
weatherflow-viorel/
├── README.md
├── .gitignore
├── requirements.txt
├── data/            raw and processed data (created by the pipeline, ignored by Git)
├── docs/            architecture notes, critique, data dictionary
├── notebooks/       exploration notebooks
└── sql/             SQL queries
```
