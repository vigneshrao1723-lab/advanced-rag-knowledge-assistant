# Skills

This directory is the future home of reusable, documented procedures
("skills") that agents working on this repository can follow for recurring
kinds of work. As of this writing it contains **only this roster and
process document** — no individual skill procedures have been written yet.
Elaborate skill implementations are deliberately deferred until there's
real implementation work for them to support; see `AGENTS.md` §5 for the
project's anti-fabrication and documentation-accuracy rules, which apply
here too.

## Memory-type distinction

This project distinguishes several kinds of persistent knowledge — don't
conflate them:

| Type | What it is | Where it lives |
|---|---|---|
| **RULE** | A persistent constraint | `AGENTS.md`, `docs/SECURITY.md` |
| **SKILL** | A reusable procedure | `.agents/skills/` (this directory) |
| **MCP** | An external tool/data integration | Tool-specific configuration (none configured yet) |
| **MEMORY** | Persistent project state/knowledge | `PROJECT_STATE.md`, this repository generally |
| **ADR** | An architecture decision record | `docs/DECISIONS/` |
| **HANDOFF** | Immediate continuation state | `HANDOFF.md` |
| **SOLVING** | Historical hard-won technical knowledge | `SOLVING.md` |

A skill is a **procedure** ("how to do X reliably"), not a decision (that's
an ADR), not a status snapshot (that's `PROJECT_STATE.md`/`HANDOFF.md`), and
not a standing constraint (that's a rule in `AGENTS.md`).

## Potential skills (roster — not yet implemented)

These are candidate skills identified during project planning. Each would,
when written, live at `.agents/skills/<name>/` with a procedure document.
None exist yet:

- `architecture-review` — reviewing a proposed change against
  `docs/ARCHITECTURE.md` and the modular-monolith/no-premature-infra rules.
- `requirements-analysis` — turning a vague request into a scoped
  requirement consistent with `docs/REQUIREMENTS.md`.
- `code-review` — general code review procedure aligned with `AGENTS.md`
  coding standards.
- `security-audit` — walking a change against `docs/SECURITY.md`'s
  checklist.
- `threat-modeling` — identifying trust-boundary risks for a new feature
  (especially anything touching retrieval of untrusted content or
  workspace isolation).
- `debugging` — a structured approach to hard bugs, feeding into
  `SOLVING.md`.
- `test-engineering` — deciding what layer(s) of test a change needs, per
  `AGENTS.md` §3.
- `performance-review` — sanity-checking latency/throughput for
  pipeline-stage changes.
- `deployment` — the local Docker/Compose and (later) CI/CD procedure.
- `solving-log` — how to write a good `SOLVING.md` entry.
- `rag-pipeline-review` — reviewing changes to the retrieval/generation
  pipeline against `docs/RAG_DESIGN.md`.
- `retrieval-evaluation` — running and interpreting the retrieval metrics
  in `docs/EVALUATION.md`.
- `chunking-review` — comparing chunking strategy changes.
- `embedding-evaluation` — assessing embedding model/version changes.
- `hallucination-evaluation` — assessing faithfulness/citation-correctness
  regressions.

## Adding a skill

When a skill is actually needed (i.e., the procedure has been done at least
once and is worth making repeatable), add `.agents/skills/<name>/SKILL.md`
describing the procedure, and update the roster above to mark it as written
rather than potential. Keep skills scoped to *procedures*; if what's being
captured is actually a constraint or a decision, it belongs in `AGENTS.md`
or `docs/DECISIONS/` instead.
