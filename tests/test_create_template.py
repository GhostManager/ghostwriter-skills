"""Structural and helper-behavior checks for the create-template skill."""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "create-template" / "SKILL.md"
REFERENCE = ROOT / "skills" / "create-template" / "references" / "ghostwriter-graphql.md"
STYLE_RULES = ROOT / "skills" / "create-template" / "references" / "style-rules.md"
DOCUMENT_STRUCTURE = ROOT / "skills" / "create-template" / "references" / "document-structure.md"
STRUCTURED_SECTIONS = ROOT / "skills" / "create-template" / "references" / "structured-sections.md"
TEMPLATE_CONTEXT = ROOT / "skills" / "create-template" / "references" / "template-context.md"
HELPER = ROOT / "skills" / "create-template" / "scripts" / "replace_docx_text_spans.py"
EXTERNAL_AUDITOR = (
    ROOT / "skills" / "create-template" / "scripts" / "audit_docx_external_references.py"
)


class CreateTemplateSkillTests(unittest.TestCase):
    def setUp(self):
        self.skill = SKILL.read_text(encoding="utf-8")
        self.reference = REFERENCE.read_text(encoding="utf-8")
        self.style_rules = STYLE_RULES.read_text(encoding="utf-8")
        self.document_structure = DOCUMENT_STRUCTURE.read_text(encoding="utf-8")
        self.structured_sections = STRUCTURED_SECTIONS.read_text(encoding="utf-8")
        self.template_context = TEMPLATE_CONTEXT.read_text(encoding="utf-8")

    def test_has_a_discriminating_portable_definition(self):
        self.assertIn("name: create-template", self.skill)
        self.assertIn("offline by default", self.skill)
        self.assertIn("not for uploading or activating", self.skill)

    def test_keeps_connected_mode_read_only_and_optional(self):
        self.assertIn("connected discovery mode", self.skill)
        self.assertIn("never required", self.skill)
        self.assertIn("never uploads, activates, modifies, or deletes", self.skill)
        self.assertIn("getExtraFieldSpec", self.reference)
        self.assertIn("Do not call a mutation", self.reference)
        self.assertIn("https://<host>/v1/graphql", self.skill)
        self.assertIn("Authorization: Bearer <token>", self.skill)
        self.assertIn("/api/getExtraFieldSpec", self.reference)
        self.assertIn("project-read service token", self.skill)

    def test_requires_ambiguity_review_and_docx_visual_qa(self):
        self.assertIn("Do not silently convert ambiguous prose", self.skill)
        self.assertIn("Jinja expressions are often split across Word runs/text nodes", self.skill)
        self.assertIn("Render the output before delivery", self.skill)
        self.assertIn("conversion report", self.skill)

    def test_preserves_pagination_toc_and_inline_formatting(self):
        self.assertIn("document-structure reference", self.skill)
        self.assertIn("page break before each Heading 1", self.document_structure)
        self.assertIn("native Word TOC field", self.document_structure)
        self.assertIn("new-page boundary both before it and after", self.document_structure)
        self.assertIn("Do not add `w:updateFields` by default", self.document_structure)
        self.assertIn("page-boundary ledger", self.document_structure)
        self.assertIn("first matched run's formatting", self.document_structure)
        self.assertIn("paragraph.clear()", self.skill)

    def test_prefers_structured_context_over_extra_fields(self):
        for collection in ("`contacts`", "`team`", "`observations`", "`findings`"):
            self.assertIn(collection, self.skill)
            self.assertIn(collection, self.template_context)
        self.assertIn("filter_severity", self.skill)
        self.assertIn("filter_severity([\"Critical\", \"High\", \"Medium\"])", self.structured_sections)
        self.assertIn("{%tr for contact in contacts %}", self.structured_sections)
        self.assertIn("{%tr for member in team %}", self.structured_sections)
        self.assertIn("{%p for observation in observations %}", self.structured_sections)
        self.assertIn("first-sentence expression only when", self.structured_sections)
        self.assertIn("page-break paragraph", self.structured_sections)
        self.assertIn("before the loop's closing tag", self.structured_sections)
        self.assertIn("Error! Reference source not found.", self.skill)
        self.assertIn("matching `w:bookmarkStart/@w:name`", self.document_structure)

    def test_requires_external_reference_audit_without_conflating_update_fields(self):
        self.assertIn("audit_docx_external_references.py", self.skill)
        self.assertIn("A Word warning is not proof", self.skill)
        self.assertIn("TargetMode=\"External\"", self.document_structure)

        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            internal_only = temporary / "internal-only.docx"
            with zipfile.ZipFile(internal_only, "w") as archive:
                archive.writestr(
                    "word/settings.xml",
                    b'<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                    b'<w:updateFields w:val="true"/></w:settings>',
                )
                archive.writestr(
                    "word/document.xml",
                    b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                    b'<w:body><w:p><w:r><w:instrText>TOC \\o "1-2"</w:instrText></w:r></w:p>'
                    b'</w:body></w:document>',
                )

            internal_result = subprocess.run(
                [sys.executable, str(EXTERNAL_AUDITOR), str(internal_only)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(internal_result.returncode, 0, internal_result.stderr)
            self.assertIn('"has_external_references": false', internal_result.stdout)
            self.assertIn('"update_fields_on_open": true', internal_result.stdout)

            external = temporary / "external.docx"
            with zipfile.ZipFile(external, "w") as archive:
                archive.writestr(
                    "word/document.xml",
                    b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                    b'<w:body><w:p><w:r><w:instrText>INCLUDEPICTURE "https://example.com/a.png"'
                    b'</w:instrText></w:r></w:p></w:body></w:document>',
                )
                archive.writestr(
                    "word/_rels/document.xml.rels",
                    b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                    b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
                    b'Target="https://example.com/a.png" TargetMode="External"/></Relationships>',
                )

            external_result = subprocess.run(
                [
                    sys.executable,
                    str(EXTERNAL_AUDITOR),
                    str(external),
                    "--fail-on-external",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(external_result.returncode, 1, external_result.stderr)
            self.assertIn('"has_external_references": true', external_result.stdout)
            self.assertIn('"type": "INCLUDEPICTURE"', external_result.stdout)

    def test_supports_testable_style_rules_without_parsing_localized_dates(self):
        self.assertIn("style guide", self.skill)
        self.assertIn("representative values", self.skill)
        self.assertIn("project.start_month", self.style_rules)
        self.assertIn("Do not parse `project.start_date`", self.style_rules)
        for expected_output in (
            "June 20-22, 2026",
            "June 20 - July 4, 2026",
            "December 25, 2026 - January 14, 2027",
        ):
            self.assertIn(expected_output, self.style_rules)
        self.assertIn("one uninterrupted Word run", self.style_rules)

    def test_helper_replaces_only_word_text_node_content(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            source = temporary / "source.docx"
            output = temporary / "output.docx"
            document_xml = (
                b'<w:document xmlns:w="urn:test"><w:body>'
                b'<w:r><w:t>{{p extra_fields.exsum}}</w:t></w:r>'
                b'<w:bookmarkStart w:name="extra_fields.exsum"/>'
                b'</w:body></w:document>'
            )
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("word/document.xml", document_xml)
                archive.writestr("[Content_Types].xml", b"<Types />")

            result = subprocess.run(
                [
                    sys.executable,
                    str(HELPER),
                    str(source),
                    str(output),
                    "--old",
                    "extra_fields.exsum",
                    "--new",
                    "extra_fields.executive_summary",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            with zipfile.ZipFile(output) as archive:
                converted = archive.read("word/document.xml")
            self.assertIn(b"{{p extra_fields.executive_summary}}", converted)
            self.assertIn(b'w:name="extra_fields.exsum"', converted)

    def test_helper_refuses_to_overwrite_an_existing_output(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            source = temporary / "source.docx"
            output = temporary / "existing.docx"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr(
                    "word/document.xml",
                    b'<w:document xmlns:w="urn:test"><w:t>old</w:t></w:document>',
                )
            original_output = b"important existing content"
            output.write_bytes(original_output)

            result = subprocess.run(
                [sys.executable, str(HELPER), str(source), str(output), "--old", "old", "--new", "new"],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 2)
            self.assertEqual(output.read_bytes(), original_output)

    def test_helper_replaces_cross_run_text_and_preserves_first_run_formatting(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            source = temporary / "source.docx"
            output = temporary / "output.docx"
            document_xml = (
                b'<w:document xmlns:w="urn:test"><w:body><w:p>'
                b'<w:r><w:rPr><w:b/><w:color w:val="7030A0"/></w:rPr><w:t>Cyber </w:t></w:r>'
                b'<w:r><w:rPr><w:i/></w:rPr><w:t>Partners</w:t></w:r>'
                b'</w:p></w:body></w:document>'
            )
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("word/document.xml", document_xml)

            result = subprocess.run(
                [
                    sys.executable,
                    str(HELPER),
                    str(source),
                    str(output),
                    "--old",
                    "Cyber Partners",
                    "--new",
                    "{{ client.name }}",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            with zipfile.ZipFile(output) as archive:
                converted = archive.read("word/document.xml")
            self.assertIn(b'<w:b/><w:color w:val="7030A0"/>', converted)
            self.assertIn(b'<w:t>{{ client.name }}</w:t>', converted)
            self.assertIn(b'<w:rPr><w:i/></w:rPr><w:t></w:t>', converted)

    def test_helper_escapes_xml_text_and_leaves_no_output_on_no_match(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            source = temporary / "source.docx"
            escaped_output = temporary / "escaped.docx"
            missing_output = temporary / "missing.docx"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr(
                    "word/document.xml",
                    b'<w:document xmlns:w="urn:test"><w:t>old</w:t></w:document>',
                )

            escaped = subprocess.run(
                [
                    sys.executable,
                    str(HELPER),
                    str(source),
                    str(escaped_output),
                    "--old",
                    "old",
                    "--new",
                    "A & B < C",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(escaped.returncode, 0, escaped.stderr)
            with zipfile.ZipFile(escaped_output) as archive:
                xml = archive.read("word/document.xml")
            root = ElementTree.fromstring(xml)
            self.assertEqual("".join(root.itertext()), "A & B < C")

            missing = subprocess.run(
                [
                    sys.executable,
                    str(HELPER),
                    str(source),
                    str(missing_output),
                    "--old",
                    "not-present",
                    "--new",
                    "new",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(missing.returncode, 3)
            self.assertFalse(missing_output.exists())


if __name__ == "__main__":
    unittest.main()
