"""Behavioral checks for the review-template skill and offline linter."""

import json
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "review-template"
SKILL = SKILL_DIR / "SKILL.md"
LINTER = SKILL_DIR / "scripts" / "lint_template.py"
EXACT_LINTER = SKILL_DIR / "scripts" / "run_ghostwriter_lint.py"
PARITY_REFERENCE = SKILL_DIR / "references" / "ghostwriter-linting.md"
STYLE_REFERENCE = SKILL_DIR / "references" / "style-guide-review.md"

LINTER_SPEC = importlib.util.spec_from_file_location("review_template_linter", LINTER)
LINTER_MODULE = importlib.util.module_from_spec(LINTER_SPEC)
sys.modules[LINTER_SPEC.name] = LINTER_MODULE
LINTER_SPEC.loader.exec_module(LINTER_MODULE)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def styles_xml(include_table_grid=True):
    styles = [
        ("Bullet List", "paragraph"),
        ("Number List", "paragraph"),
        ("CodeBlock", "paragraph"),
        ("CodeInline", "character"),
        ("Caption", "paragraph"),
        ("List Paragraph", "paragraph"),
        ("Blockquote", "paragraph"),
        ("footnote text", "paragraph"),
        ("footnote reference", "character"),
    ]
    styles.extend((f"Heading {level}", "paragraph") for level in range(1, 7))
    if include_table_grid:
        styles.append(("Table Grid", "table"))
    elements = "".join(
        f'<w:style w:type="{style_type}" w:styleId="S{index}">'
        f'<w:name w:val="{name}"/></w:style>'
        for index, (name, style_type) in enumerate(styles)
    )
    return f'<w:styles xmlns:w="{W_NS}">{elements}</w:styles>'


def write_docx(
    path,
    body="{{ client.name }}",
    *,
    include_table_grid=True,
    settings=None,
    extra_relationship=None,
    raw_body=False,
):
    content_types = """<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
      <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
      <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
    </Types>"""
    document_body = body if raw_body else f"<w:p><w:r><w:t>{body}</w:t></w:r></w:p>"
    document = f'<w:document xmlns:w="{W_NS}"><w:body>{document_body}</w:body></w:document>'
    relationships = (
        f'<Relationships xmlns="{REL_NS}">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        f"{extra_relationship or ''}</Relationships>"
    )
    with ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("word/document.xml", document)
        archive.writestr("word/styles.xml", styles_xml(include_table_grid))
        archive.writestr("word/_rels/document.xml.rels", relationships)
        if settings:
            archive.writestr("word/settings.xml", settings)


def run_linter(path, *args, env=None):
    completed = subprocess.run(
        [sys.executable, str(LINTER), str(path), *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    return completed, json.loads(completed.stdout)


class ReviewTemplateSkillTests(unittest.TestCase):
    def test_skill_is_discriminating_and_read_only(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("name: review-template", text)
        self.assertIn("not for editing, uploading, or activating", text)
        self.assertIn("No local Ghostwriter checkout is required", text)
        self.assertIn("offline static parity", text)
        self.assertIn("Style-guide matrix", text)
        self.assertIn("Do not claim that a template is production-ready", text)
        self.assertIn("run_ghostwriter_lint.py", text)
        self.assertIn("https://<host>/v1/graphql", text)
        self.assertIn("Authorization: Bearer <token>", text)
        self.assertIn("project-read service token", text)

    def test_exact_lint_wrapper_advertises_read_only_controls(self):
        text = EXACT_LINTER.read_text(encoding="utf-8")
        self.assertIn("RejectDatabaseWrites", text)
        self.assertIn("database_writes_blocked", text)
        completed = subprocess.run(
            [sys.executable, str(EXACT_LINTER), "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("without", completed.stdout)
        self.assertIn("uploading it", completed.stdout)

    def test_references_capture_current_ghostwriter_behavior(self):
        parity = PARITY_REFERENCE.read_text(encoding="utf-8")
        style = STYLE_REFERENCE.read_text(encoding="utf-8")
        self.assertIn("v7.2.6-2-g446ba7fe", parity)
        self.assertIn("Table Grid", parity)
        self.assertIn("representative lint data", parity)
        self.assertIn("one or more ordinary slides", parity)
        self.assertIn("requirements matrix", style)
        self.assertIn("not testable", style)

    def test_clean_docx_passes_static_parity(self):
        with tempfile.TemporaryDirectory() as temporary:
            template = Path(temporary) / "clean.docx"
            write_docx(template)
            completed, result = run_linter(template, "--fail-on", "error")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(result["ghostwriter_parity"]["status"], "success")
            self.assertEqual(result["overall_status"], "success")

    def test_missing_required_style_and_unknown_filter_fail_parity(self):
        with tempfile.TemporaryDirectory() as temporary:
            template = Path(temporary) / "bad.docx"
            write_docx(
                template,
                "{{ findings | made_up_filter }}",
                include_table_grid=False,
            )
            completed, result = run_linter(template, "--fail-on", "error")
            self.assertEqual(completed.returncode, 1)
            codes = {
                issue["code"] for issue in result["ghostwriter_parity"]["issues"]
            }
            self.assertIn("GW-STYLE-TABLE-GRID-MISSING", codes)
            self.assertIn("GW-JINJA-FILTER-UNKNOWN", codes)

    def test_duplicate_structural_tag_is_a_compatibility_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            template = Path(temporary) / "duplicate.docx"
            write_docx(template, "{%p if client %}{%p endif %}")
            completed, result = run_linter(template, "--fail-on", "error")
            self.assertEqual(completed.returncode, 1)
            codes = {issue["code"] for issue in result["compatibility"]["issues"]}
            self.assertIn("DOCX-STRUCTURAL-TAG-DUPLICATE", codes)

    def test_docxtpl_wrapped_structural_tags_are_not_false_jinja_errors(self):
        with tempfile.TemporaryDirectory() as temporary:
            template = Path(temporary) / "wrapped.docx"
            write_docx(template, "{{%p if client %}}Visible{{%p endif %}}")
            completed, result = run_linter(template, "--fail-on", "error")
            codes = {
                issue["code"] for issue in result["ghostwriter_parity"]["issues"]
            }
            self.assertNotIn("GW-JINJA-SYNTAX", codes)

    def test_external_dependency_and_update_fields_are_reported_separately(self):
        with tempfile.TemporaryDirectory() as temporary:
            template = Path(temporary) / "linked.docx"
            write_docx(
                template,
                settings=(
                    f'<w:settings xmlns:w="{W_NS}"><w:updateFields w:val="true"/>'
                    "</w:settings>"
                ),
                extra_relationship=(
                    '<Relationship Id="rId9" '
                    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/attachedTemplate" '
                    'Target="https://example.invalid/template.dotx" TargetMode="External"/>'
                ),
            )
            completed, result = run_linter(template, "--fail-on", "never")
            self.assertEqual(completed.returncode, 0)
            codes = {issue["code"] for issue in result["compatibility"]["issues"]}
            self.assertIn("PKG-EXTERNAL-DEPENDENCY", codes)
            self.assertIn("DOCX-UPDATE-FIELDS-ON-OPEN", codes)
            self.assertEqual(result["ghostwriter_parity"]["status"], "success")

    def test_reference_findings_identify_cached_results_and_toc_entries(self):
        with tempfile.TemporaryDirectory() as temporary:
            template = Path(temporary) / "references.docx"
            write_docx(
                template,
                f'''<w:p><w:r><w:t>Compromised Hosts</w:t></w:r>
                <w:r><w:fldChar w:fldCharType="begin"/></w:r>
                <w:r><w:instrText> PAGEREF _TocMissing \\h </w:instrText></w:r>
                <w:r><w:fldChar w:fldCharType="separate"/></w:r>
                <w:r><w:t>8</w:t></w:r>
                <w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>
                <w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r>
                <w:r><w:instrText> REF _RefMissing \\h </w:instrText></w:r>
                <w:r><w:fldChar w:fldCharType="separate"/></w:r>
                <w:r><w:t>Attack Path Narrative</w:t></w:r>
                <w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>''',
                raw_body=True,
            )
            completed, result = run_linter(template, "--fail-on", "never")
            self.assertEqual(completed.returncode, 0)
            issues = {issue["code"]: issue for issue in result["compatibility"]["issues"]}
            self.assertEqual(issues["DOCX-TOC-SOURCE-TARGETS-UNRESOLVED"]["severity"], "info")
            self.assertIn("Compromised Hosts (cached page 8)", issues["DOCX-TOC-SOURCE-TARGETS-UNRESOLVED"]["message"])
            self.assertIn("_RefMissing (cached result: Attack Path Narrative)", issues["DOCX-BOOKMARK-TARGET-MISSING"]["message"])

    def test_remote_extra_field_spec_validates_fields_without_leaking_token(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, size):
                return json.dumps(
                    {
                        "data": {
                            "getExtraFieldSpec": {
                                "extraFieldSpec": json.dumps(
                                    {
                                        "known": {
                                            "internalName": "known",
                                            "type": "string",
                                            "default": "not included in the review",
                                        }
                                    }
                                )
                            }
                        }
                    }
                ).encode("utf-8")

        requests = []

        class FakeOpener:
            def open(self, request, timeout):
                requests.append(request)
                return FakeResponse()

        with tempfile.TemporaryDirectory() as temporary:
            template = Path(temporary) / "remote-extra-fields.docx"
            write_docx(
                template,
                "{{ extra_fields.known }} {{ extra_fields.missing }}",
            )
            token = "review-template-test-token"
            with patch.object(LINTER_MODULE, "build_opener", return_value=FakeOpener()):
                spec, failure = LINTER_MODULE.fetch_remote_extra_field_spec(
                    "https://ghostwriter.example/v1/graphql", token, "report", 1
                )
            self.assertIsNone(failure)
            self.assertEqual(spec, {"known": "string"})
            review = LINTER_MODULE.Review(template, "docx")
            LINTER_MODULE.check_extra_field_references(
                review,
                {"word/document.xml": "{{ extra_fields.known }} {{ extra_fields.missing }}"},
                "docx",
                {"report": spec},
            )
            result = review.result()
            codes = {issue["code"] for issue in result["ghostwriter_parity"]["issues"]}
            self.assertIn("GW-EXTRA-FIELD-UNDEFINED", codes)
            self.assertNotIn(token, json.dumps(result))
            self.assertEqual(len(requests), 1)
            self.assertEqual(requests[0].get_header("Authorization"), f"Bearer {token}")
            self.assertEqual(
                json.loads(requests[0].data)["variables"],
                {"model": "report"},
            )
            self.assertIn(
                "getExtraFieldSpec(model: $model) {\n    extraFieldSpec\n",
                json.loads(requests[0].data)["query"],
            )

    def test_pptx_with_an_ordinary_slide_matches_ghostwriter_warning(self):
        with tempfile.TemporaryDirectory() as temporary:
            template = Path(temporary) / "slides.pptx"
            with ZipFile(template, "w") as archive:
                archive.writestr(
                    "[Content_Types].xml",
                    """<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
                    <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
                    </Types>""",
                )
                archive.writestr(
                    "ppt/presentation.xml",
                    '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"/>',
                )
                archive.writestr(
                    "ppt/slides/slide1.xml",
                    '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"/>',
                )
            completed, result = run_linter(template, "--fail-on", "never")
            self.assertEqual(completed.returncode, 0)
            codes = {
                issue["code"] for issue in result["ghostwriter_parity"]["issues"]
            }
            self.assertIn("GW-PPTX-NOT-EMPTY", codes)
            self.assertEqual(result["ghostwriter_parity"]["status"], "warning")


if __name__ == "__main__":
    unittest.main()
