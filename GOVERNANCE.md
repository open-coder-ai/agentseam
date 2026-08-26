# Governance

## Current state

agentseam is maintained by open-coder-ai. Decisions are made by the maintainers in
public via issues and pull requests. This document describes how that works today
rather than an aspirational structure nobody is staffing yet.

## Decision rules

Two classes of change carry standing rules, because they are where this project can
do harm:

1. **Matrix rows** are evidence-bound. Adding or widening a capability claim requires
   a `verified` record naming the agent version, the date, and the method (vendor doc,
   vendor example repo, or captured live run). "It seemed to work" is not a method.
2. **The contract** (`contract.py`, `dispatch.py`) changes by discussion first. Adding
   an agent must never require touching it; if a proposed adapter does, that is evidence
   the abstraction is wrong and the abstraction gets fixed instead.

## Compatibility

Semantic versioning. The canonical event vocabulary, `Decision` semantics, and the
adapter interface are the public API; breaking any of them is a MAJOR bump. Adding an
adapter or an event is MINOR. A matrix correction is PATCH — and is expected to happen
often, because vendors change.

## Relationship to other projects

agentseam is deliberately consumer-agnostic. Guardrail engines, observability sinks,
cost meters, and notifiers are all equal consumers; no consumer's needs get privileged
placement in the core. If a feature only makes sense for one consumer, it belongs in
that consumer.
