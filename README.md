# home-assistant-config

A public, anonymised reference for one family's Home Assistant instance: the design records,
the tests that keep them honest, and sanitised snapshots of the live configuration.

**Almost nothing here is deployable.** The dashboards and automations are exports with
rooms and people replaced by neutral placeholders, so they deliberately do not match the
live instance. The exception is `esphome/`, which is flashed as-is (every secret is a
`!secret` reference; see `esphome/secrets.yaml.example`).

## What is here

| path | what |
|---|---|
| `docs/climate-control-design.md` | Per-room heating and cooling: the design record and every review round behind it |
| `docs/self-maintaining-dashboards.md` | Dashboards generated from the area registry and labels, so a new device appears without an edit |
| `automations/` | Sanitised exports of the climate automation and its template sensors |
| `lovelace-dashboards/` | Sanitised dashboard exports and the `button-card` templates they use |
| `tests/climate/` | Scenario tests run against the **live** automation expressions, with mutation testing |
| `tests/dashboards/` | Dashboard lint, mutation tests, anonymised export and a headless renderer |
| `tests/leakcheck.py` | Scans tracked files and unpushed commits for anything the anonymisation should have removed |
| `esphome/` | Bluetooth proxy and Geiger counter configs |

## Working on it

Read [`AGENTS.md`](AGENTS.md) first. It covers the anonymisation rules, the tests to run
before committing, and the write-the-test-first rule for climate changes.
