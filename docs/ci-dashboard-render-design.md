# CI: render the dashboard on an invented house; test the real one locally

Status: 2026-10-25, rev 4. Supersedes rev 1-3 (same day), which published anonymised copies
of the real registries; see "History" at the end.

## Decision

The operator, after seeing rev 3 run: the anonymised fixtures still told the public too much
about the household (every room, every socket, the appliances, the car), and the full-house
screenshots were "ridiculously long". So:

- **Locally, test against real data.** `lint.py`, `mutate.py` and the climate suite read the
  live instance, as they did before CI existed. The render pipeline can run against a
  gitignored real-house fixture (`tests/fixtures/real/`) on the operator's machine.
- **Upstream, everything is synthetic and small.** CI builds an invented house: two floors,
  two rooms each, one or two devices per kind, two invented people. Nothing in it is derived
  from the instance, at build time or at run time.

## Invariants

- **I1. CI depends on nothing but the repo.** No job reaches the instance, reads an export of
  its registries, or uses a value that came from it.
- **I2. A screenshot shows only the invented house.** Its rooms, devices, people and states
  are hand-written in `tests/fixtures/synthetic.py`. The dashboard config it renders comes
  from the public exports in `lovelace-dashboards/` (the repo's reason to exist), with the
  person badges and the floor cards' room maps pointed at the invented house.
- **I3. CI never writes to `master`.** Screenshots go to the `screenshots` branch.
- **I4. No self-hosted runner.** Public repo: a pull request would run code beside the house.

## The invented house (`tests/fixtures/synthetic.py`)

Downstairs: living room, kitchen. Upstairs: bedroom, office. Per room: one or two lights, a
Magic Areas all-lights group and occupancy sensor (what the room card resolves), resolved
temperature and humidity labelled `on_room_page`. Living room and bedroom carry a climate
unit and the climate helpers (automatic-climate switch, day/night targets, air-filter
switch), so Home's Comfort section has something to generate. House-wide: the entities the
Home view names (weather, alarm, the Needs-attention roll-ups, night helper, outdoor
temperature, AQI, purifier filter), the kitchen tile's appliance states, two people.
States are designed, not generated: a calm afternoon, one lamp on, nothing to attend to.

The dashboard is Home plus the room-page skeleton cloned per room (every room page shares
one skeleton, lint C14). Climate, Energy, Appliances and Security are curated tabs that name
specific real entities; they are not rendered upstream.

**Test, written first: `tests/fixtures/test_synthetic.py`.** The invented house is
hand-maintained, so it drifts behind the dashboard. It fails when the dashboard names an
entity the house lacks, a floor card maps a room that is missing, on another floor or
without a page, an area has no entities (no tile), an entity has no designed state or
carries an unknown label, or a room lacks the Magic Areas group or occupancy sensor the room
card resolves. Its first run found three entities named only inside the room card's
JavaScript (kitchen appliances, outdoor motion); the house gained them.

## Render pipeline (`tests/render/`)

- `cards.json`: each custom card pinned to the live version with its sha256; downloads that
  do not match are refused. Resources the dashboard lists without a pin are refused.
- `bootstrap.py prepare`: the config dir from a fixture (`FIXTURE_STORAGE`): one placeholder
  config entry of a domain that does not exist (`ci_fixture`) owns every device and entity.
  Read from 2026.10.3's `device_registry.async_cleanup`: a device whose entry is unknown is
  removed with its entities; an entry whose integration is missing is kept as "not loaded".
  Writes `lovelace_dashboards` (the household dashboard is a registered dashboard at
  `/lovelace`) and the default panel. The registry's `settings` keys must be present.
- `bootstrap.py onboard`: onboarding over the API, a long-lived token over the websocket, then
  removes what onboarding installed by itself (sun, shopping list, radio browser, Google
  Translate, analytics, backup, a person; two reach the internet), sweeping until nothing new
  appears for 15 s.
- `bootstrap.py verify`: the registry equals the fixture exactly, entities and devices, as
  sets. This caught the onboarding race on its first run.
- `seed.py`: with `states.json`, posts the designed states; without (local real run), derives
  placeholders from a hash of each entity id.
- `shoot.py` + `dashboards/render.py`: Home and the living-room page at 390 and 1280 px
  (`RENDER_PAGES` for more), browser clock frozen at the run's start, animations off. Exit 1
  on any `hui-error-card`/`hui-warning` except `custom:alarmo-card`, whose backend needs the
  house's alarm configuration; it is exempt by type and printed every run. A crashed browser
  is retried once and reported as a crash, never as a card. Proven: a planted
  `custom:no-such-card` turns the job red.

## Workflows

`ci.yml` on every push except to `screenshots`: secret scan, ESPHome secrets, JSON parse,
compile, and `test_synthetic.py`.

`render.yml`:

- triggers: `pull_request` and `push` to `master`, both path-filtered to
  `lovelace-dashboards/**`, `tests/fixtures/synthetic.py`, `tests/render/**` code and data,
  `tests/dashboards/render.py` and the workflow itself; plus `workflow_dispatch`.
- `concurrency: render-${{ github.ref }}`, cancel in progress (per ref: a PR never cancels master).
- job `render` (`contents: read`): build the house, test it, boot Home Assistant 2026.10.3
  pinned by digest, onboard, verify, seed, shoot; screenshots as a 14-day artifact.
- job `publish` (`contents: write`), master only: when any image's sha256 differs from the
  `screenshots` branch, force-push one orphan commit there as `github-actions[bot]`.

Loop protection: publishing never touches `master`; `render.yml` triggers on `master` only;
`ci.yml` ignores `screenshots`; pushes made with `GITHUB_TOKEN` start no workflow. Dry-run
against a local bare repo: first publish, unchanged (no push), changed (fresh orphan commit).
Verified on GitHub: the publish started no run.

## Locally

- `python3 tests/dashboards/lint.py` and `mutate.py`: the live instance, as before.
- `python3 tests/dashboards/export.py` also writes `tests/fixtures/real/` (gitignored),
  allowlisted, masked (MAC, IEEE, e-mail in names) and scrubbed, gated by
  `tests/fixtures/check.py` and the lint. Point `FIXTURE_STORAGE` at it and run bootstrap,
  `seed.py` (no states file) and `shoot.py` with `RENDER_PAGES` to render the real house in a
  local container.

## Failure modes

| Failure | Guard |
|---------|-------|
| Real data reaches CI | Nothing in CI reads anything but the repo (I1); `tests/fixtures/real/` is gitignored; AGENTS.md rule 7 |
| Synthetic house drifts behind the dashboard | `test_synthetic.py` in CI and in the render job |
| HA drops registry entries at start-up | placeholder config entry; exact set verify |
| A card's JS fails to load or a card errors | checksums; `shoot.py` exits 1 |
| CI commit retriggers CI | four layers, above |
| Fork pull request | read-only token, nothing published |

## History

- Rev 1-3 (2026-10-25) committed `tests/fixtures/storage`: the live registries cut to an
  allowlist and anonymised, so CI could also run the dashboard lint. Two review rounds
  passed it as privacy-safe, but by the operator's judgement it still published too much
  household intel, and its screenshots covered every tab of the full house. Rev 4 removes
  it from the repository and from history (master rewritten from c3815b1 and
  force-pushed; the `screenshots` branch replaced). The dashboard lint is local-only again.
- Kept from rev 1-3: the bootstrap facts above, the allowlist builder and its check (now
  for the local real fixture only), the card pins, and the publish mechanics.
