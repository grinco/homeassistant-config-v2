#!/usr/bin/env python3
"""Run the metered_step cases against the macro DEPLOYED in Home Assistant.

    python3 tests/energy/run.py

Each case calls the live macro with literal inputs, so this tests what runs, not a
copy. Uses the climate suite's transport. Exit 0 = pass, 1 = failures, 2 = could not run.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "climate"))
sys.path.insert(0, HERE)
import harness  # noqa: E402


def lit(v):
    """A Jinja literal: JSON, except that Jinja spells null `none`."""
    return "none" if v is None else json.dumps(v)
from cases import CASES  # noqa: E402

SEP = "\n@@@\n"
IMPORT = "{% from 'metered_total.jinja' import metered_step %}"


def build(cases):
    parts = []
    for c in cases:
        field = c["field"]
        if field.startswith("last."):
            pick = "r['last'].get(%s)" % json.dumps(field[5:])
        else:
            pick = "r[%s]" % json.dumps(field)
        parts.append("{%% set r = metered_step(%s, %s, %s, %s) | from_json %%}{{ %s }}"
                     % (lit(c["total"]), lit(c["last"]), lit(c["entity"]), lit(c["value"]), pick))
    return IMPORT + SEP.join(parts)


def results(tpl):
    got = harness.evaluate(tpl)
    if isinstance(got, dict):
        got = got.get("result", json.dumps(got))
    return got


def main():
    try:
        got = results(build(CASES))
    except RuntimeError as exc:
        print("SUITE ERROR: %s" % exc, file=sys.stderr)
        return 2
    res = [x.strip() for x in str(got).split("@@@")]
    if len(res) != len(CASES):
        print("SUITE ERROR: the template did not render: %s" % str(got)[:400], file=sys.stderr)
        return 2
    fails = 0
    w = max(len(c["name"]) for c in CASES)
    for c, r in zip(CASES, res):
        ok = r == str(c["expect"])
        fails += not ok
        print("  %s  %-*s  %s" % ("PASS" if ok else "FAIL", w, c["name"],
                                  "" if ok else "expected %r, got %r  [%s]"
                                  % (str(c["expect"]), r, c.get("finding", ""))))
    print("\n%d/%d passed" % (len(CASES) - fails, len(CASES)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
