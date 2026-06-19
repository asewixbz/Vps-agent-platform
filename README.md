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

## What is not included yet

- Postgres
- GPU/model runner
- automatic code generation for arbitrary tools
- full sandbox hardening with seccomp/AppArmor profiles
- multi-step agent runtime with persistent memory

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
      cli.py
      executor.py
      job_queue.py
      main.py
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
python -m app.cli model-health
python -m app.cli model-chat --payload '{"messages":[{"role":"user","content":"Say hello"}]}'
python -m app.cli plan "Summarize the latest open tasks"
python -m app.cli register-tool local_python_test python --description "Run a local Python smoke test" --entrypoint python --status trusted --trust-level 2
python -m app.cli submit local_python_test --payload '{"script":"print(\"hello from the runner\")"}'
python -m app.cli approve <task-id> --note "approved for run"
```

Use `--base-url` if the API is not running on `http://localhost:8000`.

## Model endpoints

- `GET /model/health`
- `POST /model/chat`
- `POST /agent/plan`

The planning endpoint is conservative by design: it can return a heuristic plan even when the model runner is disabled, and it will try to refine that plan through the configured adapter when model execution is enabled.

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

### Phase 3
- Postgres
- stronger policy engine
- trust scoring
- safer tool promotion

### Phase 4
- automatic tool synthesis
- sandbox-first execution
- human approval gates for risky actions

## Notes on safety

The shell runner is guarded by a basic allowlist and heuristic policy checks. This is not enough for high-risk production use by itself. Treat this platform as a controlled development system, not as a fully hardened security boundary.
