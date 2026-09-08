"""Structural safety checks for the report-readiness skill."""

from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "report-readiness" / "SKILL.md"
REFERENCE = ROOT / "skills" / "report-readiness" / "references" / "readiness-checks.md"
GRADER = ROOT / "skills" / "report-readiness" / "scripts" / "grade_readiness.py"


class ReportReadinessSkillTests(unittest.TestCase):
    def setUp(self):
        self.skill = SKILL.read_text(encoding="utf-8")
        self.reference = REFERENCE.read_text(encoding="utf-8")

    def test_has_a_discriminating_skill_definition(self):
        self.assertIn("name: report-readiness", self.skill)
        self.assertIn("project-read GraphQL token", self.skill)
        self.assertIn("not for editing data", self.skill)

    def test_supports_offline_and_connected_read_only_inputs(self):
        self.assertIn("offline mode", self.skill)
        self.assertIn("decoded report-data JSON export", self.skill)
        self.assertIn("do not make a network request", self.skill)
        for requirement in ("project ID", "GraphQL endpoint", "service token"):
            self.assertIn(requirement, self.skill)
        self.assertIn("https://<host>/v1/graphql", self.skill)
        self.assertIn("Authorization: Bearer <token>", self.skill)
        self.assertIn("internal Action-handler", self.skill)
        self.assertIn("never changes", self.skill)
        self.assertIn("do not invoke any other GraphQL mutation", self.skill)
        self.assertIn("data.generateReport.reportData", self.reference)
        self.assertIn("/api/generateReport", self.reference)
        self.assertIn("operationName", self.reference)

    def test_does_not_hard_code_objective_statuses(self):
        self.assertIn("administrator-defined", self.skill)
        self.assertIn("do not assume labels are universal", self.skill)
        self.assertIn("Do not infer terminal status", self.reference)

    def test_declares_template_and_passive_voice_limits(self):
        self.assertIn("not assessed", self.skill)
        self.assertIn("report-wide and project-wide checks as not applicable", self.skill)
        self.assertIn("Do not run passive-voice checks", self.skill)
        self.assertNotIn("getReportTemplateDependencies", self.skill)

    def test_uses_the_report_setting_as_the_bloodhound_intent_gate(self):
        self.assertIn("`include_bloodhound_data` setting as the intent gate", self.reference)
        self.assertIn("key even when inclusion is disabled", self.reference)
        self.assertIn("mark the check not applicable", self.reference)

    def test_grade_rules_are_mutually_exclusive(self):
        scenarios = (
            (0, 0, (), "A"),
            (0, 1, (), "B"),
            (0, 20, (), "B"),
            (1, 0, (), "C"),
            (2, 4, (), "C"),
            (0, 0, ("--essential-unassessed",), "C"),
            (3, 0, (), "D"),
            (0, 0, ("--fundamental-failure",), "D"),
        )
        for blockers, warnings, flags, expected in scenarios:
            with self.subTest(blockers=blockers, warnings=warnings, flags=flags):
                result = subprocess.run(
                    [
                        sys.executable,
                        str(GRADER),
                        "--blockers",
                        str(blockers),
                        "--warnings",
                        str(warnings),
                        *flags,
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), expected)

    def test_grader_rejects_negative_counts(self):
        result = subprocess.run(
            [sys.executable, str(GRADER), "--blockers", "-1", "--warnings", "0"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
