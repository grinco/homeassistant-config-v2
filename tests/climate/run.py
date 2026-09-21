#!/usr/bin/env python3
"""Run the climate decision suite against the LIVE expressions.

    python3 tests/climate/run.py              # needs a token (see README)
    python3 tests/climate/run.py --emit F     # write the template for manual eval
    python3 tests/climate/run.py --verify F   # score a rendered result

Exit code 0 = all pass, 1 = failures, 2 = the suite could not run.
"""

import io
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])

import harness  # noqa: E402
from cases import CASES  # noqa: E402


def build():
    expressions = harness.load_expressions()
    sensors = harness.load_sensor_templates()
    return harness.build_template(CASES, expressions, sensors)


def score(results):
    failures = []
    for case, got in zip(CASES, results):
        want = str(case["expect"])
        if got != want:
            failures.append((case, want, got))
    width = max(len(c["name"]) for c in CASES)
    for case, got in zip(CASES, results):
        ok = got == str(case["expect"])
        print("  %s  %-*s  %s" % ("PASS" if ok else "FAIL", width, case["name"],
                                  "" if ok else "expected %r, got %r" % (str(case["expect"]), got)))
    print("\n%d/%d passed" % (len(CASES) - len(failures), len(CASES)))
    if failures:
        print("\nFAILURES -- each names the finding it locks down:\n")
        for case, want, got in failures:
            print("  %s" % case["name"])
            print("      expected %r, got %r" % (want, got))
            if case.get("finding"):
                print("      guards: %s" % case["finding"])
            print("")
    return 1 if failures else 0


def main(argv):
    if "--emit" in argv:
        path = argv[argv.index("--emit") + 1]
        with io.open(path, "w", encoding="utf-8") as fh:
            fh.write(build())
        print("wrote %s (%d cases)" % (path, len(CASES)))
        return 0
    if "--verify" in argv:
        path = argv[argv.index("--verify") + 1]
        with io.open(path, encoding="utf-8") as fh:
            return score(harness.split_results(fh.read(), len(CASES)))
    try:
        expressions = harness.load_expressions()
        sensors = harness.load_sensor_templates()
        results = harness.evaluate_cases(CASES, expressions, sensors)
    except RuntimeError as exc:
        if str(exc) == "NO_TOKEN":
            print("No Home Assistant token.\n"
                  "  Create one: HA profile -> Security -> Long-lived access tokens\n"
                  "  Then:       echo '<token>' > tests/climate/.ha_token   (gitignored)\n"
                  "  Or:         export HA_TOKEN=<token>\n\n"
                  "Without a token, use --emit / --verify (see README).", file=sys.stderr)
            return 2
        raise
    except harness.ExtractionError as exc:
        print("SUITE ERROR: %s" % exc, file=sys.stderr)
        return 2
    return score(results)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
