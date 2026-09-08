# Style-guide rules in Ghostwriter templates

Read this reference when a user provides a style guide or a specific reusable formatting request. Apply only rules that have a clear scope, a reliable data source in Ghostwriter's report context, and representative examples that can be rendered for review.

The project date components and Jinja conventions here were verified against Ghostwriter `v7.2.6-2-g446ba7fe`, using the bundled Word-template documentation and project serializer.

## Decision boundary

Do not turn every style preference into Jinja. Static typography, colors, headings, margins, and table styles belong in Word styles. Use Jinja only where output changes with report data, such as optional sections, labels based on assessment type, or date-range presentation.

Before inserting logic, capture the rule as: input field(s), condition(s), exact expected output(s), fallback behavior, and target template location. Use the target Ghostwriter version's template linter or a rendered sample to verify the rule. A guide that says “use professional dates” is too vague; request a rule or preserve the existing presentation.

## Project date-range pattern

Current Ghostwriter report context exposes localized project dates and reliable components:

- `project.start_month`, `project.start_day`, `project.start_year`
- `project.end_month`, `project.end_day`, `project.end_year`

Use the component values for branch comparisons. Do not parse `project.start_date` or `project.end_date`, because they are already localized display strings and their format is configurable per server.

For a guide requiring these English-style outputs:

- Same month/year: `June 20-22, 2026`
- Different month, same year: `June 20 - July 4, 2026`
- Different year: `December 25, 2026 - January 14, 2027`

place this complete inline expression in one uninterrupted Word run inside an ordinary paragraph (not a `{{p ...}}` rich-text paragraph):

```jinja2
{% if project.start_year == project.end_year and project.start_month == project.end_month and project.start_day == project.end_day %}{{ project.start_month }} {{ project.start_day }}, {{ project.start_year }}{% elif project.start_year == project.end_year and project.start_month == project.end_month %}{{ project.start_month }} {{ project.start_day }}-{{ project.end_day }}, {{ project.end_year }}{% elif project.start_year == project.end_year %}{{ project.start_month }} {{ project.start_day }} - {{ project.end_month }} {{ project.end_day }}, {{ project.end_year }}{% else %}{{ project.start_month }} {{ project.start_day }}, {{ project.start_year }} - {{ project.end_month }} {{ project.end_day }}, {{ project.end_year }}{% endif %}
```

The first branch deliberately handles a one-day assessment. If the style guide uses a different dash, capitalization, locale, or single-day convention, alter the literal punctuation/text and document the change. Confirm that the target instance's locale produces the required month names; otherwise the style requirement needs an agreed locale-aware alternative.

After insertion, inspect the paragraph's OOXML and confirm that no individual Jinja tag is split across multiple `w:r` runs. Word may create hidden run boundaries during editing even when the paragraph looks continuous. Treat a split tag as a conversion defect and normalize it before linting.

## Verification cases

Render or lint a temporary copy with at least these values and compare the entire output string exactly:

| Start | End | Expected output |
| --- | --- | --- |
| 2026-06-20 | 2026-06-22 | `June 20-22, 2026` |
| 2026-06-20 | 2026-07-04 | `June 20 - July 4, 2026` |
| 2026-12-25 | 2027-01-14 | `December 25, 2026 - January 14, 2027` |
| 2026-06-20 | 2026-06-20 | `June 20, 2026` |

Do not infer that every date occurrence should use this pattern. Apply it only to locations covered by the style guide or user request, such as a report cover's assessment period.
