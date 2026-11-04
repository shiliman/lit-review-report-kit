# -*- coding: utf-8 -*-
"""把报告压成一份汇报用 PPT 骨架。

原则：PPT 不重写正文，只从报告里**摘**——每章一页，要点取该章的小标题与首句，
避免“用同一段话生成两套内容”时出现的口径不一致。

版面故意做得素：16:9 白底、左侧一条深蓝竖条、标题左对齐、正文用项目符号，
不加渐变、不加居中大字、不加装饰图标。
"""

from __future__ import annotations

import re

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

from .refs import CITATION

INK = RGBColor(0x1A, 0x1A, 0x1A)
MUTED = RGBColor(0x59, 0x59, 0x59)
ACCENT = RGBColor(0x1F, 0x4E, 0x79)
LIGHT = RGBColor(0xFF, 0xFF, 0xFF)
FONT = "微软雅黑"


def _font(run, size=18, bold=False, color=INK):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = FONT
    rpr = run._r.get_or_add_rPr()
    ea = rpr.find("{http://schemas.openxmlformats.org/drawingml/2006/main}ea")
    if ea is None:
        from lxml import etree
        ea = etree.SubElement(rpr, "{http://schemas.openxmlformats.org/drawingml/2006/main}ea")
    ea.set("typeface", FONT)


def _textbox(slide, left, top, width, height):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    frame = box.text_frame
    frame.word_wrap = True
    return frame


def _first_sentences(text: str, limit=2, max_chars=110) -> list[str]:
    parts = re.split(r"(?<=[。！？；])", text or "")
    picked, total = [], 0
    for part in parts:
        sentence = part.strip()
        if not sentence:
            continue
        if total + len(sentence) > max_chars * limit and picked:
            break
        picked.append(sentence)
        total += len(sentence)
        if len(picked) >= limit:
            break
    return picked


def _sections_of(project: dict) -> list[dict]:
    """按 h1 把 sections 切成章，章内保留 h2 标题与首段。"""
    chapters, current = [], None
    for block in project.get("sections", []):
        block_type = block.get("type", "p")
        if block_type == "h1":
            current = {"title": block.get("text", ""), "subs": [], "lead": ""}
            chapters.append(current)
        elif current is None:
            continue
        elif block_type == "h2":
            current["subs"].append(block.get("text", ""))
        elif block_type == "p" and not current["lead"]:
            current["lead"] = block.get("text", "")
    return chapters


def _page_no(slide, prs):
    frame = _textbox(slide, 12.1, 6.95, 0.9, 0.35)
    paragraph = frame.paragraphs[0]
    paragraph.alignment = PP_ALIGN.RIGHT
    run = paragraph.add_run()
    run.text = str(len(prs.slides))
    _font(run, size=11, color=MUTED)


def _cover(prs, project):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bar = slide.shapes.add_shape(1, Inches(0), Inches(0), Inches(0.22), prs.slide_height)
    bar.fill.solid()
    bar.fill.fore_color.rgb = ACCENT
    bar.line.fill.background()
    frame = _textbox(slide, 1.1, 2.1, 11.0, 1.4)
    paragraph = frame.paragraphs[0]
    run = paragraph.add_run()
    run.text = project.get("title", "文献检索报告")
    _font(run, size=40, bold=True)
    if project.get("subtitle"):
        frame2 = _textbox(slide, 1.1, 3.5, 11.0, 0.8)
        run = frame2.paragraphs[0].add_run()
        run.text = project["subtitle"]
        _font(run, size=18, color=MUTED)
    frame3 = _textbox(slide, 1.1, 5.9, 11.0, 0.6)
    run = frame3.paragraphs[0].add_run()
    run.text = project.get("cover_date", "")
    _font(run, size=14, color=MUTED)


def _bullets_slide(prs, title, bullets, kicker=""):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bar = slide.shapes.add_shape(1, Inches(0), Inches(0), Inches(0.14), prs.slide_height)
    bar.fill.solid()
    bar.fill.fore_color.rgb = ACCENT
    bar.line.fill.background()
    frame = _textbox(slide, 0.9, 0.55, 11.8, 1.0)
    run = frame.paragraphs[0].add_run()
    run.text = title
    _font(run, size=28, bold=True)
    if kicker:
        frame0 = _textbox(slide, 0.9, 1.45, 11.8, 0.5)
        run = frame0.paragraphs[0].add_run()
        run.text = kicker
        _font(run, size=12, color=MUTED)
    body = _textbox(slide, 0.95, 1.95, 11.6, 4.9)
    for index, bullet in enumerate(bullets):
        paragraph = body.paragraphs[0] if index == 0 else body.add_paragraph()
        paragraph.space_after = Pt(14)
        paragraph.line_spacing = 1.25
        run = paragraph.add_run()
        run.text = "· " + bullet
        _font(run, size=16)
    _page_no(slide, prs)


def _table_slide(prs, caption, headers, rows, widths=None):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bar = slide.shapes.add_shape(1, Inches(0), Inches(0), Inches(0.14), prs.slide_height)
    bar.fill.solid()
    bar.fill.fore_color.rgb = ACCENT
    bar.line.fill.background()
    frame = _textbox(slide, 0.9, 0.55, 11.8, 0.9)
    run = frame.paragraphs[0].add_run()
    run.text = caption
    _font(run, size=24, bold=True)
    columns = len(headers)
    row_height = 0.52
    table = slide.shapes.add_table(len(rows) + 1, columns, Inches(0.9), Inches(1.65),
                                   Inches(11.5), Inches(row_height * (len(rows) + 1))).table
    table.rows[0].height = Inches(row_height + 0.06)
    total = sum(widths) if widths else columns
    for index, (header, width) in enumerate(zip(headers, widths or [1] * columns)):
        cell = table.cell(0, index)
        cell.text = header
        cell.fill.solid()
        cell.fill.fore_color.rgb = ACCENT
        for paragraph in cell.text_frame.paragraphs:
            for run in paragraph.runs:
                _font(run, size=14, bold=True, color=LIGHT)
            paragraph.alignment = PP_ALIGN.CENTER
        cell.width = Inches(11.5 * width / total)
    for row_index, row in enumerate(rows, start=1):
        table.rows[row_index].height = Inches(row_height)
        for column_index, value in enumerate(row):
            cell = table.cell(row_index, column_index)
            cell.text = str(value)
            cell.fill.solid()
            cell.fill.fore_color.rgb = RGBColor(0xF4, 0xF6, 0xFA) if row_index % 2 else LIGHT
            for paragraph in cell.text_frame.paragraphs:
                for run in paragraph.runs:
                    _font(run, size=12)
    _page_no(slide, prs)


def build_deck(project: dict, citations, output_path):
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    # 先按正文顺序把引用“走”一遍，否则文末文献页会是空的
    if citations is not None:
        for block in project.get("sections", []):
            text = block.get("text", "")
            if not text:
                continue
            for match in CITATION.finditer(text):
                citations.cite(match.group(1))

    _cover(prs, project)

    chapters = _sections_of(project)
    outline = [chapter["title"] for chapter in chapters][:6] or ["课题分析", "检索过程", "结果分析"]
    _bullets_slide(prs, "汇报提纲", outline)

    for chapter in chapters:
        bullets = []
        for sub in chapter["subs"][:4]:
            bullets.append(sub)
        for sentence in _first_sentences(chapter["lead"]):
            bullets.append(sentence)
        if not bullets:
            bullets = ["（本章内容见报告正文）"]
        _bullets_slide(prs, chapter["title"], bullets[:5])

    for block in project.get("sections", []):
        if block.get("type") == "table" and block.get("caption"):
            _table_slide(prs, block["caption"], block["headers"], block["rows"][:6], block.get("widths"))
            break

    if citations is not None:
        refs = citations.cited_references()[:8]
        if refs:
            _bullets_slide(prs, "主要参考文献",
                           [ref.format()[:88] + ("…" if len(ref.format()) > 88 else "") for ref in refs])

    # 元数据清空，避免把本机用户名/单位带进交付件
    props = prs.core_properties
    props.author = ""
    props.last_modified_by = ""
    props.comments = ""
    props.subject = ""
    props.keywords = ""
    props.category = ""
    prs.save(output_path)
    return output_path
