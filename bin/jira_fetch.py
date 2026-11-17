#!/usr/bin/env python3
"""Jira 티켓을 읽어 마크다운으로 출력한다 (읽기 전용).

사용:
  python3 -I bin/jira_fetch.py <URL 또는 KEY> [--attachments DIR]
  python3 -I bin/jira_fetch.py --repo        설정된 소스 폴더, 전용 작업 폴더, 브랜치 접두어를 한 줄씩 출력
  python3 -I bin/jira_fetch.py --selftest

설정: devflow/.env (대시보드 '설정' 탭에서 저장) 또는 환경변수
      JIRA_EMAIL, JIRA_API_TOKEN, (선택) JIRA_BASE_URL. .env 값이 우선한다.
토큰 값은 절대 출력하지 않는다.
"""
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE = ""  # 회사 주소는 코드에 두지 않는다: 설정 탭(JIRA_BASE_URL)에서 지정
KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")
BASE_RE = re.compile(r"https://[a-z0-9-]+\.atlassian\.net")
ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
ENV_KEYS = ("JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_BASE_URL", "JIRA_PROJECTS", "DEVFLOW_REPO", "DEVFLOW_WORK_REPO", "DEVFLOW_ENGINE", "DEVFLOW_BRANCH_PREFIX",
            "DEVFLOW_BASE_REF", "DEVFLOW_CATEGORIES", "JIRA_HIGHLIGHT")
DEFAULT_BRANCH_PREFIX = "feature/"
FIELDS = ",".join([
    "summary", "status", "issuetype", "priority", "assignee", "reporter", "labels",
    "components", "fixVersions", "duedate", "description", "comment", "attachment",
    "parent", "issuelinks", "subtasks", "created", "updated",
])


def load_config():
    """환경변수 위에 devflow/.env 를 덮어써 읽는다 (웹에서 바꾼 값이 바로 적용되게)."""
    cfg = {k: os.environ.get(k, "") for k in ENV_KEYS}
    try:
        with open(ENV_PATH, encoding="utf-8") as fp:
            for line in fp:
                k, sep, v = line.strip().partition("=")
                if sep and k in cfg and v.strip():
                    cfg[k] = v.strip().strip("\"'")
    except FileNotFoundError:
        pass
    cfg["JIRA_BASE_URL"] = (cfg["JIRA_BASE_URL"] or DEFAULT_BASE).rstrip("/")
    return cfg


def write_env(updates):
    """.env 의 지정한 키만 바꾸고 나머지 줄은 그대로 둔다. 파일은 처음부터 본인만 읽기 가능(600)."""
    for k, v in updates.items():
        if k not in ENV_KEYS or "\n" in str(v) or "\r" in str(v):
            raise ValueError(f"저장할 수 없는 설정값: {k}")
    try:
        with open(ENV_PATH, encoding="utf-8") as fp:
            existing = fp.read().splitlines()
    except FileNotFoundError:
        existing = []
    lines, done = [], set()
    for line in existing:
        k = line.partition("=")[0].strip()
        if k in updates:
            lines.append(f"{k}={updates[k]}"); done.add(k)
        else:
            lines.append(line)
    lines += [f"{k}={v}" for k, v in updates.items() if k not in done]
    tmp = ENV_PATH + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fp:
        fp.write("\n".join(lines) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, ENV_PATH)


def basic_auth(email, token):
    return "Basic " + base64.b64encode(f"{email}:{token}".encode()).decode()


def parse_target(arg, base=DEFAULT_BASE):
    key = KEY_RE.search(arg)
    if not key:
        raise SystemExit(f"Jira 키를 찾을 수 없습니다: {arg}")
    if arg.startswith("http"):
        u = urllib.parse.urlparse(arg)
        base = f"{u.scheme}://{u.netloc}"
    base = (base or "").rstrip("/")
    if not base:
        raise SystemExit("Jira 주소가 설정되지 않았습니다. 대시보드 설정 탭에서 Jira 주소를 저장하거나 전체 URL 을 주세요.")
    # 토큰이 Atlassian 이 아닌 곳으로 나가지 않게 한다
    if not BASE_RE.fullmatch(base):
        raise SystemExit(f"Atlassian Jira 주소가 아닙니다: {base}")
    return base, key.group(1)


def request(url, auth, raw=False):
    req = urllib.request.Request(url, headers={"Authorization": auth, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as res:
        data = res.read()
    return data if raw else json.loads(data)


# ---------- ADF(Atlassian Document Format) -> Markdown ----------

def adf_to_md(node, depth=0):
    if node is None:
        return ""
    if isinstance(node, list):
        return "".join(adf_to_md(n, depth) for n in node)
    t = node.get("type")
    kids = node.get("content", [])
    if t == "doc":
        return adf_to_md(kids, depth).strip() + "\n"
    if t == "text":
        s = node.get("text", "")
        for m in node.get("marks", []):
            if m["type"] == "code":
                s = f"`{s}`"
            elif m["type"] == "strong":
                s = f"**{s}**"
            elif m["type"] == "link":
                s = f"[{s}]({m.get('attrs', {}).get('href', '')})"
        return s
    if t == "paragraph":
        return adf_to_md(kids, depth) + "\n\n"
    if t == "heading":
        return "#" * node.get("attrs", {}).get("level", 3) + " " + adf_to_md(kids, depth) + "\n\n"
    if t == "hardBreak":
        return "\n"
    if t in ("bulletList", "orderedList"):
        out = []
        for i, item in enumerate(kids, 1):
            bullet = f"{i}." if t == "orderedList" else "-"
            body = adf_to_md(item.get("content", []), depth + 1).strip()
            out.append("  " * depth + f"{bullet} {body}")
        return "\n".join(out) + "\n\n"
    if t == "codeBlock":
        lang = node.get("attrs", {}).get("language", "") or ""
        return f"```{lang}\n{adf_to_md(kids, depth)}\n```\n\n"
    if t in ("blockquote", "panel"):
        body = adf_to_md(kids, depth).strip()
        return "\n".join("> " + line for line in body.splitlines()) + "\n\n"
    if t == "mention":
        return "@" + node.get("attrs", {}).get("text", "").lstrip("@")
    if t in ("inlineCard", "blockCard"):
        return node.get("attrs", {}).get("url", "")
    if t in ("mediaSingle", "mediaGroup", "media"):
        return "[첨부 이미지]\n\n" if t != "media" else ""
    if t == "emoji":
        return node.get("attrs", {}).get("text", "")
    if t == "table":
        rows = []
        for r in kids:
            cells = [adf_to_md(c.get("content", []), depth).strip().replace("\n", " ") for c in r.get("content", [])]
            rows.append("| " + " | ".join(cells) + " |")
        if rows:
            rows.insert(1, "|" + "---|" * rows[0].count(" | ") + "---|")
        return "\n".join(rows) + "\n\n"
    if t == "rule":
        return "---\n\n"
    return adf_to_md(kids, depth)


def name(obj, field="displayName"):
    return (obj or {}).get(field) or "-"


def render(base, key, issue):
    f = issue["fields"]
    lines = [
        f"# {key} {f.get('summary', '')}",
        "",
        f"- URL: {base}/browse/{key}",
        f"- 유형/상태/우선순위: {name(f.get('issuetype'), 'name')} / {name(f.get('status'), 'name')} / {name(f.get('priority'), 'name')}",
        f"- 담당자/보고자: {name(f.get('assignee'))} / {name(f.get('reporter'))}",
    ]
    if f.get("parent"):
        p = f["parent"]
        lines.append(f"- 상위: {p.get('key')} {p.get('fields', {}).get('summary', '')}")
    if f.get("labels"):
        lines.append("- 라벨: " + ", ".join(f["labels"]))
    if f.get("fixVersions"):
        lines.append("- 수정 버전: " + ", ".join(v.get("name", "") for v in f["fixVersions"]))
    if f.get("duedate"):
        lines.append(f"- 기한: {f['duedate']}")
    for link in f.get("issuelinks", []):
        other = link.get("outwardIssue") or link.get("inwardIssue") or {}
        lines.append(f"- 연결: {link.get('type', {}).get('name', '')} {other.get('key', '')} {other.get('fields', {}).get('summary', '')}")
    lines += ["", "## 설명", "", adf_to_md(f.get("description")) or "(없음)"]
    comments = (f.get("comment") or {}).get("comments", [])
    if comments:
        lines += ["## 댓글", ""]
        for c in comments:
            lines += [f"### {name(c.get('author'))} ({c.get('created', '')[:10]})", "", adf_to_md(c.get("body"))]
    atts = f.get("attachment") or []
    if atts:
        lines += ["## 첨부", ""]
        lines += [f"- {a.get('filename')} ({a.get('mimeType')}, {a.get('size', 0) // 1024}KB)" for a in atts]
    return "\n".join(lines).rstrip() + "\n"


def download_images(issue, auth, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    saved = []
    for a in issue["fields"].get("attachment") or []:
        if not str(a.get("mimeType", "")).startswith("image/"):
            continue
        safe = re.sub(r"[^\w.\-가-힣]", "_", a.get("filename", "image"))
        path = os.path.join(out_dir, f"{a.get('id')}_{safe}")
        with open(path, "wb") as fp:
            fp.write(request(a["content"], auth, raw=True))
        saved.append(path)
    return saved


def selftest():
    doc = {"type": "doc", "content": [
        {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "재현"}]},
        {"type": "orderedList", "content": [
            {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "앱 실행"}]}]},
            {"type": "listItem", "content": [{"type": "paragraph", "content": [
                {"type": "text", "text": "dp", "marks": [{"type": "code"}]}]}]},
        ]},
        {"type": "paragraph", "content": [{"type": "text", "text": "a"}, {"type": "hardBreak"}, {"type": "text", "text": "b"}]},
        {"type": "table", "content": [
            {"type": "tableRow", "content": [{"type": "tableHeader", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "OS"}]}]},
                                             {"type": "tableHeader", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "결과"}]}]}]},
        ]},
    ]}
    md = adf_to_md(doc)
    assert md.startswith("## 재현"), md
    assert "1. 앱 실행" in md and "2. `dp`" in md, md
    assert "a\nb" in md, md
    assert "| OS | 결과 |" in md and "|---|---|" in md, md
    assert parse_target("https://example.atlassian.net/browse/PROJ-8188?x=1") == ("https://example.atlassian.net", "PROJ-8188")
    assert parse_target("BUG-8598", "https://example.atlassian.net")[1] == "BUG-8598"
    try:
        parse_target("https://evil.example.com/browse/PROJ-1")
        raise AssertionError("외부 호스트 허용됨")
    except SystemExit:
        pass
    print("selftest ok")


def main():
    args = sys.argv[1:]
    if args == ["--selftest"]:
        return selftest()
    if args == ["--repo"]:
        cfg = load_config()
        if not cfg["DEVFLOW_REPO"]:
            raise SystemExit("소스 폴더가 설정되지 않았습니다. 대시보드(http://127.0.0.1:4100) 설정 탭에서 지정하세요.")
        print(cfg["DEVFLOW_REPO"])
        print(cfg["DEVFLOW_WORK_REPO"] or cfg["DEVFLOW_REPO"] + "-devflow")
        print(cfg["DEVFLOW_BRANCH_PREFIX"] or DEFAULT_BRANCH_PREFIX)
        return
    if not args:
        raise SystemExit(__doc__)
    cfg = load_config()
    email, token = cfg["JIRA_EMAIL"], cfg["JIRA_API_TOKEN"]
    if not email or not token:
        raise SystemExit("Jira 이메일/토큰이 없습니다. 대시보드(http://127.0.0.1:4100) '설정' 탭에서 저장하세요.")
    auth = basic_auth(email, token)
    base, key = parse_target(args[0], cfg["JIRA_BASE_URL"])
    try:
        issue = request(f"{base}/rest/api/3/issue/{key}?fields={FIELDS}", auth)
    except urllib.error.HTTPError as e:
        hint = {401: "인증 실패 (이메일/토큰 확인)", 403: "권한 없음", 404: "티켓이 없거나 볼 권한이 없음"}.get(e.code, "")
        raise SystemExit(f"Jira 요청 실패: HTTP {e.code} {hint}")
    print(render(base, key, issue))
    if "--attachments" in args:
        out = args[args.index("--attachments") + 1]
        for p in download_images(issue, auth, out):
            print(f"[이미지 저장] {p}")


if __name__ == "__main__":
    main()
