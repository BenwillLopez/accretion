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

-- Ratings remember when they last changed.
create or replace function public.touch_rating() returns trigger
language plpgsql as $$
begin
  new.updated_at := now();
  return new;
end;
$$;
drop trigger if exists touch_rating on public.app_ratings;
create trigger touch_rating before update on public.app_ratings for each row execute function public.touch_rating();

-- Reports: the reporter is always the signed-in user; mods record who resolved them.
create or replace function public.check_report() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if tg_op = 'INSERT' then
    new.reporter := auth.uid();
    new.status := 'open';
    new.resolved_by := null;
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
  using (id = auth.uid() or public.is_mod()) with check (id = auth.uid() or public.is_mod());

drop policy if exists "visible posts are public" on public.posts;
create policy "visible posts are public" on public.posts for select
  using (not hidden or author = auth.uid() or public.is_mod());
drop policy if exists "write own posts" on public.posts;
create policy "write own posts" on public.posts for insert to authenticated
  with check (public.can_write());
drop policy if exists "edit own posts or moderate" on public.posts;
create policy "edit own posts or moderate" on public.posts for update to authenticated
  using ((author = auth.uid() and public.can_write()) or public.is_mod())
  with check ((author = auth.uid() and public.can_write()) or public.is_mod());
drop policy if exists "delete own posts or moderate" on public.posts;
create policy "delete own posts or moderate" on public.posts for delete to authenticated
  using (author = auth.uid() or public.is_mod());

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
    execute format('create policy "own insert" on public.%I for insert to authenticated with check (%I = auth.uid() and public.can_write())', t, col);
    execute format('drop policy if exists "own update" on public.%I', t);
    execute format('create policy "own update" on public.%I for update to authenticated using (%I = auth.uid() and public.can_write()) with check (%I = auth.uid())', t, col, col);
    execute format('drop policy if exists "own delete" on public.%I', t);
    execute format('create policy "own delete" on public.%I for delete to authenticated using (%I = auth.uid())', t, col);
  end loop;
end;
$$;

drop policy if exists "anyone signed in can report" on public.reports;
create policy "anyone signed in can report" on public.reports for insert to authenticated
  with check (auth.uid() is not null);
drop policy if exists "mods read reports" on public.reports;
create policy "mods read reports" on public.reports for select to authenticated using (public.is_mod());
drop policy if exists "mods resolve reports" on public.reports;
create policy "mods resolve reports" on public.reports for update to authenticated
  using (public.is_mod()) with check (public.is_mod());

drop policy if exists "own notifications" on public.notifications;
create policy "own notifications" on public.notifications for select to authenticated using (user_id = auth.uid());
drop policy if exists "mark own notifications" on public.notifications;
create policy "mark own notifications" on public.notifications for update to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());
drop policy if exists "clear own notifications" on public.notifications;
create policy "clear own notifications" on public.notifications for delete to authenticated using (user_id = auth.uid());

-- ---------------------------------------------------------------- views
-- security_invoker: the views run with the caller's rights, so the policies above apply.

create or replace view public.post_feed with (security_invoker = true) as
select
  p.id, p.author, p.app_id, p.parent_id, p.body, p.hidden, p.created_at, p.edited_at,
  pr.username, pr.display_name, pr.color, pr.role,
  (select count(*) from public.post_likes l where l.post_id = p.id)::int as likes,
  (select count(*) from public.posts r where r.parent_id = p.id and not r.hidden)::int as replies
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
  (select count(*) from public.app_likes a where a.user_id = pr.id)::int as liked_apps
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
  using (public.is_mod());

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
grant update (username, display_name, bio, color, role, banned) on public.profiles to authenticated;
grant insert, update, delete on public.posts, public.post_likes, public.app_likes,
  public.app_ratings, public.follows to authenticated;
grant select, insert, update on public.reports to authenticated;
grant select, update, delete on public.notifications to authenticated;
grant execute on function public.is_mod(), public.is_admin(), public.can_write() to anon, authenticated;
grant select on public.app_hits, public.app_trending to anon, authenticated;
grant select on public.search_misses, public.missing_searches to authenticated;

-- ---------------------------------------------------------------- make yourself admin
-- After you sign up on the site, run this once with your username:
--   update public.profiles set role = 'admin' where username = 'your_username';
-- Give a trusted user moderator rights:
--   update public.profiles set role = 'mod' where username = 'their_username';
