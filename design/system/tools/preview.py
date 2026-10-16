"""View the design system locally: writes design/system/_preview/ (git-ignored) with every component
card in dark and light, styled the way the hosted design-system page styles them (tokens compiled
to CSS, then components/bundle.css), and sheet.html showing them all side by side.

    python design/system/tools/preview.py      then open design/system/_preview/sheet.html
"""

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "_preview"


def value(v):
    return re.sub(r"^\{(.+)\}$", r"var(--\1)", v)


def tokens_css(t):
    themes = [x["id"] for x in t["color"]["themes"]]
    css = []
    for i, theme in enumerate(themes):
        selector = f':root, [data-theme="{theme}"]' if i == 0 else f'[data-theme="{theme}"]'
        lines = []
        for tok in t["color"]["tokens"]:
            v = tok["value"]
            if isinstance(v, str):
                if i == 0:
                    lines.append(f"--{tok['name']}: {value(v)};")
            elif theme in v:
                lines.append(f"--{tok['name']}: {value(v[theme])};")
        css.append(selector + " {\n  " + "\n  ".join(lines) + "\n}")
    rest = [
        f"--{x['name']}: {x['value']};"
        for f in ("spacing", "radius", "layout", "opacity")
        for x in t[f]["tokens"]
    ]
    rest += [f"--font-{k}: {v};" for k, v in t["type"]["families"].items()]
    css.append(":root {\n  " + "\n  ".join(rest) + "\n}")
    for f in t["type"]["fonts"]:
        family, file, weight = f["family"], f["file"], f["weight"]
        css.append(f'@font-face {{ font-family: "{family}"; src: url(../{file}); font-weight: {weight}; }}')
    return themes, "\n".join(css)


def main():
    OUT.mkdir(exist_ok=True)
    t = json.loads((ROOT / "tokens.json").read_text(encoding="utf-8"))
    themes, css = tokens_css(t)
    (OUT / "tokens.css").write_text(css, encoding="utf-8")
    cards = sorted(d.name for d in (ROOT / "components").iterdir() if d.is_dir())
    if "Cover" in cards:
        cards.remove("Cover")
        cards.insert(0, "Cover")
    heights = {}
    links = '<link rel="stylesheet" href="tokens.css"><link rel="stylesheet" href="../components/bundle.css">'
    for card in cards:
        src = (ROOT / "components" / card / "preview.html").read_text(encoding="utf-8")
        heights[card] = int(re.search(r"height=(\d+)", src.splitlines()[0]).group(1))
        src = src.replace("<head>", "<head>" + links, 1).replace("../../assets/", "../assets/")
        for theme in themes:
            themed = src.replace('<html lang="en">', f'<html lang="en" data-theme="{theme}">', 1)
            (OUT / f"{card}-{theme}.html").write_text(themed, encoding="utf-8")
    sheet = [
        "<!doctype html><meta charset=utf-8><title>Accretion components</title><style>"
        "body{margin:0;background:#444;font:12px sans-serif;color:#fff}h3{margin:8px}"
        "div{display:grid;grid-template-columns:repeat(2,minmax(0,960px));gap:8px;padding:0 8px}"
        "iframe{width:100%;border:0;background:#888}</style>"
    ]
    for card, h in heights.items():
        frames = "".join(f"<iframe src='{card}-{th}.html' style='height:{h}px'></iframe>" for th in themes)
        sheet.append(f"<h3>{card}</h3><div>{frames}</div>")
    (OUT / "sheet.html").write_text("\n".join(sheet), encoding="utf-8")
    print(f"{len(heights)} cards in {OUT / 'sheet.html'}")


if __name__ == "__main__":
    main()
