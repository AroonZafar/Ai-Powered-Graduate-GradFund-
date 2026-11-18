-- 0001: users and student profiles.
-- Plain SQL constraints only (no SQLite-specific features beyond strftime defaults)
-- so the schema can be ported to PostgreSQL.

CREATE TABLE users (
    id            TEXT PRIMARY KEY,
    email         TEXT NOT NULL COLLATE NOCASE UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE student_profiles (
    user_id             TEXT PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
    full_name           TEXT NOT NULL,
    funding_mode        TEXT NOT NULL,
    gpa                 REAL NOT NULL,
    gpa_scale           REAL NOT NULL,
    undergraduate_field TEXT NOT NULL,
    english_test        TEXT,
    english_score       REAL,
    gre_total           INTEGER,
    annual_budget_usd   INTEGER,
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    CONSTRAINT chk_full_name CHECK (length(full_name) BETWEEN 1 AND 120),
    CONSTRAINT chk_funding_mode CHECK (funding_mode IN ('funded_only', 'open_to_unfunded')),
    CONSTRAINT chk_gpa CHECK (gpa >= 0 AND gpa_scale > 0 AND gpa <= gpa_scale),
    CONSTRAINT chk_field CHECK (length(undergraduate_field) BETWEEN 1 AND 100),
    CONSTRAINT chk_english_test CHECK (english_test IS NULL OR english_test IN ('ielts', 'toefl_ibt', 'duolingo')),
    CONSTRAINT chk_english_pair CHECK ((english_test IS NULL) = (english_score IS NULL)),
    CONSTRAINT chk_gre CHECK (gre_total IS NULL OR gre_total BETWEEN 260 AND 340),
    CONSTRAINT chk_budget CHECK (annual_budget_usd IS NULL OR annual_budget_usd >= 0)
);
