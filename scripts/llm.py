"""One door to the free language models (Google Gemini and OpenRouter ":free" models).

ask() tries the models in ai/models.json in order and returns the first usable answer, or None.
A model that answers 429 (rate limited), 503 (busy) or 404 (gone) is skipped for the rest of the
run. Providers without a key (GEMINI_API_KEY, OPENROUTER_API_KEY) are skipped. Only free models are
ever called: OpenRouter ids must end in ":free". llm.last_model names the model that answered.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request

from common import path

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
KEYS = {"gemini": "GEMINI_API_KEY", "openrouter": "OPENROUTER_API_KEY"}
BUSY_CODES = (404, 429, 503)

last_model = None  # "provider:model" that answered the latest ask(), None when none did
busy = set()  # models to leave alone for the rest of this run
TYPES = {"str": str, "bool": bool, "int": int, "list": list}


def config():
    try:
        with open(path("ai/models.json"), encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"order": [], "moderation": ""}


def usable(spec):
    """True when the model is free (OpenRouter) and its provider has a key"""
    provider, _, model = spec.partition(":")
    if provider not in KEYS or not model or not os.environ.get(KEYS[provider], "").strip():
        return False
    return provider != "openrouter" or model.endswith(":free")


def post(url, headers, body):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Content-Type": "application/json", **headers},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def call(spec, system, user, max_tokens):
    """One request to one model: the answer text. Raises HTTPError, URLError or ValueError."""
    provider, _, model = spec.partition(":")
    key = os.environ.get(KEYS[provider], "").strip()
    if provider == "gemini":
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            # the model reasons before answering, and that counts against the limit
            "generationConfig": {"maxOutputTokens": max_tokens * 4},
        }
        data = post(GEMINI_URL.format(model), {"x-goog-api-key": key}, body)
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts).strip()
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    data = post(OPENROUTER_URL, {"Authorization": f"Bearer {key}"}, body)
    return (data["choices"][0]["message"]["content"] or "").strip()


def parse(raw, schema):
    """(dict, None) for a reply that is JSON matching the schema, else (None, what was wrong).
    Schema: key -> "str", "bool", "int", "list", or a list of allowed values."""
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.IGNORECASE)
    try:
        data = json.loads(raw)
    except ValueError:
        start, end = raw.find("{"), raw.rfind("}")
        try:
            data = json.loads(raw[start : end + 1]) if 0 <= start < end else None
        except ValueError:
            data = None
    if not isinstance(data, dict):
        return None, "the reply was not a JSON object"
    for key, spec in schema.items():
        if key not in data:
            return None, f"missing key {key!r}"
        value = data[key]
        if isinstance(spec, (list, tuple, set)):
            if value not in spec:
                return None, f"{key!r} must be one of {sorted(spec)}, got {value!r}"
        elif not isinstance(value, TYPES[spec]) or (spec == "int" and isinstance(value, bool)):
            return None, f"{key!r} must be {spec}"
    return data, None


def ask(task, system, user, schema=None, max_tokens=800):
    """The answer (text, or a dict when a schema is given) from the first free model that works,
    else None. task "moderate" uses only the moderation model."""
    global last_model
    last_model = None
    cfg = config()
    order = [cfg["moderation"]] if task == "moderate" else cfg.get("order", [])
    if schema:
        system += (
            "\n\nReply with one JSON object only, no markdown fences and no other text. Keys: "
            + ", ".join(
                f"{k} ({'one of ' + '/'.join(map(str, s)) if isinstance(s, (list, tuple, set)) else s})"
                for k, s in schema.items()
            )
            + "."
        )
    for spec in order:
        if spec in busy or not usable(spec):
            continue
        prompt, error = user, None
        for _ in range(2 if schema else 1):
            try:
                raw = call(spec, system, prompt, max_tokens)
            except urllib.error.HTTPError as e:
                if e.code in BUSY_CODES:
                    busy.add(spec)
                print(f"llm[{task}]: {spec} answered {e.code}", file=sys.stderr)
                break
            except (urllib.error.URLError, KeyError, IndexError, ValueError, TimeoutError, OSError) as e:
                print(f"llm[{task}]: {spec} failed ({type(e).__name__})", file=sys.stderr)
                break
            if not schema:
                if raw:
                    last_model = spec
                    return raw
                break
            data, error = parse(raw, schema)
            if data is not None:
                last_model = spec
                return data
            prompt = f"{user}\n\nYour last reply was rejected: {error}. Reply with valid JSON only."
    return None
