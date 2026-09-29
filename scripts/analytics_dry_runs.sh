#!/usr/bin/env bash
# Run as a child process: bash scripts/analytics_dry_runs.sh. Never source this file.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  printf 'Execute com bash scripts/analytics_dry_runs.sh; não use source.\n' >&2
  return 2
fi
set +e  # Capture failures explicitly, even if errexit was inherited.
set -u
set -o pipefail
umask 077
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 2
python_bin="${PYTHON_BIN:-python}"
fixture="${ANALYTICS_FIXTURE:-tests/fixtures/analytics_readiness/synthetic.json}"
validation_dir="${ANALYTICS_VALIDATION_DIR:-$(mktemp -d /tmp/analytics-dry-runs.XXXXXX)}"
mkdir -p "$validation_dir" || exit 2
summary="$validation_dir/dry-run-summary.tsv"
printf 'model\tpython_exit\ttee_exit\tstatus\n' > "$summary" || exit 2
models=(
  analytics_store_daily
  analytics_customer_metrics
  analytics_customer_purchase_sequence
  analytics_cohorts
  analytics_purchase_distribution
  analytics_products_daily
  analytics_funnel_daily
)
overall=0
for model in "${models[@]}"; do
  "$python_bin" -m src.analytics.parity dry-run \
    --fixture "$fixture" --output "$validation_dir" \
    --model "$model" --allow-gcp --confirm-project up-data-intelligence-dev \
    --maximum-bytes-billed "${ANALYTICS_MAXIMUM_BYTES_BILLED:-1000000000}" \
    2>&1 | tee "$validation_dir/$model.log"
  # Capture both statuses immediately: even a printf would replace PIPESTATUS.
  pipeline_status=("${PIPESTATUS[@]}")
  python_status="${pipeline_status[0]}"
  tee_status="${pipeline_status[1]}"
  status=PASSOU
  if (( python_status != 0 || tee_status != 0 )); then
    status=FALHOU
    if (( overall == 0 )); then
      if (( python_status != 0 )); then overall="$python_status"; else overall="$tee_status"; fi
    fi
  fi
  printf '%s: %s (python=%s, tee=%s)\n' "$model" "$status" "$python_status" "$tee_status"
  if ! printf '%s\t%s\t%s\t%s\n' "$model" "$python_status" "$tee_status" "$status" >> "$summary"; then
    overall=1
  fi
done
printf 'Resumo: %s\n' "$summary"
exit "$overall"
