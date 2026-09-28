-- Security hardening: public Data API is not used by the Suvacya browser.
-- The application server performs authentication and authorization itself.
-- Deny direct anon/authenticated Data API access to all application data while
-- retaining server-side access through the privileged database connection.
DO $$
DECLARE
  table_name text;
  tables text[] := ARRAY[
    'auth_users','auth_sessions','user_profiles','voice_memory','content_items',
    'content_versions','approval_requests','feedback_entries','audit_logs',
    'agent_runs','brand_memory','historical_posts','linkedin_connections',
    'linkedin_oauth_states','linkedin_oauth_exchanges','system_flags',
    'research_sources','content_opportunities','learning_events',
    'learning_memories','durable_jobs'
  ];
BEGIN
  FOREACH table_name IN ARRAY tables LOOP
    IF to_regclass('public.' || table_name) IS NOT NULL THEN
      EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name);
      EXECUTE format('REVOKE ALL ON TABLE public.%I FROM anon, authenticated', table_name);
      EXECUTE format(
        'DROP POLICY IF EXISTS "backend_only_deny_anon_authenticated" ON public.%I',
        table_name
      );
      EXECUTE format(
        'CREATE POLICY "backend_only_deny_anon_authenticated" ON public.%I FOR ALL TO anon, authenticated USING (false) WITH CHECK (false)',
        table_name
      );
    END IF;
  END LOOP;
END $$;

-- Ensure future application tables do not inherit broad Data API privileges.
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon, authenticated;
