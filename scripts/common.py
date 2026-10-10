"""Helpers shared by discover.py and merge.py."""

import datetime as dt
import json
import os
import re
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USER_AGENT = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) accretion"
MAX_BYTES = 40 * 1024 * 1024


def path(name):
    return os.path.join(ROOT, name)


def read_list(name):
    """Lines of a text file, without blanks and # comments. Missing file -> []."""
    try:
        with open(path(name)) as f:
            lines = [line.split(" #")[0].strip() for line in f]
    except FileNotFoundError:
        return []
    return [line for line in lines if line and not line.startswith("#")]


def load_json(name, default):
    """Parse a JSON file in the repo root, or return default if it does not exist yet."""
    try:
        with open(path(name)) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def today():
    return dt.datetime.now(dt.timezone.utc).date()


def is_blocked(url, blocklist):
    u = url.lower()
    return any(b.lower() in u for b in blocklist)


def fetch_bytes(url, timeout=60, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("response too large")
        return data, r.geturl()


def parse_source(raw):
    """Return the source dict if raw is an AltStore/SideStore source, else raise."""
    data = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(data, dict) or not isinstance(data.get("apps"), list):
        raise TypeError("not an AltStore source (no apps list)")
    if not any(isinstance(a, dict) and a.get("bundleIdentifier") for a in data["apps"]):
        raise ValueError("source has no apps with a bundleIdentifier")
    return data


def fetch_source(url, timeout=60):
    raw, final_url = fetch_bytes(url, timeout)
    return parse_source(raw), final_url, len(raw)


def version_key(v):
    """'v1.20.3 (45)' -> (1, 20, 3, 45). Non-numeric versions sort lowest."""
    return tuple(int(n) for n in re.findall(r"\d+", str(v or ""))[:8])


APP_STORE_DAY = "2008-07-10"  # nothing sideloadable is older than the App Store


def plausible_day(day):
    """False for placeholder dates (2000-01-01, 1970-01-01) and dates in the future."""
    day = str(day or "")[:10]
    return APP_STORE_DAY <= day <= (today() + dt.timedelta(days=1)).isoformat()


def date_from_url(url):
    """Upload date from a Unix timestamp in a download link, e.g. 'App_3.10_1737138371.ipa'."""
    for stamp in re.findall(r"(?<!\d)(\d{10}|\d{13})(?!\d)", str(url or "")):
        secs = int(stamp[:10])
        day = dt.datetime.fromtimestamp(secs, dt.timezone.utc).date().isoformat()
        if plausible_day(day):
            return day
    return None


def date_key(d):
    """Normalise the many date formats sources use into a sortable string."""
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ](\d{1,2}:\d{2}(?::\d{2})?))?", str(d or ""))
    if not m:
        return ""
    y, mo, da, t = m.groups()
    return f"{y}-{int(mo):02d}-{int(da):02d}T{t or '00:00'}"
