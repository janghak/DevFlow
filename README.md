# devflow

Jira 티켓을 받아 로컬 저장소에서 AI(Claude Code 또는 Codex)로 작업·분석하고, 진행 상황과 변경 내용을 보는 로컬 대시보드입니다.

- 내 Jira 목록(프로젝트·기간 필터)에서 **작업 시작** / **분석만** → 대기열로 하나씩 실행
- 작업은 소스 폴더 옆 **전용 작업 폴더**(git worktree)에서만 해서, 개발 중인 폴더를 건드리지 않음
- 티켓별 변경 내용(diff), 실시간 진행 단계, 개선 제안 생성, 작업 기록, 지정 프로젝트 자동 작업
- **커밋·푸시·PR 은 하지 않습니다.** AI 실행 권한에서 막혀 있고, 필요하면 Claude Code 에서 `/jira` 로 직접 요청합니다.
- Jira 는 읽기만 합니다.

## 준비물

- macOS (폴더 선택 창은 macOS 전용, 나머지는 다른 OS 에서도 동작)
- Python 3.9 이상 (외부 패키지 없음)
- git
- [Claude Code](https://claude.com/claude-code) CLI 설치·로그인 (`claude --version` 이 동작해야 함). Codex 를 쓰려면 Codex CLI 도 설치·로그인
- Jira Cloud API 토큰: https://id.atlassian.com/manage-profile/security/api-tokens

## 시작하기

```bash
git clone <이 저장소 주소> DevFlow
cd DevFlow
python3 install.py      # /jira, /suggest 스킬을 ~/.claude/skills 에 설치 (기존 스킬은 백업)
python3 server.py       # http://127.0.0.1:4100
```

브라우저에서 http://127.0.0.1:4100 을 열고 **설정** 탭을 위에서부터 채웁니다.

1. **소스 프로젝트**: 작업할 git 저장소를 "후보 찾기" 또는 "폴더 선택…"으로 고르고, 브랜치 접두어(예: `feature/`), 기준 브랜치(예: `origin/develop`)를 넣고 저장 → 옆에 `<저장소>-devflow` 전용 작업 폴더가 자동으로 만들어집니다.
   - 선택: 빌드 확인 명령, 커밋 메시지 형식, PR 주소 형식, 개선 제안 카테고리
2. **실행 엔진**: Claude Code 또는 Codex
3. **Jira 연결**: 이메일, API 토큰, Jira 주소(`https://<회사>.atlassian.net`), 볼 프로젝트 키, 빨강으로 강조할 프로젝트
4. (선택) **자동 작업**: 지정 프로젝트에 새로 할당되는 티켓을 자동으로 대기열에 넣기 (하루 상한)

설정이 비어 있으면 대시보드 위에 안내가 나옵니다.

## 어디에 무엇이 저장되나

| 위치 | 내용 | git |
|---|---|---|
| `.env` | Jira 이메일·토큰·주소, 소스 경로, 브랜치 규칙 등 모든 설정 (권한 600) | 제외 |
| `data/` | 작업 기록, 개선 제안, 분석 결과, 실행 로그, Jira 첨부 | 제외 |
| `skills/` | `/jira`, `/suggest` 규칙 (경로·회사 값 없음, 설정에서 읽음) | 포함 |

회사·개인 정보는 코드에 넣지 않습니다. 모두 설정 탭에서 이 PC 의 `.env` 에만 저장됩니다.

## Claude Code 에서 직접 쓰기

```text
/jira https://<회사>.atlassian.net/browse/PROJ-1234
/suggest 성능
```

`/jira` 는 브랜치 생성·구현·빌드 확인·작업 기록까지 하고 멈춥니다. 커밋·푸시·PR 은 그 메시지에서 "커밋해줘"처럼 요청할 때만 합니다.

## 테스트

```bash
python3 -I bin/jira_fetch.py --selftest
python3 -m unittest discover tests
```
