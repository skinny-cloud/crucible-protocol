# Sample Payments Service (KNOWN-GOOD)

This is the corrected counterpart of `examples/known-bad`. Every CRUCIBLE defect
has been fixed. Running `crucible audit examples/known-good` shows the static
gates PASS and the git/tool gates SKIP (they cannot run against a plain dir).

Coverage is reported from the CI run (dynamic), not a hardcoded badge.
