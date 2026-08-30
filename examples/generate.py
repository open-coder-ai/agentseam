#!/usr/bin/env python3
"""Generate `examples/generated/` -- one page per agent, one section per hook it supports.

Nothing here is written by hand. Every config fragment and every response comes out of the
real code paths, so the pages cannot describe behaviour the library does not have.
`tests/test_examples.py` regenerates them and fails if the committed files differ, which
turns the examples into a claim CI checks rather than documentation that rots.

What the pages cannot do is verify the vendors. Most rows rest on vendor documentation --
a claim about what a vendor says, not an observation of what their build does -- so every
page states its basis and tells the reader to confirm against their own installation.

    python3 examples/generate.py [--check]
"""

from __future__ import annotations

import difflib
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from scenarios import SCENARIOS  # noqa: E402

import agentseam as A  # noqa: E402
from agentseam import Decision, adapters, packaging, permissions  # noqa: E402
from agentseam.matrix import basis  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "generated")

DECISIONS = [
    ("allow", lambda: Decision.allow(), "the handler is happy"),
    ("deny", lambda: Decision.deny("secret detected in file content"), "the handler refuses"),
    ("ask", lambda: Decision.ask("looks like a credential -- confirm?"), "the handler wants a human"),
    (
        "rewrite",
        lambda: Decision.rewrite({"content": "AWS_SECRET_ACCESS_KEY=<redacted>"}, "redacting the secret"),
        "the handler wants the input changed",
    ),
    # The loud one, and the reason it belongs on these pages: on all but the two vendors in
    # allow_semantics.VOUCH_SPEAKS it reduces to a plain `allow`, and a reader needs to see
    # which side of that line their agent falls on before writing a handler that vouches.
    ("vouch", lambda: Decision.vouch("signed by a trusted key"), "the handler actively approves"),
]
# These pages are where a reader learns what a handler may return, so a missing outcome is a
# missing part of the API. Checked rather than trusted: `rewrite` was added to the vocabulary
# and this list did not notice, and neither did anything else.
assert [name for name, _make, _why in DECISIONS] == [
    n for n, v in vars(Decision).items() if isinstance(v, classmethod)
], "examples/generate.py does not show every Decision outcome"

#: What each basis means for someone deciding how far to trust a page.


from provenance import BASIS_CAVEAT, _provenance  # noqa: E402,F401


def _fence(text, lang=""):
    return "```%s\n%s\n```" % (lang, text.rstrip("\n"))


def _json(obj):
    return json.dumps(obj, indent=2, sort_keys=True)


def _decision_rows(agent, raw):
    rows = []
    for name, make, why in DECISIONS:
        text, code, _event, final = A.handle(raw, lambda _e, _m=make: _m(), agent=agent)
        note = "" if final.outcome == name else "reduced to `%s`: this agent cannot %s" % (final.outcome, name)
        rows.append((name, why, text, code, note))
    return rows


def _also_claimed_by(agent, raw):
    """Other adapters that claim this payload, which is why `detect()` would refuse it."""
    return [n for n, m in sorted(adapters.ADAPTERS.items()) if n != agent and m.claims(raw)]


def _normalized(event):
    fields = (
        ("event", event.event),
        ("tool", event.tool),
        ("path", event.path),
        ("command", event.command),
        ("content", (event.content or "")[:48] or None),
        ("output", (event.output or "")[:48] or None),
    )
    return "\n".join("%-8s = %s" % (k, v) for k, v in fields if v is not None)


def _body(text, empty):
    if not text:
        return "_%s_" % empty
    return _fence(text, "json" if text.lstrip().startswith("{") else "")


def _hook_section(agent, event_name, raw, mod, index):
    out = []
    add = out.append
    add("### %d. `%s` — called `%s` here\n" % (index, event_name, mod.REVERSE_EVENT_MAP[event_name]))
    add("Enforcement: **%s**.\n" % A.enforcement_level(agent, event_name))

    others = _also_claimed_by(agent, raw)
    if others:
        add(
            "> Also claimed by **%s**, so `detect()` declines this payload and the agent has\n"
            '> to be named: `handle(raw, handler, agent="%s")`. Guessing between adapters\n'
            "> that answer differently is worse than declining.\n" % (", ".join(others), agent)
        )

    add("The agent sends:\n")
    add(_fence(_json(raw), "json"))
    add("\nwhich normalizes to:\n")
    add(_fence(_normalized(mod.parse(raw))))

    if event_name == A.PRE_TOOL:
        add("\nThis is the gate, so every decision is worth seeing.\n")
        for name, why, text, code, note in _decision_rows(agent, raw):
            add("**`Decision.%s()`** — %s\n" % (name, why))
            if note:
                add("> %s\n" % note)
            add(_body(text, "No output; the exit code carries the answer."))
            add("\nExit code: `%d`\n" % code)
    else:
        text, code, _e, _d = A.handle(raw, lambda _e: Decision.deny("policy violation"), agent=agent)
        add("\nA `Decision.deny()` here produces:\n")
        add(_body(text, "Nothing. This event is observation only, so a decision is not read."))
        add("\nExit code: `%d`\n" % code)
    return "\n".join(out)


def _page(agent):
    row = A.MATRIX[agent]
    mod = adapters.get(agent)
    scenarios = SCENARIOS[agent]
    out = []
    add = out.append

    add("# %s\n" % row["display"])
    add("> Generated by `examples/generate.py`. Do not edit by hand.\n")
    add(_provenance(agent))
    add(
        "\nOne section per hook this agent is claimed to support, in lifecycle order. Every\n"
        "block is produced by running agentseam, so it is what this agent actually gets.\n"
    )

    add("## What agentseam claims\n")
    add("| | |")
    add("|---|---|")
    add("| tier | `%s` |" % row["tier"])
    add("| enforcement at `pre_tool` | **%s** |" % A.enforcement_level(agent, A.PRE_TOOL))
    add(
        "| can block / rewrite | %s / %s |"
        % (
            "yes" if A.can_block(agent, A.PRE_TOOL) else "no",
            "yes" if A.can_rewrite(agent, A.PRE_TOOL) else "no",
        )
    )
    add("| hooks covered | %d |" % len(scenarios))
    add("| hook config | `%s` |" % row["config"])
    add("| evidence | `%s` — %s |" % (basis(agent), row["verified"]["method"]))
    add("")
    add("%s\n" % row["notes"])

    add("## What `agentseam install` writes\n")
    add("One handler wired for every hook this agent supports.\n")
    add("`%s`\n" % mod.CONFIG_PATH)
    config = mod.hook_config(list(scenarios), "python3 guard.py")
    if getattr(mod, "CONFIG_FORMAT", "json") == "toml":
        add(_fence(mod.render_config(config), "toml"))
    else:
        add(_fence(_json(config), "json"))

    add("\n## Every hook, one at a time\n")
    add(
        "The story is held constant across agents so the pages compare: the same credential\n"
        "heading for a memory file, the same failing test, the same prompt.\n"
    )
    for i, (event_name, raw) in enumerate(scenarios.items(), 1):
        add(_hook_section(agent, event_name, raw, mod, i))
    return "\n".join(out)


def _primitive_section(agent):
    out = ["## Other primitives\n"]
    try:
        plan = permissions.plan(agent, [permissions.Rule("deny", "shell", "curl *")])
        out.append("**Permissions** — `deny shell curl *` rendered into `%s`:\n" % plan.path)
        body = plan.fragment
        out.append(_fence(body if isinstance(body, str) else _json(body), "" if isinstance(body, str) else "json"))
        for gap in plan.unrepresentable:
            out.append("\n> Not representable here: %s\n" % gap.reason)
    except KeyError:
        out.append("**Permissions** — no model recorded: %s\n" % permissions.UNRECORDED[agent])

    try:
        bundle = packaging.Bundle("secrets-guard", description="Keeps secrets out of memory files")
        bundle.parts.append(packaging.Part(packaging.SKILL, "secret-scan", "# Secret scan\n"))
        laid = packaging.plan(agent, bundle)
        out.append("\n**Packaging** — a one-skill bundle, rooted at `%s`:\n" % laid.root)
        out.append(_fence("\n".join(sorted(laid.files))))
    except KeyError:
        out.append("\n**Packaging** — no format recorded: %s\n" % packaging.UNRECORDED[agent])
    return "\n".join(out)


def _index():
    out = ["# Generated vendor examples\n"]
    out.append("> Generated by `examples/generate.py`. Do not edit by hand.\n")
    out.append(
        "One page per agent agentseam can hook, with a section for **every hook that agent\n"
        "supports** -- the payload it sends, the normalized event a handler sees, and what\n"
        "comes back. The story is held constant across agents so the pages compare.\n"
    )
    out.append(
        "\n**These pages describe what vendors document, not what their builds were observed\n"
        "to do.** The `evidence` column says which for each agent. Only one row here rests on\n"
        "a live run; most are read from vendor documentation, and vendors change hook surfaces\n"
        "without notice. Verify against your own installation before relying on any of it.\n"
    )
    out.append("\n| agent | hooks | enforcement | block | rewrite | evidence | config |")
    out.append("|---|---|---|---|---|---|---|")
    for agent in sorted(SCENARIOS):
        row = A.MATRIX[agent]
        out.append(
            "| [%s](%s.md) | %d | %s | %s | %s | `%s` | `%s` |"
            % (
                row["display"],
                agent,
                len(SCENARIOS[agent]),
                A.enforcement_level(agent, A.PRE_TOOL),
                "yes" if A.can_block(agent, A.PRE_TOOL) else "no",
                "yes" if A.can_rewrite(agent, A.PRE_TOOL) else "no",
                basis(agent),
                row["config"],
            )
        )
    out.append(
        "\nAgents with no page are not omissions. Aider and Zed expose no hook surface at all,\n"
        "and Junie, Replit and Tabnine have no adapter here yet -- `agentseam agents` lists\n"
        "every one of them with the reason.\n"
    )
    return "\n".join(out)


def build():
    files = {"README.md": _index() + "\n"}
    for agent in sorted(SCENARIOS):
        files["%s.md" % agent] = _page(agent) + "\n" + _primitive_section(agent) + "\n"
    return files


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    files = build()
    if "--check" in argv:
        drift = []
        for name, body in sorted(files.items()):
            path = os.path.join(OUT, name)
            current = open(path).read() if os.path.exists(path) else None
            if current != body:
                drift.append(name)
                sys.stderr.writelines(
                    difflib.unified_diff(
                        (current or "").splitlines(keepends=True),
                        body.splitlines(keepends=True),
                        fromfile="committed/%s" % name,
                        tofile="generated/%s" % name,
                    )
                )
        if drift:
            sys.stderr.write(
                "\nexamples are stale: %s\n"
                "run `python3 examples/generate.py` and commit the result, or enable the\n"
                "hook that does it for you: `git config core.hooksPath .githooks`\n" % ", ".join(drift)
            )
            return 1
        print("examples up to date (%d files)" % len(files))
        return 0
    os.makedirs(OUT, exist_ok=True)
    for name, body in sorted(files.items()):
        with open(os.path.join(OUT, name), "w") as fh:
            fh.write(body)
    print("wrote %d files to %s" % (len(files), OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
