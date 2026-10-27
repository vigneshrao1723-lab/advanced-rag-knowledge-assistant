"""Larger deterministic retrieval-evaluation fixture (pre-release audit).

`retrieval_fixture.py`'s six documents are each one chunk long, so every
chunking strategy produces the identical chunks there and the comparison
cannot distinguish them (see docs/EVALUATION.md). This fixture exists to
make the strategies *able* to differ:

- **Long, multi-section documents** that split into several chunks.
- **Near-duplicate distractor documents** (the "Aldrin" runbook vs the
  "Borealis" runbook, the X100 vs X200 manuals) that share headings and
  vocabulary but give different facts.
- **Boundary-spanning evidence**: for the three `boundary` queries the
  answer is one ~260-character sentence positioned so that it straddles
  the first window edge of `FixedSizeChunker` (window 1000, overlap 100
  -> the second window starts at 900, so a sentence that starts before
  900 and ends after 1000 is wholly contained in neither window). A
  strategy that cuts mid-sentence cannot put that sentence in any single
  chunk. `backend/tests/test_eval_large_fixture.py` verifies this
  property holds, so the fixture cannot silently stop testing it.
- **Multi-fact queries** whose answer needs two different chunks.
- **Unanswerable queries** with no supporting evidence anywhere.

Relevance is judged by `evidence_phrases`: verbatim strings that must
appear inside a retrieved chunk (`evidence_coverage_at_k`), so the same
judgments score every chunking strategy without hand-labelling each
strategy's chunks. All text is synthetic and deterministic (no
randomness); the facts are fictional.

Like the small fixture, query wording shares literal keywords with its
evidence: `LocalHashingEmbeddingProvider` has no semantic understanding,
so results describe this pipeline's current local providers only -- not a
real embedding model or LLM.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LargeDocument:
    key: str
    filename: str
    # (heading, body text) pairs; each pair becomes one ExtractedSection.
    sections: tuple[tuple[str | None, str], ...]


@dataclass(frozen=True)
class LargeQuery:
    query: str
    category: str  # direct | distractor | multi_fact | boundary | unanswerable
    # Verbatim phrases that must each appear in some retrieved chunk.
    # Empty only for `unanswerable` queries.
    evidence_phrases: tuple[str, ...]


# Generic, topic-parameterised filler. Deliberately free of numbers and of
# any fact a query asks about; each sentence is ~95-105 characters so the
# offsets that the boundary sections rely on are predictable.
_FILLER: tuple[str, ...] = (
    "Teams are expected to keep records of {topic} decisions so that reviewers can follow them later.",
    "Questions about {topic} that are not covered in this section should be raised with the team lead.",
    "This section is reviewed every quarter and updated whenever the {topic} process changes in practice.",
    "Colleagues joining midway through a cycle should read the {topic} summary before taking any part.",
    "Exceptions to the standard {topic} process are rare and must always be documented in the team log.",
    "A short checklist for {topic} is kept in the shared drive alongside the usual template documents.",
    "Feedback on how {topic} works in practice is collected during the regular retrospective meetings.",
    "Older versions of the {topic} guidance remain available in the archive for audit purposes only.",
)


def _filler(topic: str, sentences: int, start: int = 0) -> str:
    return " ".join(_FILLER[(start + i) % len(_FILLER)].format(topic=topic) for i in range(sentences))


def _body(topic: str, facts: tuple[str, ...], lead: int = 3, trail: int = 3) -> str:
    """Filler, then the fact sentences, then more filler -- so the evidence
    sits mid-section rather than at its edges."""
    return " ".join([_filler(topic, lead), *facts, _filler(topic, trail, start=lead)])


def _boundary_body(topic: str, key_sentence: str) -> str:
    """Eight filler sentences (~800 characters) then the ~260-character key
    sentence, so the key sentence starts before offset 900 and ends after
    offset 1000 -- the region `FixedSizeChunker` cuts through."""
    return " ".join([_filler(topic, 8), key_sentence, _filler(topic, 5, start=1)])


# --- Boundary-spanning key sentences (each ~260 characters) ------------------

RETENTION_SENTENCE = (
    "The Calloway data retention schedule requires that customer support transcripts are kept for "
    "exactly eighteen months, after which the compliance office must confirm deletion in writing "
    "and the storage team must purge every backup copy within a further thirty days."
)
PROCUREMENT_SENTENCE = (
    "Any Hartwell procurement above forty thousand dollars must be supported by three competitive "
    "quotations, reviewed by the sourcing committee, and countersigned by the chief financial "
    "officer before a purchase order is issued to the selected supplier."
)
TRAVEL_SENTENCE = (
    "Overseas travel under the Lindqvist policy must be booked at least twenty one days in advance "
    "through the approved agency, and the traveller must file a written itinerary with the safety "
    "desk before departure so that emergency contacts can be verified."
)

DOCUMENTS: tuple[LargeDocument, ...] = (
    LargeDocument(
        key="hr_handbook",
        filename="hr_handbook.txt",
        sections=(
            (
                "Annual Leave",
                _body(
                    "leave",
                    (
                        "Every full-time employee receives twenty four days of annual leave per calendar year.",
                        "Unused leave of up to five days may be carried into the following year.",
                    ),
                ),
            ),
            (
                "Remote Work",
                _body(
                    "remote work",
                    (
                        "Remote work beyond two days a week requires written approval from the regional director.",
                    ),
                ),
            ),
            (
                "Expenses",
                _body(
                    "expense",
                    (
                        "Meal expenses during business travel are reimbursed up to seventy five dollars per day.",
                    ),
                ),
            ),
            ("Conduct", _body("conduct", ("Harassment of any kind is grounds for immediate disciplinary review.",))),
        ),
    ),
    LargeDocument(
        key="it_security",
        filename="it_security_policy.txt",
        sections=(
            (
                "Passwords",
                _body(
                    "password",
                    ("Credentials for production systems must be rotated every ninety days.",),
                ),
            ),
            (
                "Devices",
                _body(
                    "device",
                    ("Lost or stolen laptops must be reported to the service desk within four hours.",),
                ),
            ),
            ("Backups", _body("backup", ("Nightly backups are verified by restoring a random sample each week.",))),
        ),
    ),
    LargeDocument(
        key="borealis_runbook",
        filename="borealis_runbook.txt",
        sections=(
            (
                "Deployments",
                _body(
                    "deployment",
                    ("Borealis production deployments run every Tuesday at 02:00 UTC.",),
                ),
            ),
            (
                "Rollback",
                _body(
                    "rollback",
                    (
                        "A Borealis rollback needs approval from the release captain and completes in under fifteen minutes.",
                    ),
                ),
            ),
            (
                "Monitoring",
                _body(
                    "monitoring",
                    (
                        "Borealis latency alerts page the on-call engineer when the p95 exceeds eight hundred milliseconds.",
                    ),
                ),
            ),
        ),
    ),
    # Distractor: same headings and vocabulary as the Borealis runbook.
    LargeDocument(
        key="aldrin_runbook",
        filename="aldrin_runbook.txt",
        sections=(
            (
                "Deployments",
                _body(
                    "deployment",
                    ("Aldrin production deployments run every Thursday at 22:00 UTC.",),
                ),
            ),
            (
                "Rollback",
                _body(
                    "rollback",
                    (
                        "An Aldrin rollback needs approval from the platform manager and takes about two hours.",
                    ),
                ),
            ),
            (
                "Monitoring",
                _body(
                    "monitoring",
                    (
                        "Aldrin latency alerts page the on-call engineer when the p95 exceeds three seconds.",
                    ),
                ),
            ),
        ),
    ),
    LargeDocument(
        key="x200_manual",
        filename="x200_manual.txt",
        sections=(
            (
                "Specifications",
                _body("specification", ("The X200 battery lasts thirty six hours on a single charge.",)),
            ),
            (
                "Charging",
                _body(
                    "charging",
                    ("The X200 charges fully in ninety minutes using the supplied USB-C adapter.",),
                ),
            ),
            (
                "Warranty",
                _body("warranty", ("The X200 is covered by a three year limited warranty.",)),
            ),
        ),
    ),
    # Distractor: same headings and vocabulary as the X200 manual.
    LargeDocument(
        key="x100_manual",
        filename="x100_manual.txt",
        sections=(
            (
                "Specifications",
                _body("specification", ("The X100 battery lasts twelve hours on a single charge.",)),
            ),
            (
                "Charging",
                _body(
                    "charging",
                    ("The X100 charges fully in four hours using the supplied micro USB cable.",),
                ),
            ),
            (
                "Warranty",
                _body("warranty", ("The X100 is covered by a one year limited warranty.",)),
            ),
        ),
    ),
    LargeDocument(
        key="finance_faq",
        filename="finance_faq.txt",
        sections=(
            (
                "Reimbursements",
                _body(
                    "reimbursement",
                    ("Approved expense claims are paid within ten working days of submission.",),
                ),
            ),
            (
                "Invoices",
                _body(
                    "invoice",
                    ("Supplier invoices above five thousand dollars need two signatures.",),
                ),
            ),
        ),
    ),
    # Boundary-spanning evidence (see module docstring).
    LargeDocument(
        key="compliance_policies",
        filename="compliance_policies.txt",
        sections=(
            ("Data Retention", _boundary_body("retention", RETENTION_SENTENCE)),
            ("Procurement", _boundary_body("procurement", PROCUREMENT_SENTENCE)),
            ("Travel", _boundary_body("travel", TRAVEL_SENTENCE)),
        ),
    ),
)

QUERIES: tuple[LargeQuery, ...] = (
    # direct
    LargeQuery(
        "How many days of annual leave does a full-time employee receive?",
        "direct",
        ("twenty four days of annual leave",),
    ),
    LargeQuery(
        "How often must production credentials be rotated?",
        "direct",
        ("rotated every ninety days",),
    ),
    LargeQuery(
        "How quickly are approved expense claims paid after submission?",
        "direct",
        ("paid within ten working days of submission",),
    ),
    LargeQuery(
        "What is the daily meal allowance for business travel?",
        "direct",
        ("reimbursed up to seventy five dollars per day",),
    ),
    LargeQuery(
        "Within how many hours must a lost laptop be reported to the service desk?",
        "direct",
        ("reported to the service desk within four hours",),
    ),
    LargeQuery(
        "How many signatures do large supplier invoices need?",
        "direct",
        ("need two signatures",),
    ),
    # distractor-sensitive: a near-duplicate document gives a different answer
    LargeQuery(
        "How long does the X200 battery last on a single charge?",
        "distractor",
        ("The X200 battery lasts thirty six hours",),
    ),
    LargeQuery(
        "How long is the X100 limited warranty?",
        "distractor",
        ("The X100 is covered by a one year limited warranty",),
    ),
    LargeQuery(
        "When do Borealis production deployments run?",
        "distractor",
        ("Borealis production deployments run every Tuesday at 02:00 UTC",),
    ),
    LargeQuery(
        "Who approves an Aldrin rollback?",
        "distractor",
        ("An Aldrin rollback needs approval from the platform manager",),
    ),
    # multi-fact: the answer needs two different chunks
    LargeQuery(
        "What is the annual leave allowance and who must approve extended remote work?",
        "multi_fact",
        ("twenty four days of annual leave", "written approval from the regional director"),
    ),
    LargeQuery(
        "When do Borealis deployments run and who approves a Borealis rollback?",
        "multi_fact",
        (
            "Borealis production deployments run every Tuesday at 02:00 UTC",
            "A Borealis rollback needs approval from the release captain",
        ),
    ),
    LargeQuery(
        "How long does the X200 battery last and how long is the X200 warranty?",
        "multi_fact",
        ("The X200 battery lasts thirty six hours", "three year limited warranty"),
    ),
    # boundary-spanning: the whole sentence must sit inside one chunk
    LargeQuery(
        "How long are customer support transcripts kept under the Calloway data retention schedule?",
        "boundary",
        (RETENTION_SENTENCE,),
    ),
    LargeQuery(
        "What approvals does a Hartwell procurement above forty thousand dollars need?",
        "boundary",
        (PROCUREMENT_SENTENCE,),
    ),
    LargeQuery(
        "How far in advance must overseas travel be booked under the Lindqvist policy?",
        "boundary",
        (TRAVEL_SENTENCE,),
    ),
    # unanswerable: nothing in the corpus supports an answer
    LargeQuery("What is the capital of Atlantis?", "unanswerable", ()),
    LargeQuery("Who won the 1987 chess championship in Reykjavik?", "unanswerable", ()),
    LargeQuery("What is the airspeed velocity of an unladen swallow?", "unanswerable", ()),
)

__all__ = [
    "DOCUMENTS",
    "QUERIES",
    "RETENTION_SENTENCE",
    "PROCUREMENT_SENTENCE",
    "TRAVEL_SENTENCE",
    "LargeDocument",
    "LargeQuery",
]
