# The interactive demo

`claim demo` starts a local, zero-dependency browser UI over the real
`ClaimStore`. It exists to make the lifecycle visible: a conflicting write is
refused, a supersession is an explicit human choice, and a brief reports the
bytes it omitted.

It is not a second implementation. The browser calls the same store, validation,
conflict matcher and byte-budget renderer as the CLI and MCP server.

```bash
python -m pip install -e .
claim demo
# ClaimLedger demo
#   http://127.0.0.1:8765/
#   store: disposable demo store (synthetic Atlas scenario)
```

No model key, network call, database or third-party package is needed. The demo
seeds a synthetic Atlas API project into a temporary directory and deletes it on
exit. It never reads or writes `.claim-ledger/claims.jsonl` unless you pass
`--store` explicitly. A supplied store is **read-only by default** and is never
seeded implicitly; `--write` is the explicit opt-in for recording.

## Options

| Flag | Meaning |
| --- | --- |
| `--store PATH` | Bind an existing `claims.jsonl`. The UI is **read-only by default**, `Reset` is disabled, and the store is never seeded implicitly. |
| `--write` | Allow recording into a store supplied with `--store`. |
| `--seed` | With `--store --write`, explicitly seed an empty bound store with the synthetic scenario. |
| `--port N` | Default `8765`; `0` chooses a free port. |
| `--no-open` | Do not launch a browser automatically. |
| `--no-seed` | Start the disposable demo store empty instead of loading the synthetic scenario. |
| `--host` | Default `127.0.0.1`. Do not expose the demo on an untrusted network: it has no authentication. |

The same UI is available from the checkout without installing the console script:

```bash
python -m chat_distiller.demo --no-open
```

## The 60-second tour

1. **Ledger.** Ten claims across six topics: five current, three disputed, two
   superseded. The `database` and `auth` topics each keep their predecessor
   with a `superseded_by` pointer.
2. **Record → conflict.** Open **Record**, choose **Conflicting decision** and
   submit. The text overlaps the current PostgreSQL claim, so the write is
   refused before it touches the store. Nothing is written until you choose
   **Supersede** or **Record as disputed**. **Preview proposal** runs the same
   conflict check plus status-filtered evidence and returns a review-only
   proposal; it never writes, and its panel says so.
3. **Supersede.** Confirm the replacement. The old PostgreSQL claim becomes
   superseded, the new SQLite claim becomes current, and the store SHA-256 in
   the sidebar changes. This is a real JSONL write. If a write overlaps several
   current claims, the dialog supersedes every detected conflict together; a
   partial supersede is refused by the store.
4. **Brief.** Open **Brief**, drag the budget to 1 KB. The packet is still
   deterministic and still within budget; six entries are omitted and listed as
   omitted, not silently dropped. Switch to **Wire JSON** to see the exact
   serialized packet.
5. **Search.** Query `use sqlite`. Turn on **Include superseded** to rank with
   no lifecycle awareness: the superseded SQLite decision is the top lexical
   match. Turn it off to filter superseded claims before ranking and surface
   disputed ones.
6. **Context.** Open **Context** and build `use sqlite`. The packet joins the
   deterministic brief with one status-checked evidence hit and reports
   `1 filtered` — the superseded SQLite passage was retrieved, then excluded.
   Turn on **Historical intent** to include that passage as `Historical`
   instead. Expand **Show the brief contents** to compare the authority layer
   with the evidence layer; open **Wire JSON** to see the exact bytes. The
   demo ships a synthetic evidence index both in the checkout and in the
   installed package.
7. **Evidence.** The benchmark table and CompileBench cards are read from
   `benchmarks/*/results.json` when present, with the README figures as a
   fallback. Nothing is synthesized at request time.

## What is real, what is synthetic

| Part | Status |
| --- | --- |
| `ClaimStore.record` / `brief` / `claims`, validation, conflict matching, byte accounting | Real code paths, the same as CLI and MCP |
| HTTP API and browser UI | Real, but deliberately single-user and local |
| Atlas API claims, sources and quotes | Synthetic, handwritten demo data |
| RAG evidence chunks | Synthetic passages, joined to the seeded claim ids; status filtering is the real engine |
| Conflict example | Real lexical matcher output over the synthetic claim; no semantic model |
| Benchmark numbers | Checked-in fixtures and reports; synthetic, zero model calls |
| Model calls | Zero in the engine, the demo and the asset build |

The demo is a demonstration of lifecycle mechanics, not a measurement of
semantic truth, agent task success or distillation quality.

## HTTP API

The UI is a static page plus a small JSON layer. These routes are stable enough
to script a tour or a screenshot capture:

| Route | Purpose |
| --- | --- |
| `GET /api/state` | Claims, counts, topics, store digest, examples |
| `POST /api/record` | Record/supersede/dispute; `409` with conflict details, `403` when read-only |
| `GET /api/brief?max_bytes=N` | Byte-bounded packet, wire form, omitted claims |
| `GET /api/search?q=...&include_superseded=0\|1` | Status-aware or status-blind ranking |
| `GET /api/context?q=...&intent=current\|historical` | Brief + status-filtered evidence packet; `max_bytes` defaults to 4096 |
| `POST /api/suggest` | Review-only claim proposal with conflicts and evidence; never writes |
| `GET /api/evidence` | Benchmark reports when present |
| `POST /api/reset` | Restore the synthetic demo store (disposable mode only; `403` otherwise) |

All routes bind to localhost by default and set `Cache-Control: no-store`.

## Rebuild the screenshots and GIF

The checked-in images under `assets/demo/` were captured from the running demo
at 1440×960. The GIF composition script is not a runtime dependency; it needs
Pillow only when rebuilding assets:

```bash
python -m pip install pillow
python tools/build_demo_gif.py
```

This writes `assets/demo/claimledger-demo.gif` and
`assets/demo/social-preview.png` from the existing PNGs. It does not call a
model. The GIF uses seven frames: ledger, conflict, brief, search, context,
evidence and chain. Re-capture the six view screenshots after UI changes so
the GIF and README stay honest.

## Publish the landing page

`site/` is a self-contained static page (no external fonts, trackers or
network requests). The included workflow deploys it to GitHub Pages on every
push to `main`:

```text
.github/workflows/pages.yml → actions/upload-pages-artifact (site/) → actions/deploy-pages
```

One-time repository setting: **Settings → Pages → Build and deployment →
Source: GitHub Actions**. Then the page is available at
`https://anhao1314.github.io/ClaimLedger/`.

You can preview it locally without Python:

```text
Open site/index.html in a browser.
```

The language toggle (`EN / 中文`) is local-only and remembered in
`localStorage`. Append `?lang=zh` or `?lang=en` to force a language for a
screenshot or a shared link.

## Boundaries

- Single local user, no authentication. Concurrent writes are serialized by the
  claim-store writer lock, but the HTTP surface is not a multi-tenant server.
- `--store` opens a real ledger read-only by default. `--write` is an explicit
  opt-in; there is no undo beyond the underlying file and no automatic backup.
- The demo does not install the Skill, run MCP, call a model or import
  conversations.
- The HTTP API is a demo surface, not a stable public API contract.

---

## 中文速览

`claim demo` 用零依赖的 Python 标准库启动一个本地浏览器界面，直接调用真实的
`ClaimStore`：冲突拒写、显式取代、字节预算简报、状态感知检索都是真实代码路径，
不是前端假动画。

```bash
python -m pip install -e .
claim demo        # http://127.0.0.1:8765
```

演示会把一个合成的 Atlas API 项目写入临时目录，退出即删除，不碰真实账本。传
`--store` 默认只读打开已有存储，且不会隐式灌入演示数据；要写入必须再加
`--write`（显式 seed 还需 `--seed`）。演示没有鉴权，只应监听本机。

60 秒路径：在 **Record** 提交预填的冲突决策 → 被拒绝 → 显式取代 → 到 **Brief**
把预算拉到 1 KB，看六条被省略并计数 → 到 **Search** 关闭状态过滤，看已过期的
SQLite 决策排到第一 → 到 **Evidence** 查看可复现的基准数字。

截图与 GIF 由实际运行的演示生成；重建素材需要 Pillow（仅构建时，不是运行依赖）：

```bash
python -m pip install pillow
python tools/build_demo_gif.py
```

产品落地页在 `site/`，推送到 `main` 时由 `.github/workflows/pages.yml` 部署；
需在仓库 Settings → Pages 中把 Source 设为 GitHub Actions。
