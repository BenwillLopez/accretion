// download: hands out Accretion's own builds (Accretion Mods, the Accretion app) to account holders.
//
//   GET /functions/v1/download?app=<bundle id>             with "Authorization: Bearer <user JWT>"
//   GET /functions/v1/download?app=<bundle id>&key=<key>   for AltStore, SideStore and Feather
//
// Answers with a redirect to a 5-minute link into the private "builds" bucket, or a short
// explanation (401 not signed in, 404 not hosted). Deployed with --no-verify-jwt so the key form
// works without a login; the function checks the login itself.
import { createClient } from "npm:@supabase/supabase-js@2.117.2";

const admin = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);

const cors = { "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "authorization, apikey" };
const reply = (status: number, message: string) =>
  new Response(JSON.stringify({ message }), { status, headers: { ...cors, "Content-Type": "application/json" } });

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response(null, { headers: cors });
  const url = new URL(req.url);
  const app = url.searchParams.get("app") ?? "";
  const key = url.searchParams.get("key") ?? "";
  if (!/^[A-Za-z0-9][A-Za-z0-9.-]*$/.test(app)) return reply(400, "Which app? Add ?app=<bundle id>.");

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
  if (!owner) return reply(401, "Sign in to your Accretion account to download, or use your personal source link.");

  const { data: build } = await admin
    .from("hosted_builds").select("path").eq("bundle_id", app)
    .order("created_at", { ascending: false }).limit(1).maybeSingle();
  if (!build) return reply(404, "Accretion doesn't host this app.");

  const { data: signed, error } = await admin.storage.from("builds").createSignedUrl(build.path, 300);
  if (error || !signed) return reply(500, "Couldn't prepare the download. Try again.");

  await admin.from("download_log").insert({ owner, bundle_id: app, via });
  return new Response(null, { status: 302, headers: { ...cors, Location: signed.signedUrl } });
});
