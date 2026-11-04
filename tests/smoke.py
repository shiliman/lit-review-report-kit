# -*- coding: utf-8 -*-
"""端到端冒烟测试：不联网，验证 new → plan → build → slides 能跑通。

跑法：
    python tests/smoke.py

断言的是「产物存在且非空」，不是「内容好看」。格式类的回归靠 examples 里的示例人工看，
这里只保证链路不炸、接口不漂。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO = os.path.join(ROOT, "examples", "demo-llm-agent")
PY = sys.executable


def run(args, cwd=ROOT):
    result = subprocess.run([PY, "-m", "litreport"] + args, cwd=cwd,
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    return result


def check(condition, message):
    if not condition:
        print(f"[FAIL] {message}")
        raise SystemExit(1)
    print(f"[ok] {message}")


def main():
    workdir = tempfile.mkdtemp(prefix="litreport-smoke-")
    try:
        # 1. new
        result = run(["new", "--dir", workdir, "--title", "冒烟测试"])
        check(result.returncode == 0, f"new 退出码为 0（stderr: {result.stderr.strip()[:200]}）")
        project_path = os.path.join(workdir, "project.json")
        refs_path = os.path.join(workdir, "refs.json")
        check(os.path.exists(project_path) and os.path.exists(refs_path), "new 生成了 project.json 与 refs.json")

        # 2. plan（用示例的概念组）
        with open(os.path.join(DEMO, "project.json"), "r", encoding="utf-8") as handle:
            demo = json.load(handle)
        with open(project_path, "r", encoding="utf-8") as handle:
            project = json.load(handle)
        project["concepts"] = demo["concepts"]
        with open(project_path, "w", encoding="utf-8") as handle:
            json.dump(project, handle, ensure_ascii=False, indent=2)

        result = run(["plan", "--project", project_path])
        check(result.returncode == 0, "plan 退出码为 0")
        check("概念分解表" in result.stdout and "CNKI" in result.stdout, "plan 输出了概念表与检索式")

        # 3. build（用示例的正文与题录）
        project = demo
        project["title"] = "冒烟测试报告"
        with open(project_path, "w", encoding="utf-8") as handle:
            json.dump(project, handle, ensure_ascii=False, indent=2)
        out_docx = os.path.join(workdir, "报告.docx")
        result = run(["build", "--project", project_path, "--out", out_docx])
        check(result.returncode == 0, f"build 退出码为 0（stderr: {result.stderr.strip()[:300]}）")
        check(os.path.getsize(out_docx) > 20000, "docx 已生成且体积正常")
        check("规格自检" in result.stdout, "build 打印了规格自检")

        # 4. slides
        out_pptx = os.path.join(workdir, "汇报.pptx")
        result = run(["slides", "--project", project_path, "--out", out_pptx])
        check(result.returncode == 0, f"slides 退出码为 0（stderr: {result.stderr.strip()[:300]}）")
        check(os.path.getsize(out_pptx) > 20000, "pptx 已生成且体积正常")

        # 5. 负例：引用了不存在的 key 必须失败，不能静默通过
        broken = dict(project)
        broken["sections"] = [{"type": "p", "text": "引用一个不存在的条目{{no_such_key}}。"}]
        with open(project_path, "w", encoding="utf-8") as handle:
            json.dump(broken, handle, ensure_ascii=False, indent=2)
        result = run(["build", "--project", project_path, "--out", os.path.join(workdir, "bad.docx")])
        check(result.returncode != 0, "引用缺失 key 时 build 退出码非 0（负例）")

        print("\n全部通过。")
        return 0
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
