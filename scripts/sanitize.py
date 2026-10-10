"""Clean app entries so the published source follows the AltStore source format.

Sources in the wild are messy: http links, made-up categories, sizes as strings,
odd dates, duplicate fields from other formats. Everything is fixed or dropped
here, and validate() refuses to publish anything that still breaks the rules.
Reference: https://faq.altstore.io/developers/make-a-source
"""

import re

from common import date_key, version_key

CATEGORIES = {
    "developer",
    "entertainment",
    "games",
    "lifestyle",
    "other",
    "photo-video",
    "social",
    "utilities",
}
CATEGORY_ALIASES = {
    "game": "games",
    "emulator": "games",
    "emulators": "games",
    "arcade": "games",
    "photo": "photo-video",
    "photos": "photo-video",
    "video": "photo-video",
    "music": "entertainment",
    "streaming": "entertainment",
    "media": "entertainment",
    "books": "entertainment",
    "news": "lifestyle",
    "health": "lifestyle",
    "education": "lifestyle",
    "productivity": "utilities",
    "utility": "utilities",
    "tools": "utilities",
    "tweaks": "utilities",
    "tweaked": "utilities",
    "jailbreak": "developer",
    "developer-tools": "developer",
    "dev": "developer",
    "social-networking": "social",
    "communication": "social",
}

VERSION_KEYS = (
    "version",
    "buildVersion",
    "marketingVersion",
    "date",
    "localizedDescription",
    "downloadURL",
    "minOSVersion",
    "maxOSVersion",
    "size",
    "sha256",
)
NEWS_KEYS = ("title", "identifier", "caption", "date", "tintColor", "imageURL", "notify", "url", "appID")

MAX_VERSIONS = 2
MAX_SCREENSHOTS = 5
MAX_DESCRIPTION = 1200
MAX_NOTES = 300
MAX_SUBTITLE = 120
URL_RE = re.compile(r"^https://[^\s/$.?#][^\s]*$", re.IGNORECASE)
BUNDLE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-_]*$")
HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")


def https(u):
    u = str(u or "").strip()
    if u.lower().startswith("http://"):
        return None  # never upgrade blindly: plain-http hosts often have no valid certificate
    return u if URL_RE.match(u) else None


def text(s, limit):
    s = str(s or "").replace("\r\n", "\n").strip()
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def iso_date(d):
    k = date_key(d)
    if not k:
        return None
    day, t = k.split("T")
    return day if t == "00:00" else f"{day}T{t if t.count(':') == 2 else t + ':00'}Z"


def to_int(n):
    try:
        n = int(float(n))
        return n if n >= 0 else None
    except (TypeError, ValueError):
        return None


def category(c):
    c = re.sub(r"[\s_/&]+", "-", str(c or "").strip().lower())
    return c if c in CATEGORIES else CATEGORY_ALIASES.get(c, "other")


def tint(c):
    m = HEX_RE.match(str(c or "").strip())
    return m.group(1).upper() if m else None


def clean_version(v):
    url = https(v.get("downloadURL"))
    date = iso_date(v.get("date"))
    version = text(v.get("version"), 64)
    if not url or not date or not version:
        return None
    out = {k: v[k] for k in VERSION_KEYS if v.get(k) not in (None, "", [])}
    out.update(version=version, date=date, downloadURL=url, size=to_int(v.get("size")) or 0)
    if out.get("localizedDescription"):
        out["localizedDescription"] = text(out["localizedDescription"], MAX_NOTES)
    for k in ("buildVersion", "marketingVersion", "minOSVersion", "maxOSVersion"):
        if k in out:
            out[k] = text(out[k], 32)
    return out


def screenshots(app):
    raw = app.get("screenshots")
    if isinstance(raw, dict):  # {"iphone": [...], "ipad": [...]}
        raw = raw.get("iphone") or next(iter(raw.values()), [])
    if not isinstance(raw, list):
        raw = app.get("screenshotURLs") or []
    urls = []
    for s in raw if isinstance(raw, list) else []:
        u = https(s.get("imageURL") if isinstance(s, dict) else s)
        if u and u not in urls:
            urls.append(u)
    return urls[:MAX_SCREENSHOTS]


def clean_app(app, versions):
    """Return a spec-compliant copy of app with its newest versions, or None if unusable."""
    bid = str(app.get("bundleIdentifier") or app.get("bundleID") or "").strip()
    name = text(app.get("name"), 80)
    icon = https(app.get("iconURL") or app.get("icon"))
    vers = [v for v in (clean_version(v) for v in versions) if v][:MAX_VERSIONS]
    if not BUNDLE_RE.match(bid) or not name or not icon or not vers:
        return None
    subtitle = text(app.get("subtitle"), MAX_SUBTITLE)
    out = {
        "name": name,
        "bundleIdentifier": bid,
        "developerName": text(app.get("developerName"), 80) or "Unknown developer",
        "subtitle": subtitle,
        "localizedDescription": text(app.get("localizedDescription"), MAX_DESCRIPTION) or subtitle or name,
        "iconURL": icon,
        "category": category(app.get("category")),
        "screenshotURLs": screenshots(app),
        "versions": vers,
    }
    if not out["subtitle"]:
        del out["subtitle"]
    if tint(app.get("tintColor")):
        out["tintColor"] = tint(app.get("tintColor"))
    if isinstance(app.get("appPermissions"), dict):
        out["appPermissions"] = app["appPermissions"]
    if app.get("beta") is True:
        out["beta"] = True
    latest = vers[0]
    # legacy single-version fields for older clients (release notes stay in versions only)
    out.update(
        version=latest["version"],
        versionDate=latest["date"],
        downloadURL=latest["downloadURL"],
        size=latest["size"],
    )
    return out


def clean_news(item, app_ids):
    if not isinstance(item, dict):
        return None
    out = {k: item[k] for k in NEWS_KEYS if item.get(k) not in (None, "")}
    out["date"] = iso_date(item.get("date"))
    if not out.get("title") or not out.get("identifier") or not out["date"]:
        return None
    out["title"], out["caption"] = text(out["title"], 120), text(out.get("caption"), 400)
    for k in ("imageURL", "url"):
        if k in out and not https(out[k]):
            del out[k]
    if out.get("appID") and out["appID"] not in app_ids:
        del out["appID"]
    if tint(out.get("tintColor")):
        out["tintColor"] = tint(out["tintColor"])
    else:
        out.pop("tintColor", None)
    out["notify"] = False  # never push notifications on behalf of other sources
    return out


def validate(source):
    """List every rule the source breaks. An empty list means it is safe to publish."""
    errors = []
    for k in ("name", "identifier", "apps"):
        if not source.get(k):
            errors.append(f"source is missing {k}")
    seen = set()
    for i, a in enumerate(source.get("apps", [])):
        where = f"app {i} ({a.get('bundleIdentifier')})"
        if a.get("bundleIdentifier") in seen:
            errors.append(f"{where}: duplicate bundleIdentifier")
        seen.add(a.get("bundleIdentifier"))
        for k in ("name", "bundleIdentifier", "developerName", "localizedDescription", "iconURL", "versions"):
            if not a.get(k):
                errors.append(f"{where}: missing {k}")
        if a.get("category") not in CATEGORIES:
            errors.append(f"{where}: bad category {a.get('category')!r}")
        if not https(a.get("iconURL")):
            errors.append(f"{where}: iconURL is not https")
        vs = a.get("versions") or []
        for v in vs:
            if not https(v.get("downloadURL")):
                errors.append(f"{where}: downloadURL is not https")
            if not isinstance(v.get("size"), int) or not iso_date(v.get("date")):
                errors.append(f"{where}: bad size or date in version {v.get('version')}")
        keys = [
            (version_key(v.get("version")), version_key(v.get("buildVersion")), date_key(v.get("date")))
            for v in vs
        ]
        if keys != sorted(keys, reverse=True):
            errors.append(f"{where}: versions are not newest first")
        if vs and a.get("downloadURL") != vs[0].get("downloadURL"):
            errors.append(f"{where}: legacy fields do not point at the newest version")
    for app_id in source.get("featuredApps", []):
        if app_id not in seen:
            errors.append(f"featured app {app_id} is not in the source")
    return errors
