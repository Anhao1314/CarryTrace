# CarryTrace / 续迹: visual and naming system

**The continuity skill for AI agents.**

Your work continues. Keep the decisions. Bring the evidence.

CarryTrace is a local-first, Skill-first developer tool. The public name is **CarryTrace**, the machine-readable Skill and preferred CLI are **carrytrace**. Avoid names that imply universal history access, automatic truth verification or measured task success.

## Visual direction

A continuous C-shaped trace and forward movement connect earlier work to the next step. Cream and deep-blue surfaces, a lime trace and a cyan evidence point connect the identity to Eason's Playground without copying the personal mascot. Use legible system typography rather than embedded fonts or third-party services.

| Token | Light | Dark |
| --- | --- | --- |
| Surface | `#f6f5ee` | `#142035` |
| Text | `#182b49` | `#f4f5ef` |
| Secondary text | `#526176` | `#a9b6c8` |
| Accent | `#385dba` | `#c2f586` |
| Evidence point | `#67cfe7` | `#67cfe7` |

The headline is always static text. The optional decorative line draws once over 4.6 seconds and stops. Independent static SVGs are the default fallback; README `<picture>` opts into motion only for `prefers-reduced-motion: no-preference`. Artwork is illustrative, not an experiment replay.

```bash
python tools/build_brand_assets.py --check
```

## Migration boundary

Update current branding, navigation and repository links. Preserve historical evidence and old public interfaces where compatibility matters. The small “formerly chat-distiller” label belongs on the overview and migration guide, not on every heading. See [migration contracts](brand-migration.md).

## Primary references consulted

- [Agent Skills specification](https://agentskills.io/specification): name/parent-directory alignment and progressive disclosure.
- [PyPA entry points](https://packaging.python.org/en/latest/specifications/entry-points/): independent console command names over the same distribution.
- [GitHub repository renaming](https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository): redirects and explicit remote updates.
