# Shared helpers for the scripts. Source it: `. "$(dirname "$0")/_lib.sh"`.
BASE_URL="${MOCHI_BASE_URL:-http://localhost:8000}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage_and_exit_if_help() {
  # $1 = usage text; prints it and exits 0 when the script was called with -h or --help.
  case "${2:-}" in -h|--help) printf '%s\n' "$1"; exit 0 ;; esac
}

need() {
  command -v "$1" >/dev/null 2>&1 || { echo "missing tool: $1 ($2)" >&2; exit 1; }
}

post() {
  # post PATH [JSON_BODY]  -> prints the response body, fails on HTTP errors
  curl --silent --show-error --fail-with-body -X POST "$BASE_URL$1" \
    -H 'Content-Type: application/json' --data "${2:-{\}}"
}
