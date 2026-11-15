#!/usr/bin/env python3
"""Confirm the metered_step cases detect bugs.

Reads the DEPLOYED macro, applies one plausible bug at a time, inlines the mutated
macro in place of the import, and requires at least one case to fail.
"""
import io, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run  # noqa: E402
from run import CASES  # noqa: E402

LIVE = os.environ.get("HA_CONFIG", "/usr/share/hassio/homeassistant") + "/custom_templates/metered_total.jinja"

MUTATIONS = [
    ("raw sum: a dip subtracts", "{%- elif v < prev * 0.1 -%}", "{%- elif true -%}{%- set ns.add = v - prev -%}{%- set ns.keep = v -%}{%- elif false -%}"),
    ("first reading counted", "{%- set ns.keep = v -%}\n  {%- elif v >= prev", "{%- set ns.keep = v -%}{%- set ns.add = v -%}\n  {%- elif v >= prev"),
    ("reset threshold a half", "v < prev * 0.1", "v < prev * 0.5"),
    ("reset threshold inclusive", "v < prev * 0.1", "v <= prev * 0.1 + 0.2"),
    ("a dip lowers the remembered reading", "{%- endif -%}\n{%- endif -%}", "{%- else -%}{%- set ns.keep = v -%}{%- endif -%}\n{%- endif -%}"),
    ("unavailable stored as the reading",
     "{%- if ns.keep is not none -%}{%- set out = dict(out, **{entity: ns.keep}) -%}{%- endif -%}",
     "{%- if v is none -%}{%- set out = dict(out, **{entity: v}) -%}{%- else -%}{%- set out = dict(out, **{entity: ns.keep}) -%}{%- endif -%}"),
    ("negative readings accepted", "{%- set v = none if v is not none and v < 0 else v -%}", ""),
    ("text attribute not parsed", "{%- set last = last | from_json -%}", ""),
    ("other meters dropped", "{%- set out = dict(last) -%}", "{%- set out = {} -%}"),
]


def main():
    src = io.open(LIVE, encoding="utf-8").read()
    body = src[src.index("{%- macro"):]
    base = run.build(CASES)
    survived = 0
    for label, old, new in MUTATIONS:
        if body.count(old) != 1:
            print("  STALE    %s  (pattern not found once in the live macro)" % label)
            survived += 1
            continue
        tpl = base.replace(run.IMPORT, body.replace(old, new), 1)
        res = [x.strip() for x in str(run.results(tpl)).split("@@@")]
        killed = len(res) != len(CASES) or any(r != str(c["expect"]) for c, r in zip(CASES, res))
        survived += not killed
        print("  %s  %s" % ("KILLED  " if killed else "SURVIVED", label))
    print("\n%d/%d mutations killed" % (len(MUTATIONS) - survived, len(MUTATIONS)))
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
