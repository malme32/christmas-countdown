# Christmas working-days countdown

`christmas_countdown.py` is a dependency-free web app built on the Python
standard library's `http.server`. It serves a Christmas countdown widget whose
headline number is the remaining **working days** (Monday-Friday) until
Christmas Day, alongside calendar days, weekend days and a live clock.

## Usage

```bash
python3 christmas_countdown.py                    # http://127.0.0.1:8000/
python3 christmas_countdown.py --port 8080        # custom port
python3 christmas_countdown.py --host 0.0.0.0     # all interfaces
```

Then open <http://127.0.0.1:8000/> or:

```bash
curl http://127.0.0.1:8000/                  # HTML widget (includes server-rendered weather)
curl http://127.0.0.1:8000/api/countdown     # JSON numbers
curl http://127.0.0.1:8000/api/weather       # JSON weather (current/daily/weekly/monthly)
curl "http://127.0.0.1:8000/api/weather?lat=51.5&lon=-0.12"  # custom location
curl http://127.0.0.1:8000/healthz           # health check
```

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

## Defined behaviour

- The target is the next **25 December** on or after today; on Christmas Day the
  countdown is zero and the page shows `Merry Christmas!`. After Christmas the
  target rolls forward to the following year.
- **Working days** are Monday-Friday strictly after today, up to and including
  the target. Weekends are excluded; public holidays are **not** excluded, so
  the count is deterministic and needs no data files or network access.
- `GET /` returns `200 OK` with the HTML widget.
- `GET /api/countdown` returns `200 OK` with a JSON object containing `today`,
  `target`, `calendar_days`, `working_days`, `weekend_days`, `weeks` and
  `is_christmas`.
- `GET /api/weather` returns `200 OK` with a JSON object containing `current`
  (temperature, windspeed, winddirection, weathercode, description),
  `daily` per-day entries, `weekly` 7-day aggregates, `monthly` per-month
  aggregates, plus `latitude`, `longitude`, `source` and `cached_at`.
  Optional `?lat=-90..90&lon=-180..180` overrides the default (Athens
  37.9838, 23.7275); invalid values return `400` with an `error` object.
  When the upstream Open-Meteo API is unreachable or returns a malformed
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
  `Referrer-Policy: no-referrer`. The HTML page's inline script is authorised by
  a per-response `nonce`, so no `script-src 'unsafe-inline'` is needed.
- The working-days headline is computed from the **server's** local date while
  the live clock targets local midnight on the **client**. If the two timezones
  differ the headline and clock can be off by a day; reload to resync.
- The ready date is computed per request from an injectable clock, so the HTTP
  handler can be pinned to a fixed date in tests (`create_server(..., today_provider=...)`).

## Tests

```bash
python3 -m unittest -v test_christmas_countdown.py
```

---

# Pacman web app

A dependency-free Pacman game built with plain HTML, CSS, JavaScript and the
Canvas API. There is no build step and no third-party dependency; the core game
logic is separated from the canvas/input layer so it can be unit tested.

## Run

```sh
python3 -m http.server 8000
```

Then open <http://localhost:8000/>.

## Controls

- Move: arrow keys or `WASD`
- Mute: `M` (or the on-screen button)
- Pause / resume: `P`
- Start / play again: `Enter` or `Space`

## Tests

```sh
node --test test/
# or
npm test
```

## Layout

- `index.html` - page shell, HUD and canvas.
- `styles.css` - presentation only.
- `src/core/` - pure game logic: `maze.js`, `movement.js`, `player.js`,
  `ghost.js`, `game.js` (fixed 60 Hz timestep) and `constants.js`.
- `src/ui/` - `render.js` (canvas), `input.js` (keyboard) and `audio.js`
  (Web Audio cues synthesised at runtime; pure `cueFor(event)`).
- `src/main.js` - bootstrap and the `requestAnimationFrame` loop.
- `test/` - Node unit tests (`node:test`) for the core and pure UI helpers.

## Rules and data model

- 28x31 tile maze with 238 pellets and 4 power pellets (242 in total).
- One player and four ghosts (Blinky, Pinky, Inky, Clyde) with scatter/chase
  targeting and a frightened state after a power pellet.
- Scoring: pellet 10, power pellet 50, frightened ghosts 200/400/800/1600.
- A life is lost when the player's tile overlaps a non-eaten ghost; three lives
  start, and losing them all ends the game.
- Eating every pellet completes the level (5 levels); clearing the final level
  wins. The tunnel edges wrap horizontally.
- Movement, collision and ghost AI run on a fixed 60 Hz timestep, decoupled from
  rendering.

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
