# Christmas working-days countdown

`christmas_countdown.py` is a dependency-free web app built on the Python
standard library's `http.server`. It serves a Christmas countdown widget whose
headline number is the remaining **working days** (Monday-Friday) until
Christmas Day **after deducting the Greek public (bank) holidays** that fall in
the period. It also renders a full month-by-month calendar and exposes the same
numbers as JSON.

## Usage

```bash
python3 christmas_countdown.py                    # http://127.0.0.1:8000/
python3 christmas_countdown.py --port 8080        # custom port
python3 christmas_countdown.py --host 0.0.0.0     # all interfaces
```

Then open <http://127.0.0.1:8000/> or:

```bash
curl http://127.0.0.1:8000/                  # HTML countdown widget
curl http://127.0.0.1:8000/calendar          # full month-by-month calendar
curl http://127.0.0.1:8000/api/countdown     # JSON numbers
curl http://127.0.0.1:8000/api/weather       # JSON weather (current/daily/weekly/monthly)
curl "http://127.0.0.1:8000/api/weather?lat=51.5&lon=-0.12"  # custom location
curl http://127.0.0.1:8000/healthz           # health check
```

## Greek bank holidays

The holiday set is computed deterministically from the calendar (no data files
or network access):

- **Fixed**: 1 Jan (New Year's Day), 6 Jan (Epiphany), 25 Mar (Independence
  Day), 1 May (Labour Day), 15 Aug (Assumption), 28 Oct (Ochi Day),
  25 Dec (Christmas Day) and 26 Dec (Second Day of Christmas).
- **Movable** (relative to Orthodox Easter Sunday, computed with the Meeus
  Julian algorithm): Clean Monday (Easter - 48 days), Good Friday (Easter - 2),
  Easter Sunday, Easter Monday (Easter + 1) and Holy Spirit Monday (Easter + 50).
- **Labour Day transfer**: when 1 May falls on a weekend or coincides with
  another public holiday, Greek law moves it to the next working day that is
  not already a holiday (e.g. 2022 → Mon 2 May, 2021 and 2027 → Tue 4 May after
  Easter Monday). The observed date is returned instead of 1 May.

Only holidays that fall on a working day are deducted from the countdown; those
that land at the weekend are listed (and shown in the calendar) but do not
change the total.

## Weather feature

The countdown page includes a **server-rendered weather section** showing the
current conditions plus a daily, weekly and monthly forecast for the default
location (Athens, Greece: 37.9838, 23.7275). Data comes from the
[Open-Meteo](https://open-meteo.com/) forecast API (no API key needed) and is
cached in memory per `(latitude, longitude)` with a 10-minute TTL
(`WeatherCache`: thread-safe, bounded to 128 entries with oldest-timestamp
eviction). Rendering is server-side only — the page emits no client-side
`fetch()`, so it works under the restrictive CSP (`default-src 'none'`).

### Configuration

There are no weather-specific environment variables or CLI flags. The server
CLI only exposes `--host` and `--port`. Weather is configured two ways:

- **Per request:** `GET /api/weather?lat=<lat>&lon=<lon>` overrides the
  location. Latitude must be -90..90, longitude -180..180; anything else
  (non-numeric, missing pairing, out of range) returns `400` with an `error`
  object.
- **In code:** override the module-level constants in `christmas_countdown.py`
  before calling `fetch_weather()` / `weather_summary()`:

| Constant | Default | Description |
|---|---|---|
| `WEATHER_API_URL` | `https://api.open-meteo.com/v1/forecast` | Open-Meteo API base URL |
| `WEATHER_CACHE_TTL` | `600` (seconds) | How long cached weather data stays valid |
| `WEATHER_DEFAULT_LAT` | `37.9838` (Athens) | Default latitude |
| `WEATHER_DEFAULT_LON` | `23.7275` (Athens) | Default longitude |
| `WEATHER_FORECAST_DAYS` | `16` | Daily forecast days requested (Open-Meteo max) |

### API: `GET /api/weather`

Returns `200 OK` with current conditions, a `current` alias of those
conditions, a `daily` per-day forecast (16 days max), `weekly` 7-day-chunk
aggregates and `monthly` per-`YYYY-MM` aggregates, plus `latitude`,
`longitude`, `source` and `cached_at` (UTC ISO-8601).

Daily entries carry `date`, `weathercode`, `description`, `temp_max`,
`temp_min`, `precipitation_sum`, `precipitation_probability` and
`windspeed_max`. Weekly/monthly summaries carry `days`, `temp_avg`,
`precipitation_total`, the dominant `weather_dominant` code and its
`description` (plus `week_start` / `month`).

When the upstream Open-Meteo API is unreachable or returns a malformed
payload, the endpoint returns `200 OK` with an `error` object
(`{"error": ..., "latitude": ..., "longitude": ...}`) — never a 5xx.
Invalid `?lat=`/`?lon=` values return `400` with an `error` object.

Weather codes follow the
[WMO Weather interpretation codes](https://open-meteo.com/en/docs) standard
(`translate_weather_code()`; unknown codes map to `"Unknown"`), rendered with
Unicode icons (`weather_icon_for_code()`).

### Attribution

Weather data © Open-Meteo (CC BY 4.0). The rendered page footer and API
`source` field credit `open-meteo`; see <https://open-meteo.com/> and
<https://creativecommons.org/licenses/by/4.0/>.

### Operations (production readiness)

- **Production behaviour:** no API key, env vars, or CLI flags are needed for
  weather. Upstream timeout is 10 s (`fetch_weather(timeout=...)`); on any
  upstream or payload failure the API returns `200` with an `error` object
  (never a 5xx) and `GET /` renders a "Weather currently unavailable."
  fallback section, so the countdown stays up when Open-Meteo is down.
- **Rate limits:** Open-Meteo's free API needs no key and is rate-limited
  server-side. This app calls it at most once per `(lat, lon)` per 10 minutes
  (`WEATHER_CACHE_TTL = 600`, thread-safe `WeatherCache`); cache hits serve
  from memory with no upstream call. The cache is bounded to 128 entries
  (oldest-timestamp eviction) and coordinates are validated
  (`lat -90..90`, `lon -180..180`, `400` otherwise), so cycling `?lat=`/`?lon=`
  cannot grow memory or fan out to upstream.
- **Monitoring and logging:** access logs go to stderr
  (`ChristmasCountdownHandler.log_message`); every weather upstream failure
  logs one stderr line (`weather unavailable lat=.. lon=..: <reason>`) via
  `weather_summary()`. Liveness: `GET /healthz` returns `{"status": "ok"}`
  without touching upstream. Alert on a rising rate of `weather unavailable`
  lines or on `/healthz` non-200.
- **Rollback:** the weather feature is additive (new functions, one new route,
  one optional template section). Roll back with `git revert <commit>` (or
  check out the pre-weather commit) and restart:
  `pkill -f 'christmas_countdown.py'`, then
  `python3 christmas_countdown.py --host 127.0.0.1 --port 8000`.
  No migrations, no external state; the in-memory cache is lost on restart.
- **Performance benchmarks** (measured 2026-09-21, local, no network except
  where noted): `countdown_summary` ~0.10 ms/op, `countdown_page` with full
  16-day weather ~0.04 ms/op (~0.006 ms/op fallback), `aggregate_weekly`
  ~0.020 ms/op, `aggregate_monthly` ~0.013 ms/op, `WeatherCache.get` hit
  ~0.0005 ms/op. Live smoke (pinned date 2026-09-21): `/healthz` ~26 ms,
  `/api/countdown` ~1 ms, `/api/weather` first fetch ~660 ms (upstream),
  cache hit ~0.003 ms, `GET /` with warm cache ~644 ms first page (one
  upstream fetch) then cache-speed.

## Defined behaviour

- The target is the next **25 December** on or after today; on Christmas Day the
  countdown is zero and the page shows `Merry Christmas!`. After Christmas the
  target rolls forward to the following year.
- `working_days` counts Monday-Friday strictly after today up to and including
  the target. `bank_holiday_days` counts the Greek public holidays in that
  window that fall on a working day, and `remaining_working_days` is
  `working_days - bank_holiday_days` (never below zero). The headline number is
  `remaining_working_days`.
- `GET /` returns `200 OK` with the HTML widget, the holiday list and a link to
  the calendar.
- `GET /calendar` returns `200 OK` with an HTML calendar for every month from
  the current one through the target month, highlighting weekends, bank
  holidays, today and Christmas Day. It contains no JavaScript.
- `GET /api/countdown` returns `200 OK` with a JSON object containing `today`,
  `target`, `calendar_days`, `working_days`, `bank_holiday_days`,
  `remaining_working_days`, `weekend_days`, `weeks`, `is_christmas` and
  `holidays` (a list of `{date, name, working_day}`).
- `GET /api/weather` returns `200 OK` with current conditions, a `current`
  alias, a `daily` per-day forecast, `weekly` 7-day-chunk aggregates and
  `monthly` per-`YYYY-MM` aggregates, plus `latitude`, `longitude`, `source`
  and `cached_at`. Optional `?lat=-90..90&lon=-180..180` overrides the default
  (Athens 37.9838, 23.7275); invalid values return `400` with an `error`
  object. When upstream Open-Meteo is unreachable or returns a malformed
  payload, the endpoint returns `200 OK` with an `error` object (never a 5xx).
- `GET /` embeds the same weather data as static server-rendered HTML below
  the countdown facts (current conditions, 7-day cards, weekly/monthly
  summaries). No client-side fetch is emitted, so the page works under the
  restrictive CSP. When weather is unavailable the section shows a fallback
  message. Weather data © Open-Meteo (CC BY 4.0).
- `GET /healthz` returns `200 OK` with `{"status": "ok"}`.
- Any other path returns `404 Not Found`; query strings do not affect routing
  except `/api/weather`, which honours `?lat=`/`?lon=`.
- `HEAD` is supported for all routes (headers only, no body). Responses carry
  `X-Content-Type-Options: nosniff`, a restrictive `Content-Security-Policy` and
  `Referrer-Policy: no-referrer`. The HTML countdown page's inline script is
  authorised by a per-response `nonce`; script-free pages use `script-src 'none'`.
- The working-days headline is computed from the **server's** local date while
  the live clock targets local midnight on the **client**. If the two timezones
  differ the headline and clock can be off by a day; reload to resync.
- The ready date is computed per request from an injectable clock, so the HTTP
  handler can be pinned to a fixed date in tests (`create_server(..., today_provider=...)`).

## Tests

```bash
python3 -m unittest -v test_christmas_countdown.py
```

# Static Christmas countdown (`index.html`, GitHub Pages)

`index.html` is a dependency-free static Christmas countdown for GitHub Pages:
no backend, no build step, no network calls.

- Client-side mirror of the Python logic: the target is the next **25 December**
  on or after today; **working days** are Monday-Friday strictly after today, up
  to and including the target, minus the **Greek public holidays** (fixed dates
  plus Orthodox Easter computus, verified against the Python implementation).
  The headline is `remaining_working_days`.
- Shows the working-days headline (or `Merry Christmas!`), calendar/weekend/full
  weeks facts, and a live clock ticking to local midnight on the target date.
- Run: `python3 -m http.server 8000`, then open <http://localhost:8000/>.
- Note: the Python server features (`/api/*`, `/calendar`, server-rendered
  weather) cannot run on Pages; use `christmas_countdown.py` for the full app.
- Pacman lives in `malme32/pacman-web-app`; it is not part of this repo's Pages
  output.

---

# Olympiacos next matches

Small, dependency-free helper that reports the next matches for **Olympiacos FC
(Piraeus)**. It fetches live fixtures from the public
[TheSportsDB](https://www.thesportsdb.com/free_sports_api) API and falls back to
a bundled, verified snapshot when the API is unreachable or returns nothing.

## Usage

```bash
python3 olympiakos_fixtures.py                 # next 5 matches (live, with fallback)
python3 olympiakos_fixtures.py --limit 10      # more matches
python3 olympiakos_fixtures.py --offline       # use the bundled snapshot only
python3 olympiakos_fixtures.py --json          # machine-readable output
```

Example output:

```
Next 5 Olympiacos matches (source: fallback)
  2026-09-20 14:00 (local 17:00)  Levadiakos vs Olympiacos  [Greek Super League 1] @ Levadia Municipal Stadium, Livadia
  2026-10-11 18:00 (local 21:00)  Olympiacos vs Panathinaikos  [Greek Super League 1] @ Stadio Georgios Karaiskakis, Piraeus
  ...
```

## Tests

```bash
python3 -m unittest -v test_olympiakos_fixtures.py
```

## Current answer

As of 2026-09-19 the next Olympiacos fixture is:

- **Levadiakos vs Olympiacos** - Sun **20 September 2026**, 17:00 EEST
  (14:00 UTC), Greek Super League 1, Levadia Municipal Stadium.

Confirmed against the club's official matchcenter at
<https://www.olympiacos.org/en> and TheSportsDB.

Clock times in the fallback snapshot are the club's local kick-off times (EEST,
UTC+3); the `datetime_utc` values are the corresponding UTC instants.

# Arithmetic calculator

`calculator.py` is a small, dependency-free arithmetic calculator supporting
`+ - * / % ^`, parentheses and unary sign. `^` is right-associative and binds
tighter than unary minus (`-2^2` is `-4`).

## Usage

```bash
python3 calculator.py "2 + 3 * 4"          # 14
python3 calculator.py "(2 + 3) * 4" --json # {"expression": "...", "result": 20}
echo "10 / 4" | python3 calculator.py      # 2.5
python3 calculator.py                      # interactive prompt
```

## Defined behaviour

- Empty or whitespace-only input raises `CalculatorError("empty expression")`.
- Division (or modulo) by zero raises `CalculatorError("division by zero")`.
- Non-numeric or otherwise malformed input raises `CalculatorError` with a
  message naming the offending character/token.
- On any `CalculatorError` the CLI prints `error: <message>` to stderr (or a
  JSON object with an `error` key when `--json` is used) and exits with status
  `1`. Valid expressions print the result and exit `0`.

## Acceptance criteria

1. Supports `+`, `-`, `*`, `/`, `%`, `^`, parentheses and unary sign with the
   documented precedence.
2. Each of the four basic operations produces the correct arithmetic result
   (see `test_addition`, `test_subtraction`, `test_multiplication`,
   `test_division`).
3. Division by zero has defined behaviour: it raises `CalculatorError` and the
   CLI exits non-zero (see `test_division_by_zero_raises`).
4. Invalid/non-numeric input raises `CalculatorError` and exits non-zero (see
   `test_non_numeric_input_raises`, `test_unexpected_character_raises`).
5. A documented entry point exists: `calculator.py` (CLI) exposing
   `calculate()`.

## Tests

```bash
python3 -m unittest -v test_calculator.py
```

## Entry point

```bash
python3 calculator.py "2 + 3 * 4"
```
