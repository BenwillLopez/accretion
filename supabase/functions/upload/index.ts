// upload: puts a new build of Accretion's own apps (the Accretion app, Accretion Mods) straight
// into the private "builds" bucket, so release files never sit in a public GitHub release.
//
//   POST /functions/v1/upload            {bundle_id, version}         → {signedUrl, path}
//        then PUT the .ipa to signedUrl (Content-Type: application/octet-stream)
//   POST /functions/v1/upload?finish=1   {bundle_id, version, size}   → {path}
//
// Every call needs "x-upload-key: <UPLOAD_KEY>", a secret only the release workflows and the
// mods publish script hold. Deployed with --no-verify-jwt; the key is the check.
import { createClient } from "npm:@supabase/supabase-js@2.117.2";

const admin = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);

const reply = (status: number, body: Record<string, unknown>) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

// constant-time comparison, so the key can't be guessed one character at a time
function same(a: string, b: string): boolean {
  const x = new TextEncoder().encode(a);
  const y = new TextEncoder().encode(b);
  if (x.length !== y.length) return false;
  let diff = 0;
  for (let i = 0; i < x.length; i++) diff |= x[i] ^ y[i];
  return diff === 0;
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return reply(405, { message: "Use POST." });
  const expected = Deno.env.get("UPLOAD_KEY") ?? "";
  if (expected.length < 32 || !same(req.headers.get("x-upload-key") ?? "", expected)) {
    return reply(401, { message: "Not allowed." });
  }

  let body: { bundle_id?: string; version?: string; size?: number };
  try {
    body = await req.json();
  } catch {
    return reply(400, { message: "Send JSON: {bundle_id, version}." });
  }
  const bundle = body.bundle_id ?? "";
  const version = body.version ?? "";
  if (!/^[A-Za-z0-9][A-Za-z0-9.-]*$/.test(bundle) || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$/.test(version)) {
    return reply(400, { message: "bundle_id or version looks wrong." });
  }
  const path = `${bundle}/${version}.ipa`;

  if (new URL(req.url).searchParams.get("finish") !== "1") {
    const { data, error } = await admin.storage.from("builds").createSignedUploadUrl(path, { upsert: true });
    if (error || !data) return reply(500, { message: `Couldn't prepare the upload: ${error?.message ?? "unknown"}` });
    return reply(200, { signedUrl: data.signedUrl, path });
  }

  // finish: the file must be there before the download server starts handing it out
  const { data: files } = await admin.storage.from("builds").list(bundle, { search: `${version}.ipa` });
  if (!files?.some((f: { name: string }) => f.name === `${version}.ipa`)) {
    return reply(409, { message: "The file isn't in storage yet. Upload it first." });
  }
  await admin.from("hosted_builds").delete().eq("bundle_id", bundle).eq("version", version);
  const { error } = await admin.from("hosted_builds").insert({
    bundle_id: bundle,
    version,
    path,
    size: typeof body.size === "number" ? body.size : null,
  });
  if (error) return reply(500, { message: `Couldn't record the build: ${error.message}` });
  return reply(200, { path });
});
