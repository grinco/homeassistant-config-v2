"""Evaluate the LIVE climate decision expressions against synthetic inputs.

The one rule this suite exists to enforce:

    THE TEST NEVER CONTAINS THE LOGIC.

Every expression under test is read out of the running configuration at run
time -- `automations.yaml` for the control loop, `.storage/core.config_entries`
for the resolved-temperature template sensors.  A case supplies inputs and an
expected output, never a reimplementation.  If the automation changes, the
suite runs against the new expression and tells you what moved.

That matters here because the whole failure history of this system is fixes
that moved a hazard rather than closing it.  A test suite holding its own copy
of the logic would have agreed with every one of them.
"""

import io
import json
import os
import re
import urllib.error
import urllib.request

AUTOMATIONS = os.environ.get("HA_AUTOMATIONS", "/usr/share/hassio/homeassistant/automations.yaml")
ENTRIES = os.environ.get("HA_ENTRIES", "/usr/share/hassio/homeassistant/.storage/core.config_entries")
AUTOMATION_ID = "1789725511503"          # climate -- maintain per-room targets
PURIFIER_ID = "1789947000001"            # purifier -- run after the cat toilet
HA_URL = os.environ.get("HA_URL", "http://localhost:8123")

SENTINEL = "|CASE|"


class ExtractionError(Exception):
    pass


def load_expressions(automation_id=AUTOMATION_ID):
    """Pull every named `variables:` expression out of a live automation.

    Also collects `value_template` strings from conditions, keyed by the step's
    `alias` where it has one -- a guard expressed as a condition is still a
    decision, and this system's habit is to put the interesting logic there.
    """
    import yaml

    with io.open(AUTOMATIONS, encoding="utf-8") as fh:
        autos = yaml.safe_load(fh)
    match = [a for a in autos if str(a.get("id")) == automation_id]
    if not match:
        raise ExtractionError("automation %s not found in %s" % (automation_id, AUTOMATIONS))

    found = {}

    def walk(node):
        if isinstance(node, dict):
            block = node.get("variables")
            if isinstance(block, dict):
                for name, tpl in block.items():
                    if isinstance(tpl, str):
                        found.setdefault(name, tpl)
            if node.get("alias") and isinstance(node.get("value_template"), str):
                found.setdefault(node["alias"], node["value_template"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(match[0].get("actions") or [])
    walk(match[0].get("conditions") or [])
    return found


def load_sensor_templates():
    """Pull the `state:` template of every Climate template sensor."""
    with io.open(ENTRIES, encoding="utf-8") as fh:
        data = json.load(fh)
    out = {}
    for entry in data["data"]["entries"]:
        if entry.get("domain") != "template":
            continue
        title = entry.get("title") or ""
        if not title.startswith("Climate "):
            continue
        state = (entry.get("options") or {}).get("state")
        if isinstance(state, str):
            out[title] = state
    return out


_QUOTED = re.compile(r"^\s*('[^']*'|\"[^\"]*\")\s*$")
_NUMERIC = re.compile(r"^\s*-?\d+(\.\d+)?\s*$")
_BOOL = re.compile(r"^\s*(true|false)\s*$")


def check_substitution_type(old, new, label):
    """Reject a substitution whose literal does not match the call's return type.

    Substitution is a source-to-source rewrite, so it can change an expression's
    MEANING rather than merely inject a value -- and a type-mismatched literal
    that still evaluates is precisely the case that passes for the wrong reason.

    `states()` returns a STRING.  `states('x') | float(-999)` relies on that: if
    a case substitutes the bare number 23.0 where the live system yields '23.0',
    the case stops exercising the string-coercion path the automation actually
    runs, and an entity reporting 'unavailable' would no longer be represented.
    So a `states()` substitution must be quoted.  `is_state()` returns a bool and
    `now().timestamp()` a float; those are checked the same way.
    """
    new = str(new)
    if old.startswith("states(") and not _QUOTED.match(new) and new.strip() != "none":
        raise ExtractionError(
            "%s: substituting %s with %r -- states() returns a STRING, so the "
            "literal must be quoted (e.g. \"'23.0'\") or the case stops testing "
            "the coercion path the automation really takes" % (label, old, new))
    if old.startswith("is_state(") and not _BOOL.match(new):
        raise ExtractionError(
            "%s: substituting %s with %r -- is_state() returns a BOOLEAN, "
            "use true/false" % (label, old, new))
    if old.endswith("timestamp()") and not _NUMERIC.match(new):
        raise ExtractionError(
            "%s: substituting %s with %r -- a timestamp must be numeric"
            % (label, old, new))


def apply_substitutions(expression, subs, label):
    """Replace impure reads with literals, asserting every rule actually fires.

    Two distinct hazards, both of which would make a case pass for the wrong
    reason, and they need separate guards:

    1. A rule that does not match leaves the expression reading REAL state, so
       the case silently tests the live house instead of its inputs.  Every rule
       must therefore match at least once or the case is an error, not a pass.
    2. A rule that DOES match but injects the wrong type rewrites the meaning of
       the expression rather than supplying a value.  See check_substitution_type.
    """
    for old, new in (subs or {}).items():
        if old not in expression:
            raise ExtractionError(
                "%s: substitution %r never matched -- the expression changed shape, "
                "so this case is no longer testing what it claims" % (label, old)
            )
        check_substitution_type(old, new, label)
        expression = expression.replace(old, str(new))
    return expression


def _literal(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if value is None:
        return "none"
    return json.dumps(str(value))


def render_case(case, expressions, sensors):
    """Build the Jinja fragment that evaluates one case."""
    label = case["name"]
    if "sensor" in case:
        source = sensors
        key = case["sensor"]
        kind = "sensor"
    elif case.get("automation"):
        source = load_expressions(case["automation"])
        key = case["expr"]
        kind = "expression"
    else:
        source = expressions
        key = case["expr"]
        kind = "expression"
    if key not in source:
        raise ExtractionError("%s: %s %r not found in the live config" % (label, kind, key))

    expression = apply_substitutions(source[key], case.get("subs"), label)
    preamble = "".join(
        "{%% set %s = %s %%}" % (name, _literal(value))
        for name, value in sorted((case.get("given") or {}).items())
    )
    return "%s%s{%% set __out %%}%s{%% endset %%}{{ __out | trim }}" % (
        preamble, "", expression,
    )


def build_template(cases, expressions, sensors):
    parts = []
    for case in cases:
        parts.append("%s%s" % (SENTINEL, render_case(case, expressions, sensors)))
    return "".join(parts) + SENTINEL


def _token():
    token = os.environ.get("HA_TOKEN")
    if token:
        return token.strip()
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".ha_token")
    if os.path.exists(path):
        with io.open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    return None


def _mcp_url():
    """The local ha-mcp endpoint, if this machine has one configured.

    Using it as transport means the suite runs with no setup at all: the MCP
    server already holds Home Assistant credentials.  A long-lived token is
    still supported and takes precedence, for CI or another machine.
    """
    if os.environ.get("HA_MCP_URL"):
        return os.environ["HA_MCP_URL"]
    path = os.path.expanduser("~/.claude.json")
    if not os.path.exists(path):
        return None
    try:
        with io.open(path, encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (ValueError, OSError):
        return None
    server = (cfg.get("mcpServers") or {}).get("ha-mcp") or {}
    return server.get("url")


def _evaluate_via_mcp(template, url):
    def rpc(method, params, _id):
        req = urllib.request.Request(
            url,
            data=json.dumps({"jsonrpc": "2.0", "id": _id, "method": method,
                             "params": params}).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Accept": "application/json, text/event-stream"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
        for line in body.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
        return json.loads(body)

    rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                       "clientInfo": {"name": "climate-tests", "version": "1"}}, 1)
    out = rpc("tools/call", {"name": "ha_eval_template",
                             "arguments": {"template": template}}, 2)
    if "error" in out:
        raise RuntimeError("MCP error: %s" % out["error"])
    content = out["result"]["content"][0]["text"]
    try:
        return json.loads(content)["result"]
    except (ValueError, KeyError):
        return content


def evaluate(template):
    """Render a template through Home Assistant. Returns the raw string."""
    token = _token()
    if not token:
        url = _mcp_url()
        if url:
            return _evaluate_via_mcp(template, url)
        raise RuntimeError("NO_TOKEN")
    req = urllib.request.Request(
        HA_URL.rstrip("/") + "/api/template",
        data=json.dumps({"template": template}).encode("utf-8"),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def split_results(rendered, count):
    parts = rendered.split(SENTINEL)
    # leading and trailing empties from the delimiters
    body = parts[1:-1] if len(parts) >= 2 else []
    if len(body) != count:
        raise ExtractionError(
            "expected %d results, parsed %d -- a case probably failed to render"
            % (count, len(body))
        )
    return [p.strip() for p in body]
