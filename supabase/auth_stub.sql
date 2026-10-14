-- A small stand-in for Supabase's auth schema so schema.sql and test.sql run on plain
-- Postgres (CI and local checks). Do NOT run this on Supabase: it already has these.
create role anon nologin;
create role authenticated nologin;
create role service_role nologin bypassrls;
-- like Supabase: the server key can read and write every table created later
alter default privileges in schema public grant all on tables to service_role;
alter default privileges in schema public grant all on sequences to service_role;
grant usage on schema public to service_role;
create schema auth;
create table auth.users (id uuid primary key, raw_user_meta_data jsonb default '{}', last_sign_in_at timestamptz);
create function auth.uid() returns uuid language sql stable as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
$$;
grant usage on schema auth to anon, authenticated;
