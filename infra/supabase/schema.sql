-- Supabase PostgreSQL schema for the LinkedIn Personal Brand OS internal MVP
-- Run this in the Supabase SQL editor.

CREATE TABLE IF NOT EXISTS auth_users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    linkedin_url VARCHAR(255),
    display_name VARCHAR(150),
    role VARCHAR(50) NOT NULL DEFAULT 'owner',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_whitelisted BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES auth_users(id) ON DELETE CASCADE,
    token_hash VARCHAR(128) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_profiles (
    id SERIAL PRIMARY KEY,
    display_name VARCHAR(150) NOT NULL DEFAULT 'User',
    professional_title VARCHAR(200),
    industry VARCHAR(200),
    audience VARCHAR(200),
    goals TEXT,
    brand_positioning TEXT,
    tone VARCHAR(200),
    role VARCHAR(50) DEFAULT 'owner',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS voice_memory (
    id SERIAL PRIMARY KEY,
    profile_id INTEGER REFERENCES user_profiles(id) ON DELETE SET NULL,
    tone VARCHAR(200) NOT NULL DEFAULT 'practical',
    sentence_style VARCHAR(200) NOT NULL DEFAULT 'clear',
    vocabulary TEXT,
    preferred_phrases TEXT,
    avoid_phrases TEXT,
    emoji_usage VARCHAR(100),
    humor_style VARCHAR(100),
    technical_depth VARCHAR(100),
    opinion_style VARCHAR(100),
    storytelling_style VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS content_items (
    id SERIAL PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES user_profiles(id),
    title VARCHAR(200) NOT NULL,
    topic VARCHAR(300) NOT NULL,
    pillar VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'IDEA',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS content_versions (
    id SERIAL PRIMARY KEY,
    content_id INTEGER NOT NULL,
    body TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    version_number INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS approval_requests (
    id SERIAL PRIMARY KEY,
    content_version_id INTEGER NOT NULL,
    action_type VARCHAR(50) NOT NULL DEFAULT 'PUBLISH_POST',
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    approval_hash VARCHAR(64),
    reason TEXT,
    edited_body TEXT,
    expires_at TIMESTAMPTZ,
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS feedback_entries (
    id SERIAL PRIMARY KEY,
    content_version_id INTEGER,
    approval_id INTEGER,
    action VARCHAR(50) NOT NULL DEFAULT 'APPROVED',
    reason TEXT,
    payload TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS system_flags (
    id SERIAL PRIMARY KEY,
    emergency_stop BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_approval_requests_status
    ON approval_requests(status);

CREATE INDEX IF NOT EXISTS idx_approval_requests_expires_at
    ON approval_requests(expires_at);

CREATE TABLE IF NOT EXISTS agent_runs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES auth_users(id),
    mode VARCHAR(50) NOT NULL,
    trigger VARCHAR(150) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'RUNNING',
    created_count INTEGER NOT NULL DEFAULT 0,
    details TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_content_items_profile_id
    ON content_items(profile_id);

CREATE INDEX IF NOT EXISTS idx_content_versions_content_id
    ON content_versions(content_id);

CREATE INDEX IF NOT EXISTS idx_agent_runs_user_id
    ON agent_runs(user_id);

CREATE INDEX IF NOT EXISTS idx_voice_memory_profile_id
    ON voice_memory(profile_id);

CREATE INDEX IF NOT EXISTS idx_feedback_entries_approval_id
    ON feedback_entries(approval_id);

CREATE INDEX IF NOT EXISTS idx_audit_logs_event_type
    ON audit_logs(event_type);

-- Initial safety default: execution is off unless explicitly enabled in prod.
INSERT INTO system_flags (emergency_stop)
SELECT FALSE
WHERE NOT EXISTS (SELECT 1 FROM system_flags);
