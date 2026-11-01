-- Restrict auxiliary application tables to the trusted backend role.
-- The browser uses the application API and must not access these tables directly.
DO $$
DECLARE
  table_name text;
  tables text[] := ARRAY[
    'observability_events',
    'user_feedback',
    'job_search_cache'
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

ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon, authenticated;
