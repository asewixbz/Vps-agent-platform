# Model Adapter Contract

## Goal

This project must be able to switch between external model providers without rewriting the control plane or the agent runtime.

The model layer is intentionally isolated behind a provider-neutral contract so the rest of the system only depends on:

- messages going in
- structured responses coming out
- capability information
- errors and health status

## Current status

Stage 1 now includes a concrete provider connector:

- the internal contract exists
- the adapter registry exists
- settings are ready for provider selection
- there is a placeholder adapter for the unconfigured state
- the Kie.ai adapter is wired in
- the FastAPI app exposes `/model/health` and `/model/chat`
- the CLI exposes `model-health` and `model-chat`

What is still intentionally limited:

- streaming is surfaced in the contract but not yet wired through the runtime as a first-class streaming API
- provider routing between multiple providers is not implemented
- planner-style agent execution sits on top of this layer and is still a later step

## Contract

The core file is `backend/app/model_adapter.py`.

It defines:

- `ModelMessage` — a single chat message passed to a model
- `ModelRequest` — the full request sent to a model
- `ModelResponse` — the normalized response returned from a model
- `ModelUsage` — token usage metadata
- `ModelCapabilities` — what a provider can do
- `ModelHealth` — whether the provider is available and configured
- `ModelAdapterSpec` — which adapter and model should be used
- `ModelAdapter` — the provider-neutral interface
- `register_model_adapter()` — registry hook for new adapters
- `resolve_model_adapter()` — selects the configured adapter
- `build_model_adapter()` — convenience helper from settings

## Design rules

### 1. Keep the core neutral

The execution core should not know whether the provider is Kie.ai, another aggregator, or a direct model API.

Only adapters may know provider-specific payload shapes, response formats, auth details, or special limits.

### 2. Treat provider swaps as configuration, not code rewrites

The app should switch providers through settings and adapter registration, not by scattering provider checks throughout the runtime.

### 3. Prefer structured outputs

The next layers of the system will need more than plain text. The contract already includes a `structured_data` field so the agent runtime can later ask for JSON-like output when planning or classifying work.

### 4. Keep capability discovery explicit

Before the agent runtime relies on a model for structured output, tool calls, or streaming, it should inspect `ModelCapabilities`.

## Settings

The model-related settings live in `backend/app/settings.py`:

- `model_adapter_name`
- `model_default_alias`
- `model_request_timeout_seconds`
- `model_adapter_options_json`

The `.env.example` file documents the matching environment variables.

For Kie.ai, the adapter options JSON can include:

- `api_key`
- `base_url`
- `endpoint`
- `default_model`
- `request_timeout_seconds`

## Adapter behavior

### Unconfigured adapter

If no provider is configured yet, the system uses `UnconfiguredModelAdapter`.

This adapter is deliberate:

- it makes the unconfigured state explicit
- it avoids pretending a model is available when it is not
- it gives the runtime a clean error path instead of a silent failure

### Kie.ai adapter

The Kie.ai adapter translates the neutral request shape into `POST /codex/v1/responses`.

It currently supports:

- bearer-token auth
- text message conversion
- tool-call payload passthrough via request metadata
- response normalization into `ModelResponse`
- health reporting

### Future adapters

A new adapter should only be added if it can translate the external API into the existing contract without leaking provider-specific details into the core.

A provider adapter should be responsible for:

- auth and request formatting
- provider-specific retries and rate limits
- mapping provider responses into `ModelResponse`
- reporting accurate capabilities

## Adding a new provider later

When you implement a concrete provider connector:

1. Create a new adapter module under `backend/app/`
2. Implement the `ModelAdapter` interface
3. Register it with `register_model_adapter()`
4. Update the settings or env file to select it
5. Keep provider-specific code out of the agent runtime

## What the next stage should do

The next stage is not another interface change. It should be a real connector for one external provider, wired into the existing contract.

After that, the project can add:

- provider routing
- fallback behavior
- prompt building
- planner output schemas
- agent execution loops
