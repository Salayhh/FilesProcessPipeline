import unittest
from pathlib import Path


class SkillFilesTest(unittest.TestCase):
    def test_codex_and_openclaw_skill_instructions_match(self):
        root = Path(__file__).resolve().parents[1]
        codex_skill = root / ".codex" / "skills" / "files-process-pipeline" / "SKILL.md"
        openclaw_skill = root / ".agents" / "skills" / "files-process-pipeline" / "SKILL.md"

        self.assertEqual(
            codex_skill.read_text(encoding="utf-8"),
            openclaw_skill.read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
