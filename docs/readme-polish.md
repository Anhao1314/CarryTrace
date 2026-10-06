# Wiki-first README refinement (2026-10-06)

Baseline: `6227ab053b39ac0a04e7304a25b0eed0bca5b8e6`.
This documentation-only pass places the executed Wiki lifecycle before the manual setup,
keeps the manual workflow in an expandable section, and exposes both Python read interfaces.
The package remains 0.3.0; engine, schema, dependencies, and benchmark fixtures are unchanged.

Local Linux / Python 3.13.5 verification:

- 215 baseline tests passed; 221 candidate tests passed, including six added homepage checks.
- The full 16-command / 12-check Wiki demo is now executed directly from a marked README block.
- Both language versions share the CLI, summary excerpt, manual setup, and SDK examples.
- Two lifecycle SVGs and a path/UUID-independent receipt are regenerated from raw CLI results.
- Four README metric tables are checked against the existing JSON reports; both benchmarks remain unchanged.
- The documentation checker validates 120 local links/anchors. External links are counted, not fetched.

Chromium rendered English and Chinese local Markdown previews at 1280 px and 390 px.
The two expandable sections opened correctly, the inline SVG loaded, and the page had no
horizontal body overflow in either viewport. Navigation to file/loopback URLs was blocked
in this environment, so the preview used in-memory HTML with embedded SVG and no HTTP requests.
This is not GitHub server-side rendering, an external badge check, or Mermaid rendering verification.

Reproduce from the repository root with the installed environment activated:

```bash
python -m unittest discover -s tests -v
python benchmarks/evaluate.py
python benchmarks/wiki/evaluate.py --check
python tools/verify_docs.py
```

`python tools/verify_docs.py --write-demo`
regenerates both the atomic recovery display and the Wiki lifecycle displays only after executing the examples.
The PR and its evidence workflow record the final source tree and installed-wheel results.
