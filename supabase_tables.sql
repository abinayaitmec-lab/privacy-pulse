-- Run these SQL statements in your Supabase SQL editor to create the required tables

CREATE TABLE IF NOT EXISTS pending_contributions (
    id SERIAL PRIMARY KEY,
    domain TEXT NOT NULL,
    policy_url TEXT DEFAULT '',
    policy_text TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    contributor_name TEXT DEFAULT 'Anonymous',
    submitted_at TIMESTAMP DEFAULT NOW(),
    status TEXT DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS approved_policies (
    id SERIAL PRIMARY KEY,
    domain TEXT NOT NULL,
    policy_text TEXT NOT NULL,
    policy_url TEXT DEFAULT '',
    approved_at TIMESTAMP DEFAULT NOW(),
    is_community BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_approved_policies_domain ON approved_policies (domain);

-- If table already exists without contributor_name, add it
DO $$ BEGIN
    IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'pending_contributions') THEN
        IF NOT EXISTS (SELECT FROM information_schema.columns WHERE table_name = 'pending_contributions' AND column_name = 'contributor_name') THEN
            ALTER TABLE pending_contributions ADD COLUMN contributor_name TEXT DEFAULT 'Anonymous';
        END IF;
    END IF;
END $$;
