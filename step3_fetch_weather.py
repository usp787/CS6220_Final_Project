"""
Step 3 — Fetch Weather Data
Pulls weather aligned with the sales date range (Jan–Mar 2026) plus a 14-day
forecast window (Mar 28 – Apr 10 2026).

If the environment variable OPENWEATHER_API_KEY is set, the script will attempt
a live call to the OpenWeather One Call API 3.0.  Otherwise it generates
realistic synthetic weather data for Boston (useful for development/demo).
"""
import os
import pandas as pd
import numpy as np
from pathlib import Path

Path("data").mkdir(exist_ok=True)
API_KEY = os.environ.get("OPENWEATHER_API_KEY", "")

# ─── Synthetic weather generator ─────────────────────────────────────────────
def make_synthetic_weather(start: str, end: str, seed: int = 42) -> pd.DataFrame:
    """
    Boston-like daily weather for Jan–Apr 2026.
    Temperature rises from ~-5 °C in Jan to ~12 °C in Apr.
    Precipitation events occur ~30 % of days.
    """
    np.random.seed(seed)
    dates = pd.date_range(start, end, freq="D")
    n = len(dates)
    idx = np.arange(n)

    # Gentle warming trend + daily noise
    temp_avg  = -5 + 17 * (idx / max(n - 1, 1)) + np.random.normal(0, 2.8, n)
    temp_min  = temp_avg - np.random.uniform(2.5, 5.5, n)
    temp_max  = temp_avg + np.random.uniform(2.5, 5.5, n)

    # Precipitation: Poisson-like with 30 % occurrence
    rain_mask = np.random.rand(n) < 0.30
    precip    = np.where(rain_mask, np.random.exponential(4.5, n), 0.0)

    conditions = [
        "Heavy Rain/Snow" if p > 8
        else "Light Rain/Snow" if p > 1.5
        else "Cloudy" if np.random.rand() < 0.4
        else "Clear"
        for p in precip
    ]

    return pd.DataFrame({
        "date":          dates.strftime("%Y-%m-%d"),
        "temp_avg":      np.round(temp_avg,  1),
        "temp_min":      np.round(temp_min,  1),
        "temp_max":      np.round(temp_max,  1),
        "precipitation": np.round(precip,    1),
        "condition":     conditions,
        "source":        "synthetic",
    })


# ─── Attempt live API call (graceful fallback) ───────────────────────────────
def fetch_openweather(api_key: str, lat: float, lon: float,
                      start: str, end: str) -> pd.DataFrame | None:
    """
    Attempt to pull daily weather from OpenWeather One Call API 3.0.
    Returns a DataFrame on success, None on any error.
    """
    try:
        import requests
        rows = []
        for ts in pd.date_range(start, end, freq="D"):
            unix_ts = int(ts.timestamp())
            url = (
                f"https://api.openweathermap.org/data/3.0/onecall/timemachine"
                f"?lat={lat}&lon={lon}&dt={unix_ts}&units=metric&appid={api_key}"
            )
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                print(f"  API error {resp.status_code} for {ts.date()}, falling back.")
                return None
            d = resp.json().get("data", [{}])[0]
            rows.append({
                "date":          ts.strftime("%Y-%m-%d"),
                "temp_avg":      round(d.get("temp", float("nan")), 1),
                "temp_min":      round(d.get("temp", float("nan")), 1),
                "temp_max":      round(d.get("temp", float("nan")), 1),
                "precipitation": round(d.get("rain", {}).get("1h", 0) * 24, 1),
                "condition":     d.get("weather", [{}])[0].get("description", ""),
                "source":        "openweather",
            })
        return pd.DataFrame(rows)
    except Exception as exc:
        print(f"  Live API call failed: {exc}")
        return None


# ─── Main ─────────────────────────────────────────────────────────────────────
HIST_START, HIST_END = "2026-01-01", "2026-03-27"
FCAST_START, FCAST_END = "2026-03-28", "2026-04-10"

if API_KEY:
    print("OPENWEATHER_API_KEY found — attempting live API pull …")
    # Boston: 42.36, -71.06
    hist_df  = fetch_openweather(API_KEY, 42.36, -71.06, HIST_START, HIST_END)
    fcast_df = fetch_openweather(API_KEY, 42.36, -71.06, FCAST_START, FCAST_END)
    if hist_df is None or fcast_df is None:
        print("Falling back to synthetic data.")
        hist_df  = make_synthetic_weather(HIST_START,  HIST_END,  seed=42)
        fcast_df = make_synthetic_weather(FCAST_START, FCAST_END, seed=99)
else:
    print("No API key found — using synthetic weather data (Boston, Jan–Apr 2026).")
    hist_df  = make_synthetic_weather(HIST_START,  HIST_END,  seed=42)
    fcast_df = make_synthetic_weather(FCAST_START, FCAST_END, seed=99)

weather = pd.concat([hist_df, fcast_df], ignore_index=True)

print(f"\nWeather records: {len(weather)}")
print(f"Date range     : {weather['date'].min()} → {weather['date'].max()}")
print(f"Temp range     : {weather['temp_avg'].min():.1f} °C → {weather['temp_avg'].max():.1f} °C")
print(f"Rainy days     : {(weather['precipitation'] > 0).sum()} "
      f"({(weather['precipitation'] > 0).mean()*100:.0f} %)")
print(f"Source         : {weather['source'].iloc[0]}")
print("\nSample rows:")
print(weather.head(10).to_string(index=False))

weather.to_csv("data/weather.csv", index=False)
print("\nSaved → data/weather.csv")
