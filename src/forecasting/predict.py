"""
Price forecasting using Prophet.

Generates 6-month price forecasts for any geography in the database.
Prophet handles seasonality and trend changes automatically.

Usage:
    from src.forecasting.predict import forecast_prices
    result = forecast_prices("San Jose, CA", months=6)
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
from prophet import Prophet

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "housing.db"


def forecast_prices(
    geo_code: str,
    metric_type: str = "zhvi",
    months: int = 6,
    geo_type: str | None = None,
) -> dict:
    """Generate a price forecast for a geography.

    Args:
        geo_code: ZIP code or metro name
        metric_type: 'zhvi' or 'zori'
        months: Number of months to forecast
        geo_type: 'zip', 'metro', or 'national'. Auto-detected if None.

    Returns:
        dict with keys:
            historical: DataFrame with date, actual
            forecast: DataFrame with date, predicted, lower, upper
            metadata: dict with geo info and model details
    """
    conn = sqlite3.connect(DB_PATH)

    # Auto-detect geo_type
    if geo_type is None:
        if geo_code.isdigit() and len(geo_code) == 5:
            geo_type = "zip"
        elif geo_code == "United States":
            geo_type = "national"
        else:
            geo_type = "metro"

    # Fetch historical data
    df = pd.read_sql_query("""
        SELECT h.metric_date as ds, h.value as y
        FROM housing_metrics h
        JOIN geographies g ON g.geography_id = h.geography_id
        WHERE g.geo_code = ? AND g.geo_type = ? AND h.metric_type = ?
        ORDER BY h.metric_date
    """, conn, params=(geo_code, geo_type, metric_type))
    conn.close()

    if df.empty or len(df) < 24:
        return {
            "historical": pd.DataFrame(),
            "forecast": pd.DataFrame(),
            "metadata": {"error": f"Not enough data for {geo_code} (need 24+ months, have {len(df)})"},
        }

    df["ds"] = pd.to_datetime(df["ds"])

    # Fit Prophet model
    model = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=False,
        daily_seasonality=False,
        changepoint_prior_scale=0.05,
        seasonality_mode="multiplicative",
    )
    model.fit(df)

    # Generate future dates
    future = model.make_future_dataframe(periods=months, freq="MS")
    prediction = model.predict(future)

    # Split into historical and forecast periods
    last_date = df["ds"].max()
    historical = df.rename(columns={"ds": "date", "y": "actual"})

    forecast_df = prediction[prediction["ds"] > last_date][["ds", "yhat", "yhat_lower", "yhat_upper"]].copy()
    forecast_df.columns = ["date", "predicted", "lower", "upper"]

    # Also get the fitted values for the historical period
    fitted = prediction[prediction["ds"] <= last_date][["ds", "yhat"]].copy()
    fitted.columns = ["date", "fitted"]

    metadata = {
        "geo_code": geo_code,
        "geo_type": geo_type,
        "metric_type": metric_type,
        "data_points": len(df),
        "forecast_months": months,
        "last_actual_date": str(last_date.date()),
        "last_actual_value": float(df["y"].iloc[-1]),
        "forecast_end_value": float(forecast_df["predicted"].iloc[-1]) if not forecast_df.empty else None,
        "forecast_change_pct": (
            (float(forecast_df["predicted"].iloc[-1]) - float(df["y"].iloc[-1]))
            / float(df["y"].iloc[-1]) * 100
        ) if not forecast_df.empty else None,
    }

    return {
        "historical": historical,
        "fitted": fitted,
        "forecast": forecast_df,
        "metadata": metadata,
    }
