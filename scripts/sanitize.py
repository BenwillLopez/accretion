"""Clean app entries so the published source follows the AltStore source format.

Sources in the wild are messy: http links, made-up categories, sizes as strings,
odd dates, duplicate fields from other formats. Everything is fixed or dropped
here, and validate() refuses to publish anything that still breaks the rules.
Reference: https://faq.altstore.io/developers/make-a-source
"""

import re

from common import date_from_url, date_key, plausible_day, today, version_key

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


# When a source gives no usable category, guess one from the app's name, bundle ID and
# subtitle. Checked in order; the first match wins.
CATEGORY_HINTS = [
    (
        "games",
        r"game|games|emulator|emu|nintendo|gba|nds|psp|ps1|ps2|retroarch|minecraft|roblox|pokemon|"
        r"puzzle|rpg|arcade|racing|chess|solitaire|clash|brawl|genshin|pubg|fortnite|geometry|sudoku",
    ),
    (
        "social",
        r"instagram|tiktok|musically|whatsapp|telegram|discord|twitter|tweet|facebook|messenger|"
        r"snapchat|reddit|apollo|threads|bereal|tinder|bumble|wechat|line|viber|signal|mastodon|"
        r"bluesky|pinterest|tumblr|linkedin|kik|grindr",
    ),
    (
        "photo-video",
        r"youtube|ytlite|uyou|camera|photo|photos|video|videos|vlc|infuse|editor|capcut|"
        r"lightroom|vsco|picsart|facetune|gif|recorder|screenshot|wallpaper|filmic",
    ),
    (
        "entertainment",
        r"spotify|music|soundcloud|deezer|tidal|netflix|hulu|disney|hbo|crunchyroll|anime|"
        r"manga|movie|movies|tv|iptv|stream|streaming|twitch|podcast|radio|stremio|plex|"
        r"jellyfin|kodi|comic|comics|books|audible|kindle|webtoon",
    ),
    (
        "developer",
        r"terminal|ssh|shell|jailbreak|dopamine|palera1n|unc0ver|taurine|odyssey|trollstore|"
        r"filza|sideload|sidestore|altstore|feather|esign|scarlet|ksign|gbox|livecontainer|"
        r"developer|xcode|python|github|signer|jit|appdb|ldid",
    ),
    (
        "utilities",
        r"vpn|proxy|adblock|ad-blocker|blocker|browser|file|files|scanner|keyboard|calculator|"
        r"translator|translate|clock|alarm|password|manager|downloader|download|cleaner|"
        r"battery|widget|launcher|remote|torrent|backup|qr|pdf|notes|calendar|utility|tools",
    ),
    (
        "lifestyle",
        r"fitness|workout|health|diet|food|recipe|travel|weather|news|shopping|bank|finance|"
        r"crypto|duolingo|language|learn|education|study|meditation|sleep|habit|dating|maps",
    ),
]
_HINT_RES = [(cat, re.compile(rf"\b(?:{words})\b")) for cat, words in CATEGORY_HINTS]


def category(c, hint=""):
    c = re.sub(r"[\s_/&]+", "-", str(c or "").strip().lower())
    c = c if c in CATEGORIES else CATEGORY_ALIASES.get(c, "other")
    if c == "other" and hint:
        text = re.sub(r"[._\-]+", " ", hint.lower())
        for cat, pattern in _HINT_RES:
            if pattern.search(text):
                return cat
    return c


def tint(c):
    m = HEX_RE.match(str(c or "").strip())
    return m.group(1).upper() if m else None


# Download URL -> {"modified": day the file was uploaded, "seen": day Accretion first saw it},
# loaded by merge.py from link_dates.json. Versions whose source gives an impossible date
# (2000-01-01, 1970-01-01, future) get a real one from here; UNDATED collects the links where
# only the first-seen day was available, so the store doesn't show those apps as new.
KNOWN_DATES = {}
UNDATED = set()
REDATED = set()  # links dated from the file's upload day


def real_date(url, date):
    """A believable release date for a version whose source date is a placeholder."""
    if date and plausible_day(date):
        return date
    known = KNOWN_DATES.get(url) or {}
    found = date_from_url(url)
    if not found and plausible_day(known.get("modified")):
        found = known["modified"]
        REDATED.add(url)
    if found:
        return found
    UNDATED.add(url)
    return known.get("seen") or today().isoformat()


def clean_version(v):
    url = https(v.get("downloadURL"))
    date = iso_date(v.get("date"))
    if date and url:
        date = real_date(url, date)
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


def _shots(raw, need_size=False):
    """A spec list of screenshots: plain https URLs, or {imageURL, width, height} objects."""
    out, seen = [], set()
    for s in raw if isinstance(raw, list) else []:
        if isinstance(s, dict):
            url, w, h = https(s.get("imageURL")), to_int(s.get("width")), to_int(s.get("height"))
            item = {"imageURL": url, "width": w, "height": h} if url and w and h else url
        else:
            url = item = https(s)
        if not url or url in seen or (need_size and not isinstance(item, dict)):
            continue  # iPad screenshots must state their size
        seen.add(url)
        out.append(item)
    return out[:MAX_SCREENSHOTS]


def screenshots(app):
    """Screenshots in the current format: a list, or {"iphone": [...], "ipad": [...]}."""
    raw = app.get("screenshots")
    if isinstance(raw, dict):
        iphone, ipad = _shots(raw.get("iphone")), _shots(raw.get("ipad"), need_size=True)
        if ipad:
            return {"iphone": iphone, "ipad": ipad} if iphone else {"ipad": ipad}
        return iphone
    return _shots(raw if isinstance(raw, list) else app.get("screenshotURLs"))


def screenshot_urls(shots):
    """Flat iPhone URL list for the legacy screenshotURLs field."""
    items = shots.get("iphone", []) if isinstance(shots, dict) else shots
    return [s["imageURL"] if isinstance(s, dict) else s for s in items]


def permissions(raw):
    """appPermissions with string entitlements and string privacy descriptions, or None.

    AltStore checks these against the downloaded app and refuses to install on a
    mismatch, so anything malformed is dropped instead of guessed.
    """
    if not isinstance(raw, dict):
        return None
    ents = raw.get("entitlements")
    priv = raw.get("privacy")
    if isinstance(priv, list):  # some sources write [{"name": key, "usageDescription": text}]
        priv = {p.get("name"): p.get("usageDescription") for p in priv if isinstance(p, dict)}
    out = {}
    if isinstance(ents, list):
        out["entitlements"] = sorted({e for e in ents if isinstance(e, str) and e})
    if isinstance(priv, dict):
        out["privacy"] = {
            k: text(v, 300) for k, v in priv.items() if isinstance(k, str) and k and isinstance(v, str)
        }
    return out or None


def skip_reason(app):
    """Why an app cannot be installed from a merged source, or None if it can.

    - Patreon apps only download for patrons of the original source's campaign.
    - AltStore PAL listings point at notarized ADP packages, not .ipa files, and
      cannot install in AltStore Classic, SideStore, the iOSGods App and the like.
    """
    if isinstance(app.get("patreon"), dict):
        return "patreon"
    if app.get("marketplaceID"):
        return "pal"
    for v in app.get("versions") or []:
        if isinstance(v, dict) and (
            v.get("assetURLs") or str(v.get("downloadURL", "")).split("?")[0].endswith("manifest.json")
        ):
            return "pal"
    return None


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
        "category": category(
            app.get("category"),
            " ".join(str(app.get(k) or "") for k in ("name", "bundleIdentifier", "subtitle")),
        ),
        "screenshots": screenshots(app),
        "versions": vers,
    }
    out["screenshotURLs"] = screenshot_urls(out["screenshots"])  # for older clients
    if not out["subtitle"]:
        del out["subtitle"]
    if tint(app.get("tintColor")):
        out["tintColor"] = tint(app.get("tintColor"))
    if permissions(app.get("appPermissions")):
        out["appPermissions"] = permissions(app.get("appPermissions"))
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
    out["title"] = text(out["title"], 120)
    out["caption"] = text(out.get("caption"), 400) or out["title"]  # caption is required
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
    if not isinstance(source.get("nsfw"), bool):
        errors.append("source nsfw must be true or false")
    if len(source.get("featuredApps", [])) > 5:
        errors.append("featuredApps lists more than the 5 AltStore shows")
    news_ids = set()
    for item in source.get("news", []):
        for k in ("title", "identifier", "caption", "date"):
            if not item.get(k):
                errors.append(f"news {item.get('identifier')}: missing {k}")
        if item.get("identifier") in news_ids:
            errors.append(f"news {item.get('identifier')}: duplicate identifier")
        news_ids.add(item.get("identifier"))
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
        if skip_reason(a):
            errors.append(f"{where}: {skip_reason(a)} app cannot install from this source")
        shots = a.get("screenshots", [])
        if isinstance(shots, dict):
            for s in shots.get("ipad", []):
                if not (isinstance(s, dict) and s.get("width") and s.get("height")):
                    errors.append(f"{where}: iPad screenshot without width/height")
        elif not isinstance(shots, list):
            errors.append(f"{where}: screenshots must be a list or iphone/ipad object")
        perms = a.get("appPermissions")
        if perms is not None and permissions(perms) != perms:
            errors.append(f"{where}: malformed appPermissions")
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
