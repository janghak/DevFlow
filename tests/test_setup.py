import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "bin"))
import install  # noqa: E402
import jira_fetch as jf  # noqa: E402


class InstallTest(unittest.TestCase):
    def test_renders_paths_and_backs_up_changed_skill(self):
        with tempfile.TemporaryDirectory() as d:
            target = os.path.join(d, "skills")
            os.makedirs(os.path.join(target, "jira"))
            with open(os.path.join(target, "jira", "SKILL.md"), "w") as fp:
                fp.write("old personal skill")
            install.install(target, out=lambda *_: None)
            text = open(os.path.join(target, "jira", "SKILL.md"), encoding="utf-8").read()
            self.assertIn(ROOT, text)
            self.assertNotIn("{{DEVFLOW}}", text)
            backups = os.listdir(os.path.join(d, "skills-backup"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(open(os.path.join(d, "skills-backup", backups[0], "SKILL.md")).read(), "old personal skill")
            install.install(target, out=lambda *_: None)  # 같은 내용이면 백업을 더 만들지 않는다
            self.assertEqual(len(os.listdir(os.path.join(d, "skills-backup"))), 1)


class ConfigTest(unittest.TestCase):
    def test_config_excludes_credentials_and_decodes_template(self):
        with tempfile.TemporaryDirectory() as d:
            old = jf.ENV_PATH
            jf.ENV_PATH = os.path.join(d, ".env")
            try:
                jf.write_env({"JIRA_EMAIL": "a@b.c", "JIRA_API_TOKEN": "secret-token-123",
                              "DEVFLOW_COMMIT_TEMPLATE": "{type}: {title}\\n\\n{changes}"})
                cfg = jf.public_config()
            finally:
                jf.ENV_PATH = old
            dumped = json.dumps(cfg)
            self.assertNotIn("secret-token-123", dumped)
            self.assertNotIn("a@b.c", dumped)
            self.assertEqual(cfg["commitTemplate"], "{type}: {title}\n\n{changes}")
            self.assertEqual(cfg["baseRef"], jf.DEFAULT_BASE_REF)


class SkillsAreGenericTest(unittest.TestCase):
    def test_no_hardcoded_paths(self):
        for name in ("jira", "suggest"):
            text = open(os.path.join(ROOT, "skills", name, "SKILL.md"), encoding="utf-8").read()
            self.assertNotIn("/Users/", text)


if __name__ == "__main__":
    unittest.main()
