# AGENTS.md

## Repository layout

- `christmas_countdown.py` — dependency-free Christmas countdown web app (stdlib `http.server`).
- `test_christmas_countdown.py` — `unittest` suite for `christmas_countdown.py`.
- `calculator.py` — dependency-free arithmetic calculator (library + CLI).
- `test_calculator.py` — `unittest` suite for `calculator.py`.
- `olympiakos_fixtures.py` — Olympiacos next-match fixture reporter (unrelated helper).
- `test_olympiakos_fixtures.py` — tests for the fixture reporter.
- `README.md` — usage, defined behaviour and acceptance criteria.

## Conventions

- Python 3, standard library only (no third-party dependencies).
- Prefer small, pure functions with type hints and docstrings.
- Tests use the built-in `unittest` framework and live next to the module they
  test as `test_<module>.py`.
- CLIs use `argparse` and return an `int` exit status from `main()`.

## Commands

Run everything:

```bash
python3 -m unittest -v test_christmas_countdown.py test_calculator.py test_olympiakos_fixtures.py
```

Run just the calculator tests and try the CLI:

```bash
python3 -m unittest -v test_calculator.py
python3 calculator.py "2 + 3 * 4"
```

Run just the Christmas countdown tests and start it locally:

```bash
python3 -m unittest -v test_christmas_countdown.py
python3 christmas_countdown.py --port 8000
```

## Pacman web app

The Pacman game is plain ES-module HTML/CSS/JS + Canvas with no build step.

- Source: `index.html`, `styles.css`, `src/core/`, `src/ui/`, `src/main.js`.
- Tests: `test/` using Node's built-in `node:test` runner (Node >= 18).
- Run locally: `python3 -m http.server 8000` then open <http://localhost:8000/>.
- Run tests: `node --test test/` (or `npm test`).

## Definition of done

- Changes are committed on the feature branch.
- `python3 -m unittest -v test_christmas_countdown.py` passes.
- No third-party dependencies are introduced.
