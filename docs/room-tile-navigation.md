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

## Magic Areas owns the light groups (revised 2026-09-22)

The first implementation used a script that computed each area's lights at call time. It was
replaced at the operator's direction: **lights are managed by Magic Areas.**

Three group helpers were deleted — *Living Room Lights*, *Office Lights*, *Corridor Lights* —
and Magic Areas' `light_groups` feature was enabled on all twelve areas, which recreates them
as `light.magic_areas_light_groups_<area>_all_lights`. **Gallery was kept**: it unifies two
bulbs in a single physical fixture, so it is a fixture abstraction rather than a room grouping.

**Kitchen needed an exclusion.** With Gallery kept, the kitchen area held the fixture *and*
both of its bulbs, so Magic Areas' room group would have contained all three — the group and
its own members. `exclude_entities: [light.gallery_left, light.gallery_right]` on the kitchen
area leaves the room group as exactly `['light.gallery']`.

That same nesting is why the helpers had to go rather than be left alongside: before deletion,
the living-room group read `['light.the_moon', 'light.h60b0', 'light.living_room_lights']` —
two bulbs and a group containing those same two bulbs. Toggling it would have commanded each
bulb twice.

**Deleting a member needs a config-entry reload, not just a registry delete.** After the
helpers were removed, Magic Areas kept the dead entity in its group membership; the integration
had to be disabled and re-enabled before it rebuilt the list. Reloading the entry alone was not
enough.

**The `light_control` switches Magic Areas also creates are off** — twelve
`switch.magic_areas_light_groups_<area>_light_control` entities that would let the integration
drive lights from area presence. They default to off and were left off: presence is still
triggered by hand until real sensors are fitted, so automatic lighting would fire on a signal
that does not yet mean anything.

## What tapping does now

| rooms | tap | hold |
|---|---|---|
| Living room, Kitchen, Office, Corridor, Kids room 2 — a Magic Areas light group exists | `toggle` that group | open the room |
| the other seven — no lights in the area, so no group | nothing | open the room |

**`tap_action: none`, not a reference to a group that does not exist yet.** Magic Areas only
creates a room's light group once the area actually contains a light, and toggling a
non-existent entity raises a visible error rather than failing quietly — verified. So the
light-less rooms do nothing on tap, which is the same thing they did before, without the error.

When lights are added to one of those areas, Magic Areas creates its group automatically; the
tile then needs its `entity` set and `tap_action` changed to `toggle` — one line per room. That
is the one manual step this design keeps, and it is the price of not shipping a tile that
throws an error every time it is pressed.

### That manual step came due (2026-09-23)

A light was added to **Kids room 2** (`light.bunny`), Magic Areas created
`light.magic_areas_light_groups_kid2_room_all_lights` by itself, and the tile was switched over:
`entity` now names the group, `tap_action` is `toggle`, and `icon_tap_action` opens the room
instead of the AC's more-info dialog. The tile is now identical in behaviour to the four
lower-floor ones.

The secondary line changed with it — it used to count `n/m on` across `area_entities`, which
would have read *2/2* once the area held both the group **and** its member. It now reads the
group's own state and brightness, the same expression the living-room tile uses, and keeps the
AC temperature and mode after it.

`color` needed no change: it already preferred the area's lights over the AC and switched over
on its own the moment lights existed.

## An unresolved report

The operator reported that tapping the Kids room 1 / Kids room 2 tiles opened the **AC
more-info dialog** rather than toggling, while those tiles were configured with
`tap_action: perform-action` calling the script.

That is exactly what a `perform-action` that fails to dispatch would look like: the card falls
back to its default action, `more-info`, on whatever `entity` it carries — an AC in those two
rooms. It fits the evidence, since the four rooms whose `entity` was a light would have opened
a light dialog and been easy to misread as working, and the four rooms with no `entity` at all
would have appeared to do nothing.

It was **not** proven. Mushroom's bundled schema accepts `perform-action` and its runtime
delegates to Home Assistant's own `hass-action` event, so it should work. The rewrite removes
the question rather than answering it: every tap is now either `toggle` or `none`, the two
most basic action types, neither of which involves service dispatch from a card.

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
