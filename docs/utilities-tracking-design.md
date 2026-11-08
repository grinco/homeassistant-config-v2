# Gas and water tracking: design

*2026-11-08. Draft. The operator has not yet confirmed the meter details listed under Open.*

## Goal

Track gas and water consumption in Home Assistant over time, so the Energy dashboard shows
them beside electricity and so a sudden change in use is visible (a leak, a stuck tap, a
boiler that runs too often). Two sources with different characters:

- **Water:** a smart meter that emits readings over RF. Automatic, frequent, and it can be
  received with an RTL-SDR dongle (planned, not yet bought).
- **Gas:** read by hand from the meter. Infrequent, and the reading is only as good as the
  person who types it in.

Both should end in the same shape: a cumulative total that only goes up, plus a per-day or
per-month consumption derived from it. The Energy dashboard and the statistics recorder need
exactly that shape.

## Principles

- **A total, not a rate.** Store the meter's cumulative reading (m³ for gas and water). Derive
  consumption with `utility_meter` or the statistics recorder. Never store a consumption number
  as if it were a reading, because a missed reading then silently loses volume.
- **Prefer native helpers.** `utility_meter` for daily, weekly and monthly consumption; the
  Energy dashboard for gas and water once they carry the right `device_class` and
  `state_class`. Template sensors only where a native option cannot express the case.
- **Check, don't trust.** A manual gas reading is checked against the previous one and against
  the expected range before it is accepted. An RF reading is checked for a frozen value and for
  a counter going backwards.
- **Keep the raw reading.** Whatever decodes the RF packets, keep the meter's own counter. Any
  later correction (a changed decoder, a meter swap) is applied to the derivation, never to the
  stored total.

## Water (RF smart meter)

### Capture

The RTL-SDR receives the meter's radio packets. The usual tool for the common European
water-meter protocols is `rtl_433` (or `rtlamr` for utility AMR protocols; which one applies
depends on the meter's protocol, unknown until we see a packet). Plan:

1. Listen with `rtl_433` and log raw packets to a file for a day, to learn the protocol and
   the reporting interval.
2. Decode a packet by hand against the vendor's documentation, if one is public. The counter
   is usually a 32-bit value in litres or in 0.1 m³ steps. Confirm the unit by comparing one
   decoded value with the meter's own display at the same time.
3. Only then wire it into Home Assistant (below).

### Into Home Assistant

- Run the decoder as a small service on a host near the SDR, publishing each decoded reading to
  the existing Mosquitto broker over MQTT. Home Assistant already has the MQTT integration.
- One sensor for the total in m³: `device_class: water`, `state_class: total_increasing`,
  unit `m³`. `total_increasing` is what lets the recorder compute consumption across meter
  resets and gaps, provided the value never decreases. If the meter can reset, that has to be
  handled in the decoder, not here.
- `utility_meter` for daily and monthly water consumption from that total.
- Freshness: a binary sensor or a template-free check that flags when no reading has arrived
  for, say, 6 hours. A stalled SDR must not look like a dry house.

### Checks

- Reading must be >= the previous reading. A decrease is logged and rejected, not recorded.
- A flow rate sanity limit: a reading jump above the largest plausible burst in one interval
  (set after the capture, from the real numbers) is flagged rather than recorded.

## Gas (manual reading)

### Entry

A helper for the reading, entered from the phone:

- `input_number` for the reading in m³ (the counter's own unit; check whether the meter shows
  m³ or a corrected volume). Min 0, max set above the meter's rollover value. A new helper
  starts at its min, so the first entry must be seeded deliberately, not read as zero.
- `input_datetime` for when the reading was taken, defaulting to now. The operator enters the
  reading and the time it was read, not the time it was typed.

A reminder once a month (a notification the same way as the flush reminder) asks for the
reading, on a day the operator picks.

### Derivation

- A sensor that takes the entered reading as its total: `device_class: gas`,
  `state_class: total_increasing`, unit `m³`.
- `utility_meter` for monthly consumption from it.
- The gas volume to energy conversion (kWh) needs the calorific value from the gas supplier's
  bill. It is a single factor and it belongs in the configuration of the Energy dashboard, not
  in a template.

### Checks

- Reading must be >= the previous reading, and no more than a plausible amount above it for
  the days since the last entry. Otherwise the entry is rejected with a notification, and the
  operator is asked to check the digits.
- A missing reading is not an error. The derived consumption simply spans the gap, and the
  dashboard shows it as one period.

## The hot-water link

The boiler feeds both gas and the hot-water tank, so gas use in winter will include the hot
water. The Tado hot cycle (`docs/hot-water.md`) is one fixed weekly load of gas. Once gas is
tracked, it becomes possible to measure what the weekly cycle costs. Not in scope for the first
pass.

**Stale record.** `docs/hot-water.md` records the hot cycle as Saturday and Sunday 15:00–17:00.
The operator's current Tado schedule is Saturday 17:00–20:00 and Sunday 18:00–21:00 at 65 °C.
The record is out of date and should be updated when the operator next confirms the timetable.

The flush reminder exists already: two automations (`hot_water_flush_pipes_reminder_saturday`
at 20:00 and `hot_water_flush_pipes_reminder_sunday` at 21:00, both on the end of the Tado
window), each guarded so it does not fire while the hot water is off. They were created on
2026-11-08 and have not been fired by hand.

## Open (needs the operator)

1. **Water meter:** make and model, or the printed label. The protocol follows from it, and the
   decoder choice follows from the protocol.
2. **Gas meter:** whether the counter reads m³ or a corrected volume, and how many digits the
   counter has (for the rollover value).
3. **Gas reading frequency:** monthly is the working assumption. Weekly if the supplier allows.
4. **Who enters the gas reading**, and whether a second person should be able to.
5. **The calorific value** from the gas bill, if kWh is wanted on the Energy dashboard.
6. **Where the SDR decoder runs.** A host near the aerial, or the HA box if it has a free USB
   port.

## Not in scope yet

- Per-room or per-fixture water use. The single meter gives the house total only.
- Automatic leak shut-off. Alerting first; shut-off needs a real valve and an agreed rule.
- Using gas use to infer occupancy or boiler faults. Revisit after a season of data.
