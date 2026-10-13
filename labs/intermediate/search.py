"""
中級 3：更好的搜尋

三個版本，一步一步改進，並用測試題量出差別（python -m labs.intermediate.evals --search）：

  v1  數相同的兩字片段（入門篇 B4 的做法）
  v2  依「片段有多罕見」加權，並設最低分數門檻
      → 「公司」「提供」這種到處都有的片段不再主導結果，分數太低就回傳「找不到」
  v3  v2 + 同義詞擴充
      → 「筆電」也能找到「筆記型電腦」

更進一步的做法是用 embedding（向量）搜尋，見進階篇第 05 章。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

HANDBOOK_PATH = Path(__file__).parent / "handbook.md"

# 同義詞表：key 出現在問題裡時，把 value 也加進去一起搜尋
SYNONYMS = {
    "筆電": "筆記型電腦",
    "電腦": "筆記型電腦",
    "年假": "特休",
    "休假": "特休",
    "在家上班": "遠端工作",
    "在家工作": "遠端工作",
    "WFH": "遠端工作",
    "報銷": "報帳",
    "請款": "報帳",
    "辭職": "離職",
    "健檢": "健康檢查",
    "超時": "加班",
    "上課": "教育訓練",
    "進修": "教育訓練",
}

PUNCT = set("，。？！、：；「」（）() \n\t.,?!:;")


@dataclass(frozen=True)
class Chunk:
    id: str      # 例如 H05
    title: str   # 例如 遠端工作
    text: str

    @property
    def full(self) -> str:
        return f"{self.title}：{self.text}"


def load_chunks(path: Path = HANDBOOK_PATH) -> list[Chunk]:
    """依「## H01 標題」切段，每段一個 Chunk。"""
    text = path.read_text(encoding="utf-8")
    chunks = []
    for m in re.finditer(r"^## (H\d+) (.+?)\n(.*?)(?=^## |\Z)", text, re.S | re.M):
        chunks.append(Chunk(m.group(1), m.group(2).strip(), " ".join(m.group(3).split())))
    return chunks


def pieces(text: str) -> set[str]:
    """兩字一組的片段（英數字轉小寫）。"""
    chars = [c.lower() for c in text if c not in PUNCT]
    return {chars[i] + chars[i + 1] for i in range(len(chars) - 1)}


def expand_synonyms(question: str) -> str:
    extra = [v for k, v in SYNONYMS.items() if k.lower() in question.lower()]
    return question + " " + " ".join(extra) if extra else question


@dataclass
class Hit:
    chunk: Chunk
    score: float
    shared: list[str]


class Searcher:
    def __init__(self, chunks: list[Chunk] | None = None, version: str = "v3", min_score: float = 3.0):
        self.chunks = chunks or load_chunks()
        self.version = version
        self.min_score = min_score
        self.chunk_pieces = {c.id: pieces(c.full) for c in self.chunks}
        # 每個片段出現在幾段裡；越少見，權重越高（IDF 的概念）
        n = len(self.chunks)
        df: dict[str, int] = {}
        for ps in self.chunk_pieces.values():
            for p in ps:
                df[p] = df.get(p, 0) + 1
        self.weight = {p: math.log((n + 1) / (f + 0.5)) for p, f in df.items()}

    def search(self, question: str, top_n: int = 3) -> list[Hit]:
        if self.version == "v3":
            question = expand_synonyms(question)
        q = pieces(question)
        hits = []
        for c in self.chunks:
            shared = sorted(q & self.chunk_pieces[c.id])
            if not shared:
                continue
            if self.version == "v1":
                score = float(len(shared))
            else:
                score = sum(self.weight[p] for p in shared)
            hits.append(Hit(c, round(score, 3), shared))
        hits.sort(key=lambda h: (-h.score, h.chunk.id))
        if self.version != "v1":
            hits = [h for h in hits if h.score >= self.min_score]
        return hits[:top_n]


if __name__ == "__main__":
    import sys

    question = sys.argv[1] if len(sys.argv) > 1 else "筆電壞了怎麼辦？"
    for version in ("v1", "v2", "v3"):
        hits = Searcher(version=version).search(question)
        print(f"{version}: " + (", ".join(f"{h.chunk.id} {h.chunk.title}({h.score})" for h in hits) or "（找不到）"))
