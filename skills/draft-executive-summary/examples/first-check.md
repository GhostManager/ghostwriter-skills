# Draft-executive-summary first-check fixture

This synthetic offline snapshot is intentionally compact. It models only the fields needed for a first drafting check and is not a substitute for a complete Ghostwriter export.

```json
{
  "title": "Sample Web Assessment",
  "findings": [
    {
      "id": 101,
      "title": "Missing authorization on account export",
      "severity": "High",
      "description": "A signed-in user could request another account's export by changing the account identifier.",
      "impact": "Unauthorized disclosure of account data is possible.",
      "recommendation": "Enforce server-side authorization for the requested account before creating an export.",
      "complete": true
    },
    {
      "id": 102,
      "title": "Verbose response header",
      "severity": "Informational",
      "description": "A response header reveals framework version information.",
      "impact": "The header may assist technology fingerprinting.",
      "recommendation": "Remove unnecessary version-identifying response headers.",
      "complete": true
    }
  ],
  "totals": {
    "findings": 2,
    "findings_high": 1,
    "findings_info": 1
  },
  "project": {},
  "client": {
    "name": "SpecterOps"
  },
  "extra_fields": {}
}
```

## Expected result

The client-facing text should read as paste-ready report prose, not as a narration of the report artifact. It should lead with wording such as “The SpecterOps assessment team found a high-severity authorization weakness in the account export function.” It should explain in plain language that the weakness could expose another account's data and that authorization should be enforced server-side.

It should then use wording such as “The assessment team also found an informational response header that reveals framework version information. The team recommends removing unnecessary version-identifying headers as a secondary hardening action.” It must not say “the assessment also noted,” “the report says,” or “the snapshot shows.” It must not say the issue was exploited, that data was actually disclosed, or that remediation is complete.

The separate draft-basis notes should identify the source as an offline synthetic snapshot whose freshness is unknown, report the two-finding severity breakdown, and state that no optional extra-field context was used.

## What this does not establish

The fixture does not prove a live report is current, authorize access to a Ghostwriter instance, or establish wording for a particular customer's style guide.
