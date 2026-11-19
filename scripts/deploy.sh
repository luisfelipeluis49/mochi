#!/usr/bin/env bash
# Build the image locally, run it with .env, check /readyz, and print the Render steps.
set -euo pipefail
. "$(dirname "$0")/_lib.sh"
usage_and_exit_if_help "Usage: scripts/deploy.sh
Builds services/backend/Dockerfile (context: repo root), runs it on :8000 with ./.env, polls /readyz,
then prints how to deploy through the Render Blueprint (render.yaml). Does not push anything." "${1:-}"
need docker "install Docker"

IMAGE="mochi-backend:local"
SHA="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo dev)"
docker build -f "$ROOT/services/backend/Dockerfile" --build-arg GIT_SHA="$SHA" -t "$IMAGE" "$ROOT"
ENV_ARGS=(); [ -f "$ROOT/.env" ] && ENV_ARGS=(--env-file "$ROOT/.env")
docker rm -f mochi-backend-local >/dev/null 2>&1 || true
docker run -d --name mochi-backend-local -p 8000:8000 "${ENV_ARGS[@]}" "$IMAGE" >/dev/null
for _ in $(seq 1 30); do
  if curl -sf "$BASE_URL/readyz" >/dev/null; then curl -s "$BASE_URL/readyz"; echo; break; fi
  sleep 1
done
docker logs --tail 5 mochi-backend-local
cat <<MSG

Render: push the repo, then in the Render dashboard choose New > Blueprint and select it
(render.yaml at the repo root). Fill the secrets (sync: false) and set MOCHI_PUBLIC_URL to the
service's https URL. Stop the local container with: docker rm -f mochi-backend-local
MSG
