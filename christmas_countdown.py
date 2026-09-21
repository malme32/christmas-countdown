#!/usr/bin/env python3
"""A tiny, dependency-free Christmas countdown web app.

Serves a page with a countdown widget that shows how many *working days*
(Monday-Friday) remain until Christmas Day after deducting the Greek public
(bank) holidays that fall in the period, alongside the remaining calendar time.
A second page renders a full month-by-month calendar highlighting weekends,
bank holidays, today and Christmas Day. The same numbers are exposed as JSON.
The countdown page also embeds a server-rendered weather section (current
conditions plus daily, weekly and monthly forecast) with graceful fallback when
the upstream API is unreachable. Built only on the Python standard library.

Working days exclude weekends and Greek public holidays. The holiday set is
computed from fixed dates plus the movable Orthodox holidays derived from
Easter Sunday, so the result is deterministic and needs no data files or
network access.

Usage:
    python3 christmas_countdown.py
    python3 christmas_countdown.py --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import argparse
import calendar
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

MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
WEEKDAY_LABELS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

#: Greek statutory public holidays that fall on the same date every year.
GREEK_FIXED_HOLIDAYS: dict[tuple[int, int], str] = {
    (1, 1): "New Year's Day",
    (1, 6): "Epiphany",
    (3, 25): "Independence Day",
    (5, 1): "Labour Day",
    (8, 15): "Assumption of Mary",
    (10, 28): "Ochi Day",
    (12, 25): "Christmas Day",
    (12, 26): "Second Day of Christmas",
}

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


def orthodox_easter(year: int) -> date:
    """Return Orthodox Easter Sunday for ``year`` as a Gregorian date.

    Uses the Meeus Julian algorithm to find the Julian-calendar date and then
    adds the Julian-to-Gregorian offset, so the result is always a Sunday.
    """
    a = year % 4
    b = year % 7
    c = year % 19
    d = (19 * c + 15) % 30
    e = (2 * a + 4 * b - d + 34) % 7
    month = (d + e + 114) // 31
    day = ((d + e + 114) % 31) + 1
    julian = date(year, month, day)
    offset = year // 100 - year // 400 - 2
    return julian + timedelta(days=offset)


def greek_holidays(year: int) -> dict[date, str]:
    """Return the Greek public (bank) holidays for ``year`` keyed by date.

    Combines the fixed statutory dates with the movable Orthodox holidays
    anchored on Easter Sunday (Clean Monday, Good Friday, Easter Sunday, Easter
    Monday and Holy Spirit Monday). Greek law moves Labour Day to the next
    working day whenever 1 May is a weekend or coincides with another public
    holiday, so the observed date is returned instead of 1 May in those years.
    """
    easter = orthodox_easter(year)
    movable = {
        easter - timedelta(days=48): "Clean Monday",
        easter - timedelta(days=2): "Good Friday",
        easter: "Easter Sunday",
        easter + timedelta(days=1): "Easter Monday",
        easter + timedelta(days=50): "Holy Spirit Monday",
    }
    holidays = {
        date(year, month, day): name
        for (month, day), name in GREEK_FIXED_HOLIDAYS.items()
    }
    labour = date(year, 5, 1)
    if not is_working_day(labour) or labour in movable:
        holidays.pop(labour, None)
        observed = labour + timedelta(days=1)
        while not is_working_day(observed) or observed in movable or observed in holidays:
            observed += timedelta(days=1)
        holidays[observed] = "Labour Day (observed)"
    holidays.update(movable)
    return holidays


def bank_holidays_between(start: date, end: date) -> list[tuple[date, str]]:
    """Return Greek public holidays strictly after ``start`` up to ``end``.

    Holidays that fall at the weekend are included; callers that deduct them
    from the working-day count filter on :func:`is_working_day` first.
    """
    if end <= start:
        return []
    holidays: dict[date, str] = {}
    for year in range(start.year, end.year + 1):
        holidays.update(greek_holidays(year))
    return sorted(
        (day, name) for day, name in holidays.items() if start < day <= end
    )


def months_between(start: date, end: date) -> list[date]:
    """Return the first day of every month from ``start`` to ``end`` inclusive."""
    months: list[date] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append(date(year, month, 1))
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return months


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
    holidays = bank_holidays_between(today, target)
    bank_holiday_days = sum(1 for day, _ in holidays if is_working_day(day))
    return {
        "today": today.isoformat(),
        "target": target.isoformat(),
        "calendar_days": calendar_days,
        "working_days": working_days,
        "bank_holiday_days": bank_holiday_days,
        "remaining_working_days": max(working_days - bank_holiday_days, 0),
        "weekend_days": weekend_days_between(today, target),
        "weeks": calendar_days // 7,
        "is_christmas": today == target,
        "holidays": [
            {
                "date": day.isoformat(),
                "name": name,
                "working_day": is_working_day(day),
            }
            for day, name in holidays
        ],
    }


class WeatherCache:
    """Thread-safe weather cache with TTL using ``threading.Lock()``.

    Stores weather data keyed by (latitude, longitude) with a configurable
    time-to-live. The lock ensures safe concurrent access from multiple
    threads. The cache is bounded to ``max_entries`` (oldest-timestamp
    eviction) so an attacker cycling ``?lat=``/``?lon=`` cannot grow it
    without bound; TTL expiry still removes stale entries on read.
    """

    def __init__(self, ttl: int = WEATHER_CACHE_TTL, max_entries: int = 128) -> None:
        self._cache: dict[tuple[float, float], tuple[float, dict]] = {}
        self._ttl = ttl
        self._max_entries = max_entries
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
            if len(self._cache) > self._max_entries:
                oldest = min(self._cache.items(), key=lambda kv: kv[1][0])[0]
                del self._cache[oldest]

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


# Emoji/Unicode icons per WMO weather code (no image assets needed).
WEATHER_ICONS: dict[int, str] = {
    0: "\u2600\ufe0f",  # ☀️ clear sky
    1: "\U0001f324\ufe0f",  # 🌤️ mainly clear
    2: "\u26c5",  # ⛅ partly cloudy
    3: "\u2601\ufe0f",  # ☁️ overcast
    45: "\U0001f32b\ufe0f",  # 🌫️ fog
    48: "\U0001f32b\ufe0f",  # 🌫️ depositing rime fog
    51: "\U0001f326\ufe0f",  # 🌦️ light drizzle
    53: "\U0001f326\ufe0f",  # 🌦️ moderate drizzle
    55: "\U0001f326\ufe0f",  # 🌦️ dense drizzle
    56: "\U0001f326\ufe0f",  # 🌦️ light freezing drizzle
    57: "\U0001f326\ufe0f",  # 🌦️ dense freezing drizzle
    61: "\U0001f327\ufe0f",  # 🌧️ slight rain
    63: "\U0001f327\ufe0f",  # 🌧️ moderate rain
    65: "\U0001f327\ufe0f",  # 🌧️ heavy rain
    66: "\U0001f327\ufe0f",  # 🌧️ light freezing rain
    67: "\U0001f327\ufe0f",  # 🌧️ heavy freezing rain
    71: "\U0001f328\ufe0f",  # 🌨️ slight snow fall
    73: "\U0001f328\ufe0f",  # 🌨️ moderate snow fall
    75: "\U0001f328\ufe0f",  # 🌨️ heavy snow fall
    77: "\U0001f328\ufe0f",  # 🌨️ snow grains
    80: "\U0001f327\ufe0f",  # 🌧️ slight rain showers
    81: "\U0001f327\ufe0f",  # 🌧️ moderate rain showers
    82: "\U0001f327\ufe0f",  # 🌧️ violent rain showers
    85: "\U0001f328\ufe0f",  # 🌨️ slight snow showers
    86: "\U0001f328\ufe0f",  # 🌨️ heavy snow showers
    95: "\u26c8\ufe0f",  # ⛈️ thunderstorm
    96: "\u26c8\ufe0f",  # ⛈️ thunderstorm with slight hail
    99: "\u26c8\ufe0f",  # ⛈️ thunderstorm with heavy hail
}

WEATHER_ICON_FALLBACK = "\u2753"  # ❓ unknown code


def weather_icon_for_code(code: object) -> str:
    """Return an emoji/Unicode icon for a WMO weather code.

    Returns ``WEATHER_ICON_FALLBACK`` for missing or unrecognized codes so
    callers never have to handle ``None``.
    """
    if isinstance(code, bool):
        return WEATHER_ICON_FALLBACK
    if isinstance(code, int):
        return WEATHER_ICONS.get(code, WEATHER_ICON_FALLBACK)
    return WEATHER_ICON_FALLBACK


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
    and ``ValueError`` if the API returns a malformed payload or the
    coordinates are out of range (latitude -90..90, longitude -180..180).
    """
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError(f"Invalid coordinates: lat={lat!r} lon={lon!r}")
    cached = _weather_cache.get(lat, lon)
    if cached is not None:
        return cached

    query = urllib.parse.urlencode(
        {
            "latitude": lat,
            "longitude": lon,
            "current_weather": "true",
            "daily": "weathercode,temperature_2m_max,temperature_2m_min,"
            "precipitation_sum,precipitation_probability_max,windspeed_10m_max",
            "forecast_days": WEATHER_FORECAST_DAYS,
            "timezone": "auto",
        }
    )
    url = WEATHER_API_URL + "?" + query
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

    Never raises: any fetch or payload error is logged to stderr and returned
    as an ``error`` dict.
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
        sys.stderr.write(f"weather unavailable lat={lat} lon={lon}: {exc}\n")
        return {"error": str(exc), "latitude": lat, "longitude": lon}


def _target_label(target: str) -> str:
    """Format an ISO date as ``Friday, 25 December 2026``."""
    parsed = date.fromisoformat(target)
    return f"{parsed.strftime('%A')}, {parsed.day} {parsed.strftime('%B %Y')}"


def _holiday_rows_html(holidays: list[dict[str, object]]) -> str:
    """Render the Greek bank holidays in the countdown window as ``<li>`` items."""
    if not holidays:
        return '<li class="none">No Greek public holidays before Christmas.</li>'
    rows = []
    for holiday in holidays:
        day = date.fromisoformat(str(holiday["date"]))
        when = f"{day.strftime('%a')} {day.day} {day.strftime('%b')}"
        detail = "" if bool(holiday["working_day"]) else " (weekend, not deducted)"
        rows.append(
            f"<li><b>{escape(when)}</b> - {escape(str(holiday['name']))}{detail}</li>"
        )
    return "".join(rows)


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
    current_code = current.get("weathercode", weather.get("weathercode"))
    current_icon = weather_icon_for_code(current_code)

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
    parts.append(
        f'          <span class="weather-icon weather-icon-lg" aria-hidden="true">{current_icon}</span>\n'
    )
    parts.append('          <div class="weather-details">\n')
    parts.append(f'            <div class="weather-temp">{escape(temp)}</div>\n')
    parts.append(f'            <div class="weather-desc">{escape(description)}</div>\n')
    parts.append(f'            <div class="weather-wind">Wind {escape(wind)}</div>\n')
    parts.append("          </div>\n")
    parts.append("        </div>\n")

    parts.append('        <h3 class="weather-subtitle">7-day forecast</h3>\n')
    if forecast:
        parts.append('        <div class="forecast-grid" role="list">\n')
        for day in forecast:
            if not isinstance(day, dict):
                continue
            day_date = escape(str(day.get("date", "–")))
            day_desc = escape(str(day.get("description", "Unknown")))
            day_icon = weather_icon_for_code(day.get("weathercode"))
            hi = escape(_fmt_temp_celsius(day.get("temp_max")))
            lo = escape(_fmt_temp_celsius(day.get("temp_min")))
            prob = escape(_fmt_precip(day.get("precipitation_probability"), "%"))
            parts.append('          <div class="forecast-card" role="listitem">\n')
            parts.append(f'            <b>{day_date}</b>\n')
            parts.append(f'            <span class="weather-icon" aria-hidden="true">{day_icon}</span>\n')
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
            wicon = weather_icon_for_code(week.get("weather_dominant"))
            parts.append(
                f'          <div class="summary-row"><b>{start}</b>'
                f'<span class="weather-icon weather-icon-sm" aria-hidden="true">{wicon}</span>'
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
            micon = weather_icon_for_code(month.get("weather_dominant"))
            parts.append(
                f'          <div class="summary-row"><b>{name}</b>'
                f'<span class="weather-icon weather-icon-sm" aria-hidden="true">{micon}</span>'
                f"<span>{escape(str(days))} days · avg {avg} · "
                f"rain {total} · {mdesc}</span></div>\n"
            )
        parts.append("        </div>\n")
    else:
        parts.append('        <p class="weather-unavailable">Monthly summary unavailable.</p>\n')

    source = weather.get("source")
    if isinstance(source, str) and source:
        parts.append(
            f'        <p class="weather-source">Weather data &copy; {escape(source)} (CC BY 4.0)</p>\n'
        )
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
    remaining_days = int(summary["remaining_working_days"])
    calendar_days = int(summary["calendar_days"])
    weekend_days = int(summary["weekend_days"])
    bank_holiday_days = int(summary["bank_holiday_days"])
    weeks = int(summary["weeks"])
    is_christmas = bool(summary["is_christmas"])
    holidays = cast(list[dict[str, object]], summary["holidays"])

    if is_christmas:
        headline = "Merry Christmas!"
        caption = f"Christmas Day - {_target_label(target)}"
    else:
        noun = "working day" if remaining_days == 1 else "working days"
        holiday_noun = (
            "Greek bank holiday" if bank_holiday_days == 1 else "Greek bank holidays"
        )
        headline = str(remaining_days)
        caption = (
            f"{noun} until Christmas Day - {_target_label(target)} "
            f"({working_days} weekdays minus {bank_holiday_days} {holiday_noun})"
        )

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
        "    main { text-align: center; padding: 2rem; max-width: 46rem; }\n"
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
        "    .holidays {\n"
        "      margin: 2rem 0 0; padding: 1.1rem 1.4rem; text-align: left;\n"
        "      background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.1); border-radius: .75rem;\n"
        "    }\n"
        "    .holidays h2 { margin: 0 0 .6rem; font-size: .75rem; letter-spacing: .1em; text-transform: uppercase; color: #9fc9b0; }\n"
        "    .holidays ul { margin: 0; padding-left: 1.1rem; color: #e6f5ec; }\n"
        "    .holidays li { margin: .2rem 0; }\n"
        "    .weather { margin-top: 2rem; border-top: 1px solid rgba(255,255,255,.1); padding-top: 1.5rem; }\n"
    "    .weather-title { margin: 0 0 .75rem; font-size: 1.1rem; font-weight: 600; letter-spacing: .1em; text-transform: uppercase; color: #b7f0d0; }\n"
    "    .weather-current { background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.1); border-radius: .75rem; padding: 1rem 1.25rem; display: flex; align-items: center; gap: 1.25rem; text-align: left; }\n"
    "    .weather-details { display: flex; flex-direction: column; gap: .2rem; min-width: 0; }\n"
    "    .weather-icon { font-size: 1.75rem; line-height: 1; flex-shrink: 0; }\n"
    "    .weather-icon-lg { font-size: 3rem; }\n"
    "    .weather-icon-sm { font-size: 1.1rem; }\n"
    "    .weather-temp { font-size: 2.5rem; font-weight: 800; color: #fff; line-height: 1; font-variant-numeric: tabular-nums; }\n"
    "    .weather-desc { margin-top: .25rem; font-size: 1.05rem; color: #cfe9d8; }\n"
    "    .weather-wind { margin-top: .25rem; font-size: .85rem; color: #9fc9b0; }\n"
    "    .weather-subtitle { margin: 1.25rem 0 .6rem; font-size: .85rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: #9fc9b0; }\n"
    "    .forecast-grid { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: .6rem; }\n"
    "    .forecast-card { background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.1); border-radius: .6rem; padding: .6rem .5rem; display: flex; flex-direction: column; align-items: center; text-align: center; gap: .25rem; }\n"
    "    .forecast-card b { font-size: .8rem; color: #fff; }\n"
    "    .forecast-card .weather-icon { font-size: 1.5rem; }\n"
    "    .forecast-desc { font-size: .75rem; color: #cfe9d8; }\n"
    "    .forecast-temps { font-size: .8rem; color: #fff; font-variant-numeric: tabular-nums; }\n"
    "    .forecast-precip { font-size: .72rem; color: #9fc9b0; }\n"
    "    .summary-list { display: flex; flex-direction: column; gap: .45rem; }\n"
    "    .summary-row { background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.08); border-radius: .6rem; padding: .55rem .7rem; display: flex; gap: .6rem; align-items: center; justify-content: space-between; text-align: left; }\n"
    "    .summary-row b { color: #fff; font-size: .85rem; white-space: nowrap; }\n"
    "    .summary-row span:last-child { color: #cfe9d8; font-size: .8rem; }\n"
    "    .weather-source { margin: .9rem 0 0; font-size: .72rem; color: #9fc9b0; }\n"
    "    .weather-unavailable { color: #cfe9d8; font-size: .9rem; }\n"
    "    @media (max-width: 1024px) {\n"
    "      .forecast-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }\n"
    "    }\n"
    "    @media (max-width: 700px) {\n"
    "      .weather-current { flex-direction: column; text-align: center; gap: .5rem; }\n"
    "      .weather-details { align-items: center; }\n"
    "      .forecast-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }\n"
    "      .summary-row { flex-wrap: wrap; gap: .35rem; }\n"
    "    }\n"
    "    .calendar-link { display: inline-block; margin-top: 1.6rem; color: #b7f0d0; }\n"
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
        f'        <div class="fact"><b>{bank_holiday_days}</b><span>bank holidays</span></div>\n'
        f'        <div class="fact"><b>{weeks}</b><span>full weeks</span></div>\n'
        "      </div>\n"
        '      <section class="holidays">\n'
        "        <h2>Greek bank holidays before Christmas</h2>\n"
        f"        <ul>{_holiday_rows_html(holidays)}</ul>\n"
        "      </section>\n"
        '      <p class="clock" id="clock">Loading clock...</p>\n'
        f"{weather_section}"
        '      <a class="calendar-link" href="/calendar">View full calendar &rarr;</a>\n'
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


def _month_table_html(
    month_start: date,
    today: date,
    target: date,
    holidays: dict[date, str],
    counted: set[date],
) -> str:
    """Render one month as an HTML table with weekend/holiday highlighting.

    ``holidays`` supplies labels for every Greek bank holiday in the rendered
    years; ``counted`` marks those inside the countdown window that are actually
    deducted from the working-day total.
    """
    year, month = month_start.year, month_start.month
    header = "".join(f"<th>{label}</th>" for label in WEEKDAY_LABELS)
    rows = []
    for week in calendar.monthcalendar(year, month):
        cells = []
        for day_number in week:
            if day_number == 0:
                cells.append('<td class="empty"></td>')
                continue
            day = date(year, month, day_number)
            classes = ["day"]
            if not is_working_day(day):
                classes.append("weekend")
            if day in holidays:
                classes.append("holiday")
            if day in counted:
                classes.append("counted")
            if day == today:
                classes.append("today")
            if day == target:
                classes.append("christmas")
            name = holidays.get(day, "")
            title = f' title="{escape(name)}"' if name else ""
            badge = (
                f'<span class="hname">{escape(name)}</span>'
                if day in counted
                else ""
            )
            cells.append(
                f'<td class="{" ".join(classes)}"{title}>'
                f'<span class="dnum">{day_number}</span>{badge}</td>'
            )
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return (
        '<section class="month">'
        f"<h2>{MONTH_NAMES[month - 1]} {year}</h2>"
        f"<table><thead><tr>{header}</tr></thead>"
        f'<tbody>{"".join(rows)}</tbody></table>'
        "</section>"
    )


def calendar_page(summary: dict[str, object]) -> str:
    """Return the full month-by-month calendar for the countdown window.

    Each month from the current one through the target month is rendered as a
    grid, highlighting weekends, Greek bank holidays, today and Christmas Day,
    together with the countdown numbers and the holiday list.
    """
    today = date.fromisoformat(str(summary["today"]))
    target = date.fromisoformat(str(summary["target"]))
    remaining_days = int(summary["remaining_working_days"])
    working_days = int(summary["working_days"])
    bank_holiday_days = int(summary["bank_holiday_days"])
    weekends = int(summary["weekend_days"])
    holidays = cast(list[dict[str, object]], summary["holidays"])
    counted = {
        date.fromisoformat(str(item["date"]))
        for item in holidays
        if item["working_day"]
    }

    year_holidays: dict[date, str] = {}
    for year in range(today.year, target.year + 1):
        year_holidays.update(greek_holidays(year))

    months_html = "\n".join(
        _month_table_html(month, today, target, year_holidays, counted)
        for month in months_between(today, target)
    )

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "  <title>Christmas Countdown Calendar</title>\n"
        "  <style>\n"
        "    :root { color-scheme: dark; }\n"
        "    * { box-sizing: border-box; }\n"
        "    body {\n"
        "      margin: 0; padding: 2rem 1.25rem; font-family: system-ui, -apple-system,\n"
        '      "Segoe UI", Roboto, sans-serif; color: #f5fbf7;\n'
        "      background: radial-gradient(circle at 50% 0%, #0b3d2e, #071c15 70%);\n"
        "    }\n"
        "    a { color: #b7f0d0; }\n"
        "    header { text-align: center; max-width: 52rem; margin: 0 auto 2rem; }\n"
        "    h1 { margin: 0 0 .6rem; font-size: 1.4rem; letter-spacing: .12em; text-transform: uppercase; color: #b7f0d0; }\n"
        "    .lead { margin: 0 0 1.4rem; font-size: 1.05rem; color: #cfe9d8; }\n"
        "    .lead b { color: #e8443a; font-size: 1.5rem; }\n"
        "    .facts { display: flex; gap: 1rem; justify-content: center; flex-wrap: wrap; }\n"
        "    .fact { background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.1); border-radius: .75rem; padding: .7rem 1rem; min-width: 7rem; }\n"
        "    .fact b { display: block; font-size: 1.3rem; color: #fff; }\n"
        "    .fact span { font-size: .68rem; text-transform: uppercase; letter-spacing: .08em; color: #9fc9b0; }\n"
        "    .months { display: grid; grid-template-columns: repeat(auto-fit, minmax(19rem, 1fr)); gap: 1.25rem; max-width: 80rem; margin: 0 auto; }\n"
        "    .month { background: rgba(255,255,255,.05); border: 1px solid rgba(255,255,255,.1); border-radius: 1rem; padding: 1rem 1.1rem; }\n"
        "    .month h2 { margin: .1rem 0 .8rem; font-size: 1rem; letter-spacing: .08em; text-transform: uppercase; color: #b7f0d0; text-align: center; }\n"
        "    table { width: 100%; border-collapse: separate; border-spacing: .15rem; }\n"
        "    th { font-size: .65rem; text-transform: uppercase; letter-spacing: .06em; color: #9fc9b0; padding: .2rem; }\n"
        "    td { position: relative; vertical-align: top; height: 2.7rem; padding: .25rem .3rem; border: 1px solid rgba(255,255,255,.06); border-radius: .35rem; font-size: .8rem; }\n"
        "    td.empty { border: none; }\n"
        "    td.weekend { background: rgba(255,255,255,.04); color: #9fc9b0; }\n"
        "    td.holiday { background: rgba(232,68,58,.22); }\n"
        "    td.counted { box-shadow: inset 0 0 0 1px rgba(232,68,58,.65); }\n"
        "    td.today { outline: 2px solid #b7f0d0; }\n"
        "    td.christmas { background: rgba(232,68,58,.5); color: #fff; font-weight: 700; }\n"
        "    .dnum { font-weight: 600; }\n"
        "    .hname { display: block; font-size: .56rem; line-height: 1.1; color: #ffd9d5; }\n"
        "    .legend { max-width: 80rem; margin: 1.5rem auto 0; display: flex; gap: 1.2rem; justify-content: center; flex-wrap: wrap; font-size: .8rem; color: #cfe9d8; }\n"
        "    .legend span { display: inline-flex; align-items: center; gap: .4rem; }\n"
        "    .legend i { width: .9rem; height: .9rem; border-radius: .2rem; display: inline-block; border: 1px solid rgba(255,255,255,.2); }\n"
        "    .legend .sw-weekend { background: rgba(255,255,255,.12); }\n"
        "    .legend .sw-holiday { background: rgba(232,68,58,.35); }\n"
        "    .legend .sw-today { outline: 2px solid #b7f0d0; }\n"
        "    .legend .sw-christmas { background: rgba(232,68,58,.6); }\n"
        "    .holidays { max-width: 52rem; margin: 2rem auto 0; padding: 1.1rem 1.4rem; background: rgba(255,255,255,.05); border: 1px solid rgba(255,255,255,.1); border-radius: .75rem; }\n"
        "    .holidays h2 { margin: 0 0 .6rem; font-size: .75rem; letter-spacing: .1em; text-transform: uppercase; color: #9fc9b0; }\n"
        "    .holidays ul { margin: 0; padding-left: 1.1rem; color: #e6f5ec; }\n"
        "    .back { text-align: center; margin-top: 2rem; }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        "  <header>\n"
        "    <h1>Christmas Countdown Calendar</h1>\n"
        f'    <p class="lead"><b>{remaining_days}</b> working days remain until '
        f"{escape(_target_label(target.isoformat()))}</p>\n"
        '    <div class="facts">\n'
        f'      <div class="fact"><b>{working_days}</b><span>weekdays</span></div>\n'
        f'      <div class="fact"><b>{weekends}</b><span>weekend days</span></div>\n'
        f'      <div class="fact"><b>{bank_holiday_days}</b><span>bank holidays</span></div>\n'
        f'      <div class="fact"><b>{remaining_days}</b><span>working days left</span></div>\n'
        "    </div>\n"
        "  </header>\n"
        '  <div class="months">\n'
        f"{months_html}\n"
        "  </div>\n"
        '  <p class="legend">\n'
        '    <span><i class="sw-weekend"></i>weekend</span>\n'
        '    <span><i class="sw-holiday"></i>bank holiday</span>\n'
        '    <span><i class="sw-today"></i>today</span>\n'
        '    <span><i class="sw-christmas"></i>Christmas Day</span>\n'
        "  </p>\n"
        '  <section class="holidays">\n'
        "    <h2>Greek bank holidays in this countdown</h2>\n"
        f"    <ul>{_holiday_rows_html(holidays)}</ul>\n"
        "  </section>\n"
        '  <p class="back"><a href="/">Back to countdown</a></p>\n'
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
        if path == "/calendar":
            body = calendar_page(countdown_summary(self._today())).encode("utf-8")
            return 200, body, "text/html; charset=utf-8", _content_security_policy()
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
