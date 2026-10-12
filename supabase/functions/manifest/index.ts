// manifest: the install manifest for Accretion's Semi Local installs.
//
//   GET /functions/v1/manifest?bundleid=<id>&name=<name>&version=<v>&fetchurl=<local .ipa URL>
//
// iOS only installs over the air from a manifest served over HTTPS. Semi Local serves the app
// itself from the iPhone (plain HTTP on the device or local network), and this function returns
// the small manifest that points iOS at it. Nothing is stored or logged. The app file must be on
// the device or a private network address, so this can't be used to push installs from the internet.

const reply = (status: number, message: string) =>
  new Response(JSON.stringify({ message }), {
    status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });

const escapeXML = (text: string) =>
  text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&apos;");

// 127.0.0.0/8, 10/8, 172.16/12, 192.168/16, 169.254/16 and localhost: the device itself or its network
function isLocalHost(host: string): boolean {
  if (host === "localhost") return true;
  const parts = host.split(".").map(Number);
  if (parts.length !== 4 || parts.some((p) => !Number.isInteger(p) || p < 0 || p > 255)) return false;
  const [a, b] = parts;
  return a === 127 || a === 10 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168) || (a === 169 && b === 254);
}

Deno.serve((req) => {
  if (req.method !== "GET") return reply(405, "Use GET.");
  const params = new URL(req.url).searchParams;
  const bundleID = params.get("bundleid") ?? "";
  const name = params.get("name") ?? "";
  const version = params.get("version") ?? "";
  const fetchURL = params.get("fetchurl") ?? "";

  if (!/^[A-Za-z0-9.\-]{1,200}$/.test(bundleID)) return reply(400, "bundleid is missing or invalid.");
  if (!name || name.length > 200) return reply(400, "name is missing or too long.");
  if (!version || version.length > 64) return reply(400, "version is missing or too long.");

  let target: URL;
  try {
    target = new URL(fetchURL);
  } catch {
    return reply(400, "fetchurl is not a URL.");
  }
  if (
    !["http:", "https:"].includes(target.protocol) || !isLocalHost(target.hostname) ||
    !target.pathname.endsWith(".ipa") || target.username || target.password
  ) {
    return reply(400, "fetchurl must point to an .ipa on this device or its local network.");
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
});
