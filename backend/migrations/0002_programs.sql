-- 0002: Graduate Program Discovery.
-- Every program is imported as 'draft' and can only become 'published' after a
-- named human reviewer approves it (enforced by chk_published_reviewed).
-- field_sources stores per-field provenance (source URL + date verified).

CREATE TABLE universities (
    id      TEXT PRIMARY KEY,
    name    TEXT NOT NULL COLLATE NOCASE UNIQUE,
    country TEXT NOT NULL DEFAULT 'US',
    state   TEXT,
    website TEXT NOT NULL
);

CREATE TABLE programs (
    id                          TEXT PRIMARY KEY,
    university_id               TEXT NOT NULL REFERENCES universities (id) ON DELETE CASCADE,
    degree_name                 TEXT NOT NULL,
    field                       TEXT NOT NULL,
    program_type                TEXT NOT NULL,
    duration_months             INTEGER NOT NULL,
    tuition_intl_usd_per_year   INTEGER,
    living_cost_usd_per_year    INTEGER,
    cost_year                   INTEGER,
    gre_policy                  TEXT NOT NULL,
    min_gpa                     REAL,
    ielts_min                   REAL,
    toefl_min                   INTEGER,
    english_exemption_notes     TEXT,
    intl_admission              TEXT NOT NULL,
    intl_restrictions           TEXT,
    contact_faculty_policy      TEXT NOT NULL,
    ms_assistantships           TEXT NOT NULL,
    ms_assistantship_notes      TEXT,
    application_url             TEXT NOT NULL,
    status                      TEXT NOT NULL DEFAULT 'draft',
    content_hash                TEXT NOT NULL,
    verified_on                 TEXT NOT NULL,
    reviewed_by                 TEXT,
    reviewed_at                 TEXT,
    created_at                  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at                  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    CONSTRAINT uq_program UNIQUE (university_id, degree_name),
    CONSTRAINT chk_field CHECK (field IN ('ai', 'cybersecurity', 'cs', 'data_science', 'other')),
    CONSTRAINT chk_program_type CHECK (program_type IN ('thesis', 'thesis_optional', 'non_thesis', 'research_based')),
    CONSTRAINT chk_duration CHECK (duration_months BETWEEN 6 AND 60),
    CONSTRAINT chk_tuition CHECK (tuition_intl_usd_per_year IS NULL OR tuition_intl_usd_per_year >= 0),
    CONSTRAINT chk_living CHECK (living_cost_usd_per_year IS NULL OR living_cost_usd_per_year >= 0),
    CONSTRAINT chk_gre_policy CHECK (gre_policy IN ('required', 'optional', 'not_considered', 'unknown')),
    CONSTRAINT chk_min_gpa CHECK (min_gpa IS NULL OR min_gpa BETWEEN 0 AND 4),
    CONSTRAINT chk_intl CHECK (intl_admission IN ('open', 'closed', 'unknown')),
    CONSTRAINT chk_contact CHECK (contact_faculty_policy IN ('encouraged', 'allowed', 'discouraged', 'prohibited', 'unknown')),
    CONSTRAINT chk_assistantships CHECK (ms_assistantships IN ('professor_hires', 'department_assigns', 'both', 'none_listed', 'unknown')),
    CONSTRAINT chk_status CHECK (status IN ('draft', 'published')),
    CONSTRAINT chk_published_reviewed CHECK (status <> 'published' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))
);

CREATE INDEX idx_programs_status_field ON programs (status, field);
CREATE INDEX idx_programs_university ON programs (university_id);

CREATE TABLE program_deadlines (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    program_id            TEXT NOT NULL REFERENCES programs (id) ON DELETE CASCADE,
    intake                TEXT NOT NULL,
    deadline_date         TEXT NOT NULL,
    funding_priority_date TEXT,
    CONSTRAINT uq_deadline UNIQUE (program_id, intake),
    CONSTRAINT chk_intake CHECK (intake IN ('fall', 'spring'))
);

CREATE TABLE funding_evidence (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    program_id      TEXT NOT NULL REFERENCES programs (id) ON DELETE CASCADE,
    kind            TEXT NOT NULL,
    master_eligible TEXT NOT NULL,
    intl_eligible   TEXT NOT NULL,
    description     TEXT NOT NULL,
    CONSTRAINT chk_kind CHECK (kind IN ('RA', 'TA', 'GA', 'tuition_waiver', 'scholarship')),
    CONSTRAINT chk_master CHECK (master_eligible IN ('yes', 'no', 'unknown')),
    CONSTRAINT chk_intl_elig CHECK (intl_eligible IN ('yes', 'no', 'unknown'))
);

CREATE INDEX idx_funding_program ON funding_evidence (program_id);

CREATE TABLE field_sources (
    program_id  TEXT NOT NULL REFERENCES programs (id) ON DELETE CASCADE,
    field_key   TEXT NOT NULL,
    url         TEXT NOT NULL,
    verified_on TEXT NOT NULL,
    PRIMARY KEY (program_id, field_key)
);
