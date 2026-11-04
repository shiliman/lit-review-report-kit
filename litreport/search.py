# -*- coding: utf-8 -*-
"""把「课题」拆成可检索的概念组，并生成各数据库的检索式。

这一步不联网，只做三件事：
1. 概念分解表（课程报告里通常要求“检索概念分解与同义词扩展”）；
2. 布尔检索式（CNKI / Web of Science 的字段写法）；
3. 自然语言查询（Crossref / arXiv，它们不吃布尔式）。

原则：宁可同义词多列、漏检少一点；四组概念不要一次全 AND（结果会被压到个位数）。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Concept:
    name: str
    zh: list[str] = field(default_factory=list)
    en: list[str] = field(default_factory=list)


def concept_table(concepts: list[Concept]) -> dict:
    """生成“表 1 检索概念分解与同义词扩展”的三线表数据。"""
    rows = []
    for concept in concepts:
        rows.append([
            concept.name,
            "、".join(concept.zh[:3]) or "—",
            "、".join(concept.zh[3:]) or "—",
            ", ".join(concept.en) or "—",
        ])
    return {
        "caption": "表 1 检索概念分解与同义词扩展",
        "headers": ["概念组", "中文规范词", "同义、近义词", "英文对应词"],
        "rows": rows,
        "widths": [2.4, 4.2, 3.6, 4.4],
    }


def cnki_query(concepts: list[Concept], fields=("主题", "篇名"), pair=True) -> list[dict]:
    """生成 CNKI 式检索式。pair=True 时只做两两组合，避免四组同时 AND。"""
    if not concepts:
        return []
    def block(concept):
        terms = [t for t in concept.zh if t]
        if not terms:
            return ""
        inner = " OR ".join(terms)
        return f"({inner})" if len(terms) > 1 else inner

    queries = []
    if pair:
        for i in range(len(concepts)):
            for j in range(i + 1, len(concepts)):
                left, right = block(concepts[i]), block(concepts[j])
                if not left or not right:
                    continue
                expression = f"{fields[0]}=({left}) AND {fields[0]}=({right})"
                queries.append({
                    "label": f"{concepts[i].name} × {concepts[j].name}",
                    "database": "CNKI",
                    "expression": expression,
                    "hint": "两组概念交叉，命中量通常几十到几百条",
                })
    else:
        parts = [block(c) for c in concepts if block(c)]
        expression = " AND ".join(f"{fields[0]}=({p})" for p in parts)
        queries.append({"label": "全部概念", "database": "CNKI", "expression": expression,
                        "hint": "四组同时 AND 往往只剩个位数，仅用于查全性核对"})
    return queries


def wos_query(concepts: list[Concept]) -> str:
    groups = []
    for concept in concepts:
        terms = concept.en or concept.zh
        if not terms:
            continue
        inner = " OR ".join(f'"{t}"' if " " in t else t for t in terms)
        groups.append(f"({inner})")
    return " AND ".join(f"TS={group}" for group in groups)


def natural_query(concepts: list[Concept], language="en") -> str:
    """Crossref / arXiv 用自然语言查询；取每组第一个英文词拼成短语。"""
    if language == "en":
        words = [c.en[0] for c in concepts if c.en]
    else:
        words = [c.zh[0] for c in concepts if c.zh]
    return " ".join(words)


def arxiv_query(concepts: list[Concept]) -> str:
    fields = []
    for concept in concepts[:3]:
        terms = [t for t in concept.en if t]
        if not terms:
            continue
        inner = " OR ".join(f'abs:"{t}"' if " " in t else f"abs:{t}" for t in terms[:3])
        fields.append(f"({inner})")
    return " AND ".join(fields)


def plan(concepts: list[Concept]) -> dict:
    """一次给全：分解表 + 三套检索式，供报告与命令行共用。"""
    return {
        "table": concept_table(concepts),
        "cnki": cnki_query(concepts),
        "wos": wos_query(concepts),
        "crossref": natural_query(concepts, "en"),
        "arxiv": arxiv_query(concepts),
    }


def concepts_from_json(items: list[dict]) -> list[Concept]:
    return [Concept(name=item.get("name", ""), zh=item.get("zh", []) or [], en=item.get("en", []) or [])
            for item in items]
