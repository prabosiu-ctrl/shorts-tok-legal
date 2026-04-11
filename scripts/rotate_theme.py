"""
Reads the next theme from themes.txt (first non-empty, non-comment line),
removes it from the file, and prints it to stdout.

Used by GitHub Actions to feed a fresh theme to series_run.py each week.
"""

import sys
from pathlib import Path

THEMES_FILE = Path(__file__).parent.parent / "themes.txt"


def main():
    if not THEMES_FILE.exists():
        print("", end="")  # empty theme — scriptwriter uses its own fallback
        return

    lines = THEMES_FILE.read_text(encoding="utf-8").splitlines()

    theme = ""
    remaining = []
    found = False
    for line in lines:
        stripped = line.strip()
        if not found and stripped and not stripped.startswith("#"):
            theme = stripped
            found = True
        else:
            remaining.append(line)

    THEMES_FILE.write_text("\n".join(remaining) + "\n", encoding="utf-8")
    print(theme, end="")


if __name__ == "__main__":
    main()
