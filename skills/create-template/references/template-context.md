# Portable Ghostwriter DOCX template context

Read this reference before adding or changing built-in Ghostwriter variables in offline mode. It is a compact conversion aid, not an exhaustive schema.

This reference was derived from Ghostwriter `v7.2.6-2-g446ba7fe`, principally `DOCS/features/reporting/report-templates/word-template-variables.mdx`, `DOCS/features/reporting/templating-and-rich-text-fields.mdx`, and `ghostwriter/modules/custom_serializers.py`. The target instance's generated report JSON and documentation are authoritative.

## Common context

Current report templates expose these common top-level values:

- Report: `title`, `report_date`, `complete`, `archived`, `delivered`, `extra_fields`.
- Related records: `project`, `client`, `recipient`, `contacts`, `team`, `objectives`, `targets`, `scope`, `findings`, `observations`, `evidence`, `logs`, and `infrastructure`.
- Supporting data: `company`, `severities`, `totals`, `tools`, `docx_template`, `pptx_template`, and optionally `bloodhound`.

Useful project values include `project.type`, `project.codename`, `project.start_date`, `project.end_date`, and the component values `start_month`, `start_day`, `start_year`, `end_month`, `end_day`, and `end_year`. Dates rendered through `start_date` and `end_date` follow server configuration; use component values for conditional formats.

Never invent a property from a label in the source document. When a mapping is not listed here, inspect generated report JSON from the target instance if the user has supplied it, consult the target version's documentation, or leave the region unresolved.

## Repeated people and report records

Use these top-level collections before proposing extra fields for repeated tables or lists:

- `contacts`: project-scoped client contacts. Portable fields include `name`, `job_title`, `email`, `phone`, `timezone`, `description`, and `primary`.
- `team`: assigned project team members. Portable fields include `name`, `role`, `email`, `start_date`, `end_date`, `phone`, `timezone`, and `description`.
- `objectives`: project objectives, including `objective`, `priority`, `status`, `description`, `description_rt`, `result`, and `result_rt`.
- `observations`: report observations, including `title`, `description`, `description_rt`, `tags`, and `extra_fields`.
- `findings`: report findings, including `title`, `severity`, `description`, `description_rt`, `impact_rt`, `mitigation_rt`, `replication_steps_rt`, `references_rt`, `tags`, and `extra_fields`.

The top-level `contacts` list is scoped to the project; `client.contacts` may include client contacts unrelated to the assessment. The top-level `recipient` is the primary project contact when one is designated.

## Plain and rich-text values

Use ordinary expressions for inline/plain values:

```jinja2
{{ client.name }}
{{ project.type }}
{{ finding.title }}
```

Ghostwriter creates rich-text renderings for HTML-backed fields. In a DOCX template, place a `p`-prefixed expression alone in the paragraph it replaces:

```jinja2
{{p finding.description_rt}}
{{p finding.impact_rt}}
{{p finding.mitigation_rt}}
{{p extra_fields.executive_summary}}
```

Common finding rich-text properties include `affected_entities_rt`, `description_rt`, `impact_rt`, `mitigation_rt`, `recommendation_rt`, `replication_steps_rt`, `host_detection_techniques_rt`, `network_detection_techniques_rt`, and `references_rt`. Project/client descriptions and configured rich-text extra fields are also rendered for paragraph insertion.

## Structural tags

Use the element-specific docxtpl prefixes when the tag controls whole Word elements. The prefixed tag replaces its containing element and must not share that element with other text:

```jinja2
{%p for finding in findings %}
{{ finding.title }}
{{p finding.description_rt}}
{%p endfor %}
```

Use `{%tr ... %}` to repeat or conditionally include table rows and `{%p ... %}` for paragraphs/list items. Keep each structural tag in its own corresponding paragraph or table row. Use ordinary `{% ... %}` for inline conditional text that should remain within one paragraph.

## Current custom filters

Frequently useful Ghostwriter filters include `filter_severity`, `filter_type`, `filter_tags`, `strip_html`, `compromised`, `add_days`, `format_datetime`, `to_datetime`, `business_days`, `get_item`, `regex_search`, and `replace_blanks`. Availability varies by Ghostwriter version; do not introduce one without verifying it in the target documentation or linter.
