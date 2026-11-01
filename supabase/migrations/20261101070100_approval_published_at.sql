-- Persist the timestamp returned by publication confirmation and reconciliation.
ALTER TABLE public.approval_requests
    ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ;
