# Report-readiness first-check fixture

This synthetic first check validates both the grading boundary and the advisory finding-library comparison. Use [first-check-readiness.json](first-check-readiness.json) for the grade boundary, then compare [first-check-report.json](first-check-report.json) with the supplied [first-check-finding-library.json](first-check-finding-library.json). Neither input is a complete Ghostwriter report-data export; fields absent here would be **not assessed** in a real offline review.

```json
{
  "title": "Sample Internal Assessment",
  "findings": [
    {
      "id": 201,
      "title": "Administrative endpoint lacks role check",
      "severity": "High",
      "complete": false,
      "description": "A standard account can access an administrative endpoint.",
      "impact": "Unauthorized administrative actions may be possible.",
      "recommendation": "Enforce server-side role authorization."
    }
  ],
  "objectives": [],
  "include_bloodhound_data": false
}
```

## Expected result

- **Grade:** C - Needs remediation.
- **Blocker:** finding `201`, because `complete` is false.
- **Warnings:** seven advisory library-comparison warnings: unchanged library-derived content for findings `201` and `202`; a target-substitution cue in finding `202`; a blank-origin report finding (`203`) with a 100% match to finding-library entry `503`; title/body divergence for finding `204`; and field-intent mismatches in findings `205` and `206`. These are report-to-library comparisons, not a claim that findings are duplicated within the report.
- **Not applicable:** BloodHound, because inclusion is disabled.
- **Not assessed:** any relevant check whose source field is absent from this compact fixture, such as a complete CVSS alignment check or selected-template dependencies.
- **No mutation:** do not change finding `201` or any other Ghostwriter data.

## What this does not establish

It does not prove the report can be delivered, validate an objective policy, or substitute for the full report-wide review required by the main skill.

## First-run validation

Run both commands on the first validation. The first confirms the one-blocker grade boundary; the second uses the supplied finding-library fixture to exercise the advisory-only comparison checks. The fixtures are synthetic and never contact Ghostwriter:

```sh
python3 scripts/grade_readiness.py --blockers 1 --warnings 7 --essential-unassessed

python3 scripts/check_finding_quality.py examples/first-check-report.json \
  --library-json examples/first-check-finding-library.json --format json
```

The grade helper returns `C`. The finding-quality command exits successfully because it reports warnings rather than blocking failures. Its seven `issues` are:

```json
[
  "FINDING-LIBRARY-UNCUSTOMIZED",
  "FINDING-TARGET-PLACEHOLDER",
  "FINDING-LIBRARY-UNCUSTOMIZED",
  "FINDING-LIBRARY-CLOSE-MATCH",
  "FINDING-LIBRARY-TITLE-DIVERGENCE",
  "FINDING-FIELD-INTENT-MISMATCH",
  "FINDING-FIELD-INTENT-MISMATCH"
]
```

The fixture demonstrates: unchanged library-derived findings, an `entity tested` cue, a blank-origin finding over the 80% similarity threshold, a same-title but divergent blank-origin finding, and swaps in both References/Reproduction Steps and Description/Impact. All are warnings raised for awareness; no finding severity, status, or content changes.
