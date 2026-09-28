-- Phase: LinkedIn-assisted Brand DNA onboarding
-- Safe additive migration. No existing rows are rewritten.

ALTER TABLE public.linkedin_connections
  ADD COLUMN IF NOT EXISTS linkedin_headline TEXT,
  ADD COLUMN IF NOT EXISTS linkedin_picture_url TEXT,
  ADD COLUMN IF NOT EXISTS linkedin_locale TEXT,
  ADD COLUMN IF NOT EXISTS linkedin_vanity_name TEXT,
  ADD COLUMN IF NOT EXISTS linkedin_profile_synced_at TIMESTAMPTZ;

ALTER TABLE public.user_profiles
  ADD COLUMN IF NOT EXISTS brand_bootstrap_completed BOOLEAN NOT NULL DEFAULT FALSE;
