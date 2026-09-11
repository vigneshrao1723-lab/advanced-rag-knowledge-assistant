# Project Brief

**Status:** PROPOSED — describes intent for a system that does not yet exist.

## Problem

Knowledge workers accumulate large amounts of private, unstructured
documents (PDFs, reports, notes) and have no fast, trustworthy way to ask
questions against that corpus and get answers they can verify. Generic
chatbots either lack access to private knowledge or answer fluently without
grounding — producing plausible-sounding but unverifiable or wrong answers.

## Goal

Build a multi-user platform where a user (or a team, isolated by workspace)
can upload private documents, ask questions in natural language (text or
voice), and receive answers that are **grounded in retrieved evidence with
inspectable citations** — plus the tooling to measure and improve retrieval
and generation quality over time.

## Non-goals (for the initial implementation)

- Not a general-purpose chatbot — answers should be grounded in the user's
  own corpus, not open-domain knowledge.
- Not a distributed/microservices system — see
  [`docs/DECISIONS/0001-modular-monolith-over-microservices.md`](DECISIONS/0001-modular-monolith-over-microservices.md).
  Multi-database, message-queue, and Kubernetes architectures are explicitly
  out of scope unless a documented requirement later justifies them.
- Not a voice-first product — voice is an interaction mode added to chat
  after the text pipeline is solid, not a parallel product surface.
- Not attempting to support every document format on day one — target
  formats are PDF, DOCX, TXT, Markdown, CSV (see
  [`docs/REQUIREMENTS.md`](REQUIREMENTS.md)).

## Target users

- Individuals or small teams who need to query a private document corpus
  (internal docs, research papers, reports, meeting notes) and get
  trustworthy, source-linked answers.
- Users who need to *inspect* how an answer was produced (which chunks were
  retrieved, how they were ranked, which model generated the answer) rather
  than trust a black box.

## Success criteria (for the initial build)

Success for the first working version means, concretely:

1. A user can register, log in, and operate inside an isolated workspace.
2. A user can upload a PDF/DOCX/TXT/MD/CSV document and see it move through
   the ingestion pipeline to a `READY` state (see
   [`docs/RAG_DESIGN.md`](RAG_DESIGN.md)).
3. A user can ask a question in chat and receive an answer with citations
   that link back to the specific source document/section/page.
4. Retrieval quality is measurable — not just "it works," but reported via
   the metrics in [`docs/EVALUATION.md`](EVALUATION.md), computed against
   real evaluation runs, never fabricated numbers.
5. Cross-workspace data isolation is verified by tests, not just assumed
   (see [`docs/SECURITY.md`](SECURITY.md)).

None of the above is implemented yet — this brief defines what "done" means
when it is. Current status is tracked in
[`PROJECT_STATE.md`](../PROJECT_STATE.md).

## Relationship to other docs

- **What** to build in detail: [`docs/REQUIREMENTS.md`](REQUIREMENTS.md)
- **How** it's structured: [`docs/ARCHITECTURE.md`](ARCHITECTURE.md)
- **How the RAG pipeline works**: [`docs/RAG_DESIGN.md`](RAG_DESIGN.md)
- **How we know it's good**: [`docs/EVALUATION.md`](EVALUATION.md)
