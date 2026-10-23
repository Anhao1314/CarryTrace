# ClaimLedger 重构设计 v1

| | |
| --- | --- |
| 状态 | 已采纳；v2 修订见 §9 |
| 日期 | 2026-10-20 |
| 分支 | `refactor/design` |
| 基线 | upstream `Anhao1314/ClaimLedger@68542ef`（runtime 0.4.0，24 commits） |
| 范围 | 架构重构设计，不含具体实现 |

---

## 0. 摘要

原项目最值钱的赌注是：**确定性代码管结构与完整性，语义判断交给宿主 Agent**。本次重构不推翻这个赌注，只解决三件让它在真实使用中变慢的事：

1. **存储倒置** —— JSONL 成为唯一权威，Markdown 从"受管投影"降级为"可选导出"。
2. **协议做薄** —— 身份概念从六套收敛到三套，Gateway 的 plan/proposal 包装层隐式化。
3. **来源覆盖** —— Connector 改为声明式 Source Profile，首先支持 Claude Code / Codex 的本地会话，让"接续"承诺对主要用户成立。

按 P0→P3 分四个阶段落地，每阶段测试全绿、可独立发布、可回滚。

---

## 1. 现状诊断（证据版）

### 1.1 代码盘点

| 区域 | 行数 | 占比 | 说明 |
| --- | ---: | ---: | --- |
| Markdown 投影维护 | 1,282 | 28% | `render_notes.py` 929 + `lint_notes.py` 347 + `note_identity_issues` 约 40 |
| 身份注册与别名 | 306 | 7% | `memory_identity.py`：display_id / note_name / active / 路径投影 |
| Context Gateway | 554 | 12% | `gateway/core.py` 414 + `config.py` 73 + `cli.py` 60 |
| Wiki | 706 | 16% | store / storage / contracts / cli |
| Connector 与适配 | 475 | 11% | `doubao.py` 105 + `doubao_work.py` 220 + `transcript.py` 165 + `generic_jsonl.py` 90（实际执行路径只有 doubao） |
| Skill 安装与品牌迁移 | 592 | 13% | `skill_installer.py` 253 + `brand_skill.py` 320 + `brand_cli.py` 19 |
| 其余（store/recovery/检索/CLI 骨架） | ~490 | 11% | |
| **包合计** | **4,503** | | 测试 2,987 行，tools+benchmarks 1,379 行 |

结构性事实：**35% 的包代码（1,588 行）在维护"派生 Markdown 副本与 JSON 权威一致"和三套身份别名**。这些代码解决的是自我制造的一致性问题。

### 1.2 必须保留的核心资产

- **分层赌注**：`store.py` 的 MemoryStore 是纯验证/检索 facade，从不产生语义判断。
- **字节预算的定点收敛**：`recovery.py:10-17` 的 `_measure` 用不动点迭代让 `used_bytes` 收敛，包内三处实现一致。
- **不可信数据框架**：packet 内嵌 `trust: "untrusted_memory_data_not_instructions"`，SKILL.md 全程防提示注入。
- **fail-closed 完整性**：快照前后比对、原子写、拒绝符号链接、拒绝覆盖非托管目录。
- **零依赖、零网络、无常驻进程**：`pyproject.toml` `dependencies = []`，全库无 HTTP 客户端。
- **验证文化**：289 个测试、`verify_docs.py` 执行 README 全部命令、benchmark 结果带 fixture SHA-256 与局限性清单。

### 1.3 核心负债（五项，按严重度排序）

**L1 检索读路径依赖渲染器。** `_internal/query_memory.py:80-89`：为了读索引，先在 dry 模式重跑一次渲染器，把捕获输出与磁盘文件逐字节比对，不一致就拒绝检索（"rerender before querying"）。一个本地记忆库的**读操作**被挂在 Markdown 渲染的确定性上——渲染器 929 行里任何一次输出格式微调都会让全部检索失效。

**L2 整源哈希失效策略误伤。** `wiki/store.py:84-85、144-149`：proposal 绑定整源 `source_sha256`，任何无关卡片的修改都会让所有 wiki 页 stale。`_freshness` 里的 per-dependency 比对只用来事后解释"为什么 stale"，不影响判定。

**L3 Gateway apply 协议过重。** `gateway/core.py:209-229`：apply 要求 Agent 递回 `gateway_schema_version` / `plan_sha256` / `covered_sessions` / `retire_memory_ids` 四层包装，再做六项交叉校验。这是为"Agent 幻觉 + 源中途变化"设计的重机械，但单用户本地工具里，sync 已经把 pending 计划写进 state 文件——绑定关系可以隐式获得，不需要让 Agent 搬运哈希。

**L4 内部 API 走 CLI 表面。** `gateway/core.py:48-58`：Gateway 调渲染器的方式是**篡改 `sys.argv`、劫持 stdout、捕获 SystemExit**。模块边界是 CLI 形状的，不是 API 形状的——这是后续任何重构都要先拆的雷。

**L5 来源覆盖与目标用户错位。** `gateway/core.py:96`：`connector != "doubao"` 直接抛错；`connectors/doubao.py:18-39` 硬编码豆包 Work 三个平台的缓存路径。而 README 的目标场景（接续 Codex / Claude Code 的活）没有任何自动来源。另外目录名"对话沉淀/会话笔记/知识卡片"散布在 `store.py:24`、`cli.py:41`、`memory_identity.py:137,237` 等处，硬编码中文。

小项：`tests/test_brand_migration.py:83,233` 未 resolve 路径，macOS 上 2/289 失败（CI 只跑 ubuntu 掩盖了）；`gateway/core.py:357` 魔法数 0.68 的结构化/原始预算切分无文档。

---

## 2. 设计原则

1. **结构与判断分离不动摇。** 代码负责：身份、状态机、预算、完整性、并发写保护。Agent 负责：蒸馏、综合、真伪复核。
2. **单一权威。** 任何时刻每个事实只有一个权威存储；其它一切是可丢弃、可重建的投影。
3. **fail-closed 不放松。** 迁移、协议简化不降低现有的损坏拒绝标准。
4. **兼容是承诺不是负担。** 旧入口保留到 1.0；数据迁移一律 preview-first + 备份 + 可回滚（沿用 brand_skill.py 已有的锁与备份模式）。
5. **每阶段独立可发布。** 禁止跨阶段耦合；测试全绿才合入。
6. **零依赖是特性。** 引入任何运行时依赖都需要在本文档修订中专门论证。

---

## 3. 目标架构

```
                    ┌─────────────────────────────────────────┐
  本地会话来源       │  Source Profiles（P2，声明式）            │
  claude_code ─────▶│  discover / sessions / fingerprint /     │
  codex ───────────▶│  extract，fail-closed 解析契约            │
  doubao ──────────▶│                                          │
  generic_jsonl ───▶└───────────────┬─────────────────────────┘
                                    │ sync（增量、指纹）
                                    ▼
┌───────────────────────────────────────────────────────────────┐
│  权威存储（P1）                                                 │
│  memory.jsonl —— 每行一个对象（会话摘要 / 卡片），自带           │
│  {memory_id, status, superseded_by, card_sha256, ...}          │
│  pending/ 蒸馏计划 · wiki-state.json 页与版本                   │
└──────────┬──────────────────────────────┬─────────────────────┘
           │ 确定性检索（P1）              │ 可选 reranker 插件（P3，默认 no-op）
           ▼                              ▼
┌──────────────────────────┐   ┌───────────────────────────────┐
│  检索与恢复包             │   │  交付通道                      │
│  lexical recall（现有）   │   │  CLI（核心）· MCP stdio（P3）  │
│  字节预算 packet（现有）   │   │  Skill 指令包（现有）          │
└──────────────────────────┘   └───────────────────────────────┘
           │
           ▼  纯导出，随时可重建、可丢弃
   markdown/（Obsidian 兼容快照 + manifest，不再受管、不再 lint）
```

变化要点：原 `render → lint → load_index(再渲染比对)` 的闭环被打断；Markdown 只从权威单向流出。检索读路径直接吃 `memory.jsonl`。

---

## 4. 阶段计划

### P0 卫生与基线（0.5~1 天，零行为变更）

| 改动 | 文件 | 内容 |
| --- | --- | --- |
| 修 macOS 测试 | `tests/test_brand_migration.py:83,233` | 断言前对两侧路径 `resolve()`，或改比较 `relative_to` 前统一；修出第 289 个测试的价值 |
| CI 加 macOS | `.github/workflows/tests.yml` | 矩阵加 `macos-latest`；以后平台性回归不再靠运气 |
| 魔法数文档化 | `gateway/core.py:357` | 0.68 拆分加注释说明结构与原始层的预算权衡 |
| 路径常量集中 | 移入 P1 | P1 将重写承载这些常量的文件，先行集中只会制造双重 diff；随新存储层一并收敛为 `_internal/paths.py` |

**验收**：macOS 本地 289/289；CI 矩阵全绿；diff 无行为变更。

### P1 存储倒置与协议做薄（核心，1~2 周）

目标：删掉"自我制造的一致性问题"。这是唯一带数据迁移的阶段，也是收益最大的一阶段。

**改动清单**

1. **新权威存储 `memory.jsonl`**（替代 `.chat-distiller/distill.json` 单一大 JSON）：
   - 每行一个对象（conversation 或 card），自带全部字段：`memory_id`、`status`、`superseded_by`、`related`、`card_sha256`（规范 JSON 的 SHA-256）。
   - **路径常量收敛**（自 P0 移入）：中文目录名随存储层重写集中到 `_internal/paths.py`，默认值不变。
   - **身份收敛**：删除 `display_id`、`note_name`、`identity_registry`、`active` 标志。稳定身份只剩 `memory_id` 与 `superseded_by` 链；文件名成为导出层临时产物，不再参与校验。`memory_identity.py` 306 行预计缩至 <100 行（保留 ID 格式校验、supersession 环检测、原子写）。
   - ** retire 语义反转**：增量更新中"新源缺席的活跃卡"默认自动转 `已过期`（superseded_by 可选指向替代卡），`--keep <id>` 显式豁免。比让 Agent 递回 retire 集合更安全。
2. **Markdown 降级为导出**：
   - `render` → `export --format markdown`：单向生成快照 + manifest，输出到 `export/` 子目录，不再写回 vault 管理区。
   - `lint_notes.py` 347 行**整体删除**（漂移不复存在）；`note_identity_issues` 删除。
   - `load_index`（`query_memory.py:69-94`）改为直接读 `memory.jsonl` + 校验每行 schema 与 `card_sha256`，**删除 dry-render 比对**。检索读路径不再触碰渲染器。
   - Obsidian 用户：导出包含原有 MOC/链接结构，manifest 标注 `point_in_time_export_not_live_authority`（沿用 wiki export 的既有措辞）。
3. **Wiki 失效改 per-card 绑定**（`wiki/store.py`）：
   - proposal 的 `source_sha256` → `scope_hashes`（scope 内每卡的 `card_sha256` 字典）。
   - `_freshness`：只比对自己依赖的卡；无关修改不再产生 stale。`_snapshot:28` 的 fresh-页依赖校验同步简化。
   - 保留 `wiki_revision` 乐观并发与双检锁写（`storage.writer()`）。
4. **Gateway apply 隐式绑定**（`gateway/core.py`）：
   - 删除 `_load_apply_wrapper` 的四层包装契约；apply 直接吃 distill JSON。
   - 绑定改隐式：sync 把当次指纹写入 state，apply 时源指纹或 pending 集合已变即拒绝（错误信息指引重新 sync）。等价安全性，协议从"Agent 搬运哈希"变为"代码自查"。
   - `_render` 的 `sys.argv` 劫持（`core.py:48-58`）替换为直接函数调用——渲染器内部逻辑导出为可 import 的 API，`main()` 只是薄壳。
5. **迁移脚本 `claim store migrate`**：preview-first（默认 dry-run 报告变更）、备份到 `.chat-distiller/backup-v3/`、迁移后旧文件保留只读（不删）；失败可整目录回滚。`CHAT_DISTILLER_HOME`、`~/.chat-distiller` 路径不变。

**不动的**：`recovery.py` packet 结构（schema_version 2 保持）、`MemoryStore` 公开 API 签名、skill 安装器、wiki 的编译/recover 语义。

**验收**：
- 全测试套件通过（含 macOS），新存储的往返/损坏/并发用例 ≥30 个；
- `verify_install.py` 在隔离 wheel 上跑通新命令面；
- wiki stale 误伤用例：修改无关卡片后 `wiki status` 报 fresh（对照基线为 stale）；
- 迁移脚本对 0.4.0 合成库往返迁移零身份丢失（用 benchmark fixture 验证）；
- 渲染器相关代码净减 ≥600 行。

### P2 来源覆盖（价值最大，1 周）

目标：让"接续"对 Codex / Claude Code 用户成立。

**改动清单**

1. **声明式 Source Profile**（新 `connectors/base.py`）：从 `connectors/doubao.py` + `doubao_work.py` 归纳接口——
   `discover() -> Path`、`sessions(root) -> [SessionDir]`、`fingerprint(root, s)`、`extract(s, out) -> Record`。doubao 迁移为第一个 profile，行为零变更。
2. **内置三个新 profile**：
   - `claude_code`：`~/.claude/projects/**/*.jsonl` 会话转录（本来就是本地 JSONL，解析成本低；按项目路径聚合 session）。
   - `codex`：`~/.codex/sessions/` 滚动 JSONL。
   - `generic_jsonl`：现有公共契约提升为 profile。
   - 每个解析器 fail-closed：不认识的行跳过并计 degraded，绝不猜测字段含义（沿用 `transcript.py` 契约）。
3. **`connect` 通用化**：`claim connect <profile> [--sessions-root PATH]`；`gateway/core.py:96` 的 doubao-only 检查删除，状态/config 增加 `profile` 字段。
4. **隐私边界写进 SKILL.md**：连接新来源需显式确认；`context` 包保持 `trust` 声明与字节预算（原样复用）。

**验收**：三平台 profile 有合成 fixture 测试（脱敏样例，不含真实转录）；gateway delta benchmark 在 doubao profile 上与 P1 基线零差异；`connect claude_code` 在真实本机 discovery 冒烟通过（人工确认）。

### P3 检索两级化与 MCP 通道（增量，1 周）

1. **reranker 插件接口**：`claim recover --rerank <name>`。默认 `none`（纯词法，现状）；接口约定 `rerank(query, candidates) -> ordered candidates`，宿主 Agent 重排作为文档化约定（SKILL.md 指引：先取 top-20 候选再人工/Agent 复核），不引入模型依赖。
2. **`claim mcp`**：stdio MCP 服务器，暴露 `search / get / recover / context` 四个只读工具。实现是现有函数的薄壳（复用 MemoryStore / KnowledgeStore / Gateway），约 150 行。CLI 仍是核心；MCP 解决"宿主不能跑 shell"的场景。
3. **Skill 包更新**：WORKFLOWS/BOUNDARIES 增加 MCP 与 reranker 指引；安装器 bundle 哈希自然更新。

**验收**：MCP 服务器与 Claude Code / ZCode 冒烟联通；`--rerank none` 与基线 packet 逐字节一致（保证零回归）；新增依赖 = 0。

---

## 5. 兼容性承诺

- `chat-distiller` / `chat_distiller` / `claim` 三个入口全程保留；旧子命令在 1.0 前不删。
- `CHAT_DISTILLER_HOME` 与 `~/.chat-distiller` 数据根目录不变。
- packet JSON 的 `schema_version` 递增时保留旧字段读取能力。
- 所有数据迁移：默认 dry-run、显式 apply、迁移前备份、可整目录回滚。
- 零运行时依赖、零网络调用、无常驻进程，全程不破。

## 6. 风险与对策

| 风险 | 对策 |
| --- | --- |
| P1 数据迁移丢失身份 | 迁移脚本用 benchmark fixture 做往返测试；备份先行；旧文件保留只读 |
| Markdown 降级影响 Obsidian 用户 | export 保留全部结构（MOC/链接/状态标注），能力不缩水，只是不再受管 |
| Claude Code / Codex 格式随版本漂移 | profile 版本化 + degraded 计数；解析失败显式报告而非静默丢弃 |
| retire 默认语义改变行为 | 迁移文档单独成节；`--keep` 提供显式豁免；首次 apply 输出 retired 清单供复核 |
| 单人维护带宽 | P1/P2/P3 各自独立分支独立 PR，任何阶段可暂停 |

## 7. Non-goals

不做：内置向量检索/内嵌 embedding、后台 daemon 或文件监听、托管 Web UI、多机同步、事实真伪判定、PyPI 之外的发布渠道。后续的本地 `claim demo` 是同一存储上的一次性单用户视图，不属于托管 Web UI。可选的 RAG evidence adapter 只作为读取时的证据层接入，索引派生可重建，claim store 仍是唯一权威；语义质量的提升路径仍是"宿主 Agent 判断 + 更好的证据包"，不是更多基础设施。

## 8. 决策依据

P1 先于 P2：新来源若先接入旧存储，等于给 Markdown 投影体系增加双倍迁移成本。P3 最后：纯增量、无数据变更，随时可独立启动。诊断证据全部来自基线 commit `68542ef` 的实际代码（本文 1.3 节 file:line 可复核）。

---

## 9. v2 修订：声明管道为第一增量（2026-10-20）

§0–§8 是 v1 设计；本节记录采纳后的第一次战略修订。修订依据：记忆系统的质量上限由写路径决定，而非读路径——"事后蒸馏 + 检索"把最贵的语义工作放在了最容易腐烂的环节（pending 队列）。

**核心转向**：从"事后蒸馏 + 检索"改为"**即时捕获 + 实时简报**"。决策发生的当下，Agent 用 `record` 写入一条声明；新会话开始时注入 `brief`——由声明库确定性派生、字节预算硬约束的项目现状简报。事后蒸馏降级为回填手段。

**本修订落地内容**：

- `chat_distiller/claims.py`：
  - `ClaimStore`：单文件严格 JSONL，每次读取全量校验；损坏行带行号拒绝服务，绝不带病检索。
  - `record`：就地捕获。词法重叠标记**疑似冲突**——拒绝静默并存，要求显式 `--supersedes <id>`（替代旧声明）或 `--dispute`（记为有争议）。冲突检测是确定性词法近似，只能"摊开"不能"判定"；语义矛盾仍需 Agent 或人复核。
  - `brief`：字节预算硬契约。顺序固定：未决争议（不确定性最先可见）→ 按主题的现行声明 → 最近的被替代项（防复活旧结论）。
  - `claims`：列表与查询，状态/主题/词面过滤。
- 双 CLI 入口（`claim` / `chat-distiller`）同时支持三个命令；SDK 导出 `ClaimStore`。
- 存储默认为项目级 `.claim-ledger/claims.jsonl`，与 `~/.chat-distiller`（用户级 Gateway）和记忆 vault 相互独立，零迁移。

**优先级修订**：

- P1 存储倒置改为**在声明库上进行**：声明模型即 v1 目标存储的落地形态，记忆引擎卡片体系后续并入（§4-P1 的身份收敛与协议做薄不变）。
- P2 来源解析**降级为回填路径**：捕获优先模型下，声明库本身就是跨 Agent 交接媒介，不再依赖解析对方转录。
- P3 的 MCP **升为主要分发通道**：`brief` / `record` / `claims` 以工具而非 shell 命令的形态存在。（已落地：`claim mcp`，零依赖 JSON-RPC stdio；store 启动时绑定，工具不能寻址任意路径。）
