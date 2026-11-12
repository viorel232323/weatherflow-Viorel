"""Transform helpers shared by etl_v1.py and notebooks/01_explore.ipynb."""
import pandas as pd


def flatten(payload: dict, city_name: str) -> pd.DataFrame:
    """Turn one Open-Meteo response into a tidy table: one row per hour.

    The parallel lists under payload["hourly"] become columns. City name and the
    grid-cell coordinates Open-Meteo actually used are added to every row.
    """
    df = pd.DataFrame(payload["hourly"])
    df["city"] = city_name
    df["latitude"] = payload["latitude"]
    df["longitude"] = payload["longitude"]
    return df
