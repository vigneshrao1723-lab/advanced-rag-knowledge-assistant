"""Understanding what a question points at -- pure functions, no I/O.

Real questions refer to things by label or by name rather than by topic:
"explain Program 5", "the first program in my PC lab PDF", "explain that line
by line". Embedding/keyword similarity cannot resolve these (a hashed
bag-of-words has no notion of "Program 5" or of a filename), so they are
parsed here and resolved against the document outline and the workspace's
documents (`app.retrieval.outline`, `app.retrieval.resolve`).

Nothing here is specific to one document, filename or program number.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

# --- labelled items: "Program 5", "Exercise 3", "the first program" ---------

_KIND_ALTERNATION = (
    r"programs?|programmes?|exercises?|experiments?|practicals?|questions?|problems?|"
    r"tasks?|assignments?|listings?|examples?|labs?|chapters?|sections?"
)
_NUMBER_RE = re.compile(
    rf"\b(?P<kind>{_KIND_ALTERNATION})\b\s*(?:no\.?|num\.?|number|#|n°)?\s*[:\-]?\s*"
    rf"(?P<num>\d{{1,3}})\b",
    re.IGNORECASE,
)
_ORDINALS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6,
    "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "last": -1, "final": -1,
}  # fmt: skip
_ORDINAL_RE = re.compile(
    rf"\b(?P<ord>{'|'.join(_ORDINALS)}|\d{{1,2}}(?:st|nd|rd|th))\b\s+(?:[\w+#-]+\s+)?"
    rf"(?P<kind>{_KIND_ALTERNATION})\b",
    re.IGNORECASE,
)


def normalize_kind(word: str) -> str:
    word = word.lower()
    if word.startswith("programme"):
        return "program"
    return word[:-1] if word.endswith("s") else word


@dataclass(frozen=True)
class Locator:
    """A reference to a labelled item. Exactly one of `number` / `ordinal`
    is set; `ordinal` is 1-based, -1 meaning "the last one"."""

    kind: str
    number: int | None = None
    ordinal: int | None = None

    def describe(self) -> str:
        if self.number is not None:
            return f"{self.kind.capitalize()} {self.number}"
        if self.ordinal == -1:
            return f"the last {self.kind}"
        return f"{self.kind} #{self.ordinal}"


def parse_locator(query: str) -> Locator | None:
    match = _NUMBER_RE.search(query)
    if match:
        return Locator(kind=normalize_kind(match.group("kind")), number=int(match.group("num")))
    match = _ORDINAL_RE.search(query)
    if match:
        raw = match.group("ord").lower()
        ordinal = _ORDINALS[raw] if raw in _ORDINALS else int(re.sub(r"\D", "", raw))
        return Locator(kind=normalize_kind(match.group("kind")), ordinal=ordinal)
    return None


def heading_pattern(kind: str) -> re.Pattern[str]:
    """A line that *starts* an item of `kind`: "Program 5: ...", "## Program 5",
    "**Program 5**". A range such as "Programs 5 to 9" is a title, not an
    item, and is skipped."""
    return re.compile(
        rf"^[ \t#*>]*{re.escape(kind)}(?:s|mes?)?[ \t]*(?:no\.?|num\.?|number|#|n°)?"
        rf"[ \t]*[:\-]?[ \t]*(?P<num>\d{{1,3}})\b(?![ \t]*(?:to|and|&|-|–|through)[ \t]*\d)",
        re.IGNORECASE | re.MULTILINE,
    )


# --- naming a document ---------------------------------------------------------

_FILENAME_NOISE = {
    "pdf", "doc", "docx", "txt", "md", "csv", "file", "copy", "final", "new", "v", "draft",
}  # fmt: skip
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*")


def _words(text: str) -> list[str]:
    # Split snake/kebab/dotted names and camelCase: "PC_LAB_Test" -> pc lab test.
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    return [w.lower() for w in _TOKEN_RE.findall(spaced)]


def filename_tokens(filename: str) -> list[str]:
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    return [w for w in _words(stem) if w not in _FILENAME_NOISE]


def match_documents(query: str, documents: Iterable[tuple[uuid.UUID, str]]) -> list[uuid.UUID]:
    """Documents the question names, by filename. A document matches when
    two or more of its filename words appear in the question, when *all* of
    its (one or two) filename words do, or when its whole normalised stem is
    quoted. Returns only the best-scoring matches (several => ambiguous)."""
    query_words = set(_words(query))
    normalized_query = " ".join(_words(query))
    scored: list[tuple[int, uuid.UUID]] = []
    for doc_id, filename in documents:
        tokens = filename_tokens(filename)
        if not tokens:
            continue
        overlap = len(set(tokens) & query_words)
        stem = " ".join(tokens)
        quoted = len(tokens) >= 1 and stem in normalized_query
        if overlap >= 2 or (overlap == len(set(tokens)) >= 1 and len(set(tokens)) <= 2) or quoted:
            scored.append((max(overlap, len(tokens) if quoted else 0), doc_id))
    if not scored:
        return []
    best = max(score for score, _ in scored)
    return [doc_id for score, doc_id in scored if score == best]


# --- follow-ups --------------------------------------------------------------------

_FOLLOWUP_RE = re.compile(
    r"\b(this|that|it|these|those|above|previous|same|again|more|further|continue|simplif\w*|"
    r"shorter|simpler|elaborate|detail\w*|line[\s-]*by[\s-]*line|step[\s-]*by[\s-]*step|"
    r"beginner|exam|why|how come|what about|and the)\b",
    re.IGNORECASE,
)
_MAX_FOLLOWUP_WORDS = 14


def is_followup(query: str) -> bool:
    """A short question that leans on the previous turn ("explain that line
    by line", "now as a beginner", "why?")."""
    words = query.split()
    if not words or len(words) > _MAX_FOLLOWUP_WORDS:
        return False
    return bool(_FOLLOWUP_RE.search(query)) or len(words) <= 2


# --- content-word overlap (relevance gate) ----------------------------------------

_STOPWORDS = frozenset(
    (
        "a", "about", "above", "after", "again", "all", "also", "am", "an", "and", "any",
        "are", "as", "at", "be", "because", "been", "before", "being", "below", "between",
        "both", "but", "by", "can", "could", "did", "do", "does", "doing", "down", "during",
        "each", "few", "for", "from", "further", "had", "has", "have", "having", "he", "her",
        "here", "hers", "him", "his", "how", "i", "if", "in", "into", "is", "it", "its",
        "just", "me", "more", "most", "my", "no", "nor", "not", "now", "of", "off", "on",
        "once", "only", "or", "other", "our", "out", "over", "own", "same", "she", "should",
        "so", "some", "such", "than", "that", "the", "their", "theirs", "them", "then",
        "there", "these", "they", "this", "those", "through", "to", "too", "under", "until",
        "up", "us", "very", "was", "we", "were", "what", "when", "where", "which", "while",
        "who", "whom", "why", "will", "with", "would", "you", "your", "yours", "explain",
        "describe", "tell", "show", "give", "please", "summarise", "summarize", "list",
        "define", "write", "make", "mean", "means", "meaning", "pdf", "file", "document",
        "documents", "uploaded", "upload", "say", "says", "said", "information", "info",
        "content", "contents", "text", "details", "detail", "overview", "summary", "main",
        "key", "points", "point", "topic", "topics", "discuss", "discusses", "covered",
        "cover", "covers",
    )
)
_STEM_PREFIX = 5


def content_terms(text: str) -> set[str]:
    """Meaningful words (stopwords and command verbs removed), reduced to a
    5-letter prefix so "rotated"/"rotation"/"rotates" meet."""
    terms: set[str] = set()
    for word in re.findall(r"[A-Za-z][A-Za-z0-9_]*|\d+", text.lower()):
        if word in _STOPWORDS or (len(word) < 3 and not word.isdigit()):
            continue
        terms.add(word[:_STEM_PREFIX])
    return terms


def shares_content_terms(query: str, passage: str) -> bool:
    wanted = {t for t in content_terms(query) if not t.isdigit()}
    if not wanted:
        return True  # nothing to test against: do not discard evidence
    return bool(wanted & content_terms(passage))


def any_shares_content_terms(query: str, passages: Sequence[str]) -> bool:
    return any(shares_content_terms(query, passage) for passage in passages)


__all__ = [
    "Locator",
    "any_shares_content_terms",
    "content_terms",
    "filename_tokens",
    "heading_pattern",
    "is_followup",
    "match_documents",
    "normalize_kind",
    "parse_locator",
    "shares_content_terms",
]
