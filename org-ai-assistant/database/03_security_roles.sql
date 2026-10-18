-- =====================================================================
-- Security layer for the AI assistant.
-- Principle: the LLM NEVER connects with a powerful account. It gets a
-- READ-ONLY role that can only see curated views (no national_id, PAN,
-- bank account, address, phone). Row-level security limits what each
-- end user can see.
-- Change the passwords before using this anywhere real.
-- =====================================================================

-- ---------- Roles ----------
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ai_readonly') THEN
    CREATE ROLE ai_readonly LOGIN PASSWORD 'change_me_ai_readonly'
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ai_audit_writer') THEN
    CREATE ROLE ai_audit_writer LOGIN PASSWORD 'change_me_audit_writer'
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
  END IF;
END $$;

-- Hard limits on the AI role: read-only transactions, short timeouts
ALTER ROLE ai_readonly SET default_transaction_read_only = on;
ALTER ROLE ai_readonly SET statement_timeout = '15s';
ALTER ROLE ai_readonly SET idle_in_transaction_session_timeout = '30s';
ALTER ROLE ai_readonly CONNECTION LIMIT 20;

-- ---------- AI-facing schema of safe views ----------
DROP SCHEMA IF EXISTS ai_views CASCADE;
CREATE SCHEMA ai_views;
COMMENT ON SCHEMA ai_views IS 'Curated, PII-minimised views. The ONLY schema the AI may query.';

CREATE VIEW ai_views.employees WITH (security_barrier = true) AS
SELECT e.employee_id, e.emp_code, e.first_name, e.last_name, e.gender,
       date_part('year', age(e.date_of_birth))::int AS age_years,
       e.date_of_joining, e.date_of_exit, e.employment_status, e.marital_status,
       e.blood_group, e.email,
       d.dept_name AS department, ds.title AS designation, ds.grade,
       u.unit_name AS current_unit, l.city AS current_city, l.region,
       e.reporting_to AS reporting_to_employee_id,
       date_part('year', age(COALESCE(e.date_of_exit, CURRENT_DATE), e.date_of_joining))::int AS years_of_service
FROM core.employees e
JOIN core.departments d  ON d.department_id  = e.department_id
JOIN core.designations ds ON ds.designation_id = e.designation_id
JOIN core.units u        ON u.unit_id        = e.current_unit_id
JOIN core.locations l    ON l.location_id    = u.location_id;
COMMENT ON VIEW ai_views.employees IS 'Employee master (no national id / PAN / bank / phone / address). age_years computed from DOB';

CREATE VIEW ai_views.qualifications AS
SELECT employee_id, degree, specialization, institution, year_passed FROM core.qualifications;

CREATE VIEW ai_views.units AS
SELECT u.unit_id, u.unit_code, u.unit_name, u.unit_type, l.city, l.state, l.region
FROM core.units u JOIN core.locations l USING (location_id);

CREATE VIEW ai_views.postings AS
SELECT p.posting_id, p.employee_id, u.unit_name, l.city, ds.title AS designation,
       p.from_date, p.to_date, (p.to_date IS NULL) AS is_current,
       p.posting_type, p.order_number
FROM hr.postings p
JOIN core.units u ON u.unit_id = p.unit_id
JOIN core.locations l ON l.location_id = u.location_id
JOIN core.designations ds ON ds.designation_id = p.designation_id;
COMMENT ON VIEW ai_views.postings IS 'Posting/transfer history; is_current = true for the present posting';

CREATE VIEW ai_views.leave AS
SELECT la.leave_id, la.employee_id, lt.code AS leave_code, lt.name AS leave_type,
       la.from_date, la.to_date, la.days, la.status, la.applied_on, la.approved_by
FROM hr.leave_applications la JOIN hr.leave_types lt USING (leave_type_id);
COMMENT ON VIEW ai_views.leave IS 'Leave applications (reason text intentionally excluded)';

CREATE VIEW ai_views.appraisals AS
SELECT employee_id, appraisal_year, rating, grade, reviewer_id FROM hr.performance_appraisals;

CREATE VIEW ai_views.training AS
SELECT en.enrollment_id, en.employee_id, c.course_code, c.course_name, c.category,
       c.is_mandatory, s.start_date, s.end_date, u.unit_name AS venue,
       en.status, en.score, en.certificate_no
FROM training.enrollments en
JOIN training.sessions s ON s.session_id = en.session_id
JOIN training.courses c  ON c.course_id  = s.course_id
JOIN core.units u        ON u.unit_id    = s.unit_id;
COMMENT ON VIEW ai_views.training IS 'One row per employee per training session attended/nominated';

CREATE VIEW ai_views.courses AS
SELECT course_id, course_code, course_name, category, duration_days, is_mandatory FROM training.courses;

CREATE VIEW ai_views.payroll AS
SELECT employee_id, pay_month, basic_pay, total_allowances, gross_pay,
       income_tax, provident_fund, other_deductions, net_pay, paid_on
FROM pay.payroll;
COMMENT ON VIEW ai_views.payroll IS 'Monthly salary slips. pay_month = first day of month';

CREATE VIEW ai_views.pay_scales AS
SELECT grade, min_basic, max_basic, annual_increment_pct FROM pay.pay_scales;

-- Disciplinary records are deliberately NOT exposed to the AI.

-- ---------- Grants ----------
REVOKE ALL ON SCHEMA core, hr, training, pay, audit FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA core, hr, training, pay, audit FROM ai_readonly;
GRANT USAGE  ON SCHEMA ai_views TO ai_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA ai_views TO ai_readonly;

-- The application (not the LLM) writes the audit log with a separate account
GRANT USAGE ON SCHEMA audit TO ai_audit_writer;
GRANT INSERT ON audit.ai_query_log TO ai_audit_writer;
GRANT USAGE ON SEQUENCE audit.ai_query_log_log_id_seq TO ai_audit_writer;

-- ---------- Row-level security example ----------
-- The chat application sets these per request, e.g.
--   SET LOCAL app.user_role = 'employee'; SET LOCAL app.employee_id = '42';
-- Roles: 'hr_admin' (sees all), 'manager' (self + direct reports), 'employee' (self only)
-- RLS is applied on the base payroll table; the view runs as its owner, so
-- we use security_invoker views (PostgreSQL 15+) for the sensitive ones.
ALTER VIEW ai_views.payroll   SET (security_invoker = true);
ALTER VIEW ai_views.appraisals SET (security_invoker = true);
ALTER VIEW ai_views.leave     SET (security_invoker = true);
GRANT USAGE ON SCHEMA pay, hr, core TO ai_readonly;
GRANT SELECT ON pay.payroll, hr.performance_appraisals, hr.leave_applications, hr.leave_types TO ai_readonly;
GRANT SELECT (employee_id, reporting_to) ON core.employees TO ai_readonly;

CREATE OR REPLACE FUNCTION core.can_see_employee(target_emp INT) RETURNS BOOLEAN
LANGUAGE sql STABLE AS $$
  WITH ctx AS (
    SELECT current_setting('app.user_role', true) AS r,
           NULLIF(current_setting('app.employee_id', true), '')::int AS me
  )
  SELECT COALESCE(CASE ctx.r
           WHEN 'hr_admin' THEN TRUE
           WHEN 'manager'  THEN target_emp = ctx.me
                                OR EXISTS (SELECT 1 FROM core.employees x
                                           WHERE x.employee_id = target_emp AND x.reporting_to = ctx.me)
           WHEN 'employee' THEN target_emp = ctx.me
         END, FALSE)            -- no / unknown role => see nothing
  FROM ctx
$$;

ALTER TABLE pay.payroll                ENABLE ROW LEVEL SECURITY;
ALTER TABLE hr.performance_appraisals  ENABLE ROW LEVEL SECURITY;
ALTER TABLE hr.leave_applications      ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS ai_payroll_rls ON pay.payroll;
DROP POLICY IF EXISTS ai_appraisal_rls ON hr.performance_appraisals;
DROP POLICY IF EXISTS ai_leave_rls ON hr.leave_applications;
CREATE POLICY ai_payroll_rls   ON pay.payroll               FOR SELECT TO ai_readonly USING (core.can_see_employee(employee_id));
CREATE POLICY ai_appraisal_rls ON hr.performance_appraisals FOR SELECT TO ai_readonly USING (core.can_see_employee(employee_id));
CREATE POLICY ai_leave_rls     ON hr.leave_applications     FOR SELECT TO ai_readonly USING (core.can_see_employee(employee_id));
