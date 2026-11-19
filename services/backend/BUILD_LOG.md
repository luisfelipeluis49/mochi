# Build log

Append one entry per checkpoint: what works and how to see it.

## Scaffold
- Repo, tooling, platform wrappers, architecture-rules test. See it: `make -C services/backend verify`.

## Contracts
- Pydantic models for AGENTS section 6, one JSON example per event/payload, exported JSON Schema.
  See it: `make -C services/backend test`, `make -C services/backend contracts-schema`.

## Intelligence (M0-M4 intelligence rows)
- `decide()` cases 1-9, quiet rules, whose-word rule, learning states, `handle()` rounds, memory.
  See it: `make -C services/backend test`; 66 sentences in `packages/fixtures/decisions.json`.
