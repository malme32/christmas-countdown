#!/usr/bin/env python3
"""A tiny, dependency-free Christmas countdown web app.

Serves a page with a countdown widget that shows how many *working days*
(Monday-Friday) remain until Christmas Day, alongside the remaining calendar
time. It also exposes the same numbers as JSON. Built only on the Python
standard library.

Working days exclude weekends but do **not** exclude public holidays, so the
result is deterministic and needs no data files or network access.

Usage:
    python3 christmas_countdown.py
    python3 christmas_countdown.py --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
CHRISTMAS_MONTH = 12
CHRISTMAS_DAY = 25
WORKING_WEEKDAYS = 5

# Weather constants
WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"
WEATHER_CACHE_TTL = 600  # 10 minutes in seconds
WEATHER_DEFAULT_LAT = 37.9838  # Athens, Greece
WEATHER_DEFAULT_LON = 23.7275
WEATHER_FORECAST_DAYS = 16  # Open-Meteo serves at most 16 daily forecast days
WEATHER_SOURCE = "open-meteo"

# WMO Weather interpretation codes (https://open-meteo.com/en/docs)
WEATHER_CODES: dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}

TodayProvider = Callable[[], date]


def next_christmas(today: date) -> date:
    """Return the next Christmas Day on or after ``today``.

    On Christmas Day itself the target is that day, giving a count of zero; on
    any later day the target rolls forward to the following year.
    """
    target = date(today.year, CHRISTMAS_MONTH, CHRISTMAS_DAY)
    if today > target:
        target = date(today.year + 1, CHRISTMAS_MONTH, CHRISTMAS_DAY)
    return target


def is_working_day(day: date) -> bool:
    """Return ``True`` when ``day`` is a Monday-Friday working day."""
    return day.weekday() < WORKING_WEEKDAYS


def working_days_between(start: date, end: date) -> int:
    """Count working days strictly after ``start`` up to and including ``end``.

    Returns ``0`` when ``end`` is not after ``start``.
    """
    if end <= start:
        return 0
    count = 0
    day = start + timedelta(days=1)
    while day <= end:
        if is_working_day(day):
            count += 1
        day += timedelta(days=1)
    return count


def weekend_days_between(start: date, end: date) -> int:
    """Count Saturday/Sunday days strictly after ``start`` up to ``end``."""
    if end <= start:
        return 0
    count = 0
    day = start + timedelta(days=1)
    while day <= end:
        if not is_working_day(day):
            count += 1
        day += timedelta(days=1)
    return count


def countdown_summary(today: date | None = None) -> dict[str, object]:
    """Return the countdown values for ``today`` (defaults to the current date).

    The returned mapping is JSON-serialisable and is shared by the HTML widget
    and the JSON endpoint.
    """
    if today is None:
        today = date.today()
    target = next_christmas(today)
    calendar_days = (target - today).days
    working_days = working_days_between(today, target)
    return {
        "today": today.isoformat(),
        "target": target.isoformat(),
        "calendar_days": calendar_days,
        "working_days": working_days,
        "weekend_days": weekend_days_between(today, target),
        "weeks": calendar_days // 7,
        "is_christmas": today == target,
    }


class WeatherCache:
    """Thread-safe weather cache with TTL using ``threading.Lock()``.

    Stores weather data keyed by (latitude, longitude) with a configurable
    time-to-live. The lock ensures safe concurrent access from multiple
    threads.
    """

    def __init__(self, ttl: int = WEATHER_CACHE_TTL) -> None:
        self._cache: dict[tuple[float, float], tuple[float, dict]] = {}
        self._ttl = ttl
        self._lock = threading.Lock()

    def get(self, lat: float, lon: float) -> dict | None:
        """Return cached weather data if still valid, else ``None``."""
        key = (lat, lon)
        with self._lock:
            if key in self._cache:
                timestamp, data = self._cache[key]
                if time.time() - timestamp < self._ttl:
                    return data
                del self._cache[key]
        return None

    def set(self, lat: float, lon: float, data: dict) -> None:
        """Store weather data with the current timestamp."""
        key = (lat, lon)
        with self._lock:
            self._cache[key] = (time.time(), data)

    def clear(self) -> None:
        """Remove all cached entries."""
        with self._lock:
            self._cache.clear()


_weather_cache = WeatherCache()


def translate_weather_code(code: int) -> str:
    """Translate a WMO weather code to a human-readable description.

    Returns the description string for known codes, or "Unknown" for
    unrecognized codes.
    """
    return WEATHER_CODES.get(code, "Unknown")


def datetime_now_utc_iso() -> str:
    """Return the current UTC time as an ISO-8601 string for payload metadata."""
    return datetime.now(timezone.utc).isoformat()


def _dominant_weather_code(codes: list[int]) -> int | None:
    """Return the most frequent weather code (mode); ties go to the first seen."""
    if not codes:
        return None
    counts: dict[int, int] = {}
    for code in codes:
        counts[code] = counts.get(code, 0) + 1
    top = max(counts.values())
    for code in codes:
        if counts[code] == top:
            return code
    return codes[0]


def _parse_daily_forecast(payload_daily: object) -> list[dict]:
    """Normalise the Open-Meteo ``daily`` block into a list of per-day dicts.

    Returns an empty list when the block is missing or malformed, so callers
    still get current conditions even if the forecast section is unusable.
    """
    if not isinstance(payload_daily, dict):
        return []
    times = payload_daily.get("time")
    if not isinstance(times, list) or not times:
        return []

    def column(name: str) -> list:
        values = payload_daily.get(name)
        return list(values) if isinstance(values, list) else []

    codes = column("weathercode")
    temp_max = column("temperature_2m_max")
    temp_min = column("temperature_2m_min")
    precip_sum = column("precipitation_sum")
    precip_prob = column("precipitation_probability_max")
    wind_max = column("windspeed_10m_max")

    daily: list[dict] = []
    for i, day in enumerate(times):
        if not isinstance(day, str):
            continue
        code = codes[i] if i < len(codes) and isinstance(codes[i], int) else None
        entry: dict = {"date": day}
        entry["weathercode"] = code
        entry["description"] = translate_weather_code(code) if code is not None else "Unknown"
        entry["temp_max"] = temp_max[i] if i < len(temp_max) else None
        entry["temp_min"] = temp_min[i] if i < len(temp_min) else None
        entry["precipitation_sum"] = precip_sum[i] if i < len(precip_sum) else None
        entry["precipitation_probability"] = precip_prob[i] if i < len(precip_prob) else None
        entry["windspeed_max"] = wind_max[i] if i < len(wind_max) else None
        daily.append(entry)
    return daily


def aggregate_weekly(daily: list[dict]) -> list[dict]:
    """Aggregate daily entries into 7-day week summaries.

    Each summary has ``week_start``, ``days``, ``temp_avg`` (mean of the daily
    mid-temperatures), ``precipitation_total`` and the dominant weather code
    with its human-readable ``description``.
    """
    weeks: list[dict] = []
    for start in range(0, len(daily), 7):
        chunk = daily[start : start + 7]
        mids = [
            (day["temp_max"] + day["temp_min"]) / 2
            for day in chunk
            if isinstance(day.get("temp_max"), (int, float))
            and isinstance(day.get("temp_min"), (int, float))
        ]
        precip = sum(
            day["precipitation_sum"]
            for day in chunk
            if isinstance(day.get("precipitation_sum"), (int, float))
        )
        codes = [day["weathercode"] for day in chunk if isinstance(day.get("weathercode"), int)]
        dominant = _dominant_weather_code(codes)
        weeks.append(
            {
                "week_start": chunk[0].get("date"),
                "days": len(chunk),
                "temp_avg": round(sum(mids) / len(mids), 1) if mids else None,
                "precipitation_total": round(precip, 1),
                "weather_dominant": dominant,
                "description": translate_weather_code(dominant)
                if dominant is not None
                else "Unknown",
            }
        )
    return weeks


def aggregate_monthly(daily: list[dict]) -> list[dict]:
    """Aggregate daily entries by calendar month (``YYYY-MM``).

    Each summary has ``month``, ``days``, ``temp_avg``, ``precipitation_total``
    and the dominant weather code with its ``description``.
    """
    buckets: dict[str, list[dict]] = {}
    for day in daily:
        raw_date = day.get("date")
        month = raw_date[:7] if isinstance(raw_date, str) and len(raw_date) >= 7 else "unknown"
        buckets.setdefault(month, []).append(day)
    months: list[dict] = []
    for month in sorted(buckets):
        chunk = buckets[month]
        mids = [
            (day["temp_max"] + day["temp_min"]) / 2
            for day in chunk
            if isinstance(day.get("temp_max"), (int, float))
            and isinstance(day.get("temp_min"), (int, float))
        ]
        precip = sum(
            day["precipitation_sum"]
            for day in chunk
            if isinstance(day.get("precipitation_sum"), (int, float))
        )
        codes = [day["weathercode"] for day in chunk if isinstance(day.get("weathercode"), int)]
        dominant = _dominant_weather_code(codes)
        months.append(
            {
                "month": month,
                "days": len(chunk),
                "temp_avg": round(sum(mids) / len(mids), 1) if mids else None,
                "precipitation_total": round(precip, 1),
                "weather_dominant": dominant,
                "description": translate_weather_code(dominant)
                if dominant is not None
                else "Unknown",
            }
        )
    return months


def fetch_weather(
    lat: float = WEATHER_DEFAULT_LAT,
    lon: float = WEATHER_DEFAULT_LON,
    timeout: float = 10.0,
) -> dict:
    """Fetch current weather plus daily forecast from Open-Meteo API.

    Returns a dict with the current conditions (``temperature``, ``windspeed``,
    ``winddirection``, ``weathercode``, ``description``, ``latitude``,
    ``longitude``), a ``current`` alias of those conditions, ``daily`` (per-day
    forecast entries), ``weekly``/``monthly`` aggregates derived from the daily
    entries, plus ``source`` and ``cached_at`` metadata. Uses a thread-safe
    cache with TTL.

    Raises ``urllib.error.URLError`` or ``OSError`` if the API is unreachable,
    and ``ValueError`` if the API returns a malformed payload.
    """
    cached = _weather_cache.get(lat, lon)
    if cached is not None:
        return cached

    params = (
        f"?latitude={lat}&longitude={lon}"
        "&current_weather=true"
        "&daily=weathercode,temperature_2m_max,temperature_2m_min,"
        "precipitation_sum,precipitation_probability_max,windspeed_10m_max"
        f"&forecast_days={WEATHER_FORECAST_DAYS}"
        "&timezone=auto"
    )
    url = WEATHER_API_URL + params
    request = urllib.request.Request(url, headers={"User-Agent": "christmas-countdown/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if not isinstance(payload, dict):
        raise ValueError(f"Unexpected weather payload: {payload!r}")
    current = payload.get("current_weather")
    if not isinstance(current, dict):
        raise ValueError(f"Missing current_weather in payload: {payload!r}")
    weather_code = current.get("weathercode")
    if isinstance(weather_code, bool) or not isinstance(weather_code, int):
        raise ValueError(f"Missing weathercode in payload: {payload!r}")
    daily = _parse_daily_forecast(payload.get("daily"))
    result = {
        "temperature": current.get("temperature"),
        "windspeed": current.get("windspeed"),
        "winddirection": current.get("winddirection"),
        "weathercode": weather_code,
        "description": translate_weather_code(weather_code),
        "latitude": lat,
        "longitude": lon,
        "current": {
            "temperature": current.get("temperature"),
            "windspeed": current.get("windspeed"),
            "winddirection": current.get("winddirection"),
            "weathercode": weather_code,
            "description": translate_weather_code(weather_code),
        },
        "daily": daily,
        "weekly": aggregate_weekly(daily),
        "monthly": aggregate_monthly(daily),
        "source": WEATHER_SOURCE,
        "cached_at": datetime_now_utc_iso(),
    }

    _weather_cache.set(lat, lon, result)
    return result


def weather_summary(
    lat: float = WEATHER_DEFAULT_LAT,
    lon: float = WEATHER_DEFAULT_LON,
    timeout: float = 10.0,
) -> dict:
    """Return weather data with error handling for API failures.

    Never raises: any fetch or payload error is returned as an ``error`` dict.
    """
    try:
        return fetch_weather(lat, lon, timeout=timeout)
    except (
        urllib.error.URLError,
        OSError,
        ValueError,
        KeyError,
        AttributeError,
        TypeError,
    ) as exc:
        return {"error": str(exc), "latitude": lat, "longitude": lon}


def _target_label(target: str) -> str:
    """Format an ISO date as ``Friday, 25 December 2026``."""
    parsed = date.fromisoformat(target)
    return f"{parsed.strftime('%A')}, {parsed.day} {parsed.strftime('%B %Y')}"


def _fmt_temp_celsius(value: object) -> str:
    """Format a temperature value as ``°C`` or an en-dash when missing."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "–"
    return f"{value}°C"


def _fmt_wind(value: object) -> str:
    """Format a wind speed value as ``km/h`` or an en-dash when missing."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "–"
    return f"{value} km/h"


def _fmt_precip(value: object, suffix: str) -> str:
    """Format precipitation amount/probability or an en-dash when missing."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "–"
    return f"{value}{suffix}"


def _render_weather_section(weather: dict | None) -> str:
    """Render the server-side weather ``<section>`` for ``countdown_page``.

    All data is rendered as static HTML: no client-side fetch is emitted, so
    the section works under a ``script-src`` CSP with no external access.
    A missing or ``{"error": ...}`` payload renders a graceful fallback.
    """
    if not isinstance(weather, dict) or "error" in weather:
        return (
            '      <section class="weather" aria-label="Weather forecast">\n'
            '        <h2 class="weather-title">Athens weather</h2>\n'
            '        <p class="weather-unavailable">Weather currently unavailable.</p>\n'
            "      </section>\n"
        )
    current = weather.get("current")
    if not isinstance(current, dict):
        current = {}
    temp = _fmt_temp_celsius(current.get("temperature", weather.get("temperature")))
    description = str(current.get("description", weather.get("description", "Unknown")))
    wind = _fmt_wind(current.get("windspeed", weather.get("windspeed")))

    daily = weather.get("daily")
    daily_cards = daily if isinstance(daily, list) else []
    forecast = daily_cards[:7]

    weekly = weather.get("weekly")
    weekly_rows = weekly if isinstance(weekly, list) else []
    monthly = weather.get("monthly")
    monthly_rows = monthly if isinstance(monthly, list) else []

    parts: list[str] = []
    parts.append('      <section class="weather" aria-label="Weather forecast">\n')
    parts.append('        <h2 class="weather-title">Athens weather</h2>\n')
    parts.append('        <div class="weather-current">\n')
    parts.append(f'          <div class="weather-temp">{escape(temp)}</div>\n')
    parts.append(f'          <div class="weather-desc">{escape(description)}</div>\n')
    parts.append(f'          <div class="weather-wind">Wind {escape(wind)}</div>\n')
    parts.append("        </div>\n")

    parts.append('        <h3 class="weather-subtitle">7-day forecast</h3>\n')
    if forecast:
        parts.append('        <div class="forecast-grid">\n')
        for day in forecast:
            if not isinstance(day, dict):
                continue
            day_date = escape(str(day.get("date", "–")))
            day_desc = escape(str(day.get("description", "Unknown")))
            hi = escape(_fmt_temp_celsius(day.get("temp_max")))
            lo = escape(_fmt_temp_celsius(day.get("temp_min")))
            prob = escape(_fmt_precip(day.get("precipitation_probability"), "%"))
            parts.append('          <div class="forecast-card">\n')
            parts.append(f'            <b>{day_date}</b>\n')
            parts.append(f'            <span class="forecast-desc">{day_desc}</span>\n')
            parts.append(f'            <span class="forecast-temps">{hi} / {lo}</span>\n')
            parts.append(f'            <span class="forecast-precip">Rain {prob}</span>\n')
            parts.append("          </div>\n")
        parts.append("        </div>\n")
    else:
        parts.append('        <p class="weather-unavailable">Forecast currently unavailable.</p>\n')

    parts.append('        <h3 class="weather-subtitle">Weekly summary</h3>\n')
    if weekly_rows:
        parts.append('        <div class="summary-list">\n')
        for week in weekly_rows:
            if not isinstance(week, dict):
                continue
            start = escape(str(week.get("week_start", "–")))
            days = week.get("days", "–")
            avg = escape(_fmt_temp_celsius(week.get("temp_avg")))
            total = escape(_fmt_precip(week.get("precipitation_total"), " mm"))
            wdesc = escape(str(week.get("description", "Unknown")))
            parts.append(
                f'          <div class="summary-row"><b>{start}</b>'
                f"<span>{escape(str(days))} days · avg {avg} · "
                f"rain {total} · {wdesc}</span></div>\n"
            )
        parts.append("        </div>\n")
    else:
        parts.append('        <p class="weather-unavailable">Weekly summary unavailable.</p>\n')

    parts.append('        <h3 class="weather-subtitle">Monthly summary</h3>\n')
    if monthly_rows:
        parts.append('        <div class="summary-list">\n')
        for month in monthly_rows:
            if not isinstance(month, dict):
                continue
            name = escape(str(month.get("month", "–")))
            days = month.get("days", "–")
            avg = escape(_fmt_temp_celsius(month.get("temp_avg")))
            total = escape(_fmt_precip(month.get("precipitation_total"), " mm"))
            mdesc = escape(str(month.get("description", "Unknown")))
            parts.append(
                f'          <div class="summary-row"><b>{name}</b>'
                f"<span>{escape(str(days))} days · avg {avg} · "
                f"rain {total} · {mdesc}</span></div>\n"
            )
        parts.append("        </div>\n")
    else:
        parts.append('        <p class="weather-unavailable">Monthly summary unavailable.</p>\n')

    source = weather.get("source")
    if isinstance(source, str) and source:
        parts.append(f'        <p class="weather-source">Source: {escape(source)}</p>\n')
    parts.append("      </section>\n")
    return "".join(parts)


def countdown_page(
    summary: dict[str, object],
    nonce: str | None = None,
    weather: dict | None = None,
) -> str:
    """Return the HTML document for the Christmas countdown widget.

    When ``nonce`` is provided it is added to the inline ``<script>`` tag so the
    matching ``Content-Security-Policy`` can avoid ``script-src 'unsafe-inline'``.
    When ``weather`` is provided it is rendered server-side as a static section
    below the countdown facts; no client-side fetch is emitted.
    """
    target = str(summary["target"])
    working_days = int(summary["working_days"])
    calendar_days = int(summary["calendar_days"])
    weekend_days = int(summary["weekend_days"])
    weeks = int(summary["weeks"])
    is_christmas = bool(summary["is_christmas"])

    if is_christmas:
        headline = "Merry Christmas!"
        caption = f"Christmas Day - {_target_label(target)}"
    else:
        noun = "working day" if working_days == 1 else "working days"
        headline = str(working_days)
        caption = f"{noun} until Christmas Day - {_target_label(target)}"

    script_nonce = f' nonce="{escape(nonce)}"' if nonce else ""
    weather_section = _render_weather_section(weather)

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "  <title>Christmas Countdown</title>\n"
        "  <style>\n"
        "    :root { color-scheme: dark; }\n"
        "    * { box-sizing: border-box; }\n"
        "    body {\n"
        "      margin: 0; min-height: 100vh; display: flex; align-items: center;\n"
        "      justify-content: center; font-family: system-ui, -apple-system,\n"
        '      "Segoe UI", Roboto, sans-serif; color: #f5fbf7;\n'
        "      background: radial-gradient(circle at 50% 0%, #0b3d2e, #071c15 70%);\n"
        "    }\n"
        "    main { text-align: center; padding: 2rem; }\n"
        "    .card {\n"
        "      background: rgba(255,255,255,.05); border: 1px solid rgba(255,255,255,.1);\n"
        "      border-radius: 1.25rem; padding: 2.5rem 3rem; box-shadow: 0 20px 60px rgba(0,0,0,.35);\n"
        "    }\n"
        "    h1 {\n"
        "      margin: 0; font-size: 1.4rem; font-weight: 600; letter-spacing: .12em;\n"
        "      text-transform: uppercase; color: #b7f0d0;\n"
        "    }\n"
        "    .working {\n"
        "      font-size: clamp(4rem, 18vw, 11rem); font-weight: 800; line-height: 1;\n"
        "      color: #e8443a; text-shadow: 0 0 40px rgba(232,68,58,.45); margin: 1rem 0;\n"
        "    }\n"
        "    .caption { margin: 0; font-size: 1.05rem; color: #cfe9d8; }\n"
        "    .facts { display: flex; gap: 1.25rem; justify-content: center; margin-top: 2rem; flex-wrap: wrap; }\n"
        "    .fact {\n"
        "      background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.1);\n"
        "      border-radius: .75rem; padding: .85rem 1.1rem; min-width: 7rem;\n"
        "    }\n"
        "    .fact b { display: block; font-size: 1.4rem; color: #fff; }\n"
        "    .fact span { font-size: .7rem; text-transform: uppercase; letter-spacing: .08em; color: #9fc9b0; }\n"
        "    .clock { margin-top: 2rem; font-variant-numeric: tabular-nums; font-size: 1.1rem; color: #b7f0d0; }\n"
        "    .weather { margin-top: 2rem; border-top: 1px solid rgba(255,255,255,.1); padding-top: 1.5rem; }\n"
        "    .weather-title { margin: 0 0 .75rem; font-size: 1.1rem; font-weight: 600; letter-spacing: .1em; text-transform: uppercase; color: #b7f0d0; }\n"
        "    .weather-current { background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.1); border-radius: .75rem; padding: 1rem; }\n"
        "    .weather-temp { font-size: 2.5rem; font-weight: 800; color: #fff; line-height: 1; }\n"
        "    .weather-desc { margin-top: .25rem; font-size: 1.05rem; color: #cfe9d8; }\n"
        "    .weather-wind { margin-top: .25rem; font-size: .85rem; color: #9fc9b0; }\n"
        "    .weather-subtitle { margin: 1.25rem 0 .6rem; font-size: .85rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: #9fc9b0; }\n"
        "    .forecast-grid { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: .6rem; }\n"
        "    .forecast-card { background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.1); border-radius: .6rem; padding: .6rem .5rem; display: flex; flex-direction: column; gap: .2rem; }\n"
        "    .forecast-card b { font-size: .8rem; color: #fff; }\n"
        "    .forecast-desc { font-size: .75rem; color: #cfe9d8; }\n"
        "    .forecast-temps { font-size: .8rem; color: #fff; font-variant-numeric: tabular-nums; }\n"
        "    .forecast-precip { font-size: .72rem; color: #9fc9b0; }\n"
        "    .summary-list { display: flex; flex-direction: column; gap: .45rem; }\n"
        "    .summary-row { background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.08); border-radius: .6rem; padding: .55rem .7rem; display: flex; gap: .6rem; align-items: baseline; justify-content: space-between; text-align: left; }\n"
        "    .summary-row b { color: #fff; font-size: .85rem; white-space: nowrap; }\n"
        "    .summary-row span { color: #cfe9d8; font-size: .8rem; }\n"
        "    .weather-source { margin: .9rem 0 0; font-size: .72rem; color: #9fc9b0; }\n"
        "    .weather-unavailable { color: #cfe9d8; font-size: .9rem; }\n"
        "    @media (max-width: 700px) {\n"
        "      main { padding: 1rem; }\n"
        "      .card { padding: 1.5rem 1.25rem; }\n"
        "      .forecast-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }\n"
        "      .summary-row { flex-direction: column; gap: .15rem; }\n"
        "    }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        "  <main>\n"
        '    <div class="card">\n'
        "      <h1>Christmas Countdown</h1>\n"
        f'      <div class="working" id="working">{escape(headline)}</div>\n'
        f'      <p class="caption">{escape(caption)}</p>\n'
        '      <div class="facts">\n'
        f'        <div class="fact"><b>{calendar_days}</b><span>calendar days</span></div>\n'
        f'        <div class="fact"><b>{weekend_days}</b><span>weekend days</span></div>\n'
        f'        <div class="fact"><b>{weeks}</b><span>full weeks</span></div>\n'
        "      </div>\n"
        '      <p class="clock" id="clock">Loading clock...</p>\n'
        f"{weather_section}"
        "    </div>\n"
        "  </main>\n"
        f"  <script{script_nonce}>\n"
        f'    const target = new Date("{escape(target)}T00:00:00");\n'
        "    const clock = document.getElementById(\"clock\");\n"
        "    const pad = (n) => String(n).padStart(2, \"0\");\n"
        "    function tick() {\n"
        "      const remaining = target - new Date();\n"
        "      if (remaining <= 0) { clock.textContent = \"Merry Christmas!\"; return; }\n"
        "      const total = Math.floor(remaining / 1000);\n"
        "      const days = Math.floor(total / 86400);\n"
        "      const hours = Math.floor((total % 86400) / 3600);\n"
        "      const minutes = Math.floor((total % 3600) / 60);\n"
        "      const seconds = total % 60;\n"
        "      clock.textContent = days + \"d \" + pad(hours) + \"h \" + pad(minutes) + \"m \" + pad(seconds) + \"s of calendar time remaining\";\n"
        "      setTimeout(tick, 1000);\n"
        "    }\n"
        "    tick();\n"
        "  </script>\n"
        "</body>\n"
        "</html>\n"
    )


def _content_security_policy(nonce: str | None = None) -> str:
    """Return the Content-Security-Policy header value.

    The inline ``<script>`` is authorised by a per-response nonce when one is
    supplied, so the HTML page never needs ``script-src 'unsafe-inline'``.
    """
    script_src = f"script-src 'nonce-{nonce}'" if nonce else "script-src 'none'"
    return (
        "default-src 'none'; style-src 'unsafe-inline'; " + script_src + "; "
        "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    )


def _parse_weather_coords(query: str) -> tuple[float, float] | None:
    """Parse ``?lat=..&lon=..`` overrides, falling back to the defaults.

    Returns ``None`` when a supplied value is not a finite number or is out of
    range (latitude -90..90, longitude -180..180).
    """
    params = urllib.parse.parse_qs(query, keep_blank_values=True)
    try:
        lat_raw = params.get("lat", [None])[0]
        lon_raw = params.get("lon", [None])[0]
        lat = WEATHER_DEFAULT_LAT if lat_raw in (None, "") else float(lat_raw)
        lon = WEATHER_DEFAULT_LON if lon_raw in (None, "") else float(lon_raw)
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


class ChristmasCountdownHandler(BaseHTTPRequestHandler):
    """Request handler serving the countdown page and a JSON endpoint."""

    server_version = "ChristmasCountdown/1.0"

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        self._handle(send_body=True)

    def do_HEAD(self) -> None:  # noqa: N802 (http.server API)
        self._handle(send_body=False)

    def _today(self) -> date:
        """Return the current date from the server's injectable clock."""
        return cast(ChristmasCountdownServer, self.server).today_provider()

    def _route(self) -> tuple[int, bytes, str, str]:
        """Map the request path to ``(status, body, content_type, csp)``."""
        path = self.path.split("?", 1)[0]
        if path == "/":
            nonce = secrets.token_urlsafe(16)
            body = countdown_page(
                countdown_summary(self._today()),
                nonce=nonce,
                weather=weather_summary(),
            ).encode("utf-8")
            return 200, body, "text/html; charset=utf-8", _content_security_policy(nonce)
        if path == "/api/countdown":
            body = json.dumps(countdown_summary(self._today())).encode("utf-8")
            return 200, body, "application/json; charset=utf-8", _content_security_policy()
        if path == "/api/weather":
            query = self.path.split("?", 1)[1] if "?" in self.path else ""
            coords = _parse_weather_coords(query)
            if coords is None:
                body = json.dumps(
                    {"error": "Invalid coordinates: expected ?lat=-90..90&lon=-180..180"}
                ).encode("utf-8")
                return 400, body, "application/json; charset=utf-8", _content_security_policy()
            lat, lon = coords
            body = json.dumps(weather_summary(lat, lon)).encode("utf-8")
            return 200, body, "application/json; charset=utf-8", _content_security_policy()
        if path == "/healthz":
            return 200, b'{"status": "ok"}', "application/json; charset=utf-8", _content_security_policy()
        return 404, b"Not Found\n", "text/plain; charset=utf-8", _content_security_policy()

    def _handle(self, *, send_body: bool) -> None:
        status, body, content_type, csp = self._route()
        self._respond(status, body, content_type, csp, send_body=send_body)

    def _respond(
        self, status: int, body: bytes, content_type: str, csp: str, *, send_body: bool = True
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", csp)
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        """Write access logs to stderr, keeping stdout clean."""
        sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))


class ChristmasCountdownServer(ThreadingHTTPServer):
    """HTTP server carrying the injectable date provider used by the handler."""

    today_provider: TodayProvider

    def __init__(
        self,
        server_address: tuple[str, int],
        RequestHandlerClass: type[BaseHTTPRequestHandler],
        today_provider: TodayProvider | None = None,
    ) -> None:
        super().__init__(server_address, RequestHandlerClass)
        self.today_provider = today_provider or date.today


def create_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    today_provider: TodayProvider | None = None,
) -> ChristmasCountdownServer:
    """Create (but do not start) an HTTP server bound to ``host:port``.

    Passing ``port=0`` binds an ephemeral port, which is convenient for tests.
    ``today_provider`` is an injectable clock returning the current date; it
    defaults to :func:`datetime.date.today` and lets tests pin time so the
    suite stays deterministic year-round.
    """
    return ChristmasCountdownServer(
        (host, port), ChristmasCountdownHandler, today_provider=today_provider
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Christmas working-days countdown web app")
    parser.add_argument("--host", default=DEFAULT_HOST, help="interface to bind")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="port to bind")
    args = parser.parse_args(argv)

    server = create_server(args.host, args.port)
    host, port = server.server_address[:2]
    print(f"Serving Christmas countdown on http://{host}:{port}/ (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
