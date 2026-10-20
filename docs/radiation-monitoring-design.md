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

## The operator's previously-working config, and what it settled

After two days of zero counts the operator produced a configuration that had worked on this
same hardware. Four things in it differ from what reasoning had produced here, and the
reasoning lost.

```yaml
pin: 13                    # no mode block, no pull-up
count_mode: {rising_edge: DISABLE, falling_edge: INCREMENT}
use_pcnt: False            # SOFTWARE counting
internal_filter: 180us     # ten times PCNT's hard ceiling
```

**`use_pcnt: False` is the headline.** This design used the ESP32's hardware pulse counter, on
the argument that the board is also a bluetooth proxy — counting in an ISR competes with radio
interrupts, while hardware counting cannot miss a pulse. That argument is still true and it was
still beside the point: the working config counted in software, and the PCNT version counted
nothing at all. The cost is bounded anyway — background is roughly **0.3 pulses per second**,
so the interrupt fires far too rarely for radio contention to matter.

**`internal_filter: 180us` is the evidence that made it make sense.** PCNT's glitch filter tops
out at 1023 APB cycles — **12.8 µs** — which is why this config had been sitting at 13 µs and
then 1 µs. A known-good value an order of magnitude above that ceiling says the pulse from this
board is **wide**, and that the filter exists to reject *ringing on a long pulse* rather than RF
pickup. That combination is simply not expressible with PCNT.

**The pull-up was removed.** It had been added the same day as the leading hypothesis — these
boards often drive the pulse open-collector, which needs a pull-up to have a level to pull down
from. The working config has no pull-up, which means this board drives the line itself. The
hypothesis was reasonable and is now retired.

**Edge polarity was a red herring, correctly.** The working config also counts falling edges
only, confirming the earlier conclusion that polarity could not explain zero counts.

### Two things in it deliberately NOT adopted

**`offset: -12.0`** subtracts 12 CPM before scaling, described in the upstream example as
"background noise". It is not noise — it *is* the background, and this instrument exists to
measure background. Subtracting it would park a healthy house at roughly zero and hide exactly
the drift worth seeing. (It also comes from the same upstream example as the obsolete factor
below, which is not a reassuring provenance.)

**`multiply: 0.0081203703703704` with `unit_of_measurement: 'μSv/h'`** converts on the device,
using the **obsolete 18 CPS/mR/h** factor. Current J305 datasheets declare 44, giving 0.00332 —
a 2.45× difference, derived earlier in this document. The conversion stays in Home Assistant
behind a helper so that confirming a tube is a slider move rather than a reflash, and so the
count history survives changing it.

## Zero counts is not a measurement of zero radiation

The dose sensor reported **0.0 µSv/h** for a day while its signal wire was on the wrong header
pin. That is worse than reporting nothing: it writes a confident, false zero into long-term
statistics and puts a reassuring number on the dashboard, from an instrument that is
disconnected.

The original design said the opposite — *"0 CPM is data; unavailable is not"* — and that was
wrong on the physics. Counts from a GM tube are **Poisson**. A J305 sitting in ~20 CPM
background has a probability of **e⁻²⁰, about 2 in a billion**, of recording exactly zero
across a 60-second window. There is no such thing as zero background at ground level, so a
sustained 0 CPM does not mean "no radiation" — it means **no pulses are arriving**.

The cutoff is therefore `>= 1`, and it deliberately sits at one count rather than at some
plausibility floor: one count in a minute is a real, if statistically lonely, measurement.

### It had to be `availability`, not an empty state

The first attempt gated inside the `state` template, rendering an empty string below the
cutoff. **It did not work.** Home Assistant kept the entity's previous numeric value — the
dashboard went on showing `0.0 µSv/h`, `last_updated` stopped advancing, and the sensor
stopped responding to its own inputs. Verified directly: the stored template rendered to `[]`
while the entity still read `0.0`.

`availability` is the mechanism HA provides for exactly this, and it behaves correctly — the
entity goes `unavailable`, which is the honest state for *the instrument is not giving me a
reading*:

```jinja
state:        {{ (cpm * factor) | round(3) }}          {# pure arithmetic #}
availability: {{ cpm | float(-1) >= 1 }}               {# the gate #}
```

Keeping the state template as pure arithmetic and the gate entirely in `availability` also
means the two never disagree.

**The suite had a blind spot here and now does not.** `load_sensor_templates()` read only
`state`, so an availability template was invisible to it — a sensor could be gated, or
un-gated, with every case still green. Availability templates are now extracted as
`"<title>::availability"` and tested like any other expression, with two mutations against
them. Note they are stored nested under `additional_options` by the config flow, though HA
flattens them on setup, so the extractor checks both shapes.

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

## Alerting on a sustained elevation: measured first (issue #9, 2026-10-20)

The request: notify when the level stays above background, not on one high minute. The
threshold has to come from a measured baseline, and the measurement came first. **It found that
the instrument is not ready to alert on**, and why.

### What ten days of counts say

The recorder holds per-minute counts from 2026-10-10 to 2026-10-20 (14 960 numeric readings,
3 833 unavailable rows from proxy reconnects). Read straight from the database, read-only:

| | all readings | dark readings only |
|---|---|---|
| mean | 57.4 CPM | **22.6 CPM** |
| median | 28 CPM | 22 CPM |
| variance ÷ mean | **57** | **1.1** |
| max one-minute | 385 CPM | 46 CPM |
| max 60-minute mean | 291 CPM | **25.7 CPM** |

A GM tube in a steady field counts Poisson: variance ÷ mean ≈ 1. In the dark it does, at 1.1,
around a background of 22.6 CPM (0.075 µSv/h at 0.00332). That is a healthy J305, and it is the
baseline. Across the whole day the variance is 57 times the mean. That is not radiation.

**The excess follows the light.** Median counts by hour (local time) are 22 CPM from 18:00 to
07:00, then rise to 44 at 08:00, 103 at 10:00 and 154 at noon, and are back to 23 by 18:00. The
correlation of the counts with indoor illuminance is r = +0.74 (kitchen) and +0.61 (hallway),
against +0.20 for the hallway temperature. Taking only the minutes when the hallway reads
below 5 lx leaves a mean of 23.1 CPM and variance ÷ mean of 1.09: the dark minutes are the
clean ones, by any of the three measures.

**The likeliest cause is light on the tube, and that is a hypothesis, not a finding.** The J305
is a glass tube, and a GM tube's cathode can respond to light. But all the data shows is that
the excess comes with the light. Daytime is also when the house is busy, so other causes that
follow the day are not excluded (companion review, 2026-10-20):

- **Bluetooth proxy activity.** The same ESP32 is a busy BLE proxy (3 833 reconnect rows in ten
  days). Daytime radio traffic or reconnect replays would also be quiet at night.
- **Mains or RF pickup** from appliances in daytime use.
- **Board temperature.** Only the hallway's air temperature was correlated (r = +0.20); the
  board's own temperature is not measured.
- **Radon** is the least likely. Indoor radon usually *peaks at night*, with the windows shut
  and no ventilation, the opposite of this curve. But radon progeny would be real radiation, so
  it is named here rather than dismissed.

**The sleeve is also the experiment.** If shading the tube flattens the daytime curve, light was
the cause. If the curve survives shading, the next suspects are the proxy and pickup, in that
order. That test needs a fork, not a threshold.

**What a naive alert would have done.** On the whole-day data, a 60-minute mean above 1.5 ×
the median would have fired on most sunny days, every day by noon. That is the alert this
issue warned against shipping. The measurement caught it.

### Prerequisite: shade the tube, then measure again

Put the tube in the dark: an opaque sleeve or black heat-shrink over the glass, or the board in
an opaque enclosure. Beta particles still pass a thin sleeve, and gamma passes anything this
small. Then repeat the measurement over at least **three full days, sunny ones included**.

Pass mark: variance ÷ mean ≤ 1.3 across the whole day, and no hour-of-day median more than
20 % above the night median. Both are computed by the same read-only query as the table above.
Until that passes, any daytime alert measures whatever the daytime excess is, not background.

If it does not pass after shading, the light hypothesis was wrong: correlate the counts with the
proxy's connection events and with appliance power next, before thinking about any threshold.

### The alert, once it does

Every number below is a value in a helper, not a constant, so re-tuning is never a code change.

| piece | how | value from the measurement |
|---|---|---|
| `input_number.radiation_baseline_cpm` | the measured background | **22.6** (re-measure after shading) |
| `input_number.radiation_alert_factor` | how far above background counts as elevated | **1.5** |
| `sensor.radiation_cpm_mean` | native `statistics` helper, mean of `sensor.background_radiation_cpm`, `max_age` 60 min, `sampling_size` 120 | window from the table |
| `binary_sensor.radiation_elevated` | template: mean > baseline × factor, availability needs ≥ 45 samples in the window, `delay_on` 30 min | "sustained" |
| automation | elevated `on` → both adults, once, with the mean and the baseline; `off` → a short "back to background" | notify only |

**Why these numbers.**
- *60-minute mean.* At 22.6 CPM the Poisson standard deviation of a 60-minute mean is
  √(22.6 / 60) ≈ 0.61 CPM. The highest dark 60-minute mean in ten days was 25.7, which is
  +5 σ. Fluctuation alone does not leave that band.
- *Factor 1.5* means 34 CPM, about +18 σ on the 60-minute mean: no fluctuation reaches it,
  and a 50 % sustained rise does. The factor is a helper because what is worth a phone call is
  the operator's judgement, not the tube's.
- *`delay_on` 30 min on top of the 60-minute window.* The level has to stay above the line for
  half an hour after the window first crosses it. One burst, a reconnect replaying counts, or a
  short spike cannot fire it.
- *Availability on sample count.* The proxy drops off now and then (3 833 unavailable rows in
  ten days). A mean over three samples is not a 60-minute mean.

The `statistics` window is a helper *option*, edited in the UI, not an `input_number`. The
native helper takes it as configuration, and a template re-implementing a moving average to
make it a slider would be a second copy of what `statistics` already does.

**An interim option, if waiting for the sleeve is not acceptable:** evaluate only while the
hallway is dark (`sensor.hallway_presence_illuminance` < 5 lx; those minutes are Poisson-clean,
as above). It would catch a sustained elevation overnight and miss one that starts and ends in
daylight. It is not built: shading the tube fixes the cause, and the gate would only hide it.

### Not built yet, on purpose

No helper, sensor or automation from the table exists on the instance. The design is complete.
What is missing is a baseline that holds in daylight, and that waits for the sleeve.
