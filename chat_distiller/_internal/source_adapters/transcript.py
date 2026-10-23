"""Shared deterministic text cleaning and staging contract."""
import json
import os
import re
from datetime import datetime, timezone, timedelta

CN_TZ = timezone(timedelta(hours=8))


SYSTEM_BLOCK_TAGS = [
    "system-reminder", "retained_skills", "artifact_reload", "tool_search_remind",
    "installed-skills", "current-state", "account-state", "connector-usage",
    "project-directories", "agent-workspace", "user-preferences",
    "current-user-location", "os-and-device", "current-date",
    "permission-and-authorization", "usage_guide",
]


SUMMARY_SECTIONS = [
    "TASK_FOCUS", "TASK_GOAL", "TASK_NARRATIVE", "KEY_FACTS_AND_IDS",
    "ARTIFACTS", "REFERENCED_IMAGES", "SKILLS_LOADED",
    "SKILLS_LOADED_RECALL_CONTRACT", "OPEN_ITEMS_AND_RESUME_NOTES",
]


def strip_system_blocks(text: str) -> str:
    """移除成对系统标签块（含其内容），DOTALL 跨行。"""
    for tag in SYSTEM_BLOCK_TAGS:
        text = re.sub(rf"<{re.escape(tag)}\b.*?</{re.escape(tag)}>",
                      "", text, flags=re.DOTALL | re.IGNORECASE)
        # 极少数只有开标签没有闭标签的情况：只删掉开标签本身，其后正文原样保留
        text = re.sub(rf"<{re.escape(tag)}\b[^>]*>", "", text, flags=re.IGNORECASE)
    return text


def strip_summary_sections(text: str) -> str:
    """移除 === SECTION === 形式的压缩摘要段（从该标题到下一个 === 标题或文本末尾）。"""
    names = "|".join(re.escape(n) for n in SUMMARY_SECTIONS)
    # 匹配「=== 名字 ===」开头，直到下一个「=== 任意 ===」标题或字符串结尾
    pattern = rf"===\s*(?:{names})\s*===.*?(?====\s*[A-Z_]+\s*===|\Z)"
    return re.sub(pattern, "", text, flags=re.DOTALL)


def clean_text(text) -> str:
    """把任意 content 规整为干净文本。content 可能是 str、None 或多模态分段 list。"""
    if text is None:
        return ""
    if isinstance(text, list):  # 多模态：只拼 type=text 的段
        parts = []
        for seg in text:
            if isinstance(seg, dict) and seg.get("type") == "text":
                parts.append(seg.get("text", ""))
            elif isinstance(seg, str):
                parts.append(seg)
        text = "\n".join(parts)
    if not isinstance(text, str):
        text = str(text)
    text = strip_system_blocks(text)
    text = strip_summary_sections(text)
    text = re.sub(r"<think[^>]*>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)  # 折叠多余空行
    return text.strip()


def iso_to_cn(iso: str):
    """ISO(UTC) -> (datetime, 'YYYY-MM-DD HH:MM' 北京时间)。失败返回 (None, 原串)。"""
    if not iso:
        return None, ""
    m = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", iso)
    if not m:
        return None, iso
    try:
        dt = datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        cn = dt.astimezone(CN_TZ)
        return cn, cn.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return None, iso


def slug_preview(text: str, n: int = 120) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    return t[:n]


def build_transcript(session_id, created_cn, updated_cn, turns, replies, tool_trail,
                     agent_ids, bad_lines, rel_source, degraded):
    L = []
    L.append("---")
    L.append(f"session_id: {session_id}")
    L.append(f"created: {created_cn or ''}")
    L.append(f"updated: {updated_cn or ''}")
    L.append(f"user_turns: {len(turns)}")
    L.append(f"assistant_replies: {len(replies)}")
    L.append(f"agents: {json.dumps(agent_ids, ensure_ascii=False)}")
    L.append("extracted_by: chat-distiller/extract_sessions")
    L.append("---")
    L.append("")
    L.append(f"# 会话 {session_id} · 干净转录")
    L.append("")
    L.append(f"> 时间：{created_cn or '未知'} → {updated_cn or '未知'}（北京时间）  |  "
             f"用户 {len(turns)} 轮 / 助手关键回复 {len(replies)} 条  |  来源：`{rel_source}`")
    L.append("")
    if degraded:
        L.append("> [!warning] 提取降级（浓缩时请留意）")
        for d in degraded:
            L.append(f"> - {d}")
        L.append("")
    L.append("## 一、用户需求时间线")
    L.append("")
    if turns:
        for i, (_, cn, body) in enumerate(turns, 1):
            L.append(f"### 轮次 {i}" + (f" · {cn}" if cn else ""))
            L.append("")
            L.append(body)
            L.append("")
    else:
        L.append("_（未提取到用户需求：assignment.md 缺失，且 trajectory 中没有可用的 user 文本）_")
        L.append("")
    L.append("## 二、助手关键回复（结论与产出）")
    L.append("")
    if replies:
        for i, r in enumerate(replies, 1):
            L.append(f"### 回复 {i}")
            L.append("")
            L.append(r)
            L.append("")
    else:
        L.append("_（无纯文本回复，可能是纯工具执行会话）_")
        L.append("")
    if tool_trail:
        L.append("## 三、操作轨迹（调用工具序列）")
        L.append("")
        # 相邻去重，便于看出做了哪类动作
        seq = []
        for t in tool_trail:
            if not seq or seq[-1] != t:
                seq.append(t)
        L.append("`" + " → ".join(seq) + "`")
        L.append("")
    if bad_lines:
        L.append(f"<!-- 解析时跳过 {bad_lines} 行坏 JSON -->")
    return "\n".join(L).rstrip() + "\n"


def write_index(records, out_dir):
    records.sort(key=lambda r: r.get("created", ""))
    with open(os.path.join(out_dir, "sessions_index.json"), "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    L = ["# 会话清单（extract_sessions 生成）", "",
         f"共 {len(records)} 个会话，按时间升序。agent 据此挑选有沉淀价值的会话做浓缩。", "",
         "标记列：⚠️空＝无任何用户轮次与助手回复；⚠️降级＝assignment.md 缺失，"
         "用户轮次回退自 trajectory。", "",
         "| # | 时间 | 用户首轮需求（截断） | 轮次 | 回复 | 字数 | 标记 | 转录 |",
         "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for i, r in enumerate(records, 1):
        req = r["first_request"].replace("|", "\\|").replace("\n", " ")
        if len(req) > 60:
            req = req[:60] + "…"
        mark = '⚠️空' if r["empty"] else ('⚠️降级' if r.get("degraded") else '')
        L.append(f"| {i} | {r['created']} | {req} | {r['user_turns']} | "
                 f"{r['assistant_replies']} | {r['chars']} | {mark} "
                 f"| [[{r['transcript'].replace('transcripts/','').replace('.transcript.md','')}]] |")
    with open(os.path.join(out_dir, "sessions_index.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
