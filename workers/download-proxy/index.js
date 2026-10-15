// download-proxy: streams a third-party IPA to the person downloading it, saved as "<App>_<version>.ipa",
// without ever showing them (or the page) the source's URL.
//
//   GET https://dl.getaccretion.app/<App>_<version>.ipa?t=<token>
//
// The token comes from the store's download function (supabase/functions/download), which checks the
// account, the rate limit and the private link table first. It is AES-256-GCM encrypted with the
// DOWNLOAD_PROXY_KEY secret both sides share, so it can't be read, changed or made up here:
//   base64url( 12-byte IV | ciphertext of {"u": upstream https URL, "n": file name, "e": expiry ms} )
// Nothing is stored or logged by this Worker; files pass through and are never cached.

const NAME = /^[A-Za-z0-9-]{1,64}_[A-Za-z0-9.-]{1,32}\.ipa$/;
const FORWARD = ["content-length", "content-range", "accept-ranges", "last-modified", "etag"];

function b64url(text) {
  const bin = atob(text.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((text.length + 3) % 4));
  return Uint8Array.from(bin, (c) => c.charCodeAt(0));
}

async function readToken(token, secret) {
  try {
    const raw = b64url(token);
    if (raw.length < 13 + 16) return null;
    const key = await crypto.subtle.importKey("raw", b64url(secret), "AES-GCM", false, ["decrypt"]);
    const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv: raw.slice(0, 12) }, key, raw.slice(12));
    const data = JSON.parse(new TextDecoder().decode(plain));
    if (typeof data.u !== "string" || typeof data.n !== "string" || typeof data.e !== "number") return null;
    return data;
  } catch {
    return null;
  }
}

const say = (status, message) =>
  new Response(message + "\n", {
    status,
    headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store", "X-Robots-Tag": "noindex" },
  });

export default {
  async fetch(request, env) {
    if (request.method !== "GET" && request.method !== "HEAD") return say(405, "Only downloads here.");
    if (!env.DOWNLOAD_PROXY_KEY) return say(503, "Downloads are not set up yet.");
    const url = new URL(request.url);
    const name = decodeURIComponent(url.pathname.slice(1));
    const data = await readToken(url.searchParams.get("t") ?? "", env.DOWNLOAD_PROXY_KEY);
    if (!data || data.n !== name || !NAME.test(name)) return say(403, "This download link isn't valid. Start the download again from getaccretion.app.");
    if (Date.now() > data.e) return say(410, "This download link has expired. Start the download again from getaccretion.app.");
    let upstream;
    try {
      upstream = new URL(data.u);
    } catch {
      return say(403, "This download link isn't valid.");
    }
    if (upstream.protocol !== "https:" || upstream.username || upstream.password) return say(403, "This download link isn't valid.");

    const headers = { "User-Agent": "Accretion-Download/1.0", Accept: "*/*" };
    const range = request.headers.get("Range");
    if (range && /^bytes=\d*-\d*$/.test(range)) headers.Range = range;
    let source;
    try {
      source = await fetch(upstream.href, { method: request.method, headers, redirect: "follow", cf: { cacheTtl: 0, cacheEverything: false } });
    } catch {
      return say(502, "The app's source didn't answer. Try again later.");
    }
    if (source.status !== 200 && source.status !== 206) return say(502, `The app's source answered ${source.status}. Try again later.`);

    const out = new Headers({
      "Content-Type": "application/octet-stream",
      "Content-Disposition": `attachment; filename="${name}"`,
      "Cache-Control": "private, no-store",
      "Referrer-Policy": "no-referrer",
      "X-Content-Type-Options": "nosniff",
      "X-Robots-Tag": "noindex",
    });
    for (const h of FORWARD) {
      const v = source.headers.get(h);
      if (v) out.set(h, v);
    }
    return new Response(request.method === "HEAD" ? null : source.body, { status: source.status, headers: out });
  },
};
