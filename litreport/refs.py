# -*- coding: utf-8 -*-
"""题录模型与 GB/T 7714 顺序编码制格式化。

一条题录就是一个 dict，字段见 `FIELDS` 说明；本模块只做“把结构化字段变成
规范字符串”和“按首次引用顺序编号”两件事，不联网、不猜数据。

设计约束（来自课程模板的实际要求，也写在 docs/TEMPLATE.md）：
- 顺序编码制：正文用 {{key}} 占位，渲染时替换成 [n]，参考文献表按首次引用排序；
- 文末未引用的条目可以丢弃，避免“凑数文献”；
- 缺字段宁可不输出该字段（年份未知就别写 2026），不允许补全或猜测。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# 题录类型到 GB/T 7714 的文献类型标识
KIND_MARKS = {
    "journal": "J",
    "conference": "C",
    "preprint": "EB/OL",
    "book": "M",
    "thesis": "D",
    "standard": "S",
    "report": "R",
}

CITATION = re.compile(r"\{\{([a-zA-Z0-9_,\-\s]+)\}\}")
ENGLISH_AUTHOR = re.compile(r"^[\x00-\x7F]+$")


@dataclass
class Reference:
    key: str
    kind: str = "journal"
    title: str = ""
    authors: list[str] = field(default_factory=list)
    year: str = ""
    journal: str = ""
    volume: str = ""
    issue: str = ""
    pages: str = ""
    doi: str = ""
    publisher: str = ""
    place: str = ""
    conference: str = ""
    arxiv: str = ""
    standard_no: str = ""
    note: str = ""

    # ---------------------------------------------------------------- 作者
    def author_text(self) -> str:
        names = [a.strip() for a in self.authors if a and a.strip()]
        if not names:
            return ""
        english = all(ENGLISH_AUTHOR.match(n) for n in names)
        if english:
            shown = names[:3]
            text = ", ".join(_english_name(n) for n in shown)
            if len(names) > 3:
                text += ", et al"
            return text
        shown = names[:3]
        text = ", ".join(shown)
        if len(names) > 3:
            text += ", 等"
        return text

    # ---------------------------------------------------------------- 判定
    def is_english(self) -> bool:
        """题目与期刊名都不含中日韩字符时算英文文献（用于统计英文篇数）。"""
        sample = f"{self.title} {self.journal} {self.conference} {self.publisher}"
        return not re.search(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", sample)

    # ---------------------------------------------------------------- 出版项
    def _year_volume_issue(self) -> str:
        head = self.year or ""
        if self.volume:
            head += (", " if head else "") + self.volume
        if self.issue:
            head += f"({self.issue})"
        return head

    def _pages(self) -> str:
        return f": {self.pages}" if self.pages else ""

    def format(self, mark_override: str | None = None) -> str:
        mark = mark_override or KIND_MARKS.get(self.kind, "Z")
        authors = self.author_text()
        lead = f"{authors}. " if authors else ""
        title = (self.title or "").strip().rstrip(".")
        body = ""

        if self.kind == "journal":
            body = f"{title}[{mark}]. {self.journal}"
            tail = self._year_volume_issue()
            if tail:
                body += f", {tail}"
            body += self._pages() + "."
        elif self.kind == "conference":
            body = f"{title}[{mark}]//{self.conference}"
            if self.place or self.publisher:
                body += f". {self.place}: {self.publisher}".rstrip()
            tail = self.year
            if tail:
                body += f", {tail}" if body.endswith("]") is False else f". {tail}"
            body += self._pages() + "."
        elif self.kind == "preprint":
            body = f"{title}[{mark}]. "
            if self.arxiv:
                body += f"arXiv:{self.arxiv}"
                if self.year:
                    body += f", {self.year}"
                body += "."
            else:
                body += f"{self.year}." if self.year else ""
        elif self.kind == "book":
            body = f"{title}[{mark}]. "
            if self.place:
                body += f"{self.place}: "
            body += f"{self.publisher}" if self.publisher else ""
            if self.year:
                body += f", {self.year}"
            body += "."
        elif self.kind == "thesis":
            body = f"{title}[{mark}]. "
            if self.place:
                body += f"{self.place}: "
            body += f"{self.publisher}" if self.publisher else ""
            if self.year:
                body += f", {self.year}"
            body += "."
        elif self.kind == "standard":
            head_no = f"{self.standard_no} " if self.standard_no else ""
            body = f"{head_no}{title}[{mark}]. "
            body += f"{self.year}." if self.year else ""
        else:
            body = f"{title}[{mark}]. {self.publisher or self.journal}"
            if self.year:
                body += f", {self.year}"
            body += "."

        text = (lead + body).strip()
        text = re.sub(r"\s+\.", ".", text)
        text = re.sub(r"\.{2,}", ".", text)
        if self.doi:
            text += f" DOI:{self.doi}."
        if self.note:
            text += f" {self.note}"
        return text.strip()


def _english_name(name: str) -> str:
    """把 'Yao Shunyu' / 'Shunyu Yao' 统一成 'YAO S' 这种 GB/T 7714 写法。"""
    parts = [p for p in re.split(r"[\s,]+", name.strip()) if p]
    if not parts:
        return name
    # 全大写姓氏已经合规时不再动（复合姓如 IZQUIERDO-BADIOLA 也算）
    if parts[0].isupper() and len(parts[0]) <= 40 and parts[0].replace("-", "").isalpha():
        surname, rest = parts[0], parts[1:]
    else:
        surname, rest = parts[-1], parts[:-1]
    initials = " ".join(f"{p[0].upper()}" for p in rest if p)
    return f"{surname.upper()} {initials}".strip()


# -------------------------------------------------------------------- 引用编号
class CitationBook:
    """按首次引用顺序编号，并记录每条题录被引用的序号。"""

    def __init__(self, references: list[Reference]):
        self.references = list(references)
        self.by_key = {r.key: r for r in references}
        self.order: list[str] = []
        self.missing: list[str] = []
        self.duplicates: list[str] = []

    def cite(self, keys: str) -> str:
        numbers = []
        for raw in keys.split(","):
            key = raw.strip()
            if not key:
                continue
            if key not in self.by_key:
                if key not in self.missing:
                    self.missing.append(key)
                continue
            if key in self.order:
                if key not in self.duplicates:
                    self.duplicates.append(key)
            else:
                self.order.append(key)
            numbers.append(self.order.index(key) + 1)
        if not numbers:
            return "[?]"
        return "[" + ",".join(str(n) for n in numbers) + "]"

    def cited_references(self) -> list[Reference]:
        return [self.by_key[k] for k in self.order]

    def uncited(self) -> list[Reference]:
        return [r for r in self.by_key.values() if r.key not in self.order]


def parse_references(items: list[dict]) -> list[Reference]:
    """把 JSON 里的 dict 列表转成 Reference，未知字段忽略（不报错、不丢数据到日志）。"""
    known = set(Reference.__dataclass_fields__.keys())
    refs = []
    for item in items:
        data = {k: v for k, v in item.items() if k in known}
        if "authors" in data and isinstance(data["authors"], str):
            data["authors"] = [a.strip() for a in re.split(r"[,;，；]", data["authors"]) if a.strip()]
        for key in ("year", "volume", "issue", "pages", "doi", "arxiv"):
            if key in data and data[key] is not None and not isinstance(data[key], str):
                data[key] = str(data[key])
        refs.append(Reference(**data))
    return refs
