# Surfacing the September additions, and pulling the sockets together

*2026-09-23.*

## The complaint

> "i have reorganised the panels a little in Home Assistant and added more sensors and media
> players. make sure all surface in relevant dashboards, and that the sockets functionality is
> consolidated on the energy tab. i dont generally need to switch them on or off - theyre there
> for energy monitoring"

Two separate jobs. The first is a coverage question: 306 entities were created between
2026-09-20 and 2026-09-23, and **98 of them were named by no view at all**. The second is a
design question about what a socket card is *for*.

## How the gap was measured, not guessed

The room subviews are generated — each is `strategy: {type: home-area, area: <id>}` — so
anything with an **area** already surfaces by itself. That makes the interesting set narrow:
entities the curated views must name explicitly, because nothing else will show them.

The check was mechanical rather than by eye:

1. every `entity_id` in `.storage/core.entity_registry` with `created_at` after the cutoff,
   minus anything `disabled_by`, `hidden_by`, or carrying an `entity_category` (diagnostic and
   config entities do not belong on a family dashboard);
2. minus every id that appears anywhere in the two dashboards' JSON.

That left 98, which grouped cleanly by integration and made the work obvious.

| new since 2026-09-20 | where it now surfaces |
|---|---|
| `cz_energy_spot_prices` — electricity + gas spot rate, CZK/kWh | Energy → **Spot price** (new section) |
| `powercalc` — 12 virtual-power devices + the *All lights* domain group | Energy → **Modelled load** (new section) |
| `denonavr`, `heos`, `androidtv_remote` (SHIELD), `homekit_controller` (TV) | Home → **Media** (rebuilt) |
| `music_assistant` players | Home → **Media**, conditionally (see below) |
| `switchbot` Meter Pro CO₂ ×2, Indoor/Outdoor Meter ×2 | already resolved into `sensor.climate_*`; the unplaced one moved to the admin panel |
| `xiaomi_miio` air purifier PM2.5 | Climate → **Air quality — indoors** |
| corridor resolved temperature / humidity | Climate → **Temperature** and **Humidity** |
| `light.bunny` in Kids room 2 → Magic Areas light group | Home room tile — see [room-tile-navigation.md](room-tile-navigation.md) |
| `withings` body/skin temperature | nowhere, deliberately — see below |

## The sockets: a card that measures is not a card that switches

Socket cards existed **twice on the Energy view** — a "Sockets" subtitle under *Load now* with
seven `tile` cards on the power sensors, and a separate *Sockets* section further down with
seven Mushroom cards on the switches. Same seven devices, two presentations, neither obviously
the canonical one.

They were also a third time on the admin **Network** view, which carried
`switch.poe_network` and `switch.lr_powerline` with their power *and* energy sensors, plus the
USB gang on the TV socket.

All of it is now one section on the Energy tab. The design rule that settled the layout is the
operator's own sentence: *they're there for energy monitoring.*

**Every gesture on a socket card opens more-info.** `tap_action`, `icon_tap_action` and
`hold_action` are all `more-info`. Nothing on the card toggles anything.

This is not the same as removing control. The more-info dialog still has the toggle. What
changed is that switching now takes a deliberate second step instead of being the default
consequence of touching the card.

*Corrected 2026-09-23:* this paragraph originally also claimed "the room subviews still list
the switches", which was true of the generated views and stopped being true when the room
views were rebuilt on button-card — see [room-views-button-card.md](room-views-button-card.md).
The sockets are now on the Energy tab and in the more-info dialog, and the two rooms whose
only device is a socket link out to the Energy tab instead of carrying a switch.

That matters most for the two cards where a misfire is expensive. The PoE card feeds the
switches and access points; the previous design guarded it with a confirmation dialog on
`tap_action`, which is a guard that has to *work* to be worth anything. The card now has no
toggle action to confirm, so there is nothing to misfire — a strictly stronger guarantee than a
dialog, and one that does not depend on Mushroom's action plumbing behaving. (This repo has
already had one unproven report of a Mushroom `perform-action` failing to dispatch; see
[room-tile-navigation.md](room-tile-navigation.md#an-unresolved-report). Designing so that the
question cannot arise is cheaper than answering it.)

The section carries, in order:

- a heading badged with the live total;
- **one 24 h `mini-graph-card` plotting all seven sockets together** — the monitoring depth that
  justifies the section, in one card rather than seven;
- seven cards, each showing live watts when the socket is on and `Off` when it is not, coloured
  by draw (grey → green → amber → deep-orange);
- a subtitle, *Outlets without metering*, for the two gangs that share a plug with a metered
  socket but have no measurement of their own. They are on the Energy tab because that is where
  sockets live now, not because they contribute a number.

### The total was wrong, and had been since the 22nd

`sensor.socket_power_total` is a `min_max` sum helper listing its members explicitly. The
Media Corner socket was added on 2026-09-22 and never added to it, so the Energy view's badge —
the one number that answers *what are the sockets drawing* — had been under-reporting ever
since.

Adding it moved the reading from **145 W to 191 W**, which is the 45 W the media corner was
drawing at the time. An explicit member list is the right helper for this — it means a socket
is either counted or it is not, with no guessing — but it also means every new socket is a
two-step job, and the second step is easy to skip.

## Media: one card per physical device, not one per integration

Twenty `media_player` entities exist for **eight** real devices. The living-room TV alone has
four: Android TV remote, Cast, Music Assistant and HomeKit. SHIELD has three, the AV receiver
has three.

Assigning areas to all of them would have "surfaced" them — straight into the Living Room
subview as nine near-identical cards. So the Media section is curated instead, one card per
device, choosing the integration by what it actually lets you do:

| device | card | why that integration |
|---|---|---|
| Living room TV | `androidtv_remote` | power, volume, transport |
| Home Theater | `denonavr` | power, volume, **input select** (HEOS duplicates it without the inputs) |
| SHIELD | `androidtv_remote` | power, volume, transport |
| TV inputs | `homekit_controller` | the only entity exposing the TV's 14 sources; shown only while the TV is on |
| Kitchen, Office | `alexa_media` | the two Echos whose area is current |
| Echo Spot | `alexa_media` | hidden while `unavailable`, which is its current state |

**The Music Assistant players are conditional.** Three of them mirror devices already on the
card list, so they appear only while `playing`, `paused` or `buffering`, under their own
subtitle, and the whole block collapses when nothing is playing. They are the queue targets, not
a fourth way to press play on the same box.

## What was deliberately left off

- **`withings` body and skin temperature.** Six new sensors, all of them about people rather
  than the house. They belong to whoever wants to look at them, not on the family wall.
- **`sensor.background_radiation_total_counts`.** A monotonic accumulator. The Climate view
  already shows the dose rate and the CPM it is derived from, which are the readings a person
  can act on.
- **The raw SwitchBot / Matter meter entities.** Every room's temperature, humidity and CO₂ on
  the Climate view reads a resolved `sensor.climate_*` template, which already tiers BLE →
  Matter → AC → TRV. Adding the underlying sensors would put two numbers for the same room on
  the same screen and invite the reader to wonder which one is true.
- **`sensor.all_climate_power`.** It never summed anything; the operator deleted the group
  while this change was being written. See below.

## Open items, not fixed here

1. ~~`sensor.all_climate_power` never summed anything.~~ **Closed by the operator, 2026-09-23**,
   who deleted the *All Climate* powercalc group — correct: it was a `domain` group over
   `climate`, no `climate` entity has a powercalc virtual-power sensor, and `sensor.ac_power_total`
   already sums what the ACs report themselves.

   **This nearly shipped a broken view.** *All Switches* was deleted in the same pass, and the
   *Modelled load* section had been written minutes earlier naming `sensor.all_switches_power`
   and `sensor.all_switches_energy`. Two dead tiles and a dead graph series, live, with the
   wiring check already green — because that check had run **before** the deletion. The section
   is now *Modelled load — lights*, carrying only the surviving *All lights* group, and the
   wiring check was re-run afterwards: 363 referenced ids, zero missing, none disabled or hidden.

   The lesson is the one AGENTS.md already states about `wiring.py` — an entity-existence check
   is only worth the moment it ran in. It has to be the **last** thing done, not a step in the
   middle.
2. **Both SwitchBot meters are exposed twice**, over BLE (`switchbot`) and over Matter through
   the hub. This is load-bearing, not an accident: the resolved climate template reads BLE first
   and falls back to Matter. It is now written down on the admin panel next to the meter, so the
   next person to tidy up does not delete half a fallback chain.
3. **`golemio` and `transit_departures` are installed but have produced no entities** — both
   raise a `restart_required` repair. Nothing can be put on a dashboard until Home Assistant
   restarts.
4. ~~One Echo device carries a given name inside its `entity_id`.~~ **Closed 2026-09-23** — the
   operator removed the device from their Alexa account, and its card came off the Media section
   with it. The token stays in the local scrub list at the operator's direction, since the
   registry entries linger until `alexa_media` drops them.

   **The reasoning failure is worth keeping even though the item closed.** The first placeholder
   was `kid1`, picked from the room the device was assigned to. The operator then said there is
   no Echo in either child's room — so that assignment was legacy, from before they moved. *An
   inference drawn from a registry field nobody has re-checked is not an inference.* The
   replacement, `echo_show_ha_dashboard`, was chosen to claim nothing at all, which is the right
   default for an anonymisation placeholder: scrubbing errs safely toward removing more, but a
   *guessed identity* invents a false association that the raw name never asserted.

   The same instinct fixed the card label: naming it *HA dashboard*, by function, made both the
   room and the person irrelevant to it.
5. **The corridor template sensors log an error whenever the purifier is unreachable.** Both
   `sensor.climate_temp_corridor` and `sensor.climate_humidity_corridor` end their expression
   with a bare `{% endif %}`, so when the source reads `unavailable` they render the **empty
   string** and Home Assistant logs
   `Received invalid sensor state:  for entity sensor.climate_temp_corridor, expected a number`.

   The *intent* is right — emit no value rather than a wrong one — and the one consumer, the
   purifier automation, reads them through `| float(-99)` sentinels, so nothing misbehaves. It
   is the encoding that is wrong: a numeric template sensor says "no value" with `unknown` or an
   `availability` template, not with `''`.

   It was found only because these two sensors were put on the Climate view in this pass; it has
   been there since they were created on 2026-09-20. It is **not fixed here**: AGENTS.md names
   the `Climate temp *` template sensors as test-first territory, so the fix starts with a
   failing case in `tests/climate/cases.py`, not with an edit.

## Not covered by any test

`tests/climate/` is an expression oracle for the climate loop and has nothing to say about
dashboards. What was verified instead:

- **every entity id named by either dashboard exists.** All 365 were extracted from the
  committed storage and checked against the entity registry; the only misses were the Jinja
  concatenation stems (`sensor.climate_temp_` + room), two service names caught by the same
  regex, `sun.sun` (real, but not a registry entity) and two ids quoted inside the new admin
  markdown. Zero real misses.
- **every new Jinja template rendered against live state** — socket secondary and colour, the
  spot-price colour band, the cheapest-block window, the rewritten Kids room 2 tile line.
- **the socket total was read back after the helper edit**: members now seven, value 191 W,
  and the seven individual readings sum to the same number.
- **the Mushroom media-player card's option names were checked against the bundled
  `mushroom.js`** rather than assumed — `media_controls`, `volume_controls`,
  `use_media_info`, `use_media_artwork`, `show_volume_level` and their permitted values all
  appear in its own editor strings.

Not verified, because it cannot be from here: that any of it *looks* right. No card was
rendered.
