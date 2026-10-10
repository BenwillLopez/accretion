"""Check published source files against the rules in sanitize.validate().

Usage: python scripts/validate.py source.json [curated.json ...]
"""

import json
import sys

from common import path
from sanitize import validate


def main(names):
    failed = False
    for name in names:
        try:
            with open(path(name)) as f:
                data = json.load(f)
        except FileNotFoundError:
            print(f"{name}: not built yet, skipped")
            continue
        errors = validate(data)
        if errors:
            failed = True
            print(f"{name}: {len(errors)} problems", *errors[:50], sep="\n  ")
        else:
            print(f"{name}: ok ({len(data['apps'])} apps)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["source.json", "curated.json"]))
