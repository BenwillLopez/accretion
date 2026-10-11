// source: a personal copy of an AltStore source whose apps Accretion hosts, for apps that can't
// sign in (AltStore, SideStore, Feather, ESign).
//
//   GET /functions/v1/source?key=<personal key>&name=mods|app
//
// Fetches the public source (Accretion Mods or the Accretion app), checks the key, and points
// every hosted app's download at /download?app=…&key=…, so downloads keep working while the
// files themselves stay private. Apps Accretion doesn't host keep their original links.
import { createClient } from "npm:@supabase/supabase-js@2.117.2";

const admin = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);

const SOURCES: Record<string, string> = {
  mods: "https://raw.githubusercontent.com/AccretionMods/mods/main/mods.json",
  app: "https://raw.githubusercontent.com/GETAccretion/accretion-app/main/app-repo.json",
};

const reply = (status: number, message: string) =>
  new Response(JSON.stringify({ message }), { status, headers: { "Content-Type": "application/json" } });

type Version = { downloadURL?: string };
type App = { bundleIdentifier?: string; downloadURL?: string; versions?: Version[] };

Deno.serve(async (req) => {
  const url = new URL(req.url);
  const key = url.searchParams.get("key") ?? "";
  const upstream = SOURCES[url.searchParams.get("name") ?? "mods"];
  if (!upstream) return reply(400, "Unknown source. Use name=mods or name=app.");
  if (!/^[0-9a-f]{64}$/.test(key)) return reply(401, "This link needs your personal key. Copy it from your Accretion account.");

  const { data: holder } = await admin.from("download_keys").select("owner").eq("key", key).maybeSingle();
  if (!holder) return reply(401, "This key isn't valid any more. Copy your current source link from your Accretion account.");

  const response = await fetch(upstream);
  if (!response.ok) return reply(502, "Couldn't load the source. Try again shortly.");
  const source = await response.json();

  const { data: hosted } = await admin.from("hosted_builds").select("bundle_id");
  const hostedIds = new Set((hosted ?? []).map((row: { bundle_id: string }) => row.bundle_id));
  const base = `${Deno.env.get("SUPABASE_URL")}/functions/v1/download`;

  for (const app of (source.apps ?? []) as App[]) {
    if (!app.bundleIdentifier || !hostedIds.has(app.bundleIdentifier)) continue;
    const link = `${base}?app=${encodeURIComponent(app.bundleIdentifier)}&key=${key}`;
    app.downloadURL = link;
    for (const version of app.versions ?? []) version.downloadURL = link;
  }
  source.sourceURL = url.toString();
  return new Response(JSON.stringify(source), {
    headers: { "Content-Type": "application/json", "Cache-Control": "private, max-age=300" },
  });
});
