# AGENTS.md

## Repository layout

- `christmas_countdown.py` — dependency-free Christmas countdown web app (stdlib `http.server`).
- `test_christmas_countdown.py` — `unittest` suite for `christmas_countdown.py`.
- `calculator.py` — dependency-free arithmetic calculator (library + CLI).
- `test_calculator.py` — `unittest` suite for `calculator.py`.
- `olympiakos_fixtures.py` — Olympiacos fixture reporter (unrelated helper).
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

## Definition of done

- Changes are committed on the feature branch `agent/count-down-to-christmas-f33f48`.
- `python3 -m unittest -v test_christmas_countdown.py` passes.
- No third-party dependencies are introduced.
