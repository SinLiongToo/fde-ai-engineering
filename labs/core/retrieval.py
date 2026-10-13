"""
第 5 章：檢索 / Chapter 5: Retrieval

內容 / Contents
- BM25：詞彙比對，擅長精確的 ID、錯誤碼、設定名稱。
- CharNgramVectorizer：字元 n-gram 的 TF-IDF 向量。
  ⚠ 這「不是」語義向量模型。它能處理詞形變化（migrate / migration）與錯字，
    但不懂同義詞（slow ≠ latency）。它的用途是讓 lab 能離線執行；
    要體驗真正的 dense retrieval，請實作 Embedder 介面並接上 embedding 模型。
  ⚠ This is NOT a semantic embedding model. It is an offline stand-in that handles
    morphology and typos but not synonyms. Plug a real model in via `Embedder`.
- reciprocal_rank_fusion：只用名次融合，不需要校準兩種分數。
- 權限過濾：先過濾再排序，避免把使用者無權看的文件送進 prompt。
- recall_at_k / mrr：檢索品質指標。
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Protocol


@dataclass(frozen=True)
class Doc:
    id: str
    title: str
    text: str
    allowed_groups: frozenset[str] = field(default_factory=lambda: frozenset({"everyone"}))

    @property
    def content(self) -> str:
        return f"{self.title}\n{self.text}"


CORPUS: list[Doc] = [
    Doc("CLAUSE-001", "Payment webhook latency SLA",
        "APAC payment gateway authorization webhooks must respond within 250 ms at P99 under peak load. "
        "Responses slower than 500 ms open a P1 incident."),
    Doc("CLAUSE-002", "Cross-border transfer of personal data",
        "Personal data of EU customers stays in the Frankfurt region. Transfers outside the EU require "
        "pseudonymization and a documented legal basis under GDPR Article 44.",
        frozenset({"legal", "security"})),
    Doc("CLAUSE-003", "Destructive database operations",
        "DROP, TRUNCATE and unbounded DELETE statements on production ledgers require approval from two "
        "engineers and a verified snapshot taken within the last hour."),
    Doc("CLAUSE-004", "Zero-downtime schema migration",
        "DDL on high-traffic PostgreSQL tables must set lock_timeout = 2s and statement_timeout = 5s so a "
        "blocked migration fails fast instead of queueing every query behind its lock."),
    Doc("CLAUSE-005", "Model API rate limits",
        "Calls to external model APIs use exponential backoff with jitter and a per-tenant limit of 100 "
        "requests per minute to protect the shared token budget."),
    Doc("CLAUSE-006", "Incident error code PAY-4102",
        "PAY-4102 means the card network rejected the authorization because the merchant category code is "
        "missing. Retrying will not help; fix the merchant profile."),
    Doc("CLAUSE-007", "Secrets handling",
        "API keys and database passwords are read from the secret manager at startup. Secrets never appear "
        "in source code, logs, prompts or model outputs.", frozenset({"security"})),
    Doc("CLAUSE-008", "Read replica usage",
        "Analytics and reporting queries run against the read replica. The primary database only serves "
        "transactional traffic from the checkout service."),
    Doc("CLAUSE-009", "Data retention",
        "Raw chat transcripts are deleted after 30 days. Aggregated, anonymized metrics may be kept for "
        "two years for capacity planning.", frozenset({"legal"})),
    Doc("CLAUSE-010", "On-call escalation",
        "If the primary on-call engineer does not acknowledge a P1 page within 10 minutes, the page escalates "
        "to the secondary and then to the engineering manager."),
]


# ---------------------------------------------------------------- lexical: BM25

TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*")
STOPWORDS = frozenset(
    "a an the and or of to in on for is are be by do does i how what when with from at it this that".split()
)


def tokenize(text: str) -> list[str]:
    """
    保留 lock_timeout、PAY-4102 這種帶連字號/底線的識別字為單一 token，並移除停用詞。
    注意：這個 tokenizer 不處理中文。中文需要斷詞（如 jieba）或字元 n-gram。
    Keeps identifiers like lock_timeout / PAY-4102 intact. Does not handle CJK text.
    """
    return [t for t in TOKEN_RE.findall(text.lower()) if t not in STOPWORDS]


class BM25:
    def __init__(self, docs: list[Doc], k1: float = 1.2, b: float = 0.75):
        self.docs = docs
        self.k1, self.b = k1, b
        self.doc_tokens = [tokenize(d.content) for d in docs]
        self.tf = [Counter(toks) for toks in self.doc_tokens]
        self.avgdl = sum(len(t) for t in self.doc_tokens) / max(len(docs), 1)
        df: Counter[str] = Counter()
        for toks in self.doc_tokens:
            df.update(set(toks))
        n = len(docs)
        # Lucene 版本的 IDF，保證非負 / Lucene-style IDF, always >= 0
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def score(self, query: str, i: int) -> float:
        tf, dl = self.tf[i], len(self.doc_tokens[i])
        s = 0.0
        for t in tokenize(query):
            if t not in tf:
                continue
            f = tf[t]
            s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
        return s

    def search(self, query: str, top_n: int = 5) -> list[tuple[Doc, float]]:
        scored = [(d, self.score(query, i)) for i, d in enumerate(self.docs)]
        scored = [x for x in scored if x[1] > 0]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_n]


# ---------------------------------------------------------------- vector

class Embedder(Protocol):
    """接真正的 embedding 模型時，實作這個介面即可 / Implement this to plug in a real model."""

    def embed(self, texts: list[str]) -> list[dict[str, float] | list[float]]: ...


def _ngrams(text: str, n: int) -> list[str]:
    s = f" {' '.join(tokenize(text))} "
    return [s[i:i + n] for i in range(len(s) - n + 1)]


class CharNgramVectorizer:
    """字元 3-gram TF-IDF（離線替身，見檔案開頭說明）/ char 3-gram TF-IDF stand-in."""

    def __init__(self, docs: Iterable[Doc], n: int = 3):
        self.n = n
        grams = [Counter(_ngrams(d.content, n)) for d in docs]
        df: Counter[str] = Counter()
        for g in grams:
            df.update(g.keys())
        total = len(grams)
        self.idf = {g: math.log((1 + total) / (1 + f)) + 1 for g, f in df.items()}

    def embed(self, texts: list[str]) -> list[dict[str, float]]:
        out = []
        for t in texts:
            c = Counter(_ngrams(t, self.n))
            vec = {g: tf * self.idf.get(g, 0.0) for g, tf in c.items()}
            norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
            out.append({g: v / norm for g, v in vec.items()})
        return out


def cosine_sparse(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())


class VectorIndex:
    def __init__(self, docs: list[Doc], embedder: Embedder | None = None):
        self.docs = docs
        self.embedder = embedder or CharNgramVectorizer(docs)
        self.vectors = self.embedder.embed([d.content for d in docs])

    def search(self, query: str, top_n: int = 5) -> list[tuple[Doc, float]]:
        q = self.embedder.embed([query])[0]
        scored = [(d, _similarity(q, v)) for d, v in zip(self.docs, self.vectors)]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_n]


def _similarity(a, b) -> float:
    if isinstance(a, dict):
        return cosine_sparse(a, b)
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


# ---------------------------------------------------------------- fusion

def reciprocal_rank_fusion(
    rankings: list[list[str]], k: int = 60, top_n: int = 5
) -> list[tuple[str, float]]:
    """
    RRF(d) = Σ_r 1 / (k + rank_r(d))，rank 從 1 開始。
    只看名次，所以 BM25 分數（無上限）與 cosine（-1..1）不必先正規化。
    k 越大，排名靠後的文件影響越平均；60 是原論文 (Cormack et al., 2009) 的經驗值。
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_n]


@dataclass
class HybridResult:
    lexical: list[tuple[Doc, float]]
    vector: list[tuple[Doc, float]]
    fused: list[tuple[Doc, float]]


class HybridRetriever:
    def __init__(self, docs: list[Doc] = CORPUS, embedder: Embedder | None = None, candidates: int = 5):
        self.docs = docs
        self.bm25 = BM25(docs)
        self.vec = VectorIndex(docs, embedder)
        self.candidates = candidates
        self.by_id = {d.id: d for d in docs}

    def search(self, query: str, user_groups: set[str] | None = None, top_n: int = 3) -> HybridResult:
        allowed = _allowed_ids(self.docs, user_groups)
        # 先過濾權限，再取候選。正式系統要在資料庫查詢裡做（WHERE 條件），而不是查完再丟掉。
        # Filter by permission first. In production do it inside the DB query.
        lex = [x for x in self.bm25.search(query, len(self.docs)) if x[0].id in allowed][: self.candidates]
        vec = [x for x in self.vec.search(query, len(self.docs)) if x[0].id in allowed][: self.candidates]
        fused = reciprocal_rank_fusion([[d.id for d, _ in lex], [d.id for d, _ in vec]], top_n=top_n)
        return HybridResult(lex, vec, [(self.by_id[i], s) for i, s in fused])


def _allowed_ids(docs: list[Doc], user_groups: set[str] | None) -> set[str]:
    groups = (user_groups or set()) | {"everyone"}
    return {d.id for d in docs if d.allowed_groups & groups}


# ---------------------------------------------------------------- metrics

def recall_at_k(retrieved: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 1.0
    return len(set(retrieved[:k]) & relevant) / len(relevant)


def reciprocal_rank(retrieved: list[str], relevant: set[str]) -> float:
    for rank, doc_id in enumerate(retrieved, start=1):
        if doc_id in relevant:
            return 1.0 / rank
    return 0.0


if __name__ == "__main__":
    r = HybridRetriever()
    for q in ["PAY-4102", "how do I migrate a big postgres table safely", "personal data leaving the EU"]:
        res = r.search(q, user_groups={"legal"})
        print(f"\n> {q}")
        for name, rows in (("BM25", res.lexical), ("vector", res.vector), ("RRF", res.fused)):
            print(f"  {name:7}", ", ".join(f"{d.id}({s:.3f})" for d, s in rows[:3]))
