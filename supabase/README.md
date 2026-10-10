# Community setup (Supabase)

Accounts, comments, likes, ratings, follows, the feed, notifications and moderation run on a
free [Supabase](https://supabase.com) project. The store works without it. The community
features turn on once the two settings below are set.

## 1. Create the project

1. Sign up at supabase.com and click **New project**. Name it `accretion`, pick the region
   closest to your users, and set a database password (keep it private).
2. **Authentication → URL Configuration**
   - **Site URL:** `https://benwilllopez.github.io/accretion/`
   - **Redirect URLs:** add the same address.
3. **Authentication → Providers → Email:** leave **Confirm email** on. It stops throwaway
   sign-ups.
4. Optional, against bots: **Authentication → Attack Protection → CAPTCHA** (Cloudflare
   Turnstile is free).

## 2. Create the tables

Open **SQL Editor → New query**, paste all of [`schema.sql`](schema.sql), and click **Run**.
You can run it again later; it only updates what changed.

## 3. Turn it on in the store

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

## 4. Make yourself admin

Create your account on the store. Then, in the SQL Editor:

```sql
update public.profiles set role = 'admin' where username = 'your_username';
```

You can now open **Edit profile → Open moderation** (or go to `#/mod`). From there you can hide
posts, ban users, and give trusted people moderator rights. Mods can hide posts and ban users;
only admins can change roles.

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

`test.sql` checks all of the above on a plain Postgres. CI runs it on every change.
