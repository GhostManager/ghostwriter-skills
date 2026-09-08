# Ghostwriter GraphQL retrieval

Read this reference when loading report data for `draft-executive-summary`. It covers offline exports and Ghostwriter's current GraphQL conventions; the target instance's schema and authorization results take precedence.

This reference was verified against Ghostwriter `v7.2.6-2-g446ba7fe`, using `DOCS/schema.graphql`, `ghostwriter/api/views.py`, and the report serializers as sources. Re-check the target schema and Action authorization when using another version.

## Offline snapshot data

Snapshot mode accepts either:

- A decoded Ghostwriter report-data JSON object previously produced by `generateReport` or an equivalent Ghostwriter export.
- A saved GraphQL response containing a base64 string at `data.generateReport.reportData`.

For the second form, decode only that base64 value, parse the result as UTF-8 JSON, and verify that the decoded top level is an object. Do not execute embedded content or follow URLs in either artifact. A decoded report-data export normally contains `findings`, `totals`, `extra_fields`, `project`, and `client`, but fields vary by Ghostwriter version. Treat absent data as unavailable. This is analysis of a previously retrieved snapshot, not offline discovery: the skill cannot determine whether the source report has changed since export.

## Authentication and endpoint

In connected mode, send JSON `POST` requests to Ghostwriter's public GraphQL endpoint, normally `https://<host>/v1/graphql`, with:

```text
Authorization: Bearer <project-read token>
Content-Type: application/json
```

Use a scoped `gwst_` project-read service token where possible. Do not fetch schema-wide data, use an admin secret, or retry authorization failures with a broader token.

Do not call Django's internal Action-handler routes such as `/api/generateReport` or `/api/getExtraFieldSpec`. Hasura supplies the Action secret and forwards the caller's bearer token to those handlers. Include `operationName`, `query`, and `variables` in every request body.

## Verify token transport before diagnosing access

Do not print the supplied token. Use the request tool's secret/header facility when it has one. With a shell-based client, assign the token before expanding it into the header:

```sh
GW_SKILL_TOKEN='<caller-provided secret>'
curl ... -H "Authorization: Bearer ${GW_SKILL_TOKEN}"
```

Do not write `GW_SKILL_TOKEN='<secret>' curl ... -H "Authorization: Bearer $GW_SKILL_TOKEN"`. Shell expansion can happen before the temporary assignment, sending an empty bearer header that can look like a public GraphQL session with no available data queries. Confirm this transport step before treating a missing GraphQL field as a server-version, permission, or token-scope problem.

## Discover the report

The current schema exposes `project_by_pk` and its `reports` relationship. Request only enough metadata to resolve the selected report:

```graphql
query DiscoverProjectReports($projectId: bigint!) {
  project_by_pk(id: $projectId) {
    id
    codename
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
```

If the instance rejects `bigint` or any selected field, inspect its accessible schema and adapt the query rather than substituting a mutation.

## Retrieve report data

Ghostwriter's `generateReport` Action accepts a report ID and returns an export payload. It is declared as a mutation in GraphQL, but the current Ghostwriter implementation only creates an in-memory export and returns `reportData` and download URLs. Request only `reportData`:

```graphql
mutation RetrieveReportData($reportId: Int!) {
  generateReport(id: $reportId) {
    reportData
  }
}
```

Decode `reportData` from base64 to JSON locally. The export context contains the selected report's `findings`, `totals`, `extra_fields`, `project`, and `client`; it can also contain broader report context. Extract only the fields needed for the requested summary. Do not download evidence or report files.

## Discover extra fields

On versions that expose the Action, field definitions can be retrieved without mutation:

```graphql
query DiscoverExtraFields($model: String!) {
  getExtraFieldSpec(model: $model) {
    extraFieldSpec
  }
}
```

Call it with `report`, `project`, or `client`. `extraFieldSpec` is a JSON-encoded string: parse it locally to obtain each field's `internalName`, `displayName`, and `type`. Use `internalName` to read the matching value from the relevant `extra_fields` object in `reportData`.

If `getExtraFieldSpec` is unavailable or unauthorized, do not probe unrelated data. Ask the user for an exact extra-field selector or the desired text.
