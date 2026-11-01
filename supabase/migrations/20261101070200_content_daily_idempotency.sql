-- Ensure a committed scheduled draft is reused if the worker crashes before
-- marking its AgentRun as successful. Manual content keeps a NULL key.
ALTER TABLE public.content_items
    ADD COLUMN IF NOT EXISTS scheduled_key varchar(160);

CREATE UNIQUE INDEX IF NOT EXISTS ix_content_items_scheduled_key
    ON public.content_items (scheduled_key)
    WHERE scheduled_key IS NOT NULL;
