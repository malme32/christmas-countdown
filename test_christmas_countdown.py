#!/usr/bin/env python3
"""Tests for christmas_countdown."""

from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date
from http.client import HTTPMessage

from christmas_countdown import (
    WeatherCache,
    WEATHER_CODES,
    _parse_weather_coords,
    _render_weather_section,
    countdown_page,
    countdown_summary,
    create_server,
    fetch_weather,
    is_working_day,
    next_christmas,
    translate_weather_code,
    weather_icon_for_code,
    weather_summary,
    weekend_days_between,
    working_days_between,
)

FIXED_TODAY = date(2026, 12, 1)


class NextChristmasTests(unittest.TestCase):
    def test_returns_this_year_when_before_christmas(self) -> None:
        self.assertEqual(next_christmas(date(2026, 1, 1)), date(2026, 12, 25))

    def test_returns_today_on_christmas(self) -> None:
        self.assertEqual(next_christmas(date(2026, 12, 25)), date(2026, 12, 25))

    def test_rolls_forward_after_christmas(self) -> None:
        self.assertEqual(next_christmas(date(2026, 12, 26)), date(2027, 12, 25))


class WorkingDayTests(unittest.TestCase):
    def test_weekdays_are_working_days(self) -> None:
        # 2026-12-25 is a Friday; 2026-12-28 is a Monday.
        self.assertTrue(is_working_day(date(2026, 12, 25)))
        self.assertTrue(is_working_day(date(2026, 12, 28)))

    def test_weekend_is_not_a_working_day(self) -> None:
        # 2026-09-19 is a Saturday; 2026-12-26 is a Saturday.
        self.assertFalse(is_working_day(date(2026, 9, 19)))
        self.assertFalse(is_working_day(date(2026, 12, 26)))

    def test_counts_only_weekdays_after_start(self) -> None:
        # Tue 1 Dec -> Fri 25 Dec 2026 inclusive, start excluded.
        self.assertEqual(working_days_between(date(2026, 12, 1), date(2026, 12, 25)), 18)

    def test_counts_short_final_week(self) -> None:
        self.assertEqual(working_days_between(date(2026, 12, 21), date(2026, 12, 25)), 4)

    def test_zero_when_start_is_target(self) -> None:
        self.assertEqual(working_days_between(date(2026, 12, 25), date(2026, 12, 25)), 0)

    def test_zero_when_end_before_start(self) -> None:
        self.assertEqual(working_days_between(date(2026, 12, 26), date(2026, 12, 25)), 0)

    def test_weekend_counter_complements_working_days(self) -> None:
        start, end = date(2026, 12, 1), date(2026, 12, 25)
        self.assertEqual(weekend_days_between(start, end), 6)
        self.assertEqual(
            working_days_between(start, end) + weekend_days_between(start, end),
            (end - start).days,
        )


class CountdownSummaryTests(unittest.TestCase):
    def test_summary_mid_season(self) -> None:
        summary = countdown_summary(date(2026, 12, 1))
        self.assertEqual(summary["target"], "2026-12-25")
        self.assertEqual(summary["calendar_days"], 24)
        self.assertEqual(summary["working_days"], 18)
        self.assertEqual(summary["weekend_days"], 6)
        self.assertEqual(summary["weeks"], 3)
        self.assertFalse(summary["is_christmas"])

    def test_summary_on_christmas(self) -> None:
        summary = countdown_summary(date(2026, 12, 25))
        self.assertEqual(summary["calendar_days"], 0)
        self.assertEqual(summary["working_days"], 0)
        self.assertTrue(summary["is_christmas"])

    def test_summary_after_christmas_targets_next_year(self) -> None:
        summary = countdown_summary(date(2026, 12, 26))
        self.assertEqual(summary["target"], "2027-12-25")
        self.assertEqual(summary["calendar_days"], 364)
        self.assertEqual(summary["working_days"], 260)
        self.assertEqual(summary["weekend_days"], 104)

    def test_summary_is_json_serialisable(self) -> None:
        json.dumps(countdown_summary(date(2026, 12, 1)))


class CountdownPageTests(unittest.TestCase):
    def test_page_is_html(self) -> None:
        page = countdown_page(countdown_summary(date(2026, 12, 1)))
        self.assertTrue(page.lstrip().startswith("<!DOCTYPE html>"))
        self.assertIn("<title>Christmas Countdown</title>", page)

    def test_page_shows_working_days_and_target(self) -> None:
        page = countdown_page(countdown_summary(date(2026, 12, 1)))
        self.assertIn(">18<", page)
        self.assertIn("working days until Christmas Day", page)
        self.assertIn("Friday, 25 December 2026", page)

    def test_page_uses_singular_day_for_one(self) -> None:
        page = countdown_page(countdown_summary(date(2026, 12, 24)))
        self.assertIn('id="working">1</div>', page)
        self.assertIn("working day until Christmas Day", page)
        self.assertNotIn("working days until Christmas Day", page)

    def test_page_shows_merry_christmas_on_the_day(self) -> None:
        page = countdown_page(countdown_summary(date(2026, 12, 25)))
        self.assertIn("Merry Christmas!", page)

    def test_page_embeds_target_for_live_clock(self) -> None:
        page = countdown_page(countdown_summary(date(2026, 12, 1)))
        self.assertIn('new Date("2026-12-25T00:00:00")', page)

    def test_page_omits_nonce_by_default(self) -> None:
        page = countdown_page(countdown_summary(date(2026, 12, 1)))
        self.assertNotIn("nonce=", page)

    def test_page_applies_nonce_to_script_when_given(self) -> None:
        page = countdown_page(countdown_summary(date(2026, 12, 1)), nonce="abc123")
        self.assertIn('<script nonce="abc123">', page)


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Pin the clock so the suite is deterministic whatever the real date is.
        cls.server = create_server("127.0.0.1", 0, today_provider=lambda: FIXED_TODAY)
        cls.host, cls.port = cls.server.server_address[:2]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def _request(self, path: str, method: str = "GET") -> tuple[int, HTTPMessage, str]:
        request = urllib.request.Request(
            f"http://{self.host}:{self.port}{path}", method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.headers, response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            return error.code, error.headers, error.read().decode("utf-8")

    def _get(self, path: str) -> tuple[int, str, str]:
        status, headers, body = self._request(path)
        return status, headers.get("Content-Type", ""), body

    def test_root_serves_countdown_page(self) -> None:
        status, content_type, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", content_type)
        # Date-stable invariants only. The caption copy (plural/singular/Merry
        # Christmas) is covered by the pure countdown_page tests, not here.
        self.assertIn("<title>Christmas Countdown</title>", body)
        self.assertIn(">18</div>", body)

    def test_api_returns_countdown_json(self) -> None:
        status, content_type, body = self._get("/api/countdown")
        self.assertEqual(status, 200)
        self.assertIn("application/json", content_type)
        payload = json.loads(body)
        self.assertIn("working_days", payload)
        self.assertIn("target", payload)
        # Deterministic because the server clock is pinned to FIXED_TODAY.
        self.assertEqual(payload["target"], "2026-12-25")
        self.assertEqual(payload["working_days"], 18)

    def test_health_endpoint(self) -> None:
        status, content_type, body = self._get("/healthz")
        self.assertEqual(status, 200)
        self.assertIn("application/json", content_type)
        self.assertEqual(json.loads(body), {"status": "ok"})

    def test_unknown_path_returns_404(self) -> None:
        status, _, body = self._get("/missing")
        self.assertEqual(status, 404)
        self.assertIn("Not Found", body)

    def test_query_string_is_ignored(self) -> None:
        status, _, body = self._get("/?year=2026")
        self.assertEqual(status, 200)
        self.assertIn("Christmas Countdown", body)

    def test_security_headers_are_sent(self) -> None:
        status, headers, _ = self._request("/")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
        csp = headers.get("Content-Security-Policy", "")
        self.assertIn("default-src 'none'", csp)
        # The inline script is authorised by a nonce, not 'unsafe-inline'.
        self.assertIn("script-src 'nonce-", csp)
        self.assertNotIn("script-src 'unsafe-inline'", csp)

    def test_head_request_returns_headers_without_body(self) -> None:
        status, headers, body = self._request("/", method="HEAD")
        self.assertEqual(status, 200)
        self.assertEqual(body, "")
        self.assertGreater(int(headers.get("Content-Length", "0")), 0)
        self.assertIn("text/html", headers.get("Content-Type", ""))


class ChristmasDayServerTests(unittest.TestCase):
    """End-to-end check of the Christmas-Day copy using a pinned clock."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.server = create_server(
            "127.0.0.1", 0, today_provider=lambda: date(2026, 12, 25)
        )
        cls.host, cls.port = cls.server.server_address[:2]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def test_root_shows_merry_christmas(self) -> None:
        with urllib.request.urlopen(
            f"http://{self.host}:{self.port}/", timeout=5
        ) as response:
            body = response.read().decode("utf-8")
        self.assertEqual(response.status, 200)
        self.assertIn("Merry Christmas!", body)


class WeatherCodeTests(unittest.TestCase):
    """Tests for weather code translation."""

    def test_clear_sky(self) -> None:
        self.assertEqual(translate_weather_code(0), "Clear sky")

    def test_mainly_clear(self) -> None:
        self.assertEqual(translate_weather_code(1), "Mainly clear")

    def test_partly_cloudy(self) -> None:
        self.assertEqual(translate_weather_code(2), "Partly cloudy")

    def test_overcast(self) -> None:
        self.assertEqual(translate_weather_code(3), "Overcast")

    def test_fog(self) -> None:
        self.assertEqual(translate_weather_code(45), "Fog")

    def test_rain(self) -> None:
        self.assertEqual(translate_weather_code(61), "Slight rain")
        self.assertEqual(translate_weather_code(63), "Moderate rain")
        self.assertEqual(translate_weather_code(65), "Heavy rain")

    def test_snow(self) -> None:
        self.assertEqual(translate_weather_code(71), "Slight snow fall")
        self.assertEqual(translate_weather_code(73), "Moderate snow fall")
        self.assertEqual(translate_weather_code(75), "Heavy snow fall")

    def test_thunderstorm(self) -> None:
        self.assertEqual(translate_weather_code(95), "Thunderstorm")
        self.assertEqual(translate_weather_code(96), "Thunderstorm with slight hail")
        self.assertEqual(translate_weather_code(99), "Thunderstorm with heavy hail")

    def test_unknown_code(self) -> None:
        self.assertEqual(translate_weather_code(999), "Unknown")

    def test_all_codes_have_descriptions(self) -> None:
        for code in WEATHER_CODES:
            result = translate_weather_code(code)
            self.assertIsInstance(result, str)
            self.assertGreater(len(result), 0)


class WeatherCacheTests(unittest.TestCase):
    """Tests for thread-safe weather cache with TTL."""

    def test_cache_stores_and_retrieves(self) -> None:
        cache = WeatherCache(ttl=60)
        cache.set(37.98, 23.72, {"temp": 25})
        result = cache.get(37.98, 23.72)
        self.assertEqual(result, {"temp": 25})

    def test_cache_returns_none_for_miss(self) -> None:
        cache = WeatherCache(ttl=60)
        self.assertIsNone(cache.get(37.98, 23.72))

    def test_cache_expires_after_ttl(self) -> None:
        cache = WeatherCache(ttl=0)  # TTL=0 means always expired
        cache.set(37.98, 23.72, {"temp": 25})
        self.assertIsNone(cache.get(37.98, 23.72))

    def test_cache_separates_by_coordinates(self) -> None:
        cache = WeatherCache(ttl=60)
        cache.set(37.98, 23.72, {"temp": 25})
        cache.set(40.00, 24.00, {"temp": 20})
        self.assertEqual(cache.get(37.98, 23.72), {"temp": 25})
        self.assertEqual(cache.get(40.00, 24.00), {"temp": 20})

    def test_cache_clear(self) -> None:
        cache = WeatherCache(ttl=60)
        cache.set(37.98, 23.72, {"temp": 25})
        cache.clear()
        self.assertIsNone(cache.get(37.98, 23.72))

    def test_cache_thread_safety(self) -> None:
        cache = WeatherCache(ttl=60)
        errors = []

        def writer() -> None:
            for i in range(100):
                cache.set(37.98, 23.72, {"temp": i})

        def reader() -> None:
            for _ in range(100):
                try:
                    cache.get(37.98, 23.72)
                except Exception as exc:
                    errors.append(exc)

        threads = [threading.Thread(target=writer) for _ in range(5)]
        threads += [threading.Thread(target=reader) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        self.assertEqual(errors, [])


class FetchWeatherTests(unittest.TestCase):
    """Tests for Open-Meteo API integration."""

    def test_fetch_weather_returns_expected_keys(self) -> None:
        try:
            result = fetch_weather()
            self.assertIn("temperature", result)
            self.assertIn("windspeed", result)
            self.assertIn("winddirection", result)
            self.assertIn("weathercode", result)
            self.assertIn("description", result)
            self.assertIn("latitude", result)
            self.assertIn("longitude", result)
        except (urllib.error.URLError, OSError):
            self.skipTest("Open-Meteo API unreachable")

    def test_fetch_weather_default_location(self) -> None:
        try:
            result = fetch_weather()
            self.assertEqual(result["latitude"], 37.9838)
            self.assertEqual(result["longitude"], 23.7275)
        except (urllib.error.URLError, OSError):
            self.skipTest("Open-Meteo API unreachable")

    def test_fetch_weather_custom_location(self) -> None:
        try:
            result = fetch_weather(lat=51.5074, lon=-0.1278)
            self.assertEqual(result["latitude"], 51.5074)
            self.assertEqual(result["longitude"], -0.1278)
        except (urllib.error.URLError, OSError):
            self.skipTest("Open-Meteo API unreachable")

    def test_fetch_weather_description_matches_code(self) -> None:
        try:
            result = fetch_weather()
            code = result["weathercode"]
            description = result["description"]
            expected = WEATHER_CODES.get(code, "Unknown")
            self.assertEqual(description, expected)
        except (urllib.error.URLError, OSError):
            self.skipTest("Open-Meteo API unreachable")

    def test_fetch_weather_caches_result(self) -> None:
        from christmas_countdown import _weather_cache

        _weather_cache.clear()
        try:
            result1 = fetch_weather()
            result2 = fetch_weather()
            self.assertEqual(result1, result2)
        except (urllib.error.URLError, OSError):
            self.skipTest("Open-Meteo API unreachable")
        finally:
            _weather_cache.clear()

    def test_fetch_weather_invalid_api_url(self) -> None:
        import christmas_countdown
        from unittest.mock import patch

        def mock_urlopen(*args, **kwargs):
            raise urllib.error.URLError("Connection refused")

        original_url = christmas_countdown.WEATHER_API_URL
        try:
            christmas_countdown._weather_cache.clear()
            christmas_countdown.WEATHER_API_URL = "https://invalid.example.com/weather"
            with patch(
                "christmas_countdown.urllib.request.urlopen", side_effect=mock_urlopen
            ):
                with self.assertRaises(urllib.error.URLError):
                    fetch_weather(timeout=1.0)
        finally:
            christmas_countdown.WEATHER_API_URL = original_url
            christmas_countdown._weather_cache.clear()

    def test_fetch_weather_success_mocked(self) -> None:
        import christmas_countdown
        from unittest.mock import patch

        class FakeResponse:
            def __init__(self, payload: object) -> None:
                self._body = json.dumps(payload).encode("utf-8")

            def read(self) -> bytes:
                return self._body

            def __enter__(self) -> FakeResponse:
                return self

            def __exit__(self, *args: object) -> None:
                return None

        payload = {
            "current_weather": {
                "temperature": 18.0,
                "windspeed": 8.5,
                "winddirection": 270,
                "weathercode": 61,
            },
            "daily": {
                "time": ["2026-09-21", "2026-09-22", "2026-09-23"],
                "weathercode": [61, 1, 1],
                "temperature_2m_max": [20.0, 22.0, 23.0],
                "temperature_2m_min": [12.0, 13.0, 14.0],
                "precipitation_sum": [2.5, 0.0, 0.0],
                "precipitation_probability_max": [80, 10, 5],
                "windspeed_10m_max": [15.0, 10.0, 8.0],
            },
        }
        expected_daily = [
            {
                "date": "2026-09-21",
                "weathercode": 61,
                "description": "Slight rain",
                "temp_max": 20.0,
                "temp_min": 12.0,
                "precipitation_sum": 2.5,
                "precipitation_probability": 80,
                "windspeed_max": 15.0,
            },
            {
                "date": "2026-09-22",
                "weathercode": 1,
                "description": "Mainly clear",
                "temp_max": 22.0,
                "temp_min": 13.0,
                "precipitation_sum": 0.0,
                "precipitation_probability": 10,
                "windspeed_max": 10.0,
            },
            {
                "date": "2026-09-23",
                "weathercode": 1,
                "description": "Mainly clear",
                "temp_max": 23.0,
                "temp_min": 14.0,
                "precipitation_sum": 0.0,
                "precipitation_probability": 5,
                "windspeed_max": 8.0,
            },
        ]
        try:
            christmas_countdown._weather_cache.clear()
            with patch(
                "christmas_countdown.urllib.request.urlopen",
                return_value=FakeResponse(payload),
            ) as mock_urlopen:
                result = fetch_weather(lat=1.0, lon=2.0)
                cached = fetch_weather(lat=1.0, lon=2.0)
            cached_at = result.pop("cached_at")
            self.assertIsInstance(cached_at, str)
            self.assertEqual(
                result,
                {
                    "temperature": 18.0,
                    "windspeed": 8.5,
                    "winddirection": 270,
                    "weathercode": 61,
                    "description": "Slight rain",
                    "latitude": 1.0,
                    "longitude": 2.0,
                    "current": {
                        "temperature": 18.0,
                        "windspeed": 8.5,
                        "winddirection": 270,
                        "weathercode": 61,
                        "description": "Slight rain",
                    },
                    "daily": expected_daily,
                    "weekly": [
                        {
                            "week_start": "2026-09-21",
                            "days": 3,
                            "temp_avg": 17.3,
                            "precipitation_total": 2.5,
                            "weather_dominant": 1,
                            "description": "Mainly clear",
                        }
                    ],
                    "monthly": [
                        {
                            "month": "2026-09",
                            "days": 3,
                            "temp_avg": 17.3,
                            "precipitation_total": 2.5,
                            "weather_dominant": 1,
                            "description": "Mainly clear",
                        }
                    ],
                    "source": "open-meteo",
                },
            )
            # Second call is served from the cache: urlopen runs only once.
            self.assertEqual(cached, result)
            self.assertEqual(mock_urlopen.call_count, 1)
        finally:
            christmas_countdown._weather_cache.clear()

    def test_fetch_weather_rejects_malformed_payloads(self) -> None:
        import christmas_countdown
        from unittest.mock import patch

        class FakeResponse:
            def __init__(self, payload: object) -> None:
                self._body = json.dumps(payload).encode("utf-8")

            def read(self) -> bytes:
                return self._body

            def __enter__(self) -> FakeResponse:
                return self

            def __exit__(self, *args: object) -> None:
                return None

        for bad_payload in ({}, {"current_weather": None}, [1, 2, 3]):
            try:
                christmas_countdown._weather_cache.clear()
                with patch(
                    "christmas_countdown.urllib.request.urlopen",
                    return_value=FakeResponse(bad_payload),
                ):
                    with self.assertRaises(ValueError):
                        fetch_weather(lat=1.0, lon=2.0)
            finally:
                christmas_countdown._weather_cache.clear()


class WeatherSummaryTests(unittest.TestCase):
    """Tests for weather summary with error handling."""

    def test_weather_summary_success(self) -> None:
        try:
            result = weather_summary()
            self.assertIn("temperature", result)
            self.assertNotIn("error", result)
        except (urllib.error.URLError, OSError):
            self.skipTest("Open-Meteo API unreachable")

    def test_weather_summary_error_handling(self) -> None:
        import christmas_countdown
        from unittest.mock import patch

        def mock_urlopen(*args, **kwargs):
            raise urllib.error.URLError("Connection refused")

        original_url = christmas_countdown.WEATHER_API_URL
        try:
            christmas_countdown._weather_cache.clear()
            christmas_countdown.WEATHER_API_URL = "https://invalid.example.com/weather"
            with patch(
                "christmas_countdown.urllib.request.urlopen", side_effect=mock_urlopen
            ):
                result = weather_summary(timeout=1.0)
            self.assertIn("error", result)
            self.assertIn("latitude", result)
            self.assertIn("longitude", result)
        finally:
            christmas_countdown.WEATHER_API_URL = original_url
            christmas_countdown._weather_cache.clear()

    def test_weather_summary_malformed_payloads_return_error(self) -> None:
        import christmas_countdown
        from unittest.mock import patch

        class FakeResponse:
            def __init__(self, payload: object) -> None:
                self._body = json.dumps(payload).encode("utf-8")

            def read(self) -> bytes:
                return self._body

            def __enter__(self) -> FakeResponse:
                return self

            def __exit__(self, *args: object) -> None:
                return None

        for bad_payload in ({}, {"current_weather": None}, [1, 2, 3]):
            try:
                christmas_countdown._weather_cache.clear()
                with patch(
                    "christmas_countdown.urllib.request.urlopen",
                    return_value=FakeResponse(bad_payload),
                ):
                    result = weather_summary(lat=1.0, lon=2.0)
                self.assertIn("error", result)
                self.assertEqual(result["latitude"], 1.0)
                self.assertEqual(result["longitude"], 2.0)
            finally:
                christmas_countdown._weather_cache.clear()

    def test_weather_summary_json_serialisable(self) -> None:
        try:
            result = weather_summary()
            json.dumps(result)
        except (urllib.error.URLError, OSError):
            self.skipTest("Open-Meteo API unreachable")


def _fake_weather_payload() -> dict:
    daily = [
        {
            "date": f"2026-12-{day:02d}",
            "weathercode": 1,
            "description": "Mainly clear",
            "temp_max": 20.0,
            "temp_min": 12.0,
            "precipitation_sum": 0.0,
            "precipitation_probability": 10,
            "windspeed_max": 10.0,
        }
        for day in range(1, 9)
    ]
    return {
        "temperature": 18.0,
        "windspeed": 8.5,
        "winddirection": 270,
        "weathercode": 1,
        "description": "Mainly clear",
        "latitude": 37.9838,
        "longitude": 23.7275,
        "current": {
            "temperature": 18.0,
            "windspeed": 8.5,
            "winddirection": 270,
            "weathercode": 1,
            "description": "Mainly clear",
        },
        "daily": daily,
        "weekly": [
            {
                "week_start": "2026-12-01",
                "days": 7,
                "temp_avg": 16.0,
                "precipitation_total": 0.0,
                "weather_dominant": 1,
                "description": "Mainly clear",
            },
            {
                "week_start": "2026-12-08",
                "days": 1,
                "temp_avg": 16.0,
                "precipitation_total": 0.0,
                "weather_dominant": 1,
                "description": "Mainly clear",
            },
        ],
        "monthly": [
            {
                "month": "2026-12",
                "days": 8,
                "temp_avg": 16.0,
                "precipitation_total": 0.0,
                "weather_dominant": 1,
                "description": "Mainly clear",
            }
        ],
        "source": "open-meteo",
        "cached_at": "2026-01-01T00:00:00+00:00",
    }


class ParseWeatherCoordsTests(unittest.TestCase):
    def test_defaults_when_no_query(self) -> None:
        self.assertEqual(_parse_weather_coords(""), (37.9838, 23.7275))

    def test_valid_overrides(self) -> None:
        self.assertEqual(_parse_weather_coords("lat=51.5&lon=-0.12"), (51.5, -0.12))

    def test_rejects_non_numeric(self) -> None:
        self.assertIsNone(_parse_weather_coords("lat=abc&lon=10"))

    def test_rejects_out_of_range(self) -> None:
        self.assertIsNone(_parse_weather_coords("lat=91&lon=0"))
        self.assertIsNone(_parse_weather_coords("lat=0&lon=181"))
        self.assertIsNone(_parse_weather_coords("lat=-91&lon=0"))

    def test_fetch_weather_rejects_out_of_range_directly(self) -> None:
        with self.assertRaises(ValueError):
            fetch_weather(lat=91.0, lon=0.0)
        with self.assertRaises(ValueError):
            fetch_weather(lat=0.0, lon=200.0)


class RenderWeatherSectionTests(unittest.TestCase):
    def test_full_section_has_all_blocks(self) -> None:
        html = _render_weather_section(_fake_weather_payload())
        self.assertIn('class="weather"', html)
        self.assertIn('class="weather-current"', html)
        self.assertIn("18.0&deg;C".replace("&deg;", "°") if False else "18.0°C", html)
        self.assertIn("7-day forecast", html)
        self.assertEqual(html.count('class="forecast-card"'), 7)
        self.assertIn("Weekly summary", html)
        self.assertIn("Monthly summary", html)
        self.assertIn("CC BY 4.0", html)
        self.assertIn("open-meteo", html)

    def test_no_client_side_fetch(self) -> None:
        html = _render_weather_section(_fake_weather_payload())
        self.assertNotIn("fetch(", html)
        self.assertNotIn("XMLHttpRequest", html)
        self.assertNotIn("api.open-meteo.com", html)

    def test_error_and_none_fallback(self) -> None:
        for bad in (None, {"error": "boom", "latitude": 1.0, "longitude": 2.0}):
            html = _render_weather_section(bad)  # type: ignore[arg-type]
            self.assertIn("Weather currently unavailable", html)
            self.assertNotIn("fetch(", html)
        # An empty dict is not an error payload: it renders the section
        # skeleton with per-block fallbacks rather than crashing.
        html = _render_weather_section({})
        self.assertIn("Athens weather", html)
        self.assertIn("Forecast currently unavailable", html)

    def test_escaping(self) -> None:
        payload = _fake_weather_payload()
        payload["current"]["description"] = '<script>alert("x")</script>'  # type: ignore[index]
        html = _render_weather_section(payload)
        self.assertNotIn('<script>alert("x")</script>', html)
        self.assertIn("&lt;script&gt;", html)

    def test_page_embeds_weather_below_facts(self) -> None:
        page = countdown_page(countdown_summary(date(2026, 12, 1)), weather=_fake_weather_payload())
        self.assertGreater(page.find('class="weather"'), page.find('class="facts"'))
        self.assertIn("CC BY 4.0", page)
        self.assertNotIn("fetch(", page)

    def test_weather_icon_helper(self) -> None:
        self.assertEqual(weather_icon_for_code(0), "\u2600\ufe0f")
        self.assertEqual(weather_icon_for_code(999), "\u2753")
        self.assertEqual(weather_icon_for_code(None), "\u2753")


class WeatherApiRouteTests(unittest.TestCase):
    """Route-level tests for /api/weather with a mocked upstream."""

    @classmethod
    def setUpClass(cls) -> None:
        import christmas_countdown

        cls._mod = christmas_countdown
        cls._mod._weather_cache.clear()

        class FakeResponse:
            def __init__(self, payload: object) -> None:
                self._body = json.dumps(payload).encode("utf-8")

            def read(self) -> bytes:
                return self._body

            def __enter__(self) -> FakeResponse:
                return self

            def __exit__(self, *args: object) -> None:
                return None

        cls._payload = {
            "current_weather": {
                "temperature": 18.0,
                "windspeed": 8.5,
                "winddirection": 270,
                "weathercode": 1,
            },
            "daily": {
                "time": ["2026-12-01", "2026-12-02"],
                "weathercode": [1, 1],
                "temperature_2m_max": [20.0, 21.0],
                "temperature_2m_min": [12.0, 13.0],
                "precipitation_sum": [0.0, 0.0],
                "precipitation_probability_max": [10, 5],
                "windspeed_10m_max": [10.0, 9.0],
            },
        }

        from unittest.mock import patch

        real_urlopen = urllib.request.urlopen
        cls._upstream_calls: list[str] = []

        def _fake_urlopen(request, timeout=5, *args, **kwargs):
            url = request.full_url if isinstance(request, urllib.request.Request) else str(request)
            if "open-meteo" in url or "invalid.example.com" in url:
                cls._upstream_calls.append(url)
                return FakeResponse(cls._payload)
            return real_urlopen(request, timeout=timeout, *args, **kwargs)

        cls._patcher = patch(
            "christmas_countdown.urllib.request.urlopen",
            side_effect=_fake_urlopen,
        )
        cls._mock = cls._patcher.start()
        cls.server = create_server("127.0.0.1", 0, today_provider=lambda: FIXED_TODAY)
        cls.host, cls.port = cls.server.server_address[:2]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls._patcher.stop()
        cls._mod._weather_cache.clear()

    def _request(self, path: str, method: str = "GET") -> tuple[int, HTTPMessage, str]:
        request = urllib.request.Request(
            f"http://{self.host}:{self.port}{path}", method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, response.headers, response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            return error.code, error.headers, error.read().decode("utf-8")

    def test_weather_endpoint_returns_full_shape(self) -> None:
        status, headers, body = self._request("/api/weather")
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers.get("Content-Type", ""))
        payload = json.loads(body)
        for key in ("current", "daily", "weekly", "monthly", "source", "cached_at"):
            self.assertIn(key, payload)

    def test_weather_endpoint_rejects_bad_coords(self) -> None:
        status, _, body = self._request("/api/weather?lat=999&lon=0")
        self.assertEqual(status, 400)
        self.assertIn("Invalid coordinates", json.loads(body)["error"])

    def test_weather_endpoint_head_and_security_headers(self) -> None:
        status, headers, body = self._request("/api/weather", method="HEAD")
        self.assertEqual(status, 200)
        self.assertEqual(body, "")
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
        csp = headers.get("Content-Security-Policy", "")
        self.assertIn("default-src 'none'", csp)
        self.assertIn("script-src 'none'", csp)

    def test_weather_endpoint_cache_hit(self) -> None:
        self._mod._weather_cache.clear()
        self._upstream_calls.clear()
        self._request("/api/weather?lat=10&lon=20")
        self._request("/api/weather?lat=10&lon=20")
        self.assertEqual(len(self._upstream_calls), 1)

    def test_root_embeds_server_side_weather(self) -> None:
        status, _, body = self._request("/")
        self.assertEqual(status, 200)
        self.assertIn('class="weather"', body)
        self.assertIn("CC BY 4.0", body)
        self.assertNotIn("fetch(", body)


if __name__ == "__main__":
    unittest.main()
