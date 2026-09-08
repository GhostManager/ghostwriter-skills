# Repository Guidelines

## Purpose

This repository contains portable Agent Skills for Ghostwriter. It is a distribution repository, not a copy of the Ghostwriter application source code.

Most skill users will not run Ghostwriter or Ghostwriter CLI on the same machine as the agent. Design every skill to work without a local checkout, Docker access, or Ghostwriter CLI. The normal integration path is Ghostwriter's GraphQL API; a local copy of the documentation or application source is an optional authoring and troubleshooting aid, not a runtime dependency.

## Skill format

- Put each user-facing skill under `skills/<skill-name>/`.
- Every skill must contain `SKILL.md` with YAML frontmatter.
- `name` must match the parent directory and use lowercase letters, numbers, and hyphens.
- `description` must explain both what the skill does and when it should be used.
- Keep `SKILL.md` focused; place detailed references and executable helpers in the skill directory.
- Do not put secrets, credentials, customer data, or instance-specific URLs in skills.

## Validation

Run `make validate` for every change that adds or modifies a skill. Review scripts for unsafe commands, undocumented dependencies, network access, and destructive behavior.

## Compatibility

Prefer the portable Agent Skills format. Treat agent-specific files and metadata as optional compatibility layers. Document required Ghostwriter versions, local tools, network access, and permissions in each skill.

### Ghostwriter knowledge sources

- Prefer the published documentation at `https://ghostwriter.wiki` for user-facing guidance. A local `DOCS/` checkout may be used when available, especially to verify a version-specific behavior or inspect the bundled GraphQL schema.
- Do not require agents to download a source checkout merely to use a skill. If a skill ships a compact reference, identify the Ghostwriter version it was derived from and its source document.
- Treat the target instance's GraphQL schema and authorization response as authoritative for that instance. Account for version differences; do not assume a field, Action, or service-token grant exists without verification.

### Portable GraphQL access

- Skills that retrieve Ghostwriter data should use GraphQL queries with a caller-supplied instance URL and token. Do not embed instance URLs, credentials, or customer data in a skill, fixture, command history, or output.
- Prefer a scoped, read-only service token (`gwst_`) for analysis, reporting, and audit skills. Request only the client, project, or activity-log access needed for the stated task.
- A user API token (`gwat_`) inherits that user's permissions and is therefore higher risk. Treat its availability as permission to authenticate, not blanket permission to mutate data.
- Keep credentials in the calling environment or a secret store; pass them in an `Authorization: Bearer` header without echoing them. Redact tokens and sensitive identifiers from diagnostic output.
- Verify credential transport before interpreting an authorization or schema result. For a shell-based request, assign a secret variable in an earlier statement before expanding it in a header, such as `GW_SKILL_TOKEN='<secret>'; curl ... -H "Authorization: Bearer ${GW_SKILL_TOKEN}"`. Do **not** combine a temporary assignment and its expansion in one command, such as `GW_SKILL_TOKEN='<secret>' curl ... -H "Authorization: Bearer $GW_SKILL_TOKEN"`; shell expansion can occur before that temporary assignment. An omitted or empty bearer value can present as the public role and `no_queries_available`, which is not proof that a valid token lacks access. Prefer a tool's secret/header facility when it is available.
- Keep GraphQL requests read-only by default. Use explicit operation names, query only the fields and records needed, and communicate unavailable data or authorization failures instead of trying broader access.

### Proposing GraphQL capabilities

This section applies while developing or maintaining skills, not while a distributed skill is running for an end user. A development agent may recommend a new Ghostwriter GraphQL Action or endpoint when the existing API cannot provide the minimum data or operation needed safely. A proposal is not an available dependency and does not authorize a change to a Ghostwriter server.

Use proposals to improve the eventual user experience, consistency, and least-privilege design of related skills. Describe the proposed capability in terms of its use case, inputs, response shape, read/write behavior, token type and minimum permission scope, authorization checks, data-minimization benefits, and the Ghostwriter version it would require. Prefer narrowly scoped, read-only Actions for analysis and drafting workflows over expanding broad table permissions or requiring a user token. Do not make an endpoint implementation, schema change, or permission change unless the user separately asks for it. Runtime skill instructions must treat only documented, installed capabilities as available.

#### Current development proposals

- **Expose extra-field descriptions:** Extend the existing read-only `getExtraFieldSpec(model)` Action's JSON string so each returned specification includes `description` alongside `internalName`, `displayName`, `type`, and `default`. This would improve semantic field matching for template conversion and writing-guidance discovery without retrieving record values. Retain the current project-read service-token requirement and existing model allowlist. This is a response-only enhancement for a future Ghostwriter version; runtime skills must continue to work when `description` is absent.
- **Report template dependencies:** Consider a read-only `getReportTemplateDependencies(reportId, documentType)` Action that resolves the DOCX or PPTX template selected for that report and returns `{reportId, templateId, documentType, dependencies, parserWarnings}`. Each dependency could be shaped like `{path, model, internalName, valueType, requiredByTemplate}`. Require read access to the report's project, including for project-scoped service tokens. Return names and types without template bytes or record values. This could support readiness checks for empty referenced extra fields in a future Ghostwriter version; runtime skills must mark the check unavailable until the capability is documented and installed.

### Mutations and user consent

Some Ghostwriter GraphQL mutations and all state-changing CLI commands can alter or delete records, templates, files, configuration, containers, or backups. A skill may prepare a proposed change, but it must not execute a mutation merely because the supplied credential allows it.

Before any external state-changing mutation, show the user the intended operation, exact target, and material effects, then obtain explicit confirmation in the current interaction. Reconfirm if those details change. Do not treat a prior read-only query, a user token, or a general request to "automate" something as confirmation. Prefer the least-privileged API capability that can perform the approved action.

Some GraphQL Actions are syntactically mutations but do not change Ghostwriter state. A skill may use one without mutation approval only when the installed Ghostwriter version documents it as read-only, the skill says why it is safe, and it invokes no state-changing operation in the same flow. For example, the current `generateReport` Action exports report data and download URLs; it does not save changes to the report.

### Ghostwriter CLI

Ghostwriter CLI is optional and is for administering a local Ghostwriter installation; it is not a remote API client. Use it only when the user has confirmed that a compatible local installation is in scope and has explicitly authorized the specific command.

- `config set`, host/origin changes, container lifecycle commands, installation/update/migration commands, tag cleanup, restore, PostgreSQL upgrades, and certificate generation are mutating operations and require the confirmation above.
- `restore`, `uninstall`, `containers down --volumes`, and any command that overwrites or removes volumes, media, backups, or configuration require a separate, explicit confirmation that identifies the affected environment and data. Do not run them as part of a skill's normal flow.
- `config get` and full configuration displays can reveal secrets. Request only the necessary non-secret setting and do not surface values such as passwords, keys, or tokens.
- The CLI's `update` and `version` commands can make outbound requests. Document and obtain approval for such network access when a skill needs it.

## Changes

Keep changes narrowly scoped. Add or update tests and examples when a skill's behavior changes. Use imperative commit subjects and tag published skill releases independently from Ghostwriter application releases.
