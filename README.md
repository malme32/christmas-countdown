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
curl http://127.0.0.1:8000/                  # HTML widget
curl http://127.0.0.1:8000/api/countdown     # JSON numbers
curl http://127.0.0.1:8000/healthz           # health check
```

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
- `GET /healthz` returns `200 OK` with `{"status": "ok"}`.
- Any other path returns `404 Not Found`; query strings are ignored when routing.

## Tests

```bash
python3 -m unittest -v test_christmas_countdown.py
```

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
