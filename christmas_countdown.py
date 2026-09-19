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
import sys
from collections.abc import Callable
from datetime import date, timedelta
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
CHRISTMAS_MONTH = 12
CHRISTMAS_DAY = 25
WORKING_WEEKDAYS = 5

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


def _target_label(target: str) -> str:
    """Format an ISO date as ``Friday, 25 December 2026``."""
    parsed = date.fromisoformat(target)
    return f"{parsed.strftime('%A')}, {parsed.day} {parsed.strftime('%B %Y')}"


def countdown_page(summary: dict[str, object]) -> str:
    """Return the HTML document for the Christmas countdown widget."""
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
        "    </div>\n"
        "  </main>\n"
        "  <script>\n"
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

    def _route(self) -> tuple[int, bytes, str]:
        """Map the request path to a ``(status, body, content_type)`` tuple."""
        path = self.path.split("?", 1)[0]
        if path == "/":
            body = countdown_page(countdown_summary(self._today())).encode("utf-8")
            return 200, body, "text/html; charset=utf-8"
        if path == "/api/countdown":
            body = json.dumps(countdown_summary(self._today())).encode("utf-8")
            return 200, body, "application/json; charset=utf-8"
        if path == "/healthz":
            return 200, b'{"status": "ok"}', "application/json; charset=utf-8"
        return 404, b"Not Found\n", "text/plain; charset=utf-8"

    def _handle(self, *, send_body: bool) -> None:
        status, body, content_type = self._route()
        self._respond(status, body, content_type, send_body=send_body)

    def _respond(
        self, status: int, body: bytes, content_type: str, *, send_body: bool = True
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
        )
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
