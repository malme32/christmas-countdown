#!/usr/bin/env python3
"""A tiny, dependency-free Christmas countdown web app.

Serves a page with a countdown widget that shows how many *working days*
(Monday-Friday) remain until Christmas Day after deducting the Greek public
(bank) holidays that fall in the period, alongside the remaining calendar time.
A second page renders a full month-by-month calendar highlighting weekends,
bank holidays, today and Christmas Day. The same numbers are exposed as JSON.
Built only on the Python standard library.

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
    Monday and Holy Spirit Monday).
    """
    easter = orthodox_easter(year)
    holidays = {
        date(year, month, day): name
        for (month, day), name in GREEK_FIXED_HOLIDAYS.items()
    }
    holidays.update(
        {
            easter - timedelta(days=48): "Clean Monday",
            easter - timedelta(days=2): "Good Friday",
            easter: "Easter Sunday",
            easter + timedelta(days=1): "Easter Monday",
            easter + timedelta(days=50): "Holy Spirit Monday",
        }
    )
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


def countdown_page(summary: dict[str, object], nonce: str | None = None) -> str:
    """Return the HTML document for the Christmas countdown widget.

    When ``nonce`` is provided it is added to the inline ``<script>`` tag so the
    matching ``Content-Security-Policy`` can avoid ``script-src 'unsafe-inline'``.
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
        headline = str(remaining_days)
        caption = (
            f"{noun} until Christmas Day - {_target_label(target)} "
            f"({working_days} weekdays minus {bank_holiday_days} Greek bank holidays)"
        )

    script_nonce = f' nonce="{escape(nonce)}"' if nonce else ""

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
    counted = {date.fromisoformat(str(item["date"])) for item in holidays}

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
            body = countdown_page(countdown_summary(self._today()), nonce=nonce).encode("utf-8")
            return 200, body, "text/html; charset=utf-8", _content_security_policy(nonce)
        if path == "/calendar":
            body = calendar_page(countdown_summary(self._today())).encode("utf-8")
            return 200, body, "text/html; charset=utf-8", _content_security_policy()
        if path == "/api/countdown":
            body = json.dumps(countdown_summary(self._today())).encode("utf-8")
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
