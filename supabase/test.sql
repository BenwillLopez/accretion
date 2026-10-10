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
insert into public.posts (body, app_id, author) values ('  first!  ', 'com.app', '00000000-0000-0000-0000-00000000000a');
insert into public.posts (body, parent_id) values ('reply', (select max(id) from public.posts));
insert into public.posts (body, parent_id) values ('reply to reply', (select max(id) from public.posts));
-- bob cannot promote himself or ban carol
update public.profiles set role = 'admin', bio = 'hi' where username = 'bob';
update public.profiles set banned = true where username = 'carol';
commit;
do $$ begin
  assert (select author from public.posts order by id limit 1) = '00000000-0000-0000-0000-00000000000b', 'author forced';
  assert (select body from public.posts order by id limit 1) = 'first!', 'body trimmed';
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

\echo 'all database checks passed'
