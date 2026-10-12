# Community setup (Supabase)

Accounts, comments, likes, ratings, follows, the feed, notifications and moderation run on a
free [Supabase](https://supabase.com) project. The store works without it. The community
features turn on once the two settings below are set.

## Quick setup (one click)

1. **Sign up** at [supabase.com](https://supabase.com) (free) and open the dashboard once.
2. **Create an access token:** [supabase.com/dashboard/account/tokens](https://supabase.com/dashboard/account/tokens)
   → **Generate new token** → name it `accretion-setup` → copy it.
3. **Add it to GitHub:** this repo → **Settings → Secrets and variables → Actions → Secrets →
   New repository secret**, named `SUPABASE_ACCESS_TOKEN`, with the token as the value.
4. **Run it:** **Actions → Set up community → Run workflow**. It creates the project, sets up
   the database and sign-in links, saves the public settings, and rebuilds the store. That takes
   about 3–5 minutes.
5. **Become admin:** sign up on the store, then run **Set up community** again with your
   username in **admin_username**.

The token can manage your Supabase account, so it's kept as an encrypted GitHub secret and only
this workflow uses it. If you don't use Apple sign-in, you can delete it at supabase.com after
setup; the store keeps working, and you can create a new one if you ever need to re-run setup.

## Sign in with Apple, Google, GitHub and Discord

Each provider needs a small "app" registered on its developer site. You give it the callback
URL below, it gives you an ID and a secret, and you save those as GitHub secrets (**Settings →
Secrets and variables → Actions → Secrets**). Then run **Set up community** again. Each button
appears on the store as soon as its provider is switched on. Set up any you want, in any order.

The same sign-in works in the Accretion app (email, Google, GitHub and Discord). The app returns
to `accretion://auth-callback`, which **Set up community** adds to the allowed redirect URLs
([`scripts/supabase_setup.py`](../scripts/supabase_setup.py)). The providers need nothing extra.

**Callback URL** for every provider:

```
https://bbcjpinhvlxocjxlyplt.supabase.co/auth/v1/callback
```

### Google (free)

1. Open [console.cloud.google.com](https://console.cloud.google.com), then create a project
   named `Accretion`.
2. **APIs & Services → OAuth consent screen:** choose **External**. Use app name `Accretion`,
   your support email, and app domain `getaccretion.github.io`. Add the scopes `email`,
   `profile` and `openid`. Then **Publish app**.
3. **APIs & Services → Credentials → Create credentials → OAuth client ID:** choose **Web
   application**.
   - **Authorized JavaScript origins:** `https://getaccretion.github.io`
   - **Authorized redirect URIs:** the callback URL above
4. Save these as secrets: `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.

### Discord (free)

1. Open [discord.com/developers/applications](https://discord.com/developers/applications)
   and click **New Application**, named `Accretion`.
2. **OAuth2 → Redirects:** add the callback URL above, then save.
3. Copy the **Client ID**, then **Reset Secret** and copy the secret.
4. Save these as secrets: `DISCORD_CLIENT_ID` and `DISCORD_CLIENT_SECRET`.

### GitHub (free)

1. Open [github.com/settings/developers](https://github.com/settings/developers), then
   **OAuth Apps → New OAuth App**.
   - **Homepage URL:** `https://getaccretion.github.io/`
   - **Authorization callback URL:** the callback URL above
2. **Generate a new client secret.**
3. Save these as secrets: `GH_OAUTH_CLIENT_ID` and `GH_OAUTH_CLIENT_SECRET`. GitHub doesn't
   allow secret names starting with `GITHUB_`, hence `GH_`.

### Apple (needs the Apple Developer Program, $99/year)

1. At [developer.apple.com/account](https://developer.apple.com/account), go to **Certificates,
   Identifiers & Profiles**.
2. **Identifiers → + → App IDs:** create one (for example `io.accretion.app`) and tick **Sign in
   with Apple**.
3. **Identifiers → + → Services IDs:** create one (for example `io.accretion.signin`). This is
   the client ID. Open it, tick **Sign in with Apple → Configure**, choose the App ID from step 2,
   and set:
   - **Domains:** `bbcjpinhvlxocjxlyplt.supabase.co`
   - **Return URLs:** the callback URL above
4. **Keys → +:** tick **Sign in with Apple**, configure it with the same App ID, and download the
   `.p8` file. You can only download it once. Note the **Key ID**.
5. Save these as secrets:
   - `APPLE_SERVICES_ID`: the Services ID from step 3
   - `APPLE_TEAM_ID`: your Team ID (shown top right in the developer account)
   - `APPLE_KEY_ID`: the Key ID from step 4
   - `APPLE_PRIVATE_KEY`: the full contents of the `.p8` file, including the BEGIN/END lines

Apple's sign-in key must be renewed at least every 6 months. **Set up community** re-signs it
automatically on the 1st of every month, so there is nothing to remember.

### Shortcut: one secret per provider

Instead of two secrets, you can save one per provider named `GOOGLE`, `GIT` or `DISCORD`. Paste
the client ID and the secret together (on one line or two, in either order), or just the secret:
client IDs are public, so they can live in [`providers.json`](providers.json) instead.

### Turn them on

Run **Actions → Set up community → Run workflow**. Its log lists the providers that are on.

**Keep the access token** if you use Apple: the monthly renewal needs `SUPABASE_ACCESS_TOKEN`.

## Emails (free, up to 500 a day)

Supabase's built-in sender only manages a few emails an hour. A dedicated Gmail account sends
sign-up confirmations, sign-in links and password resets as "Accretion", for free:

1. Create a new Gmail account just for the store (for example `getaccretion@gmail.com`).
2. Turn on **2-Step Verification**: [myaccount.google.com/security](https://myaccount.google.com/security).
3. Create an **app password**: [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords),
   named `Accretion`. Google shows 16 letters in groups of four.
4. Save a repository secret named `SMTP` with the address on the first line and the app password
   on the second, spaces and all.
5. Run **Set up community**. Its log says which address the emails come from.

Another provider works too: save `SMTP_USER`, `SMTP_PASS`, `SMTP_HOST` and `SMTP_PORT` instead.

## Manual setup

Use this instead of the quick setup if you prefer to click through the dashboard yourself.

### 1. Create the project

1. Sign up at supabase.com and click **New project**. Name it `accretion`, pick the region
   closest to your users, and set a database password (keep it private).
2. **Authentication → URL Configuration**
   - **Site URL:** `https://getaccretion.github.io/`
   - **Redirect URLs:** add the same address, and `accretion://auth-callback` for the app.
3. **Authentication → Providers → Email:** leave **Confirm email** on. It stops throwaway
   sign-ups.
4. Optional, against bots: **Authentication → Attack Protection → CAPTCHA** (Cloudflare
   Turnstile is free).

### 2. Create the tables

Open **SQL Editor → New query**, paste all of [`schema.sql`](schema.sql), and click **Run**.
You can run it again later; it only updates what changed.

### 3. Turn it on in the store

In **Project Settings → API**, copy the **Project URL** and the **anon public** key. Both are
meant to be public. **Never use the `service_role` key here.**

In this GitHub repo: **Settings → Secrets and variables → Actions → Variables → New repository
variable**:

| Name | Value |
|---|---|
| `SUPABASE_URL` | the Project URL, like `https://abcd1234.supabase.co` |
| `SUPABASE_ANON_KEY` | the anon public key |

Then run **Actions → Build source → Run workflow**. Sign in, Feed, comments and ratings appear
on the next deploy.

### 4. Make yourself admin

Create your account on the store. Then, in the SQL Editor:

```sql
update public.profiles set role = 'admin' where username = 'your_username';
```

You can now open **Edit profile → Open moderation** (or go to `#/mod`). From there you can hide
posts, ban users, and give trusted people moderator rights. Admins can also give donors the ♥ supporter badge. Mods can hide posts and ban users;
only admins can change roles.

## Private downloads

Accretion's own builds, the Accretion app (`io.github.getaccretion.Accretion`) and Accretion Mods
(from [AccretionMods/mods](https://github.com/AccretionMods/mods)), are kept in the private
`builds` Storage bucket. Third-party apps are never copied there. Three Edge Functions in
[`functions/`](functions) serve the bucket:

| Function | Call | What it does |
|---|---|---|
| `download` | `?app=<bundle id>` with a login (`Authorization: Bearer …`), or `&key=<personal key>`; optional `&version=` | Answers with a 302 to a 5-minute signed link and logs the download. Without a login or key, a browser is sent to the app's store page. The Accretion app is always served at its newest version. |
| `source` | `?name=mods\|app&key=<personal key>` | A personal copy of the Accretion Mods or Accretion app source, with every hosted version's download link pointing at `download` |
| `upload` | `POST` with the `x-upload-key` header | Gives a signed upload link for a new build, then records it in `hosted_builds` |
| `manifest` | `?bundleid=&name=&version=&fetchurl=` | The install manifest for the app's Semi Local installs. `fetchurl` must be an `.ipa` on the device or a private network address. Nothing is stored. |

The Accretion app adds `&av=<its version>` to downloads. A request from a version below
`minimumVersion` in [`site/app-config.json`](../site/app-config.json) gets a 426 asking to update,
except a download of Accretion itself, so every old copy can still update.

People find their source links under **Edit profile → Your download links**, with **Copy** and
**Replace key**. Replacing the key turns the old links off.

**Upload key:** the release workflows and the mods publish script upload new builds with a shared
key. Save it as the GitHub secret `ACCRETION_UPLOAD_KEY` (at least 32 characters) in this repo and
in the repos that release builds; **Set up community** copies it to the functions as `UPLOAD_KEY`.
The [Host builds](../.github/workflows/host-builds.yml) workflow
([`scripts/host_builds.py`](../scripts/host_builds.py)) is a fallback that copies any newer build
from the public sources; new releases upload directly.

## How access is enforced

Every rule lives in the database as row level security in `schema.sql`, so it holds no matter
what code runs in the browser:

- Anyone can read profiles, visible posts, likes, ratings and follows.
- Signed-in users who aren't banned can write their own posts, likes, ratings and follows.
- Nobody can post as someone else, edit someone else's post, or give themselves a role.
- Moderators can hide posts, read and resolve reports, and ban users.
- Notifications are private to their owner; reports are visible only to moderators.
- Posting is limited to 5 a minute and 60 an hour per user, and posts are 1–2000 characters.
- People can delete their own account, which removes their profile and everything they posted.
- Search, view and install counts are anonymous: once per visitor per app per day, at most 300
  a day per visitor, with no account or IP address stored. Per-app totals are public; searches
  that found nothing are visible to moderators only (Moderation → What people look for).
- Hosted builds: anyone can see which versions are hosted (`hosted_builds`), but the files sit
  in a private bucket and are reachable only through 5-minute signed links from `download`.
- Personal download keys (`download_keys`) are visible only to their owner, through the
  `my_download_key(rotate)` function; `rotate` replaces the key and the old one stops working.
- The download log (`download_log`) is readable by admins only.
- Only holders of the upload key can add builds; the functions check it themselves.

`test.sql` checks all of the above on a plain Postgres. CI runs it on every change.
