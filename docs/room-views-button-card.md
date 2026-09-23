# The dashboards, rebuilt on the fork's own button cards

*2026-09-23.*

## What this repository is a fork of, and what had happened to it

This repo is a fork of [eximo84/homeassistant-config-v2](https://github.com/eximo84/homeassistant-config-v2),
and the thing it was forked *for* is `Custom Buttons/` — a library of
[`custom:button-card`](https://github.com/custom-cards/button-card) templates, most
notably a set of Hue bulb SVGs that take the bulb's own colour.

None of it was in use. Two facts, both checked rather than assumed:

- the live dashboard's config had exactly one top-level key, `views`. There was **no
  `button_card_templates` key at all**, so not one of the 41 templates was loaded;
- of the six custom cards the library depends on, **four were not installed**.

| dependency | references in the library | before |
|---|---:|---|
| `custom:button-card` | 156 | not installed |
| `custom:slider-entity-row` | 27 | not installed |
| `custom:mini-media-player` | 14 | installed |
| `custom:mini-graph-card` | 10 | installed |
| `custom:multiple-entity-row` | 3 | not installed |
| `custom:stack-in-card` | 2 | not installed |
| `custom:simple-thermostat` | 2 | not installed |
| `custom:simple-weather-card` | 1 | not installed |

All six are installed now. One needed a substitution: upstream's README points at
`nervetattoo/simple-thermostat`, which HACS no longer carries — the maintained fork is
`Wheemer/simple-thermostat`, and that is what is installed. It is the same card.

The Hue bulb icons need no asset files; they are **inline SVG** in the templates, filled
with `var(--button-card-light-color)`, so a bulb on the dashboard glows in the colour the
real bulb is set to. The only external asset the whole library wants is
`/local/tado_thermostat.svg`, used by the Climate Button alone, and it is still missing —
that button is unused here.

## Where the buttons went, and where they did not

The room views. Each of the twelve was a generated
`strategy: {type: home-area, area: <id>}` — Home Assistant deciding the contents. They are
now real pages built from upstream's Room View templates.

**The Mushroom Home view is untouched.** That was the point of putting them here: the room
pages are where upstream designed these buttons to live, and rebuilding them adds a layer
without overriding a design that had already been agreed. The Home tiles still hold-to-open,
and every `path` is unchanged, so no navigation broke.

A room page now carries, in order and only where the room has them:

- **Lights** — the Magic Areas group first where the room has more than one light, then one
  Room View Light Button per bulb: inline Hue SVG, an inline brightness slider, and a
  separate power pill so the card body stays a more-info tap.
- **Air** — the purifier, where there is one.
- **Climate** — `simple-thermostat` per climate entity, AC and radiator valve separately.
- **Media** — `mini-media-player` per player.
- **Conditions** — sensor buttons reading the **resolved** `sensor.climate_*` templates, not
  the raw SwitchBot/Matter entities, for the reason given in
  [dashboard-surfacing-2026-09.md](dashboard-surfacing-2026-09.md).
- **Elsewhere** — links out to the consolidated views.

**Sockets are deliberately not on the room pages.** They live on the Energy tab, monitoring
first, and putting a switch button back in the room would undo that consolidation. The rooms
whose only device is a socket — Bathroom, Shower — carry a link to the Energy tab instead.

## Extending upstream without touching it

The operator's instruction was to *extend* eximo84's capabilities, not override them. That is
enforced structurally rather than by intention:

- every one of the 41 upstream templates is loaded **verbatim**, and this was verified by
  diffing the live `button_card_templates` against the repo files — byte-identical, no
  missing, no extra, no content drift;
- the additions this household needed are **two** templates, `vg_room_master` and `vg_nav`,
  under a `vg_` prefix that cannot collide;
- they live in a **new file**, `Custom Buttons/vg-extensions.yaml`, beside upstream's. Not one
  upstream file was edited, so the library can be re-pulled without a merge.

### The one place upstream is routed around rather than fixed

`view_light_button_style` — the base of the `view_hue_*` family — carries a hardcoded
entity in its label template:

```js
var bri = states['light.office'].attributes.brightness;
```

There is no `light.office` on this instance. Editing it would have been overriding upstream,
so the room views build on **`view_light_layout`** instead, via `hue_color_bulb`,
`hue_white_bulb` and `hue_led_strip`. Those are equally upstream's, carry the same inline
SVGs, and take their state line from a variable the card supplies rather than from a fixed
entity id. The broken template is still loaded, untouched, for anyone who wants it.

A second upstream artefact was left alone for the same reason: `Room View Automation and
Scene Button.yaml` has a malformed example dashboard appended after its templates, which
makes the file invalid YAML as a whole. The export reads only each file's
`button_card_templates:` block and stops at the next top-level key, so upstream's broken
example costs nothing and is not ours to repair.

### Bulb template per light, chosen from capability not model string

`supported_color_modes` was read from each light rather than inferred from its model name:

| light | modes | template |
|---|---|---|
| The Moon, Hugo, Torchere, Stairs, Bunny | `color_temp` + `xy` | `hue_color_bulb` |
| Aurora (Govee) | `color_temp` + `rgb` | `hue_led_strip` |
| Gallery, Office Main, Entrance | `color_temp` or `brightness` only | `hue_white_bulb` |

The white templates fill from `--button-card-light-color-no-temperature`, which is correct:
a white bulb's icon should not track a colour it cannot produce.

## Verified

Re-run after the propagation, not just after the pilot:

- **41/41 upstream templates byte-identical** to the repo files — checked again at the end, so
  none of the nine transforms disturbed the library.
- **Every `template:` a card names is defined** — 9 distinct across both dashboards, none
  undefined.
- **Every `custom:` card type has a registered resource** — all 11 in use resolve. This is the
  analogue of the entity wiring check and it is the only thing that catches a card type with no
  JavaScript behind it; such a card renders an error box and no entity check would notice.
- **Every entity named anywhere exists** — 361 referenced across both dashboards *including
  inside the button-card JS templates*, which are plain strings in the config and so fall inside
  the same scan. One hit: `light.office`, which lives only inside upstream's dormant
  `view_light_button_style`. Confirmed unreachable from any real card by expanding the template
  graph transitively from the cards actually in use.
- **No debug keys left behind.** The transforms carried counters on the view objects; the final
  sweep confirms none survive.
- The anonymised export round-trips across all seven files, canaries unmoved, zero hits for any
  scrubbed term.

**Deliberately not exported:** the admin panel. It carries Wi-Fi network names, firewall rules
and VPN route names, which is the kind of detail a public reference repo has no business
holding — a different reason from the anonymisation rule, and a standing one.

**Not verified: how any of it looks.** No view was rendered. Card geometry — upstream's
150px card heights against Home Assistant's 12-column section grid, and the `grid-template-areas`
each template sets — is the most likely thing to need adjustment, and it is exactly what a
screenshot would show and reasoning will not.

## Propagated to every other view — same day

The room views were the pilot; the operator asked for the rest. **197 button cards** now, across
both dashboards. The rule that decided each card is one sentence:

> Convert anything that is just *icon + name + state*. Keep every graph card, every tile carrying
> a `trend-graph` or `bar-gauge` sparkline, and every slider, dropdown, stepper, command row or
> mode selector.

That boundary is not taste, it is capability. **button-card cannot draw a graph and cannot move a
slider.** Converting a tile that carries one would have cost function to buy consistency, and the
operator's instruction was explicitly *"just don't kill the graphs — I like them"* (the outside,
CO₂, temperature and humidity ones by name). So:

| view | converted | kept as-is | why they were kept |
|---|---:|---:|---|
| Home | 26 | 7 | media players, vacuum card, alarm mode row |
| Climate | 13 | 16 | **20 mini-graphs**, weather forecasts, purifier speed, AC mode+temp |
| Climate — advanced | 26 | 38 | 21 sliders, 12 toggles, 5 counter steppers |
| Energy | 18 | 23 | statistics graphs, bar gauges, energy cards |
| Appliances | 35 | 9 | program selectors, vacuum and lock command rows |
| Security | 7 | 3 | alarmo card, camera picture |
| admin: System / Network / Water | 72 | 11 | health markdowns, trend sparklines, selectors |

`Home (classic)` was left alone entirely — it is the rollback view, and a rollback that has been
restyled is not a rollback.

Two classes of card needed real translation rather than a mechanical swap, because their logic
lived in Jinja and button-card speaks JavaScript:

- **the twelve Home room tiles**, whose documented tap-toggles / hold-opens gesture model had to
  survive intact (see [room-tile-navigation.md](room-tile-navigation.md)). They now take
  `grp` / `ac` / `pres` / `special` as button-card `variables`, so one label expression and one
  colour expression serve all twelve rather than twelve hand-written pairs;
- **the Energy socket cards**, which had to keep the property that *no gesture toggles a socket* —
  every one is still `tap_action: more-info`, and the wattage-or-`Off` line and load colouring are
  the same logic re-expressed.

One upstream quirk surfaced during the propagation and is worth recording: the HomeKit-style
`standard_btn_states` keys its styling off `entity.state`, so the one card with **no entity** —
Home's *all lights off* button — uses `standard_btn_layout` alone. Composing the two templates is
otherwise the standard pairing across all 197 cards.

## The propagation was a regression, and what it cost

The operator's verdict on the pass above: *"the admin panels don't render correctly (all three
of them) … the buttons are of inconsistent sizes, and they don't look aesthetically pleasing -
the radiation dose rate for example - is giant … the switch buttons no longer show load in a
graph (like the ACs do)."* All three were real, and all three were mine.

**The admin panel did not render at all.** button-card resolves `template:` names against *the
dashboard the card lives on*. Every admin card named `standard_btn_layout` and
`standard_btn_states`, which existed only in the `lovelace` config, so 72 cards across three
views could not resolve a template.

The worse part is the check. It walked **both** dashboards' cards and compared them against
**one** dashboard's library, so it reported "every template a card names is defined" while being
structurally incapable of seeing the failure. That is the exact defect this repo keeps
relearning — *a check that cannot fail is worse than no check* — arriving this time in the
verification rather than in the code.

**The giant card was one inherited property.** `standard_btn_layout` sets `aspect_ratio: 1/1`, so
height follows width: the same template is a small square at `columns: 4` and a full-width square
at `columns: 12`. The radiation card was at 12. Nothing was wrong with any individual card; the
inconsistency was emergent, and every converted card had it.

**The sockets lost their meter** because the rule "keep anything with a graph feature" was written
when button-card could not draw one. It kept the AC tiles as tiles with their `bar-gauge` and
converted the sockets to plain numbers — so two things that should read alike stopped matching.

### What replaced it

A small vocabulary, `vg_stat` / `vg_room` / `vg_meter`, informed by the form guidance the operator
asked for: *a single current value is a stat tile; a single ratio against a limit is a meter.*

- **`vg_stat`** sets no aspect ratio and `height: 100%`, so the section grid owns the height and
  `grid_options.rows: 2` makes every card the same size by construction rather than by care.
- **Text wears text tokens.** Name is `--secondary-text-color`, value is `--primary-text-color`;
  only the icon carries the status colour. The first pass let `standard_btn_states` recolour the
  text, which is the anti-pattern of identity-by-colour-alone.
- **`vg_meter`** draws the track button-card lacks, as a custom field. Sockets and ACs now read
  identically, which is what was asked for.
- The three shared templates are **defined in both dashboards**, which is what makes the admin
  panel resolve.

### The ceilings are measured, not guessed

A meter is only honest if its limit means something. The first ceilings were invented; they are
now read from two weeks of recorder statistics:

| socket | observed peak | ceiling |
|---|---:|---:|
| TV | 246 W | 300 |
| Media corner | 88 W | 150 |
| Vacuum dock | 1430 W | 1600 |
| Toilet down | 1410 W | 1600 |
| Toilet up | 793 W | 1000 |
| PoE network | 37 W | 60 |
| LR powerline | 34 W | 50 |

**The air conditioners deliberately keep 1500 W, their equipment rating, not their observed peak.**
Two weeks of shoulder-season data shows them under 120 W; the moment heating season starts they
will draw ten times that, and a ceiling fitted to today's data would peg every bar at full. That
is the distinction the form guidance forces: for a socket the limit is the device's own peak, for
an AC it is its capacity. The socket ceilings should be revisited if a device is replaced.

## A test suite for dashboards

`tests/climate/` is an expression oracle for the climate loop and says nothing about dashboards.
That gap is what let three broken views ship, so it now has a sibling:

**`tests/dashboards/lint.py`** reads the live `.storage` configs and checks six things, each one
written because something it catches actually shipped:

| | check |
|---|---|
| C1 | every `template:` resolves **in its own dashboard** |
| C2 | no card carries an option belonging to a different card type |
| C3 | no button-card resolves to an `aspect_ratio`, and every grid-positioned one declares `grid_options.rows` |
| C4 | every entity named anywhere exists — **including inside button-card JS**, which a structural walk over `entity:` keys would miss |
| C5 | every `custom:` card type has a registered resource |
| C6 | no scratch key left on a view by a transform |

C4 scans only the **reachable** surface — views plus the templates cards actually reach — so
upstream's dormant `view_light_button_style` and its hardcoded `light.office` do not fail the
build today, but *will* the moment a card uses it.

**`tests/dashboards/mutate.py`** is the half that matters. It copies the live storage to a temp
directory, reintroduces each bug, and runs `lint.py` **unmodified** against it via an `HA_STORAGE`
override — so what is proven is the real script, not a re-implementation of its logic. All eight
mutations are caught, including the two that shipped and the JS-only dead entity.

Written in the order AGENTS.md requires: the lint first, run against the broken config, where it
failed on exactly the three complaints plus one latent issue. Only then the fix.

## Still unused, and available

Loading the whole library rather than the subset the room views need means these are ready
without further work: the standard/HomeKit-style button set (`light_btn`, `switch_btn`,
`climate_btn`, `half_btn`), the round HomeKit-style badges, the animated button, the weather
button, and the garbage-collection button. The scene and automation buttons
(`view_scene_button`, `view_automation_button`) are wired and waiting but have nothing to
show: this instance has **no `scene` entities**, and its four automations are climate and
purifier logic rather than anything a room page should offer.
