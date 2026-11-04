# lit-review-report-kit

把「写一篇科技文献检索报告」里**机械、可核验**的部分自动化：

1. 把课题拆成概念组，生成 CNKI / Web of Science / Crossref / arXiv 的检索式；
2. 用 Crossref 逐条核验题录**真实存在**（四态输出，不猜、不补全）；
3. 按常见课程模板生成 docx（A4、三线表、页脚页码、GB/T 7714 顺序编码制）；
4. 从报告摘一份 pptx 汇报骨架。

它**不写研究内容**，也**不替你读文献**。工具能保证的是「检索式合理、题录真实、排版合规」；
观点、分析、结论仍然要你自己写。

## 为什么做这个

检索报告的门槛不在写作，而在三件容易翻车的事：

- 概念没拆开，检索式写成一长串 AND，结果只有个位数；
- 题录从各处抄来，卷期页码对不上，甚至论文根本不存在；
- 排版每次重来：三线表、悬挂缩进、页脚页码。

这三件事都能被程序可靠地做掉，剩下的才是人该花时间的部分。

## 安装

```bash
python -m pip install -r requirements.txt
```

只依赖 `python-docx` 与 `python-pptx`。核验功能用标准库 `urllib` 访问 Crossref，不需要 API Key。

Python 3.9 及以上。

## 五分钟跑通

```bash
# 1. 建一个课题目录
python -m litreport new --dir my-report --title "我的课题"

# 2. 编辑 my-report/project.json：填 concepts（概念组）与 sections（正文）
#    编辑 my-report/refs.json：填题录

# 3. 生成检索式
python -m litreport plan --project my-report/project.json

# 4. 核验题录（联网）
python -m litreport verify --refs my-report/refs.json --cache my-report/.refs-cache.json

# 5. 生成 docx（会打印规格自检）
python -m litreport build --project my-report/project.json --out my-report/报告.docx

# 6. 可选：生成 pptx 骨架
python -m litreport slides --project my-report/project.json --out my-report/汇报.pptx
```

也可以直接跑自带示例：

```bash
cd examples/demo-llm-agent
python -m litreport plan --project project.json
python -m litreport build --project project.json --out 示例报告.docx
```

示例正文是虚构的，题录是真实存在的公开论文，`verify` 能核验通过。

## 题录核验怎么判

每条题录输出四种状态之一：

| 状态 | 含义 | 该怎么办 |
| --- | --- | --- |
| 通过 | 有 DOI 且题名一致，或题名检索相似度 ≥ 0.90 | 可以直接用 |
| 不一致 | 相似度 0.75–0.90，或 DOI 存在但题名不同 | 人工打开原文核对，多半是卷期或题名抄错 |
| 未找到 | 没有足够相似的候选，或 DOI 404 | 不要写进报告，除非你能给出别处可查的证据 |
| 无法判定 | 网络失败、接口超时、返回结构不认识 | 换个时间重跑；报告里注明核验方式 |

「无法判定」不等于「通过」。这是刻意的：宁可让你多查一次，也不让一条假文献混进去。

## 正文与引用

正文写在 `project.json` 的 `sections` 里，引用用 `{{key}}` 占位，例如：

```json
{ "type": "p", "text": "工具调用的关键变化在于模型输出可被程序执行{{yao2023react}}。" }
```

生成时按**首次引用顺序**编号为 `[1]`、`[2]`，文末只列被引用过的条目。
如果正文引用了题录里没有的 key，`build` 会直接报错退出，并列出缺哪些 key。

`sections` 支持的块类型：

| type | 作用 |
| --- | --- |
| `h1` / `h2` / `h3` | 一、二、三级标题 |
| `p` | 正文段落（支持 `{{key}}`） |
| `table` | 三线表，需要 `headers`、`rows`、可选 `widths`、`note` |
| `caption` | 单独一行图表题注 |
| `pagebreak` | 分页 |

## 规格自检

`build` 结束会打印：

```
【规格自检】
正文字符数（含标题）：1234，其中中文 987 字
参考文献：6 条（题录合计 8 条）
英文文献：4 条
未被引用的题录：2 条 → ['x2020', 'y2021']
一级标题：4 个
```

**工具只报数，不判合格**。课程要求是 3000 字还是 4000 字、英文文献要 8 篇还是 10 篇，各校不同，
请按你手上的模板核对。未被引用的题录默认不会出现在文末，这通常意味着「凑数文献」或漏引。

## 目录结构

```
litreport/
  refs.py       题录模型、GB/T 7714 著录、顺序编码
  search.py     概念分解与四库检索式
  verify.py     Crossref 核验（四态）
  docx_kit.py   docx 排版（三线表、页脚、悬挂缩进）
  slides.py     pptx 骨架
  cli.py        命令行入口
examples/
  demo-llm-agent/   可跑示例（虚构正文 + 真实题录）
docs/
  TEMPLATE.md   课程模板规格与版式参数
  ACADEMIC.md   学术边界：什么不能交给工具做
tools/
  verify_privacy.py  发布前隐私扫描
tests/
  smoke.py      端到端冒烟测试
```

## 隐私

生成的 docx / pptx 会把 `作者`、`最后修改人`、`公司` 这些元数据字段清空（python-docx / python-pptx 的默认值，
以及 Word 会记住的本机用户名，都属于不该随文件交出去的东西）。

上传或分享整个目录之前，可以先跑一遍扫描：

```bash
python tools/verify_privacy.py .
```

它逐文件扫路径、邮箱、IP、MAC、令牌、设备号，并读取 Office 文档的 `docProps` 元数据与 PDF 元数据；
命中即退出码 1，有文件没扫成（二进制、缺依赖、读不了）退出码 2——**「无法判定」不算通过**。
报告里不回显命中原文，只给打码片段。

## 边界（请务必读）

- **不生成研究内容**：它不会替你写“研究现状”“发展趋势”的实质判断；
- **不代替阅读**：摘要级信息不能支撑述评，工具只保证你引用的是真实文献；
- **核验有上限**：Crossref 覆盖期刊与会议论文较好，中文期刊、部分会议、标准文献覆盖有限，
  这类条目会落到「无法判定」，需要你用 CNKI / 标准委官网自行核对；
- **不保证格式通吃**：模板参数在 `docs/TEMPLATE.md` 里写死了，换学校就要改 `docx_kit.py`。

## 许可

MIT。示例中的论文题录版权归原作者，仅作引用示例。
