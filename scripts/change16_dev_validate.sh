#!/usr/bin/env bash
# Future LIVE round only. Never source into an interactive shell. No token printed.
set +x
[[ "${BASH_SOURCE[0]}" == "$0" ]] || { printf "Execute with bash, do not source.\n"; return 1; }
set -euo pipefail
umask 077
: "${CHANGE16_LIVE_CONFIRM:?Set exactly up-data-intelligence-dev}"
: "${CHANGE16_APPROVED_SHA:?Full approved main commit SHA required}"
: "${META_ACCOUNT_ID:?Explicit approved numeric account required}"
: "${META_CONFIRM_ACCOUNT_ID:?Repeat approved account}"
: "${META_API_VERSION:?Explicit approved vNN.0 API version required}"
: "${META_TOKEN_SECRET_REFERENCE:?Global server-side Secret Version reference required}"
[[ "$CHANGE16_LIVE_CONFIRM" == up-data-intelligence-dev ]]
[[ "$META_ACCOUNT_ID" =~ ^[0-9]+$ && "$META_ACCOUNT_ID" == "$META_CONFIRM_ACCOUNT_ID" ]]
[[ "$META_API_VERSION" =~ ^v[0-9]+\.0$ ]]
[[ "$META_TOKEN_SECRET_REFERENCE" =~ ^projects/up-data-intelligence-dev/secrets/up-intelligence-meta-global-token/versions/[0-9]+$ ]]
ROOT=$(git rev-parse --show-toplevel)
cd "$ROOT"
[[ $(git branch --show-current) == main ]]
[[ $(git rev-parse HEAD) == "$CHANGE16_APPROVED_SHA" ]]
[[ $(git rev-parse origin/main) == "$CHANGE16_APPROVED_SHA" ]]
[[ -z $(git status --porcelain) ]]
[[ $(gcloud config get-value project 2>/dev/null) == up-data-intelligence-dev ]]
gcloud auth application-default print-access-token >/dev/null
# Ensure the global token exists without exposing or storing its bytes.
gcloud secrets versions access "${META_TOKEN_SECRET_REFERENCE##*/}" --project=up-data-intelligence-dev --secret=up-intelligence-meta-global-token >/dev/null
PYTHON="$ROOT/.venv/bin/python"
[[ -x "$PYTHON" ]]
ARGS=(--live --project up-data-intelligence-dev --confirm-project up-data-intelligence-dev --location southamerica-east1 --policy config/analytics/mx-fashion.dev.json --store-id mx-fashion --confirm-store mx-fashion --account-id "$META_ACCOUNT_ID" --confirm-account-id "$META_ACCOUNT_ID" --api-version "$META_API_VERSION" --lease-bucket up-data-intelligence-dev-876521886531-leases)
# Mandatory authority already present. Missing table/binding stops; never auto-binds.
"$PYTHON" -m src.intelligence.live.cli preflight "${ARGS[@]}"
ROUND=$(mktemp -d /tmp/up-change16-round.XXXXXX)
PY_PID=""; NEXT_PID=""
cleanup() {
  [[ -z "$NEXT_PID" ]] || kill "$NEXT_PID" 2>/dev/null || true
  [[ -z "$PY_PID" ]] || kill "$PY_PID" 2>/dev/null || true
  [[ -z "$NEXT_PID" ]] || wait "$NEXT_PID" 2>/dev/null || true
  [[ -z "$PY_PID" ]] || wait "$PY_PID" 2>/dev/null || true
  unset DASHBOARD_DEV_PREVIEW_TOKEN
  # Saved plans can contain sensitive state; delete local round artifacts, never DEV data.
  rm -rf "$ROUND"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
terraform -chdir=infra/terraform init -input=false
terraform -chdir=infra/terraform plan -input=false -var-file=environments/dev.tfvars -out="$ROUND/change16.tfplan"
terraform -chdir=infra/terraform show -json "$ROUND/change16.tfplan" > "$ROUND/plan.json"
"$PYTHON" -m scripts.change16_plan_guard "$ROUND/plan.json"
printf 'Type APPLY_CHANGE16_DEV to apply this reviewed additive saved plan: '
read -r answer
[[ "$answer" == APPLY_CHANGE16_DEV ]] || { printf 'Apply not authorized. Stopping.\n'; exit 1; }
terraform -chdir=infra/terraform apply -input=false "$ROUND/change16.tfplan"
# Read-only account verification; listing does not write binding or select an account.
"$PYTHON" -m src.intelligence.live.cli list-accounts "${ARGS[@]}" --secret-reference "$META_TOKEN_SECRET_REFERENCE" > "$ROUND/accounts.json"
"$PYTHON" - "$ROUND/accounts.json" "$META_ACCOUNT_ID" <<'PY'
import json,sys
rows=[r for r in json.load(open(sys.argv[1])) if r['account_id']==sys.argv[2]]
if len(rows)!=1 or rows[0]['currency']!='BRL' or rows[0]['timezone']!='America/Sao_Paulo':raise SystemExit('INCOMPATIBLE_META_ACCOUNT')
PY
"$PYTHON" -m src.intelligence.live.cli meta-sync "${ARGS[@]}" --resource all --page-limit 100 --secret-reference "$META_TOKEN_SECRET_REFERENCE"
# Keep both instants fixed for retry of this logical publication. Operators record non-secret values.
SNAPSHOT=$("$PYTHON" -c 'from datetime import datetime,UTC; print(datetime.now(UTC).isoformat())')
CALCULATED="$SNAPSHOT"
printf 'Controlled source snapshot/calculated_at: %s\n' "$SNAPSHOT"
printf 'Type PUBLISH_CHANGE16_DEV to initialize HEAD if absent and publish all models: '
read -r answer
[[ "$answer" == PUBLISH_CHANGE16_DEV ]] || exit 1
"$PYTHON" -m src.intelligence.live.cli materialize "${ARGS[@]}" --source-snapshot-at "$SNAPSHOT" --calculated-at "$CALCULATED" --initialize-head
"$PYTHON" -m src.intelligence.live.cli validate "${ARGS[@]}"
export DASHBOARD_DEV_PREVIEW_TOKEN
DASHBOARD_DEV_PREVIEW_TOKEN=$("$PYTHON" -c 'import secrets; print(secrets.token_urlsafe(48))')
"$PYTHON" -m src.dashboard.dev_preview_server --project up-data-intelligence-dev --location southamerica-east1 --policy config/analytics/mx-fashion.dev.json --tenant-id demo-up --store-id mx-fashion --confirm-store mx-fashion --allow-bq-read --port 8765 >"$ROUND/read-api.log" 2>&1 &
PY_PID=$!
(cd frontend && exec env DASHBOARD_DATA_MODE=read-api-preview DASHBOARD_READ_API_BASE_URL=http://127.0.0.1:8765 node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3100) >"$ROUND/next.log" 2>&1 &
NEXT_PID=$!
# Readiness never queries BigQuery: check only the local login page/listening socket.
for ((n=0;n<60;n++)); do
  kill -0 "$PY_PID"; kill -0 "$NEXT_PID"
  if curl --silent --fail http://127.0.0.1:3100/ >/dev/null; then break; fi
  sleep 1
done
curl --silent --fail http://127.0.0.1:3100/ >/dev/null
(cd frontend && DASHBOARD_E2E_LIVE=1 ./node_modules/.bin/playwright test --config=playwright.b2b-preview.config.ts --grep 'CHANGE16 integrated')
printf 'CHANGE16 single DEV round completed. No schedulers enabled; DEV data retained.\n'
