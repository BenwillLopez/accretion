// download-proxy: Accretion's one public download address, so people only ever see getaccretion.app
// (not supabase.co, cloudfront.net or a source's own host).
//
//   GET https://dl.getaccretion.app/<App>_<version>.ipa?t=<token>
//     streams an IPA (another source's, or one of our own builds) saved as "<App>_<version>.ipa",
//     without ever showing the person (or the page) where it really comes from.
//   GET https://dl.getaccretion.app/download?app=<bundle id>[&key=…&version=…]
//     the store's download function (supabase/functions/download) under this address; its answer
//     (a redirect to a /<App>_<version>.ipa link above, or a short message) is passed on as it is.
//   GET https://dl.getaccretion.app/manifest?bundleid=…&name=…&version=…&fetchurl=<local .ipa URL>
//     the install manifest for Semi Local installs (same as supabase/functions/manifest), so iOS
//     asks "dl.getaccretion.app would like to install …".
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

// /download: the download function (wrangler.toml [vars] DOWNLOAD_FUNCTION) under this address
const CORS = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "authorization, apikey" };

async function download(request, env, url) {
  if (request.method === "OPTIONS") return new Response(null, { headers: CORS });
  if (request.method !== "GET" && request.method !== "HEAD") return say(405, "Only downloads here.");
  if (!env.DOWNLOAD_FUNCTION) return say(503, "Downloads are not set up yet.");
  const headers = {};
  for (const h of ["authorization", "apikey", "accept"]) {
    const v = request.headers.get(h);
    if (v) headers[h] = v;
  }
  let answer;
  try {
    answer = await fetch(`${env.DOWNLOAD_FUNCTION}${url.search}`, { headers, redirect: "manual" });
  } catch {
    return say(502, "The download server didn't answer. Try again later.");
  }
  const out = new Headers({ ...CORS, "Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Robots-Tag": "noindex" });
  for (const h of ["location", "content-type"]) {
    const v = answer.headers.get(h);
    if (v) out.set(h, v);
  }
  return new Response(request.method === "HEAD" ? null : answer.body, { status: answer.status, headers: out });
}

const escapeXML = (text) =>
  text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&apos;");

// 127.0.0.0/8, 10/8, 172.16/12, 192.168/16, 169.254/16 and localhost: the device itself or its network
function isLocalHost(host) {
  if (host === "localhost") return true;
  const parts = host.split(".").map(Number);
  if (parts.length !== 4 || parts.some((p) => !Number.isInteger(p) || p < 0 || p > 255)) return false;
  const [a, b] = parts;
  return a === 127 || a === 10 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168) || (a === 169 && b === 254);
}

// /manifest: Semi Local serves the app itself from the iPhone; this is the small HTTPS manifest that
// points iOS at it. Nothing is stored or logged, and the file must be on the device or a private
// network address, so this can't be used to push installs from the internet.
function manifest(url) {
  const params = url.searchParams;
  const bundleID = params.get("bundleid") ?? "";
  const name = params.get("name") ?? "";
  const version = params.get("version") ?? "";
  if (!/^[A-Za-z0-9.-]{1,200}$/.test(bundleID)) return say(400, "bundleid is missing or invalid.");
  if (!name || name.length > 200) return say(400, "name is missing or too long.");
  if (!version || version.length > 64) return say(400, "version is missing or too long.");
  let target;
  try {
    target = new URL(params.get("fetchurl") ?? "");
  } catch {
    return say(400, "fetchurl is not a URL.");
  }
  if (
    !["http:", "https:"].includes(target.protocol) || !isLocalHost(target.hostname) ||
    !target.pathname.endsWith(".ipa") || target.username || target.password
  ) {
    return say(400, "fetchurl must point to an .ipa on this device or its local network.");
  }
  const plist = `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>items</key>
  <array>
    <dict>
      <key>assets</key>
      <array>
        <dict>
          <key>kind</key><string>software-package</string>
          <key>url</key><string>${escapeXML(target.href)}</string>
        </dict>
      </array>
      <key>metadata</key>
      <dict>
        <key>bundle-identifier</key><string>${escapeXML(bundleID)}</string>
        <key>bundle-version</key><string>${escapeXML(version)}</string>
        <key>kind</key><string>software</string>
        <key>title</key><string>${escapeXML(name)}</string>
      </dict>
    </dict>
  </array>
</dict>
</plist>
`;
  return new Response(plist, {
    headers: {
      "Content-Type": "application/xml; charset=utf-8",
      "Cache-Control": "no-store",
      "Referrer-Policy": "no-referrer",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

const say = (status, message) =>
  new Response(message + "\n", {
    status,
    headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store", "X-Robots-Tag": "noindex" },
  });

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/download") return download(request, env, url);
    if (request.method !== "GET" && request.method !== "HEAD") return say(405, "Only downloads here.");
    if (url.pathname === "/manifest") return manifest(url);
    if (!env.DOWNLOAD_PROXY_KEY) return say(503, "Downloads are not set up yet.");
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
