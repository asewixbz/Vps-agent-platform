# Vps Agent Platform — Handoff and Implementation Plan

## Purpose

This repository is the control plane for an AI system that must do more than generate text. The intended product is an AI-driven execution platform:

- a user can submit a task in natural language
- the system decides what tools or workflows are needed
- the system executes work on machine resources
- the system stores state, artifacts, and progress
- the system asks for approval when a step is risky or not trusted

The project should be treated as an execution platform first, and a UI product second.

## Current stage of the project

### Already implemented

- FastAPI control plane
- SQLite persistence
- Redis-backed queue
- worker loop
- tool registry
- task registry
- approval flow
- policy gate
- Python runner
- shell runner
- browser runner scaffold

### What exists but is still early

- browser execution is behind a feature flag
- model execution is only a placeholder
- shell execution is intentionally restricted
- there is no conversational agent layer yet
- there is no CLI client yet
- there is no durable memory layer for long-running work
- there is no production-grade sandboxing

## Technical direction

The project should evolve in three layers:

1. **Control plane**
   - stores tools, tasks, approvals, and results
   - decides whether a task may run
   - queues work and tracks state

2. **Agent runtime**
   - converts user intent into plans
   - chooses tools
   - runs multi-step loops
   - retries, compares, and continues work until the task is done or blocked

3. **Persistence and memory**
   - stores task history
   - stores experiment results and artifacts
   - stores long-lived context for projects, contacts, and recurring workflows

## Primary usage model

The system must work from the command line first.

The CLI should be the initial operational interface for:

- submitting tasks
- checking status
- approving tasks
- inspecting outputs
- eventually driving agent-style workflows without a web UI

The web interface can come later as another client, not as the core dependency.

## Intended workload types

The platform should support at least three categories of work:

### 1. Autonomous engineering tasks

Examples:

- design a neural network architecture for a task
- train and debug it
- inspect metrics and logs
- apply changes repeatedly until human attention is needed again

This requires:

- code execution
- artifact storage
- iterative planning
- retry loops
- comparison of experiment runs

### 2. Monitoring and ranking workflows

Examples:

- scan procurement or auction listings
- normalize the data
- score items against custom criteria
- produce a ranked report
- repeat on a schedule or on demand

This requires:

- data collection tools
- repeatable pipelines
- deduplication
- explainable scoring
- stable report generation

### 3. Long-running conversational workflows

Examples:

- continue a conversation over time
- keep a per-contact dossier
- track current stage and next step
- recall prior context when needed

This requires:

- long-term memory
- contact/task summaries
- conversation history
- structured notes and state

## Recommended implementation path

### Recommended overall approach

Use a **control-plane-first, CLI-first, model-agnostic architecture**.

Why this is the right path:

- the existing code already gives a control plane and execution foundation
- the project needs reliability before autonomy
- the model provider is not settled yet, so the AI layer must be swappable
- CLI-first delivery gets the system working sooner than a web app
- different workloads need different execution modes, and the architecture should support that

### Alternatives considered

#### Agent-first

Build a strong chatbot/agent experience first, then add infrastructure later.

- Pros: faster demo value, more immediate AI feel
- Cons: tends to become brittle, hard to secure, and hard to scale

#### Workflow-first

Model everything as fixed pipelines or DAGs.

- Pros: predictable, testable, good for repetitive tasks
- Cons: too rigid for open-ended engineering or conversational work

#### Web-first

Build a UI and then connect execution later.

- Pros: good for product demos
- Cons: does not solve the main technical problem, which is reliable execution

#### Sandbox-first

Spend the most effort on isolation and runtime hardening before higher-level features.

- Pros: safest eventual platform
- Cons: slows down useful iteration too early

### Why the recommended path wins

The recommended path keeps the project useful early while still allowing hardening later. It supports:

- flexible reasoning for open-ended tasks
- fixed workflows for repeated monitoring work
- memory-backed continuation for long-running relationships with projects or contacts

## Phase plan

### Phase 1 — CLI-first operational layer

Goal: make the system usable without a web interface.

Deliverables:

- a CLI entrypoint
- commands to inspect health, tools, tasks, and queue state
- a command to create tasks from the terminal
- a command to approve queued tasks
- human-readable output with an optional JSON mode later

Acceptance criteria:

- a developer can send a task to the platform from the terminal
- a developer can view the task id and status
- a developer can approve a task without using a browser
- the CLI works against the existing FastAPI backend

### Phase 2 — Model adapter and agent planner

Goal: connect an external model through a provider-agnostic layer.

Deliverables:

- a model adapter abstraction
- prompt/response handling
- structured plan output
- tool-selection logic
- error handling for retries and malformed output

Acceptance criteria:

- a text request can become a structured plan
- the plan can choose between direct execution and workflow execution
- the model provider can be changed without rewriting the application core

### Phase 3 — Agent runtime and multi-step execution

Goal: let the system continue working across multiple steps.

Deliverables:

- execution loop
- step state tracking
- partial results
- checkpoint and stop conditions
- safe interruption and resume behavior

Acceptance criteria:

- the system can complete a task with multiple tool calls
- the system can summarize progress
- the system can stop when human input is needed

### Phase 4 — Durable memory

Goal: make long-running work actually persistent.

Deliverables:

- conversation history storage
- project/task summaries
- contact dossiers
- experiment logs
- artifact indexing

Acceptance criteria:

- the system can continue a task later without losing the important context
- the system can track long-lived work items and their state

### Phase 5 — Workflow templates

Goal: make repeated jobs predictable and cheap to run.

Deliverables:

- scanning workflows
- ranking workflows
- report generation workflows
- scheduling hooks later if needed

Acceptance criteria:

- repeated jobs can run through a fixed template instead of a fully open-ended agent loop
- the results are reproducible and easier to debug

### Phase 6 — Runtime hardening

Goal: make execution safer and more production-ready.

Deliverables:

- stronger sandboxing
- better isolation per task
- artifact retention
- observability and audit logs
- migration away from SQLite when required

Acceptance criteria:

- tasks are isolated better than the current basic runner setup
- execution is traceable and easier to audit

## Current code map

- `backend/app/main.py` — API endpoints for tools, tasks, approvals, and queue status
- `backend/app/store.py` — SQLite schema and CRUD
- `backend/app/policy.py` — trust and safety checks
- `backend/app/job_queue.py` — Redis queue wrapper
- `backend/app/runner.py` — Python, shell, and browser execution helpers
- `backend/app/executor.py` — task execution orchestration
- `backend/app/worker.py` — queue consumer loop
- `backend/app/settings.py` — configuration

## Immediate next work

1. Add a CLI client that talks to the FastAPI backend.
2. Make task submission and approval usable from the terminal.
3. Add a lightweight model adapter interface.
4. Define the first agent runtime loop after the CLI is working.

## Working rules for future contributors

- Do not optimize for a web UI before the CLI flow works.
- Keep the model provider abstract until a concrete provider choice is made.
- Preserve the control plane and approval model; do not bypass them for convenience.
- Prefer clear, inspectable state over hidden automation.
- Separate open-ended agent work from fixed workflows.

## Current project status summary

The repository is already a usable execution backbone. The next real step is to make it operable from the command line and then connect a provider-agnostic AI orchestration layer on top.
