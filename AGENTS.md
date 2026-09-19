# AGENTS.md

Conventions for agents and contributors working in this repository.

## Scope

This repository hosts the Pacman web app. Keep changes small, reviewable and
reversible. Do not commit secrets or generated artifacts.

## Branches

- `main` is the integration branch and must always be releasable.
- Work happens on short-lived branches named
  `agent/<task-slug>-<short-id>` or `feature/<slug>`.
- Never force-push shared branches.

## Commits

- Write clear, imperative commit messages ("Add ...", "Fix ...").
- One logical change per commit.
- Do not commit `.agent/` or `.agent-company/` scratch/state files.

## Tests

- Add or update tests alongside behaviour changes.
- Run the full test suite before opening a pull request and report the result.

## Local development

The app is not implemented yet. When source is added, document the exact run
and test commands here.

## Security

- Never hard-code tokens, keys or passwords. Read credentials from the
  environment.
- Never echo secrets into logs, commits or chat.

## Delivery

- Pushing, merging and deploying require explicit operator approval.
- Prefer pull requests over direct pushes to `main` once the team grows.
