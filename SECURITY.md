# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 0.1.x (latest) | yes |
| older | no |

## Reporting a vulnerability

agentseam runs in the path of every tool call an AI coding agent makes, and its
adapters are copied into other projects. A vulnerability here can propagate widely.

- **Preferred:** open a private security advisory:
  <https://github.com/open-coder-ai/agentseam/security/advisories/new>
- Do **not** open a public issue for exploitable findings.
- Include: affected adapter or module, reproduction steps, and impact.

Expect acknowledgment within 7 days and an initial assessment within 14 days.

## The threat model we design against

The adversary is **the agent itself, steered by injected content** — a poisoned web page
or tool result that persuades the agent to weaken its own guardrails. That attacker has
the agent's access, and the agent's access flows through the hooks this library wires.

Findings we treat as high severity:

- **Silent allow.** Any path where a `deny` decision does not reach the agent, or where
  a crash results in the action proceeding without the caller being told. A guard that
  fails open while reporting success is worse than no guard.
- **Claim inflation.** A matrix row asserting an enforcement the vendor does not provide.
  This is a security bug, not a docs bug: downstream tools promise their users based on it.
- **Config tampering via the wired command.** Installation writes into agent config files;
  anything letting untrusted content redirect or widen that write.
- **Payload injection.** Vendor payloads are attacker-influenced data (a tool result can
  contain anything). An adapter that treats payload text as code or shell input is a bug.

An owner-level attacker on the developer's machine is explicitly **out of scope**: they can
uninstall the hooks. We do not claim to defend against that, and we will not accept a
change that implies we do.
