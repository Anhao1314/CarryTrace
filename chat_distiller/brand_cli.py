"""CarryTrace entry point. Existing data, imports and CLI semantics stay compatible."""
import sys
from . import __version__
from .cli import main as legacy_main


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["--version"]:
        print("CarryTrace " + __version__ + " (distribution: chat-distiller)")
        return 0
    if argv and argv[0] == "skill":
        from .brand_skill import main as skill_main
        return skill_main(argv[1:])
    return legacy_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
