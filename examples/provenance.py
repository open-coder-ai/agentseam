"""What a generated page says its claims rest on.

Split from the page renderer because stating the evidence behind a claim is a different
activity from laying out the claim -- and because generate.py crossed the 300-line review
budget, where the remedy is splitting by activity rather than raising the number.

BASIS_CAVEAT is deliberately a plain dict lookup with no default: adding a basis to the
matrix vocabulary without writing the sentence that explains it to a reader raises KeyError
here and fails the build, rather than quietly emitting a page with the caveat missing.
"""

from __future__ import annotations

from agentseam.matrix import MATRIX, basis

BASIS_CAVEAT = {
    "live-run": "observed against a running agent",
    "live-run-partial": "observed against a running agent, but not at every event this row "
    "claims -- see the matrix `observed` list for which ones were",
    "vendor-source": "read from the vendor's own source code",
    "vendor-docs": "read from the vendor's documentation -- a claim about what the vendor "
    "says, not an observation of what their build does",
    "third-party-install": "read from a working installation somebody else published, not from the vendor",
    "inherited": "carried over unverified -- a lead, not a fact",
}


def _provenance(agent):
    row = MATRIX[agent]
    return (
        "> **How this was established.** %s: %s. Checked %s.\n>\n"
        "> Vendors change their hook surfaces without telling us. Confirm against your own\n"
        "> installation before relying on any of it, and open an issue if a page is wrong --\n"
        "> a claim that has quietly stopped being true is the failure mode this project\n"
        "> cares most about.\n" % (basis(agent), BASIS_CAVEAT[basis(agent)], row["verified"]["date"])
    )
