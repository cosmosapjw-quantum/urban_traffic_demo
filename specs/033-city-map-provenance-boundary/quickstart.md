# Quickstart: Source Boundary Review

1. Read `docs/map/CITY_MAP_SOURCE_PROVENANCE.md`.
2. Confirm a proposed implementation uses only Metroflow specs and tests.
3. Run `.venv/bin/python -m pytest tests/test_city_map_provenance.py -q`.
4. Stop if a diff adds a CSUR import, dependency, vendored file, or copied code.
