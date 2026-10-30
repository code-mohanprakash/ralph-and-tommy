"""Block commits that contain an API key.

pre-commit passes the staged files as arguments. If any of them holds something
that looks like an Anthropic API key, this prints the file and line and exits
with 1, which stops the commit. It never prints the key itself.

This guards the one secret this project has. It is not a general secret scanner.
"""

import re
import sys
from pathlib import Path

PATTERNS = (
    # Anthropic keys start with "sk-ant-". Real ones are about 100 characters.
    re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
    # A value pasted straight after the variable name, whatever its shape.
    re.compile(r"ANTHROPIC_API_KEY\s*=\s*['\"]?[A-Za-z0-9_-]{20,}"),
)


def lines_with_keys(text: str) -> list[int]:
    """Return the line numbers (from 1) that look like they hold a key."""
    return [
        number
        for number, line in enumerate(text.splitlines(), start=1)
        if any(pattern.search(line) for pattern in PATTERNS)
    ]


def main(paths: list[str]) -> int:
    found = False
    for path in paths:
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
        for number in lines_with_keys(text):
            print(f"{path}:{number}: looks like an API key. Keep keys only in .env.")
            found = True
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
