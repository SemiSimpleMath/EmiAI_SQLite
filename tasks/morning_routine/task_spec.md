---
schema_version: 1
task_id: morning_routine_v1
manager: emi_team_manager
description: Morning routine summary (email, calendar, top news, and HTML report).

includes:
  - tasks/morning_routine/rules.md

inputs:
  - id: email_window_hours
    path: tasks/morning_routine/email_window_hours.txt
    type: text
    required: true
  - id: output_template
    path: tasks/morning_routine/template.html
    type: text
    required: false

outputs:
  - id: morning_summary
    path: tasks/morning_routine/morning_routine.html
    format: html
    overwrite: true

acceptance_tests:
  - id: out_exists
    type: file_exists
    target: outputs.morning_summary

idempotency: overwrite_outputs

limits:
  timeout_seconds: 900
  max_cycles: 50
---
# Task

Run the morning routine and write a single HTML report.

Steps:
1) Read `tasks/morning_routine/email_window_hours.txt` to get the number of hours to look back for email (default is 10 if the file is empty).
2) Fetch emails from the last N hours.
3) Fetch today's calendar events.
4) Visit CNN and identify today's main story (headline + 1-2 sentence summary).
5) Visit Daily Kos and identify the main topics people are discussing (2-4 bullets).
6) Write a clean HTML report to `tasks/morning_routine/morning_routine.html` using the template if provided.

Output sections (in order):
- Email summary (top 5 items)
- Calendar summary (today's events)
- CNN main story
- Daily Kos discussion highlights

If any source fails, include a short error note in that section and continue.
