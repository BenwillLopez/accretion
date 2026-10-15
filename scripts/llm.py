"""One door to the free language models (Google Gemini and OpenRouter ":free" models).

ask() tries the models in ai/models.json in order and returns the first usable answer, or None.
Up to 3 neighbouring OpenRouter models go out as ONE request (OpenRouter's "models" fallback list
tries them in order). A model that answers 429 (rate limited), 503 (busy) or 404 (gone) is skipped
for the rest of the run; when a grouped request fails, all of its models are. Providers without a
key (GEMINI_API_KEY, OPENROUTER_API_KEY) are skipped. Only free models are ever called: OpenRouter
ids must end in ":free". llm.last_model names the model that answered.
embed() gives free Gemini embeddings; ask_image() asks the Gemini models about one image.
"""

import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

from common import path

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
KEYS = {"gemini": "GEMINI_API_KEY", "openrouter": "OPENROUTER_API_KEY"}
BUSY_CODES = (404, 429, 503)
GROUP_MAX = 3  # most OpenRouter models one request may list

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


def call_group(specs, system, user, max_tokens):
    """One OpenRouter request listing several models (tried in order): (answer text, spec that
    answered). Raises HTTPError, URLError or ValueError."""
    key = os.environ.get(KEYS["openrouter"], "").strip()
    body = {
        "models": [spec.partition(":")[2] for spec in specs],
        "max_tokens": max_tokens,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    data = post(OPENROUTER_URL, {"Authorization": f"Bearer {key}"}, body)
    text = (data["choices"][0]["message"]["content"] or "").strip()
    returned = str(data.get("model") or "")
    for spec in specs:
        if spec.partition(":")[2].removesuffix(":free") == returned.removesuffix(":free"):
            return text, spec
    return text, "openrouter:" + returned


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
    specs = [spec for spec in order if spec not in busy and usable(spec)]
    i = 0
    while i < len(specs):
        group = specs[i : i + 1]
        if group[0].startswith("openrouter:"):
            while (
                len(group) < GROUP_MAX
                and i + len(group) < len(specs)
                and specs[i + len(group)].startswith("openrouter:")
            ):
                group.append(specs[i + len(group)])
        i += len(group)
        while group:
            prompt, answered = user, None
            for _ in range(2 if schema else 1):
                try:
                    if len(group) > 1:
                        raw, answered = call_group(group, system, prompt, max_tokens)
                    else:
                        answered = group[0]
                        raw = call(answered, system, prompt, max_tokens)
                except urllib.error.HTTPError as e:
                    if e.code in BUSY_CODES:
                        busy.update(group)
                    print(f"llm[{task}]: {', '.join(group)} answered {e.code}", file=sys.stderr)
                    group = []
                    break
                except (urllib.error.URLError, KeyError, IndexError, ValueError, TimeoutError, OSError) as e:
                    print(f"llm[{task}]: {', '.join(group)} failed ({type(e).__name__})", file=sys.stderr)
                    group = []
                    break
                if not schema:
                    if raw:
                        last_model = answered
                        return raw
                    break
                data, error = parse(raw, schema)
                if data is not None:
                    last_model = answered
                    return data
                prompt = f"{user}\n\nYour last reply was rejected: {error}. Reply with valid JSON only."
            # the model that answered gave nothing usable: the rest of the group goes out again
            if group:
                group.remove(answered if answered in group else group[0])
    return None


EMBED_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:batchEmbedContents"
EMBED_BATCH = 100  # most texts one request may carry
EMBED_PAUSE = 20  # seconds to wait before the one retry after a 429 or 503


def embed(texts, dims=256, pause=EMBED_PAUSE):
    """One vector (list of floats) per text from the free Gemini embedding model, or None when the
    key is missing or the model stays busy (429/503: one retry after a pause) or fails."""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    out = []
    for i in range(0, len(texts), EMBED_BATCH):
        chunk = texts[i : i + EMBED_BATCH]
        body = {
            "requests": [
                {
                    "model": "models/gemini-embedding-001",
                    "content": {"parts": [{"text": t}]},
                    "outputDimensionality": dims,
                }
                for t in chunk
            ]
        }
        for attempt in range(2):
            try:
                data = post(EMBED_URL, {"x-goog-api-key": key}, body)
                vectors = [e["values"] for e in data["embeddings"]]
                if len(vectors) != len(chunk):
                    raise ValueError("wrong number of embeddings")
                out.extend(vectors)
                break
            except urllib.error.HTTPError as e:
                print(f"llm[embed]: answered {e.code}", file=sys.stderr)
                if e.code in (429, 503) and attempt == 0:
                    time.sleep(pause)
                    continue
                return None
            except (urllib.error.URLError, KeyError, IndexError, ValueError, TimeoutError, OSError) as e:
                print(f"llm[embed]: failed ({type(e).__name__})", file=sys.stderr)
                return None
    return out


def call_image(spec, system, user, mime, data, max_tokens):
    """One Gemini request with an inline image: the answer text."""
    model = spec.partition(":")[2]
    key = os.environ.get(KEYS["gemini"], "").strip()
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": user},
                    {"inlineData": {"mimeType": mime, "data": base64.b64encode(data).decode()}},
                ],
            }
        ],
        "generationConfig": {"maxOutputTokens": max_tokens * 4},
    }
    out = post(GEMINI_URL.format(model), {"x-goog-api-key": key}, body)
    parts = out["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts).strip()


def ask_image(task, system, user, mime, data, schema, max_tokens=200):
    """Like ask() for one image and a JSON schema; only Gemini models from ai/models.json are used.
    Returns the dict or None."""
    global last_model
    last_model = None
    system += (
        "\n\nReply with one JSON object only, no markdown fences and no other text. Keys: "
        + ", ".join(
            f"{k} ({'one of ' + '/'.join(map(str, s)) if isinstance(s, (list, tuple, set)) else s})"
            for k, s in schema.items()
        )
        + "."
    )
    for spec in config().get("order", []):
        if not spec.startswith("gemini:") or spec in busy or not usable(spec):
            continue
        prompt = user
        for _ in range(2):
            try:
                raw = call_image(spec, system, prompt, mime, data, max_tokens)
            except urllib.error.HTTPError as e:
                if e.code in BUSY_CODES:
                    busy.add(spec)
                print(f"llm[{task}]: {spec} answered {e.code}", file=sys.stderr)
                break
            except (urllib.error.URLError, KeyError, IndexError, ValueError, TimeoutError, OSError) as e:
                print(f"llm[{task}]: {spec} failed ({type(e).__name__})", file=sys.stderr)
                break
            parsed, error = parse(raw, schema)
            if parsed is not None:
                last_model = spec
                return parsed
            prompt = f"{user}\n\nYour last reply was rejected: {error}. Reply with valid JSON only."
    return None
