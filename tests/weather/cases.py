"""Cases for the `weather_ahead` macro (custom_templates/weather_ahead.jinja).

The macro reduces an hourly forecast to what the Home tower picture shows: the
worst condition in the next few hours, the scene image for it, day or night,
and the numbers that decide what to wear. Each case gives a forecast and a
"now", and names one output field and its expected value.

Forecast rows carry only the keys a case needs; times are UTC, as the weather
integration returns them.
"""

NOW = "2026-11-12T10:30:00+00:00"


def row(hour, condition, **kw):
    d = {"datetime": "2026-11-12T%02d:00:00+00:00" % hour, "condition": condition,
         "temperature": kw.pop("t", 8), "apparent_temperature": kw.pop("feels", 6),
         "precipitation": kw.pop("mm", 0), "precipitation_probability": kw.pop("pp", 10),
         "wind_speed": kw.pop("wind", 5), "is_daytime": kw.pop("day", True)}
    d.update(kw)
    return d


CLOUDY_DAY = [row(h, "cloudy") for h in range(10, 16)]


def with_(base, hour, condition, **kw):
    return [row(hour, condition, **kw) if r["datetime"][11:13] == "%02d" % hour else r
            for r in base]


CASES = [
    dict(name="all cloudy -> cloudy", forecast=CLOUDY_DAY, field="condition", expect="cloudy",
         finding="baseline"),
    # Window: the hour in progress (10:00) through 13:00, the last hour that starts
    # before now + 3 h. 14:00 starts after 13:30 and is out.
    dict(name="rain in the last hour of the window counts", field="condition", expect="rainy",
         forecast=with_(CLOUDY_DAY, 13, "rainy"),
         finding="window edge: an hour starting before now+3h is in"),
    dict(name="rain just past the window does not count", field="condition", expect="cloudy",
         forecast=with_(CLOUDY_DAY, 14, "rainy"),
         finding="window edge: an hour starting after now+3h is out"),
    dict(name="the hour in progress counts", field="condition", expect="rainy",
         forecast=with_(CLOUDY_DAY, 10, "rainy"),
         finding="window start: 10:00 has not ended at 10:30"),
    dict(name="an hour that has ended does not count", field="condition", expect="cloudy",
         forecast=[row(9, "pouring")] + CLOUDY_DAY,
         finding="window start: 09:00 ended at 10:00"),
    # Ranking: what changes what you wear outranks what does not.
    dict(name="snow outranks rain", field="condition", expect="snowy",
         forecast=with_(with_(CLOUDY_DAY, 11, "rainy"), 12, "snowy"), finding="ranking"),
    dict(name="storm outranks pouring", field="condition", expect="lightning-rainy",
         forecast=with_(with_(CLOUDY_DAY, 11, "pouring"), 12, "lightning-rainy"), finding="ranking"),
    dict(name="windy outranks cloudy", field="condition", expect="windy",
         forecast=with_(CLOUDY_DAY, 12, "windy"), finding="ranking"),
    dict(name="partly cloudy outranks sunny", field="condition", expect="partlycloudy",
         forecast=[row(h, "sunny") for h in (10, 11)] + [row(12, "partlycloudy")], finding="ranking"),
    dict(name="tie (clear-night then sunny) -> the earlier hour", field="condition",
         expect="clear-night",
         forecast=[row(10, "clear-night", day=False), row(11, "sunny"), row(12, "sunny")],
         finding="mutate.py: ties went to the later hour unseen"),
    dict(name="rain outranks fog", field="condition", expect="rainy",
         forecast=with_(with_(CLOUDY_DAY, 11, "fog"), 12, "rainy"), finding="ranking"),
    # Scene: every HA condition maps onto one of the ten rendered scenes.
    dict(name="snowy-rainy -> sleet", field="scene", expect="sleet",
         forecast=with_(CLOUDY_DAY, 11, "snowy-rainy"), finding="scene map"),
    dict(name="hail -> pouring", field="scene", expect="pouring",
         forecast=with_(CLOUDY_DAY, 11, "hail"), finding="scene map"),
    dict(name="lightning -> storm", field="scene", expect="storm",
         forecast=with_(CLOUDY_DAY, 11, "lightning"), finding="scene map"),
    dict(name="clear-night -> sunny scene", field="scene", expect="sunny",
         forecast=[row(h, "clear-night", day=False) for h in range(10, 14)], finding="scene map"),
    dict(name="windy-variant -> windy", field="scene", expect="windy",
         forecast=with_(CLOUDY_DAY, 11, "windy-variant"), finding="scene map"),
    dict(name="exceptional -> cloudy scene", field="scene", expect="cloudy",
         forecast=[row(h, "exceptional") for h in range(10, 14)], finding="scene map"),
    # Dressing numbers over the window only (14:00 is outside and must not leak in).
    dict(name="feels-like minimum over the window", field="feels_min", expect="1",
         forecast=[row(10, "cloudy", feels=5), row(11, "cloudy", feels=3),
                   row(12, "cloudy", feels=1), row(13, "cloudy", feels=2),
                   row(14, "cloudy", feels=-4)],
         finding="window bounds the minimum"),
    dict(name="temperature range over the window", field="temp_range", expect="4..9",
         forecast=[row(10, "cloudy", t=4), row(11, "cloudy", t=9), row(12, "cloudy", t=6),
                   row(13, "cloudy", t=5), row(14, "cloudy", t=15)],
         finding="window bounds the range"),
    dict(name="precipitation summed over the window", field="precip", expect="1.3",
         forecast=[row(10, "rainy", mm=0.4), row(11, "rainy", mm=0.9), row(12, "cloudy"),
                   row(13, "cloudy"), row(14, "pouring", mm=6)],
         finding="window bounds the sum"),
    dict(name="highest rain probability over the window", field="precip_prob", expect="60",
         forecast=[row(10, "cloudy", pp=10), row(13, "rainy", pp=60), row(14, "rainy", pp=90)],
         finding="window bounds the maximum"),
    dict(name="strongest wind over the window", field="wind_max", expect="30",
         forecast=[row(10, "cloudy", wind=10), row(12, "windy", wind=30), row(13, "cloudy", wind=20),
                   row(14, "windy", wind=60)],
         finding="review 2026-11-11: wind_max had no case"),
    # No forecast at all (integration down): nothing to show.
    dict(name="empty forecast -> no condition", field="condition", expect="None",
         forecast=[], finding="availability"),
]
