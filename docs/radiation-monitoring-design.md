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
hour is counts multiplied by a **per-tube sensitivity factor** — 0.00812 µSv/h per CPM for a
J305, 0.0065 for an M4011, 0.0057 for an SBM-20. Those differ by 40 %.

So the factor is an `input_number`, not a constant:

| | |
|---|---|
| `sensor.background_radiation_cpm` | ESPHome, 60 s window, tube-independent |
| `input_number.radiation_usv_per_cpm` | the tube's sensitivity — range 0.001–0.02, seeded 0.00812 |
| `sensor.radiation_dose_rate` | `cpm × factor`, µSv/h |

```jinja
{% set c = states('sensor.background_radiation_cpm') | float(-1) %}
{% set k = states('input_number.radiation_usv_per_cpm') | float(0.00812) %}
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

## Reading it once it runs

Background for a J305 is roughly **10–30 CPM**, i.e. **0.08–0.24 µSv/h**. Two failure
signatures:

- **exactly 0 CPM, always** — the divider is on the wrong net, or the output is not where
  it was assumed to be
- **hundreds or thousands of CPM** — the input is floating, because the board's output is
  open-collector with no pull-up. Add 10 k from VOUT to the board's **3V3** (not to 5 V).

The first 60-second window reports nothing; the counter needs a full window before it
publishes anything real.

## What is not covered

The suite tests the **conversion**, not the counting. Pulse capture, the divider, the
`50us` filter value and whether GPIO13 is the right pin are all hardware facts that only
the running device can settle. A green suite says the arithmetic is right; it says nothing
about whether a single count ever arrives.
