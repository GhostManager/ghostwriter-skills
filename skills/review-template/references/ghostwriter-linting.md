# Ghostwriter lint parity

Use this reference to interpret the offline review and to compare it with a target Ghostwriter checkout. The bundled baseline was verified against Ghostwriter `v7.2.6-2-g446ba7fe` (`446ba7fe`). A target checkout is authoritative when it differs.

## Source locations

Inspect these files in the target checkout:

- `ghostwriter/reporting/models.py` — document-type dispatch and status calculation.
- `ghostwriter/modules/reportwriter/base/docx.py` — Word linter and required/recommended styles.
- `ghostwriter/modules/reportwriter/base/pptx.py` — PowerPoint linter.
- `ghostwriter/modules/reportwriter/report/base.py` — report lint data and rich-text mapping.
- `ghostwriter/modules/reportwriter/project/base.py` — project lint data and rich-text mapping.
- `ghostwriter/modules/linting_utils.py` — representative lint context.
- `ghostwriter/modules/reportwriter/__init__.py` — sandbox and registered filters.
- `ghostwriter/modules/reportwriter/base/__init__.py` — user-facing error mapping.
- `DOCS/features/reporting/report-templates/report-template-linting.mdx` — documented behavior.
- `DOCS/features/reporting/report-templates/word-template-styles.mdx` — documented style intent.
- `DOCS/features/reporting/report-templates/word-template-variables.mdx` — variables, filters, and docxtpl tags.

Do not assume the public documentation and current code are identical. Record differences that affect the result.

## Status calculation

`ReportTemplate.lint()` produces:

- `failed` when the errors list is non-empty;
- `warning` when errors are empty and warnings are non-empty; and
- `success` when both lists are empty.

The interface and documentation also discuss `error` for an unexpected linter failure or stored state. Keep the application's returned label verbatim when an exact lint was run. The offline checker uses `failed`, `warning`, and `success`.

## DOCX linter behavior

`ExportDocxBase.lint()` performs these steps:

1. Confirm the template path exists.
2. Build representative lint data for a report or project, including configured extra fields from the database.
3. Construct the DOCX exporter and load the file through `DocxTemplate`.
4. Ask `docxtpl`/Jinja for undeclared template variables. A top-level variable absent from the lint data becomes a warning.
5. Inspect the document's current styles.
6. Require `Table Grid`; absence is an error.
7. Warn when a recommended style is absent.
8. Warn when selected styles have the wrong Word style type.
9. Run the exporter with representative data. This exercises Jinja parsing/rendering, rich-text conversion, evidence handling, document properties, image replacement, and package saving.
10. Warn for undefined variables observed by the debug undefined object during rendering.

Any mapped template/render exception becomes `Linting failed: ...` and is an error. An unexpected exception becomes `Template rendering failed unexpectedly`.

### Recommended styles

The code checks these styles by name:

| Style | Expected type | Linter impact |
|---|---|---|
| `Bullet List` | Paragraph | Warning if missing or mistyped |
| `Number List` | Paragraph | Warning if missing or mistyped |
| `CodeBlock` | Paragraph | Warning if missing or mistyped |
| `CodeInline` | Character | Warning if missing or mistyped |
| `Caption` | Paragraph | Warning if missing |
| `List Paragraph` | Paragraph | Warning if missing or mistyped |
| `Blockquote` | Paragraph | Warning if missing |
| `footnote text` | Paragraph | Warning if missing or mistyped |
| `footnote reference` | Character | Warning if missing or mistyped |
| `Heading 1` through `Heading 6` | Paragraph | Warning if missing |
| `Table Grid` | Table | Error if missing; current code checks presence, not type |

The code performs style checks before `create_styles()` runs. The exporter can create `CodeBlock`, `CodeInline`, `Caption`, and `Blockquote` later, so their absence may produce a linter warning even when the representative render succeeds.

The current code checks `footnote text` for a Paragraph style but its warning text says “not a character style.” Treat Paragraph as the implemented requirement and note this message discrepancy if it appears.

If the template record has a configured `p_style`, the linter warns when that style is absent.

## Report versus project context

Report DOCX lint data uses the full `LINTER_CONTEXT` and adds configured extra fields for Report, Project, Client, Finding, OplogEntry, Domain, StaticServer, and Observation objects.

Project DOCX lint data uses the project-oriented subset: `project`, `client`, `contacts`, `team`, `objectives`, `targets`, `scope`, `deconflictions`, `whitecards`, `infrastructure`, `logs`, `company`, `report_date`, `tools`, `recipient`, and top-level `extra_fields`. It adds configured Report, Project, Client, OplogEntry, Domain, and StaticServer extra fields.

The offline checker can validate top-level variable names from a supplied context, but it cannot prove that instance-specific nested extra-field keys exist unless their specifications or representative JSON are supplied.

## Jinja environment

Current Ghostwriter uses an immutable sandboxed environment with autoescaping. It blocks access through Jinja environment/template/extension objects, Python modules, `docx`/`docxtpl` objects, private capability objects, and unregistered callables.

Current registered custom filters are discovered from the target checkout when possible. The bundled baseline includes:

- `filter_severity`
- `filter_type`
- `strip_html`
- `compromised`
- `add_days`
- `format_datetime`
- `to_datetime`
- `business_days`
- `get_item`
- `regex_search`
- `filter_tags`
- `replace_blanks`
- `filter_bhe_findings_by_domain`
- `translate_domain_sid`

Unknown filters and unsupported statements can make parsing fail. Never silence an unknown filter merely to make the static checker pass.

## PPTX linter behavior

`ExportBasePptx.lint()` currently:

1. Confirms the file path exists.
2. Opens it as a PowerPoint presentation.
3. Warns when it contains one or more ordinary slides.

It does not currently inspect layout order, placeholder types, theme quality, or generated-slide overflow. Those are compatibility checks based on Ghostwriter's PowerPoint documentation, not linter-parity failures.

## What offline parity cannot prove

A static parser and `docxtpl` structural render do not reproduce:

- database-backed extra-field specifications;
- organization-level report and company configuration;
- Ghostwriter's exact sandbox implementation;
- rich-text HTML conversion;
- evidence lookup and image/text insertion;
- every filter's runtime type/value behavior;
- the final output generated from a real report; or
- Word/PowerPoint's native rendering and repair behavior.

Label these omissions. If a configured local Ghostwriter environment is available, use `scripts/run_ghostwriter_lint.py` to exercise the target exporter/linter against the local file without saving a `ReportTemplate` record. The wrapper blocks database writes while allowing the linter to read instance configuration and extra-field specifications. Do not create, upload, or mutate a template-library record as part of this skill.
