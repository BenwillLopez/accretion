# Contributing

Thanks for helping keep Accretion useful.

## Suggest a source

[Open a source request](../../issues/new?template=add-source.yml) with the source URL. A source can be
added if:

- it is in the AltStore JSON format and served over **https**
- it lists at least one app with a bundle ID, an https icon, a version, a release date and an
  https download link
- it is maintained: it has been updated recently and its downloads work

Sources that pass these checks automatically may already be picked up by the weekly discovery.
Check [`REPORT.md`](REPORT.md) first.

## Report a broken or bad source

[Open a source report](../../issues/new?template=report-source.yml). For malware or anything
harmful, follow [SECURITY.md](SECURITY.md) instead.

## Change the code

1. Fork the repo and make your change in `scripts/`.
2. Add or update a test in `tests/`.
3. Run the checks:
   ```sh
   pip install ruff
   ruff check . && ruff format --check .
   python -m unittest discover -s tests
   python scripts/merge.py && python scripts/validate.py
   ```
4. Open a pull request. CI runs the same checks.

Do not commit generated files (`source.json`, `curated.json`, `stats.json`, `history.json`, `REPORT.md`,
`discovered.*`, `dead_links.json`, `assets/card-*.svg`, `assets/recent-*.svg`). The workflows build them.

## Style

- Python 3.10+, standard library only. The pipeline must run without installing packages.
- Formatted with `ruff format`, linted with `ruff check` (config in `pyproject.toml`).
- Network failures must never break a build: log them and fall back to the cached copy.
