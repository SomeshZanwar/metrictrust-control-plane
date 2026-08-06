#!/usr/bin/env bash
# Runs the real dbt project (dbt Core + DuckDB) and leaves manifest.json /
# run_results.json in dbt_project/target for app/evidence.py to read.
set -euo pipefail
cd "$(dirname "$0")/../dbt_project"
export DBT_PROFILES_DIR="../.dbt"
dbt seed
dbt run
dbt test || true   # evidence broker reads the *results*, including failures — don't abort the script on a failing test
echo "dbt artifacts refreshed: target/manifest.json, target/run_results.json"
