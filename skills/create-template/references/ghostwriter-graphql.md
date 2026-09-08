# Optional Ghostwriter extra-field discovery

Read this reference only when `create-template` has a user-supplied Ghostwriter endpoint and read-authorized token. The offline conversion workflow does not require it. The target instance's schema and authorization response take precedence over these current conventions.

This reference was verified against Ghostwriter `v7.2.6-2-g446ba7fe`, using `ghostwriter/api/views.py` and `DOCS/schema.graphql`. Re-check the target Action when using another version.

## Authentication and boundary

Send a JSON `POST` request to Ghostwriter's public GraphQL endpoint, normally `https://<host>/v1/graphql`, with a scoped read-only token. Do not send the request to the Django Action handler (for example, `/api/getExtraFieldSpec`); Hasura supplies the Action secret and forwards the caller's bearer token to that internal handler.

```text
Authorization: Bearer <read-only token>
Content-Type: application/json
```

Request the minimum field specifications needed to map visible source sections. Do not include a token in a template, conversion report, console transcript, or diagnostic. Do not call a mutation, upload a template, create an extra field, or retrieve unrelated customer/project data.

## Read extra-field specifications

On current Ghostwriter versions, the following read-only Action exposes the configured field definitions for one model:

```graphql
query DiscoverExtraFields($model: String!) {
  getExtraFieldSpec(model: $model) {
    extraFieldSpec
  }
}
```

Call it first with `report`. Call it with `project` or `client` only if the source has a section that belongs to that model, such as assessment parameters or client-specific report-writing guidance.

`extraFieldSpec` is JSON encoded as a string. Parse it locally. In the verified version, each field contains `internalName`, `displayName`, `type`, and `default`; it does not contain the administrator's description. Use the first three attributes for matching and ignore `default`, which can contain instance-specific report content. An internal name is the value placed in the Jinja expression; it is not necessarily the user-facing label.

## Matching example

For a report section named “Executive Summary,” a rich-text field whose display name is “Executive Summary” and internal name is `executive_summary` is an unambiguous mapping:

```jinja2
{{p extra_fields.executive_summary}}
```

If an instance instead has fields named `summary`, `executive_summary`, and `leadership_notes`, list their display names, internal names, and types and request a selection unless one is clearly designated by the available metadata. The current Action does not return administrator descriptions. A non-rich-text match must not be emitted using `{{p ...}}`.

## Compatibility and failure handling

If the Action is absent, its response shape differs, or the token lacks access, report the limitation and keep the output offline-compatible. Propose fields instead of inventing existing instance fields. Do not query schema-wide metadata or retry with a broader credential.
