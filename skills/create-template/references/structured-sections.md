# Converting repeated report sections to Ghostwriter Jinja

Use these patterns before proposing extra fields for source tables, bullet lists, repeated summaries, observations, and findings. The source determines the layout and wording; these examples show the portable data paths and structural tags.

## Decision process

1. Identify the semantic record represented by each source row, bullet, card, or detail section.
2. Compare the repeated values with `contacts`, `team`, `objectives`, `observations`, `findings`, and other documented collections.
3. Match source columns and text fragments to documented attributes. Use a loop only when that match is high-confidence.
4. Reuse the source row, list-item, heading, and paragraph formatting for the loop body.
5. Propose an extra field only for content that is genuinely synthesized or unsupported by the documented context.

Place each `{%p ... %}` tag in its own paragraph and each `{%tr ... %}` tag in its own table row. Do not put other text beside a prefixed structural tag.

## Project contacts

The top-level `contacts` collection contains contacts selected for the project. For a source table with Name, Role, and Email columns, use a table-row loop such as:

```jinja2
{%tr for contact in contacts %}
{{ contact.name }}
{% if contact.primary %}Primary{% else %}Secondary{% endif %}
{{ contact.email }}
{%tr endfor %}
```

Available portable fields include `name`, `job_title`, `email`, `phone`, `timezone`, `description`, and `primary`. Prefer `contacts` over `client.contacts` for an assessment-participant table because the former is scoped to the project.

## Assigned assessment team

The top-level `team` collection contains project assignments. For a source table with Name, Role, and Email columns:

```jinja2
{%tr for member in team %}
{{ member.name }}
{{ member.role }}
{{ member.email }}
{%tr endfor %}
```

Other portable assignment fields include `start_date`, `end_date`, `phone`, `timezone`, and `description`.

## Positive observations

The top-level `observations` collection exposes `title`, `description`, and `description_rt`. Use it for both observation summaries and details rather than creating a report extra field.

If the source's Results Overview uses one bullet per observation with a title and a one-sentence description, preserve the source bullet paragraph as the loop body:

```jinja2
{%p for observation in observations %}
{{ observation.title }} – {{ (observation.description|strip_html|regex_search("^[^.!?]*[.!?]")) or (observation.description|strip_html) }}
{%p endfor %}
```

Use `{{p observation.description_rt}}` for a full rich-text observation detail section. Use the first-sentence expression only when comparison with the full observation text shows that the sample summary follows that convention. Otherwise use the full stripped description or leave the summary rule unresolved.

## Findings summaries and severity thresholds

Compare the source summary list or table with every detailed finding and its severity. If the summary consistently includes only a subset of severities, reproduce the observed allowlist with `filter_severity`; do not assume a threshold from one coincidental omission.

For a source that lists Medium and higher findings and formats each bullet as title, severity, and a short description:

```jinja2
{%p for finding in findings|filter_severity(["Critical", "High", "Medium"]) %}
{{ finding.title }} ({{ finding.severity }}) – {{ (finding.description|strip_html|regex_search("^[^.!?]*[.!?]")) or (finding.description|strip_html) }}
{%p endfor %}
```

Preserve the source bullet style on the loop-body paragraph. If the source summary includes all findings, loop over `findings` without a filter. If the sample and available context do not establish the rule, list the candidate interpretations in the conversion report instead of inventing an allowlist.

Detailed finding sections should use the documented rich-text fields, for example `description_rt`, `impact_rt`, `mitigation_rt`, `replication_steps_rt`, and `references_rt`, inside a paragraph loop over `findings`.

When the sample begins each detailed finding on a new page, preserve the break as part of the repeated record. Put a page break between the summary table/related boilerplate and the loop, then put a page-break paragraph after the last finding field and before the loop's closing tag:

```jinja2
{%p for finding in findings %}
{{ finding.title }}
Severity: {{ finding.severity }}
Description
{{p finding.description_rt}}
Impact
{{p finding.impact_rt}}
Mitigation
{{p finding.mitigation_rt}}
Replication Steps
{{p finding.replication_steps_rt}}
<page-break paragraph>
{%p endfor %}
```

The page-break paragraph is ordinary Word content inside the loop, not part of a structural Jinja tag. Because the final item also emits the break, do not add another immediately before the next appendix; retain only one effective boundary.

## Results Overview

Treat a Results Overview as a composition of structured and narrative parts. Objectives, observations, and findings can often be generated from their collections. A free-form account of access, compromise, or business impact may still require an executive-summary or results-overview rich-text field if no documented record supplies it.

Do not replace an entire Results Overview with one extra field when its visible sublists can be generated from structured data. Preserve static lead-in sentences and source list formatting where appropriate, and use extra fields only for the remaining synthesized narrative.
