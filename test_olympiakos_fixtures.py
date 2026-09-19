import io
import json
import unittest
from unittest import mock

import olympiakos_fixtures as of


SAMPLE_PAYLOAD = {
    "events": [
        {
            "strTimestamp": "2026-10-15T19:00:00",
            "strTimeLocal": "22:00:00",
            "strHomeTeam": "Marseille",
            "strAwayTeam": "Olympiacos",
            "strLeague": "UEFA Europa League",
            "strVenue": "Stade Velodrome",
        },
        {
            "strTimestamp": "2026-09-20T14:00:00",
            "strTimeLocal": "17:00:00",
            "strHomeTeam": "Levadiakos",
            "strAwayTeam": "Olympiacos",
            "strLeague": "Greek Super League 1",
            "strVenue": "Levadia Municipal Stadium",
        },
    ]
}


class ParseEventsTests(unittest.TestCase):
    def test_parses_and_sorts_by_datetime(self):
        fixtures = of.parse_events(SAMPLE_PAYLOAD)
        self.assertEqual(len(fixtures), 2)
        self.assertEqual(fixtures[0]["home"], "Levadiakos")
        self.assertEqual(fixtures[0]["local_time"], "17:00")
        self.assertEqual(fixtures[1]["home"], "Marseille")
        self.assertEqual(fixtures[0]["source"], "thesportsdb")

    def test_handles_empty_payload(self):
        self.assertEqual(of.parse_events({}), [])
        self.assertEqual(of.parse_events({"events": None}), [])


class NextMatchesTests(unittest.TestCase):
    def test_offline_returns_fallback(self):
        fixtures, source = of.next_matches(offline=True, limit=3)
        self.assertEqual(source, "fallback")
        self.assertEqual(len(fixtures), 3)
        self.assertEqual(fixtures[0]["home"], "Levadiakos")
        self.assertEqual(fixtures[0]["away"], "Olympiacos")

    def test_live_data_preferred(self):
        with mock.patch.object(of, "fetch_next_matches", return_value=of.parse_events(SAMPLE_PAYLOAD)):
            fixtures, source = of.next_matches(limit=5)
        self.assertEqual(source, "thesportsdb")
        self.assertEqual(fixtures[0]["home"], "Levadiakos")

    def test_merge_appends_fallback_without_duplicates(self):
        live = of.parse_events(SAMPLE_PAYLOAD)
        merged = of.merge_fixtures(live, of.FALLBACK_FIXTURES)
        keys = [(f["datetime_utc"], f["home"], f["away"]) for f in merged]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(merged[0]["home"], "Levadiakos")
        self.assertEqual(merged[0]["source"], "thesportsdb")
        self.assertTrue(any(f["away"] == "Panathinaikos" for f in merged))

    def test_falls_back_when_api_fails(self):
        with mock.patch.object(of, "fetch_next_matches", side_effect=OSError("offline")):
            fixtures, source = of.next_matches(limit=2)
        self.assertEqual(source, "fallback")
        self.assertEqual(len(fixtures), 2)


class FetchTests(unittest.TestCase):
    def test_fetch_reads_json(self):
        raw = json.dumps(SAMPLE_PAYLOAD).encode("utf-8")
        fake_response = mock.MagicMock()
        fake_response.read.return_value = raw
        fake_response.__enter__ = mock.Mock(return_value=fake_response)
        fake_response.__exit__ = mock.Mock(return_value=False)
        with mock.patch.object(of.urllib.request, "urlopen", return_value=fake_response):
            fixtures = of.fetch_next_matches()
        self.assertEqual(fixtures[0]["away"], "Olympiacos")


class FormatTests(unittest.TestCase):
    def test_format_includes_teams_and_competition(self):
        line = of.format_match(of.FALLBACK_FIXTURES[0])
        self.assertIn("Levadiakos vs Olympiacos", line)
        self.assertIn("Greek Super League 1", line)
        self.assertIn("2026-09-20 14:00", line)


class CliTests(unittest.TestCase):
    def test_json_output_offline(self):
        buffer = io.StringIO()
        with mock.patch("sys.stdout", buffer):
            rc = of.main(["--offline", "--limit", "2", "--json"])
        self.assertEqual(rc, 0)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["source"], "fallback")
        self.assertEqual(len(payload["fixtures"]), 2)


if __name__ == "__main__":
    unittest.main()
