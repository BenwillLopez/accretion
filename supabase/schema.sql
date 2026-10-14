-- Accretion community: accounts, comments, likes, ratings, follows, notifications
-- and moderation. Paste the whole file into Supabase > SQL Editor and run it once.
-- Safe to run again: it replaces functions, triggers, policies and views.
--
-- Security model: every table has row level security. The browser only ever uses
-- the public anon key, so these policies are what decide who can do what.
--   * anyone can read profiles, visible posts, likes, ratings and follows
--   * signed-in users who are not banned can write their own rows
--   * moderators can hide posts, resolve reports and ban users
--   * only admins can change roles

create extension if not exists citext;

-- ---------------------------------------------------------------- tables

create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  username citext unique not null check (username ~ '^[A-Za-z0-9_]{3,20}$'),
  display_name text not null default '' check (char_length(display_name) <= 40),
  bio text not null default '' check (char_length(bio) <= 280),
  color text not null default '8B5CF6' check (color ~ '^[0-9A-Fa-f]{6}$'),
  role text not null default 'user' check (role in ('user', 'mod', 'admin')),
  banned boolean not null default false,
  created_at timestamptz not null default now()
);
-- supporters (donors) get a badge; only admins can give or take it
alter table public.profiles add column if not exists supporter boolean not null default false;

create table if not exists public.posts (
  id bigint generated always as identity primary key,
  author uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  app_id text check (app_id is null or char_length(app_id) between 1 and 200),
  parent_id bigint references public.posts (id) on delete cascade,
  body text not null check (char_length(btrim(body)) between 1 and 2000),
  hidden boolean not null default false,
  created_at timestamptz not null default now(),
  edited_at timestamptz
);
create index if not exists posts_app_idx on public.posts (app_id, created_at desc);
create index if not exists posts_author_idx on public.posts (author, created_at desc);
create index if not exists posts_parent_idx on public.posts (parent_id);
create index if not exists posts_recent_idx on public.posts (created_at desc);

create table if not exists public.post_likes (
  post_id bigint not null references public.posts (id) on delete cascade,
  user_id uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (post_id, user_id)
);

create table if not exists public.app_likes (
  app_id text not null check (char_length(app_id) between 1 and 200),
  user_id uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (app_id, user_id)
);

create table if not exists public.app_ratings (
  app_id text not null check (char_length(app_id) between 1 and 200),
  user_id uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  stars smallint not null check (stars between 1 and 5),
  updated_at timestamptz not null default now(),
  primary key (app_id, user_id)
);

create table if not exists public.follows (
  follower uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  followee uuid not null references public.profiles (id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (follower, followee),
  check (follower <> followee)
);
create index if not exists follows_followee_idx on public.follows (followee);

create table if not exists public.reports (
  id bigint generated always as identity primary key,
  reporter uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  post_id bigint references public.posts (id) on delete cascade,
  profile_id uuid references public.profiles (id) on delete cascade,
  reason text not null check (char_length(btrim(reason)) between 1 and 500),
  status text not null default 'open' check (status in ('open', 'resolved', 'dismissed')),
  resolved_by uuid references public.profiles (id) on delete set null,
  created_at timestamptz not null default now(),
  check ((post_id is not null) <> (profile_id is not null))
);
-- reports filed by the AI moderation job (public.ai_report) have no human reporter
alter table public.reports alter column reporter drop not null;

create table if not exists public.notifications (
  id bigint generated always as identity primary key,
  user_id uuid not null references public.profiles (id) on delete cascade,
  actor uuid references public.profiles (id) on delete cascade,
  kind text not null check (kind in ('like', 'reply', 'follow')),
  post_id bigint references public.posts (id) on delete cascade,
  read boolean not null default false,
  created_at timestamptz not null default now()
);
create index if not exists notifications_user_idx on public.notifications (user_id, created_at desc);

-- ---------------------------------------------------------------- helpers

create or replace function public.is_mod() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (
    select 1 from public.profiles
    where id = auth.uid() and role in ('mod', 'admin') and not banned
  );
$$;

create or replace function public.is_admin() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.profiles where id = auth.uid() and role = 'admin' and not banned);
$$;

-- signed in, has a profile, not banned
create or replace function public.can_write() returns boolean
language sql stable security definer set search_path = public as $$
  select auth.uid() is not null
    and exists (select 1 from public.profiles where id = auth.uid() and not banned);
$$;

-- ---------------------------------------------------------------- triggers

-- Create a profile for every new account. The username is the one chosen at sign-up, or
-- the handle from Apple/Google/GitHub/Discord when it is valid and free, otherwise
-- user_<8 chars> (people can change it later). The display name comes from the provider.
create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  meta jsonb := coalesce(new.raw_user_meta_data, '{}'::jsonb);
  wanted text;
  candidate text;
  final text;
begin
  foreach candidate in array array[
    meta ->> 'username', meta ->> 'user_name', meta ->> 'preferred_username', meta ->> 'nickname'
  ] loop
    candidate := left(regexp_replace(coalesce(candidate, ''), '[^A-Za-z0-9_]', '', 'g'), 20);
    if candidate ~ '^[A-Za-z0-9_]{3,20}$'
       and not exists (select 1 from public.profiles where username = candidate::citext) then
      wanted := candidate;
      exit;
    end if;
  end loop;
  final := wanted;
  if final is null then
    -- user_ + part of the account id, longer if needed until it is free
    for n in 8..15 loop
      final := 'user_' || substr(replace(new.id::text, '-', ''), 1, n);
      exit when not exists (select 1 from public.profiles where username = final::citext);
    end loop;
    if exists (select 1 from public.profiles where username = final::citext) then
      final := 'user_' || substr(md5(random()::text || clock_timestamp()::text), 1, 15);
    end if;
  end if;
  insert into public.profiles (id, username, display_name)
  values (
    new.id,
    final,
    left(coalesce(meta ->> 'display_name', meta ->> 'full_name', meta ->> 'name', ''), 40)
  )
  on conflict (id) do nothing;
  return new;
end;
$$;
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();

-- Users edit their own name, bio and color; only mods change bans, only admins change roles.
-- Not security definer on purpose: current_user is then the caller's role, so changes made
-- from the SQL Editor (as postgres) are allowed, while the website (anon/authenticated) is checked.
create or replace function public.protect_profile() returns trigger
language plpgsql set search_path = public as $$
begin
  if current_user not in ('anon', 'authenticated') then
    return new;
  end if;
  new.id := old.id;
  new.created_at := old.created_at;
  if not public.is_admin() then
    new.role := old.role;
    new.supporter := old.supporter;
  end if;
  if not public.is_mod() or (old.role = 'admin' and not public.is_admin()) then
    new.banned := old.banned;
  end if;
  return new;
end;
$$;
drop trigger if exists protect_profile on public.profiles;
create trigger protect_profile before update on public.profiles
  for each row execute function public.protect_profile();

-- Posts: one level of replies, rate limits, and fields only mods may change.
create or replace function public.check_post() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  parent public.posts;
  recent int;
begin
  if tg_op = 'INSERT' then
    new.author := auth.uid();
    new.hidden := false;
    new.edited_at := null;
    new.created_at := now(); -- never the client's: it drives the rate limits and feed order
    new.body := btrim(new.body);
    if new.parent_id is not null then
      select * into parent from public.posts where id = new.parent_id;
      if parent.id is null or parent.hidden then
        raise exception 'That post is no longer available';
      end if;
      -- replies to replies attach to the top-level post
      new.parent_id := coalesce(parent.parent_id, parent.id);
      new.app_id := parent.app_id;
    end if;
    if not public.is_mod() then
      select count(*) into recent from public.posts
        where author = new.author and created_at > now() - interval '1 minute';
      if recent >= 5 then
        raise exception 'Slow down a little: try again in a minute';
      end if;
      select count(*) into recent from public.posts
        where author = new.author and created_at > now() - interval '1 hour';
      if recent >= 60 then
        raise exception 'Hourly post limit reached: try again later';
      end if;
    end if;
  else
    new.id := old.id;
    new.author := old.author;
    new.app_id := old.app_id;
    new.parent_id := old.parent_id;
    new.created_at := old.created_at;
    if not public.is_mod() then
      new.hidden := old.hidden;
    end if;
    if new.body is distinct from old.body then
      if auth.uid() is distinct from old.author then
        new.body := old.body; -- moderators hide, they do not rewrite
      else
        new.body := btrim(new.body);
        new.edited_at := now();
      end if;
    end if;
  end if;
  return new;
end;
$$;
drop trigger if exists check_post on public.posts;
create trigger check_post before insert or update on public.posts
  for each row execute function public.check_post();

-- Notifications for replies, likes and follows (never for your own actions).
create or replace function public.notify() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  target uuid;
begin
  if tg_table_name = 'posts' then
    if new.parent_id is null then return new; end if;
    select author into target from public.posts where id = new.parent_id;
    if target is not null and target <> new.author then
      insert into public.notifications (user_id, actor, kind, post_id) values (target, new.author, 'reply', new.id);
    end if;
  elsif tg_table_name = 'post_likes' then
    select author into target from public.posts where id = new.post_id;
    if target is not null and target <> new.user_id
       and not exists (select 1 from public.notifications
                       where user_id = target and actor = new.user_id and kind = 'like' and post_id = new.post_id) then
      insert into public.notifications (user_id, actor, kind, post_id) values (target, new.user_id, 'like', new.post_id);
    end if;
  elsif tg_table_name = 'follows' then
    if not exists (select 1 from public.notifications
                   where user_id = new.followee and actor = new.follower and kind = 'follow') then
      insert into public.notifications (user_id, actor, kind) values (new.followee, new.follower, 'follow');
    end if;
  end if;
  return new;
end;
$$;
drop trigger if exists notify_reply on public.posts;
create trigger notify_reply after insert on public.posts for each row execute function public.notify();
drop trigger if exists notify_like on public.post_likes;
create trigger notify_like after insert on public.post_likes for each row execute function public.notify();
drop trigger if exists notify_follow on public.follows;
create trigger notify_follow after insert on public.follows for each row execute function public.notify();

-- Ratings remember when they last changed (set by the server, also on insert).
create or replace function public.touch_rating() returns trigger
language plpgsql set search_path = public as $$
begin
  new.updated_at := now();
  return new;
end;
$$;
drop trigger if exists touch_rating on public.app_ratings;
create trigger touch_rating before insert or update on public.app_ratings for each row execute function public.touch_rating();

-- Likes and follows: the server sets created_at, never the client.
create or replace function public.stamp_created() returns trigger
language plpgsql set search_path = public as $$
begin
  new.created_at := now();
  return new;
end;
$$;
drop trigger if exists stamp_created on public.post_likes;
create trigger stamp_created before insert on public.post_likes for each row execute function public.stamp_created();
drop trigger if exists stamp_created on public.app_likes;
create trigger stamp_created before insert on public.app_likes for each row execute function public.stamp_created();
drop trigger if exists stamp_created on public.follows;
create trigger stamp_created before insert on public.follows for each row execute function public.stamp_created();

-- Reports: the reporter is always the signed-in user; mods record who resolved them.
create or replace function public.check_report() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if tg_op = 'INSERT' and current_setting('accretion.ai_report', true) = 'on' then
    -- only reachable through public.ai_report (server key): no human reporter, labelled reason
    new.reporter := null;
    new.status := 'open';
    new.resolved_by := null;
    new.created_at := now();
    if new.reason not like 'AI: %' then
      raise exception 'AI reports need a reason starting with "AI: "';
    end if;
    return new;
  end if;
  if tg_op = 'INSERT' then
    new.reporter := auth.uid();
    new.status := 'open';
    new.resolved_by := null;
    new.created_at := now();
    if not public.can_write() then
      raise exception 'Your account can''t send reports right now';
    end if;
    -- one open report per thing per person, and at most 20 an hour, so the queue can't be flooded
    if exists (
      select 1 from public.reports r
      where r.reporter = new.reporter and r.status = 'open'
        and r.post_id is not distinct from new.post_id and r.profile_id is not distinct from new.profile_id
    ) then
      raise exception 'You already reported this';
    end if;
    if (select count(*) from public.reports r
        where r.reporter = new.reporter and r.created_at > now() - interval '1 hour') >= 20 then
      raise exception 'Too many reports. Try again later';
    end if;
  else
    new.reporter := old.reporter;
    new.post_id := old.post_id;
    new.profile_id := old.profile_id;
    new.reason := old.reason;
    new.resolved_by := auth.uid();
  end if;
  return new;
end;
$$;
drop trigger if exists check_report on public.reports;
create trigger check_report before insert or update on public.reports
  for each row execute function public.check_report();

-- The AI moderation job (scripts/ai_jobs.py moderate) flags a post for moderators: one open AI
-- report per post. It never hides or deletes anything. Only the server key can call it.
create or replace function public.ai_report(p_post_id bigint, p_label text) returns bigint
language plpgsql security definer set search_path = public as $$
declare
  rid bigint;
begin
  if not exists (select 1 from public.posts where id = p_post_id) then
    return null;
  end if;
  if exists (select 1 from public.reports where post_id = p_post_id and reporter is null and status = 'open') then
    return null;
  end if;
  perform set_config('accretion.ai_report', 'on', true);
  insert into public.reports (post_id, reason)
    values (p_post_id, left('AI: ' || coalesce(nullif(btrim(p_label), ''), 'flagged'), 500))
    returning id into rid;
  perform set_config('accretion.ai_report', 'off', true);
  return rid;
end;
$$;
revoke all on function public.ai_report(bigint, text) from public, anon, authenticated;
grant execute on function public.ai_report(bigint, text) to service_role;

-- Let people delete their own account; their profile, posts, likes and follows go with it.
create or replace function public.delete_my_account() returns void
language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() is null then
    raise exception 'Not signed in';
  end if;
  delete from auth.users where id = auth.uid();
end;
$$;
revoke all on function public.delete_my_account() from public;
grant execute on function public.delete_my_account() to authenticated;

-- ---------------------------------------------------------------- row level security

alter table public.profiles enable row level security;
alter table public.posts enable row level security;
alter table public.post_likes enable row level security;
alter table public.app_likes enable row level security;
alter table public.app_ratings enable row level security;
alter table public.follows enable row level security;
alter table public.reports enable row level security;
alter table public.notifications enable row level security;

drop policy if exists "profiles are public" on public.profiles;
create policy "profiles are public" on public.profiles for select using (true);
drop policy if exists "edit own profile or moderate" on public.profiles;
create policy "edit own profile or moderate" on public.profiles for update
  using (id = (select auth.uid()) or (select public.is_mod()))
  with check (id = (select auth.uid()) or (select public.is_mod()));

drop policy if exists "visible posts are public" on public.posts;
create policy "visible posts are public" on public.posts for select
  using (not hidden or author = (select auth.uid()) or (select public.is_mod()));
drop policy if exists "write own posts" on public.posts;
create policy "write own posts" on public.posts for insert to authenticated
  with check ((select public.can_write()));
drop policy if exists "edit own posts or moderate" on public.posts;
create policy "edit own posts or moderate" on public.posts for update to authenticated
  using ((author = (select auth.uid()) and (select public.can_write())) or (select public.is_mod()))
  with check ((author = (select auth.uid()) and (select public.can_write())) or (select public.is_mod()));
drop policy if exists "delete own posts or moderate" on public.posts;
create policy "delete own posts or moderate" on public.posts for delete to authenticated
  using (author = (select auth.uid()) or (select public.is_mod()));

-- likes, app likes, ratings and follows share the same shape: public reads, own writes
do $$
declare
  t text;
  col text;
begin
  foreach t in array array['post_likes', 'app_likes', 'app_ratings', 'follows'] loop
    col := case when t = 'follows' then 'follower' else 'user_id' end;
    execute format('drop policy if exists "public read" on public.%I', t);
    execute format('create policy "public read" on public.%I for select using (true)', t);
    execute format('drop policy if exists "own insert" on public.%I', t);
    execute format('create policy "own insert" on public.%I for insert to authenticated with check (%I = (select auth.uid()) and (select public.can_write()))', t, col);
    execute format('drop policy if exists "own update" on public.%I', t);
    execute format('create policy "own update" on public.%I for update to authenticated using (%I = (select auth.uid()) and (select public.can_write())) with check (%I = (select auth.uid()))', t, col, col);
    execute format('drop policy if exists "own delete" on public.%I', t);
    execute format('create policy "own delete" on public.%I for delete to authenticated using (%I = (select auth.uid()))', t, col);
  end loop;
end;
$$;

drop policy if exists "anyone signed in can report" on public.reports;
create policy "anyone signed in can report" on public.reports for insert to authenticated
  with check ((select auth.uid()) is not null);
drop policy if exists "mods read reports" on public.reports;
create policy "mods read reports" on public.reports for select to authenticated using ((select public.is_mod()));
drop policy if exists "mods resolve reports" on public.reports;
create policy "mods resolve reports" on public.reports for update to authenticated
  using ((select public.is_mod())) with check ((select public.is_mod()));

drop policy if exists "own notifications" on public.notifications;
create policy "own notifications" on public.notifications for select to authenticated using (user_id = (select auth.uid()));
drop policy if exists "mark own notifications" on public.notifications;
create policy "mark own notifications" on public.notifications for update to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
drop policy if exists "clear own notifications" on public.notifications;
create policy "clear own notifications" on public.notifications for delete to authenticated using (user_id = (select auth.uid()));

-- ---------------------------------------------------------------- views
-- security_invoker: the views run with the caller's rights, so the policies above apply.

create or replace view public.post_feed with (security_invoker = true) as
select
  p.id, p.author, p.app_id, p.parent_id, p.body, p.hidden, p.created_at, p.edited_at,
  pr.username, pr.display_name, pr.color, pr.role,
  (select count(*) from public.post_likes l where l.post_id = p.id)::int as likes,
  (select count(*) from public.posts r where r.parent_id = p.id and not r.hidden)::int as replies,
  pr.supporter
from public.posts p
join public.profiles pr on pr.id = p.author;

create or replace view public.app_stats with (security_invoker = true) as
select
  app_id,
  sum(likes)::int as likes,
  sum(ratings)::int as ratings,
  round(sum(star_sum)::numeric / nullif(sum(ratings), 0), 2) as avg_rating,
  sum(comments)::int as comments
from (
  select app_id, count(*) as likes, 0 as ratings, 0 as star_sum, 0 as comments
    from public.app_likes group by app_id
  union all
  select app_id, 0, count(*), sum(stars), 0 from public.app_ratings group by app_id
  union all
  select app_id, 0, 0, 0, count(*) from public.posts
    where app_id is not null and not hidden group by app_id
) s
group by app_id;

create or replace view public.profile_stats with (security_invoker = true) as
select
  pr.id, pr.username, pr.display_name, pr.bio, pr.color, pr.role, pr.banned, pr.created_at,
  (select count(*) from public.posts p where p.author = pr.id and not p.hidden)::int as posts,
  (select count(*) from public.follows f where f.followee = pr.id)::int as followers,
  (select count(*) from public.follows f where f.follower = pr.id)::int as following,
  (select count(*) from public.app_likes a where a.user_id = pr.id)::int as liked_apps,
  pr.supporter
from public.profiles pr;

-- ---------------------------------------------------------------- demand (anonymous counts)
-- Which apps people search for, open and install, and what they search for that the store
-- doesn't have. No accounts and no IP addresses are stored: a visitor counts once per app per
-- day through a salted daily hash that can't be reversed, and those hashes are deleted after
-- two days. Each visitor can add at most 300 counts a day.

create schema if not exists private;
revoke all on schema private from public;

create table if not exists private.salt (
  id int primary key default 1 check (id = 1),
  value text not null default md5(random()::text || clock_timestamp()::text)
);
insert into private.salt default values on conflict do nothing;

create table if not exists private.seen (
  key text primary key,
  day date not null default current_date
);
create index if not exists seen_day_idx on private.seen (day);

create table if not exists private.visitor_day (
  visitor text primary key,
  day date not null default current_date,
  n int not null default 0
);

create table if not exists public.app_hits (
  app_id text not null check (char_length(app_id) between 1 and 200),
  day date not null default current_date,
  searches int not null default 0,
  views int not null default 0,
  installs int not null default 0,
  primary key (app_id, day)
);

create table if not exists public.search_misses (
  query text not null check (char_length(query) between 2 and 40),
  day date not null default current_date,
  hits int not null default 0,
  primary key (query, day)
);

-- kind: 'search' (opened from search results), 'view' (app page), 'install' (install tapped),
-- 'miss' (a search with no results; p_q is the search text)
create or replace function public.track(p_kind text, p_app text default null, p_q text default null)
returns void
language plpgsql security definer set search_path = public, private as $$
declare
  v_headers json := coalesce(nullif(current_setting('request.headers', true), ''), '{}')::json;
  v_ip text := coalesce(v_headers->>'cf-connecting-ip', v_headers->>'x-real-ip',
                        split_part(v_headers->>'x-forwarded-for', ',', 1), '');
  v_visitor text;
  v_item text;
  v_n int;
begin
  if p_kind is null or p_kind not in ('search', 'view', 'install', 'miss') then return; end if;
  if p_kind = 'miss' then
    v_item := lower(regexp_replace(btrim(coalesce(p_q, '')), '\s+', ' ', 'g'));
    if v_item !~ '^[a-z0-9][a-z0-9 .+&''-]{1,39}$' then return; end if;
  else
    v_item := btrim(coalesce(p_app, ''));
    if char_length(v_item) not between 1 and 200 then return; end if;
  end if;

  v_visitor := md5((select value from private.salt) || current_date::text || btrim(v_ip));
  insert into private.visitor_day as d (visitor) values (v_visitor)
    on conflict (visitor) do update set n = d.n + 1
    returning n into v_n;
  if v_n > 300 then return; end if;

  insert into private.seen (key) values (md5(v_visitor || p_kind || v_item)) on conflict do nothing;
  if not found then return; end if; -- already counted today

  if p_kind = 'miss' then
    insert into public.search_misses as m (query, hits) values (v_item, 1)
      on conflict (query, day) do update set hits = m.hits + 1;
  else
    insert into public.app_hits as a (app_id, searches, views, installs)
      values (v_item, (p_kind = 'search')::int, (p_kind = 'view')::int, (p_kind = 'install')::int)
      on conflict (app_id, day) do update set
        searches = a.searches + excluded.searches,
        views = a.views + excluded.views,
        installs = a.installs + excluded.installs;
  end if;

  if random() < 0.02 then
    delete from private.seen where day < current_date - 1;
    delete from private.visitor_day where day < current_date - 1;
  end if;
end;
$$;
revoke all on function public.track(text, text, text) from public;
grant execute on function public.track(text, text, text) to anon, authenticated;

alter table public.app_hits enable row level security;
alter table public.search_misses enable row level security;
drop policy if exists "app counts are public" on public.app_hits;
create policy "app counts are public" on public.app_hits for select using (true);
drop policy if exists "mods read missing searches" on public.search_misses;
create policy "mods read missing searches" on public.search_misses for select to authenticated
  using ((select public.is_mod()));

-- last 7 days; a search that leads to an app counts most
create or replace view public.app_trending with (security_invoker = true) as
select app_id,
  sum(searches)::int as searches,
  sum(views)::int as views,
  sum(installs)::int as installs,
  (3 * sum(searches) + 2 * sum(installs) + sum(views))::int as score
from public.app_hits
where day > current_date - 7
group by app_id;

-- last 30 days, mods only (through the policy on search_misses)
create or replace view public.missing_searches with (security_invoker = true) as
select query, sum(hits)::int as hits, max(day) as last_day
from public.search_misses
where day > current_date - 30
group by query;

-- ---------------------------------------------------------------- grants
-- Supabase grants these by default; listed so the file also works on plain Postgres.

grant usage on schema public to anon, authenticated;
grant select on public.profiles, public.posts, public.post_likes, public.app_likes,
  public.app_ratings, public.follows, public.post_feed, public.app_stats, public.profile_stats
  to anon, authenticated;
grant update (username, display_name, bio, color, role, banned, supporter) on public.profiles to authenticated;
grant insert, update, delete on public.posts, public.post_likes, public.app_likes,
  public.app_ratings, public.follows to authenticated;
grant select, insert, update on public.reports to authenticated;
grant select, update, delete on public.notifications to authenticated;
grant execute on function public.is_mod(), public.is_admin(), public.can_write() to anon, authenticated;
grant select on public.app_hits, public.app_trending to anon, authenticated;
grant select on public.search_misses, public.missing_searches to authenticated;

-- ---------------------------------------------------------------- certificate backups
-- The Accretion app backs up signing certificates to the user's account. Every payload is
-- sealed on the phone (AES-GCM with a key derived from a passphrase only the user knows), so
-- this table never holds a readable .p12, its password or the passphrase. Only the owner can
-- see or change their rows; nobody else, including moderators, can read them.

create table if not exists public.certificate_backups (
  id uuid primary key default gen_random_uuid(),
  owner uuid not null default auth.uid() references auth.users (id) on delete cascade,
  label text not null default '' check (char_length(label) <= 80),
  expires timestamptz,
  payload text not null check (char_length(payload) <= 2000000),
  salt text not null check (char_length(salt) <= 64),
  rounds int not null default 210000 check (rounds between 100000 and 10000000),
  created_at timestamptz not null default now()
);
create index if not exists certificate_backups_owner on public.certificate_backups (owner);

-- at most 20 backups per account, so one account can't fill the database
create or replace function public.limit_backups() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if (select count(*) from public.certificate_backups where owner = auth.uid()) >= 20 then
    raise exception 'You have 20 backups already. Delete an old one first';
  end if;
  return new;
end;
$$;
drop trigger if exists limit_backups on public.certificate_backups;
create trigger limit_backups before insert on public.certificate_backups
  for each row execute function public.limit_backups();

alter table public.certificate_backups enable row level security;
drop policy if exists "own certificate backups" on public.certificate_backups;
create policy "own certificate backups" on public.certificate_backups for all to authenticated
  using (owner = (select auth.uid())) with check (owner = (select auth.uid()));

revoke all on public.certificate_backups from anon;
grant select, insert, delete on public.certificate_backups to authenticated;

-- ---------------------------------------------------------------- hosted builds
-- Accretion's own builds (Accretion Mods and the Accretion app) live in a private storage bucket.
-- The `download` function hands out 5-minute links to signed-in users, or to anyone using a
-- personal key (for AltStore, SideStore and Feather, which can't sign in). Files and the log are
-- only reachable through the functions, which use the service role.

-- storage only exists on Supabase; the CI test database skips this
do $$
begin
  if to_regclass('storage.buckets') is not null then
    insert into storage.buckets (id, name, public) values ('builds', 'builds', false)
    on conflict (id) do update set public = false;
  end if;
end;
$$;

create table if not exists public.hosted_builds (
  id bigint generated always as identity primary key,
  bundle_id text not null check (bundle_id ~ '^[A-Za-z0-9][A-Za-z0-9.-]*$'),
  version text not null check (char_length(version) <= 40),
  path text not null check (char_length(path) <= 300),
  size bigint,
  created_at timestamptz not null default now()
);
create index if not exists hosted_builds_bundle on public.hosted_builds (bundle_id, created_at desc);
-- Stop deployment on conflicting historical rows rather than deleting a published record.
create unique index if not exists hosted_builds_bundle_version on public.hosted_builds (bundle_id, version);
alter table public.hosted_builds add column if not exists sha256 text check (sha256 ~ '^[0-9a-f]{64}$');

create table if not exists public.download_keys (
  owner uuid primary key references auth.users (id) on delete cascade default auth.uid(),
  -- two random UUIDs (244 random bits) as 64 hex characters; no extension needed
  key text not null unique default replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', ''),
  created_at timestamptz not null default now()
);

create table if not exists public.download_log (
  id bigint generated always as identity primary key,
  owner uuid references auth.users (id) on delete set null,
  bundle_id text not null,
  via text not null check (via in ('login', 'key')),
  at timestamptz not null default now()
);
create index if not exists download_log_owner_at on public.download_log (owner, at desc);

-- Serialize issuance per account. The Edge Function must successfully record the download
-- before returning its signed URL, so parallel requests cannot race the quota or a ban.
create or replace function public.check_download() returns trigger
language plpgsql security definer set search_path = public as $$
declare blocked boolean;
begin
  select banned into blocked from public.profiles where id = new.owner for update;
  if not found or blocked then
    raise exception using errcode = 'PT403', message = 'Account cannot download';
  end if;
  new.at := clock_timestamp();
  if (select count(*) from public.download_log
      where owner = new.owner and at > new.at - interval '10 minutes') >= 30 then
    raise exception using errcode = 'PT429', message = 'Download limit reached';
  end if;
  return new;
end;
$$;
drop trigger if exists check_download on public.download_log;
create trigger check_download before insert on public.download_log
  for each row execute function public.check_download();
revoke execute on function public.check_download() from public, anon, authenticated;

alter table public.hosted_builds enable row level security;
alter table public.download_keys enable row level security;
alter table public.download_log enable row level security;

drop policy if exists "hosted builds are listed" on public.hosted_builds;
create policy "hosted builds are listed" on public.hosted_builds for select using (true);
drop policy if exists "own download key" on public.download_keys;
create policy "own download key" on public.download_keys for select to authenticated using (owner = (select auth.uid()));
drop policy if exists "admins read download log" on public.download_log;
create policy "admins read download log" on public.download_log for select to authenticated using ((select public.is_admin()));

-- The signed-in user's personal key, created on first use. A new key replaces the old one
-- (rotate = true), which turns off every source link that used it.
create or replace function public.my_download_key(rotate boolean default false) returns text
language plpgsql security definer set search_path = public as $$
declare result text;
begin
  if auth.uid() is null then
    raise exception 'Not signed in';
  end if;
  if rotate then
    delete from public.download_keys where owner = auth.uid();
  end if;
  insert into public.download_keys (owner) values (auth.uid()) on conflict (owner) do nothing;
  select key into result from public.download_keys where owner = auth.uid();
  return result;
end;
$$;
revoke all on function public.my_download_key(boolean) from public;
grant execute on function public.my_download_key(boolean) to authenticated;

grant select on public.hosted_builds to anon, authenticated;
grant select on public.download_keys to authenticated;
grant select on public.download_log to authenticated;

-- ---------------------------------------------------------------- what's new (announcements)
-- Accretion's own updates feed: new Accretion versions and Accretion Mods are posted
-- automatically when they're published (the upload function); admins can post news by hand.
-- Anyone can read; signed-in users can like.
create table if not exists public.announcements (
  id bigint generated always as identity primary key,
  kind text not null check (kind in ('release', 'mod', 'fix', 'news')),
  title text not null check (char_length(btrim(title)) between 1 and 120),
  body text not null default '' check (char_length(body) <= 4000),
  app_id text check (app_id is null or char_length(app_id) <= 200),
  version text check (version is null or char_length(version) <= 40),
  link text check (link is null or link ~ '^https://'),
  created_at timestamptz not null default now()
);
create index if not exists announcements_created on public.announcements (created_at desc);

create table if not exists public.announcement_likes (
  announcement_id bigint not null references public.announcements (id) on delete cascade,
  user_id uuid not null default auth.uid() references public.profiles (id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (announcement_id, user_id)
);
drop trigger if exists stamp_created on public.announcement_likes;
create trigger stamp_created before insert on public.announcement_likes for each row execute function public.stamp_created();

alter table public.announcements enable row level security;
alter table public.announcement_likes enable row level security;
drop policy if exists "announcements are public" on public.announcements;
create policy "announcements are public" on public.announcements for select using (true);
drop policy if exists "admins post announcements" on public.announcements;
create policy "admins post announcements" on public.announcements for insert to authenticated with check ((select public.is_admin()));
drop policy if exists "admins remove announcements" on public.announcements;
create policy "admins remove announcements" on public.announcements for delete to authenticated using ((select public.is_admin()));
drop policy if exists "announcement likes are public" on public.announcement_likes;
create policy "announcement likes are public" on public.announcement_likes for select using (true);
drop policy if exists "like announcements" on public.announcement_likes;
create policy "like announcements" on public.announcement_likes for insert to authenticated
  with check (user_id = (select auth.uid()) and (select public.can_write()));
drop policy if exists "unlike announcements" on public.announcement_likes;
create policy "unlike announcements" on public.announcement_likes for delete to authenticated using (user_id = (select auth.uid()));

create or replace view public.announcement_feed with (security_invoker = true) as
select a.*, (select count(*) from public.announcement_likes l where l.announcement_id = a.id)::int as likes
from public.announcements a;

grant select on public.announcements, public.announcement_likes, public.announcement_feed to anon, authenticated;
grant insert, delete on public.announcements to authenticated;
grant insert, delete on public.announcement_likes to authenticated;

-- first posts, only while the feed is empty
insert into public.announcements (kind, title, body, app_id, version, link)
select * from (values
  ('mod', 'Swift Radio+ 4.0.0',
   'Swift Radio, the open-source radio app, with the Accretion mod menu: force dark mode and keep the screen awake.',
   'io.github.accretionmods.swiftradio', '4.0.0', 'https://getaccretion.github.io/#/app/io.github.accretionmods.swiftradio'),
  ('release', 'Accretion 1.0.6',
   E'• Sign your own apps guide in the app
• Install button remembers your installer
• Saved apps show updates first
• Comments: like, reply, delete, report
• Notification bell and community shelves in Discover',
   'io.github.getaccretion.Accretion', '1.0.6', 'https://getaccretion.github.io/#/app/io.github.getaccretion.Accretion')
) as seed (kind, title, body, app_id, version, link)
where not exists (select 1 from public.announcements);

-- ---------------------------------------------------------------- community stats (moderators only)
-- One call for the moderator stats panel (website Status and Moderation pages, app Status
-- screen). Counts only, nothing per person. Refuses anyone who isn't a moderator or admin.
create or replace function public.mod_stats() returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare
  result jsonb;
begin
  if not public.is_mod() then
    raise exception 'Moderators only';
  end if;
  select jsonb_build_object(
    'users', (select count(*) from public.profiles),
    'new_7d', (select count(*) from public.profiles where created_at > now() - interval '7 days'),
    'new_30d', (select count(*) from public.profiles where created_at > now() - interval '30 days'),
    'signed_in_7d', (select count(*) from auth.users where last_sign_in_at > now() - interval '7 days'),
    'active_30d', (select count(distinct who) from (
        select author as who from public.posts where created_at > now() - interval '30 days'
        union all select user_id from public.post_likes where created_at > now() - interval '30 days'
        union all select user_id from public.app_likes where created_at > now() - interval '30 days'
        union all select user_id from public.app_ratings where updated_at > now() - interval '30 days'
        union all select owner from public.download_log where at > now() - interval '30 days'
      ) a where who is not null),
    'banned', (select count(*) from public.profiles where banned),
    'moderators', (select count(*) from public.profiles where role in ('mod', 'admin')),
    'supporters', (select count(*) from public.profiles where supporter),
    'posts', (select count(*) from public.posts where parent_id is null and not hidden),
    'comments', (select count(*) from public.posts where app_id is not null and not hidden),
    'posts_7d', (select count(*) from public.posts where created_at > now() - interval '7 days'),
    'likes', (select count(*) from public.post_likes) + (select count(*) from public.app_likes),
    'ratings', (select count(*) from public.app_ratings),
    'follows', (select count(*) from public.follows),
    'reports_open', (select count(*) from public.reports where status = 'open'),
    'downloads', (select count(*) from public.download_log),
    'downloads_7d', (select count(*) from public.download_log where at > now() - interval '7 days'),
    'downloaders_30d', (select count(distinct owner) from public.download_log where at > now() - interval '30 days'),
    'downloads_by_key_30d', (select count(*) from public.download_log where via = 'key' and at > now() - interval '30 days'),
    'download_keys', (select count(*) from public.download_keys),
    'backups', (select count(*) from public.certificate_backups),
    'backup_accounts', (select count(distinct owner) from public.certificate_backups),
    'whats_new_likes', (select count(*) from public.announcement_likes),
    'views_7d', (select coalesce(sum(views), 0) from public.app_hits where day > current_date - 7),
    'installs_7d', (select coalesce(sum(installs), 0) from public.app_hits where day > current_date - 7),
    'top_downloads_30d', (select coalesce(jsonb_agg(jsonb_build_object('app', bundle_id, 'n', n) order by n desc), '[]'::jsonb)
        from (select bundle_id, count(*) as n from public.download_log where at > now() - interval '30 days'
              group by bundle_id order by n desc limit 5) t),
    'signups_by_day', (select coalesce(jsonb_agg(jsonb_build_object('day', d::date, 'n', coalesce(c.n, 0)) order by d), '[]'::jsonb)
        from generate_series(current_date - 29, current_date, interval '1 day') d
        left join (select created_at::date as day, count(*) as n from public.profiles
                   where created_at > now() - interval '30 days' group by 1) c on c.day = d::date)
  ) into result;
  return result;
end;
$$;
revoke all on function public.mod_stats() from public;
grant execute on function public.mod_stats() to authenticated;

-- ---------------------------------------------------------------- install reports
-- When an install stalls, the app's diagnostic alert offers "Send Report": the install mode, the
-- stage it reached and what the install server saw (the alert's own text). Sent only when the
-- user taps it, with or without an account; nothing else about the device. Moderators read them.
create table if not exists public.install_reports (
  id bigint generated always as identity primary key,
  reporter uuid default auth.uid() references public.profiles (id) on delete set null,
  app_version text not null check (char_length(app_version) between 1 and 20),
  ios text not null check (char_length(ios) between 1 and 20),
  mode smallint not null check (mode between 0 and 2),
  stage text not null check (char_length(stage) between 1 and 40),
  bundle_id text check (char_length(bundle_id) <= 200),
  details text not null check (char_length(details) between 1 and 4000),
  created_at timestamptz not null default now()
);
create index if not exists install_reports_created on public.install_reports (created_at desc);
alter table public.install_reports enable row level security;

-- no impersonation, and a flood guard: at most 30 reports a minute from everyone together
create or replace function public.check_install_report() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  -- Serialize the shared quota and use receipt time after waiting for the lock.
  perform pg_advisory_xact_lock(hashtext('accretion.install_reports'));
  new.reporter := auth.uid();
  new.created_at := clock_timestamp();
  if (select count(*) from public.install_reports where created_at > clock_timestamp() - interval '1 minute') >= 30 then
    raise exception 'Too many reports right now. Try again in a minute.';
  end if;
  return new;
end;
$$;
drop trigger if exists check_install_report on public.install_reports;
create trigger check_install_report before insert on public.install_reports
  for each row execute function public.check_install_report();

drop policy if exists "anyone can send an install report" on public.install_reports;
create policy "anyone can send an install report" on public.install_reports for insert to anon, authenticated
  with check (true);
drop policy if exists "mods read install reports" on public.install_reports;
create policy "mods read install reports" on public.install_reports for select to authenticated
  using ((select public.is_mod()));
grant insert on public.install_reports to anon, authenticated;
grant select on public.install_reports to authenticated;

-- Index referencing columns as well as primary keys: deletes and moderation lookups use these.
create index if not exists announcement_likes_user on public.announcement_likes (user_id);
create index if not exists app_likes_user on public.app_likes (user_id);
create index if not exists app_ratings_user on public.app_ratings (user_id);
create index if not exists install_reports_reporter on public.install_reports (reporter);
create index if not exists notifications_actor on public.notifications (actor);
create index if not exists notifications_post on public.notifications (post_id);
create index if not exists post_likes_user on public.post_likes (user_id);
create index if not exists reports_post on public.reports (post_id);
create index if not exists reports_profile on public.reports (profile_id);
create index if not exists reports_reporter on public.reports (reporter);
create index if not exists reports_resolved_by on public.reports (resolved_by);

-- Supabase may grant roles EXECUTE directly through default privileges. Revoking PUBLIC alone
-- does not remove those grants. Trigger-only functions do not need to be public RPCs.
revoke execute on function public.handle_new_user(), public.check_post(), public.check_report(),
  public.notify(), public.limit_backups(), public.check_install_report(), public.protect_profile(),
  public.touch_rating(), public.stamp_created() from public, anon, authenticated;
revoke execute on function public.mod_stats(), public.my_download_key(boolean),
  public.delete_my_account() from public, anon;

-- ---------------------------------------------------------------- make yourself admin
-- After you sign up on the site, run this once with your username:
--   update public.profiles set role = 'admin' where username = 'your_username';
-- Give a trusted user moderator rights:
--   update public.profiles set role = 'mod' where username = 'their_username';
