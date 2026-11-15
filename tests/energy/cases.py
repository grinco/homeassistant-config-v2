"""Cases for the `metered_step` macro (custom_templates/metered_total.jinja).

The house has no mains meter. `sensor.metered_grid_import` stands in for one: the
sum of what every metered device used, fed to the Energy dashboard as its grid
import. Summing the meters' raw readings is not safe -- one plug resetting to 0
takes ~1000 kWh off a ~14 000 kWh sum, which the recorder books as a huge negative
day (or, past a 10 % drop, as a meter reset that re-counts the whole sum). So the
sensor adds each meter's *increase* since its last reading instead.

Each case gives the previous total, the per-meter last readings, one meter's new
reading, and names the output field ("total", or "last.<meter>") and its value.
"""

L = {"sensor.a": 100.0, "sensor.b": 50.0}

CASES = [
    dict(name="an increase is added", total=10, last=L, entity="sensor.a", value="100.5",
         field="total", expect="10.5", finding="baseline"),
    dict(name="the new reading is remembered", total=10, last=L, entity="sensor.a",
         value="100.5", field="last.sensor.a", expect="100.5", finding="baseline"),
    dict(name="other meters are kept", total=10, last=L, entity="sensor.a", value="100.5",
         field="last.sensor.b", expect="50.0", finding="baseline"),
    dict(name="a meter seen for the first time adds nothing", total=10, last=L,
         entity="sensor.c", value="900", field="total", expect="10.0",
         finding="a new meter's lifetime reading is not this period's use"),
    dict(name="a meter seen for the first time is remembered", total=10, last=L,
         entity="sensor.c", value="900", field="last.sensor.c", expect="900.0",
         finding="seed, then count from the next reading"),
    dict(name="the first ever reading starts from 0", total="unknown", last=None,
         entity="sensor.a", value="100", field="total", expect="0.0",
         finding="a new sensor's state is 'unknown'"),
    dict(name="last may arrive as JSON text", total=10, last='{"sensor.a": 100.0}',
         entity="sensor.a", value="101", field="total", expect="11.0",
         finding="restored attribute could be text"),
    dict(name="unavailable adds nothing", total=10, last=L, entity="sensor.a",
         value="unavailable", field="total", expect="10.0", finding="offline meter"),
    dict(name="unavailable keeps the last reading", total=10, last=L, entity="sensor.a",
         value="unavailable", field="last.sensor.a", expect="100.0",
         finding="the gap is counted when it returns"),
    dict(name="the use over a gap is counted on return", total=10,
         last={"sensor.a": 100.0}, entity="sensor.a", value="103", field="total",
         expect="13.0", finding="offline meter"),
    dict(name="a reset counts the reading since the reset", total=10, last=L,
         entity="sensor.a", value="0.4", field="total", expect="10.4",
         finding="plug counter reset to 0 must not subtract its lifetime"),
    dict(name="a reset re-seeds the meter", total=10, last=L, entity="sensor.a",
         value="0.4", field="last.sensor.a", expect="0.4", finding="plug counter reset"),
    dict(name="a dip adds nothing", total=10, last=L, entity="sensor.a", value="60",
         field="total", expect="10.0",
         finding="a group meter dips when a member drops out; not a reset"),
    dict(name="a dip keeps the higher reading", total=10, last=L, entity="sensor.a",
         value="60", field="last.sensor.a", expect="100.0",
         finding="recovery from a dip must not be counted twice"),
    dict(name="recovery from a dip counts only the excess", total=10, last=L,
         entity="sensor.a", value="100.2", field="total", expect="10.2",
         finding="paired with 'a dip keeps the higher reading'"),
    dict(name="just under a tenth is a reset", total=10, last=L, entity="sensor.a",
         value="9.9", field="total", expect="19.9", finding="reset threshold, crossing"),
    dict(name="just over a tenth is a dip", total=10, last=L, entity="sensor.a",
         value="10.1", field="total", expect="10.0", finding="reset threshold, crossing"),
    dict(name="a negative reading is ignored", total=10, last=L, entity="sensor.a",
         value="-5", field="total", expect="10.0", finding="garbage reading"),
]
