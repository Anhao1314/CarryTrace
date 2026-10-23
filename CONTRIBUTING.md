# Contributing

Start with the [architecture](docs/architecture.md) and [API contract](docs/memory-engine.md).
A small reproducible change is easier to review than an unmeasured new subsystem.

## Development checks

After installing from a checkout and activating the environment:

```bash
python3 -m unittest discover -s tests -v
python3 benchmarks/evaluate.py
python tools/verify_docs.py
```

Documentation checks execute the marked README snippets using the installed CLI. They
use temporary synthetic vaults, compare bilingual examples, validate local links, and
compare generated display assets with new CLI output. External links are not fetched.
After an intentional fixture change, use `python tools/verify_docs.py --write-demo`,
inspect the JSON/SVG diff, and rerun without that flag. Do not regenerate expected values
to hide an unexpected behavioral regression.

## Review boundaries

Preserve stable identity history, explicit lifecycle states, and legacy entry points.
Do not silently migrate, repair, or overwrite a user's vault. Add regression tests for
failures as well as successful paths. Keep semantic judgments separate from deterministic
validation; a passing structural check is not proof that a claim is true.

Keep the fixed benchmark intact for regression comparisons. New experiments should use
separate fixtures and disclose provenance, method, sample size, and failures. Do not
present a manually authored fixture as an automatically distilled dataset or a retrieval
score as an agent task-success rate.

## Report issues safely

Include the package/Python versions, exact command, a minimal **synthetic** input, expected
behavior, actual output, and reproduction steps. Remove credentials and private paths.
Never attach real personal conversations or user vaults to a public issue. For a sensitive
report, do not publish exploit details or private data in a public discussion; a dedicated
private disclosure channel is not currently advertised by this project.

README edits must preserve both language editions' commands and their `verify:` markers.
Put detailed contracts in `docs/` or `references/`, and link them from the documentation map.
