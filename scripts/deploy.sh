#!/usr/bin/env bash
set -euo pipefail

: "${DEPLOY_SSH_KEY:?Missing DEPLOY_SSH_KEY secret}"
: "${DEPLOY_KNOWN_HOSTS:?Missing DEPLOY_KNOWN_HOSTS secret}"
: "${GITHUB_SHA:?Missing commit SHA}"
: "${GITHUB_RUN_ID:?Missing workflow run ID}"
: "${GITHUB_RUN_ATTEMPT:?Missing workflow attempt}"

task_tmp=$(mktemp -d)
trap 'rm -rf "$task_tmp"' EXIT
umask 077
printf '%s\n' "$DEPLOY_SSH_KEY" > "$task_tmp/id_ed25519"
printf '%s\n' "$DEPLOY_KNOWN_HOSTS" > "$task_tmp/known_hosts"
unset DEPLOY_SSH_KEY DEPLOY_KNOWN_HOSTS
ssh_options=(-i "$task_tmp/id_ed25519" -o IdentityAgent=none -o IdentitiesOnly=yes
  -o BatchMode=yes -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$task_tmp/known_hosts"
  -o ConnectTimeout=20 -o ServerAliveInterval=15 -o ServerAliveCountMax=3)
destination=u0252265@server122.hosting.reg.ru

if [[ ${1:-deploy} == rollback ]]; then
  [[ ${EXPECTED_RELEASE:-} =~ ^[0-9a-f]{40}-[0-9]+-[0-9]+$ ]] || { echo 'Invalid expected release'; exit 1; }
  ssh "${ssh_options[@]}" "$destination" "rollback $EXPECTED_RELEASE"
  exit
fi

[[ $GITHUB_SHA =~ ^[0-9a-f]{40}$ && $GITHUB_RUN_ID =~ ^[0-9]+$ && $GITHUB_RUN_ATTEMPT =~ ^[0-9]+$ ]] || exit 1
release_id="$GITHUB_SHA-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT"
mkdir "$task_tmp/site"
tar -xzf dist/site.tar.gz -C "$task_tmp/site"
python3 - "$task_tmp/site/deploy-version.json" <<'PY'
import json, os, sys
version = json.load(open(sys.argv[1]))
assert version == {'revision': os.environ['GITHUB_SHA'], 'run_id': os.environ['GITHUB_RUN_ID'] + '-' + os.environ['GITHUB_RUN_ATTEMPT']}
PY
ssh "${ssh_options[@]}" "$destination" "deploy $GITHUB_SHA $GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT" < dist/site.tar.gz
if ! python3 scripts/verify_live.py --directory "$task_tmp/site"; then
  echo 'External verification failed. Restoring the preceding release.' >&2
  ssh "${ssh_options[@]}" "$destination" "rollback $release_id"
  exit 1
fi
if [[ -n ${GITHUB_STEP_SUMMARY:-} ]]; then
  printf 'Deployed `%s` to https://promoznachki.ru/\n\nRollback guard: `%s`\n' "$GITHUB_SHA" "$release_id" >> "$GITHUB_STEP_SUMMARY"
fi
