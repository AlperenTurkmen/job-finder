-- Companies table
CREATE TABLE companies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    domain VARCHAR(255),
    careers_url VARCHAR(500),
    location VARCHAR(255),
    industry VARCHAR(255),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Jobs table
CREATE TABLE jobs (
    id SERIAL PRIMARY KEY,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    location VARCHAR(255),
    department VARCHAR(255),
    business_unit VARCHAR(255),
    work_type VARCHAR(50),
    job_url VARCHAR(1000) UNIQUE NOT NULL,
    job_id VARCHAR(100),
    description TEXT,
    responsibilities TEXT[],
    qualifications TEXT[],
    tech_stack TEXT[],
    job_type VARCHAR(50),
    salary_range VARCHAR(100),
    status VARCHAR(50) DEFAULT 'new',
    for_me_score INTEGER,
    for_them_score INTEGER,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    applied_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX idx_jobs_company_id ON jobs(company_id);
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_location ON jobs(location);
CREATE INDEX idx_jobs_for_me_score ON jobs(for_me_score);
CREATE INDEX idx_companies_name ON companies(name);