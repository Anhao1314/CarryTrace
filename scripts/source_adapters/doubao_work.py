#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阶段 A：把豆包 Work 本地会话缓存（.sessions）提取为「干净转录 + 会话清单」。

职责（确定性、零第三方依赖，只用标准库）：
  1. 扫描 sessions-root 下每个会话目录；
  2. 从 assignment.md 取「用户每轮需求」（最干净，append-only）；
     该文件缺失时回退到 trajectory 的 user 消息，并在清单里标记「降级」；
  3. 从 trajectory.jsonl 取「助手最终文本回复」，丢弃 tool 结果与工具调用噪声；
  4. 剥离系统注入块 / 压缩摘要块 / 思考块（只剥固定白名单，绝不误删用户粘贴的合法 XML）；
  5. 为每个会话输出一份可读 transcript.md，并汇总 sessions_index.json / .md。

本脚本只做「提取与清洗」，不做知识浓缩。浓缩（判断价值、写摘要与原子卡片）由
agent 阅读 transcript 后完成，再交给 render_notes.py 渲染成 Obsidian 成品。

用法：
  python3 extract_sessions.py
  python3 extract_sessions.py --sessions-root <.sessions> --out <staging目录>
  python3 extract_sessions.py --only <session_id>             # 只处理单个会话
  python3 extract_sessions.py --keep-tool-trail               # 额外保留工具名操作轨迹
输出默认放在当前目录的 _kb_staging/ 下，可重复运行、幂等覆盖，不触碰 Obsidian 库。
"""

from .transcript import (CN_TZ, clean_text, iso_to_cn, slug_preview, build_transcript, write_index)
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta


# ---- 只剥离这些「系统注入」成对标签块；用户代码里的合法 XML（service/script/...）不在此列，绝不误删 ----
# ---- 上下文压缩后重放的摘要段（形如 === TASK_FOCUS === ... ===），仅按固定段名白名单剥离 ----










def parse_assignment(path: str):
    """解析 assignment.md，返回 [(iso, cn_str, 需求正文)]；缺失返回 []。"""
    if not path or not os.path.isfile(path):
        return []
    raw = open(path, encoding="utf-8").read()
    # 按 ## [时间戳] 需求 切块
    matches = list(re.finditer(r"^##\s*\[([^\]]+)\]\s*[^\n]*$", raw, flags=re.MULTILINE))
    turns = []
    for i, mt in enumerate(matches):
        start = mt.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        body = clean_text(raw[start:end])
        if body:
            _, cn = iso_to_cn(mt.group(1))
            turns.append((mt.group(1), cn, body))
    return turns


def parse_trajectory(path: str, keep_tool_trail: bool, collect_users: bool = False):
    """返回 (助手回复列表, 工具名轨迹列表, 坏行数, 用户消息列表)。

    collect_users 只在 assignment.md 缺失/为空时打开：那种情况下没有更干净的来源，
    只能拿 trajectory 的 user 消息兜底。它们常夹带系统注入与上下文重放，故默认不收集。
    """
    replies, tool_trail, bad, users = [], [], 0, []
    if not path or not os.path.isfile(path):
        return replies, tool_trail, bad, users
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            bad += 1
            continue
        role = o.get("role")
        if role == "assistant":
            txt = clean_text(o.get("content"))
            if txt:
                replies.append(txt)
            if keep_tool_trail and o.get("tool_calls"):
                for tc in o["tool_calls"]:
                    try:
                        tool_trail.append(tc["function"]["name"])
                    except (KeyError, TypeError):
                        pass
        elif role == "user" and collect_users:
            txt = clean_text(o.get("content"))
            if txt:
                users.append(txt)
        # role == 'tool' 的工具结果一律丢弃；user 消息默认以 assignment 为准，避免与重放内容重复
    return replies, tool_trail, bad, users


def find_agent_files(session_dir: str):
    """找到该会话下所有 agent 的 assignment.md / trajectory.jsonl（单 agent 时只有一个）。"""
    agents = []
    adir = os.path.join(session_dir, "agents")
    if os.path.isdir(adir):
        for name in sorted(os.listdir(adir)):
            sdir = os.path.join(adir, name, "system")
            tfile = os.path.join(sdir, "trajectory.jsonl")
            afile = os.path.join(sdir, "assignment.md")
            if os.path.isfile(tfile) or os.path.isfile(afile):
                agents.append((name, afile if os.path.isfile(afile) else "",
                               tfile if os.path.isfile(tfile) else ""))
    return agents






def process(session_dir, out_dir, keep_tool_trail):
    session_id = os.path.basename(session_dir.rstrip(os.sep))
    agents = find_agent_files(session_dir)
    all_turns, all_replies, all_trail, agent_ids = [], [], [], []
    degraded = []
    total_bad = 0
    iso_first = iso_last = None
    for agent_id, afile, tfile in agents:
        agent_ids.append(agent_id)
        turns = parse_assignment(afile)
        # assignment.md 是首选来源；缺失/为空时才回头收集 trajectory 的 user 消息兜底
        replies, trail, bad, user_msgs = parse_trajectory(
            tfile, keep_tool_trail, collect_users=not turns)
        total_bad += bad
        if not turns and user_msgs:
            turns = [("", "", t) for t in user_msgs]
            degraded.append(f"{agent_id}: assignment.md 缺失或为空，用户 {len(user_msgs)} 轮"
                            f"回退自 trajectory；这些消息可能残留系统注入，浓缩时需甄别")
        # 多 agent 时按 agent 顺序简单拼接（本环境均为单 agent）
        for t in turns:
            all_turns.append(t)
            iso = t[0]
            if iso:  # 回退轮次没有时间戳，跳过以免首尾时间被空串污染
                iso_first = iso if iso_first is None else min(iso_first, iso)
                iso_last = iso if iso_last is None else max(iso_last, iso)
        all_replies.extend(replies)
        all_trail.extend(trail)
    # 时间：优先 assignment 首尾；否则目录 mtime
    _, created_cn = iso_to_cn(iso_first) if iso_first else (None, "")
    _, updated_cn = iso_to_cn(iso_last) if iso_last else (None, "")
    if not created_cn:
        mt = datetime.fromtimestamp(os.path.getmtime(session_dir)).astimezone(CN_TZ)
        created_cn = updated_cn = mt.strftime("%Y-%m-%d %H:%M")
    # 按时间排序需求轮次（多 agent 合并后）
    all_turns.sort(key=lambda x: x[0])
    chars = sum(len(r) for r in all_replies) + sum(len(t[2]) for t in all_turns)
    os.makedirs(os.path.join(out_dir, "transcripts"), exist_ok=True)
    tname = f"{session_id}.transcript.md"
    tpath = os.path.join(out_dir, "transcripts", tname)
    rel_source = f".sessions/{session_id}"
    md = build_transcript(session_id, created_cn, updated_cn, all_turns, all_replies,
                          all_trail, agent_ids, total_bad, rel_source, degraded)
    open(tpath, "w", encoding="utf-8").write(md)
    first_req = slug_preview(all_turns[0][2]) if all_turns else ""
    return {
        "session_id": session_id,
        "created": created_cn,
        "updated": updated_cn,
        "first_request": first_req,
        "user_turns": len(all_turns),
        "assistant_replies": len(all_replies),
        "chars": chars,
        "agents": agent_ids,
        "degraded": degraded,
        "transcript": f"transcripts/{tname}",
        "empty": (len(all_turns) == 0 and len(all_replies) == 0),
    }




def main():
    ap = argparse.ArgumentParser(description="提取豆包Work会话缓存为干净转录+清单")
    default_root = os.path.expanduser(
        "~/Library/Application Support/DoubaoWork/Default/.doubaowork/agent_mode/workspace/.sessions")
    ap.add_argument("--sessions-root", default=default_root)
    ap.add_argument("--out", default=os.path.join(os.getcwd(), "_kb_staging"))
    ap.add_argument("--only", default="", help="只处理指定 session_id")
    ap.add_argument("--keep-tool-trail", action="store_true", help="保留工具名操作轨迹")
    args = ap.parse_args()

    if not os.path.isdir(args.sessions_root):
        print(json.dumps({"ok": False, "error": "sessions-root 不存在", "path": args.sessions_root},
                         ensure_ascii=False))
        sys.exit(1)
    ids = sorted(d for d in os.listdir(args.sessions_root)
                 if os.path.isdir(os.path.join(args.sessions_root, d)))
    if args.only:
        ids = [d for d in ids if d == args.only]
        if not ids:
            print(json.dumps({"ok": False, "error": "未找到指定会话", "session": args.only},
                             ensure_ascii=False))
            sys.exit(1)
    records = []
    for sid in ids:
        rec = process(os.path.join(args.sessions_root, sid), args.out, args.keep_tool_trail)
        records.append(rec)
    write_index(records, args.out)
    nonempty = [r for r in records if not r["empty"]]
    summary = {"ok": True, "out": args.out, "total": len(records),
               "nonempty": len(nonempty), "empty": len(records) - len(nonempty),
               "total_chars": sum(r["chars"] for r in records)}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    for r in records:
        flag = " [空]" if r["empty"] else ""
        print(f"  {r['created']}  U{r['user_turns']}/A{r['assistant_replies']}  "
              f"{r['chars']:>6}字  {r['session_id']}{flag}  {r['first_request'][:40]}")


if __name__ == "__main__":
    main()
