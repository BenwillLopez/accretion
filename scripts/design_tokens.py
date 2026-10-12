"""Accretion's look from one file: design/tokens.json.

Writes the design-token block at the top of site/style.css and, with --app, the app's
Feather/Views/Accretion/Theme/AccretionTokens.swift, so the website and the app can't drift apart.

    python scripts/design_tokens.py                      # update site/style.css
    python scripts/design_tokens.py --app ../accretion-app   # and the app's AccretionTokens.swift
    python scripts/design_tokens.py --check              # exit 1 if style.css is out of date (CI)
"""

import argparse
import json
import os
import re
import sys

from common import path

START = "/* design tokens: generated from design/tokens.json by scripts/design_tokens.py */"
END = "/* end design tokens */"
SWIFT_FILE = os.path.join("Feather", "Views", "Accretion", "Theme", "AccretionTokens.swift")


def load():
    with open(path("design/tokens.json"), encoding="utf-8") as f:
        return json.load(f)


def _grid(tokens, mode):
    g = tokens["grid"][mode]
    r, gr, b = g["rgb"]
    return f"rgba({r}, {gr}, {b}, {g['alpha']})"


def _vars(tokens, mode):
    lines = [f"--{name}: {pair[mode]};" for name, pair in tokens["colors"].items() if mode in pair]
    lines.append(f"--glow: {tokens['glow'][mode]}%;")
    lines.append(f"--grid-line: {_grid(tokens, mode)};")
    return lines


def css(tokens):
    """The block that opens site/style.css: dark :root, then light by preference or choice."""
    dark = [
        *_vars(tokens, "dark"),
        f"--display: {tokens['fonts']['display']};",
        f"--body: {tokens['fonts']['body']};",
        f"--mono: {tokens['fonts']['mono']};",
        f"--radius: {tokens['radius']}px;",
        "color-scheme: dark;",
    ]
    light = [*_vars(tokens, "light"), "color-scheme: light;"]
    out = [START, ":root {", *(f"  {x}" for x in dark), "}"]
    out += ["@media (prefers-color-scheme: light) {", '  :root:not([data-theme="dark"]) {']
    out += [f"    {x}" for x in light]
    out += ["  }", "}", ':root[data-theme="light"] {', *(f"  {x}" for x in light), "}", END]
    return "\n".join(out)


def _camel(name):
    head, *rest = name.split("-")
    return head + "".join(part.capitalize() for part in rest)


def _hex(value):
    return "0x" + value.lstrip("#").upper()


def swift(tokens):
    """AccretionTokens.swift: the same values as Swift constants for AccretionTheme."""
    lines = [
        "//",
        "//  AccretionTokens.swift",
        "//  Accretion",
        "//",
        "//  Generated from design/tokens.json in getaccretion.github.io by scripts/design_tokens.py.",
        "//  Don't edit by hand: change the tokens there and run the script with --app.",
        "//",
        "",
        "import CoreGraphics",
        "",
        "enum AccretionTokens {",
    ]
    for name, pair in tokens["colors"].items():
        dark = pair["dark"]
        light = pair.get("light", dark)
        lines.append(
            f"\tstatic let {_camel(name)}: (dark: UInt32, light: UInt32) = ({_hex(dark)}, {_hex(light)})"
        )
    glow = tokens["glow"]
    lines.append(
        f"\tstatic let glow: (dark: Double, light: Double) = ({glow['dark'] / 100}, {glow['light'] / 100})"
    )
    grid = tokens["grid"]
    for mode in ("dark", "light"):
        r, g, b = grid[mode]["rgb"]
        lines.append(f"\tstatic let gridLine{mode.capitalize()}: UInt32 = 0x{r:02X}{g:02X}{b:02X}")
        lines.append(f"\tstatic let gridAlpha{mode.capitalize()}: CGFloat = {grid[mode]['alpha']}")
    lines.append(f"\tstatic let gridSize: CGFloat = {grid['size']}")
    lines.append(f"\tstatic let radius: CGFloat = {tokens['radius']}")
    lines.append("}")
    return "\n".join(lines) + "\n"


def apply_css(text, block):
    """Replace the token block in style.css (or the hand-written one it took over from)."""
    if START in text:
        pattern = re.escape(START) + r".*?" + re.escape(END)
        return re.sub(pattern, lambda _: block, text, count=1, flags=re.S)
    # first run: the hand-written :root ... :root[data-theme="light"] { ... } blocks
    pattern = r':root \{.*?:root\[data-theme="light"\] \{.*?\n\}'
    new, n = re.subn(pattern, lambda _: block, text, count=1, flags=re.S)
    if n != 1:
        raise SystemExit("Couldn't find the token block in site/style.css")
    return new


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--app", help="path to an accretion-app checkout to write AccretionTokens.swift into")
    parser.add_argument("--check", action="store_true", help="fail if site/style.css is out of date")
    args = parser.parse_args(argv)
    tokens = load()
    style = path("site/style.css")
    with open(style, encoding="utf-8") as f:
        current = f.read()
    updated = apply_css(current, css(tokens))
    if args.check:
        if updated != current:
            print("site/style.css is out of date with design/tokens.json: run scripts/design_tokens.py")
            return 1
        print("site/style.css matches design/tokens.json")
        return 0
    if updated != current:
        with open(style, "w", encoding="utf-8", newline="\n") as f:
            f.write(updated)
        print("Updated site/style.css")
    if args.app:
        target = os.path.join(args.app, SWIFT_FILE)
        with open(target, "w", encoding="utf-8", newline="\n") as f:
            f.write(swift(tokens))
        print(f"Wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
