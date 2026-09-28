-- Rollback for 20260928_linkedin_brand_bootstrap.sql
ALTER TABLE public.linkedin_connections
  DROP COLUMN IF EXISTS linkedin_profile_synced_at,
  DROP COLUMN IF EXISTS linkedin_vanity_name,
  DROP COLUMN IF EXISTS linkedin_locale,
  DROP COLUMN IF EXISTS linkedin_picture_url,
  DROP COLUMN IF EXISTS linkedin_headline;

ALTER TABLE public.user_profiles
  DROP COLUMN IF EXISTS brand_bootstrap_completed;
