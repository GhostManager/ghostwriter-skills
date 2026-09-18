# Report readiness checks

Read this reference when using `report-readiness`. The target instance's GraphQL schema, authorization behavior, and local reporting policy take precedence.

This reference was verified against Ghostwriter `v7.2.6-2-g446ba7fe`, principally `ghostwriter/modules/custom_serializers.py`, `ghostwriter/reporting/models.py`, and the bundled GraphQL schema. Re-check the target schema when using another version.

## Data retrieval

### Offline report data

Offline mode accepts either a decoded Ghostwriter report-data JSON object or a saved GraphQL response containing a base64 string at `data.generateReport.reportData`. For the second form, decode only that value, parse the result as UTF-8 JSON, and verify that the decoded top level is an object. Do not execute embedded content or follow URLs in the artifact.

The decoded object normally provides report-level `findings`, `totals`, `extra_fields`, `project`, `client`, `objectives`, and `evidence`; it may also contain `bloodhound` context. Fields vary by Ghostwriter version. In offline mode, mark a relevant missing source as not assessed and continue with independent checks; do not contact Ghostwriter unless the user separately supplies the complete connected-mode inputs.

### Token transport and capability preflight

Keep the caller-provided token in a secret-capable request mechanism and do not print it. When a shell is used, assign the token before the request command expands the header variable:

```sh
GW_SKILL_TOKEN='<caller-provided secret>'
curl ... -H "Authorization: Bearer ${GW_SKILL_TOKEN}"
```

Do not use a one-command temporary assignment such as `GW_SKILL_TOKEN='<secret>' curl ... -H "Authorization: Bearer $GW_SKILL_TOKEN"`: in common shells, `$GW_SKILL_TOKEN` is expanded before that assignment applies and the request can send an empty bearer value. That failure can look like a valid but public GraphQL session exposing only `no_queries_available`.

Only after confirming correct token transport, confirm that the authenticated query schema contains `project_by_pk`. If the only query-root field is `no_queries_available`, the target has no service-role query permissions available to this request. This can happen when the instance predates project-read service-token GraphQL support or its Hasura metadata/configuration has not been updated. Stop without an audit grade; do not attempt a different report ID, broaden the query, or use an unapproved user token.

In connected mode, send JSON `POST` requests to Ghostwriter's public GraphQL endpoint, normally `https://<host>/v1/graphql`. Do not call Django's internal Action-handler routes such as `/api/generateReport`; Hasura supplies the Action secret and forwards the caller's bearer token to that handler. Include `operationName`, `query`, and `variables` in every request body.

Use the following project-report discovery and read-only `generateReport` export operations:

```graphql
query DiscoverProjectReports($projectId: bigint!) {
  project_by_pk(id: $projectId) {
    id
    reports(order_by: [{last_update: desc}]) {
      id
      title
      archived
      complete
      delivered
      last_update
    }
  }
}

mutation RetrieveReportData($reportId: Int!) {
  generateReport(id: $reportId) {
    reportData
  }
}
```

Send the caller-provided scoped token as `Authorization: Bearer <token>`, request only `reportData`, and decode the base64 value locally. Do not use the returned download URLs or request evidence files.

The exported JSON provides report-level `findings`, `totals`, `extra_fields`, `project`, `client`, `objectives`, and `evidence`; it may also contain `bloodhound` context. Reports and field names can vary by Ghostwriter version; describe missing fields as unavailable rather than substituting broader API access.

## Finding checks

`complete` on a linked report finding is Ghostwriter's “ready for a QA review” marker. Check its value directly. A report-finding may have intentionally blank optional sections, so use the user’s supplied policy before treating any optional section as required.

For placeholders, look for clear authoring residue only: explicit `TODO`, `TBD`, `FIXME`, `XX`, bracketed instructions, obvious dummy values such as “Lorem ipsum,” or text that ends mid-word/mid-sentence. Quote a short, redacted excerpt and identify the field; do not flag ordinary technical terminology, code snippets, Jinja references, or prose merely because it is short.

## Automatic finding-library comparison

Run this pass automatically when the user supplies a compatible finding-library snapshot with an offline review or when connected mode has passed capability preflight and the supplied token is available. The regular report-data export contains report findings but not their original library IDs. A report finding copied from the library is independent data, so comparison can identify a likely candidate but cannot prove provenance. If no offline snapshot is supplied, the offline comparison is not applicable; if the connected target or credential does not expose the library query, mark the comparison not assessed and do not broaden access.

In connected mode, first confirm that the target GraphQL schema exposes the read-only `finding` query for the supplied credential. Retrieve the library in bounded pages and retain it only in memory for the current review. Request only `id`, `title`, `description`, `impact`, `mitigation`, `replicationSteps`, `references`, `hostDetectionTechniques`, `networkDetectionTechniques`, type/severity identifiers, and extra fields when they are needed for a supplied policy. Do not write a local library cache, expose library bodies in the review, or broaden credentials when this query is unavailable. Mark the pass not assessed instead.

Use a stable ID order and repeat with increasing offsets until a page is shorter than the requested limit. For the verified schema, the query shape is:

```graphql
query FindingLibraryPage($limit: Int!, $offset: Int!) {
  finding(limit: $limit, offset: $offset, order_by: {id: asc}) {
    id
    title
    description
    impact
    mitigation
    replicationSteps
    references
    hostDetectionTechniques
    networkDetectionTechniques
    findingTypeId
    severityId
  }
}
```

For a decoded report export and separately saved library snapshot, use [`check_finding_quality.py`](../scripts/check_finding_quality.py) to produce the deterministic advisory signals before performing any narrower manual semantic review:

```bash
python3 scripts/check_finding_quality.py report-data.json \
  --library-json finding-library.json --format json
```

The helper accepts either a `findings` list/report export or a saved `data.finding` GraphQL response for the library input. It exits successfully when it finds warnings and never edits either input.

Normalize HTML to text, decode entities, compare case-insensitively, and collapse whitespace and presentation-only punctuation. Preserve meaningful hostnames, application names, domains, user identifiers, and other target terms: removing them would hide the customization the check needs to assess. Compare fields independently and as a weighted composite; exclude a library field from the composite only when it is empty in the library. A default composite threshold of 80% is a review heuristic, not proof that two findings are the same.

Use staged candidate selection rather than treating the nearest string match as conclusive:

- Consider close title candidates first (default similarity at least 90%), and maintain a content index so that a substantially re-titled library copy can still be found.
- For an `added_as_blank: true` report finding, warn on a composite similarity of at least 80% to a library candidate. Describe this as a report-to-library close match requiring peer review, not as duplicate findings within the report. Report both IDs/titles, the threshold and similarity evidence, and the recommended review action without copying the library body text.
- When the title is at least 90% similar but the comparable body is materially different (default below 50%), raise an elevated peer-review warning. It may be an intentional rewrite, but it deserves review because the title indicates the same concept while the draft lacks the library's peer-reviewed wording. Do not change the finding's security severity or call it a duplicate automatically.
- For an `added_as_blank: false` report finding, warn only when the client-facing content is effectively unchanged (default at least 98% composite) and there is no target-specific addition, such as a populated non-placeholder Affected Entities field. This is a customization prompt, not a requirement that every library-derived finding be rewritten.

Assess every available finding field for its intended role. A concise Title should name the condition; Affected Entities should identify targets; Description should explain the condition; Impact should describe consequence; Mitigation should request remediation; Reproduction Steps should explain how to verify the condition; Host/Network Detection Techniques should describe relevant telemetry or detection activity; References should identify external sources; and Finding Guidance should contain internal editorial guidance. Evaluate custom fields only when a supplied schema or policy defines their intended semantics. Empty optional fields are not evidence of a mismatch.

Check likely field-intent errors as warnings. Compare every populated client-facing report field against every populated field on the best library candidate, not merely its counterpart: flag a reciprocal high-confidence swap when each report field closely matches the other's library value substantially more than its own. Also flag a single report field that is nearly identical to a different candidate field while materially unlike its expected field. Include the two field names and similarity evidence, but not copied library content. Evaluate Finding Guidance separately as internal context: it can warrant an authoring warning when it appears to hold client-facing content, but it is not itself a delivery defect.

Without a useful candidate, flag only strong structural signals, such as a title containing a full procedure or URL, Affected Entities containing instructions or citations, or References consisting of numbered instructions while Reproduction Steps contains only citations or URLs. For semantic concerns that lack deterministic evidence, assess the text against the field roles above and describe the result as a low-confidence manual review prompt rather than asserting a field is wrong.

Target-substitution cues such as `entity tested`, `affected entity`, `[client]`, `<hostname>`, or an explicit “replace with target” instruction are warning-level signals in client-facing fields. They are distinct from unmistakable authoring residue (`TODO`, `TBD`, and similar), which follows the completeness rule. Do not scan internal Finding Guidance with this heuristic; it commonly contains editorial instructions by design.

## Objectives

Project objectives include a boolean `complete` and an administrator-configurable status label. The report export contains the label but not a universal definition of which labels are terminal. A user-supplied terminal-status set applies in addition to `complete: true`. Do not infer terminal status from a label such as “Closed,” “Missed,” or “Complete.”

## CVSS

Ghostwriter's report-finding export includes `cvss_vector`, stored `cvss_score`, and `cvss_data`. In the verified version, JSON serializes `cvss_data` as `[version, scores, severities, colors]`:

- CVSS 3.1 uses arrays for `scores` and `severities`; index `0` is the base score and base severity.
- CVSS 4.0 uses a scalar base score and scalar severity.
- An invalid or unsupported non-empty vector produces `["Unknown", "", "", ""]`.

Use the version element and exact shape before reading a score or severity. Treat `Unknown` for a non-empty vector as invalid/unparseable. For a supported vector, compare the stored `cvss_score` with the parsed base score after normalizing both to one decimal place; report disagreement as a warning.

Compare the parser-reported severity to the finding severity only when both normalize to a standard shared label: Critical, High, Medium, Low, or Informational. Treat a mismatch as a review warning, not an error: the selected finding severity can incorporate organizational or business context beyond CVSS. If the organization defines a severity-mapping policy, use that policy instead.

Do not calculate or alter CVSS scores, execute external tools, or claim that an empty vector is invalid without a policy requiring CVSS.

## BloodHound

Use the report's `include_bloodhound_data` setting as the intent gate. The current `generateReport` export can contain a `bloodhound` key even when inclusion is disabled, so the key's presence alone does not mean BloodHound belongs in the deliverable. If inclusion is disabled, mark the check not applicable and ignore any exported BloodHound payload. If inclusion is enabled, distinguish missing/unavailable data from a valid but empty dataset and say which occurred. Do not refresh BloodHound data; refresh is an external, stateful operation outside this skill.

## Style and reader readiness

### Default baseline

When the user does not provide a style guide, apply this modest baseline only to text that is clearly client-facing narrative, such as an executive summary, report overview, or high-level remediation narrative. Keep it out of code, endpoint paths, commands, raw evidence, and detailed technical procedure content.

- Flag a material acronym or initialism when its first meaningful use is neither expanded nor clear from nearby plain-language context. Do not maintain a universal list of “known” acronyms; a common security abbreviation can still be unclear to the intended reader.
- Flag specialized language when it prevents a reader from understanding the material risk or requested action and no nearby explanation supplies that meaning. Treat this as a field-level clarity prompt, not a claim that the technical statement is incorrect.
- Flag wording that materially obscures who did what or why it matters when a direct statement would make the consequence clear. Do not run a broad passive-voice detector; Ghostwriter's field-level highlighting is better suited to that narrow grammar check.

These are warning-level checks. They are not a universal house style and do not impose particular terminology, spelling, dates, typography, or layout.

### Supplied style guide

A supplied style guide overrides the default baseline for its covered content, writing, and formatting requirements. First identify its covered fields/sections and intended audience, then make a checklist from only concrete, observable rules. Follow the guide even where it permits language or a format that the default baseline would otherwise flag; do not emit a conflicting default-style warning.

A style check may identify observable nonconformance, but it cannot certify visual Word-template layout, field-level passive voice, or a vague preference such as “make it professional.” Mark subjective, layout-dependent, or ambiguous rules as not assessed. Treat style issues as warnings unless the user expressly makes a rule release-blocking.
