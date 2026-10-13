// upload: puts a new build of Accretion's own apps (the Accretion app, Accretion Mods) straight
// into the private "builds" bucket, so release files never sit in a public GitHub release.
//
//   POST /functions/v1/upload            {bundle_id, version}         → {signedUrl, path}
//        then PUT the .ipa to signedUrl (Content-Type: application/octet-stream)
//   POST /functions/v1/upload?finish=1   {bundle_id, version, size, sha256?, name?, notes?}   → {path, sha256}
//        also posts "<name> <version>" with the notes to the What's new feed (announce: false skips it)
//   POST /functions/v1/upload?base=put   {sha256}  → {signedUrl}  PUT a mod's private base .ipa
//   POST /functions/v1/upload?base=get   {sha256}  → {signedUrl}  GET it back (15 minutes)
//
// Every call needs "x-upload-key: <UPLOAD_KEY>", a secret only the release workflows and the
// mods publish script hold. Deployed with --no-verify-jwt; the key is the check.
//
// Builds go to the S3 bucket in aws/builds-cdn.yaml when BUILDS_BUCKET, BUILDS_REGION,
// BUILDS_AWS_KEY_ID and BUILDS_AWS_SECRET are set and S3 answers, and to the Supabase "builds"
// bucket otherwise. Every finished build is kept in both, so the download function can fall back
// to Supabase whenever AWS is unavailable.
import { createClient } from "npm:@supabase/supabase-js@2.117.2";
import {
  DeleteObjectCommand,
  GetObjectCommand,
  HeadBucketCommand,
  PutObjectCommand,
  S3Client,
} from "npm:@aws-sdk/client-s3@3.1149.0";
import { getSignedUrl } from "npm:@aws-sdk/s3-request-presigner@3.1149.0";

const admin = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);

const BUCKET = Deno.env.get("BUILDS_BUCKET") ?? "";
const s3 = BUCKET && Deno.env.get("BUILDS_AWS_KEY_ID") && Deno.env.get("BUILDS_AWS_SECRET")
  ? new S3Client({
    region: Deno.env.get("BUILDS_REGION") ?? "us-east-2",
    credentials: {
      accessKeyId: Deno.env.get("BUILDS_AWS_KEY_ID")!,
      secretAccessKey: Deno.env.get("BUILDS_AWS_SECRET")!,
    },
  })
  : null;

const IPA = "application/octet-stream";

// S3 is set up and answering right now
async function s3Healthy(): Promise<boolean> {
  if (!s3) return false;
  try {
    await s3.send(new HeadBucketCommand({ Bucket: BUCKET }), { abortSignal: AbortSignal.timeout(4000) });
    return true;
  } catch (e) {
    console.warn(`S3 unavailable (${e instanceof Error ? e.message : e}); using Supabase storage`);
    return false;
  }
}

// where the .ipa is PUT (valid 1 hour)
async function uploadLink(path: string): Promise<string | null> {
  if (s3 && await s3Healthy()) {
    return await getSignedUrl(s3, new PutObjectCommand({ Bucket: BUCKET, Key: path }), { expiresIn: 3600 });
  }
  const { data, error } = await admin.storage.from("builds").createSignedUploadUrl(path, { upsert: true });
  return error || !data ? null : data.signedUrl;
}

async function readFromS3(path: string): Promise<Uint8Array | null> {
  if (!s3) return null;
  try {
    const object = await s3.send(new GetObjectCommand({ Bucket: BUCKET, Key: path }));
    return object.Body ? await object.Body.transformToByteArray() : null;
  } catch {
    return null;
  }
}

async function readFromSupabase(path: string): Promise<Uint8Array | null> {
  const [bundle, file] = path.split("/");
  const { data: files } = await admin.storage.from("builds").list(bundle, { search: file });
  if (!files?.some((f: { name: string }) => f.name === file)) return null;
  const { data: blob } = await admin.storage.from("builds").download(path);
  return blob ? new Uint8Array(await blob.arrayBuffer()) : null;
}

// the stored file and where it was found, or null if it isn't anywhere
async function readBuild(path: string): Promise<{ bytes: Uint8Array; where: "s3" | "supabase" } | null> {
  const fromS3 = await readFromS3(path);
  if (fromS3) return { bytes: fromS3, where: "s3" };
  const fromSupabase = await readFromSupabase(path);
  return fromSupabase ? { bytes: fromSupabase, where: "supabase" } : null;
}

// keep a copy in the other store, so downloads still work if either one is down (best effort)
async function mirrorBuild(path: string, bytes: Uint8Array, where: "s3" | "supabase") {
  try {
    if (where === "s3") {
      const { error } = await admin.storage.from("builds").upload(path, bytes, { upsert: true, contentType: IPA });
      if (error) throw error;
    } else if (s3) {
      await s3.send(new PutObjectCommand({ Bucket: BUCKET, Key: path, Body: bytes, ContentType: IPA }));
    }
  } catch (e) {
    console.warn(`Couldn't copy ${path} from ${where} to the other store: ${e instanceof Error ? e.message : e}`);
  }
}

async function removeBuild(path: string) {
  if (s3) await s3.send(new DeleteObjectCommand({ Bucket: BUCKET, Key: path })).catch(() => {});
  await admin.storage.from("builds").remove([path]);
}

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

  // private base apps for mods (mods/scripts/base.py). Kept in S3 only, under bases/<sha256> (no
  // .ipa ending, so the Oracle mirror and the store copy script skip them), never listed anywhere
  // public. The mod build checks the file's sha256 itself.
  const baseMode = new URL(req.url).searchParams.get("base");
  if (baseMode === "put" || baseMode === "get") {
    const sha = String((body as { sha256?: string }).sha256 ?? "");
    if (!/^[0-9a-f]{64}$/.test(sha)) return reply(400, { message: "Send {sha256}: 64 lowercase hex characters." });
    if (!s3 || !(await s3Healthy())) return reply(503, { message: "S3 isn't available for base apps right now." });
    const Key = `bases/${sha}`;
    const signedUrl = baseMode === "put"
      ? await getSignedUrl(s3, new PutObjectCommand({ Bucket: BUCKET, Key }), { expiresIn: 3600 })
      : await getSignedUrl(s3, new GetObjectCommand({ Bucket: BUCKET, Key }), { expiresIn: 900 });
    return reply(200, { signedUrl, path: Key });
  }
  const bundle = body.bundle_id ?? "";
  const version = body.version ?? "";
  if (!/^[A-Za-z0-9][A-Za-z0-9.-]*$/.test(bundle) || !/^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$/.test(version)) {
    return reply(400, { message: "bundle_id or version looks wrong." });
  }
  const path = `${bundle}/${version}.ipa`;

  if (new URL(req.url).searchParams.get("finish") !== "1") {
    // a published version is never replaced: a leaked key can't swap a build people already have
    const { data: existing } = await admin.from("hosted_builds").select("id").eq("bundle_id", bundle).eq("version", version).maybeSingle();
    if (existing) return reply(409, { message: `${bundle} ${version} is already published. Bump the version.` });
    let signedUrl: string | null = null;
    let problem = "unknown";
    try {
      signedUrl = await uploadLink(path);
    } catch (e) {
      problem = e instanceof Error ? e.message : String(e);
    }
    if (!signedUrl) return reply(500, { message: `Couldn't prepare the upload: ${problem}` });
    return reply(200, { signedUrl, path });
  }

  // finish: the file must be there before the download server starts handing it out
  const stored = await readBuild(path);
  if (!stored) return reply(409, { message: "The file isn't in storage yet. Upload it first." });
  const bytes = stored.bytes;
  // fingerprint the stored file, so the app can check what it downloads is what was published
  const digest = await crypto.subtle.digest("SHA-256", bytes as Uint8Array<ArrayBuffer>);
  const sha256 = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
  const claimed = (body as { sha256?: string }).sha256;
  if (claimed && claimed.toLowerCase() !== sha256) {
    await removeBuild(path);
    return reply(422, { message: "The uploaded file doesn't match the sha256 that was sent. Upload it again." });
  }
  const { error } = await admin.from("hosted_builds").insert({
    bundle_id: bundle,
    version,
    path,
    size: bytes.byteLength,
    sha256,
  });
  if (error) return reply(500, { message: `Couldn't record the build: ${error.message}` });
  await mirrorBuild(path, bytes, stored.where);

  // the What's new feed: one post per published build (best effort; the build is already live)
  const extra = body as { name?: string; notes?: string; announce?: boolean };
  if (extra.announce !== false) {
    const isApp = bundle === "io.github.getaccretion.Accretion";
    const name = (extra.name ?? (isApp ? "Accretion" : bundle)).slice(0, 80);
    await admin.from("announcements").insert({
      kind: isApp ? "release" : "mod",
      title: `${name} ${version}`,
      body: (extra.notes ?? "").slice(0, 4000),
      app_id: bundle,
      version,
      link: `https://getaccretion.github.io/#/app/${encodeURIComponent(bundle)}`,
    });
  }
  return reply(200, { path, sha256 });
});
