# Gas and water tracking: design

*2026-11-08. Decisions from the operator are recorded; the water protocol is confirmed at capture.*

## Goal

Track gas and water consumption in Home Assistant over time, so the Energy dashboard shows
them beside electricity and so a sudden change in use is visible (a leak, a stuck tap, a
boiler that runs too often). Two sources with different characters:

- **Water:** a Qundis smart meter that emits readings over radio (868 MHz). Automatic and
  frequent. Received with an RTL-SDR dongle (planned, not yet bought).
- **Gas:** read by hand from the meter once a week. The reading is only as good as the person
  who types it in, and that person sometimes forgets, so missing readings are expected.

Both end in the same shape: a cumulative total that only goes up, plus a per-day, weekly or
monthly consumption derived from it. The Energy dashboard and the statistics recorder need
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
- **Keep the raw reading.** Whatever decodes the radio packets keeps the meter's own counter.
  Any later correction (a changed decoder, a meter swap) is applied to the derivation, never to
  the stored total.

## Water (Qundis radio meter)

### Capture

The meter is a Qundis unit transmitting on 868 MHz. Qundis products use the wireless M-Bus
(wM-Bus, EN 13757-4) radio standard, which is the usual target for `wmbusmeters` on an RTL-SDR.
That is the working assumption; it is confirmed by the first capture, not assumed in the
configuration. Plan:

1. Listen on 868 MHz with the RTL-SDR and log raw frames for a day, to confirm the protocol,
   the meter's ID and the reporting interval.
2. Decode with `wmbusmeters` (or `rtl_wmbus` for raw frames). If the frames do not decode as
   wM-Bus, fall back to a manual decode against the vendor's documentation.
3. Compare one decoded total with the meter's own display at the same time. This confirms the
   unit (m³ or litres) before anything is wired into Home Assistant.
4. Only then wire it into Home Assistant (below).

### Into Home Assistant

- Run the decoder as a small service on a host near the SDR, publishing each decoded reading to
  the existing Mosquitto broker over MQTT. Home Assistant already has the MQTT integration.
- One sensor for the total in m³: `device_class: water`, `state_class: total_increasing`,
  unit `m³`. `total_increasing` lets the recorder compute consumption across gaps, provided the
  value never decreases. If the meter can reset, that is handled in the decoder, not here.
- `utility_meter` for daily and monthly water consumption from that total.
- Freshness: a binary sensor flags when no reading has arrived for 6 hours. A stalled SDR must
  not look like a dry house.

### Checks

- Reading must be >= the previous reading. A decrease is logged and rejected, not recorded.
  The check runs in the decoder before the MQTT publish, so a rejected packet never reaches the
  sensor. The decoder keeps the last accepted value and drops anything below it.
- A flow-rate sanity limit: a reading jump above the largest plausible burst in one interval
  (set after the capture, from the real numbers) is flagged rather than recorded.

## Gas (manual weekly reading)

### Meter

The gas counter shows **m³ with 5 digits before the decimal point and 3 after**: the range is
0.000 to 99999.999 m³. It wraps to 00000.000 at 100000 m³, so the rollover value is **100000 m³**.
The resolution is 0.001 m³, which is more precise than the input the operator types.

### Entry

A helper for the reading, entered from the phone:

- `input_number` for the reading in m³, step 0.001, min 0, max 99999.999. A new helper starts at
  its min, so the first entry must be seeded deliberately, not read as zero.
- `input_datetime` for when the reading was taken, defaulting to now. The operator enters the
  reading and the time it was read, not the time it was typed.

**Rollover.** When the counter wraps (99999.999 to 00000.xxx), the operator enters the wrapped
value as read. A second helper, `input_number.gas_rollover_offset` (m³, step 100000), holds the
total volume the counter has wrapped so far. The total sensor is the entered reading plus that
offset. When the entered reading is lower than the last accepted one by more than half the
counter's range (50000 m³), validation treats it as a wrap: it adds 100000 m³ to the offset and
records the entry. The operator confirms a wrap before the offset moves.

### Reminder

- **Weekly**, a notification to Vadim only (the phone target, not the household). The day and
  time are chosen to be the least intrusive that still gets a reading in within the week.
- **Missed readings:** if no reading has been accepted for 9 days, the reminder repeats daily
  until one is entered. A missed week is then a single gap, not a silent one.

### Derivation

- A sensor that takes the entered reading plus offset as its total: `device_class: gas`,
  `state_class: total_increasing`, unit `m³`.
- `utility_meter` for weekly and monthly consumption from it.
- The gas volume to energy conversion requires the calorific value (kWh per m³) from the gas
  supplier's bill. That value is configured in the Energy dashboard, not hardcoded in a template.

### Checks

- Reading must be >= the previous accepted reading (after the rollover offset is applied), and
  no more than a configured maximum daily increase multiplied by the days since the last entry.
- Validation is an automation on the `input_number` change. If the entry fails, the automation
  sets the helper back to the last accepted value, so the helper never keeps a rejected reading,
  and sends a notification asking the operator to check the digits. The sensor is updated only
  on the accepted path.
- A missing reading is not an error. The derived consumption simply spans the gap, and the
  dashboard shows it as one period.

## Notifications

All reminders and alerts from this design go to Vadim's phone only. The household is not
notified about meter readings or missed entries.

## The hot-water link

The boiler feeds both gas and the hot-water tank, so gas use in winter includes the hot water.
The Tado hot cycle (`docs/hot-water.md`) runs a fixed weekly heating schedule. Once gas is
tracked, it becomes possible to measure what the weekly cycle costs. Not in scope for the first
pass.

**Stale record.** `docs/hot-water.md` records the hot cycle as Saturday and Sunday 15:00–17:00.
The operator's current Tado schedule is Saturday 17:00–20:00 and Sunday 18:00–21:00 at 65 °C.
The record is out of date and should be updated when the operator next confirms the timetable.

The flush reminder exists already: two automations (`hot_water_flush_pipes_reminder_saturday`
at 20:00 and `hot_water_flush_pipes_reminder_sunday` at 21:00, both on the end of the Tado
window), each guarded so it does not fire while the hot water is off. They were created on
2026-11-08 and have not been fired by hand.

## Open

1. **Water protocol:** confirmed at the first capture (wM-Bus is the working assumption).
2. **Where the SDR decoder runs:** a host near the aerial, or the HA box if it has a free USB
   port. Not yet decided.
3. **The calorific value** from the gas bill, if kWh is wanted on the Energy dashboard.
4. **Gas maximum daily increase:** the limit used by the plausibility check, to be set from the
   first few real readings.

## Not in scope yet

- Per-room or per-fixture water use. The single meter gives the house total only.
- Automatic leak shut-off. Alerting first; shut-off needs a real valve and an agreed rule.
- Using gas use to infer occupancy or boiler faults. Revisit after a season of data.
