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
    countdown_page,
    countdown_summary,
    create_server,
    is_working_day,
    next_christmas,
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


if __name__ == "__main__":
    unittest.main()
