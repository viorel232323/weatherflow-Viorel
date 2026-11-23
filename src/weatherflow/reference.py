"""Reference data shipped with the package: lookup tables."""
from pathlib import Path

import pandas as pd

REFERENCE_DIR = Path(__file__).resolve().parent / "reference"


def read_wmo_codes(path: Path = REFERENCE_DIR / "wmo_codes.csv") -> pd.DataFrame:
    """Read the WMO lookup as columns weather_code, weather_description, weather_category."""
    codes = pd.read_csv(path, encoding="utf-8")
    codes = codes.rename(columns={"code": "weather_code",
                                  "description": "weather_description",
                                  "category": "weather_category"})
    codes["weather_code"] = codes["weather_code"].astype("Int64")
    return codes