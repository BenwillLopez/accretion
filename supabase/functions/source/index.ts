// source: a personal copy of an AltStore source whose apps Accretion hosts, for apps that can't
// sign in (AltStore, SideStore, Feather, ESign).
//
//   GET /functions/v1/source?key=<personal key>&name=mods|app|store|curated
//
// Fetches the public source (Accretion Mods, the Accretion app, or the whole store: source.json /
// curated.json), checks the key, and points every hosted app's download at /download?app=…&key=…,
// so downloads keep working while the files themselves stay private. Store sources already carry
// /download links without a key (no source URL is published); this adds the key to each.
import { createClient } from "npm:@supabase/supabase-js@2.117.2";

const admin = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);

const SOURCES: Record<string, string> = {
  mods: "https://raw.githubusercontent.com/AccretionMods/mods/main/mods.json",
  app: "https://raw.githubusercontent.com/GETAccretion/accretion-app/main/app-repo.json",
  store: "https://getaccretion.app/source.json",
  curated: "https://getaccretion.app/curated.json",
};

const reply = (status: number, message: string) =>
  new Response(JSON.stringify({ message }), { status, headers: { "Content-Type": "application/json" } });

const cache = new Map<string, { text: string; at: number }>();

type Version = { version?: string; downloadURL?: string };
type App = { bundleIdentifier?: string; downloadURL?: string; versions?: Version[] };

Deno.serve(async (req) => {
  const url = new URL(req.url);
  const key = url.searchParams.get("key") ?? "";
  const name = url.searchParams.get("name") ?? "mods";
  if (!Object.hasOwn(SOURCES, name)) return reply(400, "Unknown source. Use name=mods, app, store or curated.");
  const upstream = SOURCES[name];
  if (!/^[0-9a-f]{64}$/.test(key)) return reply(401, "This link needs your personal key. Copy it from your Accretion account.");

  const { data: holder } = await admin.from("download_keys").select("owner").eq("key", key).maybeSingle();
  if (!holder) return reply(401, "This key isn't valid any more. Copy your current source link from your Accretion account.");

  // the public source changes rarely: fetch it at most every 5 minutes per instance
  let cached = cache.get(upstream);
  if (!cached || Date.now() - cached.at > 300_000) {
    const response = await fetch(upstream);
    if (!response.ok) {
      if (!cached) return reply(502, "Couldn't load the source. Try again shortly.");
    } else {
      cached = { text: await response.text(), at: Date.now() };
      cache.set(upstream, cached);
    }
  }
  const source = JSON.parse(cached!.text);

  const { data: hosted } = await admin.from("hosted_builds").select("bundle_id");
  const hostedIds = new Set((hosted ?? []).map((row: { bundle_id: string }) => row.bundle_id));
  const base = `${Deno.env.get("SUPABASE_URL")}/functions/v1/download`;

  // a /download link from the store's data: same server, needs only the key
  const keyed = (link?: string) =>
    link && link.startsWith(`${base}?`) && !/[?&]key=/.test(link) ? `${link}&key=${key}` : link;
  for (const app of (source.apps ?? []) as App[]) {
    if (!app.bundleIdentifier) continue;
    if (!hostedIds.has(app.bundleIdentifier)) {
      app.downloadURL = keyed(app.downloadURL);
      for (const version of app.versions ?? []) version.downloadURL = keyed(version.downloadURL);
      continue;
    }
    const link = `${base}?app=${encodeURIComponent(app.bundleIdentifier)}&key=${key}`;
    app.downloadURL = link;
    for (const version of app.versions ?? []) {
      version.downloadURL = version.version ? `${link}&version=${encodeURIComponent(version.version)}` : link;
    }
  }
  source.sourceURL = url.toString();
  return new Response(JSON.stringify(source), {
    headers: { "Content-Type": "application/json", "Cache-Control": "private, max-age=300" },
  });
});
