-- Enforce one durable scheduled execution row per profile, mode and local day.
-- Existing historical AgentRun rows remain untouched (NULL keys are permitted).
ALTER TABLE public.agent_runs
    ADD COLUMN IF NOT EXISTS scheduled_key varchar(160);

CREATE UNIQUE INDEX IF NOT EXISTS ix_agent_runs_scheduled_key
    ON public.agent_runs (scheduled_key)
    WHERE scheduled_key IS NOT NULL;
