-- Align production scheduled automation with the product contract:
-- 09:00 IST = exactly one post candidate per READY profile.
-- 09:15 IST = research refresh only, with no ContentItem generation.
-- Retention and learning remain independent jobs.

select cron.unschedule('brand-os-daily-discovery');
select cron.unschedule('brand-os-calendar-generation');

select cron.schedule(
  'brand-os-daily-post-generation',
  '30 3 * * *',
  $$
    select net.http_post(
      url := (select decrypted_secret from vault.decrypted_secrets where name='brand_os_vercel_url') || '/api/internal/scheduled-jobs/daily_post',
      params := jsonb_build_object('profile_id', up.id::text),
      headers := jsonb_build_object(
        'Content-Type','application/json',
        'X-Brand-OS-Job-Key',(select decrypted_secret from vault.decrypted_secrets where name='brand_os_job_key')
      ),
      body := jsonb_build_object('source','supabase-cron','execution_target','vercel','profile_id',up.id),
      timeout_milliseconds := 300000
    )
    from (
      select distinct user_profiles.id
      from user_profiles
      join brand_memory on brand_memory.profile_id = user_profiles.id
      where brand_memory.status = 'READY'
    ) up;
  $$
);

select cron.schedule(
  'brand-os-daily-research-refresh',
  '45 3 * * *',
  $$
    select net.http_post(
      url := (select decrypted_secret from vault.decrypted_secrets where name='brand_os_vercel_url') || '/api/internal/scheduled-jobs/research',
      params := jsonb_build_object('profile_id', up.id::text),
      headers := jsonb_build_object(
        'Content-Type','application/json',
        'X-Brand-OS-Job-Key',(select decrypted_secret from vault.decrypted_secrets where name='brand_os_job_key')
      ),
      body := jsonb_build_object('source','supabase-cron','execution_target','vercel','profile_id',up.id),
      timeout_milliseconds := 300000
    )
    from (
      select distinct user_profiles.id
      from user_profiles
      join brand_memory on brand_memory.profile_id = user_profiles.id
      where brand_memory.status = 'READY'
    ) up;
  $$
);
