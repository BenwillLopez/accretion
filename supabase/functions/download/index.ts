// download: hands out Accretion's own builds (Accretion Mods, the Accretion app) to account holders.
//
//   GET /functions/v1/download?app=<bundle id>             with "Authorization: Bearer <user JWT>"
//   GET /functions/v1/download?app=<bundle id>&key=<key>   for AltStore, SideStore and Feather
//   add &version=<x> for a particular version (sources list every version); newest otherwise
//
// Answers with a redirect to a 5-minute link into the private "builds" bucket, or a short
// explanation (401 not signed in, 404 not hosted, 426 Accretion too old). A browser that isn't
// signed in is sent to the app's store page instead. Deployed with --no-verify-jwt so the key
// form works without a login; the function checks the login itself.
//
// Old Accretion versions: the app adds &av=<its version> (1.0.5 and newer), and requests below
// "minimumVersion" in the store's app-config.json are refused, except for downloading Accretion
// itself, so every old copy can still update. (1.0.4 and older can't be told apart from the
// Feather app, so the store hides everything but the update from them instead: data/index.json.)
// The Accretion app itself is always served at its newest version.
import { createClient } from "npm:@supabase/supabase-js@2.117.2";

const admin = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);

const cors = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "authorization, apikey" };
const reply = (status: number, message: string) =>
  new Response(JSON.stringify({ message }), { status, headers: { ...cors, "Content-Type": "application/json" } });

const ACCRETION = "io.github.getaccretion.Accretion";
const STORE = "https://getaccretion.github.io/";

// "1.0.10" > "1.0.9"
function older(a: string, b: string): boolean {
  const x = a.split(".").map((n) => parseInt(n, 10) || 0);
  const y = b.split(".").map((n) => parseInt(n, 10) || 0);
  for (let i = 0; i < Math.max(x.length, y.length); i++) {
    if ((x[i] ?? 0) !== (y[i] ?? 0)) return (x[i] ?? 0) < (y[i] ?? 0);
  }
  return false;
}

// the store's minimum Accretion version, re-read every 5 minutes
let minimum = { version: "", at: 0 };
async function minimumVersion(): Promise<string> {
  if (Date.now() - minimum.at < 300_000) return minimum.version;
  try {
    const r = await fetch(`${STORE}app-config.json`, { headers: { "Cache-Control": "no-cache" } });
    const json = r.ok ? await r.json() : {};
    minimum = { version: typeof json.minimumVersion === "string" ? json.minimumVersion : "", at: Date.now() };
  } catch {
    minimum = { version: minimum.version, at: Date.now() };
  }
  return minimum.version;
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: cors });
  const url = new URL(req.url);
  const app = url.searchParams.get("app") ?? "";
  const key = url.searchParams.get("key") ?? "";
  const version = url.searchParams.get("version") ?? "";
  if (!/^[A-Za-z0-9][A-Za-z0-9.-]*$/.test(app)) return reply(400, "Which app? Add ?app=<bundle id>.");

  // Accretion copies below the minimum may only fetch Accretion itself
  const appVersion = url.searchParams.get("av") ?? "";
  if (app !== ACCRETION && appVersion) {
    const min = await minimumVersion();
    if (min && older(appVersion, min)) {
      return reply(426, "This version of Accretion is too old. Update Accretion to keep downloading apps.");
    }
  }

  // who is asking: a signed-in user, or the owner of a personal key
  let owner: string | null = null;
  let via: "login" | "key" = "login";
  const bearer = (req.headers.get("Authorization") ?? "").replace(/^Bearer\s+/i, "");
  if (bearer) {
    const { data } = await admin.auth.getUser(bearer);
    owner = data.user?.id ?? null;
  }
  if (!owner && /^[0-9a-f]{64}$/.test(key)) {
    const { data } = await admin.from("download_keys").select("owner").eq("key", key).maybeSingle();
    owner = data?.owner ?? null;
    via = "key";
  }
  if (!owner) {
    // someone opened the link in a browser: send them to the store page to sign in there
    if ((req.headers.get("Accept") ?? "").includes("text/html")) {
      return new Response(null, { status: 302, headers: { ...cors, Location: `${STORE}#/app/${encodeURIComponent(app)}` } });
    }
    return reply(401, "Sign in to your Accretion account to download, or use your personal source link.");
  }

  // banned accounts don't download, and nobody gets more than 30 downloads in 10 minutes
  const { data: profile } = await admin.from("profiles").select("banned").eq("id", owner).maybeSingle();
  if (profile?.banned) return reply(403, "This account can't download right now.");
  const since = new Date(Date.now() - 10 * 60_000).toISOString();
  const { count } = await admin.from("download_log").select("id", { count: "exact", head: true })
    .eq("owner", owner).gte("at", since);
  if ((count ?? 0) >= 30) return reply(429, "Too many downloads. Try again in a few minutes.");

  // newest by version number, not upload time (an old version re-uploaded can't become "newest");
  // Accretion itself is always served at its newest version
  const { data: rows } = await admin.from("hosted_builds").select("path,version").eq("bundle_id", app);
  const builds = (rows ?? []) as { path: string; version: string }[];
  const build = version && app !== ACCRETION
    ? builds.find((b) => b.version === version)
    : builds.sort((a, b) => (older(a.version, b.version) ? 1 : older(b.version, a.version) ? -1 : 0))[0];
  if (!build) return reply(404, "Accretion doesn't host this app.");

  const { data: signed, error } = await admin.storage.from("builds").createSignedUrl(build.path, 300);
  if (error || !signed) return reply(500, "Couldn't prepare the download. Try again.");

  await admin.from("download_log").insert({ owner, bundle_id: app, via });
  return new Response(null, {
    status: 302,
    headers: { ...cors, Location: signed.signedUrl, "Cache-Control": "no-store", "Referrer-Policy": "no-referrer" },
  });
});
