"""Render agentseam's brand assets: the GitHub social preview card and the mark.

Run from this directory:

    pip install cairosvg      # asset tooling only
    python gen_brand_assets.py

Writes social-preview.svg/.png (1280x640, GitHub's social-preview size) and
logo.svg/logo-512.png (512x512) beside this file.

cairosvg is NOT a dependency of agentseam. The package's runtime path is stdlib-only and
`dependencies` in pyproject.toml stays empty; this script is design tooling a maintainer
runs by hand when the artwork changes, and its output is committed.

Every fact on the card is READ FROM THE PACKAGE at render time -- the adapter names, the
event names, the decision outcomes, the version, the supported Python range. A social
preview is a claim surface, and the surest way to keep it honest is to give it no
independent copy of the truth to drift from. The counts printed beside each list are
asserted against the lists themselves, so a card that would lie fails to render.

Two lists are spelled out here because their order is a design choice (events) or because
they exist only as return literals (the enforcement words). Both are checked against the
package rather than trusted: see the assertions beside each.

The mark is a seam: uneven vendor dialect lines converging through stitches into one even
canonical envelope. Its geometry carries two invariants, also asserted rather than
eyeballed -- nothing crosses (agentseam normalizes a dialect's shape, it does not reorder),
and every pair converges (a pair spreading apart would read as fan-out).

Text renders in Geist Mono. Where that font is absent the renderer substitutes another
monospace face; re-render on a machine that has it before committing changed artwork.
"""

import pathlib
import re
import sys

import cairosvg

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

from brandkit import COOL, DIM, FAINT, GOLD, NAVY, PANEL, WHITE, H, S, W, badge, check, column, esc, seam, text

import agentseam  # noqa: E402  (needs the path above)
from agentseam import contract, matrix  # noqa: E402

#: Assets are read and written beside this script, never relative to the working directory.
#: The check job runs from here and the README tells you to run it from the repository root;
#: with bare filenames those two disagree, and the root invocation quietly writes a second
#: copy of the card somewhere nothing reads it.
ASSETS = pathlib.Path(__file__).resolve().parent

# --- facts, read from the package rather than retyped -----------------------------


def python_range():
    """The supported range.

    `requires-python` is the authoritative constraint and is always present, so the floor
    comes from there. The per-version classifiers are the same fact restated for PyPI's
    version filter; when they are present they set the ceiling and are cross-checked against
    the floor, and when they are not the card says "3.9+" rather than inventing a ceiling.
    """
    source = (ASSETS.parent.parent / "pyproject.toml").read_text(encoding="utf-8")
    floor = re.search(r'requires-python\s*=\s*"[><=~^ ]*(3\.\d+)"', source)
    assert floor, "could not read requires-python from pyproject.toml"
    low = floor.group(1)
    versions = sorted(
        re.findall(r'"Programming Language :: Python :: (3\.\d+)"', source),
        key=lambda v: int(v.split(".")[1]),
    )
    if not versions:
        return f"PYTHON {low}+"
    assert versions[0] == low, f"requires-python says {low} but the lowest classifier says {versions[0]}"
    return f"PYTHON {low}–{versions[-1]}"


def decision_outcomes():
    """The constructors on Decision are the decision vocabulary.

    Read off the class, not off a list kept here. An earlier version of this filtered a
    tuple typed into this file, which can only ever find the names already in it: when
    `rewrite` was added the card silently kept saying four. Anything that claims to be
    derived has to be able to discover a name nobody told it about.
    """
    names = [
        n
        for n, v in vars(contract.Decision).items()
        if isinstance(v, classmethod) and n not in contract.Decision.DEPRECATED_ALIASES
    ]
    # Each constructor pairs with a module-level outcome constant of the same name. If that
    # stops holding, a classmethod that is not an outcome has been added and this needs a
    # real discriminator rather than a quiet miscount. `ask`/`rewrite` are excluded above:
    # they are pre-ACS aliases of `escalate`/`transform`, not a distinct outcome constant.
    for name in names:
        assert getattr(contract, name.upper(), None) == name, (
            f"Decision.{name} has no matching outcome constant; the derivation is unsound"
        )
    return names


ADAPTERS = sorted(agentseam.adapted_agents(), key=lambda a: (a != "claude_code", a))
EVENTS = [
    "pre_tool",
    "post_tool",
    "tool_failure",
    "prompt_submit",
    "session_start",
    "session_end",
    "subagent_start",
    "subagent_stop",
    "instructions_loaded",
    "file_changed",
    "pre_compact",
    "stop",
]
assert sorted(EVENTS) == sorted(agentseam.EVENTS), "EVENTS drifted from agentseam.EVENTS"
DECISIONS = decision_outcomes()
# enforcement_level()'s vocabulary -- the honest word a CONSUMER may claim at a surface.
# Deliberately not matrix_terms.TIER_*, which is the coverage vocabulary (what the adapter
# serves). Two different five-word sets; putting one under the other's heading would be a
# quiet false claim, which is the whole thing this project exists not to do.
ENFORCEMENT = ["enforced", "enforceable", "best-effort", "detect", "none"]
# Those words live only as return literals, so they cannot be read off the function the way
# the decision constructors can. What IS checkable: every level the matrix can actually
# produce has to appear on the card. This catches a new level being added; it cannot catch
# one being dropped, since a listed level need not be reachable (no agent fails closed by
# default today, so "enforced" is declared but unreachable).
assert set(matrix.enforcement_level(a, e) for a in agentseam.agents() for e in agentseam.EVENTS) <= set(ENFORCEMENT), (
    "enforcement_level() produces a level the card does not list"
)
N_MATRIX = len(agentseam.agents())
VERSION = agentseam.__version__

# Mark geometry. Irregular gaps, but each must exceed the envelope's own gap.

CARD_ALT = (
    "agentseam — the primitives layer for every coding agent: one handler API over "
    "per-agent hooks, instruction files, plugin packaging, and config. "
    f"{len(ADAPTERS)} adapters ({', '.join(ADAPTERS)}); {len(EVENTS)} normalized events "
    f"({', '.join(EVENTS)}); {len(DECISIONS)} decision outcomes ({', '.join(DECISIONS)}); and the "
    f"{len(ENFORCEMENT)} honest enforcement levels a consumer may claim ({', '.join(ENFORCEMENT)}). "
    f"{N_MATRIX} agents in the capability matrix, {len(ADAPTERS)} adapted, zero dependencies, "
    f"Apache-2.0, version {VERSION}."
)
#: The hero image is the most prominent slot on the page, and its alt text is what a crawler
#: or an LLM retriever reads there. It states what agentseam IS before describing the mark;
#: a label that only describes the drawing spends that slot on nothing.
LOGO_ALT = (
    "agentseam: the primitives layer for every coding agent -- one handler API over "
    "per-agent hooks, instruction files, plugin packaging and config. The mark is a seam: "
    "five unevenly spaced vendor lines converging through stitches into five evenly spaced "
    "parallel lines."
)


def build_card():
    cx = [506, 754, 1002]
    cw, cy, ch = 230, 118, 378
    body = [
        f'<rect width="{W}" height="{H}" fill="{NAVY}"/>',
        badge(64, 58, 38),
        text(90, 64, 19, GOLD, "agentseam", weight=700, tracking=-0.4),
        text(206, 64, 12, FAINT, "open-coder-ai/agentseam"),
        f'<rect x="1042" y="44" width="190" height="27" rx="13" fill="{PANEL}" stroke="{GOLD}" stroke-opacity="0.22"/>',
        f'<circle cx="1062" cy="57.5" r="3.2" fill="{GOLD}"/>',
        text(1074, 62, 11, GOLD, f"v{VERSION} · APACHE-2.0", tracking=0.2),
        f'<line x1="48" y1="92" x2="1232" y2="92" stroke="{GOLD}" stroke-opacity="0.13" stroke-width="1"/>',
        text(48, 140, 10.5, DIM, "— THE PRIMITIVES LAYER", tracking=3.4),
        text(48, 190, 33, WHITE, "One handler API for", weight=700, tracking=-1.2),
        text(48, 230, 33, GOLD, "every coding agent.", weight=700, tracking=-1.2),
        text(48, 276, 13, COOL, "Every agent invented its own hook system —"),
        text(48, 298, 13, COOL, "different events, payloads, ways to say no."),
        text(48, 320, 13, COOL, "agentseam is the layer underneath."),
        text(48, 372, 10.5, DIM, "THE WHOLE API", tracking=3.4),
        f'<rect x="48" y="386" width="410" height="72" rx="9" fill="{PANEL}" stroke="{GOLD}" stroke-opacity="0.16"/>',
        text(66, 412, 12.5, COOL, "from agentseam import run, Decision"),
        text(66, 436, 12.5, GOLD, "run(handler)"),
        text(48, 498, 10.5, DIM, "DEGRADES HONESTLY — CLAIMS NEVER EXCEED THE MATRIX", tracking=1.55),
        column(cx[0], cy, cw, ch, [("ADAPTERS", ADAPTERS)]),
        column(cx[1], cy, cw, ch, [("EVENTS", EVENTS)]),
        column(cx[2], cy, cw, ch, [("DECISIONS", DECISIONS), ("ENFORCEMENT", ENFORCEMENT)]),
        f'<line x1="48" y1="560" x2="1232" y2="560" stroke="{GOLD}" stroke-opacity="0.13" stroke-width="1"/>',
        text(48, 590, 15, GOLD, str(N_MATRIX), weight=700),
        text(72, 590, 10.5, FAINT, "AGENTS IN MATRIX", tracking=1.6),
        text(212, 590, 15, GOLD, str(len(ADAPTERS)), weight=700),
        text(236, 590, 10.5, FAINT, "ADAPTED", tracking=1.6),
        text(320, 590, 15, GOLD, str(len(EVENTS)), weight=700),
        text(344, 590, 10.5, FAINT, "NORMALIZED EVENTS", tracking=1.6),
        text(494, 590, 15, GOLD, "0", weight=700),
        text(512, 590, 10.5, FAINT, "DEPENDENCIES", tracking=1.6),
        text(1232, 590, 10.5, FAINT, f"{python_range()} · STDLIB ONLY · PYPI: agentseam", tracking=1.4, anchor="end"),
    ]
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}"\n'
        f'     role="img" aria-label="{esc(CARD_ALT)}">\n  ' + "\n  ".join(body) + "\n</svg>"
    )


def build_logo():
    mark = seam(96, 416, 252, 168, 344, 126, 386, 5, 5.0, 6.5, 9)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {S} {S}" role="img"\n'
        f'     aria-label="{LOGO_ALT}">\n'
        f'  <rect width="{S}" height="{S}" rx="104" fill="{NAVY}"/>\n  ' + mark + "\n</svg>"
    )


if __name__ == "__main__":
    card, logo = build_card(), build_logo()
    if "--check" in sys.argv:
        problems = check(card, ASSETS / "social-preview") + check(logo, ASSETS / "logo")
        if problems:
            print("\n".join(problems))
            print(
                "\nThe card is derived from the package, so this means the package "
                "changed.\nRegenerate it:  python docs/assets/gen_brand_assets.py"
            )
            raise SystemExit(1)
        print("social-preview.svg and logo.svg are current")
        raise SystemExit(0)
    for name, source in (("social-preview", card), ("logo", logo)):
        (ASSETS / f"{name}.svg").write_text(source, encoding="utf-8")
    cairosvg.svg2png(
        bytestring=card.encode(), write_to=str(ASSETS / "social-preview.png"), output_width=W, output_height=H
    )
    cairosvg.svg2png(bytestring=logo.encode(), write_to=str(ASSETS / "logo-512.png"), output_width=S, output_height=S)
    print(f"rendered: {len(ADAPTERS)} adapters, {len(EVENTS)} events, {N_MATRIX} in matrix, v{VERSION}")
