#!/usr/bin/env python3
"""devflow 의 Claude Code 스킬(/jira, /suggest)을 ~/.claude/skills 에 설치한다.

실행: python3 install.py
- skills/<이름>/SKILL.md 의 {{DEVFLOW}} 를 이 폴더 경로로 바꿔 ~/.claude/skills/<이름>/SKILL.md 로 쓴다.
- 같은 이름의 스킬이 이미 있고 내용이 다르면 ~/.claude/skills-backup/<이름>-<시각>/ 으로 먼저 백업한다.
- 회사·개인 정보는 스킬에 넣지 않는다. 대시보드 설정 탭에서 저장한 값을 스킬이 실행할 때 읽는다.
"""
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
NAMES = ("jira", "suggest")


def install(target=None, out=print):
    target = target or os.environ.get("CLAUDE_SKILLS_DIR") or os.path.expanduser("~/.claude/skills")
    backup_root = os.path.join(os.path.dirname(target), "skills-backup")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for name in NAMES:
        with open(os.path.join(ROOT, "skills", name, "SKILL.md"), encoding="utf-8") as fp:
            text = fp.read().replace("{{DEVFLOW}}", ROOT)
        dst_dir = os.path.join(target, name)
        dst = os.path.join(dst_dir, "SKILL.md")
        if os.path.exists(dst):
            with open(dst, encoding="utf-8") as fp:
                if fp.read() == text:
                    out(f"그대로: /{name} (이미 최신)")
                    continue
            backup = os.path.join(backup_root, f"{name}-{stamp}")
            shutil.copytree(dst_dir, backup)
            out(f"백업: 기존 /{name} → {backup}")
        os.makedirs(dst_dir, exist_ok=True)
        with open(dst, "w", encoding="utf-8") as fp:
            fp.write(text)
        out(f"설치: /{name} → {dst}")


if __name__ == "__main__":
    if sys.version_info < (3, 9):
        raise SystemExit("python 3.9 이상이 필요합니다")
    install()
    print(f"""
다음 단계
  1. python3 {os.path.join(ROOT, 'server.py')}
  2. http://127.0.0.1:4100 → 설정 탭에서 Jira 연결, 소스 프로젝트를 채운다
  3. Claude Code 를 새로 열면 /jira, /suggest 를 쓸 수 있다""")
