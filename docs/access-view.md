# Admin → Access: who is signed in, from where

Since 2026-10-28 this page runs on **Access Guard** (`grinco/ha-access-guard`, installed through
HACS — never copied in by hand). Its design, security model and tests live in that repository;
this note records only how the house uses it.

| Part | Source |
|---|---|
| *Connected now* | `sensor.access_guard_sessions`, logins used in the last 35 minutes; icon by origin, amber when from the internet |
| *Logins* | the same sensor's `sessions`; **tap a login to sign it out** (`access_guard.sign_out`, with a confirmation). Sessions, never accounts: the person signs in again |
| *Recent activity* | `sensor.access_guard_activity`, the last 25 actions a person ran |
| new-login push | `automation.house_new_home_assistant_login`, on the `access_guard_new_login` event, to both adults |

Options: the country file is `/config/tools/geo/dbip-country-lite.csv.gz` (DB-IP Lite, offline;
attribution on the page) and the home public address comes from `sensor.home_door_wan_ip`.

It replaced a stopgap from the same morning — a `command_line` sensor parsing `.storage/auth` and
a template activity sensor — removed from `configuration.yaml` (backup
`configuration.yaml.bak.20261028-accessguard`).
