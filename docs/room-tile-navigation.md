# Room tiles: one gesture model for every room

*2026-09-21.*

## The complaint

> "on lower floor you need to hold to open, in upper floor just click"

Both were true. The Home view's room tiles had grown three different interaction models
depending on what each room happened to contain:

| rooms | tap | hold |
|---|---|---|
| Living room, Kitchen, Office, Corridor — *had a light* | toggle that light | open the room |
| Bedroom, Kids room 1, Kids room 2 — *had an AC* | open the room | more-info on the AC |
| Laundry, Shower, Hallway, Bathroom, Closet — *had neither* | open the room | — |

Nothing was wrong with any one tile. The inconsistency was emergent: each tile was built
around whatever entity the room had, so the gesture depended on the hardware rather than on
what the tile *is*.

## The model

Every room tile, all twelve, identical:

- **tap** — toggle every light in that room
- **hold** — open that room's view

`double_tap` (more-info, on four tiles) is gone. Two gestures, no exceptions, nothing that
exists only in some rooms.

**A room with no lights does nothing on tap.** That is the consistent answer rather than a
special case, and it starts working by itself the moment a light is added to the area.

## Why a script and not `target: {area_id: …}`

The obvious implementation — `light.toggle` aimed at the area — is wrong here, and quietly so.

Several rooms hold a light **group** alongside that group's own members in the same area:
`light.gallery` *is* the two gallery bulbs; `light.living_room_lights` *is* `h60b0` and
`the_moon`. A service call targeting the area resolves to the group **and** each member, so
every bulb gets toggled twice — once directly, once through the group — and lands back where
it started.

`script.toggle_area_lights` takes an `area_id` and builds its own list:

```jinja
{{ expand(area_entities(area_id)) | selectattr('domain','eq','light')
   | rejectattr('state','in',['unavailable','unknown']) | map(attribute='entity_id') | list }}
```

`expand()` flattens a group into its members, so each bulb appears exactly once.

**Any-on means all-off.** Toggling each light individually would turn a room with one lamp lit
into a room with the other two lit. A room switch is expected to mean "everything off" when
anything is on.

## Why this replaced the Magic Areas light groups that were asked for

The request was for empty Magic Areas light groups, so that lights added later would be picked
up automatically. The automatic part is the point, and it is satisfied — **`area_entities()`
resolves at call time**, so a light added to an area is picked up by the script with no edit
here and none to the dashboard.

Magic Areas was not used for it because the feature is not enabled on any of the twelve areas
(`features: {}` on every config entry) and the integration exposes **no reconfigure flow**, so
turning it on means twelve manual passes through its options UI. That buys a group entity per
room — which would be useful — but it is not what makes future lights work, and the tiles work
today without it. If those group entities are wanted later for their own sake, nothing here
conflicts with adding them.

**Presence sensors needed nothing.** All twelve areas already have
`binary_sensor.magic_areas_presence_tracking_<area>_area_state`, live and reporting; the
kitchen was reading `occupied`/`extended` at the time of writing. The dummies that were asked
for already exist.

## What the tile shows

The icon colour now follows the **room's lights** wherever the room has any — amber when
anything is lit, grey otherwise — so the tile reflects what tapping it will do. Where a room
has no lights, the previous colour logic still applies (green for occupancy, blue/red for the
shower leak sensor), and it switches to the light colour by itself once lights exist.

Each room's own detail is kept: AC temperature and mode in the bedrooms, leak and battery in
the shower, occupancy where there is nothing else to say.

## Not covered by any test

`tests/climate/` is an expression oracle for the climate loop; it has nothing to say about
dashboards or scripts. What was verified instead:

- every tile's `color` and `secondary` template rendered against live state, all twelve
- the script's entity list and `any_on` decision computed for all twelve areas before running it
- one real actuation — living room on, then off, confirmed back to its starting state

The group/member double-toggle is the failure this design avoids; it was confirmed by reading
`light.living_room_lights`, whose `entity_id` attribute lists `the_moon` and `h60b0`.
