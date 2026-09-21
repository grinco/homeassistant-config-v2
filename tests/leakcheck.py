#!/usr/bin/env python3
"""Does any committed file, or any unpushed commit message, contain a scrubbed name?

This repository is public and the live instance names two bedrooms after the
operator's children. Exports are anonymised; this is the check that the
anonymisation actually worked.

**The terms are not in this file, and must never be.** An earlier version of the
repo README documented the substitution table and republished, in full, exactly
what the scrubbing existed to remove. The terms are read from
`tests/climate/rooms.local.json`, which is gitignored.

    python3 tests/leakcheck.py            # working tree (tracked files only)
    python3 tests/leakcheck.py --commits  # also every unpushed commit + message

Why a plain word-boundary regex is NOT enough, and what bit on 2026-09-21:
`\\b` does not fire between `_` and a letter, because `_` is a word character. So
`\\bsaz\\b` silently fails to match `..._NAME_room_area_state` -- and a dashboard
export carrying a Magic Areas presence entity went into a commit looking clean.
The lookarounds below exclude only letters and digits, so `_` counts as a
boundary, which is what entity ids need.
"""

import io
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MAP = os.path.join(HERE, "climate", "rooms.local.json")


def terms():
    try:
        with io.open(MAP, encoding="utf-8") as fh:
            data = json.load(fh)
    except IOError:
        print("cannot read %s -- it is gitignored and holds the terms to scan for.\n"
              "See tests/climate/README.md." % MAP, file=sys.stderr)
        raise SystemExit(2)
    found = list(data.get("scrub_tokens") or [])
    if not found:
        print("no 'scrub_tokens' in the local map -- nothing to scan for, which is "
              "not the same as nothing to find", file=sys.stderr)
        raise SystemExit(2)
    return found


def pattern(found):
    # `_` is deliberately NOT treated as part of a word here; see the module docstring.
    alts = "|".join(re.escape(t) for t in sorted(found, key=len, reverse=True))
    return re.compile(r"(?<![A-Za-z0-9])(%s)(?![A-Za-z0-9])" % alts)


def git(*args):
    """Run git and decode leniently.

    Not `text=True`: the repo holds binary blobs (button icons), and a scanner
    that raises UnicodeDecodeError on the first PNG is a scanner that stops
    scanning halfway and reports nothing. Undecodable bytes cannot spell a name,
    so dropping them is safe; abandoning the scan is not.
    """
    raw = subprocess.check_output(["git"] + list(args), stderr=subprocess.DEVNULL)
    return raw.decode("utf-8", "ignore")


def scan_tree(pat):
    hits = []
    for path in [p for p in git("ls-files", "-z").split("\0") if p]:
        if os.path.abspath(path) == os.path.abspath(__file__):
            continue
        try:
            body = io.open(path, encoding="utf-8", errors="ignore").read()
        except (IOError, IsADirectoryError):
            continue
        for m in pat.finditer(body):
            hits.append((path, body[:m.start()].count("\n") + 1, m.group(0)))
    return hits


def scan_commits(pat):
    hits = []
    try:
        revs = git("rev-list", "origin/master..HEAD").split()
    except subprocess.CalledProcessError:
        print("no origin/master to compare against; skipping the commit scan")
        return hits
    for rev in revs:
        for path in [p for p in git("ls-tree", "-r", "--name-only", "-z", rev).split("\0") if p]:
            try:
                blob = git("show", "%s:%s" % (rev, path))
            except subprocess.CalledProcessError:
                continue
            m = pat.search(blob)
            if m:
                hits.append(("%s:%s" % (rev[:8], path), 0, m.group(0)))
        m = pat.search(git("log", "-1", "--format=%B", rev))
        if m:
            hits.append(("%s (COMMIT MESSAGE)" % rev[:8], 0, m.group(0)))
    print("scanned %d unpushed commit(s)" % len(revs))
    return hits


def main(argv):
    pat = pattern(terms())
    hits = scan_tree(pat)
    if "--commits" in argv:
        hits += scan_commits(pat)
    if hits:
        # The matched term is NOT printed: this output can end up in a log or a
        # paste. The location is enough to find it.
        print("\n%d LEAK(S) -- a scrubbed name is present:\n" % len(hits))
        for path, line, _term in hits:
            print("  %s%s" % (path, (":%d" % line) if line else ""))
        print("\nNothing is pushed yet if these are all in unpushed commits: fix the "
              "export, amend or rebase, and re-run. If any of this is already on the "
              "remote it needs a history rewrite and a force push, not a follow-up "
              "commit.")
        return 1
    print("clean: no scrubbed name in any tracked file%s"
          % (" or unpushed commit" if "--commits" in argv else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
