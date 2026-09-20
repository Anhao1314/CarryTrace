#!/usr/bin/env python3
"""Compatible extraction entry point; select --source doubao_work or generic_jsonl."""
import sys
from source_adapters import doubao_work, generic_jsonl


def main():
    source = 'doubao_work'
    if '--source' in sys.argv:
        at = sys.argv.index('--source')
        if at + 1 >= len(sys.argv):
            raise SystemExit('--source requires doubao_work or generic_jsonl')
        source = sys.argv[at+1]
        del sys.argv[at:at+2]
    if source == 'doubao_work':
        return doubao_work.main()
    if source == 'generic_jsonl':
        return generic_jsonl.main()
    raise SystemExit('unknown --source: ' + source)


if __name__ == '__main__':
    sys.exit(main())
