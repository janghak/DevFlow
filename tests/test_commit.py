import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import server as s  # noqa: E402
import jira_fetch as jf  # noqa: E402


def run(cwd, *args):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True).stdout


class CommitFlowTest(unittest.TestCase):
    """사용자가 누른 커밋·푸시: 고른 파일만 커밋, 푸시, PR 주소, 작업 기록 갱신, 실행 중에는 거부."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = os.path.realpath(self.tmp.name)
        home = os.path.join(d, "home")
        os.makedirs(home)
        run(d, "git", "init", "-q", "--bare", "-b", "main", "remote.git")
        run(d, "git", "clone", "-q", "remote.git", os.path.join(home, "app"))
        app = os.path.join(home, "app")
        open(os.path.join(app, "a.txt"), "w").write("a\n")
        run(app, "git", "add", "a.txt")
        run(app, "git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
        run(app, "git", "push", "-q", "origin", "main")
        run(app, "git", "config", "user.name", "t")
        run(app, "git", "config", "user.email", "t@t")
        self.saved = (s.HOME, jf.ENV_PATH, s.WORKLOG, s.REPO, s.WORK_REPO)
        s.HOME, jf.ENV_PATH, s.WORKLOG = home, os.path.join(d, ".env"), os.path.join(d, "worklog")
        os.makedirs(s.WORKLOG)
        jf.write_env({"JIRA_BASE_URL": "https://example.atlassian.net",
                      "DEVFLOW_COMMIT_TEMPLATE": "{type}: {title} ({key})\\n\\n{changes}",
                      "DEVFLOW_PR_URL": "https://git.example.com/compare/{base}...{branch}"})
        code, _ = s.save_project({"repo": app, "baseRef": "origin/main", "branchPrefix": "feature/"})
        self.assertEqual(code, 200)
        self.remote = os.path.join(d, "remote.git")
        w = s.WORK_REPO
        run(w, "git", "switch", "-q", "-c", "feature/TT-1", "origin/main")
        open(os.path.join(w, "a.txt"), "w").write("changed\n")
        open(os.path.join(w, "skip.txt"), "w").write("not chosen\n")
        json.dump({"key": "TT-1", "title": "중복 클릭", "change": "방지 추가", "tags": ["Bugfix"]},
                  open(os.path.join(s.WORKLOG, "TT-1.json"), "w"))

    def tearDown(self):
        s.HOME, jf.ENV_PATH, s.WORKLOG, s.REPO, s.WORK_REPO = self.saved
        s.work_state.clear(); s.work_state["status"] = "idle"
        self.tmp.cleanup()

    def test_commit_push_and_pr(self):
        code, p = s.commit_preview("TT-1")
        self.assertEqual(code, 200)
        self.assertEqual(p["message"], "fix: 중복 클릭 (TT-1)\n\n1. 방지 추가")
        code, r = s.commit_run({"key": "TT-1", "message": p["message"], "files": ["a.txt", "../outside.txt"], "push": True})
        self.assertEqual(code, 200, r)
        self.assertTrue(r["pushed"])
        self.assertEqual(r["prUrl"], "https://git.example.com/compare/main...feature/TT-1")
        committed = run(s.WORK_REPO, "git", "show", "--name-only", "--format=", "HEAD").split()
        self.assertEqual(committed, ["a.txt"])  # 고르지 않은 파일·목록 밖 경로는 커밋되지 않음
        self.assertIn("feature/TT-1", run(self.remote, "git", "branch"))
        self.assertEqual(json.load(open(os.path.join(s.WORKLOG, "TT-1.json")))["status"], "pushed")

    def test_refused_while_job_running(self):
        s.work_state["status"] = "running"
        self.assertEqual(s.commit_run({"key": "TT-1", "message": "x", "files": ["a.txt"]})[0], 409)


class BringToMineTest(CommitFlowTest):
    """내 폴더로 가져오기: 작업 폴더의 수정·보관분을 내 소스 폴더 브랜치로 옮긴다."""

    def test_from_work_folder(self):
        s.devflow_untracked.add("skip.txt")
        code, r = s.bring_to_mine({"key": "TT-1"})
        self.assertEqual(code, 200, r)
        app = s.REPO
        self.assertEqual(run(app, "git", "branch", "--show-current").strip(), "feature/TT-1")
        self.assertEqual(open(os.path.join(app, "a.txt")).read(), "changed\n")
        self.assertTrue(os.path.exists(os.path.join(app, "skip.txt")))
        self.assertEqual(run(s.WORK_REPO, "git", "branch", "--show-current").strip(), "")  # 작업 폴더는 떼어 둠
        self.assertEqual(run(app, "git", "stash", "list"), "")
        open(os.path.join(app, "mine.txt"), "w").write("내 파일\n")
        c = s.ticket_changes("TT-1")[1]
        self.assertEqual(c["heldBy"], app)
        d = next(x["diff"] for x in c["sections"] if x["title"].startswith("내 폴더"))
        self.assertIn("a.txt", d)
        self.assertIn("skip.txt", d)  # 가져온 새 파일도 보인다
        self.assertNotIn("mine.txt", d)  # 사용자의 다른 파일은 안 보인다
        code, r = s.enqueue_job("TT-1", "work")  # 내 폴더가 쥔 브랜치는 AI 작업을 막는다
        self.assertEqual(code, 409, r)

    def test_from_stash_and_refuses_dirty_mine(self):
        s.devflow_untracked.add("skip.txt")
        s.stash_leftovers("TT-2")
        run(s.WORK_REPO, "git", "switch", "-q", "--detach")
        open(os.path.join(s.REPO, "a.txt"), "w").write("my edit\n")
        self.assertEqual(s.bring_to_mine({"key": "TT-1", "ref": "stash@{0}"})[0], 400)  # 내 수정은 덮지 않는다
        run(s.REPO, "git", "checkout", "--", "a.txt")
        code, r = s.bring_to_mine({"key": "TT-1", "ref": "stash@{0}"})
        self.assertEqual(code, 200, r)
        self.assertEqual(open(os.path.join(s.REPO, "a.txt")).read(), "changed\n")


if __name__ == "__main__":
    unittest.main()
