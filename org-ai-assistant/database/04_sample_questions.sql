-- =====================================================================
-- Sample natural-language questions and the SQL the AI should produce.
-- These become the "few-shot examples" and the evaluation test set
-- in later steps. Add 50-100 of these from real user questions.
-- Run as: SET ROLE ai_readonly; SET app.user_role = 'hr_admin';
-- =====================================================================

-- Q1: How many active employees are there in each department?
SELECT department, count(*) AS active_employees
FROM ai_views.employees WHERE employment_status = 'Active'
GROUP BY department ORDER BY active_employees DESC;

-- Q2: Who is currently posted at the Primary Data Centre?
SELECT emp_code, first_name, last_name, designation, department
FROM ai_views.employees WHERE current_unit = 'Primary Data Centre'
ORDER BY designation, last_name;

-- Q3: Show the posting history of employee EMP000010.
SELECT p.unit_name, p.city, p.designation, p.from_date, p.to_date, p.posting_type
FROM ai_views.postings p JOIN ai_views.employees e USING (employee_id)
WHERE e.emp_code = 'EMP000010' ORDER BY p.from_date;

-- Q4: Which active employees have NOT completed the mandatory Cyber Security Awareness course?
SELECT e.emp_code, e.first_name, e.last_name, e.department
FROM ai_views.employees e
WHERE e.employment_status = 'Active'
  AND NOT EXISTS (SELECT 1 FROM ai_views.training t
                  WHERE t.employee_id = e.employee_id AND t.course_code = 'CS-101' AND t.status = 'Completed')
ORDER BY e.department, e.last_name;

-- Q5: Total salary paid (net) per month for the last 6 months.
SELECT pay_month, sum(net_pay) AS total_net_pay, count(*) AS employees_paid
FROM ai_views.payroll
WHERE pay_month >= date_trunc('month', CURRENT_DATE) - INTERVAL '6 months'
GROUP BY pay_month ORDER BY pay_month;

-- Q6: Employees retiring in the next 2 years (retirement age 60).
SELECT emp_code, first_name, last_name, designation, age_years
FROM ai_views.employees WHERE employment_status = 'Active' AND age_years >= 58
ORDER BY age_years DESC;

-- Q7: Average appraisal rating by department for last year.
SELECT e.department, round(avg(a.rating), 2) AS avg_rating
FROM ai_views.appraisals a JOIN ai_views.employees e USING (employee_id)
WHERE a.appraisal_year = EXTRACT(YEAR FROM CURRENT_DATE) - 1
GROUP BY e.department ORDER BY avg_rating DESC;

-- Q8: How many days of approved leave has each employee taken this year? (top 10)
SELECT e.emp_code, e.first_name, e.last_name, sum(l.days) AS leave_days
FROM ai_views.leave l JOIN ai_views.employees e USING (employee_id)
WHERE l.status = 'Approved' AND l.from_date >= date_trunc('year', CURRENT_DATE)
GROUP BY e.emp_code, e.first_name, e.last_name ORDER BY leave_days DESC LIMIT 10;
