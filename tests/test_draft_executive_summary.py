"""Structural safety checks for the draft-executive-summary skill."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "draft-executive-summary" / "SKILL.md"
REFERENCE = ROOT / "skills" / "draft-executive-summary" / "references" / "ghostwriter-graphql.md"


class DraftExecutiveSummarySkillTests(unittest.TestCase):
    def setUp(self):
        self.skill = SKILL.read_text(encoding="utf-8")
        self.reference = REFERENCE.read_text(encoding="utf-8")

    def test_has_a_discriminating_skill_definition(self):
        self.assertIn("name: draft-executive-summary", self.skill)
        self.assertIn("project-read GraphQL token", self.skill)
        self.assertIn("not for editing Ghostwriter data", self.skill)

    def test_supports_offline_and_connected_read_only_inputs(self):
        self.assertIn("connected mode** by default", self.skill)
        self.assertIn("offline snapshot mode", self.skill)
        self.assertIn("complete decoded report-data JSON export", self.skill)
        self.assertIn("Do not make a network request", self.skill)
        for requirement in ("project ID", "GraphQL endpoint", "service token"):
            self.assertIn(requirement, self.skill)
        self.assertIn("https://<host>/v1/graphql", self.skill)
        self.assertIn("Authorization: Bearer <token>", self.skill)
        self.assertIn("internal Action-handler", self.skill)
        self.assertIn("never saves, updates, creates, or delivers", self.skill)

    def test_handles_report_and_extra_field_ambiguity(self):
        self.assertIn("ask the user which report", self.skill)
        self.assertIn("If multiple fields are plausible", self.skill)
        self.assertIn("never guess", self.skill)

    def test_documents_the_read_only_export_action(self):
        self.assertIn("generateReport", self.skill)
        self.assertIn("read-only export", self.skill)
        self.assertIn("getExtraFieldSpec", self.reference)
        self.assertIn("data.generateReport.reportData", self.reference)
        self.assertIn("not offline discovery", self.reference)
        self.assertIn("/api/generateReport", self.reference)
        self.assertIn("operationName", self.reference)


if __name__ == "__main__":
    unittest.main()
