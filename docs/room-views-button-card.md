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

## Compaction — the third pass

*"Looks much better now, however there is some weird placement on laptop, and spaces on both
mobile and laptop views — make it more compact, don't waste real estate."*

Two causes, both measurable rather than matters of taste.

**Every card was half empty.** They were all `grid_options.rows: 2` — 120px in Home Assistant's
section grid (56px cells, 8px gaps) — carrying about 64px of content, with `align-content: center`
splitting the surplus top and bottom. `vg_stat` is now explicitly two lines and sized for
`rows: 1`:

    6px padding + 14px name + 22px value + 6px padding = 48px of 56px

`vg_meter` gains a 3px track and still fits, so a socket and an air conditioner are the same
height as a temperature reading. Across both dashboards that is **a 53% cut in stacked card
height on every view** — Home's readings drop from 3000px to 1400px, the admin Network view from
4080px to 1904px.

**The laptop had a dead column.** Home and Energy set `max_columns: 3` while *every* section was
`column_span: 2`. Two span-2 sections cannot share a 3-column cap, so the third column was empty
on every row. Raising the cap to 4 lets two sections sit side by side; because `max_columns` is a
*cap* and Home Assistant reflows on available width, this cannot make a narrow screen worse.

**And the room tiles were six-up.** They sat at `columns: 4`, which in a `column_span: 2` section
is 6-up on a laptop and 3-up on a phone — too narrow for *Living room / On 60% · 22° · here*, so
every label truncated. Everything is now on a **6 / 12 / full** ladder: 4-up laptop, 2-up phone.
The room tiles' presence indicator moved from a third line into the label, which is what let them
become two-line cards like everything else.

Check **C7** encodes all three rules — `rows: 1` for the `vg_stat` family, columns on the ladder,
and `max_columns` a multiple of `column_span` — and three of the eleven mutations exist to prove
it still fails when any of them is undone.

## Seven cards rendering a dash — C8

The compaction pass folded the room tiles' presence line into their label, which meant rewriting
that label. The rewrite was applied by template name:

```python
if "vg_room" in names:
    c["label"] = LBL          # the ROOM label
```

`vg_room` is "name plus label, no value" — and the six Home quick tiles (Lights, Indoors, Alarm,
Outside, Air quality, Žorik) and Energy's *Cheapest block* are also name-plus-label cards, so they
were on `vg_room` too. All seven had their bespoke label overwritten with one that reads
`variables.grp`, `variables.ac`, `variables.pres` — variables only a real room tile defines. Every
lookup came back undefined, the parts list stayed empty, and each card fell through to its `'—'`
fallback.

Nothing errored. The cards rendered, sized correctly, passed C1 through C7, and said nothing.

**C8** closes that class: *a card's own JS may only reference `variables.x` that the card, or a
template it uses, actually defines.* It is deliberately scoped to **card-level** strings — a
template's own JS may reference an optional variable it null-checks, which upstream's
`view_sensor_layout` does with `custom_s2`, and flagging those would be a check failing for the
wrong reason.

It found **seven**, not the six that were reported: Energy's *Cheapest block* had the same
clobbering and had not been noticed. That is the argument for the check over a careful re-read.

Each restored label was then verified by replicating it against live state — *All off*,
*22.9° · 45%*, *Armed home*, *17° · 0% rain*, *Fair · PM2.5 2*, *Charging · 100%*,
*13:00–14:00 · now* — rather than by inspecting the JS and declaring it correct.

### Background radiation moved to the heading

The dose-rate card is gone; CPM now rides the *Background radiation* heading as an entity badge,
the same pattern the *Outside* heading already used for temperature. The 24 h dose-rate graph
stays.

**One thing that move costs, and what replaced it.** The old card coloured itself by dose — grey
when the counter was silent, green, amber at 0.3 µSv/h, red at 1.0. A heading badge cannot do
that: `color` on a badge takes a token or hex and **not** a template. Dropping the card would
therefore have quietly dropped the only visual warning this instance has for radiation.

So the card is not deleted, it is made conditional: it reappears, red, only when
`sensor.radiation_dose_rate` is **above 0.3 µSv/h**. Zero space at background levels, and the
warning survives. That is the same rule the rest of these dashboards follow — only live state
earns space — applied to a threshold rather than to a reading.

### Prose off the dashboards

The CO₂ card's closing sentence — *"The purifier does not reduce CO₂ — it filters particulates.
Only fresh air does."* — is gone at the operator's instruction. It was explanation, not state, and
explanation belongs here rather than on a wall the household reads daily.

## Still unused, and available

Loading the whole library rather than the subset the room views need means these are ready
without further work: the standard/HomeKit-style button set (`light_btn`, `switch_btn`,
`climate_btn`, `half_btn`), the round HomeKit-style badges, the animated button, the weather
button, and the garbage-collection button. The scene and automation buttons
(`view_scene_button`, `view_automation_button`) are wired and waiting but have nothing to
show: this instance has **no `scene` entities**, and its four automations are climate and
purifier logic rather than anything a room page should offer.

## The pages did not grow, and that was the whole point of the page

*2026-09-23, later the same day.*

> "i added more lights and theyre not showing up in the room dashboards (hallway
> specifically) and the new light doesnt show in corridor (i replaced one and moved the bulb
> to hallway) … make sure that all future entities are automatically added to the area
> dashboard once added? lights and all? … i thought the dashboards were dinamic and would
> automatically grow/enhance their capabilities over time. is it even possible?"

Three separate complaints, one cause. The room views above had been
`strategy: {type: home-area}` — Home Assistant deciding the contents from the area, every
render. Rebuilding them on button-card replaced a generated page with a **hand-written card
list**, and a hand-written list is a snapshot of the registry on the afternoon it was typed.

What that cost, precisely:

| symptom | why |
|---|---|
| Hallway showed no lights | the page was written when the area had none; `light.stairs` and `light.hallway` are in it now |
| Corridor missed the replacement bulb | the page named `light.livingroom_stairs`, which had been renamed to `light.stairs` and moved to Hallway; `light.corridor_light` was never named |
| The Hallway tile read `—` | its `grp` variable was `""`, frozen from when the area had no Magic Areas group |
| The admin *Paired, not yet placed* list never changed | it was a hand-typed inventory of IEEE-named entities |

The honest answer to *is it even possible* is yes, and the design record should say why the
generated version was given up in the first place: nothing was wrong with it except that it
could not be styled. **That was a bad trade and it is now reversed** — the pages are generated
again, and styled, because the generation happens in a card rather than in a strategy.

### What replaced the card lists

[`auto-entities`](https://github.com/thomasloven/lovelace-auto-entities) (HACS). Each block of
a room page is a filter over the entity registry rather than a list of ids:

```yaml
type: custom:auto-entities
card: {type: grid, columns: 1}
card_param: cards
show_empty: false
filter:
  include:
    - domain: light
      area: hallway
      options: {type: custom:button-card, template: hue_white_bulb, entity: this.entity_id}
  exclude:
    - {entity_category: config}
    - {entity_category: diagnostic}
    - {label: not_on_room_pages}
```

Three facts about the card were read out of the shipped `auto-entities.js` rather than taken
from its README, because each one decides a design detail:

- **`this.entity_id` is substituted anywhere in `options`, at any depth.** The card serialises
  the options object and string-replaces. That is what lets a generated bulb card keep its
  inline `slider-entity-row` and its separate power pill — both of which name the entity a
  second time, nested. Without it the generated cards would have been flat tiles.
- **`area:` matches the area's *name or id*, resolved from the entity, falling back to its
  device.** Identical to the fallback the tiles use, so "in this room" means one thing.
- **`$$` matches against the JSON of an attribute.** `supported_color_modes` is a list, and a
  list is otherwise untestable. `"$$/xy/"` is how a bulb is asked whether it can do colour.

That last one is what keeps **upstream's templates unedited**. Rather than one bulb template
with a capability switch inside it — which would have meant copying upstream's inline SVGs into
a `vg_` template — there are three include rules, most specific first, deduplicated with
`unique: entity`:

| rule | matches | template |
|---|---|---|
| `supported_color_modes` contains `xy` | Hue colour bulbs | `hue_color_bulb` |
| contains `rgb` | the Govee strip | `hue_led_strip` |
| anything else | white and brightness-only bulbs | `hue_white_bulb` |

A bulb takes the first rule that fits. A *new* bulb takes one too, without anybody choosing.

**The headings are generated as well.** A heading is its own `auto-entities` card with
`card_param: badges` and `show_empty: false`, so *Media* exists on a page only while that room
has a media player, and appears in the same render as the first one. It carries up to three
live badges. This is the rule the rest of these dashboards already follow — only live state
earns space — applied to the label rather than to the card.

### The tiles resolve their own room

The Home room tiles had the same disease in a smaller space: `grp`, `ac` and `pres` were entity
ids pasted in at authoring time. They now take **one variable, `area`**, and resolve the room's
group, bulbs, thermostat and presence sensor from `hass.entities` on every render — button-card
hands JS the whole `hass` object, so the registry is reachable from inside a card.

The gesture model in [room-tile-navigation.md](room-tile-navigation.md) is unchanged, and for
the first time it is *structurally* true. That document promised a room with no lights "starts
working by itself the moment a light is added to the area"; with a pasted group id that was
aspiration. Tap is now:

```yaml
tap_action:
  action: perform-action
  perform_action: "[[[ …any light on in this area? … ]]]"   # turn_off : turn_on
  target: {area_id: "[[[ return variables.area; ]]]"}
```

button-card evaluates templates inside action configs — plain Lovelace does not, and the HA
docs say so — which is what allows the group's *semantics* (any on → all off) to survive
without naming a group. Checked in the bundled `button-card.js`, not assumed.

**No tile renders a dash any more.** A room with neither lights nor climate falls back to its
presence sensor and says `Empty` or `● here`. A room whose bulbs are all unreachable says
`Unavail` rather than reporting `Off` for a light nobody can switch — the corridor is in
exactly that state as this is written, and the first draft of the label quietly said `Off`.

### Curation moved into Home Assistant

A generic filter cannot carry exceptions, and the moment it does it stops being generic. So the
exceptions live in the registry instead, as a label — **`Not on room pages`** — applied to 33
entities:

- every raw reading that already **feeds a resolved `sensor.climate_*`** shown on the same page.
  A child's room would otherwise show four temperatures (meter, AC, TRV, resolved) and invite the
  reader to wonder which is true. Which entities those are was read out of each template
  helper's own config, not guessed;
- the two `light.gallery` member bulbs, which the fixture group already represents;
- `sensor.background_radiation_total_counts`, a monotonic accumulator that
  [dashboard-surfacing-2026-09.md](dashboard-surfacing-2026-09.md) had already ruled off the
  dashboards.

Anyone can now suppress an entity from its room page by labelling it, with no dashboard edit
and no code change. That is the same instinct as the rest of this repo: make the general case
structural and let the exception be data.

**Energy readings are excluded by device class, not by label** — `power`, `energy`, `voltage`,
`current` and their relatives, in one regex. Without it the living room's Conditions block came
to **34 cards** of per-socket watts and kWh, which would have undone the consolidation that put
socket monitoring on the Energy tab. It was measured before it shipped, not after.

### Sockets stay off the room pages, and are excluded by class

The first version of this change put switches on the room pages wholesale, which brought the
sockets back with them. The operator's correction was immediate and is the same sentence that
settled their design the first time:

> "exclude sockets from the room views, too - theyre there only for measuring energy
> consumption"

So the **2026-09-23 consolidation stands unreversed**: sockets live on the Energy tab, and the
two rooms whose only device is a socket keep their link out to it rather than a switch.

The interesting part is how they are excluded. A list of seven entity ids would have been the
same mistake this whole document is about — correct on the day it was typed, and silently wrong
the next time a plug is bought. The exclusion is therefore **by device class**:

```yaml
exclude:
  - {attributes: {device_class: outlet}}
```

That only worked after fixing the data. **Only the two Tuya SP112s declared
`device_class: outlet`; the five Zigbee2MQTT plugs reported nothing at all**, so a class-based
rule would have caught two of seven and looked like it worked. All nine outlet entities — seven
plugs plus the two USB gangs — now carry the class in the entity registry, which is also simply
correct metadata and gives them the right icon.

The remaining seam is honest and worth stating: **a newly paired plug that does not declare
itself an outlet will appear on its room page** until someone sets *Show as: Outlet*. That is a
one-field fix in the entity settings, and it is a far smaller seam than a hand-maintained list.

An earlier draft tried to close it entirely with a registry-side rule — *a switch whose device
also reports power must be an outlet* — and it was dropped: that catches every air conditioner's
display-lighting and sound-effect switch too, and **a check that fails for the wrong reason is
worse than no check**. The heuristic that would have distinguished them (the switch's object id
equals its device's slug) fails on the two SP112s, whose entity ids are area-prefixed while
their device names are not. So the invariant is asserted where it is exact, on the dashboard:

| | check |
|---|---|
| C12 | no room page generates a `device_class: outlet` entity |

**C12 found a gap in its own fix.** Written first and run against the live config, it reported
**24** offending blocks rather than twelve: the *heading* cards filter on `switch` too, so the
Controls heading would have carried a live socket badge above a card that no longer listed it.
The exclusion now goes on both.

One thing did not change: `switch.poe_network` and `switch.lr_powerline` also carry the
`not_on_room_pages` label. They feed the switches, access points and powerline adapter, and a
mis-tap drops the network. Belt and braces is proportionate there — the class rule alone would
be undone by one person clearing a device class.

### The checks came first, and two of them caught this change

Written against the broken config before anything was fixed, in the order AGENTS.md requires:

| | check |
|---|---|
| C9 | every entity an **area** holds is reachable from that area's room view — named outright, or matched by an auto-entities rule for that area and domain. It is driven from the **area registry**, so a room that loses its tile or its page fails loudly instead of dropping out of the loop |
| C10 | a Home room tile resolves its room from `variables.area` and names no per-room entity id, so it cannot freeze at the moment it was written |
| C11 | `home-classic` carries none of the rebuild's vocabulary — no button-card, no auto-entities |
| C12 | no room page generates a `device_class: outlet` entity — see above |

C9 and C10 failed on the live config exactly as intended: twelve tiles pinning entity ids,
twelve areas whose pages could not be checked at all.

**C11 exists because the fix broke something the lint could not see.** The transform found the
room tiles by their section heading, *"Rooms"* — and `Home (classic)` has a section with that
heading too, built from native `area` cards. The first dry run silently restyled the rollback
view. A rollback that has been restyled is not a rollback. The transform now matches the Home
view **by path**, and C11 makes the leak fail a build rather than depend on someone noticing.

This is the third time in this repo that *selecting by a name instead of by structure* has hit
the same class of bug — `vg_room` clobbering seven unrelated cards (C8), the template check
comparing against the wrong dashboard's library, and now a heading shared by two views. It was
caught here only because the change was dry-run against a copy of `.storage` and diffed before
being written to the live instance, which is now the standing procedure:

1. write the transform to a file;
2. apply it to a **copy** of `.storage`, run `lint.py` and `mutate.py` against the copy;
3. push it through `ha_config_set_dashboard(python_transform=…)`;
4. **diff the live config against the tested copy** and require them to be identical.

Step 4 is the one that makes step 2 mean anything — it proves the thing that was tested is the
thing that shipped.

`mutate.py` now carries **19** mutations, seven of them new, including the two that started this
(a tile pinning its light group; a page losing its lights rule) and the rollback restyle.

### The export is code now

`tests/dashboards/export.py` re-exports the sanitised snapshots, applying the anonymisation
rules AGENTS.md states as prose: lookaround anchors that treat `_` as a boundary, multi-token
forms before general stems, 22 canary words counted before and after, and a scan of the result
for every original term. The live names are not in the script; it reads them from the same
gitignored file `leakcheck.py` uses, and refuses to run if that file is missing rather than
exporting raw.

### Not verified

- **How any of it looks.** No view was rendered. The generated blocks are new geometry — a grid
  card inside a section grid — and that is exactly what a screenshot would show and reasoning
  will not.
- **That a newly added entity appears.** The filters were replicated against the live registry
  to predict each page's contents (133 generated cards across the twelve), and the tile labels
  were replicated against live state. Neither is the same as adding a bulb and watching it turn
  up, which is the one test that would actually close this.
- **`auto-entities` is a new runtime dependency** on the dashboard the household uses daily.
  Its resource is registered and C5 now covers it, so a missing resource fails the lint — but a
  breaking change in the card itself would take every room page's contents with it.
