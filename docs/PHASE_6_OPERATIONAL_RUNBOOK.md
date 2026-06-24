# Phase 6 operational runbook

## Purpose

Use this guide when a run is blocked, a task fails, or you need to inspect the current runtime and audit state without reading the implementation first.

## 1) Fast health check

Start with the control plane and queue:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/queue
curl http://localhost:8000/security/controls
curl http://localhost:8000/persistence/layers
curl http://localhost:8000/persistence/schema
```

What to look for:

- `health.status` should be `ok` for a normal local setup
- `queue.healthy` should be `true`
- `security/controls` should show the current trust levels, approval triggers, and budget limits
- `persistence/schema` should show `schema_name=persistence` and the seeded schema metadata row once startup has run

## 2) Task triage

List tasks and inspect the task that failed or blocked:

```bash
python -m app.cli tasks
python -m app.cli task <task-id>
python -m app.cli queue
```

If a task is waiting for approval:

```bash
python -m app.cli approve <task-id> --note "approved after review"
```

Useful fields:

- `status`
- `reason`
- `stdout`
- `stderr`
- `approved`
- `approval_note`

## 3) Runtime triage

Inspect the runtime run first, then the event stream, then the trace:

```bash
python -m app.cli runs
python -m app.cli run-show <runtime-run-id>
python -m app.cli run-events <runtime-run-id>
python -m app.cli run-events <runtime-run-id> --grouped
python -m app.cli run-provenance <runtime-run-id> --limit 50 --depth 2
```

The most useful runtime fields are:

- `status`
- `summary`
- `blocked_reason`
- `resume_hint`
- `checkpoint.next_step_index`
- `steps`
- `event_count`

If you need the full inspection surface, fetch the trace API:

```bash
curl http://localhost:8000/agent/runs/<runtime-run-id>/trace?limit=100&depth=2
```

The trace payload now carries:

- `trace_context`
- `events`
- `grouped_events`
- `steps`
- `artifacts`
- `audit`
- `navigation`

## 4) How to interpret audit data

When a run or event blocks, check these fields first:

- `reason_code`
- `blocked_reason`
- `resume_hint`
- `tool_name`
- `task_id`
- `artifact_refs`
- `trace.correlation_id`

The runtime audit summary in the trace is the quickest way to see:

- which event names appeared
- which reason codes were emitted
- which tools and tasks were involved
- which artifact refs were recorded
- whether the run spent time blocked or waiting for approval

## 5) Workflow and schedule triage

List and inspect workflow schedules:

```bash
python -m app.cli workflow-schedules
python -m app.cli workflow-schedule <schedule-id>
python -m app.cli workflow-schedule-dispatch-due --limit 10
```

If a schedule does not trigger:

- confirm `status` is `active`
- confirm `next_run_at` is populated and not in the future
- confirm the target workflow template still exists
- inspect the last runtime run id and last run status on the schedule record

## 6) Memory and provenance triage

For long-lived work, check the durable memory and provenance trail:

```bash
python -m app.cli memory-list
python -m app.cli memory-show <memory-record-id>
python -m app.cli memory-provenance <memory-record-id> --limit 50 --depth 2
python -m app.cli memory-record-links <memory-record-id>
```

Useful when you need to answer:

- what snapshot was persisted
- which artifacts were linked
- how a runtime run relates to a project or contact dossier
- which links or refs led to the current durable record

## 7) Common failure patterns

### Blocked by policy

If the task is blocked before execution, inspect:

- `reason`
- `reason_code`
- `policy`
- `policy_source`
- `requires_approval`

### Blocked by timeout or step budget

If the task or runtime stops early, inspect:

- `timeout_budget`
- `checkpoint`
- `resume_hint`
- `runtime_max_steps_hard_limit`

### Browser failures

If browser execution is disabled or gated:

- verify `APP_BROWSER_RUNNER_ENABLED=true` in the environment
- check `/security/controls` for browser approval triggers
- confirm the URL scheme is `http` or `https`

### Persistence or schema issues

If startup or inspection fails around durable state:

- check `/persistence/layers`
- check `/persistence/schema`
- verify the `schema_metadata` row exists after startup
- confirm the SQLite file is writable

## 8) Quick reference

### Control-plane endpoints

- `GET /health`
- `GET /queue`
- `GET /tools`
- `GET /tasks`
- `GET /tasks/{task_id}`
- `POST /tasks/{task_id}/approve`

### Runtime endpoints

- `POST /agent/plan`
- `POST /agent/run`
- `GET /agent/runs`
- `GET /agent/runs/{runtime_run_id}`
- `GET /agent/runs/{runtime_run_id}/events`
- `GET /agent/runs/{runtime_run_id}/trace`
- `GET /agent/runs/{runtime_run_id}/provenance`

### Operational endpoints

- `GET /security/controls`
- `GET /persistence/layers`
- `GET /persistence/schema`
- `GET /workflow-schedules`
- `GET /workflow-schedules/{schedule_id}`
- `POST /workflow-schedules/dispatch-due`

## 9) When to escalate

Escalate if any of the following are true:

- the run is blocked with an unclear `reason_code`
- the same task keeps failing after a valid resume hint
- the trace shows missing or inconsistent audit metadata
- the persistence schema snapshot is missing after startup
- the queue is unhealthy or the worker is not draining tasks

When escalating, include:

- the runtime run id or task id
- the `reason_code`
- the `resume_hint`
- the trace payload
- the output of `/security/controls`
- the output of `/persistence/schema`
