# Preserving DOCX structure during template conversion

Use these rules when converting a source DOCX so pagination, the table of contents, and inline formatting remain part of the resulting Ghostwriter template.

## Page and section boundaries

Inventory all three boundary mechanisms before editing:

- explicit page breaks: `w:br` with `w:type="page"`;
- paragraph or paragraph-style `w:pageBreakBefore`;
- section properties in `w:sectPr`, including section type, page size, margins, headers, and footers.

Create a page-boundary ledger with one entry per break: mechanism, package part/paragraph locator, preceding semantic block, following semantic block, and the corresponding location in the generated template. Retain source boundaries around cover pages, front matter, tables with their surrounding boilerplate, large Heading 1 sections, findings, and appendices. Replacing or deleting the paragraph immediately before a break must not consume the break accidentally.

When a conversion condenses or newly constructs the body, transfer every source break whose preceding and following semantic blocks remain in the template. A changed content length does not erase an intentional boundary. Start each appendix and major Heading 1 on a new page if the source did. Otherwise, default to a paragraph-level page break before each Heading 1. Do not add another break when an immediately preceding explicit page break or next-page section break already creates the same boundary. Render the result and remove accidental blank pages.

For repeated records, map an item-to-item source boundary into the loop body. If each source finding starts on a new page, place an explicit page-break paragraph after the final content paragraph and before `{%p endfor %}`. Place any break between a summary table/boilerplate and the first item outside the loop. This gives the first item its own page and repeats the boundary after every rendered item. Account for the loop's trailing break when positioning the following appendix so two adjacent breaks do not create a blank page.

Prefer `pageBreakBefore` on the heading paragraph to an empty paragraph containing a page break. Apply it to individual headings unless the source consistently defines the behavior in the Heading 1 style.

## Native Word table of contents

Search the DOCX XML for a TOC field before modifying front matter. A native TOC may be represented by:

- a complex field using `w:fldChar` begin/separate/end elements with `w:instrText` containing `TOC`; or
- `w:fldSimple` with a TOC instruction.

Preserve the complete field, cached TOC paragraphs, TOC styles, hyperlinks, and bookmarks in their original relative location. A TOC is a bounded block: preserve or create a new-page boundary both before it and after its final cached entry. A next-page section break after the TOC satisfies the latter rule; otherwise use an explicit page break or `pageBreakBefore` on the following section. Keep converted section headings on compatible Heading styles or outline levels.

If the source contains a native TOC but the conversion must rebuild its cached entries, retain the field instruction. Do not add `w:updateFields` by default: Word can respond with the generic warning “fields that may refer to other files” even when the DOCX contains only internal TOC, REF, PAGEREF, SEQ, or PAGE fields. Preserve the source's update-on-open setting unless the user explicitly requests automatic updates and accepts the prompt. Otherwise, keep the cached TOC, explain that it should be refreshed manually in Word with Select All and Update Fields, and verify separately that no external relationship or external-capable field exists. If the source has only a typed or cached-looking list and no TOC field, create a native Word TOC field rather than copying stale page numbers. A conversion is incomplete when a source TOC silently disappears or becomes a manually maintained list.

LibreOffice and headless rendering may show stale cached page numbers even when the field is valid. Record that limitation and structurally verify the TOC field; do not delete the TOC because the renderer does not refresh it.

## Inline replacement formatting

For each inline replacement, identify the source paragraph and the run that visually owns the value. Preserve:

- paragraph style and `w:pPr`, including alignment, spacing, indentation, tabs, and keep/page-break settings;
- source `w:rPr`, including font, size, bold, italic, color, highlighting, capitalization, and language;
- surrounding drawings, text boxes, fields, bookmarks, hyperlinks, and proofing markup.

The replacement expression should live in the text node of the intended formatted run. When a token spans several runs, put the replacement in the first semantically styled run and clear only the consumed text from subsequent runs. Do not reconstruct the whole paragraph with default formatting.

Use `scripts/replace_docx_text_spans.py` for confirmed literal replacements. It preserves the first matched run's formatting even when the source token is split across adjacent Word text nodes within one paragraph. Use a document library only when structural changes are required, and copy the relevant `w:rPr` before replacing the run text.

## Verification

Compare the rendered source and output at every changed page. Explicitly check:

- cover client name, report title, subtitle/classification, and date;
- running headers and footers;
- first page of each Heading 1 and appendix;
- TOC presence, native field structure, indentation, leaders, and page-number alignment;
- no blank page introduced by duplicate boundaries.

Also inspect OOXML to confirm Jinja tags are not split across runs and that TOC/page-break elements remain present.

## External-reference audit

Inspect every package `.rels` part, not only `word/_rels/document.xml.rels`. Flag relationships with `TargetMode="External"` and classify ordinary hyperlinks separately from external templates, images, OLE/package objects, or other content dependencies. Inspect `w:instrText` and `w:fldSimple/@w:instr` for field types capable of reaching outside the document, including `DDE`, `DDEAUTO`, `DATABASE`, `INCLUDEPICTURE`, `INCLUDETEXT`, `LINK`, and `RD`.

Run `scripts/audit_docx_external_references.py` before and after conversion. If the audit is clean but Word still shows an external-file field warning, check `word/settings.xml` for `w:updateFields`; remove a conversion-added setting and leave field refresh manual. Do not claim that the warning proves an external reference without package evidence.

Internal cross-references need a separate integrity check. For every retained `REF` or `PAGEREF` field, parse its bookmark name and verify that a matching `w:bookmarkStart/@w:name` remains in the package. Boilerplate copied from a completed report often contains cross-references to captions or appendices that a condensed template removes. Recreate the target when the relationship is still useful; otherwise replace the field with its intended visible text and preserve the source run formatting. Search the final extracted text and render for “Error! Reference source not found.” before delivery.
