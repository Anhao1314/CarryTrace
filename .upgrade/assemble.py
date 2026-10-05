"""One-shot guarded assembly; publishes source objects only, never refs or workflows."""
import argparse
import gzip
import hashlib
import json
import os
import subprocess
import tempfile
import urllib.request
import urllib.error
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--publish", action="store_true")
args = parser.parse_args()
root = Path.cwd()
raw = b"".join(p.read_bytes() for p in sorted((root / ".upgrade").glob("plan-*.gzpart")))
plan = json.loads(gzip.decompress(raw))
evidence = Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())) / "engine-assembly-evidence"
evidence.mkdir(exist_ok=True)

def git(*argv, data=None, env=None):
    return subprocess.check_output(["git", *argv], input=data, env=env, cwd=root)

def checked_path(value):
    p = Path(value)
    if p.is_absolute() or ".." in p.parts or str(p).startswith((".git/", ".upgrade/")):
        raise ValueError("invalid generated path")
    return root / p

if not args.publish:
    for item in plan["files"]:
        if "content" in item:
            text = item["content"]
        else:
            original = git("show", plan["base_tree"] + ":" + item["source"])
            assert hashlib.sha256(original).hexdigest() == item["source_sha256"], item["source"]
            lines = original.decode("utf-8").splitlines(keepends=True)
            for edit in reversed(item["edits"]):
                lines[edit["start"]:edit["stop"]] = [edit["text"]]
            text = "".join(lines)
        data = text.encode("utf-8")
        assert hashlib.sha256(data).hexdigest() == item["sha256"], item["path"]
        destination = checked_path(item["path"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)

entries = []
with tempfile.TemporaryDirectory() as tmp:
    env = dict(os.environ, GIT_INDEX_FILE=str(Path(tmp) / "index"))
    git("read-tree", plan["base_tree"], env=env)
    for item in plan["files"]:
        data = checked_path(item["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == item["sha256"], "generated file changed: " + item["path"]
        sha = git("hash-object", "-w", "--stdin", data=data).decode().strip()
        git("update-index", "--add", "--cacheinfo", "100644," + sha + "," + item["path"], env=env)
        entries.append({"path": item["path"], "mode": "100644", "type": "blob", "content": data.decode("utf-8")})
    tree = git("write-tree", env=env).decode().strip()
assert tree == plan["expected_tree"], (tree, plan["expected_tree"])
(evidence / "source.tar").write_bytes(git("archive", "--format=tar", tree))
receipt = {"expected_tree": tree, "changed_files": len(entries), "plan_sha256": hashlib.sha256(raw).hexdigest(), "branch_updated": False}
if args.publish:
    assert os.environ["GITHUB_REPOSITORY"] == "Anhao1314/chat-distiller"
    assert os.environ["GITHUB_REF"] == "refs/heads/codex/verified-memory-engine"
    # Workflow mutations belong to the explicitly authorized GitHub connector.
    source_entries = [entry for entry in entries if not entry["path"].startswith(".github/")]
    request = urllib.request.Request(
        "https://api.github.com/repos/Anhao1314/chat-distiller/git/trees",
        data=json.dumps({"base_tree": plan["base_tree"], "tree": source_entries}, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"], "Accept": "application/vnd.github+json", "Content-Type": "application/json", "X-GitHub-Api-Version": "2022-11-28"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        print("Object publication rejected:", exc.code, exc.read().decode("utf-8")[:2000])
        raise
    assert result["sha"] == "d3db65d853dfa99195f1222c4cf2ea935ff089d3", result["sha"]
    receipt["published_source_tree"] = result["sha"]
    receipt["tree_url"] = result["url"]
(evidence / "tree-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
print(json.dumps(receipt, indent=2))
