# -*- coding: utf-8 -*-
"""Word 排版工具：按中文课程报告的常见模板生成 docx。

为什么不用现成的模板文件：模板样式一改就要重新对，而这里所有字号、行距、
缩进都写在代码里，改一行就能复现；同时避免把某个学校的模板文件带进仓库。

约定（与 docs/TEMPLATE.md 一致）：
- A4，上下 2.54 cm，左右 3.175 cm；
- 正文小四（12 pt）、1.25 倍行距、首行缩进 2 字符；
- 标题黑体：一级 18 pt、二级 15 pt、三级 14 pt；
- 三线表：顶线与底线 1.5 磅、内部横线 0.75 磅、无竖线；
- 页脚居中页码。
"""

from __future__ import annotations

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from .refs import CITATION, CitationBook

CN, HEI, EN, KAI = "宋体", "黑体", "Times New Roman", "楷体"
INK = RGBColor(0x1A, 0x1A, 0x1A)
GREY = RGBColor(0x59, 0x59, 0x59)
ACCENT = RGBColor(0x1F, 0x4E, 0x79)


def _set_font(run, cn=CN, en=EN, size=12, bold=False, color=INK):
    run.font.name = en
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), cn)


def _borders(table, inner_size=6, color="000000"):
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "bottom"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "12")
        el.set(qn("w:color"), color)
        borders.append(el)
    el = OxmlElement("w:insideH")
    el.set(qn("w:val"), "single")
    el.set(qn("w:sz"), str(inner_size))
    el.set(qn("w:color"), color)
    borders.append(el)
    for edge in ("left", "right", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "none")
        borders.append(el)
    table._tbl.tblPr.append(borders)


def _fixed_widths(table, widths):
    tbl = table._tbl
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tbl.tblPr.append(layout)
    total = OxmlElement("w:tblW")
    total.set(qn("w:type"), "dxa")
    total.set(qn("w:w"), str(int(sum(widths) * 567)))
    tbl.tblPr.append(total)
    grid = tbl.find(qn("w:tblGrid"))
    if grid is not None:
        for col, width in zip(grid.findall(qn("w:gridCol")), widths):
            col.set(qn("w:w"), str(int(width * 567)))
    for row in table.rows:
        for cell, width in zip(row.cells, widths):
            cell.width = Cm(width)


def _add_page_field(paragraph):
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instr)
    run._r.append(end)
    _set_font(run, cn=CN, size=9, color=GREY)


class ReportDoc:
    """一份报告文档。所有 add_* 方法都立刻写入 docx 文档树。"""

    def __init__(self, line_spacing=1.25, body_size=12):
        self.body_size = body_size
        self.doc = Document()
        section = self.doc.sections[0]
        section.page_width, section.page_height = Cm(21.0), Cm(29.7)
        section.top_margin = section.bottom_margin = Cm(2.54)
        section.left_margin = section.right_margin = Cm(3.175)

        normal = self.doc.styles["Normal"]
        normal.font.name = EN
        normal.font.size = Pt(body_size)
        normal.element.rPr.rFonts.set(qn("w:eastAsia"), CN)
        normal.paragraph_format.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
        normal.paragraph_format.line_spacing = line_spacing
        normal.paragraph_format.space_after = Pt(0)

        # 页脚不在构造时创建：有封面时封面那节不该有页码，
        # 由 cover() 分节、或 save() 兜底再加。
        self._footer_ready = False

    # ------------------------------------------------------------- 基础排版
    def rich(self, paragraph, text, size=None, cn=CN, bold=False, color=INK, citations=None):
        """写入一段可能含 {{key}} 引用的文字。citations 为 CitationBook 时替换成 [n]。"""
        size = size or self.body_size
        pos = 0
        for match in CITATION.finditer(text):
            if match.start() > pos:
                _set_font(paragraph.add_run(text[pos:match.start()]), cn=cn, size=size, bold=bold, color=color)
            raw = match.group(1)
            label = citations.cite(raw) if citations else "[" + raw + "]"
            _set_font(paragraph.add_run(label), cn=cn, size=size, bold=bold, color=color)
            pos = match.end()
        if pos < len(text):
            _set_font(paragraph.add_run(text[pos:]), cn=cn, size=size, bold=bold, color=color)

    def para(self, text="", size=None, bold=False, cn=CN, color=INK, align="both",
             indent=True, before=0, after=0, spacing=None, keep=False, citations=None):
        paragraph = self.doc.add_paragraph()
        fmt = paragraph.paragraph_format
        fmt.alignment = {
            "left": WD_ALIGN_PARAGRAPH.LEFT,
            "center": WD_ALIGN_PARAGRAPH.CENTER,
            "right": WD_ALIGN_PARAGRAPH.RIGHT,
            "both": WD_ALIGN_PARAGRAPH.JUSTIFY,
        }[align]
        fmt.space_before = Pt(before)
        fmt.space_after = Pt(after)
        if spacing:
            fmt.line_spacing = spacing
        if keep:
            fmt.keep_with_next = True
        size = size or self.body_size
        if indent:
            fmt.first_line_indent = Pt(size * 2)
        if text:
            self.rich(paragraph, text, size=size, cn=cn, bold=bold, color=color, citations=citations)
        return paragraph

    def title(self, text, size=22, after=16):
        return self.para(text, size=size, bold=True, cn=HEI, align="center",
                         indent=False, after=after, spacing=1.3)

    def h1(self, text):
        return self.para(text, size=18, bold=True, cn=HEI, align="left",
                         indent=False, before=12, after=6, spacing=1.3, keep=True)

    def h2(self, text):
        return self.para(text, size=15, bold=True, cn=HEI, align="left",
                         indent=False, before=9, after=5, spacing=1.3, keep=True)

    def h3(self, text):
        return self.para(text, size=14, bold=True, cn=HEI, align="left",
                         indent=False, before=7, after=4, spacing=1.3, keep=True)

    def caption(self, text, before=8):
        return self.para(text, size=10.5, bold=True, cn=HEI, align="center",
                         indent=False, before=before, after=3, spacing=1.1, keep=True)

    def page_break(self):
        self.doc.add_page_break()

    # --------------------------------------------------------------- 表格
    def _cell(self, cell, text, bold=False, size=9.5, align="left", citations=None):
        cell.text = ""
        paragraph = cell.paragraphs[0]
        fmt = paragraph.paragraph_format
        fmt.space_before = Pt(1.5)
        fmt.space_after = Pt(1.5)
        fmt.line_spacing = 1.0
        fmt.first_line_indent = None
        fmt.alignment = {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER}[align]
        self.rich(paragraph, text, size=size, bold=bold, citations=citations)

    def table(self, headers, rows, widths, size=9.5, aligns=None, note=None,
              keep_together=True, citations=None):
        table = self.doc.add_table(rows=1, cols=len(headers))
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = False
        _borders(table)
        aligns = aligns or ["left"] * len(headers)
        header = table.rows[0]
        for cell, text in zip(header.cells, headers):
            self._cell(cell, text, bold=True, size=size, align="center", citations=citations)
        for data in rows:
            row = table.add_row()
            for cell, text, align in zip(row.cells, data, aligns):
                self._cell(cell, text, size=size, align=align, citations=citations)
        for row in table.rows:
            props = row._tr.get_or_add_trPr()
            cant = OxmlElement("w:cantSplit")
            cant.set(qn("w:val"), "true")
            props.append(cant)
        header_props = header._tr.get_or_add_trPr()
        repeat = OxmlElement("w:tblHeader")
        repeat.set(qn("w:val"), "true")
        header_props.append(repeat)
        _fixed_widths(table, widths)
        if keep_together:
            for row in table.rows[:-1]:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        paragraph.paragraph_format.keep_with_next = True
        if note:
            self.para(note, size=9, color=GREY, indent=False, before=3, after=6, spacing=1.1)
        else:
            self.para("", size=6, indent=False, after=4)
        return table

    # ----------------------------------------------------------- 封面与文献
    def cover(self, title, subtitle="", meta=None, date_text=""):
        """封面。写完封面会新开一节，正文页码从 1 重新起算。"""
        if isinstance(meta, dict):
            entries = list(meta.items())
        elif isinstance(meta, (list, tuple)):
            entries = []
            for item in meta:
                text = str(item)
                if "：" in text:
                    label, value = text.split("：", 1)
                elif ":" in text:
                    label, value = text.split(":", 1)
                else:
                    label, value = text, ""
                entries.append((label.strip(), value.strip()))
        else:
            entries = []

        self.para("", size=self.body_size, indent=False, after=40)
        self.para(title, size=22, bold=True, cn=HEI, align="center", indent=False, after=20, spacing=1.5)
        if subtitle:
            self.para(subtitle, size=14, align="center", indent=False, after=60, spacing=1.4)
        else:
            self.para("", size=14, indent=False, after=60)
        for label, value in entries:
            paragraph = self.doc.add_paragraph()
            fmt = paragraph.paragraph_format
            fmt.alignment = WD_ALIGN_PARAGRAPH.CENTER
            fmt.space_before = Pt(0)
            fmt.space_after = Pt(14)
            fmt.line_spacing = 1.0
            run = paragraph.add_run(f"{label}：")
            _set_font(run, cn=KAI, size=14, bold=True)
            run = paragraph.add_run(value if value else "\u00a0" * 12)
            _set_font(run, cn=KAI, size=14, bold=bool(value))
            if not value:
                run.font.underline = True
        if date_text:
            self.para(date_text, size=14, cn=KAI, align="center", indent=False, before=40)
        self._start_body_section()

    def _start_body_section(self):
        """封面之后另起一节：正文页码从 1 开始，封面不显示页码。"""
        section = self.doc.add_section(WD_SECTION.NEW_PAGE)
        section.page_width, section.page_height = Cm(21.0), Cm(29.7)
        section.top_margin = section.bottom_margin = Cm(2.54)
        section.left_margin = section.right_margin = Cm(3.175)
        footer = section.footer
        footer.is_linked_to_previous = False
        paragraph = footer.paragraphs[0]
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for child in list(paragraph._p):
            paragraph._p.remove(child)
        _add_page_field(paragraph)
        sect_pr = section._sectPr
        for old in sect_pr.findall(qn("w:pgNumType")):
            sect_pr.remove(old)
        pg_num = OxmlElement("w:pgNumType")
        pg_num.set(qn("w:start"), "1")
        sect_pr.append(pg_num)
        self._footer_ready = True

    def _ensure_footer(self):
        if self._footer_ready:
            return
        section = self.doc.sections[0]
        footer = section.footer
        footer.is_linked_to_previous = False
        paragraph = footer.paragraphs[0]
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for child in list(paragraph._p):
            paragraph._p.remove(child)
        _add_page_field(paragraph)
        self._footer_ready = True

    def references(self, citations: CitationBook, heading="参考文献"):
        """按首次引用顺序输出文末文献表。未引用的条目不输出。"""
        self.h1(heading)
        for index, ref in enumerate(citations.cited_references(), start=1):
            paragraph = self.doc.add_paragraph()
            fmt = paragraph.paragraph_format
            fmt.alignment = WD_ALIGN_PARAGRAPH.LEFT
            fmt.left_indent = Cm(0.85)
            fmt.first_line_indent = Cm(-0.85)
            fmt.space_before = Pt(0)
            fmt.space_after = Pt(3)
            fmt.line_spacing = 1.15
            _set_font(paragraph.add_run(f"[{index}] "), cn=CN, size=10.5)
            _set_font(paragraph.add_run(ref.format()), cn=CN, size=10.5)

    def save(self, path):
        self._ensure_footer()
        # 元数据清空：作者名会随文档一起交出去，默认值（或 Word 记住的本机用户名）都算泄露
        props = self.doc.core_properties
        props.author = ""
        props.last_modified_by = ""
        props.comments = ""
        props.subject = ""
        props.keywords = ""
        props.category = ""
        self.doc.save(path)
        return path
