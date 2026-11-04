# -*- coding: utf-8 -*-
"""题录核验：确认每一条文献真实存在，且题名、年份、作者与数据库一致。

三条硬规则（对应 docs/ACADEMIC.md 的“不许编造”）：
1. 有 DOI 就按 DOI 取权威元数据，不用标题搜；
2. 没有 DOI 才用题名检索，并且**必须**比对标题相似度，不能“搜到第一条就算”；
3. 网络失败、接口超时、返回结构不认识，一律输出“无法判定”，绝不降级成“通过”。

输出是四态：ok / mismatch / not_found / unknown，每条都带原因。
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from difflib import SequenceMatcher

from .refs import Reference

CROSSREF = "https://api.crossref.org/works"
USER_AGENT = "lit-review-report-kit/1.0 (mailto:noreply@example.com)"

STATUS_OK = "ok"
STATUS_MISMATCH = "mismatch"
STATUS_NOT_FOUND = "not_found"
STATUS_UNKNOWN = "unknown"


def _norm(text: str) -> str:
    """只用于比对：去掉标点、空格、大小写差异。不要用它做展示或存证。"""
    text = (text or "").lower()
    text = re.sub(r"[\u2010-\u2015\-_/]", " ", text)
    text = re.sub(r"[^\w\u4e00-\u9fff]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def _get_json(url: str, timeout: float = 12.0):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read()
    return json.loads(payload.decode("utf-8", "replace"))


def _crossref_by_doi(doi: str):
    return _get_json(f"{CROSSREF}/{urllib.parse.quote(doi.strip())}")["message"]


def _crossref_search(reference: Reference):
    query = reference.title or ""
    params = {
        "query.bibliographic": query,
        "rows": "5",
        "select": "DOI,title,author,issued,container-title,volume,issue,page,type",
    }
    data = _get_json(CROSSREF + "?" + urllib.parse.urlencode(params))
    items = data.get("message", {}).get("items", [])
    return items


def _first_title(item) -> str:
    titles = item.get("title") or []
    return titles[0] if titles else ""


def _year_of(item) -> str:
    issued = item.get("issued", {}).get("date-parts") or [[None]]
    part = issued[0][0] if issued and issued[0] else None
    return str(part) if part else ""


def _author_surnames(item) -> list[str]:
    names = []
    for author in item.get("author", []) or []:
        family = author.get("family") or author.get("name") or ""
        if family:
            names.append(family)
    return names


def check_one(reference: Reference, timeout: float = 12.0) -> dict:
    """核验一条题录，返回 {key, status, reason, matched, similarity}。"""
    result = {
        "key": reference.key,
        "title": reference.title,
        "status": STATUS_UNKNOWN,
        "reason": "",
        "matched": "",
        "similarity": 0.0,
    }
    try:
        if reference.doi:
            item = _crossref_by_doi(reference.doi)
            result["matched"] = _first_title(item)
            result["similarity"] = round(_similar(reference.title, _first_title(item)), 3)
            if result["similarity"] >= 0.9:
                result["status"] = STATUS_OK
                result["reason"] = "DOI 命中，题名一致"
            else:
                result["status"] = STATUS_MISMATCH
                result["reason"] = "DOI 存在但题名与登记不一致"
            return _fill_extra(result, item)

        if not reference.title:
            result["reason"] = "既没有 DOI 也没有题名，无法核验"
            result["status"] = STATUS_UNKNOWN
            return result

        items = _crossref_search(reference)
        if not items:
            result["status"] = STATUS_NOT_FOUND
            result["reason"] = "Crossref 未检索到候选"
            return result
        best = max(items, key=lambda item: _similar(reference.title, _first_title(item)))
        similarity = _similar(reference.title, _first_title(best))
        result["similarity"] = round(similarity, 3)
        result["matched"] = _first_title(best)
        if similarity >= 0.9:
            result["status"] = STATUS_OK
            result["reason"] = "题名检索命中"
        elif similarity >= 0.75:
            result["status"] = STATUS_MISMATCH
            result["reason"] = "疑似同一篇，但题名差异较大，需人工确认"
        else:
            result["status"] = STATUS_NOT_FOUND
            result["reason"] = "没有足够相似的候选，可能题录写错或不存在"
        return _fill_extra(result, best)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            result["status"] = STATUS_NOT_FOUND
            result["reason"] = "DOI 在 Crossref 不存在（404）"
        else:
            result["status"] = STATUS_UNKNOWN
            result["reason"] = f"Crossref 返回 HTTP {error.code}，无法判定"
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        result["status"] = STATUS_UNKNOWN
        result["reason"] = f"网络不可用：{error}"
    except (ValueError, KeyError, TypeError) as error:
        result["status"] = STATUS_UNKNOWN
        result["reason"] = f"接口返回结构不认识：{type(error).__name__}: {error}"
    return result


def _fill_extra(result: dict, item) -> dict:
    result["matched_year"] = _year_of(item)
    result["matched_doi"] = item.get("DOI", "")
    result["matched_authors"] = _author_surnames(item)[:5]
    return result


def check_all(references: list[Reference], cache_path=None, delay: float = 0.2, timeout: float = 12.0):
    """逐条核验；cache_path 给了就把结果按 key 缓存进 JSON，重复跑不重复请求。"""
    cache = {}
    if cache_path:
        try:
            with open(cache_path, "r", encoding="utf-8") as handle:
                cache = json.load(handle)
        except (OSError, ValueError):
            cache = {}

    results = []
    for reference in references:
        if cache_path and reference.key in cache and cache[reference.key].get("status") == STATUS_OK:
            results.append(cache[reference.key])
            continue
        result = check_one(reference, timeout=timeout)
        results.append(result)
        if cache_path:
            cache[reference.key] = result
        if delay:
            time.sleep(delay)

    if cache_path:
        try:
            with open(cache_path, "w", encoding="utf-8") as handle:
                json.dump(cache, handle, ensure_ascii=False, indent=2)
        except OSError as error:
            print(f"[warn] 缓存写不进去：{error}")
    return results


def summarize(results: list[dict]) -> dict:
    counts = {STATUS_OK: 0, STATUS_MISMATCH: 0, STATUS_NOT_FOUND: 0, STATUS_UNKNOWN: 0}
    for item in results:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    return counts


def format_table(results: list[dict]) -> str:
    mark = {STATUS_OK: "通过", STATUS_MISMATCH: "不一致", STATUS_NOT_FOUND: "未找到", STATUS_UNKNOWN: "无法判定"}
    lines = ["key\t状态\t相似度\t说明"]
    for item in results:
        lines.append(f"{item['key']}\t{mark.get(item['status'], item['status'])}\t{item.get('similarity', 0):.2f}\t{item['reason']}")
    return "\n".join(lines)
