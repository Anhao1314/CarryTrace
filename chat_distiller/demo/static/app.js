'use strict';

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const STATUS = {
  '现行': { key: 'current', cls: 'current', dot: 'dot--current' },
  '有争议': { key: 'disputed', cls: 'disputed', dot: 'dot--disputed' },
  '已过期': { key: 'superseded', cls: 'superseded', dot: 'dot--superseded' },
};
const statusOf = (claim) => {
  if (claim.redacted_at) return { key: 'redacted', cls: 'redacted', dot: 'dot--superseded' };
  return STATUS[claim.status] || { key: 'superseded', cls: 'superseded', dot: 'dot--superseded' };
};
const DEFAULT_BUDGET = 2048;

/* ---------------- i18n (default: Chinese, persisted) ---------------- */
const LANG_KEY = "claim-ledger-lang";
let LANG = (localStorage.getItem(LANG_KEY) || "zh") === "en" ? "en" : "zh";
const I18N = {
"status.current": ["Current", "现行"],
"status.disputed": ["Disputed", "有争议"],
"status.superseded": ["Superseded", "已过期"],
"status.historical": ["Historical", "历史"],
"status.redacted": ["Redacted", "已脱敏"],
"nav.ledger": ["Ledger", "台账"],
"nav.record": ["Record", "记录"],
"nav.brief": ["Brief", "简报"],
"nav.search": ["Search", "检索"],
"nav.context": ["Context", "上下文"],
"nav.evidence": ["Evidence", "证据"],
"nav.safety": ["Safety", "安全"],
"brand.tagline": ["decision ledger", "决策账本"],
"store.demo": ["Live demo store", "演示数据存储"],
"store.readonly": ["Read-only store", "只读存储"],
"store.local": ["Live local store", "本地实时存储"],
"store.claims": ["claims", "条声明"],
"store.reset": ["Reset", "重置"],
"store.resetTitle": ["Restore the synthetic demo store", "恢复为合成演示数据"],
"sidebar.foot": ["Zero dependencies · zero model calls", "零依赖 · 零模型调用"],
"topbar.local": ["Local demo", "本地演示"],
"topbar.modelCalls": ["model calls: 0", "模型调用：0"],
"topbar.modelCallsTitle": ["Every claim and brief is produced by deterministic Python", "每条声明与简报都由确定性 Python 生成"],
"story.try": ["Try", "试一下"],
"story.long": ["the conflict case", "冲突案例"],
"story.short": ["a conflict", "冲突"],
"mode.title": ["Read-only ledger", "只读账本"],
"mode.body": ["This demo is bound to an existing store. Restart with <code>--write</code> to record; reset is disabled.", "当前演示绑定的是已有存储。加 <code>--write</code> 重启后才能记录；重置已禁用。"],
"ledger.eyebrow": ["Decision ledger", "决策台账"],
"ledger.h1": ["Everything still counts — or it says why not.", "一切仍然算数——否则它会说明为什么不算。"],
"ledger.lede": ["One JSONL file is the authority. Claims carry a status and a source; supersession keeps the old decision as history instead of deleting it.", "一个 JSONL 文件就是唯一权威。每条声明都带状态与出处；取代让旧决定作为历史保留，而不是被删除。"],
"ledger.hint.current": ["served by the brief", "由简报提供服务"],
"ledger.hint.disputed": ["surfaced for review", "呈报人工复核"],
"ledger.hint.superseded": ["kept as history", "作为历史保留"],
"ledger.store": ["Store", "存储"],
"ledger.topics": ["Claims by topic", "按主题查看声明"],
"ledger.topicsNote": ["The state machine is the product. A superseded claim keeps its successor; a dispute keeps both voices.", "状态机就是产品本身。已过期声明保留后继者；争议保留双方声音。"],
"ledger.emptyTitle": ["No claims yet", "还没有任何声明"],
"ledger.emptyNote": ["Record the first decision to start the ledger.", "记录第一条决策，让台账开始运转。"],
"ledger.emptyCta": ["Record a claim", "记录一条声明"],
"record.eyebrow": ["Record at decision time", "在决策发生时记录"],
"record.h1": ["The write is where trust starts.", "信任从写入那一刻开始。"],
"record.lede": ["Type a decision that overlaps a current claim. The ledger refuses the write and shows you the conflict — it never picks a winner for you.", "输入一条与现行声明重叠的决策。账本会拒绝写入并展示冲突——它绝不会替你选边。"],
"record.newClaim": ["New claim", "新声明"],
"record.decision": ["Decision", "决策内容"],
"record.decisionPh": ["Use PostgreSQL 16 for all Atlas storage", "Atlas 全部存储统一使用 PostgreSQL 16"],
"record.decisionHint": ["one standalone statement", "一句可独立理解的话"],
"record.topic": ["Topic", "主题"],
"record.tags": ["Tags", "标签"],
"record.tagsHint": ["comma-separated", "逗号分隔"],
"record.tagsPh": ["storage, postgres", "存储, postgres"],
"record.scope": ["Scope", "生效范围"],
"record.scopeHint": ["where it applies", "适用的环境"],
"record.scopeTitle": ["all, production, staging, mobile-ios…", "all（全部）、production（生产）、staging（预发）…"],
"record.source": ["Source", "来源"],
"record.sourcePh": ["Architecture review · 2026-10-23", "架构评审 · 2026-10-23"],
"record.quote": ["Quote", "引文"],
"record.quoteHint": ["optional evidence", "可选证据"],
"record.quotePh": ["The exact sentence from the discussion that supports this.", "讨论中支持该决策的原句。"],
"record.dispute": ["Record as disputed", "记为有争议"],
"record.disputeNote": ["Keeps both positions open; also bypasses a detected conflict without superseding.", "保留双方观点；也可以在不取代的前提下绕过检测到的冲突。"],
"record.submit": ["Record claim", "记录声明"],
"record.preview": ["Preview proposal", "预览提案"],
"record.previewTitle": ["Build a review-only proposal; nothing is written", "生成只读提案；不写入任何内容"],
"record.tryCase": ["Try a case", "试个例子"],
"record.caseConflict": ["Conflicting decision", "冲突决策"],
"record.caseClean": ["New, unrelated decision", "新的无关决策"],
"record.caseDispute": ["Open dispute", "悬而未决的争议"],
"record.guardrail": ["What the guardrail does", "护栏做了什么"],
"record.s1t": ["Validate", "校验"],
"record.s1p": ["Stable schema, topic grammar, byte limits. Corruption refuses service.", "稳定 schema、主题文法、字节上限。数据损坏即拒绝服务。"],
"record.s2t": ["Surface overlap", "摊开重叠"],
"record.s2p": ["Lexical overlap above a threshold is a suspicion, never a verdict.", "超过阈值的词法重叠只是一种怀疑，绝不是判决。"],
"record.s3t": ["Require a decision", "要求人做决定"],
"record.s3p": ["Supersede the old claim, mark the new one disputed, or cancel. No silent wins.", "取代旧声明、把新声明记为争议，或者取消。绝不悄悄分出胜负。"],
"record.guardrailNote": ["Conflict matching is deterministic and lexical. It can miss semantic contradictions — and it never adjudicates truth.", "冲突匹配是确定性的词法匹配。它可能漏掉语义矛盾——也绝不裁定真伪。"],
"record.checking": ["Current claims being checked", "正在比对的现行声明"],
"record.checks": ["{n} checks", "{n} 条比对"],
"record.noCurrent": ["No current claims.", "暂无现行声明。"],
"record.needText": ["A claim needs text.", "声明需要正文。"],
"record.needTextPreview": ["A claim needs text before it can be proposed.", "需要先填写正文才能生成提案。"],
"record.readOnly": ["This ledger is read-only. Restart with --write to record.", "该账本为只读。加 --write 重启后才能记录。"],
"record.readOnlyToast": ["Read-only ledger; no write was attempted.", "只读账本；未尝试写入。"],
"record.formNote": ["Record writes a real line to the JSONL store; preview never writes.", "「记录」会向 JSONL 存储写入真实一行；「预览」绝不写入。"],
"record.formNoteRo": ["Read-only ledger: proposal preview still works; Record is disabled.", "只读账本：提案预览仍可用；「记录」已禁用。"],
"record.success": ["Claim recorded. The store digest changed — this was a real write.", "声明已记录。存储摘要已变化——这是一次真实写入。"],
"record.duplicate": ["That claim already exists in the ledger.", "该声明已存在于台账中。"],
"record.refused": ["The write was refused.", "写入被拒绝。"],
"record.conflictMsgOne": ["“{text}” overlaps {count} current claim. The write was refused before it touched the store. Choose how to settle it — or cancel.", "「{text}」与 {count} 条现行声明重叠。写入在触碰存储前被拒绝。请选择如何处理——或者取消。"],
"record.conflictMsgMany": ["“{text}” overlaps {count} current claims. The write was refused before it touched the store. Choose how to settle it — or cancel.", "「{text}」与 {count} 条现行声明重叠。写入在触碰存储前被拒绝。请选择如何处理——或者取消。"],
"record.conflictMsgAll": [" All detected conflicts are superseded together.", " 所有被检测到的冲突将被一并取代。"],
"record.supersedeOne": ["Supersede {id} & record", "取代 {id} 并记录"],
"record.supersedeAll": ["Supersede all {n} & record", "取代全部 {n} 条并记录"],
"record.supersedeBtn": ["Supersede & record", "取代并记录"],
"modal.eyebrow": ["Write refused", "写入被拒绝"],
"modal.title": ["A possible conflict was surfaced.", "发现一处可能的冲突。"],
"modal.cancel": ["Cancel", "取消"],
"modal.dispute": ["Record as disputed", "记为有争议"],
"modal.supersede": ["Supersede & record", "取代并记录"],
"modal.fineprint": ["The ledger surfaces the suspicion. Superseding is an explicit human decision, written into the chain.", "账本只负责摊开怀疑。取代与否是人的显式决定，并会写入链条。"],
"receipt.title": ["Write receipt", "写入回执"],
"receipt.claim": ["claim", "声明"],
"receipt.body": ["Recorded with provenance and a stable claim id.", "已记录，含出处与稳定的声明 ID。"],
"receipt.viewLedger": ["View in ledger", "在台账中查看"],
"receipt.renderBrief": ["Render a brief", "渲染简报"],
"suggest.title": ["Claim proposal · review only", "声明提案 · 仅供评审"],
"suggest.proposed": ["Proposed", "待评审"],
"suggest.conflicts": ["conflicts", "冲突"],
"suggest.nextStep": ["next step", "下一步"],
"suggest.fineprint": ["Nothing was written. Run <code>claim record --supersedes …</code> or use Record to commit after review.", "未写入任何内容。可运行 <code>claim record --supersedes …</code>，或评审后用「记录」提交。"],
"suggest.none": ["none detected", "未检测到"],
"suggest.resolve": ["Supersede every conflict, or record as disputed.", "取代全部冲突，或记为有争议。"],
"suggest.justRecord": ["Record with claim_record.", "用 claim_record 记录即可。"],
"suggest.evidence": ["{n} linked passage{s} · {filtered} filtered by status or identity", "{n} 条关联片段 · {filtered} 条因状态或身份被过滤"],
"suggest.retrieverError": [" · retriever error: {err}", " · 检索器错误：{err}"],
"suggest.readyToast": ["Proposal ready. Nothing was written.", "提案已生成。未写入任何内容。"],
"suggest.buildError": ["Could not build the proposal.", "无法生成提案。"],
"brief.eyebrow": ["Read as a briefing", "读作一份简报"],
"brief.h1": ["A brief that fits, and says what it left out.", "一份放得下的简报，并且说清楚它省略了什么。"],
"brief.lede": ["Drag the budget down. Entries are dropped deterministically and counted — the packet is a rebuildable view, never a second source of truth.", "把预算往下拖。条目被确定性地丢弃并逐一计数——数据包是可重建的视图，绝不是第二个真相源。"],
"brief.budget": ["Byte budget", "字节预算"],
"brief.fineprint": ["The budget covers the whole serialized UTF-8 JSON packet, including metadata and the trailing newline. Bytes are not tokens.", "预算覆盖完整序列化的 UTF-8 JSON 包，含元数据与结尾换行。字节不是 token。"],
"brief.rendered": ["Rendered packet", "渲染的数据包"],
"brief.view": ["View", "视图"],
"brief.wire": ["Wire JSON", "线上格式"],
"brief.orderNote": ["Order is fixed: open disputes → current claims by topic → recently superseded.", "顺序固定：未决争议 → 按主题的现行声明 → 最近被取代。"],
"brief.why": ["Why this is not a summary", "为什么这不是“摘要”"],
"brief.whyNote": ["No model writes the brief. It is rendered from the store on every request, so it cannot rot out of sync. Regenerating it is lossless.", "简报不由任何模型撰写。它随每次请求从存储渲染，因此不会腐化失真。重建是无损的。"],
"brief.docTitle": ["Session brief · derived view", "会话简报 · 派生视图"],
"brief.docSub": ["what still counts", "什么仍然算数"],
"brief.disputes": ["Open disputes", "未决争议"],
"brief.currentClaims": ["Current claims", "现行声明"],
"brief.recent": ["Recently superseded", "最近被取代"],
"brief.omittedTitle": ["Omitted to fit the budget", "为满足预算而省略"],
"brief.omittedFlag": ["omitted", "省略"],
"brief.empty": ["The store is empty. Record a claim to render a brief.", "存储为空。记录一条声明即可渲染简报。"],
"brief.omittedCount": ["{n} omitted", "省略 {n} 条"],
"brief.renderError": ["Could not render the brief.", "无法渲染简报。"],
"search.eyebrow": ["Long-tail retrieval", "长尾检索"],
"search.h1": ["Status-aware search, next to the status-blind baseline.", "状态感知检索，与状态盲基线并排对比。"],
"search.lede": ["Search is lexical and local. The comparison below is the point: feeding raw history back can rank a dead decision first.", "检索是词法的、本地的。下面的对比才是重点：把原始历史直接喂回去，死掉的决策可能排到第一。"],
"search.ph": ["database, use sqlite, timeout, api v1…", "数据库、use sqlite、timeout、api v1…"],
"search.aria": ["Search claims", "搜索声明"],
"search.submit": ["Search", "搜索"],
"search.include": ["Include superseded", "包含已过期"],
"search.statusBlind": ["status-blind", "状态盲"],
"search.defaultHint": ["Enter a query to compare retrieval policies.", "输入查询，对比两种检索策略。"],
"search.failed": ["Search failed.", "检索失败。"],
"search.noMatch": ["No lexical match for “{q}”. The ledger does not guess.", "没有词法命中「{q}」。账本不做猜测。"],
"search.noMatchBody": ["Nothing matched. Try another term, or record this as a new claim.", "没有命中。换个词试试，或者把它作为新声明记录下来。"],
"search.blindHead": ["{n} results · status-blind lexical ranking · ", "{n} 条结果 · 状态盲词法排序 · "],
"search.blindWarn": ["{n} of {total} results are superseded. This is what feeding raw history back looks like.", "{total} 条中有 {n} 条已过期。这就是把原始历史直接喂回去的样子。"],
"search.blindClean": ["No superseded claims matched this query.", "本次查询没有命中已过期声明。"],
"search.blindHint": ["The ledger's status filter is off; superseded text ranks by overlap alone.", "账本的状态过滤已关闭；已过期文本仅按重叠度排序。"],
"search.awareHead": ["{n} results · status-aware · 0 superseded can appear.", "{n} 条结果 · 状态感知 · 已过期绝不会出现。"],
"search.awareHint": ["{n} disputed claim(s) surfaced for review.", "{n} 条争议声明已呈报复核。"],
"search.awareHintClean": ["Only current claims are eligible.", "只有现行声明符合条件。"],
"search.supersededBy": ["superseded by", "被取代于"],
"context.eyebrow": ["RAG, on the ledger's terms", "按台账规则的 RAG"],
"context.h1": ["Evidence may be retrieved. Authority stays with the store.", "证据可以检索，权威仍归存储。"],
"context.lede": ["A context packet joins a deterministic brief with evidence from a retriever. Every hit must resolve to a claim and pass the same status filter — superseded passages cannot pose as current.", "上下文包把确定性简报与检索器给出的证据拼在一起。每条命中都必须解析到某条声明并接受同一套状态过滤——过期片段不能冒充现行。"],
"context.build": ["Build a context packet", "构建上下文包"],
"context.query": ["Query", "查询"],
"context.ph": ["use sqlite, token, timeout…", "use sqlite、token、timeout…"],
"context.aria": ["Context query", "上下文查询"],
"context.historical": ["Historical intent", "历史意图"],
"context.historicalHint": ["include superseded, labelled", "包含已过期并标注"],
"context.showWire": ["Show wire JSON", "显示线上 JSON"],
"context.showWireHint": ["exact bytes", "精确字节"],
"context.ragNote": ["{n} synthetic chunk{s} via {provider}{seal}. Every hit must resolve to a claim and pass the same status policy as the brief.", "来自 {provider} 的 {n} 个合成片段{seal}。每条命中都必须解析到声明并接受与简报相同的状态策略。"],
"context.ragNoteSealed": [" · sealed to one store digest", " · 已密封到单一存储摘要"],
"context.ragNoteUnsealed": [" · unsealed", " · 未密封"],
"context.ragNoteOff": ["No evidence index is available; packets fall back to the deterministic brief.", "暂无证据索引；上下文包将退回纯确定性简报。"],
"context.ragLoading": ["Loading evidence index status…", "正在加载证据索引状态…"],
"context.packet": ["Packet", "数据包"],
"context.bytes": ["bytes", "字节"],
"context.brief": ["brief", "简报"],
"context.evidence": ["evidence", "证据"],
"context.shown": ["shown", "条展示"],
"context.omitted": ["omitted", "条省略"],
"context.excluded": ["excluded", "过滤"],
"context.filtered": ["{n} filtered", "过滤 {n} 条"],
"context.window": ["window", "窗口"],
"context.briefOnly": ["brief-only", "仅简报"],
"context.candidates": ["{n} candidates · {c} search{cs}", "{n} 个候选 · {c} 次检索"],
"context.defaultEmpty": ["Enter a query to build a context packet.", "输入查询以构建上下文包。"],
"context.buildError": ["Could not build the packet.", "无法构建数据包。"],
"context.toastError": ["Could not build the context packet.", "无法构建上下文包。"],
"context.docTitle": ["Grounded context · two layers", "有据上下文 · 双层结构"],
"context.authority": ["authority: claim store", "权威：声明存储"],
"context.statEvidence": ["evidence", "证据"],
"context.statCurrent": ["current", "现行"],
"context.statIntent": ["intent", "意图"],
"context.layerNote": ["brief = deterministic authority view · evidence = retrieved passages, untrusted data joined to a claim", "简报 = 确定性权威视图 · 证据 = 检索片段，作为挂到声明上的不可信数据"],
"context.layer1": ["Authority layer · deterministic brief", "权威层 · 确定性简报"],
"context.showBrief": ["Show the brief contents", "展开简报内容"],
"context.claimsCount": ["{n} claims", "{n} 条声明"],
"context.layer2on": ["Evidence layer · status-filtered", "证据层 · 已按状态过滤"],
"context.layer2off": ["Evidence layer · not attached", "证据层 · 未挂载"],
"context.providerNote": ["Retrieved by {provider} · every hit is joined to a claim and cannot override it.", "由 {provider} 检索 · 每条命中都挂到声明上，且无法覆盖声明。"],
"context.noProvider": ["No retriever is attached.", "未挂载检索器。"],
"context.candidatesOnly": ["{n} candidate passage(s) were retrieved, but none passed claim identity, status, or quota checks.", "检索到 {n} 条候选片段，但没有任何一条通过声明身份、状态或配额检查。"],
"context.noCandidates": ["The retriever returned no candidates for this query.", "检索器对该查询没有返回候选。"],
"context.emptyBrief": ["The brief is empty.", "简报为空。"],
"context.errorHead": ["Evidence unavailable: {err}. The brief is still authoritative.", "证据不可用：{err}。简报仍然是权威。"],
"context.chipCandidates": ["{n} candidates", "{n} 个候选"],
"context.chipStale": ["stale excluded {n}", "排除过期 {n}"],
"context.chipUnlinked": ["unlinked {n}", "未挂链 {n}"],
"context.chipUnresolved": ["unresolved {n}", "未解析 {n}"],
"context.chipQuota": ["over quota {n}", "超配额 {n}"],
"context.chipBudget": ["over budget {n}", "超预算 {n}"],
"context.chipWindow": ["window {n} · {c} call(s)", "窗口 {n} · {c} 次调用"],
"context.historicalFlag": ["historical", "历史"],
"context.footStore": ["store", "存储"],
"context.footIndex": ["index", "索引"],
"context.copyToast": ["Context wire JSON copied · {size}", "上下文 JSON 已复制 · {size}"],
"evidence.eyebrow": ["Evidence you can replay", "可复现的证据"],
"evidence.h1": ["Numbers with the limits attached.", "数字旁边，附上边界。"],
"evidence.lede": ["Synthetic fixtures, deterministic code, zero model calls. These measure structure and lifecycle safety — not semantic truth or agent task success.", "合成数据、确定性代码、零模型调用。这些度量衡量结构与生命周期安全——不是语义真值，也不是 Agent 任务成功率。"],
"evidence.retrieval": ["Retrieval", "检索"],
"evidence.colMethod": ["Method", "方法"],
"evidence.loadError": ["Could not load evidence.", "无法加载证据。"],
"evidence.checks": ["Structural safety checks", "结构安全检查"],
"evidence.checksNote": ["CompileBench: four topics, twelve curated cards, zero model calls.", "CompileBench：四个主题、十二张精选卡片、零模型调用。"],
"evidence.cannot": ["What this cannot prove", "它无法证明什么"],
"evidence.card1": ["Invalid proposals blocked", "无效提案被拦截"],
"evidence.card1Hint": ["Without creating compiled state", "且不创建已编译状态"],
"evidence.card2": ["Exact byte budgets", "精确字节预算"],
"evidence.card2Hint": ["Serialized UTF-8 packet checks", "序列化 UTF-8 包校验"],
"evidence.card3": ["Stale pages served", "提供过期页面"],
"evidence.card3Hint": ["Freshness gate enabled", "新鲜度门禁开启"],
"evidence.card4Hint": ["Freshness gate disabled — the ablation", "新鲜度门禁关闭——消融实验"],
"evidence.fallback1": ["Not an independent holdout or automatic LLM synthesis evaluation.", "不是独立保留集，也不是自动 LLM 综合评测。"],
"evidence.fallback2": ["Status and scope are explicit; unknown semantic contradictions can be missed.", "状态与范围是显式的；未知的语义矛盾可能被漏掉。"],
"evidence.fallback3": ["A false synthesis with a real quote can pass structurally and remains review-required.", "带真实引用的错误综合在结构上可以通过，仍需人工复核。"],
"evidence.fallback4": ["Numbers describe engineering checks, not agent task success.", "数字描述的是工程检查，不是 Agent 任务成功率。"],
"evidence.everyFixture": ["Every fixture", "全部数据"],
"evidence.synthetic": ["synthetic · zero model calls", "合成数据 · 零模型调用"],
"safety.eyebrow": ["Data safety", "数据安全"],
"safety.h1": ["Backups you can verify. Removal you can audit.", "可验证的备份。可审计的删除。"],
"safety.lede": ["Every snapshot carries a checksummed manifest. Redaction keeps a content-free tombstone and the supersession chain; deletion removes rows and names what references them. Both write an audit entry and a plaintext pre-change backup by default.", "每个快照都带校验清单。脱敏保留不含内容的墓碑与取代链；删除会移除记录并指出谁引用了它。两者默认都会写审计记录和改动前的明文备份。"],
"safety.snapshots": ["Snapshots", "快照"],
"safety.backupNow": ["Backup now", "立即备份"],
"safety.backupNote": ["Snapshots are written next to the store with a manifest: claim count, byte count and two SHA-256 digests.", "快照写入存储旁目录并附带清单：声明数、字节数与两个 SHA-256 摘要。"],
"safety.backupNoteRo": ["This ledger is read-only; backup still works because it writes only to the backups directory.", "该账本只读；备份仍可用，因为它只写入备份目录。"],
"safety.audit": ["Audit trail", "审计轨迹"],
"safety.auditNote": ["Append-only. Records the action, claim ids, before/after store digests and the backup filename — never the claim text.", "只追加。记录动作、声明 ID、前后存储摘要与备份文件名——绝不记录声明正文。"],
"safety.guarantees": ["What this guarantees — and what it does not", "它保证什么——以及不保证什么"],
"safety.g1": ["Writes are serialized by a cross-process lock; contention past the timeout is an explicit busy error, never a silent overwrite.", "写入由跨进程锁串行化；超时后的争用是明确的忙错误，绝不是静默覆盖。"],
"safety.g2": ["Restore verifies byte count, file digest, store digest and claim count against the manifest before touching the store.", "恢复会先按清单校验字节数、文件摘要、存储摘要与声明数，然后才触碰存储。"],
"safety.g3": ["Backups are plaintext and local — protect the backups directory like the store itself.", "备份是明文且本地的——请像保护存储一样保护备份目录。"],
"safety.g4": ["Redaction does not reach transcripts, logs, old backups or derived evidence indexes; rebuild or purge those separately.", "脱敏不会触达转录、日志、旧备份或派生的证据索引；请单独重建或清理。"],
"safety.noBackups": ["No snapshots yet. Create the first one with “Backup now”.", "还没有快照。点“立即备份”创建第一个。"],
"safety.listError": ["Could not list backups.", "无法列出备份。"],
"safety.noAudit": ["No redact, delete or restore operations yet.", "还没有脱敏、删除或恢复操作。"],
"safety.auditError": ["Could not read the audit log.", "无法读取审计日志。"],
"safety.oneEntry": ["1 entry", "1 条记录"],
"safety.nEntries": ["{n} entries", "{n} 条记录"],
"safety.noBackup": ["no backup retained", "未保留备份"],
"safety.backupToast": ["Snapshot written · {n} claims · {size}", "快照已写入 · {n} 条声明 · {size}"],
"safety.backupError": ["Backup failed.", "备份失败。"],
"safety.redactConfirm": ["Remove the content of {id}? The claim id, status and supersession chain stay; the text, tags, topic, source and quote become a tombstone. A pre-change backup is kept.", "移除 {id} 的内容？声明 ID、状态与取代链保留；正文、标签、主题、来源与引文变为墓碑。默认保留改动前备份。"],
"safety.deleteConfirm": ["Permanently delete {id}? If another claim supersedes it, the store refuses — the CLI --cascade flag removes the whole chain. A pre-change backup is kept.", "永久删除 {id}？若有其它声明取代它，存储会拒绝——CLI 的 --cascade 才会移除整条链。默认保留改动前备份。"],
"safety.doneToast": ["{verb} {ids} · backup {file}", "{verb} {ids} · 备份 {file}"],
"safety.verbRedact": ["Redacted", "已脱敏"],
"safety.verbDelete": ["Deleted", "已删除"],
"safety.actionError": ["{action} failed.", "{action} 失败。"],
"safety.redactedAt": ["redacted", "脱敏于"],
"toast.readOnlyShort": ["This ledger is read-only. Restart with --write to record.", "该账本为只读。加 --write 重启后才能记录。"],
"toast.copyError": ["Clipboard is unavailable in this browser.", "当前浏览器剪贴板不可用。"],
"toast.wireCopied": ["Wire JSON copied · {size}", "线上 JSON 已复制 · {size}"],
"toast.resetConfirm": ["Restore the synthetic Atlas scenario? Local writes to this demo store are dropped.", "恢复为合成的 Atlas 场景？本演示存储上的本地写入将被丢弃。"],
"toast.resetDone": ["Demo store restored to the Atlas scenario.", "演示存储已恢复为 Atlas 场景。"],
"toast.storySubmit": ["Submit the prefilled decision — the guardrail will refuse it.", "提交这条预填的决策——护栏会拒绝它。"],
"common.required": ["required", "必填"],
"common.bytes": ["bytes", "字节"],
"common.try": ["Try", "试一试"],
"common.copyWire": ["Copy wire JSON", "复制线上 JSON"],
"common.provenance": ["Provenance & quote", "出处与引文"],
"safety.cli": ["CLI equivalents: <code>claim backup</code> · <code>claim backups</code> · <code>claim audit</code> · <code>claim restore --from …</code> · <code>claim redact … --yes</code> · <code>claim delete … --yes</code>", "命令行等价：<code>claim backup</code> · <code>claim backups</code> · <code>claim audit</code> · <code>claim restore --from …</code> · <code>claim redact … --yes</code> · <code>claim delete … --yes</code>"],
"brief.meterAria": ["Brief bytes used", "简报已用字节"],
"brief.sliderAria": ["Brief byte budget", "简报字节预算"],
"foot.note": ["Local-first · single JSONL authority · formerly chat-distiller / CarryTrace", "本地优先 · 单一 JSONL 权威 · 前身 chat-distiller / CarryTrace"],
};

function t(key, vars) {
  const entry = I18N[key];
  let out = entry ? (entry[LANG === "en" ? 0 : 1] ?? entry[0]) : key;
  if (vars) {
    for (const [name, value] of Object.entries(vars)) {
      out = out.split("{" + name + "}").join(String(value));
    }
  }
  return out;
}

function statusLabel(key) { return t("status." + key); }

function applyI18n() {
  document.documentElement.lang = LANG === "zh" ? "zh-CN" : "en";
  document.querySelectorAll("[data-i18n]").forEach((node) => { node.textContent = t(node.dataset.i18n); });
  document.querySelectorAll("[data-i18n-html]").forEach((node) => { node.innerHTML = t(node.dataset.i18nHtml); });
  document.querySelectorAll("[data-i18n-ph]").forEach((node) => { node.placeholder = t(node.dataset.i18nPh); });
  document.querySelectorAll("[data-i18n-title]").forEach((node) => { node.title = t(node.dataset.i18nTitle); });
  document.querySelectorAll("[data-i18n-aria]").forEach((node) => { node.setAttribute("aria-label", t(node.dataset.i18nAria)); });
  $("#langBtn").textContent = LANG === "zh" ? "EN" : "中文";
  $("#crumb").textContent = t("nav." + S.view);
  renderChrome();
  renderLedger();
  renderRecordSide();
  if (S.brief) renderBrief();
  if (S.search) renderSearch();
  if (S.context) renderContext();
  if (S.evidence) renderEvidence();
  if (S.proposal) renderProposal();
  if (S.view === "safety") loadSafety();
}


const S = {
  state: null,
  view: 'ledger',
  brief: null,
  briefBudget: DEFAULT_BUDGET,
  briefMode: 'view',
  search: null,
  evidence: null,
  context: null,
  proposal: null,
  backups: [],
  pendingRecord: null,
  conflictData: null,
  toastTimer: null,
  briefTimer: null,
};

const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[ch]));
const num = (n) => new Intl.NumberFormat('en-US').format(n);

function formatBytes(bytes) {
  if (bytes === null || bytes === undefined) return '–';
  if (bytes < 1024) return num(bytes) + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(bytes < 10240 ? 1 : 0) + ' KB';
  return (bytes / 1024 / 1024).toFixed(1) + ' MB';
}
function formatWhen(iso) {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' }) + ' · ' +
    date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC' });
}
function shortId(id) { return id ? id.replace(/^clm_/, 'clm_').slice(0, 12) : '—'; }

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  let data;
  try {
    data = await response.json();
  } catch (err) {
    data = { ok: false, error: 'The server returned a non-JSON response.', error_type: 'ProtocolError' };
  }
  return { response, data };
}

function toast(message, isError = false) {
  const el = $('#toast');
  el.textContent = message;
  el.classList.toggle('toast--error', isError);
  el.hidden = false;
  clearTimeout(S.toastTimer);
  S.toastTimer = setTimeout(() => { el.hidden = true; }, 4200);
}

/* ---------------- navigation ---------------- */
function applyView(view, { focus = false } = {}) {
  if (!document.querySelector(`[data-view-panel="${view}"]`)) view = 'ledger';
  S.view = view;
  $$('.view').forEach((panel) => { panel.hidden = panel.dataset.viewPanel !== view; });
  $$('#nav .nav__item').forEach((btn) => {
    if (btn.dataset.view === view) btn.setAttribute('aria-current', 'page');
    else btn.removeAttribute('aria-current');
  });
  $('#crumb').textContent = t('nav.' + view);
  if (focus) {
    const heading = $('.view:not([hidden]) h1');
    if (heading) heading.focus?.();
  }
  if (view === 'brief') loadBrief();
  if (view === 'context' && S.state) enterContext();
  if (view === 'evidence' && !S.evidence) loadEvidence();
  if (view === 'safety') loadSafety();
  window.scrollTo({ top: 0, behavior: 'instant' in window ? 'instant' : 'auto' });
}

function navigate(view) {
  if (location.hash === '#' + view) applyView(view);
  else location.hash = view;
}

/* ---------------- state / ledger ---------------- */
async function loadState({ silent = false } = {}) {
  const { data } = await api('/api/state');
  if (!data.ok) {
    if (!silent) toast(data.error || 'Could not load the ledger.', true);
    return null;
  }
  S.state = data;
  renderChrome();
  renderLedger();
  renderRecordSide();
  return data;
}

function renderChrome() {
  const data = S.state;
  if (!data) return;
  const { counts, store, scenario } = data;
  $('#navCount').textContent = num(counts.total);
  $('#storeProject').textContent = scenario?.name || 'Decision ledger';
  $('#storeCount').textContent = num(counts.total);
  $('#storeBytes').textContent = formatBytes(store.bytes);
  $('#storeDigest').textContent = (store.sha256 || '').slice(0, 12) + '…';
  $('#storeDigest').title = store.sha256 || '';
  $('#metricCurrent').textContent = num(counts.current);
  $('#metricDisputed').textContent = num(counts.disputed);
  $('#metricSuperseded').textContent = num(counts.superseded);
  $('#metricBytes').textContent = formatBytes(store.bytes);
  $('#metricDigest').textContent = 'sha256 ' + (store.sha256 || '').slice(0, 10) + '…';
  $('#version').textContent = data.version;
  const readOnly = !data.writable;
  $('#storeMode').textContent = readOnly
    ? t('store.readonly')
    : (data.mode === 'demo' ? t('store.demo') : t('store.local'));
  $('.store-card').classList.toggle('store-card--readonly', readOnly);
  $('#modeBanner').hidden = !readOnly;
  $('#resetBtn').hidden = !data.writable;
  $('#storyBtn').disabled = readOnly;
  $('#storyBtn').title = readOnly ? t('record.readOnly') : '';
  const form = $('#recordForm');
  form.classList.toggle('is-readonly', readOnly);
  form.querySelectorAll('input, textarea, button').forEach((element) => {
    element.disabled = readOnly;
  });
  if (readOnly) {
    // Drafting a proposal is read-only, so the text fields stay usable.
    ['#fText', '#fTopic', '#fTags'].forEach((selector) => {
      const element = $(selector);
      if (element) element.disabled = false;
    });
  }
  $('#suggestBtn').disabled = false;
  $('#formNote').textContent = readOnly ? t('record.formNoteRo') : t('record.formNote');
  $('#currentCount').textContent = t('record.checks', { n: num(counts.current) });
}

function renderLedger() {
  const data = S.state;
  if (!data) return;
  const byTopic = new Map();
  for (const claim of data.claims) {
    if (!byTopic.has(claim.topic)) byTopic.set(claim.topic, []);
    byTopic.get(claim.topic).push(claim);
  }
  const rank = { '现行': 0, '有争议': 1, '已过期': 2 };
  const topics = Array.from(byTopic.keys()).sort();
  const html = topics.map((topic) => {
    const claims = byTopic.get(topic).slice().sort((a, b) => {
      const delta = rank[a.status] - rank[b.status];
      return delta !== 0 ? delta : (b.created_at || '').localeCompare(a.created_at || '');
    });
    const current = claims.filter((c) => c.status === '现行').length;
    const disputed = claims.filter((c) => c.status === '有争议').length;
    const history = claims.filter((c) => c.status === '已过期').length;
    const parts = [];
    if (current) parts.push(current + ' ' + statusLabel('current').toLowerCase());
    if (disputed) parts.push(disputed + ' ' + statusLabel('disputed').toLowerCase());
    if (history) parts.push(history + ' ' + t('status.superseded').toLowerCase());
    return `
      <section class="topic">
        <div class="topic__head">
          <span class="topic__name">${esc(topic)}</span>
          <span class="topic__rule"></span>
          <span class="topic__count">${esc(parts.join(' · '))}</span>
        </div>
        <div class="topic__claims">${claims.map(claimCard).join('')}</div>
      </section>`;
  }).join('');
  $('#ledgerTopics').innerHTML = html;
  $('#ledgerEmpty').hidden = data.claims.length > 0;
  if (!data.claims.length) $('#ledgerTopics').innerHTML = '';
}

function claimCard(claim) {
  const redacted = Boolean(claim.redacted_at);
  const meta = statusOf(claim);
  const successor = claim.superseded_by
    ? S.state.claims.find((c) => c.claim_id === claim.superseded_by)
    : null;
  const chain = claim.superseded_by
    ? `<div class="chain">
         <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M14 7l5 5-5 5"/></svg>
         ${esc(t('search.supersededBy'))} <code>${esc(claim.superseded_by)}</code>
         ${successor ? `<span class="tag">${esc(successor.text.slice(0, 46))}${successor.text.length > 46 ? '…' : ''}</span>` : ''}
       </div>` : '';
  const tags = claim.tags.length
    ? `<span class="claim__tags">${claim.tags.map((t) => `<span class="tag">${esc(t)}</span>`).join('')}</span>`
    : '';
  const scopeTag = !redacted && claim.scope && claim.scope !== 'all'
    ? `<span class="tag tag--scope" title="applies to this scope">scope: ${esc(claim.scope)}</span>`
    : '';
  const expiryTag = !redacted && claim.expires_at
    ? `<span class="tag tag--scope" title="stops counting as current after this moment">until ${esc(claim.expires_at)}</span>`
    : '';
  const provenance = claim.quote || claim.session_hint
    ? `<details class="prov"><summary>${esc(t('common.provenance'))}</summary>
         ${claim.quote ? `<blockquote>“${esc(claim.quote)}”</blockquote>` : ''}
         ${claim.session_hint ? `<div class="claim__meta"><span>session <code>${esc(claim.session_hint)}</code></span></div>` : ''}
       </details>`
    : '';
  const actions = S.state?.writable && !redacted
    ? `<div class="claim__actions">
         <button class="mini-btn" type="button" data-safety="redact" data-claim="${esc(claim.claim_id)}">${esc(t('status.redacted'))}</button>
         <button class="mini-btn" type="button" data-safety="delete" data-claim="${esc(claim.claim_id)}">${esc(t('nav.safety')) === '安全' ? '删除' : 'Delete'}</button>
       </div>`
    : '';
  return `
    <article class="claim claim--${meta.cls}${redacted ? ' claim--redacted' : ''}">
      <div class="claim__rail" aria-hidden="true"></div>
      <div class="claim__body">
        <div class="claim__row">
          <p class="claim__text">${esc(claim.text)}</p>
        </div>
        <div class="claim__meta">
          <code title="${esc(claim.claim_id)}">${esc(claim.claim_id)}</code>
          <span>${esc(formatWhen(claim.created_at))}</span>
          ${claim.redacted_at ? `<span>${esc(t('safety.redactedAt'))} ${esc(formatWhen(claim.redacted_at))}</span>` : ''}
          ${claim.source ? `<span class="claim__source">${esc(claim.source)}</span>` : ''}
          ${tags}
          ${scopeTag}
          ${expiryTag}
          ${'' }
        </div>
        ${chain}
        ${provenance}
      </div>
      <div class="claim__side">
        <span class="status-pill status--${meta.cls}">${esc(statusLabel(meta.key))}</span>
        ${actions}
      </div>
    </article>`;
}

function renderRecordSide() {
  const data = S.state;
  if (!data) return;
  const current = data.claims.filter((c) => c.status === '现行');
  $('#currentList').innerHTML = current.length
    ? current.map((c) => {
        const meta = statusOf(c);
        return `<li>
          <div class="mini-list__text"><span class="dot ${meta.dot}"></span><span>${esc(c.text)}</span></div>
          <div class="mini-list__meta">${esc(c.topic)} · ${esc(shortId(c.claim_id))}</div>
        </li>`;
      }).join('')
    : `<li><div class="mini-list__text">${esc(t('record.noCurrent'))}</div></li>`;
}

/* ---------------- record ---------------- */
function formPayload() {
  const tags = $('#fTags').value.split(',').map((t) => t.trim()).filter(Boolean);
  return {
    text: $('#fText').value.trim(),
    topic: $('#fTopic').value.trim() || 'general',
    scope: $('#fScope').value.trim() || 'all',
    tags,
    source: $('#fSource').value.trim() || null,
    quote: $('#fQuote').value.trim() || null,
    dispute: $('#fDispute').checked,
  };
}

function fillExample(key) {
  if (!S.state?.writable) {
    toast(t('toast.readOnlyShort'), true);
    return;
  }
  const example = S.state?.examples?.[key];
  if (!example) return;
  $('#fText').value = example.text;
  $('#fTopic').value = example.topic;
  $('#fScope').value = 'all';
  $('#fTags').value = (example.tags || []).join(', ');
  $('#fSource').value = example.source || '';
  $('#fQuote').value = example.quote || '';
  $('#fDispute').checked = false;
  updateFormCount();
  hideError();
  $('#suggestPanel').hidden = true;
  S.proposal = null;
  $('#fText').focus();
  S.pendingRecord = null;
}

function updateFormCount() {
  $('#formCount').textContent = $('#fText').value.length;
}
function hideError() {
  const box = $('#recordError');
  box.hidden = true;
  box.textContent = '';
}
function showError(message) {
  const box = $('#recordError');
  box.hidden = false;
  box.textContent = message;
  box.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}

async function submitRecord(payload, { supersedes = null, dispute = false, source = 'form' } = {}) {
  if (!S.state?.writable) {
    showError(t('record.readOnly'));
    toast(t('record.readOnlyToast'), true);
    return false;
  }
  const body = { ...payload };
  if (supersedes) body.supersedes = supersedes;
  if (dispute) body.dispute = true;
  const button = $('#recordSubmit');
  button.disabled = true;
  const { data } = await api('/api/record', { method: 'POST', body: JSON.stringify(body) });
  button.disabled = !S.state?.writable;
  if (data.ok) {
    closeConflict();
    showReceipt(data.receipt);
    hideError();
    await loadState({ silent: true });
    if (S.view === 'brief') loadBrief();
    toast(t('record.success'));
    $('#recordForm').reset();
    $('#fTopic').value = 'general';
    $('#fScope').value = 'all';
    $('#fDispute').checked = false;
    $('#suggestPanel').hidden = true;
    S.proposal = null;
    S.context = null;
    updateFormCount();
    return true;
  }
  if (data.error_type === 'Conflict') {
    openConflict(data, payload);
    return false;
  }
  if (data.error_type === 'Duplicate') {
    showError(data.error);
    toast(t('record.duplicate'), true);
    return false;
  }
  showError(data.error || t('record.refused'));
  toast(data.error || t('record.refused'), true);
  return false;
}

function openConflict(data, payload) {
  S.pendingRecord = payload;
  S.conflictData = data;
  const conflicts = data.conflicts || [];
  $('#conflictMessage').textContent = t(conflicts.length === 1 ? 'record.conflictMsgOne' : 'record.conflictMsgMany', {
      text: payload.text, count: conflicts.length,
    }) + (conflicts.length > 1 ? t('record.conflictMsgAll') : '');
  $('#conflictList').innerHTML = conflicts.map((claim) => {
    const meta = statusOf(claim);
    return `<div class="conflict-item">
      <div class="conflict-item__text">${esc(claim.text)}</div>
      <div class="conflict-item__meta">
        <span class="status-pill status--${meta.cls}">${esc(statusLabel(meta.key))}</span>
        <code>${esc(claim.claim_id)}</code>
        <span>${esc(claim.topic)}</span>
      </div>
    </div>`;
  }).join('');
  const primary = conflicts[0];
  const btn = $('#conflictSupersede');
  btn.textContent = conflicts.length > 1
    ? t('record.supersedeAll', { n: conflicts.length })
    : (primary ? t('record.supersedeOne', { id: shortId(primary.claim_id) }) : t('record.supersedeBtn'));
  btn.disabled = !primary;
  const modal = $('#conflictModal');
  modal.hidden = false;
  modal.classList.add('is-open');
  document.body.style.overflow = 'hidden';
  btn.focus();
}

function closeConflict() {
  const modal = $('#conflictModal');
  modal.hidden = true;
  modal.classList.remove('is-open');
  document.body.style.overflow = '';
  S.conflictData = null;
  S.pendingRecord = null;
  if (S.state?.writable) $('#recordSubmit').focus();
}

function showReceipt(receipt) {
  const meta = STATUS[receipt.status] || STATUS['现行'];
  $('#recordReceipt').hidden = false;
  $('#receiptStatus').className = 'status-pill status--' + meta.cls;
  $('#receiptStatus').textContent = statusLabel(meta.key);
  $('#receiptText').textContent = t('receipt.body');
  $('#receiptId').textContent = receipt.claim_id;
  $('#receiptDigest').textContent = (receipt.store_sha256 || '').slice(0, 12) + '…';
  $('#receiptDigest').title = receipt.store_sha256 || '';
  const superseded = (receipt.superseded_claims && receipt.superseded_claims.length)
    ? receipt.superseded_claims.join(', ')
    : (receipt.superseded || '—');
  $('#receiptSuperseded').textContent = superseded;
  $('#recordReceipt').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

/* ---------------- review-only proposal ---------------- */
async function previewSuggestion() {
  const payload = formPayload();
  if (!payload.text) {
    showError(t('record.needTextPreview'));
    $('#fText').focus();
    return;
  }
  hideError();
  const button = $('#suggestBtn');
  button.disabled = true;
  const { data } = await api('/api/suggest', {
    method: 'POST',
    body: JSON.stringify({
      text: payload.text,
      topic: payload.topic,
      tags: payload.tags,
      query: payload.text,
    }),
  });
  button.disabled = false;
  if (!data.ok) {
    showError(data.error || 'Could not build the proposal.');
    toast(data.error || t('suggest.buildError'), true);
    return;
  }
  S.proposal = data.proposal;
  renderProposal();
  toast(t('suggest.readyToast'));
}

function renderProposal() {
  const proposal = S.proposal;
  if (!proposal) return;
  const conflicts = proposal.conflicts || [];
  const tags = proposal.proposed.tags || [];
  const panel = $('#suggestPanel');
  panel.hidden = false;
  $('#suggestText').textContent = proposal.proposed.text;
  $('#suggestTopic').textContent = proposal.proposed.topic + (tags.length ? ' · ' + tags.join(', ') : '');
  $('#suggestConflicts').textContent = conflicts.length
    ? `${conflicts.length} · ${proposal.conflict_ids.join(', ')}`
    : t('suggest.none');
  $('#suggestConflicts').title = proposal.conflict_ids.join(', ');
  $('#suggestAction').textContent = proposal.resolution_required
    ? t('suggest.resolve')
    : t('suggest.justRecord');

  const parts = conflicts.map((conflict) => `<div class="suggest-conflict">
    <div class="suggest-conflict__text">${esc(conflict.text)}</div>
    <div class="suggest-conflict__meta">
      <span>${esc(conflict.claim_id)}</span>
      <span>${esc(conflict.topic)}</span>
      <span>${esc(conflict.status_label)}</span>
    </div>
  </div>`);
  const evidenceCount = (proposal.evidence || []).length;
  const filtered = proposal.stale_excluded + proposal.unlinked_excluded + proposal.unresolved_excluded;
  if (proposal.evidence_provider && proposal.evidence_provider !== 'none') {
    parts.push(`<p class="suggest-evidence">${esc(t('suggest.evidence', { n: evidenceCount, s: evidenceCount === 1 ? '' : 's', filtered }))}${proposal.evidence_error ? esc(t('suggest.retrieverError', { err: proposal.evidence_error })) : ''}</p>`);
  }
  $('#suggestDetail').innerHTML = parts.join('');
  panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

/* ---------------- brief ---------------- */
async function loadBrief() {
  const budget = S.briefBudget;
  const { data } = await api('/api/brief?max_bytes=' + budget);
  if (!data.ok) {
    $('#briefBody').innerHTML = `<p class="brief-empty">${esc(data.error || t('brief.renderError'))}</p>`;
    return;
  }
  S.brief = data;
  renderBrief();
}

function renderBrief() {
  const data = S.brief;
  if (!data) return;
  const packet = data.packet;
  const used = packet.used_bytes;
  const budget = packet.budget_bytes;
  const pct = Math.min(100, Math.round((used / budget) * 1000) / 10);
  $('#briefUsed').textContent = num(used);
  $('#briefBudgetOut').textContent = num(budget);
  $('#briefBudgetLabel').textContent = num(budget) + ' bytes';
  $('#briefOmitted').textContent = t('brief.omittedCount', { n: num(packet.omitted) });
  $('#briefStatus').textContent = packet.status;
  $('#briefMeterFill').style.width = pct + '%';
  $('#briefMeter').setAttribute('aria-valuenow', String(Math.round(pct)));
  $('#briefMeter').classList.toggle('is-tight', pct >= 85 && packet.status === 'ready');
  $('#briefMeter').classList.toggle('is-empty', packet.status === 'budget_exhausted');
  $('#briefBudget').value = String(budget);
  $('#briefBudget').setAttribute('aria-valuetext', `${used} / ${budget} ${t('common.bytes')}`);
  $$('#briefPresets .chip').forEach((chip) => {
    chip.classList.toggle('is-active', Number(chip.dataset.budget) === budget);
  });

  if (S.briefMode === 'wire') {
    $('#briefBody').hidden = true;
    $('#briefWire').hidden = false;
    $('#briefWire').textContent = data.wire;
    return;
  }
  $('#briefBody').hidden = false;
  $('#briefWire').hidden = true;
  $('#briefBody').innerHTML = briefDocument(packet, data.omitted_claims || []);
}

function briefDocument(packet, omitted) {
  const sections = [];
  const disputed = packet.disputed || [];
  if (disputed.length) {
    sections.push(briefSection(t('brief.disputes'), disputed.length,
      disputed.map((claim) => briefItem(claim, 'disputed')).join('')));
  }

  const topicHtml = (packet.topics || []).map((bucket) => {
    const items = bucket.claims.map((claim) => briefItem({
      ...claim,
      status: '现行',
      tags: claim.tags || [],
    }, 'current')).join('');
    return `<div class="brief-topic">${esc(bucket.topic)}</div>${items}`;
  }).join('');
  if (topicHtml) {
    const total = (packet.topics || []).reduce((sum, bucket) => sum + bucket.claims.length, 0);
    sections.push(briefSection(t('brief.currentClaims'), total, topicHtml));
  }

  const recent = packet.recently_superseded || [];
  if (recent.length) {
    sections.push(briefSection(t('brief.recent'), recent.length,
      recent.map((claim) => briefItem({ ...claim, status: '已过期' }, 'superseded')).join('')));
  }

  if (omitted.length) {
    sections.push(briefSection(t('brief.omittedTitle'), omitted.length,
      omitted.map((claim) => {
        const meta = statusOf(claim);
        return `<div class="brief-item brief-item--omitted">
          <span class="dot ${meta.dot}"></span>
          <div class="brief-item__main">
            <div class="brief-item__text">${esc(claim.text)}</div>
            <div class="brief-item__meta"><span>${esc(claim.claim_id)}</span><span>${esc(claim.topic)}</span></div>
          </div>
          <span class="brief-item__flag">${esc(t('brief.omittedFlag'))}</span>
        </div>`;
      }).join('')));
  }

  const empty = !disputed.length && !topicHtml && !recent.length && !omitted.length;
  return `
    <div class="brief-head">
      <div>
        <p class="brief-title">${esc(t('brief.docTitle'))}</p>
        <p class="brief-sub">${esc(S.state?.scenario?.name || 'Atlas API')} — ${esc(t('brief.docSub'))}</p>
      </div>
      <div class="brief-stats">
        <span class="brief-stat"><strong>${packet.counts.current}</strong> ${esc(statusLabel('current').toLowerCase())}</span>
        <span class="brief-stat"><strong>${packet.counts.disputed}</strong> ${esc(statusLabel('disputed').toLowerCase())}</span>
        <span class="brief-stat"><strong>${packet.counts.superseded}</strong> ${esc(t('status.superseded').toLowerCase())}</span>
      </div>
    </div>
    ${empty ? `<p class="brief-empty">${esc(t('brief.empty'))}</p>` : sections.join('')}
    <div class="brief-foot">
      <span>${esc(packet.status)} · ${num(packet.used_bytes)} / ${num(packet.budget_bytes)} ${esc(t("common.bytes"))} · ${esc(t("brief.omittedCount", { n: num(packet.omitted) }))}</span>
      <span>sha256 ${esc((packet.store_sha256 || '').slice(0, 12))}</span>
    </div>`;
}

function briefSection(title, count, body) {
  return `<section class="brief-section">
    <div class="brief-section__head"><h3>${esc(title)}</h3><span class="line"></span><span class="brief-section__count">${num(count)}</span></div>
    ${body}
  </section>`;
}

function briefItem(claim, statusKey) {
  const meta = statusKey === 'disputed' ? STATUS['有争议'] : statusKey === 'superseded' ? STATUS['已过期'] : STATUS['现行'];
  const tags = claim.tags && claim.tags.length
    ? `<span>${claim.tags.map((t) => '#' + t).join(' ')}</span>` : '';
  return `<div class="brief-item">
    <span class="dot ${meta.dot}"></span>
    <div class="brief-item__main">
      <div class="brief-item__text">${esc(claim.text)}</div>
      <div class="brief-item__meta">
        <span>${esc(claim.claim_id)}</span>
        ${meta.key === 'superseded' && claim.superseded_by ? `<span>→ ${esc(claim.superseded_by)}</span>` : ''}
        ${tags}
      </div>
    </div>
  </div>`;
}

function scheduleBrief() {
  clearTimeout(S.briefTimer);
  S.briefTimer = setTimeout(loadBrief, 120);
}

function setBriefMode(mode) {
  S.briefMode = mode;
  $$('[data-brief-mode]').forEach((btn) => btn.classList.toggle('is-active', btn.dataset.briefMode === mode));
  renderBrief();
}

async function copyWire() {
  if (!S.brief) return;
  try {
    await navigator.clipboard.writeText(S.brief.wire);
    toast(t('toast.wireCopied', { size: formatBytes(S.brief.wire_bytes) }));
  } catch (err) {
    toast(t('toast.copyError'), true);
  }
}

/* ---------------- search ---------------- */
async function runSearch(queryOverride) {
  const query = queryOverride ?? $('#searchInput').value;
  if (queryOverride !== undefined) $('#searchInput').value = queryOverride;
  const include = $('#includeSuperseded').checked;
  const { data } = await api('/api/search?q=' + encodeURIComponent(query) + '&include_superseded=' + (include ? '1' : '0'));
  if (!data.ok) {
    $('#searchSummary').innerHTML = `<span class="search-summary__hint">${esc(data.error || t('search.failed'))}</span>`;
    $('#searchResults').innerHTML = '';
    return;
  }
  S.search = data;
  renderSearch();
}

function renderSearch() {
  const data = S.search;
  const summary = $('#searchSummary');
  if (!data || !data.query) {
    summary.className = 'search-summary';
    summary.innerHTML = `<span class="search-summary__hint">${esc(t('search.defaultHint'))}</span>`;
    $('#searchResults').innerHTML = '';
    return;
  }
  if (!data.total) {
    summary.className = 'search-summary';
    summary.innerHTML = `<span class="search-summary__hint">${esc(t('search.noMatch', { q: data.query }))}</span>`;
    $('#searchResults').innerHTML = `<div class="results-empty">${esc(t('search.noMatchBody'))}</div>`;
    return;
  }
  if (data.mode === 'all') {
    summary.className = 'search-summary ' + (data.stale_in_results ? 'search-summary--warn' : 'search-summary--ok');
    const warning = data.stale_in_results
      ? `<strong>${t('search.blindWarn', { n: data.stale_in_results, total: data.total })}</strong>`
      : `<strong>${esc(t('search.blindClean'))}</strong>`;
    summary.innerHTML = `${esc(t('search.blindHead', { n: data.total }))} ${warning}
      <span class="search-summary__hint">${esc(t('search.blindHint'))}</span>`;
  } else {
    summary.className = 'search-summary search-summary--ok';
    summary.innerHTML = `${esc(t('search.awareHead', { n: data.total }))}
      <span class="search-summary__hint">${esc(data.disputed_in_results ? t('search.awareHint', { n: data.disputed_in_results }) : t('search.awareHintClean'))}</span>`;
  }
  $('#searchResults').innerHTML = data.results.map((result) => {
    const meta = statusOf(result);
    const pill = statusLabel(meta.key);
    const matched = result.matched.length
      ? result.matched.slice(0, 5).map((t) => `<span class="match">${esc(t)}</span>`).join('')
      : '';
    return `<article class="result ${meta.cls === 'superseded' ? 'result--superseded' : ''}">
      <div class="result__rank">${String(result.rank).padStart(2, '0')}</div>
      <div>
        <div class="result__text">${esc(result.text)}</div>
        <div class="result__meta">
          <span class="status-pill status--${meta.cls}">${esc(pill)}</span>
          <code>${esc(result.claim_id)}</code>
          <span>${esc(result.topic)}</span>
          ${result.source ? `<span>${esc(result.source)}</span>` : ''}
          ${result.superseded_by ? `<span>${esc(t('search.supersededBy'))} <code>${esc(result.superseded_by)}</code></span>` : ''}
          ${matched}
        </div>
      </div>
      <div class="result__right">
        <span class="result__score">score ${result.score.toFixed(3)}</span>
      </div>
    </article>`;
  }).join('');
}

/* ---------------- context (RAG) ---------------- */
function enterContext() {
  const rag = S.state?.rag;
  if (rag) {
    $('#contextRagNote').textContent = rag.available
      ? t('context.ragNote', { n: rag.chunks, s: rag.chunks === 1 ? '' : 's', provider: rag.provider,
          seal: t(rag.sealed ? 'context.ragNoteSealed' : 'context.ragNoteUnsealed') })
      : t('context.ragNoteOff');
  } else {
    $('#contextRagNote').textContent = t('context.ragLoading');
  }
  if (!$('#contextQuery').value.trim()) $('#contextQuery').value = 'use sqlite';
  loadContext();
}

async function loadContext() {
  const query = $('#contextQuery').value.trim();
  const body = $('#contextBody');
  if (!query) {
    S.context = null;
    $('#contextStatus').textContent = t('context.defaultEmpty').slice(0, 0) || 'idle';
    body.hidden = false;
    $('#contextWire').hidden = true;
    body.innerHTML = `<p class="brief-empty">${esc(t('context.defaultEmpty'))}</p>`;
    return;
  }
  const intent = $('#contextHistorical').checked ? 'historical' : 'current';
  $('#contextStatus').textContent = '…';
  const { data } = await api('/api/context?q=' + encodeURIComponent(query) +
    '&intent=' + intent + '&max_bytes=4096&top_k=8');
  if (!data.ok) {
    S.context = null;
    $('#contextStatus').textContent = 'error';
    body.hidden = false;
    $('#contextWire').hidden = true;
    body.innerHTML = `<p class="brief-empty">${esc(data.error || t('context.buildError'))}</p>`;
    toast(data.error || t('context.toastError'), true);
    return;
  }
  S.context = data;
  renderContext();
}

function renderContext() {
  const data = S.context;
  if (!data) return;
  const packet = data.packet;
  const counts = packet.brief.counts || {};
  $('#contextStatus').textContent = packet.status;
  $('#ctxUsed').textContent = num(packet.used_bytes);
  $('#ctxBudget').textContent = num(packet.budget_bytes);
  $('#ctxBriefCounts').textContent =
    `${counts.current || 0} ${statusLabel('current').toLowerCase()} · ${counts.disputed || 0} ${statusLabel('disputed').toLowerCase()} · ${counts.superseded || 0} ${t('status.superseded').toLowerCase()}`;
  $('#ctxEvidenceCount').textContent = num(packet.evidence.length);
  $('#ctxOmitted').textContent = num(packet.evidence_omitted);
  const filtered = packet.stale_excluded + packet.unlinked_excluded + packet.unresolved_excluded;
  $('#ctxExcluded').textContent = t('context.filtered', { n: filtered });
  $('#ctxExcluded').title =
    `${packet.stale_excluded} stale · ${packet.unlinked_excluded} unlinked · ${packet.unresolved_excluded} unresolved`;
  $('#ctxWindow').textContent = packet.evidence_provider === 'none'
    ? t('context.briefOnly')
    : t('context.candidates', { n: num(packet.evidence_candidates), c: packet.evidence_attempts,
        cs: packet.evidence_attempts === 1 ? '' : 'es' });
  $('#ctxWindow').title = `candidate window ${packet.evidence_candidate_window}`;
  $('#ctxIndexSha').textContent = packet.evidence_index_sha256
    ? packet.evidence_index_sha256.slice(0, 12) + '…'
    : 'none';
  $('#ctxIndexSha').title = packet.evidence_index_sha256 || '';

  const showWire = $('#contextShowWire').checked;
  $('#contextBody').hidden = showWire;
  $('#contextWire').hidden = !showWire;
  if (showWire) {
    $('#contextWire').textContent = data.wire;
  } else {
    $('#contextBody').innerHTML = contextDocument(packet);
  }
}

function contextDocument(packet) {
  const brief = packet.brief || {};
  const counts = brief.counts || {};
  const evidence = packet.evidence || [];
  const totalBrief = (counts.current || 0) + (counts.disputed || 0) + (counts.superseded || 0);
  const intent = packet.intent || 'current';
  const provider = packet.evidence_provider || 'none';

  const fold = [];
  const disputed = brief.disputed || [];
  if (disputed.length) {
    fold.push(briefSection('Open disputes', disputed.length,
      disputed.map((claim) => briefItem(claim, 'disputed')).join('')));
  }
  const topicHtml = (brief.topics || []).map((bucket) => {
    const items = bucket.claims.map((claim) => briefItem({
      ...claim,
      status: '现行',
      tags: claim.tags || [],
    }, 'current')).join('');
    return `<div class="brief-topic">${esc(bucket.topic)}</div>${items}`;
  }).join('');
  if (topicHtml) {
    const total = (brief.topics || []).reduce((sum, bucket) => sum + bucket.claims.length, 0);
    fold.push(briefSection('Current claims', total, topicHtml));
  }
  const recent = brief.recently_superseded || [];
  if (recent.length) {
    fold.push(briefSection('Recently superseded', recent.length,
      recent.map((claim) => briefItem({ ...claim, status: '已过期' }, 'superseded')).join('')));
  }

  const emptyNote = provider === 'none'
    ? t('context.noProvider')
    : packet.evidence_candidates
      ? t('context.candidatesOnly', { n: num(packet.evidence_candidates) })
      : t('context.noCandidates');

  const policy = [
    `<span class="policy-chip">${esc(t('context.chipCandidates', { n: num(packet.evidence_candidates) }))}</span>`,
    `<span class="policy-chip ${packet.stale_excluded ? 'policy-chip--guard' : ''}">${esc(t('context.chipStale', { n: num(packet.stale_excluded) }))}</span>`,
    `<span class="policy-chip ${packet.unlinked_excluded ? 'policy-chip--guard' : ''}">${esc(t('context.chipUnlinked', { n: num(packet.unlinked_excluded) }))}</span>`,
    `<span class="policy-chip ${packet.unresolved_excluded ? 'policy-chip--guard' : ''}">${esc(t('context.chipUnresolved', { n: num(packet.unresolved_excluded) }))}</span>`,
    `<span class="policy-chip ${packet.per_claim_omitted ? 'policy-chip--warn' : ''}">${esc(t('context.chipQuota', { n: num(packet.per_claim_omitted) }))}</span>`,
    `<span class="policy-chip ${packet.evidence_omitted ? 'policy-chip--warn' : ''}">${esc(t('context.chipBudget', { n: num(packet.evidence_omitted) }))}</span>`,
  ];
  if (provider !== 'none') {
    policy.push(`<span class="policy-chip">${esc(t('context.chipWindow', { n: num(packet.evidence_candidate_window), c: packet.evidence_attempts }))}</span>`);
  }

  const error = packet.evidence_error
    ? `<p class="context-error">${esc(t('context.errorHead', { err: packet.evidence_error }))}</p>`
    : '';

  return `
    <div class="brief-head">
      <div>
        <p class="brief-title">${esc(t('context.docTitle'))}</p>
        <p class="brief-sub">${esc(S.state?.scenario?.name || 'Atlas API')} — ${esc(t('context.authority'))}</p>
      </div>
      <div class="brief-stats">
        <span class="brief-stat"><strong>${evidence.length}</strong> ${esc(t('context.statEvidence'))}</span>
        <span class="brief-stat"><strong>${counts.current || 0}</strong> ${esc(t('context.statCurrent'))}</span>
        <span class="brief-stat"><strong>${esc(intent)}</strong> ${esc(t('context.statIntent'))}</span>
      </div>
    </div>
    <p class="context-layer-note">${esc(t('context.layerNote'))}</p>

    <section class="brief-section">
      <div class="brief-section__head"><h3>${esc(t('context.layer1'))}</h3><span class="line"></span><span class="brief-section__count">${esc(t('context.claimsCount', { n: num(totalBrief) }))}</span></div>
      <div class="context-counts">
        <span class="context-count"><strong>${counts.current || 0}</strong> ${esc(statusLabel('current').toLowerCase())}</span>
        <span class="context-count"><strong>${counts.disputed || 0}</strong> ${esc(statusLabel('disputed').toLowerCase())}</span>
        <span class="context-count"><strong>${counts.superseded || 0}</strong> ${esc(t('status.superseded').toLowerCase())}</span>
        ${brief.omitted ? `<span class="context-count"><strong>${num(brief.omitted)}</strong> ${esc(t('brief.omittedFlag'))}</span>` : ''}
      </div>
      <details class="context-fold">
        <summary><span>${esc(t('context.showBrief'))}</span><span class="context-fold__count">${esc(t('context.claimsCount', { n: num(totalBrief) }))}</span></summary>
        <div class="context-fold__body">${fold.join('') || `<p class="brief-empty">${esc(t('context.emptyBrief'))}</p>`}</div>
      </details>
    </section>

    <section class="brief-section">
      <div class="brief-section__head"><h3>${esc(provider === 'none' ? t('context.layer2off') : t('context.layer2on'))}</h3><span class="line"></span><span class="brief-section__count">${evidence.length} ${esc(t('context.shown'))} · ${num(packet.evidence_omitted)} ${esc(t('context.omitted'))}</span></div>
      <p class="context-layer-note">${provider === 'none' ? esc(t('context.noProvider')) : esc(t('context.providerNote', { provider }))}</p>
      ${error}
      ${evidence.map(evidenceHitCard).join('') || `<p class="brief-empty">${esc(emptyNote)}</p>`}
      <div class="context-policy">${policy.join('')}</div>
    </section>

    <div class="brief-foot">
      <span>${esc(packet.status)} · ${num(packet.used_bytes)} / ${num(packet.budget_bytes)} bytes</span>
      <span>store ${esc((packet.store_sha256 || '').slice(0, 12))} · index ${esc((packet.evidence_index_sha256 || 'none').slice(0, 12))}</span>
    </div>`;
}

function evidenceHitCard(hit) {
  const meta = STATUS[hit.claim_status] || STATUS['现行'];
  const label = hit.historical ? statusLabel('historical') : statusLabel(meta.key);
  const quote = hit.quote
    ? `“${esc(hit.quote)}”`
    : esc(hit.excerpt) + (hit.excerpt_truncated ? '…' : '');
  const score = Number(hit.score);
  return `<article class="evidence-hit evidence-hit--${meta.cls}">
    <div class="evidence-hit__head">
      <span class="status-pill status--${meta.cls}">${esc(label)}</span>
      <span class="evidence-hit__claim">${esc(hit.claim_text)}</span>
      <span class="evidence-hit__score">score ${Number.isFinite(score) ? score.toFixed(3) : '–'}</span>
    </div>
    <blockquote class="evidence-hit__quote">${quote}</blockquote>
    <div class="evidence-hit__meta">
      ${hit.chunk_id ? `<code>${esc(hit.chunk_id)}</code>` : ''}
      <span title="${esc(hit.claim_id)}">→ ${esc(shortId(hit.claim_id))}</span>
      <span>${esc(hit.topic || '')}</span>
      ${hit.source ? `<span>${esc(hit.source)}</span>` : ''}
      ${hit.historical ? `<span class="evidence-hit__flag">${esc(t('context.historicalFlag'))}</span>` : ''}
    </div>
  </article>`;
}

async function copyContextWire() {
  if (!S.context) {
    toast('Build a context packet first.', true);
    return;
  }
  try {
    await navigator.clipboard.writeText(S.context.wire);
    toast(t('context.copyToast', { size: formatBytes(S.context.wire_bytes) }));
  } catch (err) {
    toast('Clipboard is unavailable in this browser.', true);
  }
}

/* ---------------- safety (backup / audit / removal) ---------------- */
async function loadSafety() {
  await Promise.all([renderSafety(), loadBackups(), loadAudit()]);
}

async function renderSafety() {
  const writable = Boolean(S.state?.writable);
  $('#backupBtn').disabled = false;
  $('#backupBtn').title = 'Write a verified snapshot and manifest next to the store';
  $('#backupNote').textContent = writable
    ? t('safety.backupNote')
    : t('safety.backupNoteRo');
}

async function loadBackups() {
  const list = $('#backupList');
  const { data } = await api('/api/backups');
  if (!data.ok) {
    list.innerHTML = `<p class="brief-empty">${esc(data.error || t('safety.listError'))}</p>`;
    return;
  }
  S.backups = data.backups || [];
  if (!S.backups.length) {
    list.innerHTML = `<p class="brief-empty">${esc(t('safety.noBackups'))}</p>`;
    return;
  }
  list.innerHTML = S.backups.map((backup) => `
    <div class="backup-row">
      <div class="backup-row__main">
        <code title="${esc(backup.file_sha256 || '')}">${esc(backup.snapshot)}</code>
        <span class="backup-row__meta">${num(backup.claims ?? 0)} ${esc(t('store.claims'))}${backup.redacted ? ` · ${num(backup.redacted)} ${esc(t('status.redacted'))}` : ''} · ${formatBytes(backup.bytes)} · sha256 ${esc((backup.file_sha256 || '').slice(0, 10))}…</span>
      </div>
      <span class="backup-row__when">${esc(formatWhen(backup.created_at))}</span>
    </div>`).join('');
}

async function backupNow() {
  const button = $('#backupBtn');
  button.disabled = true;
  const { data } = await api('/api/backup', { method: 'POST', body: '{}' });
  button.disabled = false;
  if (!data.ok) {
    toast(data.error || 'Backup failed.', true);
    return;
  }
  toast(t('safety.backupToast', { n: num(data.claims), size: formatBytes(data.bytes) }));
  await Promise.all([loadState({ silent: true }), loadBackups(), loadAudit()]);
}

async function loadAudit() {
  const list = $('#auditList');
  const { data } = await api('/api/audit?limit=20');
  if (!data.ok) {
    list.innerHTML = `<p class="brief-empty">${esc(data.error || t('safety.auditError'))}</p>`;
    return;
  }
  $('#auditCount').textContent = data.total === 1 ? t('safety.oneEntry') : t('safety.nEntries', { n: num(data.total) });
  const entries = data.entries || [];
  if (!entries.length) {
    list.innerHTML = `<p class="brief-empty">${esc(t('safety.noAudit'))}</p>`;
    return;
  }
  list.innerHTML = entries.map((entry) => `
    <div class="audit-row">
      <div class="audit-row__main">
        <span class="audit-row__action audit-row__action--${esc(entry.action)}">${esc(entry.action)}</span>
        <span class="audit-row__ids">${(entry.claim_ids || []).map((id) => `<code>${esc(id)}</code>`).join(' ')}</span>
      </div>
      <div class="audit-row__meta">
        <span>${esc(formatWhen(entry.at))}</span>
        ${entry.actor ? `<span>actor ${esc(entry.actor)}</span>` : ''}
        ${entry.backup_file ? `<span title="${esc(entry.backup_file_sha256 || '')}">backup <code>${esc(entry.backup_file)}</code></span>` : `<span>${esc(t('safety.noBackup'))}</span>`}
      </div>
    </div>`).join('');
}

async function performSafety(action, claimId) {
  const message = t(action === 'delete' ? 'safety.deleteConfirm' : 'safety.redactConfirm', { id: claimId });
  if (!window.confirm(message)) return;
  const { data } = await api('/api/' + action, {
    method: 'POST',
    body: JSON.stringify({ claim_id: claimId, confirm: true, cascade: false }),
  });
  if (!data.ok) {
    toast(data.error || t('safety.actionError', { action }), true);
    return;
  }
  S.state = null;
  S.context = null;
  await loadState({ silent: true });
  const ids = (data.claim_ids || []).join(', ');
  const backupName = data.backup ? data.backup.path : 'no backup retained';
  toast(t('safety.doneToast', { verb: t(action === 'redact' ? 'safety.verbRedact' : 'safety.verbDelete'), ids, file: backupName.split(/[\\/]/).pop() }));
  await loadBackups();
  await loadAudit();
}

/* ---------------- evidence ---------------- */
async function loadEvidence() {
  const { data } = await api('/api/evidence');
  if (!data.ok) {
    toast(data.error || t('evidence.loadError'), true);
    return;
  }
  S.evidence = data;
  renderEvidence();
}

function pct(value) {
  return value === null || value === undefined ? '–' : (value * 100).toFixed(1) + '%';
}
function renderEvidence() {
  const data = S.evidence;
  if (!data) return;
  const methods = data.retrieval.methods || [];
  const dataset = data.retrieval.dataset || {};
  if (dataset.queries) {
    $('#evidenceDataset').textContent = `${dataset.queries} queries · ${dataset.sessions} sessions`;
  }
  const maxRows = methods.map((method, index) => {
    const accent = method.key === 'Status-aware Memory';
    const stale = method.stale5;
    const bar = (value, cls = '') => `<span class="bar ${cls}"><span style="width:${Math.max(0, Math.min(100, value * 100))}%"></span></span>`;
    const methodLabel = method.label;
    return `<div class="mt-row ${accent ? 'mt-row--accent' : ''}">
      <div class="mt-method"><span class="dot ${accent ? 'dot--current' : index === 0 ? 'dot--superseded' : 'dot--evidence'}"></span>${esc(method.label)}</div>
      <div class="mt-cell"><strong>${pct(method.recall1)}</strong>${bar(method.recall1)}</div>
      <div class="mt-cell">${pct(method.recall5)}${bar(method.recall5)}</div>
      <div class="mt-cell">${method.mrr.toFixed(4)}</div>
      <div class="mt-cell ${stale === 0 ? 'mt-cell--good' : 'mt-cell--bad'}"><strong>${pct(stale)}</strong>${bar(stale, 'bar--stale')}</div>
    </div>`;
  }).join('');
  $('#retrievalTable').innerHTML = `
    <div class="mt-row mt-head"><span>${esc(t('evidence.colMethod'))}</span><span>Recall@1</span><span>Recall@5</span><span>MRR@5</span><span>stale-hit@5</span></div>
    ${maxRows}
    <div class="mt-note">status filtering drives stale-hit@5 from 54.2% to 0.0% — at a stated Recall@5 cost (95.8% → 91.7%).</div>`;
  $('#evidenceNote').textContent = data.retrieval.evidence
    ? data.retrieval.evidence + ' · ' + data.retrieval.source_file
    : 'Synthetic fixture · retrieval only · ' + data.retrieval.source_file;

  const summary = data.compilebench.summary || {};
  const cards = [
    {
      value: `${summary.invalid_proposals_blocked ?? 16}/${summary.invalid_proposals_total ?? 16}`,
      label: t('evidence.card1'),
      hint: t('evidence.card1Hint'),
      good: true,
    },
    {
      value: `${summary.exact_budget_passes ?? 16}/${summary.exact_budget_total ?? 16}`,
      label: t('evidence.card2'),
      hint: t('evidence.card2Hint'),
      good: true,
    },
    {
      value: `${summary.stale_served_gate_enabled ?? 0}`,
      label: t('evidence.card3'),
      hint: t('evidence.card3Hint'),
      good: true,
    },
    {
      value: `${summary.stale_served_gate_disabled ?? 4}`,
      label: t('evidence.card3'),
      hint: t('evidence.card4Hint'),
      good: false,
    },
  ];
  $('#compileCards').innerHTML = cards.map((card) => `<div class="compile-card">
    <span class="compile-card__value ${card.good ? 'is-good' : 'is-bad'}">${esc(card.value)}</span>
    <span class="compile-card__label">${esc(card.label)}</span>
    <span class="compile-card__hint">${esc(card.hint)}</span>
  </div>`).join('');

  const limits = (data.compilebench.limits || []).slice(0, 5);
  $('#evidenceLimits').innerHTML = (limits.length ? limits : [
    t('evidence.fallback1'), t('evidence.fallback2'), t('evidence.fallback3'), t('evidence.fallback4'),
  ]).map((limit) => `<li>${esc(limit)}</li>`).join('');

  const sources = [
    ['Retrieval', data.retrieval.source_file, data.retrieval.fixture_sha256],
    ['CompileBench', data.compilebench.source_file, data.compilebench.summary ? (data.compilebench.limits || []).length ? 'fixture + limits' : '' : ''],
    ['Gateway', 'benchmarks/gateway/results.json', data.gateway ? 'model_calls: ' + data.gateway.model_calls : ''],
  ];
  $('#evidenceSources').innerHTML = sources.map(([label, file, hash]) => `
    <div class="source-row"><span>${esc(label)}</span><span><code>${esc(file)}</code>${hash ? ' · ' + esc(String(hash).slice(0, 14)) : ''}</span></div>
  `).join('') + `<div class="source-row"><span>${esc(t('evidence.everyFixture'))}</span><span><code>${esc(t('evidence.synthetic'))}</code></span></div>`;
}

/* ---------------- wiring ---------------- */
function bind() {
  $('#nav').addEventListener('click', (event) => {
    const button = event.target.closest('[data-view]');
    if (button) navigate(button.dataset.view);
  });
  $$('[data-goto]').forEach((button) => button.addEventListener('click', () => navigate(button.dataset.goto)));
  $('#storyBtn').addEventListener('click', () => {
    if (!S.state?.writable) {
      toast(t('toast.readOnlyShort'), true);
      return;
    }
    navigate('record');
    setTimeout(() => {
      fillExample('conflict');
      toast(t('toast.storySubmit'));
    }, 30);
  });

  $('#fText').addEventListener('input', updateFormCount);
  $('#recordForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!S.state?.writable) {
      showError(t('record.readOnly'));
      return;
    }
    hideError();
    const payload = formPayload();
    if (!payload.text) { showError(t('record.needText')); return; }
    await submitRecord(payload);
  });
  $('#exampleChips').addEventListener('click', (event) => {
    const chip = event.target.closest('[data-example]');
    if (chip) fillExample(chip.dataset.example);
  });
  $('#suggestBtn').addEventListener('click', previewSuggestion);

  $('#conflictSupersede').addEventListener('click', async () => {
    if (!S.pendingRecord || !S.conflictData) return;
    const targets = S.conflictData.suggested_supersedes || [];
    if (!targets.length) return;
    await submitRecord(S.pendingRecord, { supersedes: targets, source: 'conflict' });
  });
  $('#conflictDispute').addEventListener('click', async () => {
    if (!S.pendingRecord) return;
    await submitRecord(S.pendingRecord, { dispute: true, source: 'conflict' });
  });
  $$('[data-close-conflict]').forEach((el) => el.addEventListener('click', closeConflict));
  document.addEventListener('keydown', (event) => {
    const modal = $('#conflictModal');
    if (event.key === 'Escape' && !modal.hidden) closeConflict();
    if (event.key === 'Tab' && !modal.hidden) {
      const focusable = Array.from(modal.querySelectorAll('button:not([disabled]), [href], input:not([disabled]), textarea:not([disabled])'))
        .filter((element) => element.offsetParent !== null);
      if (focusable.length) {
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    }
    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter' && S.view === 'record') {
      $('#recordForm').requestSubmit();
    }
  });

  $('#briefBudget').addEventListener('input', (event) => {
    S.briefBudget = Number(event.target.value);
    $('#briefBudgetLabel').textContent = num(S.briefBudget) + ' bytes';
    scheduleBrief();
  });
  $('#briefPresets').addEventListener('click', (event) => {
    const chip = event.target.closest('[data-budget]');
    if (!chip) return;
    S.briefBudget = Number(chip.dataset.budget);
    $('#briefBudget').value = String(S.briefBudget);
    $('#briefBudgetLabel').textContent = num(S.briefBudget) + ' bytes';
    loadBrief();
  });
  $$('[data-brief-mode]').forEach((btn) => btn.addEventListener('click', () => setBriefMode(btn.dataset.briefMode)));
  $('#briefCopy').addEventListener('click', copyWire);

  $('#searchForm').addEventListener('submit', (event) => {
    event.preventDefault();
    runSearch();
  });
  $('#searchSuggestions').addEventListener('click', (event) => {
    const chip = event.target.closest('[data-query]');
    if (chip) runSearch(chip.dataset.query);
  });
  $('#includeSuperseded').addEventListener('change', () => {
    if ($('#searchInput').value.trim()) runSearch();
  });

  $('#contextForm').addEventListener('submit', (event) => {
    event.preventDefault();
    loadContext();
  });
  $('#contextSuggestions').addEventListener('click', (event) => {
    const chip = event.target.closest('[data-query]');
    if (!chip) return;
    $('#contextQuery').value = chip.dataset.query;
    loadContext();
  });
  $('#contextHistorical').addEventListener('change', () => {
    if ($('#contextQuery').value.trim()) loadContext();
  });
  $('#contextShowWire').addEventListener('change', () => {
    if (S.context) renderContext();
  });
  $('#contextCopy').addEventListener('click', copyContextWire);

  $('#backupBtn').addEventListener('click', backupNow);
  $('#ledgerTopics').addEventListener('click', (event) => {
    const button = event.target.closest('[data-safety]');
    if (button) performSafety(button.dataset.safety, button.dataset.claim);
  });

  $('#resetBtn').addEventListener('click', async () => {
    if (!confirm(t('toast.resetConfirm'))) return;
    const { data } = await api('/api/reset', { method: 'POST', body: '{}' });
    if (!data.ok) { toast(data.error || 'Reset failed.', true); return; }
    S.state = data;
    S.brief = null;
    S.search = null;
    renderChrome();
    renderLedger();
    renderRecordSide();
    $('#recordReceipt').hidden = true;
    $('#suggestPanel').hidden = true;
    S.proposal = null;
    S.context = null;
    hideError();
    if (S.view === 'brief') loadBrief();
    if (S.view === 'search') { $('#searchInput').value = ''; S.search = null; renderSearch(); }
    if (S.view === 'context') enterContext();
    if (S.view === 'safety') loadSafety();
    toast(t('toast.resetDone'));
  });

  window.addEventListener('hashchange', () => applyView(location.hash.replace('#', '') || 'ledger'));
}

async function init() {
  bind();
  $('#langBtn').addEventListener('click', () => {
    LANG = LANG === 'zh' ? 'en' : 'zh';
    localStorage.setItem(LANG_KEY, LANG);
    applyI18n();
  });
  applyI18n();
  const hash = location.hash.replace('#', '');
  applyView(document.querySelector(`[data-view-panel="${hash}"]`) ? hash : 'ledger');
  await loadState();
  if (S.view === 'evidence') loadEvidence();
  if (S.view === 'brief') loadBrief();
  if (S.view === 'context') enterContext();
  if (S.view === 'safety') loadSafety();
}

document.addEventListener('DOMContentLoaded', init);
