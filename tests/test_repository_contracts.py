"""Repository-level contracts shared by all distributed skills."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"


class RepositoryContractTests(unittest.TestCase):
    def test_skill_names_match_their_directories(self):
        for skill_file in SKILLS.glob("*/SKILL.md"):
            with self.subTest(skill=skill_file.parent.name):
                content = skill_file.read_text(encoding="utf-8")
                match = re.search(r"(?m)^name:\s*([^\s]+)\s*$", content)
                self.assertIsNotNone(match)
                self.assertEqual(match.group(1), skill_file.parent.name)

    def test_readme_install_example_names_an_existing_skill(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        selected_names = re.findall(r"--skill\s+([a-z0-9-]+)", readme)
        self.assertTrue(selected_names)
        existing_names = {path.parent.name for path in SKILLS.glob("*/SKILL.md")}
        self.assertTrue(set(selected_names).issubset(existing_names))

    def test_local_markdown_links_resolve(self):
        markdown_link = re.compile(r"\[[^]]*\]\(([^)]+)\)")
        for path in ROOT.rglob("*.md"):
            content = path.read_text(encoding="utf-8")
            for target in markdown_link.findall(content):
                if "://" in target or target.startswith("#"):
                    continue
                local_target = target.split("#", 1)[0]
                with self.subTest(path=path.relative_to(ROOT), target=target):
                    self.assertTrue((path.parent / local_target).exists())

    def test_distributed_files_do_not_contain_live_token_shapes(self):
        token_pattern = re.compile(r"\bgw(?:at|st)_[A-Za-z0-9_-]{20,}\b")
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts:
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            with self.subTest(path=path.relative_to(ROOT)):
                self.assertIsNone(token_pattern.search(content))


if __name__ == "__main__":
    unittest.main()
