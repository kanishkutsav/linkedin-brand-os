-- Security hardening: make public-schema application functions resistant to search_path hijacking.
-- Only user-defined functions in the public schema are changed. Extension/internal
-- functions are excluded by requiring a normal SQL function owned in public.
DO $$
DECLARE
  fn record;
BEGIN
  FOR fn IN
    SELECT p.oid::regprocedure AS signature
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public'
      AND p.prokind = 'f'
      AND p.oid >= 16384
  LOOP
    EXECUTE format('ALTER FUNCTION %s SET search_path = public, pg_temp', fn.signature);
  END LOOP;
END $$;
