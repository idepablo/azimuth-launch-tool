#!/usr/bin/env bash
# Run a command, retrying if it fails.
# Usage: retry.sh <attempts> <wait_seconds> <command...>
#
# Databricks Free Edition sometimes refuses to start compute for a while
# ("Cannot create the resource, please try again later"). Every pipeline
# step is safe to repeat (loads replace or merge, dbt rebuilds the same
# tables), so waiting and trying again is enough.
attempts=$1
wait=$2
shift 2
status=0
for i in $(seq 1 "$attempts"); do
  "$@" && exit 0
  status=$?
  if [ "$i" -lt "$attempts" ]; then
    echo "::warning title=Retrying::Attempt $i of $attempts failed (exit $status): $*. Trying again in ${wait}s."
    sleep "$wait"
  fi
done
exit "$status"
