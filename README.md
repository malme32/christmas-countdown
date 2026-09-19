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
