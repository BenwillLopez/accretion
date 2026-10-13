-- Checks for supabase/schema.sql. CI runs this on a plain Postgres with a small stand-in
-- for Supabase's auth schema (see supabase/auth_stub.sql). Any failed check stops the run.
\set ON_ERROR_STOP 1
\set QUIET 1
\o /dev/null

-- helpers: act as a user (or anon) for the rest of the transaction
create or replace function pg_temp.as_user(uid text) returns void language plpgsql as $$
begin
  perform set_config('request.jwt.claim.sub', coalesce(uid, ''), true);
  execute format('set local role %I', case when uid is null then 'anon' else 'authenticated' end);
end;
$$;
create or replace function pg_temp.fails(stmt text) returns boolean language plpgsql as $$
begin
  execute stmt;
  return false;
exception when others then
  return true;
end;
$$;

insert into auth.users values
  ('00000000-0000-0000-0000-00000000000a', '{"username":"alice"}'),
  ('00000000-0000-0000-0000-00000000000b', '{"username":"bob"}'),
  ('00000000-0000-0000-0000-00000000000c', '{"username":"carol"}'),
  ('00000000-0000-0000-0000-00000000000d', '{"username":"Alice"}');
-- SQL Editor style changes (as the database owner) must work
update public.profiles set role = 'admin' where username = 'alice';
update public.profiles set role = 'mod' where username = 'carol';
update public.profiles set banned = true where id = '00000000-0000-0000-0000-00000000000d';

do $$ begin
  assert (select role from public.profiles where username = 'alice') = 'admin', 'owner can set admin';
  assert (select username from public.profiles where id = '00000000-0000-0000-0000-00000000000d') = 'user_00000000', 'taken username falls back';
end $$;

-- bob posts; author is forced to bob; replies flatten to one level
begin;
select pg_temp.as_user('00000000-0000-0000-0000-00000000000b');
insert into public.posts (body, app_id, author, created_at) values ('  first!  ', 'com.app', '00000000-0000-0000-0000-00000000000a', '2099-01-01');
insert into public.posts (body, parent_id) values ('reply', (select max(id) from public.posts));
insert into public.posts (body, parent_id) values ('reply to reply', (select max(id) from public.posts));
-- bob cannot promote himself or ban carol
update public.profiles set role = 'admin', bio = 'hi' where username = 'bob';
update public.profiles set banned = true where username = 'carol';
commit;
do $$ begin
  assert (select author from public.posts order by id limit 1) = '00000000-0000-0000-0000-00000000000b', 'author forced';
  assert (select body from public.posts order by id limit 1) = 'first!', 'body trimmed';
  assert (select created_at from public.posts order by id limit 1) < now() + interval '1 minute', 'post date set by the server';
  assert (select count(*) from public.posts where parent_id = (select min(id) from public.posts)) = 2, 'replies flattened';
  assert (select app_id from public.posts order by id desc limit 1) = 'com.app', 'reply inherits app';
  assert (select role from public.profiles where username = 'bob') = 'user', 'no self promotion';
  assert (select bio from public.profiles where username = 'bob') = 'hi', 'own bio editable';
  assert not (select banned from public.profiles where username = 'carol'), 'users cannot ban';
end $$;

-- banned and anonymous users cannot write
begin;
select pg_temp.as_user('00000000-0000-0000-0000-00000000000d');
do $$ begin
  assert pg_temp.fails($q$insert into public.posts (body) values ('spam')$q$), 'banned cannot post';
  assert pg_temp.fails($q$insert into public.app_likes (app_id) values ('com.app')$q$), 'banned cannot like';
end $$;
rollback;
begin;
select pg_temp.as_user(null);
do $$ begin
  assert (select count(*) from public.posts) = 3, 'anon reads posts';
  assert pg_temp.fails($q$insert into public.posts (body) values ('anon')$q$), 'anon cannot post';
  assert pg_temp.fails($q$select public.delete_my_account()$q$), 'anon cannot delete accounts';
end $$;
rollback;

-- likes, follows and notifications; others cannot rewrite bob's post
begin;
select pg_temp.as_user('00000000-0000-0000-0000-00000000000a');
insert into public.post_likes (post_id) values ((select min(id) from public.posts));
insert into public.follows (followee) values ('00000000-0000-0000-0000-00000000000b');
update public.posts set body = 'hacked' where id = (select min(id) from public.posts);
do $$ begin
  assert pg_temp.fails($q$insert into public.follows (followee) values ('00000000-0000-0000-0000-00000000000a')$q$), 'no self follow';
end $$;
commit;
begin;
select pg_temp.as_user('00000000-0000-0000-0000-00000000000b');
update public.posts set body = 'first! (edited)' where id = (select min(id) from public.posts);
do $$ begin
  assert (select count(*) from public.notifications) = 2, 'bob has like + follow notifications';
  assert (select body from public.posts where id = (select min(id) from public.posts)) = 'first! (edited)', 'author edits';
  assert (select edited_at is not null from public.posts where id = (select min(id) from public.posts)), 'edit marked';
end $$;
insert into public.reports (post_id, reason) values ((select min(id) from public.posts), 'test');
do $$ begin
  assert (select count(*) from public.reports) = 0, 'users cannot read reports';
end $$;
commit;
begin;
select pg_temp.as_user('00000000-0000-0000-0000-00000000000c');
do $$ begin
  assert (select count(*) from public.notifications) = 0, 'notifications are private';
end $$;
rollback;

-- moderator: sees and resolves reports, hides posts, cannot change roles
begin;
select pg_temp.as_user('00000000-0000-0000-0000-00000000000c');
update public.posts set hidden = true where id = (select min(id) from public.posts);
update public.reports set status = 'resolved';
update public.profiles set role = 'admin' where username = 'carol';
do $$ begin
  assert (select count(*) from public.reports) = 1, 'mods read reports';
end $$;
commit;
do $$ begin
  assert (select status from public.reports limit 1) = 'resolved', 'report resolved';
  assert (select resolved_by from public.reports limit 1) = '00000000-0000-0000-0000-00000000000c', 'resolver recorded';
  assert (select role from public.profiles where username = 'carol') = 'mod', 'mods cannot promote';
end $$;
begin;
select pg_temp.as_user(null);
do $$ begin
  assert (select count(*) from public.posts) = 2, 'hidden post gone for anon';
end $$;
rollback;
begin;
select pg_temp.as_user('00000000-0000-0000-0000-00000000000b');
do $$ begin
  assert (select count(*) from public.posts) = 3, 'author still sees hidden post';
end $$;
rollback;

-- ratings and stats
begin;
select pg_temp.as_user('00000000-0000-0000-0000-00000000000b');
insert into public.app_ratings (app_id, stars) values ('com.app', 4);
insert into public.app_likes (app_id) values ('com.app');
update public.app_ratings set stars = 5 where app_id = 'com.app';
do $$ begin
  assert pg_temp.fails($q$insert into public.app_ratings (app_id, stars) values ('com.other', 9)$q$), 'stars 1-5';
end $$;
commit;
begin;
select pg_temp.as_user(null);
do $$ begin
  assert (select likes from public.app_stats where app_id = 'com.app') = 1, 'stats likes';
  assert (select avg_rating from public.app_stats where app_id = 'com.app') = 5, 'stats rating';
  assert (select comments from public.app_stats where app_id = 'com.app') = 2, 'stats comments exclude hidden';
  assert (select followers from public.profile_stats where username = 'bob') = 1, 'profile followers';
end $$;
rollback;

-- rate limit and validation
begin;
select pg_temp.as_user('00000000-0000-0000-0000-00000000000b');
insert into public.posts (body) values ('a');
insert into public.posts (body) values ('b');
do $$ begin
  assert pg_temp.fails($q$insert into public.posts (body) values ('c')$q$), 'rate limit after 5 a minute';
  assert pg_temp.fails($q$insert into public.posts (body) values ('   ')$q$), 'empty posts rejected';
end $$;
commit;

-- account deletion removes everything
begin;
select pg_temp.as_user('00000000-0000-0000-0000-00000000000b');
select public.delete_my_account();
commit;
do $$ begin
  assert not exists (select 1 from public.profiles where username = 'bob'), 'profile deleted';
  assert not exists (select 1 from public.posts where author = '00000000-0000-0000-0000-00000000000b'), 'posts deleted';
end $$;

-- sign-ups through Apple/Google/GitHub/Discord: handle and name come from the provider
insert into auth.users values
  ('00000000-0000-0000-0000-0000000000e1', '{"user_name":"octo-cat","full_name":"Octo Cat"}'),
  ('00000000-0000-0000-0000-0000000000e2', '{"full_name":"Apple Person","email":"x@privaterelay.appleid.com"}'),
  ('00000000-0000-0000-0000-0000000000e3', '{"preferred_username":"alice","name":"Not Alice"}');
do $$ begin
  assert (select username from public.profiles where id = '00000000-0000-0000-0000-0000000000e1') = 'octocat', 'provider handle cleaned';
  assert (select display_name from public.profiles where id = '00000000-0000-0000-0000-0000000000e1') = 'Octo Cat', 'provider name';
  assert (select username from public.profiles where id = '00000000-0000-0000-0000-0000000000e2') like 'user\_%', 'no handle: fallback';
  assert (select username from public.profiles where id = '00000000-0000-0000-0000-0000000000e3') like 'user\_%', 'taken handle: fallback';
end $$;

-- people can change their own username, but not to one that is taken or invalid
begin;
select pg_temp.as_user('00000000-0000-0000-0000-0000000000e2');
update public.profiles set username = 'apple_fan' where id = '00000000-0000-0000-0000-0000000000e2';
do $$ begin
  assert pg_temp.fails($q$update public.profiles set username = 'Alice' where id = '00000000-0000-0000-0000-0000000000e2'$q$), 'taken name rejected';
  assert pg_temp.fails($q$update public.profiles set username = 'no spaces!' where id = '00000000-0000-0000-0000-0000000000e2'$q$), 'invalid name rejected';
end $$;
-- and cannot rename someone else
update public.profiles set username = 'hijacked' where id = '00000000-0000-0000-0000-0000000000e1';
commit;
do $$ begin
  assert (select username from public.profiles where id = '00000000-0000-0000-0000-0000000000e2') = 'apple_fan', 'own rename';
  assert (select username from public.profiles where id = '00000000-0000-0000-0000-0000000000e1') = 'octocat', 'no renaming others';
end $$;

-- supporter badge: only admins give it
begin;
select pg_temp.as_user('00000000-0000-0000-0000-0000000000e2');
update public.profiles set supporter = true where id = '00000000-0000-0000-0000-0000000000e2';
commit;
begin;
select pg_temp.as_user('00000000-0000-0000-0000-00000000000c');
update public.profiles set supporter = true where id = '00000000-0000-0000-0000-0000000000e2';
commit;
do $$ begin
  assert not (select supporter from public.profiles where id = '00000000-0000-0000-0000-0000000000e2'), 'users and mods cannot give the badge';
end $$;
begin;
select pg_temp.as_user('00000000-0000-0000-0000-00000000000a');
update public.profiles set supporter = true where username = 'apple_fan';
commit;
do $$ begin
  assert (select supporter from public.profile_stats where username = 'apple_fan'), 'admin gives the badge';
end $$;

-- demand counts: anonymous, once per visitor per item per day, capped, misses private
begin;
select pg_temp.as_user(null);
select public.track('view', 'com.app');
select public.track('view', 'com.app');
select public.track('search', 'com.app');
select public.track('install', 'com.app');
select public.track('miss', null, '  Spotify   PLUS ');
select public.track('miss', null, 'spotify plus');
select public.track('miss', null, '<script>');
select public.track('hack', 'com.app');
do $$ begin
  assert (select views from public.app_trending where app_id = 'com.app') = 1, 'views counted once';
  assert (select score from public.app_trending where app_id = 'com.app') = 6, 'score 3 search + 2 install + 1 view';
  assert pg_temp.fails($q$select * from public.search_misses$q$), 'anon cannot read missing searches';
  assert pg_temp.fails($q$insert into public.app_hits (app_id) values ('x')$q$), 'no direct writes';
  assert pg_temp.fails($q$select * from private.seen$q$), 'private schema hidden';
end $$;
commit;
do $$ begin
  assert (select hits from public.search_misses where query = 'spotify plus') = 1, 'miss normalised and counted once';
  assert (select count(*) from public.search_misses) = 1, 'unsafe search text ignored';
end $$;
begin;
select pg_temp.as_user('00000000-0000-0000-0000-00000000000c');
do $$ begin
  assert (select hits from public.missing_searches where query = 'spotify plus') = 1, 'mods see missing searches';
end $$;
rollback;
begin;
select pg_temp.as_user(null);
select public.track('view', 'cap.' || g) from generate_series(1, 400) g;
do $$ begin
  assert (select count(*) from public.app_hits) <= 300, 'per-visitor daily cap';
end $$;
commit;

-- community stats: moderators only
begin;
select pg_temp.as_user('00000000-0000-0000-0000-00000000000b');
do $$ begin
  assert pg_temp.fails($q$select public.mod_stats()$q$), 'regular users cannot read community stats';
end $$;
rollback;
begin;
select pg_temp.as_user('00000000-0000-0000-0000-00000000000c');
do $$ begin
  assert (public.mod_stats()->>'users')::int >= 1, 'mods read community stats';
end $$;
rollback;

-- install reports: anyone sends, nobody but moderators reads, no impersonation
begin;
select pg_temp.as_user(null);
insert into public.install_reports (app_version, ios, mode, stage, details)
  values ('1.0.26', '26.4', 2, 'sendingPayload', 'Transfer: not finished after 45 s');
do $$ begin
  assert pg_temp.fails($q$select count(*) from public.install_reports$q$), 'anonymous senders cannot read reports';
  assert pg_temp.fails($q$insert into public.install_reports (app_version, ios, mode, stage, details) values ('1', '1', 7, 'x', 'y')$q$), 'mode must be 0-2';
end $$;
commit;
begin;
select pg_temp.as_user('00000000-0000-0000-0000-00000000000b');
insert into public.install_reports (reporter, app_version, ios, mode, stage, details)
  values ('00000000-0000-0000-0000-00000000000c', '1.0.26', '26.4', 1, 'ready', 'iOS never connected');
do $$ begin
  assert (select count(*) from public.install_reports) = 0, 'users cannot read reports';
end $$;
commit;
begin;
select pg_temp.as_user('00000000-0000-0000-0000-00000000000c');
do $$ begin
  assert (select count(*) from public.install_reports) = 2, 'mods read install reports';
  assert (select reporter from public.install_reports where stage = 'ready') = '00000000-0000-0000-0000-00000000000b', 'reporter is always the sender';
  assert (select reporter from public.install_reports where stage = 'sendingPayload') is null, 'anonymous reports have no reporter';
end $$;
rollback;

\echo 'all database checks passed'
