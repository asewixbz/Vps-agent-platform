# VPS Agent Control Plane

This is a starter for an agent platform that can:

- keep a registry of tools
- classify tool execution requests
- require approval for untrusted tools
- queue work through Redis
- run Python, shell, and browser tasks inside containers
- persist state in SQLite on a mounted volume

The system is intentionally conservative. It does **not** yet auto-generate arbitrary tools end-to-end. That comes in later phases after the control plane is stable.

## What is included right now

- FastAPI API
- Redis queue
- worker process
- SQLite persistence
- tool registry
- task registry
- policy gate
- Python runner
- shell runner
- browser runner
- approval flow
- terminal CLI
- provider-agnostic model adapter contract
- Kie.ai model adapter wiring
- model health/chat API endpoints
- conservative execution planner API and CLI
- conservative multi-step runtime loop API and CLI
- persistent runtime run history, checkpoint/resume markers, and event logs
- durable memory records with artifact indexing
- project and contact dossier helpers
- durable memory links between runtime snapshots, dossiers, and artifact refs
- memory provenance inspection for durable memory graphs
- runtime event replay filters by step or grouped view

## What is not included yet

- GPU/model runner
- automatic code generation for arbitrary tools
- full sandbox hardening with seccomp/AppArmor profiles
- production-grade distributed storage

## Folder layout

```text
vps-agent-platform/
  docker-compose.yml
  .env.example
  docs/
    PROJECT_HANDOFF.md
    MODEL_ADAPTER.md
  backend/
    Dockerfile
    requirements.txt
    app/
      __main__.py
      agent_runtime.py
      cli.py
      dossiers.py
      executor.py
      job_queue.py
      main.py
      memory.py
      memory_links.py
      memory_provenance.py
      model_adapter.py
      model_runtime.py
      planner.py
      policy.py
      runner.py
      settings.py
      store.py
      worker.py
      kieai_adapter.py
```

## Run locally

1. Copy env file:

```bash
cp .env.example .env
```

2. Start the stack:

```bash
docker compose up --build -d
```

3. Check health:

```bash
curl http://localhost:8000/health
```

If you want to run browser tasks, set `APP_BROWSER_RUNNER_ENABLED=true` in `.env` before starting the stack.

To use the Kie.ai adapter, set:

```bash
APP_MODEL_RUNNER_ENABLED=true
APP_MODEL_ADAPTER_NAME=kie_ai
APP_MODEL_ADAPTER_OPTIONS_JSON='{"api_key":"<your-kie-ai-api-key>"}'
```

## CLI quickstart

The backend exposes a terminal client so the project can be used without a web UI.

From `backend/`:

```bash
python -m app.cli health
python -m app.cli tools
python -m app.cli tasks
python -m app.cli runs
python -m app.cli run-show <runtime-run-id>
python -m app.cli run-events <runtime-run-id>
python -m app.cli run-events <runtime-run-id> --step-index 3
python -m app.cli run-events <runtime-run-id> --grouped
python -m app.cli memory-list
python -m app.cli memory-show <memory-record-id>
python -m app.cli memory-upsert --payload '{"memory_key":"contact:asewisher@duck.com","kind":"contact_dossier","scope_type":"contact","scope_id":"asewisher@duck.com","title":"Asewisher","summary":"Primary contact dossier","content":"Stable notes and next steps"}'
python -m app.cli memory-touch <memory-record-id>
python -m app.cli memory-artifacts <memory-record-id>
python -m app.cli memory-artifact-add <memory-record-id> --payload '{"artifact_type":"file","artifact_ref":"docs/notes.md","label":"project notes"}'
python -m app.cli memory-links
python -m app.cli memory-link-add <source-type> <source-id> <target-type> <target-id> updates --note "runtime snapshot updates dossier"
python -m app.cli memory-record-links <memory-record-id>
python -m app.cli memory-provenance <memory-record-id>
python -m app.cli model-health
python -m app.cli model-chat --payload '{"messages":[{"role":"user","content":"Say hello"}]}'
python -m app.cli plan "Summarize the latest open tasks"
python -m app.cli run "Summarize the latest open tasks"
python -m app.cli run "Continue the previous run" --runtime-run-id <runtime-run-id> --resume-from-step 3
python -m app.cli register-tool local_python_test python --description "Run a local Python smoke test" --entrypoint python --status trusted --trust-level 2
python -m app.cli submit local_python_test --payload '{"script":"print(\"hello from the runner\")"}'
python -m app.cli approve <task-id> --note "approved for run"
```

Use `--base-url` if the API is not running on `http://localhost:8000`.

## Model endpoints

- `GET /model/health`
- `POST /model/chat`
- `POST /agent/plan`
- `POST /agent/run`
- `GET /agent/runs`
- `GET /agent/runs/{runtime_run_id}`
- `GET /agent/runs/{runtime_run_id}/events`

## Memory endpoints

- `GET /memory/records`
- `POST /memory/records`
- `GET /memory/records/{memory_record_id}`
- `POST /memory/records/{memory_record_id}/touch`
- `GET /memory/records/{memory_record_id}/artifacts`
- `POST /memory/records/{memory_record_id}/artifacts`
- `GET /memory/links`
- `POST /memory/links`
- `GET /memory/records/{memory_record_id}/links`

The `memory-provenance` CLI command is the easiest way to inspect a record together with its linked memory records and artifact refs.

## Dossier endpoints

- `GET /dossiers`
- `GET /dossiers/contact`
- `POST /dossiers/contact`
- `GET /dossiers/contact/{contact_id}`
- `GET /dossiers/project`
- `POST /dossiers/project`
- `GET /dossiers/project/{project_id}`

The planning endpoint is conservative by design: it can return a heuristic plan even when the model runner is disabled, and it will try to refine that plan through the configured adapter when model execution is enabled.

The runtime endpoint executes the plan step by step and stops when it hits approval, missing input, or a failing step. It also returns checkpoint data so a later call can resume from the next step, stores the cumulative run state in SQLite, and writes step-level runtime events for auditability.

The runtime endpoint also snapshots each run into durable memory so completed or blocked runs can be rediscovered later.

If the runtime context includes `project_id` or `contact_id`, the same run snapshot is also promoted into a project/contact dossier and linked back to that dossier in durable memory.

Runtime snapshots also link to their event-log artifact refs, so the memory layer can keep a trail from run summary to supporting artifact.

The event endpoint supports replay filters:

- `step_index=<n>` to inspect one step
- `grouped=true` to bucket events by step

These route through the configured adapter and let the control plane exercise the provider without changing the runtime. The chat endpoint is enabled only when `APP_MODEL_RUNNER_ENABLED=true`.

## Check the queue

```bash
curl http://localhost:8000/queue
```

## Register a tool

```bash
curl -X POST http://localhost:8000/tools/register \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "local_python_test",
    "kind": "python",
    "description": "Run a local Python smoke test",
    "entrypoint": "python",
    "status": "trusted",
    "trust_level": 2
  }'
```

## Create a task

```bash
curl -X POST http://localhost:8000/tasks \
  -H 'Content-Type: application/json' \
  -d '{
    "tool_name": "local_python_test",
    "payload": {
      "script": "print(\"hello from the runner\")"
    },
    "auto_run": true
  }'
```

## Approve a pending task

```bash
curl -X POST http://localhost:8000/tasks/<task-id>/approve \
  -H 'Content-Type: application/json' \
  -d '{"note": "approved for run"}'
```

## Recommended rollout plan

### Phase 1
- control plane
- local Python/shell execution
- tool registry
- approval flow
- CLI client
- model adapter contract
- model API endpoints
- first provider adapter

### Phase 2
- Redis queue
- worker process
- browser runner
- artifact store
- execution planning bridge
- runtime loop scaffold

### Phase 3
- Postgres
- stronger policy engine
- trust scoring
- safer tool promotion
- persistent runtime history
- runtime event logs

### Phase 4
- durable memory records
- project/contact dossiers
- memory links
- artifact indexing
- long-lived workflow context

### Phase 5
- workflow templates
- scanning workflows
- ranking workflows
- report generation workflows

### Phase 6
- automatic tool synthesis
- sandbox-first execution
- human approval gates for risky actions
- stronger observability and audit logs

## Notes on safety

The shell runner is guarded by a basic allowlist and heuristic policy checks. This is not enough for high-risk production use by itself. Treat this platform as a controlled development system, not as a fully hardened security boundary.
