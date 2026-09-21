#!/usr/bin/env python3
"""Tests for christmas_countdown."""

from __future__ import annotations

import json
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date, timedelta
from http.client import HTTPMessage

from christmas_countdown import (
    WeatherCache,
    WEATHER_CODES,
    _dominant_weather_code,
    _parse_daily_forecast,
    _parse_weather_coords,
    _render_weather_section,
    aggregate_monthly,
    aggregate_weekly,
    bank_holidays_between,
    calendar_page,
    countdown_page,
    countdown_summary,
    create_server,
    datetime_now_utc_iso,
    fetch_weather,
    greek_holidays,
    is_working_day,
    months_between,
    next_christmas,
    orthodox_easter,
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


class OrthodoxEasterTests(unittest.TestCase):
    def test_known_dates(self) -> None:
        self.assertEqual(orthodox_easter(2023), date(2023, 4, 16))
        self.assertEqual(orthodox_easter(2024), date(2024, 5, 5))
        self.assertEqual(orthodox_easter(2025), date(2025, 4, 20))
        self.assertEqual(orthodox_easter(2026), date(2026, 4, 12))

    def test_always_a_sunday(self) -> None:
        for year in range(2000, 2031):
            self.assertEqual(orthodox_easter(year).weekday(), 6, year)


class GreekHolidayTests(unittest.TestCase):
    def test_fixed_holidays_are_present(self) -> None:
        holidays = greek_holidays(2026)
        self.assertEqual(holidays[date(2026, 1, 1)], "New Year's Day")
        self.assertEqual(holidays[date(2026, 3, 25)], "Independence Day")
        self.assertEqual(holidays[date(2026, 10, 28)], "Ochi Day")
        self.assertEqual(holidays[date(2026, 12, 25)], "Christmas Day")
        self.assertEqual(holidays[date(2026, 12, 26)], "Second Day of Christmas")

    def test_movable_holidays_follow_easter(self) -> None:
        easter = orthodox_easter(2026)
        holidays = greek_holidays(2026)
        self.assertEqual(holidays[easter - timedelta(days=48)], "Clean Monday")
        self.assertEqual(holidays[easter - timedelta(days=2)], "Good Friday")
        self.assertEqual(holidays[easter], "Easter Sunday")
        self.assertEqual(holidays[easter + timedelta(days=1)], "Easter Monday")
        self.assertEqual(holidays[easter + timedelta(days=50)], "Holy Spirit Monday")

    def test_clean_monday_and_holy_spirit_are_mondays(self) -> None:
        easter = orthodox_easter(2026)
        self.assertEqual((easter - timedelta(days=48)).weekday(), 0)
        self.assertEqual((easter + timedelta(days=50)).weekday(), 0)

    def test_labour_day_kept_when_it_is_a_working_day(self) -> None:
        # 1 May 2026 is a Friday and clashes with no other holiday.
        self.assertEqual(greek_holidays(2026)[date(2026, 5, 1)], "Labour Day")

    def test_labour_day_moves_off_a_weekend(self) -> None:
        # 1 May 2022 is a Sunday; observed on the next working day, Mon 2 May.
        holidays = greek_holidays(2022)
        self.assertNotIn(date(2022, 5, 1), holidays)
        self.assertEqual(holidays[date(2022, 5, 2)], "Labour Day (observed)")

    def test_labour_day_skips_another_holiday_when_moving(self) -> None:
        # 1 May 2021 is a Saturday and 3 May is Easter Monday, so it lands on
        # Tue 4 May. Same for 2027 (1 May Sat, Easter Sunday 2 May).
        self.assertEqual(
            greek_holidays(2021)[date(2021, 5, 4)], "Labour Day (observed)"
        )
        observed = greek_holidays(2027)
        self.assertNotIn(date(2027, 5, 1), observed)
        self.assertEqual(observed[date(2027, 5, 4)], "Labour Day (observed)")

    def test_observed_labour_day_is_always_a_working_day(self) -> None:
        for year in range(2000, 2031):
            for day, name in greek_holidays(year).items():
                if name.startswith("Labour Day"):
                    self.assertTrue(is_working_day(day), (year, day))


class BankHolidaysBetweenTests(unittest.TestCase):
    def test_returns_only_holidays_in_the_half_open_range(self) -> None:
        found = bank_holidays_between(date(2026, 1, 1), date(2026, 1, 6))
        self.assertEqual(found, [(date(2026, 1, 6), "Epiphany")])

    def test_includes_both_christmas_days_in_december(self) -> None:
        found = bank_holidays_between(date(2026, 12, 1), date(2026, 12, 31))
        self.assertEqual(
            found,
            [
                (date(2026, 12, 25), "Christmas Day"),
                (date(2026, 12, 26), "Second Day of Christmas"),
            ],
        )

    def test_empty_when_range_is_reversed_or_empty(self) -> None:
        self.assertEqual(bank_holidays_between(date(2026, 1, 6), date(2026, 1, 1)), [])
        self.assertEqual(bank_holidays_between(date(2026, 1, 6), date(2026, 1, 6)), [])

    def test_crosses_year_boundary(self) -> None:
        found = bank_holidays_between(date(2026, 12, 30), date(2027, 1, 2))
        self.assertEqual(found, [(date(2027, 1, 1), "New Year's Day")])


class MonthsBetweenTests(unittest.TestCase):
    def test_lists_every_month_inclusive(self) -> None:
        months = months_between(date(2026, 9, 19), date(2026, 12, 25))
        self.assertEqual(
            months,
            [date(2026, 9, 1), date(2026, 10, 1), date(2026, 11, 1), date(2026, 12, 1)],
        )

    def test_single_month(self) -> None:
        self.assertEqual(
            months_between(date(2026, 12, 1), date(2026, 12, 25)), [date(2026, 12, 1)]
        )

    def test_wraps_across_years(self) -> None:
        self.assertEqual(
            months_between(date(2026, 12, 26), date(2027, 2, 1)),
            [date(2026, 12, 1), date(2027, 1, 1), date(2027, 2, 1)],
        )


class CountdownSummaryTests(unittest.TestCase):
    def test_summary_mid_season(self) -> None:
        summary = countdown_summary(date(2026, 12, 1))
        self.assertEqual(summary["target"], "2026-12-25")
        self.assertEqual(summary["calendar_days"], 24)
        self.assertEqual(summary["working_days"], 18)
        self.assertEqual(summary["bank_holiday_days"], 1)
        self.assertEqual(summary["remaining_working_days"], 17)
        self.assertEqual(summary["weekend_days"], 6)
        self.assertEqual(summary["weeks"], 3)
        self.assertFalse(summary["is_christmas"])
        self.assertEqual(
            summary["holidays"],
            [{"date": "2026-12-25", "name": "Christmas Day", "working_day": True}],
        )

    def test_summary_deducts_all_bank_holidays_in_the_window(self) -> None:
        summary = countdown_summary(date(2026, 9, 19))
        self.assertEqual(summary["working_days"], 70)
        self.assertEqual(summary["bank_holiday_days"], 2)
        self.assertEqual(summary["remaining_working_days"], 68)
        names = [holiday["name"] for holiday in summary["holidays"]]
        self.assertEqual(names, ["Ochi Day", "Christmas Day"])

    def test_summary_on_christmas(self) -> None:
        summary = countdown_summary(date(2026, 12, 25))
        self.assertEqual(summary["calendar_days"], 0)
        self.assertEqual(summary["working_days"], 0)
        self.assertEqual(summary["remaining_working_days"], 0)
        self.assertTrue(summary["is_christmas"])

    def test_summary_after_christmas_targets_next_year(self) -> None:
        summary = countdown_summary(date(2026, 12, 26))
        self.assertEqual(summary["target"], "2027-12-25")
        self.assertEqual(summary["calendar_days"], 364)
        self.assertEqual(summary["working_days"], 260)
        self.assertEqual(summary["bank_holiday_days"], 9)
        self.assertEqual(summary["remaining_working_days"], 251)
        self.assertEqual(summary["weekend_days"], 104)

    def test_summary_is_json_serialisable(self) -> None:
        json.dumps(countdown_summary(date(2026, 12, 1)))


class CountdownPageTests(unittest.TestCase):
    def test_page_is_html(self) -> None:
        page = countdown_page(countdown_summary(date(2026, 12, 1)))
        self.assertTrue(page.lstrip().startswith("<!DOCTYPE html>"))
        self.assertIn("<title>Christmas Countdown</title>", page)

    def test_page_shows_remaining_working_days_and_target(self) -> None:
        page = countdown_page(countdown_summary(date(2026, 12, 1)))
        self.assertIn('id="working">17</div>', page)
        self.assertIn("working days until Christmas Day", page)
        self.assertIn("Friday, 25 December 2026", page)

    def test_page_deducts_bank_holidays(self) -> None:
        page = countdown_page(countdown_summary(date(2026, 12, 1)))
        self.assertIn("18 weekdays minus 1 Greek bank holiday", page)
        self.assertNotIn("1 Greek bank holidays", page)
        self.assertIn("Greek bank holidays before Christmas", page)
        self.assertIn("Christmas Day", page)

    def test_page_pluralises_multiple_bank_holidays(self) -> None:
        page = countdown_page(countdown_summary(date(2026, 9, 19)))
        self.assertIn("70 weekdays minus 2 Greek bank holidays", page)

    def test_page_links_to_full_calendar(self) -> None:
        page = countdown_page(countdown_summary(date(2026, 12, 1)))
        self.assertIn('href="/calendar"', page)

    def test_page_uses_singular_day_for_one(self) -> None:
        page = countdown_page(countdown_summary(date(2026, 12, 23)))
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


class CalendarPageTests(unittest.TestCase):
    def test_calendar_is_html(self) -> None:
        page = calendar_page(countdown_summary(date(2026, 9, 19)))
        self.assertTrue(page.lstrip().startswith("<!DOCTYPE html>"))
        self.assertIn("<title>Christmas Countdown Calendar</title>", page)

    def test_calendar_spans_every_month_to_christmas(self) -> None:
        page = calendar_page(countdown_summary(date(2026, 9, 19)))
        for month in ("September 2026", "October 2026", "November 2026", "December 2026"):
            self.assertIn(month, page)

    def test_calendar_marks_holidays_and_christmas(self) -> None:
        page = calendar_page(countdown_summary(date(2026, 9, 19)))
        self.assertIn("Ochi Day", page)
        self.assertIn("Christmas Day", page)
        self.assertIn('class="day holiday counted"', page)
        self.assertIn('class="day holiday counted christmas"', page)

    def test_calendar_shows_countdown_numbers(self) -> None:
        page = calendar_page(countdown_summary(date(2026, 9, 19)))
        self.assertIn("<b>68</b> working days remain", page)
        self.assertIn("<b>70</b>", page)
        self.assertIn("bank holidays", page)

    def test_calendar_only_badges_deducted_holidays(self) -> None:
        page = calendar_page(countdown_summary(date(2027, 1, 1)))
        # Easter Sunday 2 May 2027 and Assumption 15 Aug 2027 are weekend days:
        # highlighted as holidays but not counted/deducted.
        self.assertIn('class="day weekend holiday"', page)
        self.assertNotIn('class="day weekend holiday counted"', page)
        # 1 May 2027 is a Saturday, so Labour Day transfers to Tue 4 May and is
        # deducted.
        self.assertIn("Labour Day (observed)", page)
        self.assertIn('class="day holiday counted"', page)

    def test_calendar_has_no_script(self) -> None:
        page = calendar_page(countdown_summary(date(2026, 9, 19)))
        self.assertNotIn("<script", page)


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
        self.assertIn('id="working">17</div>', body)

    def test_api_returns_countdown_json(self) -> None:
        status, content_type, body = self._get("/api/countdown")
        self.assertEqual(status, 200)
        self.assertIn("application/json", content_type)
        payload = json.loads(body)
        self.assertIn("working_days", payload)
        self.assertIn("remaining_working_days", payload)
        self.assertIn("bank_holiday_days", payload)
        self.assertIn("target", payload)
        # Deterministic because the server clock is pinned to FIXED_TODAY.
        self.assertEqual(payload["target"], "2026-12-25")
        self.assertEqual(payload["working_days"], 18)
        self.assertEqual(payload["bank_holiday_days"], 1)
        self.assertEqual(payload["remaining_working_days"], 17)

    def test_calendar_endpoint_serves_html(self) -> None:
        status, content_type, body = self._get("/calendar")
        self.assertEqual(status, 200)
        self.assertIn("text/html", content_type)
        self.assertIn("<title>Christmas Countdown Calendar</title>", body)
        self.assertIn("December 2026", body)

    def test_calendar_response_is_script_free_under_csp(self) -> None:
        status, headers, body = self._request("/calendar")
        self.assertEqual(status, 200)
        csp = headers.get("Content-Security-Policy", "")
        self.assertIn("default-src 'none'", csp)
        self.assertIn("script-src 'none'", csp)
        self.assertNotIn("script-src 'unsafe-inline'", csp)
        self.assertNotIn("<script", body)

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
        self.assertIn("18.0°C", html)
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


def _make_daily(
    dates: list[str],
    code: int = 1,
    temp_max: float = 20.0,
    temp_min: float = 10.0,
    precip: float = 1.0,
) -> list[dict]:
    return [
        {
            "date": day,
            "weathercode": code,
            "description": "Mainly clear",
            "temp_max": temp_max,
            "temp_min": temp_min,
            "precipitation_sum": precip,
            "precipitation_probability": 10,
            "windspeed_max": 9.0,
        }
        for day in dates
    ]


class ParseDailyForecastTests(unittest.TestCase):
    def test_normalises_columns(self) -> None:
        payload_daily = {
            "time": ["2026-12-01", "2026-12-02"],
            "weathercode": [61, 1],
            "temperature_2m_max": [20.0, 22.0],
            "temperature_2m_min": [12.0, 13.0],
            "precipitation_sum": [2.5, 0.0],
            "precipitation_probability_max": [80, 10],
            "windspeed_10m_max": [15.0, 10.0],
        }
        daily = _parse_daily_forecast(payload_daily)
        self.assertEqual(len(daily), 2)
        self.assertEqual(daily[0]["description"], "Slight rain")
        self.assertEqual(daily[0]["precipitation_sum"], 2.5)
        self.assertEqual(daily[1]["windspeed_max"], 10.0)

    def test_missing_or_malformed_block_returns_empty(self) -> None:
        for bad in (None, {}, [], "nope", {"time": []}, {"time": "2026-12-01"}):
            self.assertEqual(_parse_daily_forecast(bad), [])  # type: ignore[arg-type]

    def test_ragged_columns_default_to_none(self) -> None:
        daily = _parse_daily_forecast({"time": ["2026-12-01"]})
        self.assertEqual(len(daily), 1)
        self.assertIsNone(daily[0]["weathercode"])
        self.assertEqual(daily[0]["description"], "Unknown")
        self.assertIsNone(daily[0]["temp_max"])
        self.assertIsNone(daily[0]["windspeed_max"])

    def test_non_string_dates_skipped(self) -> None:
        daily = _parse_daily_forecast(
            {"time": ["2026-12-01", 123, None], "weathercode": [1, 1, 1]}
        )
        self.assertEqual([entry["date"] for entry in daily], ["2026-12-01"])

    def test_non_integer_code_is_unknown(self) -> None:
        daily = _parse_daily_forecast({"time": ["2026-12-01"], "weathercode": ["1"]})
        self.assertIsNone(daily[0]["weathercode"])
        self.assertEqual(daily[0]["description"], "Unknown")


class DominantWeatherCodeTests(unittest.TestCase):
    def test_mode_wins(self) -> None:
        self.assertEqual(_dominant_weather_code([1, 61, 1, 3, 1]), 1)

    def test_tie_goes_to_first_seen(self) -> None:
        self.assertEqual(_dominant_weather_code([61, 1]), 61)
        self.assertEqual(_dominant_weather_code([1, 61]), 1)

    def test_empty_returns_none(self) -> None:
        self.assertIsNone(_dominant_weather_code([]))


class AggregateWeeklyTests(unittest.TestCase):
    def test_chunks_into_seven_day_weeks(self) -> None:
        dates = [f"2026-12-{day:02d}" for day in range(1, 9)]
        weeks = aggregate_weekly(_make_daily(dates))
        self.assertEqual(len(weeks), 2)
        self.assertEqual(weeks[0]["week_start"], "2026-12-01")
        self.assertEqual(weeks[0]["days"], 7)
        self.assertEqual(weeks[1]["week_start"], "2026-12-08")
        self.assertEqual(weeks[1]["days"], 1)

    def test_averages_and_totals(self) -> None:
        dates = [f"2026-12-{day:02d}" for day in range(1, 8)]
        weeks = aggregate_weekly(_make_daily(dates))
        self.assertEqual(weeks[0]["temp_avg"], 15.0)
        self.assertEqual(weeks[0]["precipitation_total"], 7.0)
        self.assertEqual(weeks[0]["weather_dominant"], 1)
        self.assertEqual(weeks[0]["description"], "Mainly clear")

    def test_missing_values_excluded(self) -> None:
        daily = _make_daily(["2026-12-01", "2026-12-02"])
        daily[1]["temp_max"] = None
        daily[1]["precipitation_sum"] = None
        weeks = aggregate_weekly(daily)
        self.assertEqual(weeks[0]["temp_avg"], 15.0)
        self.assertEqual(weeks[0]["precipitation_total"], 1.0)

    def test_empty_returns_empty(self) -> None:
        self.assertEqual(aggregate_weekly([]), [])


class AggregateMonthlyTests(unittest.TestCase):
    def test_groups_by_calendar_month_sorted(self) -> None:
        daily = _make_daily(["2027-01-01", "2026-12-30", "2026-12-31"])
        months = aggregate_monthly(daily)
        self.assertEqual([m["month"] for m in months], ["2026-12", "2027-01"])
        self.assertEqual(months[0]["days"], 2)
        self.assertEqual(months[1]["days"], 1)
        self.assertEqual(months[0]["temp_avg"], 15.0)
        self.assertEqual(months[0]["precipitation_total"], 2.0)

    def test_malformed_dates_bucketed_as_unknown(self) -> None:
        daily = _make_daily(["2026-12-01"])
        daily.append(
            {
                "date": None,
                "weathercode": 1,
                "description": "Mainly clear",
                "temp_max": 20.0,
                "temp_min": 10.0,
                "precipitation_sum": 0.0,
                "precipitation_probability": 0,
                "windspeed_max": 5.0,
            }
        )
        months = aggregate_monthly(daily)
        self.assertEqual([m["month"] for m in months], ["2026-12", "unknown"])

    def test_empty_returns_empty(self) -> None:
        self.assertEqual(aggregate_monthly([]), [])


class WeatherCacheEvictionTests(unittest.TestCase):
    def test_oldest_entry_evicted_when_bound_exceeded(self) -> None:
        cache = WeatherCache(ttl=60, max_entries=1)
        cache.set(1.0, 1.0, {"temp": 1})
        cache.set(2.0, 2.0, {"temp": 2})
        self.assertIsNone(cache.get(1.0, 1.0))
        self.assertEqual(cache.get(2.0, 2.0), {"temp": 2})

    def test_default_cache_stores_many_entries(self) -> None:
        cache = WeatherCache(ttl=60)
        for i in range(10):
            cache.set(float(i), float(i), {"temp": i})
        for i in range(10):
            self.assertEqual(cache.get(float(i), float(i)), {"temp": i})


class DatetimeNowUtcIsoTests(unittest.TestCase):
    def test_returns_timezone_aware_iso_string(self) -> None:
        from datetime import datetime

        parsed = datetime.fromisoformat(datetime_now_utc_iso())
        self.assertIsNotNone(parsed.tzinfo)


if __name__ == "__main__":
    unittest.main()
