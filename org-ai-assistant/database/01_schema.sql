-- =====================================================================
-- Org AI Assistant - Dummy HR database schema (PostgreSQL 15+)
-- Domains: personal details, postings, HR, training, pay
-- All data loaded into this schema by 02_seed_dummy_data.sql is FAKE.
-- =====================================================================

DROP SCHEMA IF EXISTS core, hr, training, pay, audit CASCADE;

CREATE SCHEMA core;      -- master data: units, departments, ranks, employees
CREATE SCHEMA hr;        -- postings, leave, appraisals, disciplinary
CREATE SCHEMA training;  -- courses, sessions, enrolments
CREATE SCHEMA pay;       -- pay scales, allowances, monthly payroll
CREATE SCHEMA audit;     -- AI assistant query log

-- ---------------------------------------------------------------------
-- CORE
-- ---------------------------------------------------------------------
CREATE TABLE core.locations (
    location_id   SERIAL PRIMARY KEY,
    city          VARCHAR(80)  NOT NULL,
    state         VARCHAR(80)  NOT NULL,
    region        VARCHAR(20)  NOT NULL CHECK (region IN ('North','South','East','West','Central'))
);

CREATE TABLE core.units (
    unit_id       SERIAL PRIMARY KEY,
    unit_code     VARCHAR(12)  NOT NULL UNIQUE,
    unit_name     VARCHAR(120) NOT NULL,
    location_id   INT NOT NULL REFERENCES core.locations(location_id),
    unit_type     VARCHAR(30)  NOT NULL CHECK (unit_type IN ('Headquarters','Regional Office','Branch','Training Centre','Data Centre'))
);

CREATE TABLE core.departments (
    department_id SERIAL PRIMARY KEY,
    dept_code     VARCHAR(10)  NOT NULL UNIQUE,
    dept_name     VARCHAR(80)  NOT NULL
);

CREATE TABLE core.designations (
    designation_id SERIAL PRIMARY KEY,
    title          VARCHAR(80) NOT NULL UNIQUE,
    grade          VARCHAR(5)  NOT NULL,          -- e.g. G1 (junior) .. G8 (senior)
    hierarchy_lvl  SMALLINT    NOT NULL           -- 1 = most junior
);

CREATE TABLE core.employees (
    employee_id      SERIAL PRIMARY KEY,
    emp_code         VARCHAR(12)  NOT NULL UNIQUE,         -- e.g. EMP000123
    first_name       VARCHAR(50)  NOT NULL,
    last_name        VARCHAR(50)  NOT NULL,
    gender           CHAR(1)      NOT NULL CHECK (gender IN ('M','F','O')),
    date_of_birth    DATE         NOT NULL,
    date_of_joining  DATE         NOT NULL,
    date_of_exit     DATE,
    employment_status VARCHAR(15) NOT NULL DEFAULT 'Active'
                     CHECK (employment_status IN ('Active','Retired','Resigned','Suspended','On Deputation')),
    marital_status   VARCHAR(10)  CHECK (marital_status IN ('Single','Married','Divorced','Widowed')),
    blood_group      VARCHAR(3),
    email            VARCHAR(120) UNIQUE,
    phone            VARCHAR(15),
    -- Sensitive identifiers (dummy values). Hidden from the AI via views.
    national_id      VARCHAR(20),
    pan_number       VARCHAR(10),
    bank_account_no  VARCHAR(20),
    ifsc_code        VARCHAR(11),
    address_line     VARCHAR(200),
    home_location_id INT REFERENCES core.locations(location_id),
    department_id    INT NOT NULL REFERENCES core.departments(department_id),
    designation_id   INT NOT NULL REFERENCES core.designations(designation_id),
    current_unit_id  INT NOT NULL REFERENCES core.units(unit_id),
    reporting_to     INT REFERENCES core.employees(employee_id),
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE core.emergency_contacts (
    contact_id    SERIAL PRIMARY KEY,
    employee_id   INT NOT NULL REFERENCES core.employees(employee_id) ON DELETE CASCADE,
    contact_name  VARCHAR(100) NOT NULL,
    relationship  VARCHAR(30)  NOT NULL,
    phone         VARCHAR(15)  NOT NULL
);

CREATE TABLE core.qualifications (
    qualification_id SERIAL PRIMARY KEY,
    employee_id   INT NOT NULL REFERENCES core.employees(employee_id) ON DELETE CASCADE,
    degree        VARCHAR(60)  NOT NULL,
    specialization VARCHAR(80),
    institution   VARCHAR(120),
    year_passed   SMALLINT
);

-- ---------------------------------------------------------------------
-- HR
-- ---------------------------------------------------------------------
CREATE TABLE hr.postings (
    posting_id     SERIAL PRIMARY KEY,
    employee_id    INT NOT NULL REFERENCES core.employees(employee_id) ON DELETE CASCADE,
    unit_id        INT NOT NULL REFERENCES core.units(unit_id),
    designation_id INT NOT NULL REFERENCES core.designations(designation_id),
    from_date      DATE NOT NULL,
    to_date        DATE,                         -- NULL = current posting
    order_number   VARCHAR(30),
    posting_type   VARCHAR(20) NOT NULL CHECK (posting_type IN ('Initial','Transfer','Promotion','Deputation','Attachment')),
    remarks        VARCHAR(200),
    CHECK (to_date IS NULL OR to_date >= from_date)
);

CREATE TABLE hr.leave_types (
    leave_type_id  SERIAL PRIMARY KEY,
    code           VARCHAR(5)  NOT NULL UNIQUE,
    name           VARCHAR(50) NOT NULL,
    annual_quota   SMALLINT    NOT NULL
);

CREATE TABLE hr.leave_applications (
    leave_id       SERIAL PRIMARY KEY,
    employee_id    INT NOT NULL REFERENCES core.employees(employee_id) ON DELETE CASCADE,
    leave_type_id  INT NOT NULL REFERENCES hr.leave_types(leave_type_id),
    from_date      DATE NOT NULL,
    to_date        DATE NOT NULL,
    days           SMALLINT GENERATED ALWAYS AS ((to_date - from_date) + 1) STORED,
    status         VARCHAR(10) NOT NULL CHECK (status IN ('Pending','Approved','Rejected','Cancelled')),
    reason         VARCHAR(200),
    approved_by    INT REFERENCES core.employees(employee_id),
    applied_on     DATE NOT NULL,
    CHECK (to_date >= from_date)
);

CREATE TABLE hr.performance_appraisals (
    appraisal_id   SERIAL PRIMARY KEY,
    employee_id    INT NOT NULL REFERENCES core.employees(employee_id) ON DELETE CASCADE,
    appraisal_year SMALLINT NOT NULL,
    rating         NUMERIC(3,1) NOT NULL CHECK (rating BETWEEN 1 AND 5),
    grade          VARCHAR(20) NOT NULL,          -- Outstanding / Very Good / Good / Average / Below Average
    reviewer_id    INT REFERENCES core.employees(employee_id),
    comments       VARCHAR(300),
    UNIQUE (employee_id, appraisal_year)
);

CREATE TABLE hr.disciplinary_actions (
    action_id      SERIAL PRIMARY KEY,
    employee_id    INT NOT NULL REFERENCES core.employees(employee_id) ON DELETE CASCADE,
    action_date    DATE NOT NULL,
    action_type    VARCHAR(30) NOT NULL,          -- Warning / Censure / Increment withheld ...
    description    VARCHAR(300),
    status         VARCHAR(15) NOT NULL CHECK (status IN ('Open','Closed','Under Appeal'))
);

-- ---------------------------------------------------------------------
-- TRAINING
-- ---------------------------------------------------------------------
CREATE TABLE training.courses (
    course_id      SERIAL PRIMARY KEY,
    course_code    VARCHAR(12) NOT NULL UNIQUE,
    course_name    VARCHAR(120) NOT NULL,
    category       VARCHAR(40) NOT NULL,          -- Technical / Leadership / Compliance / Cyber Security ...
    duration_days  SMALLINT NOT NULL,
    is_mandatory   BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE training.sessions (
    session_id     SERIAL PRIMARY KEY,
    course_id      INT NOT NULL REFERENCES training.courses(course_id),
    unit_id        INT NOT NULL REFERENCES core.units(unit_id),   -- venue
    start_date     DATE NOT NULL,
    end_date       DATE NOT NULL,
    trainer_name   VARCHAR(100),
    capacity       SMALLINT NOT NULL DEFAULT 30,
    CHECK (end_date >= start_date)
);

CREATE TABLE training.enrollments (
    enrollment_id  SERIAL PRIMARY KEY,
    session_id     INT NOT NULL REFERENCES training.sessions(session_id),
    employee_id    INT NOT NULL REFERENCES core.employees(employee_id) ON DELETE CASCADE,
    status         VARCHAR(12) NOT NULL CHECK (status IN ('Nominated','Attended','Completed','Failed','Absent')),
    score          NUMERIC(5,2) CHECK (score BETWEEN 0 AND 100),
    certificate_no VARCHAR(30),
    UNIQUE (session_id, employee_id)
);

-- ---------------------------------------------------------------------
-- PAY
-- ---------------------------------------------------------------------
CREATE TABLE pay.pay_scales (
    pay_scale_id   SERIAL PRIMARY KEY,
    grade          VARCHAR(5)  NOT NULL UNIQUE,   -- matches core.designations.grade
    min_basic      NUMERIC(10,2) NOT NULL,
    max_basic      NUMERIC(10,2) NOT NULL,
    annual_increment_pct NUMERIC(4,2) NOT NULL DEFAULT 3.00
);

CREATE TABLE pay.employee_pay (
    employee_id    INT PRIMARY KEY REFERENCES core.employees(employee_id) ON DELETE CASCADE,
    basic_pay      NUMERIC(10,2) NOT NULL,
    effective_from DATE NOT NULL
);

CREATE TABLE pay.allowance_types (
    allowance_type_id SERIAL PRIMARY KEY,
    code           VARCHAR(6)  NOT NULL UNIQUE,   -- DA, HRA, TA ...
    name           VARCHAR(60) NOT NULL,
    pct_of_basic   NUMERIC(5,2),                  -- NULL => fixed amount
    fixed_amount   NUMERIC(10,2)
);

CREATE TABLE pay.payroll (
    payroll_id     SERIAL PRIMARY KEY,
    employee_id    INT NOT NULL REFERENCES core.employees(employee_id) ON DELETE CASCADE,
    pay_month      DATE NOT NULL,                 -- first day of month
    basic_pay      NUMERIC(10,2) NOT NULL,
    total_allowances NUMERIC(10,2) NOT NULL,
    gross_pay      NUMERIC(10,2) NOT NULL,
    income_tax     NUMERIC(10,2) NOT NULL,
    provident_fund NUMERIC(10,2) NOT NULL,
    other_deductions NUMERIC(10,2) NOT NULL DEFAULT 0,
    net_pay        NUMERIC(10,2) NOT NULL,
    paid_on        DATE,
    UNIQUE (employee_id, pay_month)
);

CREATE TABLE pay.payroll_allowances (
    payroll_id        INT NOT NULL REFERENCES pay.payroll(payroll_id) ON DELETE CASCADE,
    allowance_type_id INT NOT NULL REFERENCES pay.allowance_types(allowance_type_id),
    amount            NUMERIC(10,2) NOT NULL,
    PRIMARY KEY (payroll_id, allowance_type_id)
);

-- ---------------------------------------------------------------------
-- AUDIT: every question the AI answers is logged here
-- ---------------------------------------------------------------------
CREATE TABLE audit.ai_query_log (
    log_id         BIGSERIAL PRIMARY KEY,
    asked_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    app_username   VARCHAR(60) NOT NULL,
    app_role       VARCHAR(30) NOT NULL,
    question       TEXT NOT NULL,
    generated_sql  TEXT,
    rows_returned  INT,
    was_blocked    BOOLEAN NOT NULL DEFAULT FALSE,
    block_reason   TEXT,
    client_ip      INET
);

-- ---------------------------------------------------------------------
-- Indexes for common lookups
-- ---------------------------------------------------------------------
CREATE INDEX ON core.employees (department_id);
CREATE INDEX ON core.employees (current_unit_id);
CREATE INDEX ON core.employees (designation_id);
CREATE INDEX ON core.employees (last_name, first_name);
CREATE INDEX ON core.employees (reporting_to);
CREATE INDEX ON hr.postings (employee_id, from_date);
CREATE INDEX ON hr.leave_applications (employee_id, from_date);
CREATE INDEX ON training.enrollments (employee_id);
CREATE INDEX ON pay.payroll (pay_month);

-- ---------------------------------------------------------------------
-- Comments: the AI reads these to understand the schema (very important
-- for text-to-SQL accuracy - write good comments on your real DB too).
-- ---------------------------------------------------------------------
COMMENT ON SCHEMA core     IS 'Master data: locations, units (offices), departments, designations and employees';
COMMENT ON SCHEMA hr       IS 'Postings/transfers history, leave, yearly performance appraisals, disciplinary actions';
COMMENT ON SCHEMA training IS 'Training courses, scheduled sessions and employee enrolments/results';
COMMENT ON SCHEMA pay      IS 'Pay scales by grade, current basic pay, monthly payroll with allowances and deductions';
COMMENT ON TABLE core.employees  IS 'One row per employee. current_unit_id = where the employee is posted now';
COMMENT ON TABLE hr.postings     IS 'Posting history. to_date IS NULL means the current posting';
COMMENT ON TABLE pay.payroll     IS 'Monthly salary slip per employee. pay_month is the first day of the month';
COMMENT ON COLUMN core.employees.employment_status IS 'Active, Retired, Resigned, Suspended, On Deputation';
COMMENT ON COLUMN hr.leave_applications.days IS 'Number of calendar days of leave (inclusive)';
COMMENT ON COLUMN training.enrollments.status IS 'Nominated, Attended, Completed, Failed, Absent';
