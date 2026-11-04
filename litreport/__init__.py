# -*- coding: utf-8 -*-
"""lit-review-report-kit：文献检索报告的骨架生成器。

四个能力，各自独立、可以只用其中一两个：
- refs     题录模型与 GB/T 7714 顺序编码制
- search   概念分解 → CNKI / WoS / Crossref / arXiv 检索式
- verify   用 Crossref 核验题录是否真实存在（四态，不猜）
- docx_kit 按课程模板生成 docx（三线表、页脚页码、参考文献）
- slides   从报告摘出 pptx 骨架（不重写内容）

明确的边界（README 与 docs/ACADEMIC.md 都写了）：
本工具负责“检索式怎么写、题录是否真实、排版是否合规”，
不生成研究内容，不代替人读文献，也不替人下结论。
"""

__version__ = "1.0.0"

from .refs import Reference, CitationBook, parse_references  # noqa: F401

__all__ = ["Reference", "CitationBook", "parse_references", "__version__"]
