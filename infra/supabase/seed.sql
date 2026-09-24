-- Seed the scoped whitelist for the internal dashboard.
-- Run this in the Supabase SQL editor after schema.sql.

INSERT INTO auth_users (email, linkedin_url, display_name, role, is_active, is_whitelisted)
VALUES
    (
        'kanishka.utsav@gmail.com',
        'https://www.linkedin.com/in/kanishkautsav/',
        'Kanishka Utsav',
        'owner',
        TRUE,
        TRUE
    ),
    (
        'pranaybeatking@gmail.com',
        'https://www.linkedin.com/in/kumar-pranay-548181309/',
        'Kumar Pranay',
        'owner',
        TRUE,
        TRUE
    )
ON CONFLICT (email) DO UPDATE
SET
    linkedin_url = EXCLUDED.linkedin_url,
    display_name = EXCLUDED.display_name,
    role = EXCLUDED.role,
    is_active = TRUE,
    is_whitelisted = TRUE,
    updated_at = NOW();

-- Keep each profile explicitly bound to its auth user. New users start with an empty Brand DNA.
INSERT INTO user_profiles (id, display_name, professional_title, industry, audience, brand_positioning, tone, role)
SELECT id, 'Kanishka Utsav', 'AI Strategy Lead', 'B2B SaaS', 'product leaders', 'clear, practical, anti-hype', 'direct and grounded', 'owner'
FROM auth_users
WHERE email = 'kanishka.utsav@gmail.com'
  AND NOT EXISTS (SELECT 1 FROM user_profiles WHERE id = auth_users.id);

INSERT INTO user_profiles (id, display_name, professional_title, industry, audience, brand_positioning, tone, role)
SELECT id, COALESCE(display_name, 'User'), NULL, NULL, NULL, NULL, NULL, role
FROM auth_users
WHERE NOT EXISTS (SELECT 1 FROM user_profiles WHERE id = auth_users.id);
