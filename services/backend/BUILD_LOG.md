# Build log

Append one entry per checkpoint: what works and how to see it.

## Scaffold
- Repo, tooling, platform wrappers, architecture-rules test. See it: `make -C services/backend verify`.

## Contracts
- Pydantic models for AGENTS section 6, one JSON example per event/payload, exported JSON Schema.
  See it: `make -C services/backend test`, `make -C services/backend contracts-schema`.
