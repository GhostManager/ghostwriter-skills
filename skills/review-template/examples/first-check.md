# Review-template first-check fixture

This fixture is a local, synthetic validation target. Generate a DOCX with these two deliberate defects:

1. A text run containing `{{ findings | made_up_filter }}`.
2. No table style named `Table Grid` in `word/styles.xml`.

Create it without overwriting an existing file, then run the bundled offline checker:

```sh
python3 examples/generate_invalid_template.py synthetic-invalid.docx
python3 scripts/lint_template.py synthetic-invalid.docx --fail-on error --format json
```

## Expected result

The command exits nonzero and its JSON report includes these codes in `ghostwriter_parity.issues`:

```json
[
  "GW-JINJA-FILTER-UNKNOWN",
  "GW-STYLE-TABLE-GRID-MISSING"
]
```

The exact issue ordering and any additional package findings can differ. The check is read-only: it does not upload, activate, or alter `synthetic-invalid.docx`.

## What this does not establish

It does not prove an arbitrary template will render correctly in a target Ghostwriter version, validate instance-specific filters, or replace visual inspection.
