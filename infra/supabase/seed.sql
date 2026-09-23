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

-- Keep a default profile row aligned with the approved dashboard owners.
INSERT INTO user_profiles (display_name, professional_title, industry, audience, brand_positioning, tone, role)
SELECT 'Kanishka Utsav', 'AI Strategy Lead', 'B2B SaaS', 'product leaders', 'clear, practical, anti-hype', 'direct and grounded', 'owner'
WHERE NOT EXISTS (SELECT 1 FROM user_profiles WHERE display_name = 'Kanishka Utsav');

INSERT INTO user_profiles (display_name, professional_title, industry, audience, brand_positioning, tone, role)
SELECT 'Kumar Pranay', 'Growth Operator', 'Technology', 'founders and operators', 'execution-focused, practical, credible', 'clear and grounded', 'owner'
WHERE NOT EXISTS (SELECT 1 FROM user_profiles WHERE display_name = 'Kumar Pranay');
