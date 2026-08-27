# Verifying an adapter against a real agent

Eleven of the twelve adapters here were built from vendor documentation or source and have
never had a real payload put through them. The matrix says so — `agentseam matrix --json` reports a `basis`
per agent, and only Claude Code's is `live-run`. Docs go stale and field names get misread,
and nothing in this repository would notice.

This turns an hour at a real machine into evidence.

## What you run

```bash
python3 tools/capture.py detect                    # which agents look installed here
python3 tools/capture.py install --agent cursor    # wire a recording probe
```

Then **use that agent normally for a minute.** Anything is useful; the more of its lifecycle
you touch, the more we learn:

- start a session, ask it something
- have it read a file
- have it run a shell command
- have it write or edit a file
- let it finish, then end the session

```bash
python3 tools/capture.py report                    # the findings
python3 tools/capture.py uninstall --agent cursor  # remove the probe
```

Paste the report back. Repeat for whichever other agents you have.

## Why it is safe to run

- **The probe always allows.** It records, answers "allow" in the agent's own dialect,
  and exits 0. It cannot block a tool call, so it cannot interfere with real work.
  Verification that costs you a broken session is not worth running, and would not get run
  twice. (The in-dialect answer is not optional: Cursor's permission gates treat a silent
  hook as a refusal and reject the command -- witnessed live before this was fixed.)
- **Nothing sensitive is written down.** Payloads are reduced to shape *before* anything
  touches disk: keys and types are kept, values are replaced with markers like `<str:41>`.
  A short allowlist of protocol enums survives (`hook_event_name`, `tool_name`) because
  those are the whole point. Prompts, file contents, paths, session ids and emails do not.
  `tests/test_capture_kit.py` asserts the strong version of this — no input string may
  appear in the output — and runs the real probe to prove it rather than reading its source.
- **Uninstall is surgical.** The probe is installed under its own ownership marker, so
  removing it leaves any hooks you already had untouched.
- The capture file is `.capture/captured.jsonl`, gitignored, and already safe to share.

## What the report tells us

- **events we do not know about** — a vendor event with no mapping here. The most valuable
  line in the report: it is a capability we are not offering because we did not know it
  existed.
- **claimed by our adapter: n/m** — payloads our detection failed to recognise. Anything
  below 100% is a live bug: an unidentified payload is allowed through.
- **parse failures** — the adapter crashed on a real payload.
- **key paths observed** — the true shape, to diff against what the adapter reads. A field
  we read that is not in this list is a field we are getting as `None` in production.
- **mapped but not observed** — usually just a hook that did not fire in your session.
  Only interesting if you know you triggered it.

## If nothing is captured

That is a finding, not a failure. It means the hook never fired, which points at the config
path or format being wrong for your version — exactly the kind of thing documentation does
not tell you. Report it with the agent's version.
