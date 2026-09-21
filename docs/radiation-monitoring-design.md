# Background radiation monitoring

*2026-09-21. A Geiger-Müller tube on the ESPHome bluetooth proxy.*

## What it is

A GM tube on an interface board, wired to **GPIO13** of the 30-pin ESP32 DevKit that
already runs as a bluetooth proxy (`geiger-counter-ble-proxy`). The board emits one pulse
per detected ionising event; ESPHome counts pulses over a 60-second window.

The tube is believed to be a **J305** from the listing photo. **The marking on the glass
has not been read yet**, and the whole design below is arranged around that not mattering
very much.

## The split: counts on the device, dose in Home Assistant

ESPHome publishes **counts per minute** and nothing else.

Counts per minute is a property of *the tube and the radiation field*. Microsieverts per
hour is counts multiplied by a **per-tube sensitivity factor**, and that factor is derived
from the tube's declared gamma sensitivity rather than looked up:

```
factor (µSv/h per CPM) = 1 / (S × 60 / 8.77)

    S     declared gamma sensitivity, CPS per mR/h, from the datasheet
    60    seconds per minute
    8.77  mSv per R — the absorbed-dose coefficient for a human phantom,
          photon energies 100 keV – 3 MeV
```

| tube | S (CPS/mR/h) | factor |
|---|---|---|
| **J305, current datasheet** | 44 | **0.00332** |
| J305, obsolete datasheet | 18 | 0.00812 |
| SBM-20 | — | 0.0057 |

**The obsolete figure is the one everybody copies.** 0.00812 is all over DIY Geiger code and
was what this project was first seeded with, from memory. It comes from a J305 datasheet
declaring **18 CPS/mR/h**; tubes sold now declare **44**. Same arithmetic, **2.45× apart** —
using the old constant overstates background by a factor of two and a half. A mutation
(*"the obsolete 18 CPS/mR/h factor comes back as the fallback"*) now fails the suite if it
creeps back in.

Dropping the 8.77 coefficient gives 0.00378 instead, which is *exposure* rather than absorbed
dose. Dose equivalent is the health-relevant quantity, so 0.00332 is what is configured.

So the factor is an `input_number`, not a constant:

| | |
|---|---|
| `sensor.background_radiation_cpm` | ESPHome, 60 s window, tube-independent |
| `input_number.radiation_usv_per_cpm` | the tube's sensitivity — range 0.001–0.02, set **0.00332** |
| `sensor.radiation_dose_rate` | `cpm × factor`, µSv/h |

```jinja
{% set c = states('sensor.background_radiation_cpm') | float(-1) %}
{% set k = states('input_number.radiation_usv_per_cpm') | float(0.00332) %}
{% if c >= 0 %}{{ (c * k) | round(3) }}{% endif %}
```

**Why it is worth the extra helper.** Confirming the tube marking then costs one slider
move. Compiling the factor into the device would make it a reflash, and a reflash discards
nothing but still takes the bluetooth proxy down — which now matters more than it used to,
because three rooms read their SwitchBot meters through that proxy. Putting the factor in
the *template* instead would be better, but still an edit to a sensor rather than a value
change, and the history would carry a silent discontinuity with nothing recording why.

A mutation (*"the tube factor is hard-coded again"*) fails the suite if anyone inlines it.

## Zero counts is a measurement

`-1` is the "no reading" sentinel, so **0 CPM resolves to 0.0 µSv/h** while an unavailable
or not-yet-reported counter resolves to nothing at all. These are different facts: a tube
reporting no events in a minute is data, a tube that is not reporting is not. Collapsing
them would either invent a reading or discard a real one, and both are tested.

## Wiring — as built, and why it survives

The board's pulse output goes **straight to GPIO13**, powered from the VIN/GND pins beside
D13. It has been wired that way for years with no damage, so this is documented as-built and
nothing below asks for it to be changed.

That is worth an explanation, because ESP32 GPIOs are not 5 V tolerant and the output is
nominally 5 V. These interface boards almost always put a **series resistor** on the output,
or drive it through an **open-collector transistor**. With resistance in the path, the ESP32's
internal clamp diode conducts and holds the pin near 3.6 V at a current the resistor limits.
Out of spec on paper, benign in practice, and consistent with the observed lifetime.

**One measurement would settle it**, whenever convenient: DC volts between the signal line and
GND with the tube powered. The line idles at the pull-up rail and is pulsed low, so the *idle*
reading is what the pin sits at essentially all of the time.

| idle reading | meaning |
|---|---|
| ~3.3 V | the board references 3V3 — nothing to do |
| ~5 V | it has been clamping for years. Still fine as-is; a 10k/15k divider (5 × 15/25 = 3.0 V) would make it nominal if that is ever worth the soldering |

Either way the config counts **falling edges**, which is the idle-high/pulse-low behaviour
both cases produce.

**High voltage:** the board steps up to roughly 400 V for the tube, and that side stays
energised briefly after power is removed.

## Counting in hardware, and the 13 µs ceiling

The ESP32 counts pulses in **hardware** (PCNT), whose glitch filter is 1023 APB clock
cycles — **12.8 µs** at 80 MHz. ESPHome rejects a larger `internal_filter` at compile time,
which is how the first attempt at 50 µs was caught.

Software counting (`use_pcnt: false`) would allow a longer filter and is the wrong trade
here. This board is also a bluetooth proxy, so it is already busy servicing radio
interrupts; counting in an ISR that competes with them would drop events precisely when the
proxy is working — and three rooms now read their SwitchBot meters through it. Hardware
counting cannot miss a pulse for that reason.

13 µs is ample regardless. A GM pulse through the interface board is tens to hundreds of
microseconds wide, so it passes; what the filter rejects is sub-microsecond RF pickup.
Background events are milliseconds apart, so no realistic rate makes this bite.

## Reading it once it runs

Background for a J305 is roughly **10–30 CPM**, i.e. **0.03–0.10 µSv/h** at 0.00332. Two failure
signatures:

- **exactly 0 CPM, always** — the divider is on the wrong net, or the output is not where
  it was assumed to be
- **hundreds or thousands of CPM** — the input is floating, because the board's output is
  open-collector with no pull-up. Add 10 k from VOUT to the board's **3V3** (not to 5 V).

The first 60-second window reports nothing; the counter needs a full window before it
publishes anything real.

## The signal pin, and why the counter reads zero

The firmware came up healthy and published **0 CPM with 0 total counts** — not `unknown`,
which would have meant a flashing problem, but a live counter detecting nothing at all. It
stayed there for hours.

**Zero is itself evidence.** With `internal_filter` at 1 µs, a floating input reads thousands
of counts from RF pickup, not zero. Zero means the line is electrically **stable** — something
is holding GPIO13 at a fixed level, and no pulse is reaching it.

**2026-09-22: GPIO13 was confirmed wired to the pin labelled `VCC`.** That is a power input,
not the output. The standard header on these boards is **`VCC / GND / OUT`** — power the board
from VCC+GND, take pulses from **OUT** (labelled **INT** on some variants, and **VIN** on the
RadiationD v1.1 / CAJOE, whose silkscreen is wrong; ESPHome's device page for that board says
so outright). A wire from VCC to a GPIO clamps the pin and delivers nothing, forever, without
damaging anything.

### Edge polarity was ruled out rather than tried

The suggestion was to switch from trailing to leading edge. **That cannot produce counts where
there are none.** Every pulse has a rising *and* a falling edge, so counting falling edges
already registers one per pulse whichever way round the board drives the line. Edge choice
changes *when within the pulse* the count lands, never *whether* it lands.

The config now counts **both** edges with `multiply: 0.5`, which yields the identical number
and removes the question permanently. It reverts to single-edge once counts arrive — two edges
per pulse is more exposed to ringing being miscounted than one is.

`internal_filter` was also dropped from 13 µs to **1 µs** during bring-up. A filter can only
ever *remove* counts, so it is the one setting capable of turning a working signal into
silence, and it had to be ruled out before the wiring was blamed.

**Tube confirmed as J305 β/γ** (2026-09-22), so the 0.00332 factor derived above stands.

## A wiring check, because the scenario suite cannot see this class

`tests/climate/wiring.py` pulls every entity id out of the live templates and asks Home
Assistant whether it resolves.

It exists because of a bug shipped the same day: `Radiation dose rate` read
`sensor.background_radiation_cpm`, while the device actually published
`sensor.hallway_geiger_counter_ble_proxy_background_radiation_cpm` — ESPHome had prefixed the
entity with the device's area. **All five scenario cases passed**, because the suite
substitutes each entity read with a literal before evaluating; that is exactly what makes it
a decision oracle, and exactly why it cannot notice that a name resolves to nothing. The
sensor read `unknown` in the house while the tests were green.

The ESPHome entities were renamed to the short stable ids rather than pointing the template at
the long one, because the long form embeds the *area* — moving the device would have broken it
again, silently, in the same way.

The check itself had to be fixed before it was worth anything: the first version batched all
46 references into one template, the render failed, `evaluate` handed back the unrendered
source, and every reference scored "ok". It reported 46/46 clean while one was genuinely
missing. It now chunks like the scenario suite and **rejects any result that is neither `ok`
nor `MISSING`**, on the principle that a probe which cannot fail is worse than no probe.

## What is not covered

The suite tests the **conversion**, not the counting. Pulse capture, the input level and
whether GPIO13 is the right pin are all hardware facts that only the running device can
settle. A green suite says the arithmetic is right; it says nothing
about whether a single count ever arrives.
