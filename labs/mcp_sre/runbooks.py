"""
把 knowledge_docs/ 的 Markdown runbook 切成段落並建立混合檢索索引。
Chunks the Markdown runbooks by `##` section and indexes them with the chapter-5 retriever.

切段原則：以標題切，每段帶上文件標題，讓段落脫離原文後仍看得懂在講什麼。
Chunk by heading and prefix each chunk with its document title so it stands alone.
"""

from __future__ import annotations

import re
from pathlib import Path

from labs.core.retrieval import Doc, HybridRetriever

DOCS_DIR = Path(__file__).parent / "knowledge_docs"


def load_chunks(docs_dir: Path = DOCS_DIR) -> list[Doc]:
    chunks: list[Doc] = []
    for path in sorted(docs_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        doc_title = title_match.group(1).strip() if title_match else path.stem
        id_match = re.search(r"Document ID\**\s*:\s*([A-Z0-9-]+)", text)
        doc_id = id_match.group(1) if id_match else path.stem
        for n, section in enumerate(re.split(r"\n(?=##\s)", text)[1:], start=1):
            heading, _, body = section.partition("\n")
            body = body.strip().strip("-").strip()
            if len(body) < 30:
                continue
            chunks.append(Doc(
                id=f"{doc_id}#{n}",
                title=f"{doc_title} / {heading.lstrip('#').strip()}",
                text=body,
            ))
    return chunks


class RunbookSearch:
    def __init__(self, docs_dir: Path = DOCS_DIR):
        self.chunks = load_chunks(docs_dir)
        self.retriever = HybridRetriever(self.chunks, candidates=8)

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        res = self.retriever.search(query, top_n=top_k)
        return [
            {"chunk_id": d.id, "title": d.title, "text": d.text, "rrf_score": round(score, 5)}
            for d, score in res.fused
        ]
