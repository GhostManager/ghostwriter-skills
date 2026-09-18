# Create-template first-check fixture

This fixture is a safe, deliberately small conversion exercise. It contains no customer data, endpoint, token, or live
Ghostwriter dependency.

## Synthetic source document

Create a one-page DOCX with these two paragraphs:

1. `Executive Summary`, using Heading 1 with a page break before it.
2. `Assessment results are summarized here.`, using the unmodified `Normal` style. The body must be black, non-italic, and free of direct run color or italic formatting.

The fixture generator creates this exact source without overwriting an existing file:

```sh
python3 examples/generate_source_docx.py synthetic-source.docx
python3 scripts/replace_docx_text_spans.py synthetic-source.docx converted-template.docx \
  --old 'Assessment results are summarized here.' \
  --new '{{p extra_fields.executive_summary}}' \
  --clear-replacement-run-formatting
```

## Requested conversion

In offline mode, map only the body paragraph to this Ghostwriter expression:

```jinja2
{{p extra_fields.executive_summary}}
```

## Expected evidence

- The converted DOCX retains the Heading 1 text, its heading style, and its page-break behavior.
- The body paragraph contains exactly the shown Jinja expression and has no direct character formatting of its own; incoming Ghostwriter rich text controls its appearance while the paragraph's Normal style and layout remain intact.
- The conversion report describes `executive_summary` as a **proposed** report-level rich-text field, rather than an instance-discovered field.
- The original source remains untouched; no Ghostwriter upload, activation, or GraphQL request occurs.

## What this does not establish

It does not test tables, headers, footnotes, loops, existing Jinja, TOC repair, or a connected extra-field lookup.
Those require an appropriately representative source document and the main skill's full verification workflow.
