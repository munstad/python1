-- ================================================
-- Visa Bot Database Schema
-- ================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ------------------------------------------------
-- Users
-- ------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id              BIGINT PRIMARY KEY,  -- Telegram user ID
    username        VARCHAR(64),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    is_banned       BOOLEAN NOT NULL DEFAULT FALSE
);

-- ------------------------------------------------
-- User personal data (AES-256 encrypted fields)
-- ------------------------------------------------
CREATE TABLE IF NOT EXISTS user_profiles (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- Personal
    full_name_enc   TEXT NOT NULL,         -- encrypted
    birth_date_enc  TEXT NOT NULL,         -- encrypted
    citizenship_enc TEXT NOT NULL,         -- encrypted
    -- Passport
    passport_no_enc TEXT NOT NULL,         -- encrypted
    passport_exp_enc TEXT NOT NULL,        -- encrypted
    passport_country_enc TEXT NOT NULL,    -- encrypted
    -- Contact
    phone_enc       TEXT,                  -- encrypted
    email_enc       TEXT,                  -- encrypted
    --
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id)
);

-- ------------------------------------------------
-- Search tasks
-- ------------------------------------------------
CREATE TYPE task_status AS ENUM (
    'pending',
    'running',
    'paused',
    'slot_found',
    'booking',
    'booked',
    'error',
    'cancelled'
);

CREATE TABLE IF NOT EXISTS search_tasks (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status          task_status NOT NULL DEFAULT 'pending',
    -- Booking params
    visa_center     VARCHAR(128) NOT NULL,
    visa_type       VARCHAR(64) NOT NULL,
    category        VARCHAR(64) NOT NULL DEFAULT 'standard',
    date_from       DATE NOT NULL,
    date_to         DATE NOT NULL,
    applicant_count SMALLINT NOT NULL DEFAULT 1,
    -- Result
    booked_slot     TIMESTAMPTZ,
    booking_ref     VARCHAR(256),
    error_message   TEXT,
    -- Meta
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ
);

CREATE INDEX idx_search_tasks_user_id ON search_tasks(user_id);
CREATE INDEX idx_search_tasks_status  ON search_tasks(status);

-- ------------------------------------------------
-- Event log
-- ------------------------------------------------
CREATE TABLE IF NOT EXISTS task_events (
    id          BIGSERIAL PRIMARY KEY,
    task_id     UUID NOT NULL REFERENCES search_tasks(id) ON DELETE CASCADE,
    event_type  VARCHAR(64) NOT NULL,
    payload     JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_task_events_task_id ON task_events(task_id);

-- ------------------------------------------------
-- Trigger: update updated_at automatically
-- ------------------------------------------------
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_profiles_updated_at
    BEFORE UPDATE ON user_profiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_tasks_updated_at
    BEFORE UPDATE ON search_tasks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
