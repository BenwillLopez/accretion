"""Helpers shared by discover.py and merge.py."""
import json
import os
import re
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
USER_AGENT = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) altsource-merge"
MAX_BYTES = 40 * 1024 * 1024


def path(name):
    return os.path.join(HERE, name)


def read_list(name):
    """Lines of a text file, without blanks and # comments. Missing file -> []."""
    try:
        with open(path(name)) as f:
            lines = [l.split(" #")[0].strip() for l in f]
    except FileNotFoundError:
        return []
    return [l for l in lines if l and not l.startswith("#")]


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
        raise ValueError("not an AltStore source (no apps list)")
    if not any(isinstance(a, dict) and a.get("bundleIdentifier") for a in data["apps"]):
        raise ValueError("source has no apps with a bundleIdentifier")
    return data


def fetch_source(url, timeout=60):
    raw, final_url = fetch_bytes(url, timeout)
    return parse_source(raw), final_url, len(raw)


def version_key(v):
    """'v1.20.3 (45)' -> (1, 20, 3, 45). Non-numeric versions sort lowest."""
    return tuple(int(n) for n in re.findall(r"\d+", str(v or ""))[:8])


def date_key(d):
    """Normalise the many date formats sources use into a sortable string."""
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ](\d{1,2}:\d{2}(?::\d{2})?))?", str(d or ""))
    if not m:
        return ""
    y, mo, da, t = m.groups()
    return f"{y}-{int(mo):02d}-{int(da):02d}T{t or '00:00'}"
