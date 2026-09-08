# Ghostwriter Skills

Portable Agent Skills for Ghostwriter users and maintainers.

This repository is intentionally separate from the Ghostwriter application source tree. It contains reusable workflows that can be installed alongside Claude Code, Codex, Cursor, GitHub Copilot, Gemini CLI, and other Agent Skills-compatible tools.

## Install

Install the collection with the `skills` CLI:

```bash
npx skills add GhostManager/ghostwriter-skills
```

Install selected skills for specific agents globally:

```bash
npx skills add GhostManager/ghostwriter-skills \
  --skill report-readiness \
  --agent claude-code \
  --agent codex \
  --global
```

The repository is also intended to be discoverable through [skills.sh](https://skills.sh).

## Repository layout

```text
skills/
  <skill-name>/
    SKILL.md          Required metadata and instructions
    scripts/          Optional executable helpers
    references/       Optional supporting documentation
    assets/           Optional templates and other resources
scripts/              Repository maintenance scripts
tests/                Skill behavior and fixture tests
```

Each skill must contain a `SKILL.md` file with `name` and `description` YAML frontmatter. Keep the core instructions focused and move detailed material into `references/` so agents can load it only when needed.

## Compatibility and versioning

Skill releases are versioned independently from Ghostwriter releases. Use Git tags for releases and document Ghostwriter version requirements in each skill's compatibility section or namespaced metadata.

Skills should remain provider-neutral wherever possible. Agent-specific metadata, such as `agents/openai.yaml`, should be added only when it improves the experience for that agent and does not make the core workflow dependent on it.

Analysis skills support an offline mode using local documents or decoded Ghostwriter report-data JSON exports. When connected metadata or report retrieval is useful, supply Ghostwriter's public `/v1/graphql` endpoint and strongly prefer a scoped `gwst_` project-read service token. Tokens belong in the `Authorization: Bearer ...` header and must not be stored in repository files or command arguments.

## Development

Validate all completed skills with the Agent Skills reference validator:

```bash
make validate
```

Do not add secrets, credentials, private customer data, or environment-specific URLs to a skill. Review every script as executable code before release.

## Available skills

- `create-template` converts a sample Word report or template into a Ghostwriter Jinja2 DOCX template.
- `draft-executive-summary` drafts a traceable executive summary from one report's findings and selected context.
- `report-readiness` grades a report or linked finding for final-reporting readiness.
- `review-template` performs offline Ghostwriter lint-parity, package, visual, and optional style-guide review for DOCX and PPTX templates.
