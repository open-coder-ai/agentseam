#!/usr/bin/env python3
"""The recording probe, as source text.

Split out of `capture.py` because writing the program that runs inside somebody else's agent
is a different activity from installing it and reporting on what it caught -- and because
capture.py hit the 300-line review budget, where the remedy is splitting by activity rather
than raising the number.

The probe is emitted as text rather than shipped as a file so it can be dropped anywhere
without an install: it carries its own sys.path setup and imports nothing that is not either
stdlib or vendored beside it.
"""

from __future__ import annotations

import os


def render(here, capture_dir):
    """The recording hook, as source text with this machine's paths baked in.

    Written as a standalone file so no install is needed to run it: the probe carries its
    own sys.path setup and imports nothing that is not stdlib or vendored beside it.
    """
    lines = [
        "#!/usr/bin/env python3",
        "# agentseam capture probe. Records the payload shape, then allows.",
        "# Allowing is not a convenience: a probe that can block turns verification into a",
        "# risk, and nobody runs it twice.",
        "import json, os, sys",
        "",
        "sys.path.insert(0, @HERE@)",
        "sys.path.insert(0, @SRC@)",
        "",
        "try:",
        "    from redact import redact",
        "",
        "    # Bytes first, decoded by us: the platform locale is how Cursor's UTF-8 BOM",
        "    # became cp1252 mojibake on Windows and a whole live run was recorded only as",
        "    # lengths. Witnessed twice now -- once by chock's gate, once by this probe.",
        "    data = sys.stdin.buffer.read()",
        "    text, encoding = None, None",
        "    for candidate in ('utf-8-sig', 'utf-16'):",
        "        try:",
        "            text, encoding = data.decode(candidate), candidate",
        "            break",
        "        except UnicodeError:",
        "            continue",
        "    payload = None",
        "    if text is not None:",
        "        try:",
        "            payload = redact(json.loads(text))",
        "        except ValueError:",
        "            pass",
        "    if payload is None:",
        "        # Shape-only diagnostics: WHY it did not parse, nothing of what it said.",
        "        parts = [ln for ln in (text or '').splitlines() if ln.strip()]",
        "        json_lines = 0",
        "        for ln in parts:",
        "            try:",
        "                json.loads(ln)",
        "                json_lines += 1",
        "            except ValueError:",
        "                pass",
        "        first = next((c for c in (text or '') if not c.isspace()), '')",
        "        payload = {'__unparsed__': {",
        "            'bytes': len(data),",
        "            'encoding': encoding or 'undecodable',",
        "            'bom': ('utf-8' if data[:3] == b'\\xef\\xbb\\xbf'",
        "                    else 'utf-16' if data[:2] in (b'\\xff\\xfe', b'\\xfe\\xff')",
        "                    else 'none'),",
        "            'first_char': (first if first in '{[\"<'",
        "                           else 'letter' if first.isalpha() else 'other'),",
        "            'lines': len(parts),",
        "            'json_lines': json_lines,",
        "        }}",
        "    agent = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('AGENTSEAM_PROBE_AGENT', '?')",
        "    os.makedirs(@CAPTURE_DIR@, exist_ok=True)",
        "    # One file per process, one os.write() per record. Cursor runs subagents in",
        "    # parallel (is_parallel_worker, subagent_id, subagentStart), so several probes",
        "    # append at once; buffered appends to a shared file interleave and tear records",
        "    # in half. Witnessed live: two records split mid-string, and the report died on",
        "    # the first fragment. Per-process files remove the sharing entirely.",
        "    line = json.dumps({'agent': agent, 'payload': payload}, sort_keys=True) + chr(10)",
        "    shard = os.path.join(@CAPTURE_DIR@, 'captured.%d.jsonl' % os.getpid())",
        "    fd = os.open(shard, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)",
        "    try:",
        "        os.write(fd, line.encode('utf-8'))",
        "    finally:",
        "        os.close(fd)",
        "    # Exit 0 is not an answer everywhere. Cursor's permission gates expect",
        "    # {'permission': 'allow'} on stdout; a silent probe there is treated as a",
        "    # refusal and BLOCKS the user's real command -- witnessed live on Windows,",
        "    # where this probe's silence made Cursor reject the very command that was",
        "    # trying to read the capture report. The adapters already speak every",
        "    # dialect, so allow in the agent's own words; raw is re-read because the",
        "    # recorded copy is redacted and parse() wants the true payload.",
        "    if text is not None and '__unparsed__' not in payload:",
        "        from agentseam import Decision, adapters",
        "",
        "        mod = adapters.ADAPTERS.get(agent)",
        "        if mod is not None:",
        "            out, _code = mod.respond(Decision.allow('agentseam capture probe'), mod.parse(json.loads(text)))",
        "            if out:",
        "                sys.stdout.write(out)",
        "                sys.stdout.flush()",
        "except Exception:",
        "    pass  # a probe that can crash the hook is a probe that can break the session",
        "sys.exit(0)  # always allow",
    ]
    src = chr(10).join(lines) + chr(10)
    return (
        src.replace("@HERE@", repr(here))
        .replace("@SRC@", repr(os.path.join(here, "..", "src")))
        .replace("@CAPTURE_DIR@", repr(capture_dir))
    )
