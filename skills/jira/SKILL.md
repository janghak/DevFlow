---
name: jira
description: Jira 티켓 URL 또는 키(예 PROJ-1234)를 받아 티켓 내용을 읽고, 설정한 기준 브랜치에서 작업 브랜치를 만들어 구현·빌드 확인까지 하고 작업 기록을 남긴다. 커밋·푸시·PR은 사용자가 그 메시지에서 명시적으로 요청할 때만 한다. "/jira <URL>" 또는 "이 지라 작업해줘 <URL>" 에 사용.
---

# /jira — Jira 티켓 기반 작업

입력: `$ARGUMENTS` (Jira URL 또는 키). 없으면 사용자에게 받는다.
devflow 폴더: `{{DEVFLOW}}` (도구·데이터. 소스 저장소 안에 파일을 만들지 않는다)

## 0. 설정 읽기
```bash
python3 -I {{DEVFLOW}}/bin/jira_fetch.py --config
```
JSON 으로 나오는 값을 이 문서 전체에서 쓴다 (토큰은 나오지 않는다):
- `repo` 작업 저장소 (git 명령은 여기서 실행), `branchPrefix` 브랜치 접두어, `baseRef` 기준 브랜치
- `buildCmd` 빌드 확인 명령, `commitTemplate` 커밋 메시지 형식, `prUrl` PR 주소 형식
값이 비어 있어 진행할 수 없으면 멈추고, 대시보드(`python3 {{DEVFLOW}}/server.py` → http://127.0.0.1:4100) **설정** 탭에서 채우라고 안내한다.

## 절대 규칙
- **커밋, 푸시, PR 생성, 원격 브랜치 생성(push -u)은 사용자가 "커밋해줘 / 푸시해줘 / PR 올려줘"처럼 해당 메시지에서 직접 요청할 때만 한다.** 이전 승인은 다음 작업에 이어지지 않는다.
- **Jira 에 쓰지 않는다.** 티켓 생성·수정·댓글·상태 변경 금지. 읽기만 한다.
- Jira 토큰 값을 출력·로그·파일에 남기지 않는다.
- `git reset --hard`, `git clean`, 강제 푸시, 남의 변경 되돌리기 금지.

## 1. 티켓 읽기
```bash
python3 -I {{DEVFLOW}}/bin/jira_fetch.py "$ARGUMENTS" --attachments {{DEVFLOW}}/data/attachments/<KEY>
```
- 이미지 첨부가 저장되면 Read 로 열어 확인한다 (UI 버그 스크린샷 등).
- 설정 없음/401 이면 멈추고 대시보드 **설정** 탭에서 Jira 이메일·토큰·주소를 저장하라고 안내한다. 대신 티켓 본문을 붙여넣어 달라고 해도 된다.
- 티켓 요약을 3~5줄로 보여준다: 무엇을, 어디서(화면/모듈), 완료 조건, 불명확한 점.
- 요구사항이 모호해 구현 방향이 갈리면 여기서 질문한다 (추측으로 진행하지 않음).

## 2. 브랜치 준비
브랜치명: `<branchPrefix><KEY>`, 기준: `<baseRef>` (예: `origin/main` → 원격 이름 `origin`, 브랜치 `main`)
```bash
git status --porcelain -uno --ignore-submodules=all   # 하위 저장소 포인터 변경은 무시
```
- 출력이 있으면(커밋 안 된 수정) **멈추고** 선택을 묻는다: `git stash push -m "<설명>"` 후 진행 / 현재 브랜치에서 그대로 진행 / 중단.
- 이미 브랜치가 있으면 (`git rev-parse --verify <브랜치>` 또는 `git ls-remote --heads origin <브랜치>`) 그 브랜치로 `git switch` 하고 `{{DEVFLOW}}/data/worklog/<KEY>.json` 을 읽어 이어서 작업한다. 새로 만들거나 리셋하지 않는다.
- 없으면:
```bash
git fetch <원격> <기준 브랜치>
git switch -c <branchPrefix><KEY> <baseRef> --no-track
```
(원격에는 만들지 않는다. 원격 브랜치는 사용자가 푸시를 요청할 때 생긴다.)

## 3. 작업 기록 시작
`{{DEVFLOW}}/data/worklog/<KEY>.json` 을 만든다 (있으면 갱신). 스키마:
```json
{
  "key": "PROJ-1234",
  "url": "<Jira 티켓 URL>",
  "title": "티켓 제목",
  "kind": "APP",
  "status": "in_progress",
  "branch": "<branchPrefix>PROJ-1234",
  "startedAt": "YYYY-MM-DD",
  "updatedAt": "YYYY-MM-DD",
  "summary": "한 줄 요약 (카드 부제)",
  "problem": "",
  "cause": "",
  "change": "",
  "files": [],
  "verification": [],
  "metric": null,
  "tags": [],
  "commits": [],
  "suggestionId": null
}
```
- `kind`: 앱 기능/버그면 `APP`, AI·자동화·개발환경이면 `AX`.
- `{{DEVFLOW}}/data/suggestions.json` 에 `jiraKey` 가 이 KEY 인 제안이 있으면 `suggestionId` 를 채우고, 그 제안의 `status` 를 `in_progress` 로 바꾼다.

## 4. 구현
- 관련 코드를 먼저 읽고(호출부, 공통 코드 영향 범위 포함), 최소 변경으로 고친다. 기존 구조·컨벤션을 따른다.
- 공통 코드를 바꾸면 사용처를 grep 해서 영향 범위를 알린다.
- 빌드 확인: `buildCmd` 를 저장소에서 실행한다. 비어 있으면 프로젝트 구조(gradle, xcodebuild, npm 등)를 보고 가장 가벼운 컴파일 확인 명령을 골라 실행하고, 설정 탭의 "빌드 확인 명령"에 등록하라고 알린다. 실패를 숨기지 않는다.
- 실기기/에뮬레이터 확인이 의미 있는 UI 변경이면, 확인 여부를 묻거나 미검증으로 명시한다.

## 5. 작업 기록 마무리
worklog JSON 을 채운다:
- `problem` 현상, `cause` 원인, `change` 수정 내용 (각 1~3문장, 보고서에 바로 쓸 수 있게)
- `files` 변경 파일 경로, `verification` 실제로 한 확인 (컴파일, 기기, 테스트) — 안 한 것은 쓰지 않음
- `metric`: 측정한 수치가 있을 때만 `{"label": "진입 시간", "before": "4.5s", "after": "0.3s"}`. 추정치 금지.
- `tags`: Performance, UX, Stability, Accessibility, Architecture, Network, Bugfix 등
- `status`: `done` (로컬 작업 완료, 커밋 전)
- 연결된 제안이 있으면 그 제안 `status` 를 `done` 으로.

마지막으로 사용자에게: 변경 요약, 브랜치명, 미검증 항목, "커밋/푸시/PR 은 요청 시 진행" 을 알린다.

## 6. 사용자가 요청할 때만: 커밋 / 푸시 / PR
**커밋** — `commitTemplate` 을 따른다. `{title}` 티켓 제목, `{key}` 키, `{url}` 티켓 URL, `{type}` feat 또는 fix, `{changes}` 변경 목록(번호 매김)으로 채운다. 비어 있으면 아래 기본 형식을 쓴다. 작업한 파일만 `git add <경로>` (전체 add 금지, 하위 저장소 제외).
```
{type}: {title} ({key})

{changes}
```
커밋 후 worklog `commits` 에 해시 추가, `status` → `committed`.

**푸시** — `git push -u <원격> <branchPrefix><KEY>`. worklog `status` → `pushed`.

**PR** — `prUrl` 이 있으면 `{base}` 기준 브랜치 이름(원격 이름 제외), `{branch}` 작업 브랜치로 채운 주소를 준다. 없으면 `gh` 가 있으면 `gh pr create` 를 제안하고, 없으면 원격 저장소 웹에서 만들라고 안내한다. PR 본문 초안(제목, 변경 내용, 테스트, 영향 범위)을 함께 준다. worklog `status` → `pr`.
