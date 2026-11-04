# -*- coding: utf-8 -*-
"""命令行入口：new / plan / verify / build / slides / all。

设计约定：
- 子命令都能单独跑，互不依赖（先 plan 再 verify 再 build 也可以）；
- 任何一步出问题都用非零退出码 + 人话说明，不吞错；
- build 完自动跑一遍「规格自检」（字数、篇数、英文数、引用完整性），把结果打出来，
  但**不替人决定**是否合格——阈值由课程要求决定，工具只报数。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import refs as refs_mod
from .docx_kit import ReportDoc
from .search import concepts_from_json, plan as build_plan
from .slides import build_deck


def _read_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def cmd_new(args):
    directory = args.dir
    os.makedirs(directory, exist_ok=True)
    project_path = os.path.join(directory, "project.json")
    refs_path = os.path.join(directory, "refs.json")
    if os.path.exists(project_path) and not args.force:
        print(f"project.json 已存在：{project_path}（加 --force 覆盖）")
        return 1
    _write_json(project_path, {
        "title": args.title or "科技文献检索报告",
        "subtitle": "——以「（你的课题）」为例",
        "cover_date": "2026 年 1 月",
        "sections": [
            {"type": "h1", "text": "1 课题分析"},
            {"type": "p", "text": "在这里写课题背景、为什么值得检索。"},
            {"type": "h2", "text": "1.1 检索概念分解"},
            {"type": "p", "text": "概念分解见下方表格；同义词决定召回率。"},
        ],
        "concepts": [],
        "references": [],
    })
    _write_json(refs_path, {"references": []})
    print(f"已创建：\n  {project_path}\n  {refs_path}\n下一步：把题录填进 refs.json，然后跑 verify。")
    return 0


def cmd_plan(args):
    project = _read_json(args.project)
    concepts = concepts_from_json(project.get("concepts", []))
    if not concepts:
        print("project.json 里没有 concepts，先补概念组。")
        return 1
    result = build_plan(concepts)
    print("【概念分解表】")
    print("\t".join(result["table"]["headers"]))
    for row in result["table"]["rows"]:
        print("\t".join(row))
    print("\n【CNKI 检索式】")
    for item in result["cnki"]:
        print(f"- {item['label']}: {item['expression']}")
    print(f"\n【Web of Science】\n{result['wos']}")
    print(f"\n【Crossref 自然语言】\n{result['crossref']}")
    print(f"\n【arXiv】\n{result['arxiv']}")
    return 0


def cmd_verify(args):
    from .verify import check_all, format_table, summarize

    payload = _read_json(args.refs)
    references = refs_mod.parse_references(payload.get("references", []))
    if not references:
        print("refs.json 里没有题录。")
        return 1
    results = check_all(references, cache_path=args.cache, delay=args.delay)
    print(format_table(results))
    counts = summarize(results)
    print(f"\n通过 {counts['ok']} / 不一致 {counts['mismatch']} / 未找到 {counts['not_found']} / 无法判定 {counts['unknown']}")
    if counts["mismatch"] or counts["not_found"] or counts["unknown"]:
        print("\n注意：不一致与未找到的条目必须先改对再写进报告；无法判定的要在报告里说明核验方式或改为不引用。")
        return 2
    return 0


def _render_sections(doc: ReportDoc, project: dict, citations):
    table_index = 0
    for block in project.get("sections", []):
        block_type = block.get("type", "p")
        if block_type == "h1":
            doc.h1(block.get("text", ""))
        elif block_type == "h2":
            doc.h2(block.get("text", ""))
        elif block_type == "h3":
            doc.h3(block.get("text", ""))
        elif block_type == "pagebreak":
            doc.page_break()
        elif block_type == "caption":
            doc.caption(block.get("text", ""))
        elif block_type == "table":
            table_index += 1
            caption = block.get("caption") or f"表 {table_index}"
            doc.caption(caption)
            doc.table(block.get("headers", []), block.get("rows", []), block.get("widths"))
            if block.get("note"):
                doc.para(block["note"], size=9)
        else:
            doc.para(block.get("text", ""), citations=citations)

    # 概念分解表：项目里给了 concepts 但正文没手写表时，自动补一张
    if project.get("concepts") and not any(b.get("type") == "table" for b in project.get("sections", [])):
        concepts = concepts_from_json(project["concepts"])
        table = build_plan(concepts)["table"]
        doc.caption(table["caption"])
        doc.table(table["headers"], table["rows"], table["widths"])


def cmd_build(args):
    project = _read_json(args.project)
    references = refs_mod.parse_references(project.get("references", []))
    citations = refs_mod.CitationBook(references)

    doc = ReportDoc()
    doc.cover(project.get("title", ""), project.get("subtitle", ""),
              project.get("cover_meta", []), project.get("cover_date", ""))
    # cover() 内部已经分页，这里不再重复 page_break，否则会多一张空白页
    _render_sections(doc, project, citations)

    missing = citations.missing
    if missing:
        print(f"[错误] 正文引用了题录里没有的 key：{missing}")
        return 1
    doc.references(citations)
    doc.save(args.out)
    print(f"已生成：{args.out}")

    report = self_check(project, citations)
    print(report)
    return 0


def self_check(project: dict, citations) -> str:
    """规格自检：只报数，不下结论。"""
    text = ""
    for block in project.get("sections", []):
        if block.get("type") in ("p", "h1", "h2", "h3"):
            text += block.get("text", "")
    chinese = len([ch for ch in text if "\u4e00" <= ch <= "\u9fff"])
    cited = citations.cited_references()
    english = 0
    for reference in cited:
        if reference.kind == "standard":
            continue
        if reference.is_english():
            english += 1
    lines = [
        "",
        "【规格自检】",
        f"正文字符数（含标题）：{len(text)}，其中中文 {chinese} 字",
        f"参考文献：{len(cited)} 条（题录合计 {len(citations.references)} 条）",
        f"英文文献：{english} 条",
        f"未被引用的题录：{len(citations.uncited())} 条"
        + (f" → {[ref.key for ref in citations.uncited()]}" if citations.uncited() else ""),
    ]
    chapters = len([b for b in project.get("sections", []) if b.get("type") == "h1"])
    lines.append(f"一级标题：{chapters} 个")
    return "\n".join(lines)


def cmd_slides(args):
    project = _read_json(args.project)
    references = refs_mod.parse_references(project.get("references", []))
    citations = refs_mod.CitationBook(references)
    build_deck(project, citations, args.out)
    print(f"已生成：{args.out}")
    return 0


def cmd_all(args):
    code = cmd_verify(argparse.Namespace(refs=args.refs, cache=args.cache, delay=args.delay))
    if code not in (0, 2):
        return code
    project = _read_json(args.project)
    payload = _read_json(args.refs)
    project["references"] = payload.get("references", project.get("references", []))
    _write_json(args.project, project)
    build_code = cmd_build(argparse.Namespace(project=args.project, out=args.out))
    if build_code != 0:
        return build_code
    if args.deck:
        cmd_slides(argparse.Namespace(project=args.project, out=args.deck))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="litreport",
        description="文献检索报告的骨架生成器：概念分解、题录核验、docx、pptx。")
    sub = parser.add_subparsers(dest="command", required=True)

    new_parser = sub.add_parser("new", help="创建 project.json 与 refs.json 模板")
    new_parser.add_argument("--dir", required=True, help="输出目录")
    new_parser.add_argument("--title", default="", help="报告标题")
    new_parser.add_argument("--force", action="store_true", help="覆盖已存在的 project.json")
    new_parser.set_defaults(func=cmd_new)

    plan_parser = sub.add_parser("plan", help="生成概念分解表与检索式")
    plan_parser.add_argument("--project", required=True)
    plan_parser.set_defaults(func=cmd_plan)

    verify_parser = sub.add_parser("verify", help="用 Crossref 核验题录真实存在")
    verify_parser.add_argument("--refs", required=True)
    verify_parser.add_argument("--cache", default=".refs-cache.json", help="核验结果缓存路径")
    verify_parser.add_argument("--delay", type=float, default=0.2, help="每条之间的间隔秒数")
    verify_parser.set_defaults(func=cmd_verify)

    build_parser_ = sub.add_parser("build", help="生成 docx")
    build_parser_.add_argument("--project", required=True)
    build_parser_.add_argument("--out", required=True)
    build_parser_.set_defaults(func=cmd_build)

    slides_parser = sub.add_parser("slides", help="生成 pptx 骨架")
    slides_parser.add_argument("--project", required=True)
    slides_parser.add_argument("--out", required=True)
    slides_parser.set_defaults(func=cmd_slides)

    all_parser = sub.add_parser("all", help="核验 → 生成 docx →（可选）生成 pptx")
    all_parser.add_argument("--project", required=True)
    all_parser.add_argument("--refs", required=True)
    all_parser.add_argument("--out", required=True)
    all_parser.add_argument("--deck", default="", help="可选：pptx 输出路径")
    all_parser.add_argument("--cache", default=".refs-cache.json")
    all_parser.add_argument("--delay", type=float, default=0.2)
    all_parser.set_defaults(func=cmd_all)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
