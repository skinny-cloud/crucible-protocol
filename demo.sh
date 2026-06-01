#!/usr/bin/env bash
# CRUCIBLE Protocol — one-command reviewer demo.
# Builds an isolated venv, pip-installs the crucible CLI, and runs it against the
# known-bad and known-good sample targets so a reviewer sees real violations
# caught and a clean target pass — end to end, no system pollution.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

VENV="$ROOT/.demo-venv"
echo "==> Building isolated venv at $VENV"
python3 -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install --quiet --upgrade pip
echo "==> pip install -e . (installs the 'crucible' CLI)"
pip install --quiet -e .

echo
echo "==> Verifying entry point resolves: $(command -v crucible)"
crucible --help >/dev/null && echo "    crucible CLI OK"

echo
echo "########################################################################"
echo "#  crucible audit examples/known-bad   (expect FAIL — real violations)  #"
echo "########################################################################"
set +e
crucible audit examples/known-bad
BAD_RC=$?
set -e
echo "    [exit code: $BAD_RC  (1 = violations found, as expected)]"

echo
echo "########################################################################"
echo "#  crucible audit examples/known-good  (expect PASS — clean target)     #"
echo "########################################################################"
set +e
crucible audit examples/known-good
GOOD_RC=$?
set -e
echo "    [exit code: $GOOD_RC  (0 = no violations, as expected)]"

echo
echo "==> Running the detector test suite (the no-theater integrity proof)"
pip install --quiet pytest
python -m pytest -q

echo
echo "==> DEMO SUMMARY"
if [ "$BAD_RC" -eq 1 ] && [ "$GOOD_RC" -eq 0 ]; then
  echo "    PASS: known-bad correctly FAILED ($BAD_RC), known-good correctly PASSED ($GOOD_RC)."
else
  echo "    UNEXPECTED: known-bad=$BAD_RC (want 1), known-good=$GOOD_RC (want 0)."
  exit 1
fi
