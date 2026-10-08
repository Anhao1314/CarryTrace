# Supported flows | carrytrace Agent Skill

## 1. Resume work using the existing Doubao Gateway

Prerequisites: an authorized Doubao Work cache, one-time local `carrytrace connect doubao` completed.

```bash
carrytrace status --json
carrytrace sync --json
carrytrace context "continue the robot navigation experiment" --max-bytes 8192 --json
```

`sync` creates an incremental review plan and local staged extracts; it does **not** publish semantic memory. The Skill can invoke these commands in an accessible local shell, rather than asking the user to paste command output. If the source is not authorized, request consent before connecting or refreshing.

## 2. Handoff from Doubao Work to Codex / Claude Code

Install this same Skill in the destination host. That host needs the CLI installed and local filesystem access to the previously authorized Gateway home, or a user-provided safe exported packet. It does not read other tools' remote/private history by magic.

With consent, call `carrytrace context "<current task>" --json`. Present current decisions, constraints, open questions and source identifiers; keep pending/raw evidence flagged `requires_review`. Ask before sharing a private packet with another host or provider.

## 3. Review an earlier choice or a displaced design

With an existing vault path supplied by the user:

```bash
carrytrace inspect --vault "<vault>"
carrytrace recover --vault "<vault>" --query "previous database choice" --intent historical --max-bytes 8192
carrytrace wiki status --vault "<vault>"
```

Historical retrieval can include superseded and disputed information. It does not mean old choices are current. For `wiki status`, inspect `fresh` and `stale` separately from the claim lifecycle.

## 4. Work with a user-exported Generic JSONL transcript

Requires the user's explicit source path and permission. This is an **advanced** path; it is not `connect jsonl` and has no automatic publishing or semantic summarization:

```bash
carrytrace extract --source generic_jsonl --input "<messages.jsonl>" --out "<new-staging-dir>"
```

After extraction, host/human semantic review, stable identity registration and explicit rendering are required before the structured MemoryStore can serve the content. Use the project's ingestion and stable-memory contracts from the repository installation for these steps. Never initialize identities over an existing vault, overwrite private data, or run `--apply` without specific approval.

## 5. If nothing matches or only recency fallback is available

Return **not found / requires review**. Explain the specific scanned source scope and distinguish `no_match` from `budget_exhausted`. A `recent_fallback` helps identify candidate sessions, not prove a claim. If the user authorizes it, narrow the query or inspect source evidence; never guess.

## Host interaction scope

Codex user skills load from `$HOME/.agents/skills/carrytrace`; Claude Code user skills load from `$HOME/.claude/skills/carrytrace`. Project installations use `.agents/skills/` or `.claude/skills/`. Skill files must be local to the host; cloud-only sessions do not automatically share a user's desktop paths.
