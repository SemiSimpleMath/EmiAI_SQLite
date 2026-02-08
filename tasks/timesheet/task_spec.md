---
schema_version: 1
task_id: timesheet_narratives_v1
manager: emi_team_manager
description: Generate time-entry narratives from a dated timesheet log.

includes:
  - tasks/timesheet/formatting_rules.md

inputs:
  - id: timesheet
    path: tasks/timesheet/timesheet_2026_2_2.txt
    type: text
    required: true

outputs:
  - id: narratives
    path: tasks/timesheet/timesheet_2026_2_2_narratives.txt
    format: text
    overwrite: true

acceptance_tests:
  - id: out_exists
    type: file_exists
    target: outputs.narratives

idempotency: overwrite_outputs

limits:
  timeout_seconds: 900
  max_cycles: 50

parsing_rules:
  date_marker_regex: '^\\*[0-9]{1,2}/[0-9]{1,2}/[0-9]{2}\\*$'
---
# Task

1) Read the dates in `tasks/timesheet/timesheet_2026_2_2.txt` marked like `*M/D/YY*`.
2) For each date marker, read the text between this marker and the next marker (or EOF for last one).
3) For each date, write narratives per company in this format:
   "<date> <entity>: <time entry block>"
4) If notes are unclear, write:
   "<date> <entity>: [Notes are lacking human assistance needed]"
