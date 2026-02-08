---
job_schema_version: 1
job_id: timesheet_batch_v1
description: Batch run for timesheet narratives.

global_context:
  summary: Generate time-entry narratives for the provided timesheet.
  stop_conditions:
    - id: objective_moot
      trigger: child_signal
      signal: objective_moot
      action: cancel_remaining

tasks:
  - job_id: timesheet_narratives
    manager: emi_team_manager
    task_file: tasks/timesheet/task_spec.md
    depends_on: []
    information: Use the task spec instructions and formatting rules.
    budget:
      max_cycles: 50
      timeout_seconds: 900

execution:
  max_parallel_managers: 1
  fail_fast: false
  resume_policy: resume
  output_policy: overwrite
---

# Job

Run the timesheet narratives task as a single managed job.
