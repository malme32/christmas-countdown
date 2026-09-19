#!/usr/bin/env python3
"""Show the next matches for Olympiacos FC (Piraeus).

Live data is fetched from TheSportsDB's public API. Because that free endpoint
can return few or no future events, a verified snapshot of the upcoming
fixtures is bundled as a fallback so the command always has something useful to
show (use ``--offline`` to force the fallback).

Usage:
    python3 olympiakos_fixtures.py
    python3 olympiakos_fixtures.py --limit 5 --json
    python3 olympiakos_fixtures.py --offline
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

TEAM_ID = "133754"
TEAM_NAME = "Olympiacos"
API_URL = "https://www.thesportsdb.com/api/v1/json/3/eventsnext.php?id={team_id}"
USER_AGENT = "olympiakos-fixtures/1.0 (+https://www.thesportsdb.com/free_sports_api)"

# Verified against https://www.olympiacos.org/en (matchcenter) and TheSportsDB
# on 2026-09-19. Times without a zone are the club's local kick-off time (EEST,
# UTC+3). Keep this list in sync when fixtures change.
FALLBACK_FIXTURES = [
    {
        "datetime_utc": "2026-09-20T14:00:00",
        "local_time": "17:00",
        "home": "Levadiakos",
        "away": "Olympiacos",
        "competition": "Greek Super League 1",
        "venue": "Levadia Municipal Stadium, Livadia",
        "source": "fallback",
    },
    {
        "datetime_utc": "2026-10-11T18:00:00",
        "local_time": "21:00",
        "home": "Olympiacos",
        "away": "Panathinaikos",
        "competition": "Greek Super League 1",
        "venue": "Stadio Georgios Karaiskakis, Piraeus",
        "source": "fallback",
    },
    {
        "datetime_utc": "2026-10-15T19:00:00",
        "local_time": "22:00",
        "home": "Marseille",
        "away": "Olympiacos",
        "competition": "UEFA Europa League",
        "venue": "Stade Velodrome, Marseille",
        "source": "fallback",
    },
    {
        "datetime_utc": "2026-10-17T15:00:00",
        "local_time": "18:00",
        "home": "Panetolikos",
        "away": "Olympiacos",
        "competition": "Greek Super League 1",
        "venue": "",
        "source": "fallback",
    },
    {
        "datetime_utc": "2026-10-22T16:00:00",
        "local_time": "19:00",
        "home": "Olympiacos",
        "away": "Sparta Prague",
        "competition": "UEFA Europa League",
        "venue": "Stadio Georgios Karaiskakis, Piraeus",
        "source": "fallback",
    },
    {
        "datetime_utc": "2026-10-24T15:00:00",
        "local_time": "18:00",
        "home": "Olympiacos",
        "away": "Kalamata",
        "competition": "Greek Super League 1",
        "venue": "Stadio Georgios Karaiskakis, Piraeus",
        "source": "fallback",
    },
    {
        "datetime_utc": "2026-10-28T17:00:00",
        "local_time": "19:00",
        "home": "GS Marko",
        "away": "Olympiacos",
        "competition": "Greek Cup",
        "venue": "",
        "source": "fallback",
    },
    {
        "datetime_utc": "2026-10-31T16:00:00",
        "local_time": "18:00",
        "home": "Kifisia",
        "away": "Olympiacos",
        "competition": "Greek Super League 1",
        "venue": "",
        "source": "fallback",
    },
    {
        "datetime_utc": "2026-11-05T17:45:00",
        "local_time": "19:45",
        "home": "Rennes",
        "away": "Olympiacos",
        "competition": "UEFA Europa League",
        "venue": "Roazhon Park, Rennes",
        "source": "fallback",
    },
    {
        "datetime_utc": "2026-11-07T16:00:00",
        "local_time": "18:00",
        "home": "Olympiacos",
        "away": "PAOK",
        "competition": "Greek Super League 1",
        "venue": "Stadio Georgios Karaiskakis, Piraeus",
        "source": "fallback",
    },
]


def fetch_next_matches(team_id: str = TEAM_ID, timeout: float = 20.0) -> list[dict]:
    """Return upcoming Olympiacos matches from TheSportsDB.

    Raises ``urllib.error.URLError`` or ``OSError`` if the API is unreachable.
    """
    request = urllib.request.Request(
        API_URL.format(team_id=team_id), headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return parse_events(payload)


def parse_events(payload: dict) -> list[dict]:
    """Convert a TheSportsDB payload into normalised fixture dicts."""
    events = payload.get("events") or []
    fixtures = []
    for event in events:
        fixtures.append(
            {
                "datetime_utc": event.get("strTimestamp") or event.get("dateEvent") or "",
                "local_time": (event.get("strTimeLocal") or "")[:5],
                "home": event.get("strHomeTeam") or "",
                "away": event.get("strAwayTeam") or "",
                "competition": event.get("strLeague") or "",
                "venue": event.get("strVenue") or "",
                "source": "thesportsdb",
            }
        )
    fixtures.sort(key=lambda fixture: fixture["datetime_utc"])
    return fixtures


def merge_fixtures(live: list[dict], fallback: list[dict]) -> list[dict]:
    """Combine live fixtures with the snapshot, de-duplicating by date and teams."""
    merged = list(live)
    seen = {(f["datetime_utc"], f["home"], f["away"]) for f in live}
    for fixture in fallback:
        key = (fixture["datetime_utc"], fixture["home"], fixture["away"])
        if key not in seen:
            merged.append(fixture)
            seen.add(key)
    merged.sort(key=lambda fixture: fixture["datetime_utc"])
    return merged


def next_matches(offline: bool = False, limit: int = 5) -> tuple[list[dict], str]:
    """Return ``(fixtures, source)`` preferring live data with fallback.

    ``source`` is ``"thesportsdb"`` when live data was used (merged with the
    bundled snapshot to fill gaps) and ``"fallback"`` otherwise.
    """
    if not offline:
        try:
            live = fetch_next_matches()
            if live:
                merged = merge_fixtures(live, FALLBACK_FIXTURES)
                return merged[:limit], "thesportsdb"
        except (urllib.error.URLError, OSError, ValueError):
            pass
    return FALLBACK_FIXTURES[:limit], "fallback"


def format_match(fixture: dict) -> str:
    """Render a single fixture as a human-readable line."""
    when = fixture["datetime_utc"].replace("T", " ")[:16]
    if fixture.get("local_time"):
        when += f" (local {fixture['local_time']})"
    teams = f"{fixture['home']} vs {fixture['away']}"
    line = f"{when}  {teams}  [{fixture['competition']}]"
    if fixture.get("venue"):
        line += f" @ {fixture['venue']}"
    return line


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Next matches for Olympiacos FC")
    parser.add_argument("--limit", type=int, default=5, help="number of matches (default 5)")
    parser.add_argument("--offline", action="store_true", help="use the bundled snapshot")
    parser.add_argument("--json", action="store_true", help="output JSON")
    args = parser.parse_args(argv)

    fixtures, source = next_matches(offline=args.offline, limit=args.limit)
    if args.json:
        print(json.dumps({"team": TEAM_NAME, "source": source, "fixtures": fixtures}, indent=2))
    else:
        print(f"Next {len(fixtures)} {TEAM_NAME} matches (source: {source})")
        for fixture in fixtures:
            print("  " + format_match(fixture))
    return 0


if __name__ == "__main__":
    sys.exit(main())
