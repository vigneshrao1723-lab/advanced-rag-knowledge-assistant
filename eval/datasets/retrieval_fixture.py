"""Deterministic retrieval-evaluation fixture set (GitHub Issue #4
"evaluation hooks" deliverable). A small, fixed set of short documents
and queries with known relevance judgments, used by
`eval/scripts/run_retrieval_evaluation.py` to compute real
docs/EVALUATION.md metrics against this project's actual pipeline
(chunking, embedding, dense/lexical/hybrid retrieval, generation) —
never fabricated numbers (docs/EVALUATION.md "Rule: never fabricate
results").

Each document is short enough (well under `ChunkingConfig`'s default
`target_chunk_size`) to become exactly one chunk, so "the document
relevant to a query" and "the chunk relevant to a query" are the same
thing — this keeps relevance judgments unambiguous without needing to
hand-label individual chunks.

Query wording deliberately shares literal keywords with its relevant
document: `LocalHashingEmbeddingProvider` (Issue #3, Slice 3.7) is an
un-weighted bag-of-hashed-words scheme with no semantic understanding,
so a fully paraphrased query would mostly test the *lexical* retrieval
path, not the dense one. This keeps the fixture representative of what
this pipeline's *current* (deterministic, local) providers can actually
be expected to do — the evaluation numbers this produces describe this
pipeline honestly, not an idealized one.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FixtureDocument:
    key: str
    filename: str
    content: str


@dataclass(frozen=True)
class FixtureQuery:
    query: str
    relevant_document_keys: frozenset[str]


DOCUMENTS: tuple[FixtureDocument, ...] = (
    FixtureDocument(
        key="refund_policy",
        filename="refund_policy.txt",
        content=(
            "Our refund policy allows returns within thirty days of purchase. "
            "Contact customer support with your order number to start a return."
        ),
    ),
    FixtureDocument(
        key="shipping_policy",
        filename="shipping_policy.txt",
        content=(
            "Standard shipping takes five to seven business days. "
            "Expedited shipping is available at checkout for an additional fee."
        ),
    ),
    FixtureDocument(
        key="warranty_policy",
        filename="warranty_policy.txt",
        content=(
            "All products include a one year limited warranty covering manufacturing defects. "
            "The warranty does not cover accidental damage or normal wear and tear."
        ),
    ),
    FixtureDocument(
        key="privacy_policy",
        filename="privacy_policy.txt",
        content=(
            "We collect only the account information necessary to provide the service. "
            "We never sell customer personal data to third parties."
        ),
    ),
    FixtureDocument(
        key="account_security",
        filename="account_security.txt",
        content=(
            "Enable two factor authentication to protect your account from unauthorized access. "
            "Never share your account password with anyone, including support staff."
        ),
    ),
    FixtureDocument(
        key="product_specs",
        filename="product_specs.txt",
        content=(
            "The device weighs three hundred grams and has a battery life of twelve hours. "
            "It supports Bluetooth five point two and USB-C charging."
        ),
    ),
)

QUERIES: tuple[FixtureQuery, ...] = (
    FixtureQuery("What is the refund policy for returns?", frozenset({"refund_policy"})),
    FixtureQuery("How long does shipping take to arrive?", frozenset({"shipping_policy"})),
    FixtureQuery(
        "Does the product warranty cover accidental damage?", frozenset({"warranty_policy"})
    ),
    FixtureQuery(
        "Do you sell my personal account data to third parties?", frozenset({"privacy_policy"})
    ),
    FixtureQuery(
        "How do I enable two factor authentication on my account?",
        frozenset({"account_security"}),
    ),
    FixtureQuery("What is the battery life of the device?", frozenset({"product_specs"})),
    FixtureQuery(
        "How many days do I have to return a purchased item for a refund?",
        frozenset({"refund_policy"}),
    ),
)

__all__ = ["DOCUMENTS", "QUERIES", "FixtureDocument", "FixtureQuery"]
