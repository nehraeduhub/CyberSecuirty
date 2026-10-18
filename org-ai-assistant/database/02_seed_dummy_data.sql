-- =====================================================================
-- Dummy data generator. ALL names, IDs, phone numbers and bank details
-- below are randomly generated and FAKE.
-- Number of employees: default 500. For a full-size test (3 lakh):
--   psql -v emp_count=300000 -d org_hr -f 02_seed_dummy_data.sql
-- setseed() keeps most of the data the same on every run (row counts can vary slightly).
-- =====================================================================
\if :{?emp_count}
\else
  \set emp_count 500
\endif

BEGIN;
SELECT setseed(0.42);

-- ---------------- Locations ----------------
INSERT INTO core.locations (city, state, region) VALUES
 ('New Delhi','Delhi','North'), ('Chandigarh','Chandigarh','North'), ('Jaipur','Rajasthan','North'),
 ('Lucknow','Uttar Pradesh','North'), ('Mumbai','Maharashtra','West'), ('Pune','Maharashtra','West'),
 ('Ahmedabad','Gujarat','West'), ('Bengaluru','Karnataka','South'), ('Chennai','Tamil Nadu','South'),
 ('Hyderabad','Telangana','South'), ('Kolkata','West Bengal','East'), ('Bhubaneswar','Odisha','East'),
 ('Guwahati','Assam','East'), ('Bhopal','Madhya Pradesh','Central'), ('Nagpur','Maharashtra','Central');

-- ---------------- Units (offices) ----------------
INSERT INTO core.units (unit_code, unit_name, location_id, unit_type) VALUES
 ('HQ-DEL','Corporate Headquarters',1,'Headquarters'),
 ('RO-N','Regional Office North',2,'Regional Office'),
 ('RO-W','Regional Office West',5,'Regional Office'),
 ('RO-S','Regional Office South',8,'Regional Office'),
 ('RO-E','Regional Office East',11,'Regional Office'),
 ('RO-C','Regional Office Central',14,'Regional Office'),
 ('BR-JAI','Jaipur Branch',3,'Branch'), ('BR-LKO','Lucknow Branch',4,'Branch'),
 ('BR-PUN','Pune Branch',6,'Branch'), ('BR-AMD','Ahmedabad Branch',7,'Branch'),
 ('BR-CHE','Chennai Branch',9,'Branch'), ('BR-HYD','Hyderabad Branch',10,'Branch'),
 ('BR-BBS','Bhubaneswar Branch',12,'Branch'), ('BR-GAU','Guwahati Branch',13,'Branch'),
 ('TC-NGP','Central Training Centre',15,'Training Centre'),
 ('DC-BLR','Primary Data Centre',8,'Data Centre');

-- ---------------- Departments ----------------
INSERT INTO core.departments (dept_code, dept_name) VALUES
 ('ADM','Administration'), ('HR','Human Resources'), ('FIN','Finance & Accounts'),
 ('IT','Information Technology'), ('CYB','Cyber Security'), ('OPS','Operations'),
 ('TRG','Training'), ('LGL','Legal'), ('PRC','Procurement'), ('AUD','Internal Audit');

-- ---------------- Designations ----------------
INSERT INTO core.designations (title, grade, hierarchy_lvl) VALUES
 ('Assistant','G1',1), ('Senior Assistant','G2',2), ('Officer','G3',3),
 ('Senior Officer','G4',4), ('Manager','G5',5), ('Senior Manager','G6',6),
 ('Deputy General Manager','G7',7), ('General Manager','G8',8);

-- ---------------- Pay scales ----------------
INSERT INTO pay.pay_scales (grade, min_basic, max_basic, annual_increment_pct) VALUES
 ('G1', 18000, 35000, 3), ('G2', 25000, 45000, 3), ('G3', 35000, 60000, 3),
 ('G4', 45000, 80000, 3), ('G5', 60000, 100000, 3), ('G6', 78000, 130000, 3),
 ('G7', 100000, 170000, 3), ('G8', 130000, 220000, 3);

INSERT INTO pay.allowance_types (code, name, pct_of_basic, fixed_amount) VALUES
 ('DA','Dearness Allowance',50.00,NULL), ('HRA','House Rent Allowance',24.00,NULL),
 ('TA','Transport Allowance',NULL,3600), ('MED','Medical Allowance',NULL,1250),
 ('SPL','Special Duty Allowance',NULL,2500);

-- ---------------- Leave types ----------------
INSERT INTO hr.leave_types (code, name, annual_quota) VALUES
 ('CL','Casual Leave',8), ('EL','Earned Leave',30), ('ML','Medical Leave',20),
 ('MAT','Maternity Leave',180), ('PAT','Paternity Leave',15), ('SPL','Special Leave',10);

-- ---------------- Training courses ----------------
INSERT INTO training.courses (course_code, course_name, category, duration_days, is_mandatory) VALUES
 ('CS-101','Cyber Security Awareness','Cyber Security',2,TRUE),
 ('CS-201','Incident Response Fundamentals','Cyber Security',5,FALSE),
 ('CS-301','Ethical Hacking & Penetration Testing','Cyber Security',10,FALSE),
 ('IT-110','Linux System Administration','Technical',5,FALSE),
 ('IT-120','Database Administration with PostgreSQL','Technical',5,FALSE),
 ('IT-210','Network Fundamentals','Technical',4,FALSE),
 ('LD-100','First-Line Supervisor Programme','Leadership',3,FALSE),
 ('LD-200','Strategic Leadership','Leadership',5,FALSE),
 ('CO-100','Code of Conduct & Ethics','Compliance',1,TRUE),
 ('CO-110','Prevention of Sexual Harassment (POSH)','Compliance',1,TRUE),
 ('FN-100','Government Financial Rules','Finance',3,FALSE),
 ('HR-100','Service Rules & Procedures','HR',3,FALSE);

-- ---------------- Employees ----------------
-- Helper arrays of fake names
CREATE TEMP TABLE _names AS SELECT
 ARRAY['Aarav','Vivaan','Aditya','Arjun','Rohan','Karan','Rahul','Vikram','Sandeep','Amit',
       'Manish','Rajesh','Suresh','Deepak','Nikhil','Harish','Pradeep','Gaurav','Ankit','Yash',
       'Imran','Faizan','Harpreet','Gurdeep','Joseph','Thomas','Ravi','Kiran','Naveen','Sunil'] AS m_first,
 ARRAY['Priya','Ananya','Neha','Pooja','Kavya','Sneha','Divya','Meera','Ritu','Sunita',
       'Anjali','Swati','Shalini','Nisha','Rekha','Asha','Lakshmi','Fatima','Simran','Mary',
       'Aisha','Jaspreet','Shreya','Isha','Tanvi','Komal','Payal','Rashmi','Geeta','Bhavna'] AS f_first,
 ARRAY['Sharma','Verma','Gupta','Singh','Kumar','Yadav','Nehra','Chauhan','Mehta','Patel',
       'Shah','Reddy','Rao','Iyer','Nair','Menon','Das','Banerjee','Mukherjee','Ghosh',
       'Khan','Ansari','Gill','Sandhu','Dsouza','Fernandes','Joshi','Kulkarni','Mishra','Pandey'] AS last;

-- Designation distribution: pyramid (many juniors, few seniors)
INSERT INTO core.employees (
    emp_code, first_name, last_name, gender, date_of_birth, date_of_joining,
    employment_status, marital_status, blood_group, email, phone,
    national_id, pan_number, bank_account_no, ifsc_code, address_line,
    home_location_id, department_id, designation_id, current_unit_id)
SELECT
    'EMP' || lpad(g::text, 6, '0'),
    fn, ln, gen,
    dob,
    doj,
    CASE WHEN r_status < 0.90 THEN 'Active'
         WHEN r_status < 0.94 THEN 'On Deputation'
         WHEN r_status < 0.97 THEN 'Resigned'
         WHEN r_status < 0.99 THEN 'Retired'
         ELSE 'Suspended' END,
    (ARRAY['Single','Married','Married','Married','Divorced','Widowed'])[1 + floor(random()*6)::int],
    (ARRAY['A+','A-','B+','B-','O+','O-','AB+','AB-'])[1 + floor(random()*8)::int],
    lower(fn) || '.' || lower(ln) || g || '@example-org.local',
    '9' || lpad((floor(random()*999999999))::bigint::text, 9, '0'),
    'XXXX-XXXX-' || lpad((floor(random()*9999))::int::text, 4, '0'),          -- fake national id
    'ABCDE' || lpad((floor(random()*9999))::int::text, 4, '0') || 'Z',          -- fake PAN
    lpad((floor(random()*1e12))::bigint::text, 12, '0'),                        -- fake account
    'DUMY0' || lpad((floor(random()*999999))::int::text, 6, '0'),               -- fake IFSC
    (floor(random()*500)+1)::int || ', Sector ' || (floor(random()*60)+1)::int || ', Dummy Nagar',
    1 + floor(random()*15)::int,
    1 + floor(random()*10)::int,
    CASE WHEN r_desig < 0.25 THEN 1 WHEN r_desig < 0.45 THEN 2 WHEN r_desig < 0.62 THEN 3
         WHEN r_desig < 0.76 THEN 4 WHEN r_desig < 0.87 THEN 5 WHEN r_desig < 0.94 THEN 6
         WHEN r_desig < 0.98 THEN 7 ELSE 8 END,
    1 + floor(random()*16)::int
FROM (
    SELECT g,
           CASE WHEN random() < 0.62 THEN 'M' WHEN random() < 0.99 THEN 'F' ELSE 'O' END AS gen,
           random() AS r_status, random() AS r_desig,
           (DATE '1966-01-01' + (floor(random()*(365*36)))::int) AS dob
    FROM generate_series(1, :emp_count) g
) base
CROSS JOIN _names
CROSS JOIN LATERAL (
    SELECT CASE WHEN gen = 'F' THEN f_first[1 + floor(random()*30)::int]
                ELSE m_first[1 + floor(random()*30)::int] END AS fn,
           last[1 + floor(random()*30)::int] AS ln,
           -- joined between age 21 and 35, but not in the future
           LEAST(dob + ((21*365) + floor(random()*(14*365)))::int, CURRENT_DATE - 30) AS doj
) x;

-- Exit dates for people who left
UPDATE core.employees
SET date_of_exit = LEAST(CURRENT_DATE - 1, date_of_joining + (floor(random()*(CURRENT_DATE - date_of_joining)))::int + 1)
WHERE employment_status IN ('Resigned','Retired');

ANALYZE core.employees;     -- fresh statistics so the next steps get good plans

-- Reporting manager: a random active employee from the nearest more senior
-- level in the same department. Managers are numbered within each
-- (department, level) group so each pick is a cheap lookup, even for lakhs.
WITH mgr AS (
    SELECT e.department_id, d.hierarchy_lvl AS lvl, e.employee_id,
           row_number() OVER (PARTITION BY e.department_id, d.hierarchy_lvl ORDER BY e.employee_id) AS rn
    FROM core.employees e JOIN core.designations d USING (designation_id)
    WHERE e.employment_status = 'Active'
), grp AS MATERIALIZED (       -- ~80 rows; built once, not per employee
    SELECT department_id, lvl, count(*) AS n FROM mgr GROUP BY 1, 2
), choice AS (
    SELECT e.employee_id, g.department_id, g.lvl, 1 + floor(random() * g.n)::int AS rn
    FROM core.employees e
    JOIN core.designations d USING (designation_id)
    CROSS JOIN LATERAL (
        SELECT * FROM grp
        WHERE grp.department_id = e.department_id AND grp.lvl > d.hierarchy_lvl
        ORDER BY grp.lvl LIMIT 1
    ) g
)
UPDATE core.employees e
SET reporting_to = m.employee_id
FROM choice c JOIN mgr m USING (department_id, lvl, rn)
WHERE e.employee_id = c.employee_id;

-- Emergency contacts (1 per employee)
INSERT INTO core.emergency_contacts (employee_id, contact_name, relationship, phone)
SELECT employee_id,
       'Contact of ' || first_name,
       (ARRAY['Spouse','Father','Mother','Brother','Sister'])[1 + floor(random()*5)::int],
       '8' || lpad((floor(random()*999999999))::bigint::text, 9, '0')
FROM core.employees;

-- Qualifications (1-2 per employee)
INSERT INTO core.qualifications (employee_id, degree, specialization, institution, year_passed)
SELECT e.employee_id,
       (ARRAY['B.A.','B.Com','B.Sc','B.Tech','BCA','MBA','M.Tech','MCA','M.Sc','LLB'])[1 + floor(random()*10)::int],
       (ARRAY['Computer Science','Commerce','Physics','Mathematics','Electronics','Finance','HR','Law','Information Security','Economics'])[1 + floor(random()*10)::int],
       (ARRAY['University of Delhi','Mumbai University','Anna University','Osmania University','Panjab University','IGNOU','Dummy Institute of Technology'])[1 + floor(random()*7)::int],
       EXTRACT(YEAR FROM e.date_of_birth)::int + 21 + n
FROM core.employees e
CROSS JOIN generate_series(0, 1) n
WHERE n = 0 OR random() < 0.4;

-- ---------------- Posting history ----------------
-- 1 to 4 postings per employee, ending in the current unit.
WITH plan AS (
    SELECT e.employee_id, e.current_unit_id, e.designation_id, e.date_of_joining,
           COALESCE(e.date_of_exit, CURRENT_DATE) AS end_dt,
           -- 1-4 postings, but at most one per ~6 months of service
           LEAST(1 + floor(random()*4)::int,
                 GREATEST(1, (COALESCE(e.date_of_exit, CURRENT_DATE) - e.date_of_joining) / 180)) AS n_post
    FROM core.employees e
), slots AS (
    SELECT p.*, s AS seq,
           p.date_of_joining + ((p.end_dt - p.date_of_joining) * (s - 1) / p.n_post) AS from_dt,
           CASE WHEN s = p.n_post THEN NULL
                ELSE p.date_of_joining + ((p.end_dt - p.date_of_joining) * s / p.n_post) - 1 END AS to_dt
    FROM plan p CROSS JOIN LATERAL generate_series(1, p.n_post) s
)
INSERT INTO hr.postings (employee_id, unit_id, designation_id, from_date, to_date, order_number, posting_type, remarks)
SELECT employee_id,
       CASE WHEN seq = n_post THEN current_unit_id ELSE 1 + floor(random()*16)::int END,
       GREATEST(1, designation_id - (n_post - seq)),
       from_dt,
       CASE WHEN to_dt IS NULL AND end_dt < CURRENT_DATE THEN end_dt ELSE to_dt END,
       'ORD/' || EXTRACT(YEAR FROM from_dt)::int || '/' || lpad((floor(random()*9999))::int::text, 4, '0'),
       CASE WHEN seq = 1 THEN 'Initial'
            WHEN GREATEST(1, designation_id - (n_post - seq)) > GREATEST(1, designation_id - (n_post - seq + 1)) THEN 'Promotion'
            WHEN random() < 0.1 THEN 'Deputation'
            ELSE 'Transfer' END,
       NULL
FROM slots;

-- ---------------- Leave (last 2 years) ----------------
INSERT INTO hr.leave_applications (employee_id, leave_type_id, from_date, to_date, status, reason, approved_by, applied_on)
SELECT e.employee_id, lt, f, f + (CASE lt WHEN 1 THEN floor(random()*3) WHEN 3 THEN floor(random()*7) ELSE floor(random()*10) END)::int,
       (ARRAY['Approved','Approved','Approved','Approved','Rejected','Pending','Cancelled'])[1 + floor(random()*7)::int],
       (ARRAY['Personal work','Family function','Medical treatment','Travel to hometown','Child care','Festival'])[1 + floor(random()*6)::int],
       e.reporting_to,
       f - (1 + floor(random()*15)::int)
FROM core.employees e
CROSS JOIN generate_series(1, 6) n
CROSS JOIN LATERAL (
    -- "0 * n" ties the subquery to each outer row so random() is re-evaluated per row
    SELECT (ARRAY[1,1,2,2,3,6])[1 + floor(random()*6)::int + 0 * n] AS lt,
           CURRENT_DATE - (floor(random()*730))::int + 0 * e.employee_id AS f
) x
WHERE e.employment_status IN ('Active','On Deputation') AND random() < 0.8;

-- ---------------- Appraisals (last 5 years) ----------------
INSERT INTO hr.performance_appraisals (employee_id, appraisal_year, rating, grade, reviewer_id, comments)
SELECT employee_id, yr, r,
       CASE WHEN r >= 4.5 THEN 'Outstanding' WHEN r >= 3.8 THEN 'Very Good'
            WHEN r >= 3.0 THEN 'Good' WHEN r >= 2.0 THEN 'Average' ELSE 'Below Average' END,
       reporting_to,
       (ARRAY['Consistent performer','Needs improvement in timeliness','Excellent technical skills',
              'Good team player','Shows leadership potential','Meets expectations'])[1 + floor(random()*6)::int]
FROM core.employees e
CROSS JOIN generate_series(EXTRACT(YEAR FROM CURRENT_DATE)::int - 5, EXTRACT(YEAR FROM CURRENT_DATE)::int - 1) yr
CROSS JOIN LATERAL (SELECT round((1.5 + random()*3.5)::numeric, 1) + 0 * yr + 0 * e.employee_id AS r) x
WHERE yr >= EXTRACT(YEAR FROM e.date_of_joining)
  AND (e.date_of_exit IS NULL OR yr <= EXTRACT(YEAR FROM e.date_of_exit));

-- ---------------- Disciplinary (~3% of staff) ----------------
INSERT INTO hr.disciplinary_actions (employee_id, action_date, action_type, description, status)
SELECT employee_id,
       GREATEST(date_of_joining, CURRENT_DATE - (floor(random()*1500))::int),
       (ARRAY['Warning','Censure','Increment Withheld','Recovery of Loss'])[1 + floor(random()*4)::int],
       (ARRAY['Unauthorised absence','Delay in submission of reports','Breach of IT security policy','Misconduct at workplace'])[1 + floor(random()*4)::int],
       (ARRAY['Open','Closed','Closed','Under Appeal'])[1 + floor(random()*4)::int]
FROM core.employees WHERE random() < 0.03;

ANALYZE;

-- ---------------- Training sessions & enrolments ----------------
-- About one session per course for every 250 employees (minimum 6).
INSERT INTO training.sessions (course_id, unit_id, start_date, end_date, trainer_name, capacity)
SELECT c.course_id,
       (ARRAY[15,15,15,1,4,16])[1 + floor(random()*6)::int],
       sd, sd + c.duration_days - 1,
       (ARRAY['Dr. A. Kapoor','Col. (Retd) R. Singh','Ms. S. Iyer','Mr. P. Thomas','Ms. N. Gill'])[1 + floor(random()*5)::int],
       60
FROM training.courses c
CROSS JOIN generate_series(1, GREATEST(6, :emp_count / 250)) n
CROSS JOIN LATERAL (SELECT CURRENT_DATE - (floor(random()*1095))::int + 60 + 0 * n + 0 * c.course_id AS sd) x;

-- Each active employee is enrolled in 0-5 random sessions held after joining.
INSERT INTO training.enrollments (session_id, employee_id, status, score, certificate_no)
SELECT DISTINCT ON (s.session_id, e.employee_id)
       s.session_id, e.employee_id, st,
       CASE WHEN st IN ('Completed','Failed') THEN round((CASE WHEN st='Completed' THEN 50 + random()*50 ELSE random()*49 END)::numeric, 2) END,
       CASE WHEN st = 'Completed' THEN 'CERT-' || s.session_id || '-' || e.employee_id END
FROM core.employees e
CROSS JOIN generate_series(1, 5) n
CROSS JOIN LATERAL (SELECT 1 + floor(random() * (SELECT max(session_id) FROM training.sessions))::int + 0 * n + 0 * e.employee_id AS sid) r
JOIN training.sessions s ON s.session_id = r.sid
CROSS JOIN LATERAL (
    SELECT CASE WHEN s.start_date > CURRENT_DATE THEN 'Nominated'
                ELSE (ARRAY['Completed','Completed','Completed','Completed','Attended','Failed','Absent'])[1 + floor(random()*7)::int + 0 * s.session_id] END AS st
) x
WHERE e.employment_status = 'Active' AND e.date_of_joining < s.start_date AND random() < 0.6;

-- ---------------- Pay ----------------
INSERT INTO pay.employee_pay (employee_id, basic_pay, effective_from)
SELECT e.employee_id,
       round((ps.min_basic + random() * (ps.max_basic - ps.min_basic)) / 100) * 100,
       date_trunc('year', CURRENT_DATE)::date
FROM core.employees e
JOIN core.designations d ON d.designation_id = e.designation_id
JOIN pay.pay_scales ps ON ps.grade = d.grade;

-- 12 months of payroll for currently paid staff
INSERT INTO pay.payroll (employee_id, pay_month, basic_pay, total_allowances, gross_pay,
                         income_tax, provident_fund, other_deductions, net_pay, paid_on)
SELECT employee_id, m, basic, allw, basic + allw,
       tax, pf, oth, basic + allw - tax - pf - oth,
       (m + INTERVAL '1 month' - INTERVAL '1 day')::date
FROM (
    SELECT ep.employee_id, m::date AS m, ep.basic_pay AS basic,
           round(ep.basic_pay * 0.74 + 3600 + 1250 + CASE WHEN e.department_id IN (4,5) THEN 2500 ELSE 0 END, 2) AS allw,
           round(ep.basic_pay * 0.12, 2) AS pf,
           round((ep.basic_pay * 1.74) * CASE WHEN ep.basic_pay > 100000 THEN 0.20 WHEN ep.basic_pay > 50000 THEN 0.10 ELSE 0.03 END, 2) AS tax,
           (ARRAY[0,0,0,200,500,1000])[1 + floor(random()*6)::int] AS oth
    FROM pay.employee_pay ep
    JOIN core.employees e ON e.employee_id = ep.employee_id
    CROSS JOIN generate_series(date_trunc('month', CURRENT_DATE) - INTERVAL '12 months',
                               date_trunc('month', CURRENT_DATE) - INTERVAL '1 month',
                               INTERVAL '1 month') m
    WHERE e.employment_status IN ('Active','On Deputation','Suspended')
      AND e.date_of_joining <= m::date
) t;

ANALYZE pay.payroll;

-- Allowance break-up per slip
INSERT INTO pay.payroll_allowances (payroll_id, allowance_type_id, amount)
SELECT p.payroll_id, a.allowance_type_id,
       COALESCE(round(p.basic_pay * a.pct_of_basic / 100, 2), a.fixed_amount)
FROM pay.payroll p
JOIN core.employees e ON e.employee_id = p.employee_id
JOIN pay.allowance_types a ON a.code <> 'SPL' OR e.department_id IN (4,5);

DROP TABLE _names;
COMMIT;

-- Summary
SELECT 'employees' AS table_name, count(*) FROM core.employees
UNION ALL SELECT 'postings', count(*) FROM hr.postings
UNION ALL SELECT 'leave_applications', count(*) FROM hr.leave_applications
UNION ALL SELECT 'appraisals', count(*) FROM hr.performance_appraisals
UNION ALL SELECT 'training_sessions', count(*) FROM training.sessions
UNION ALL SELECT 'enrollments', count(*) FROM training.enrollments
UNION ALL SELECT 'payroll_slips', count(*) FROM pay.payroll;
