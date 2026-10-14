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
// The Accretion app itself is always served at its newest release; betas (1.0.25.1) only by exact version.
//
// Builds are served from the CloudFront distribution in aws/builds-cdn.yaml when CDN_DOMAIN,
// CDN_KEY_PAIR_ID and CDN_PRIVATE_KEY are set, and from the Supabase "builds" bucket otherwise.
// Before each CloudFront redirect the function checks that CloudFront actually serves that file;
// if AWS is down, stopped or missing the file, the Supabase copy is served instead.
import { createClient } from "npm:@supabase/supabase-js@2.117.2";
import { getSignedUrl } from "npm:@aws-sdk/cloudfront-signer@3.1149.0";
import { createHash } from "node:crypto";

const admin = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);

const CDN_DOMAIN = Deno.env.get("CDN_DOMAIN") ?? "";
const CDN_KEY_PAIR_ID = Deno.env.get("CDN_KEY_PAIR_ID") ?? "";
const CDN_PRIVATE_KEY = (Deno.env.get("CDN_PRIVATE_KEY") ?? "").replace(/\\n/g, "\n");

// a 5-minute CloudFront link, only if CloudFront answers for that file right now
async function cdnLink(path: string): Promise<string | null> {
  if (!CDN_DOMAIN || !CDN_KEY_PAIR_ID || !CDN_PRIVATE_KEY) return null;
  try {
    const link = getSignedUrl({
      url: `https://${CDN_DOMAIN}/${path.split("/").map(encodeURIComponent).join("/")}`,
      keyPairId: CDN_KEY_PAIR_ID,
      privateKey: CDN_PRIVATE_KEY,
      dateLessThan: new Date(Date.now() + 300_000).toISOString(),
    });
    const check = await fetch(link, { method: "HEAD", signal: AbortSignal.timeout(4000) });
    if (check.ok) return link;
    console.warn(`CloudFront answered ${check.status} for ${path}; serving it from Supabase`);
  } catch (e) {
    console.warn(`CloudFront unreachable for ${path} (${e instanceof Error ? e.message : e}); serving it from Supabase`);
  }
  return null;
}

// The third copy: an Oracle Cloud server (handbook infra/) that pulls builds from S3 and serves
// /builds/<path> only with an nginx secure_link: md5 = base64url(md5("<expires>/builds/<path> <secret>")).
const OCI_BUILDS_HOST = Deno.env.get("OCI_BUILDS_HOST") ?? "";
const OCI_LINK_SECRET = Deno.env.get("OCI_LINK_SECRET") ?? "";

async function ociLink(path: string): Promise<string | null> {
  if (!OCI_BUILDS_HOST || !OCI_LINK_SECRET) return null;
  try {
    const expires = Math.floor(Date.now() / 1000) + 300;
    const uri = `/builds/${path}`;
    const digest = createHash("md5").update(`${expires}${uri} ${OCI_LINK_SECRET}`).digest("base64")
      .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    const link = `https://${OCI_BUILDS_HOST}/builds/${path.split("/").map(encodeURIComponent).join("/")}?md5=${digest}&expires=${expires}`;
    const check = await fetch(link, { method: "HEAD", signal: AbortSignal.timeout(4000) });
    if (check.ok) return link;
    console.warn(`The Oracle copy answered ${check.status} for ${path}`);
  } catch (e) {
    console.warn(`The Oracle copy is unreachable for ${path} (${e instanceof Error ? e.message : e})`);
  }
  return null;
}

// a 5-minute link to one build: CloudFront when it's healthy, then the Supabase copy, then the
// Oracle copy
async function signedLink(path: string): Promise<string | null> {
  const cdn = await cdnLink(path);
  if (cdn) return cdn;
  const { data, error } = await admin.storage.from("builds").createSignedUrl(path, 300);
  if (!error && data) return data.signedUrl;
  console.warn(`No Supabase copy of ${path} (${error?.message ?? "unknown"}); trying the Oracle copy`);
  return await ociLink(path);
}

const cors = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "authorization, apikey" };
const reply = (status: number, message: string) =>
  new Response(JSON.stringify({ message }), { status, headers: { ...cors, "Content-Type": "application/json" } });

const ACCRETION = "io.github.getaccretion.Accretion";
const STORE = "https://getaccretion.app/";

// "1.0.10" > "1.0.9": every number in order, like the app and the store pipeline: "4.0.0-mod1.10.0" > "4.0.0-mod1.9.0" > "4.0.0"
function older(a: string, b: string): boolean {
  const x = (a.match(/\d+/g) ?? []).map(Number);
  const y = (b.match(/\d+/g) ?? []).map(Number);
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
  const { data: profile, error: profileError } = await admin.from("profiles").select("banned").eq("id", owner).maybeSingle();
  if (profileError) return reply(503, "Couldn't check account access. Try again.");
  if (!profile || profile.banned) return reply(403, "This account can't download right now.");
  const since = new Date(Date.now() - 10 * 60_000).toISOString();
  const { count, error: quotaError } = await admin.from("download_log").select("id", { count: "exact", head: true })
    .eq("owner", owner).gte("at", since);
  if (quotaError || count === null) return reply(503, "Couldn't check download limits. Try again.");
  if ((count ?? 0) >= 30) return reply(429, "Too many downloads. Try again in a few minutes.");

  // newest by version number, not upload time (an old version re-uploaded can't become "newest");
  // Accretion itself is always served at its newest version
  const { data: rows, error: buildsError } = await admin.from("hosted_builds").select("path,version").eq("bundle_id", app);
  if (buildsError) return reply(503, "Couldn't check available builds. Try again.");
  const builds = (rows ?? []) as { path: string; version: string }[];
  // Accretion betas have four numbers (1.0.25.1, between 1.0.25 and 1.0.26): served only when asked
  // for by version (app-repo-beta.json links them that way), never as "the newest Accretion"
  const isBeta = (v: string) => /^\d+\.\d+\.\d+\.\d+$/.test(v);
  const build = version && (app !== ACCRETION || isBeta(version))
    ? builds.find((b) => b.version === version)
    : builds
      .filter((b) => app !== ACCRETION || !isBeta(b.version))
      .sort((a, b) => (older(a.version, b.version) ? 1 : older(b.version, a.version) ? -1 : 0))[0];
  if (!build) return reply(404, "Accretion doesn't host this app.");

  const location = await signedLink(build.path);
  if (!location) return reply(500, "Couldn't prepare the download. Try again.");

  const { error: logError } = await admin.from("download_log").insert({ owner, bundle_id: app, via });
  if (logError?.code === "PT403") return reply(403, "This account can't download right now.");
  if (logError?.code === "PT429") return reply(429, "Too many downloads. Try again in a few minutes.");
  if (logError) return reply(503, "Couldn't record the download. Try again.");
  return new Response(null, {
    status: 302,
    headers: { ...cors, Location: location, "Cache-Control": "no-store", "Referrer-Policy": "no-referrer" },
  });
});
