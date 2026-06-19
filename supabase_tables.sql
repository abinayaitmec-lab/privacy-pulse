-- Run these SQL statements in your Supabase SQL editor to create the required tables

CREATE TABLE pending_contributions (
    id SERIAL PRIMARY KEY,
    domain TEXT NOT NULL,
    policy_url TEXT DEFAULT '',
    policy_text TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    submitted_at TIMESTAMP DEFAULT NOW(),
    status TEXT DEFAULT 'pending'
);

CREATE TABLE approved_policies (
    id SERIAL PRIMARY KEY,
    domain TEXT NOT NULL,
    policy_text TEXT NOT NULL,
    policy_url TEXT DEFAULT '',
    approved_at TIMESTAMP DEFAULT NOW(),
    is_community BOOLEAN DEFAULT TRUE
);

-- Create an index on domain for fast lookups
CREATE INDEX idx_approved_policies_domain ON approved_policies (domain);
