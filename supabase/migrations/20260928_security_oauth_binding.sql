-- Security hardening: bind OAuth browser nonce to the server-side transaction.
ALTER TABLE public.linkedin_oauth_states
  ADD COLUMN IF NOT EXISTS browser_nonce_hash VARCHAR(128);

ALTER TABLE public.linkedin_oauth_exchanges
  ADD COLUMN IF NOT EXISTS browser_nonce_hash VARCHAR(128);

-- Existing in-flight transactions predate this field. They are expired/one-time
-- records and must not be reused after this migration.
DELETE FROM public.linkedin_oauth_states
WHERE browser_nonce_hash IS NULL;

DELETE FROM public.linkedin_oauth_exchanges
WHERE browser_nonce_hash IS NULL;

ALTER TABLE public.linkedin_oauth_states
  ALTER COLUMN browser_nonce_hash SET NOT NULL;

ALTER TABLE public.linkedin_oauth_exchanges
  ALTER COLUMN browser_nonce_hash SET NOT NULL;
