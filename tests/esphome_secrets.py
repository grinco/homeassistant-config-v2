#!/usr/bin/env python3
"""Does `esphome/secrets.yaml.example` list every `!secret` the device configs use?

The ESPHome configs are the one deployable part of this repo, and they stay
publishable only because every secret is a `!secret` reference. A config that
names a key the example does not list cannot be flashed by anyone restoring from
this repo, and it usually means the key went inline somewhere first.

    python3 tests/esphome_secrets.py
    python3 tests/esphome_secrets.py DIR   # check another directory (mutation)
"""

import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SECRET_RE = re.compile(r"!secret\s+([A-Za-z0-9_]+)")
KEY_RE = re.compile(r"^([A-Za-z0-9_]+):", re.M)


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "esphome")
    with open(os.path.join(root, "secrets.yaml.example"), encoding="utf-8") as fh:
        listed = set(KEY_RE.findall(fh.read()))
    missing = []
    for path in sorted(glob.glob(os.path.join(root, "*.yaml"))):
        with open(path, encoding="utf-8") as fh:
            for key in sorted(set(SECRET_RE.findall(fh.read()))):
                if key not in listed:
                    missing.append((os.path.basename(path), key))
    for name, key in missing:
        print("%s: !secret %s is not in secrets.yaml.example" % (name, key))
    if missing:
        return 1
    print("clean: every !secret is listed in secrets.yaml.example")
    return 0


if __name__ == "__main__":
    sys.exit(main())
