# -*- coding: utf-8 -*-
"""发布前隐私扫描：确认包里没有个人信息、设备信息、凭据。

用法：
    python tools/verify_privacy.py <目录> [--names 张三,李四] [--json out.json]

判定口径（三条，缺一不可）：
1. 逐文件扫文本，命中即为「不通过」，不给“可能是误报”的模糊出口；
2. 报告里**不回显命中的原文**，只给类型、文件、行号与打码片段，避免扫描报告本身成为泄露源；
3. 退出码：0 = 0 命中且全部扫过；1 = 有命中；2 = 有文件没扫成（读不了、类型不认识、缺依赖）。

Office 文档（.docx/.pptx/.xlsx）会额外读 `docProps/core.xml` 与 `app.xml`——
作者、最后修改人、单位这些字段常常是空的，但一旦有值，就是随文件一起交出去的真名。
PDF 用 pymupdf 读元数据；没装 pymupdf 时报「无法判定」，不假装通过。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import zipfile

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".pytest_cache", ".venv", "venv",
    "dist", "build", "out", ".idea", ".vscode",
}
TEXT_EXT = {
    ".py", ".md", ".json", ".txt", ".yml", ".yaml", ".toml", ".cfg", ".ini",
    ".html", ".css", ".js", ".ts", ".sh", ".ps1", ".bat", ".c", ".h", ".cpp",
}
TEXT_NAMES = {
    "license", "licence", "copying", "readme", "makefile", "changelog",
    ".gitignore", ".gitattributes", ".editorconfig", ".npmignore",
}
OFFICE_EXT = {".docx", ".pptx", ".xlsx"}

# 允许出现的“看起来像路径”的示例
ALLOW_SUBSTRINGS = (
    "C:\\path\\to\\", "/path/to/", "<你的路径>", "example.com", "noreply@example.com",
    "199.999.999", "192.0.2.", "127.0.0.1",
)

PATTERNS = [
    ("windows_user_path", re.compile(r"[A-Za-z]:\\\\?Users\\\\?[^\\\s\"']+")),
    ("unix_home_path", re.compile(r"/(?:home|Users)/([A-Za-z0-9._-]{2,})")),
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("ipv4", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("mac_address", re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("api_key_sk", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("device_id", re.compile(r"\b[0-9A-F]{16,}\b")),
]

# 这些是软件名而不是人，出现在 PDF 元数据里属正常
TOOL_NAMES = ("Word", "PowerPoint", "Excel", "LibreOffice", "Acrobat", "PyMuPDF", "MuPDF", "Microsoft", "Python")


def mask(value: str) -> str:
    value = value.strip()
    if len(value) <= 4:
        return "*" * len(value)
    return value[:2] + "*" * min(len(value) - 4, 8) + value[-2:]


def iter_files(root):
    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            yield os.path.join(current, name)


def is_text_file(path: str) -> bool:
    extension = os.path.splitext(path)[1].lower()
    if extension in TEXT_EXT:
        return True
    return extension == "" and os.path.basename(path).lower() in TEXT_NAMES


def scan_text(path, names):
    hits = []
    try:
        size = os.path.getsize(path)
        if size > 2 * 1024 * 1024:
            return hits, [f"文件过大（{size} 字节），未扫描"]
        with open(path, "r", encoding="utf-8", errors="strict") as handle:
            lines = handle.read().splitlines()
    except (OSError, UnicodeDecodeError) as error:
        return hits, [f"读不了：{type(error).__name__}"]

    for number, line in enumerate(lines, start=1):
        if any(allowed in line for allowed in ALLOW_SUBSTRINGS):
            continue
        for kind, pattern in PATTERNS:
            for match in pattern.finditer(line):
                value = match.group(0)
                if kind == "ipv4":
                    octets = value.split(".")
                    if not all(part.isdigit() and 0 <= int(part) <= 255 for part in octets):
                        continue
                    if value.startswith(("127.", "192.0.2.", "0.0.0.0")):
                        continue
                if kind == "device_id" and not re.search(r"[A-Fa-f]", value):
                    continue
                hits.append({"kind": kind, "file": path, "line": number, "sample": mask(value)})
        for name in names:
            if name and name in line:
                hits.append({"kind": "personal_name", "file": path, "line": number, "sample": mask(name)})
    return hits, []


def scan_office(path):
    hits, skipped = [], []
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            for part, tags in (
                ("docProps/core.xml", (("dc:creator", "office_author"), ("cp:lastModifiedBy", "office_author"))),
                ("docProps/app.xml", (("Company", "office_company"), ("Manager", "office_manager"))),
            ):
                if part not in names:
                    continue
                text = archive.read(part).decode("utf-8", "replace")
                for tag, kind in tags:
                    for match in re.finditer(rf"<{tag}>([^<]*)</{tag}>", text):
                        value = match.group(1).strip()
                        if value:
                            hits.append({"kind": kind, "file": path, "line": 0, "sample": mask(value)})
    except (OSError, zipfile.BadZipFile, KeyError) as error:
        skipped.append(f"打不开：{type(error).__name__}")
    return hits, skipped


def scan_pdf(path):
    try:
        import pymupdf  # noqa: F401
    except ImportError:
        return [], ["没装 pymupdf，无法读取 PDF 元数据"]
    try:
        document = pymupdf.open(path)
        meta = document.metadata or {}
        document.close()
    except Exception as error:  # noqa: BLE001 - 任何解析失败都算“无法判定”
        return [], [f"读不了：{type(error).__name__}"]
    hits = []
    for key in ("author", "creator", "producer", "title", "subject", "keywords"):
        value = (meta.get(key) or "").strip()
        if not value:
            continue
        if key in ("creator", "producer") and any(tool in value for tool in TOOL_NAMES):
            continue
        hits.append({"kind": f"pdf_{key}", "file": path, "line": 0, "sample": mask(value)})
    return hits, []


def scan_file(path, names):
    extension = os.path.splitext(path)[1].lower()
    if is_text_file(path):
        return scan_text(path, names)
    if extension in OFFICE_EXT:
        return scan_office(path)
    if extension == ".pdf":
        return scan_pdf(path)
    return [], ["二进制或未收录的扩展名，未扫描"]


def main(argv=None):
    parser = argparse.ArgumentParser(description="发布前隐私扫描")
    parser.add_argument("root", help="要扫描的目录")
    parser.add_argument("--names", default="", help="额外要检查的姓名/单位，逗号分隔")
    parser.add_argument("--json", default="", help="把结果写成 JSON")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.root):
        print(f"[无法判定] 不是一个目录：{args.root}")
        return 2

    names = [item.strip() for item in args.names.split(",") if item.strip()]
    hits, skipped, scanned = [], [], 0
    for path in iter_files(args.root):
        file_hits, file_skips = scan_file(path, names)
        scanned += 1
        hits.extend(file_hits)
        for reason in file_skips:
            skipped.append({"file": path, "reason": reason})

    for hit in hits:
        print(f"{hit['kind']}\t{hit['file']}:{hit['line']}\t{hit['sample']}")
    for item in skipped:
        print(f"[无法判定]\t{item['file']}\t{item['reason']}")

    print("")
    print(f"扫描文件 {scanned} 个，命中 {len(hits)} 处，无法判定 {len(skipped)} 处。")
    if hits:
        print("结论：不通过。上面的命中必须逐个确认并清除。")
    elif skipped:
        print("结论：没有命中，但有文件未扫描——请人工确认这些文件，不能当作通过。")
    else:
        print("结论：通过（0 命中，全部文件已扫描）。")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump({"scanned": scanned, "hits": hits, "skipped": skipped}, handle, ensure_ascii=False, indent=2)
        print(f"明细已写入：{args.json}")

    if hits:
        return 1
    if skipped:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
