import math
import re
from collections import Counter
from pathlib import Path

_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in",
    "is", "it", "of", "on", "or", "that", "the", "this", "to", "was",
    "were", "with",
}


def semantic_relevant_pages(wiki_dir: Path, question: str, limit: int = 5) -> list[str]:
    """Return the most relevant wiki pages using a local TF-IDF ranking."""
    pages = sorted(
        p for p in wiki_dir.glob("**/*.md")
        if p.name not in ("index.md", "log.md")
    )
    if not pages:
        return []

    docs = [_tokenize(p.read_text()) for p in pages]
    query_tokens = _tokenize(question)
    doc_freq = Counter()
    for tokens in docs:
        doc_freq.update(set(tokens))

    num_docs = len(docs)
    query_vec = _tfidf_vector(query_tokens, doc_freq, num_docs)
    ranked = []
    for page, tokens in zip(pages, docs, strict=False):
        page_vec = _tfidf_vector(tokens, doc_freq, num_docs)
        score = _cosine_similarity(query_vec, page_vec)
        ranked.append((page, score))

    ranked = sorted(ranked, key=lambda item: item[1], reverse=True)
    relevant = [
        f"{wiki_dir.name}/{page.relative_to(wiki_dir).as_posix()}"
        for page, score in ranked
        if score > 0
    ]
    return relevant[:limit]


def _tokenize(text: str) -> list[str]:
    return [
        token for token in re.findall(r"[A-Za-z0-9]+", text.lower())
        if len(token) > 1 and token not in _STOP_WORDS
    ]


def _tfidf_vector(tokens: list[str], doc_freq: Counter, num_docs: int) -> dict[str, float]:
    if not tokens:
        return {}
    counts = Counter(tokens)
    total = sum(counts.values())
    vector: dict[str, float] = {}
    for term, count in counts.items():
        tf = count / total
        idf = math.log((1 + num_docs) / (1 + doc_freq.get(term, 0))) + 1.0
        vector[term] = tf * idf
    return vector


def _cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    dot = sum(weight * right.get(term, 0.0) for term, weight in left.items())
    if dot == 0:
        return 0.0
    left_norm = math.sqrt(sum(weight * weight for weight in left.values()))
    right_norm = math.sqrt(sum(weight * weight for weight in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)
