---
name: suggest
description: 설정한 소스 저장소를 분석해 개선 제안을 근거(file:line)와 함께 만들고, 사용자가 검토 후 직접 Jira 를 만들 수 있도록 Jira 초안까지 devflow 제안 목록에 저장한다. 코드 수정·Jira 생성은 하지 않는다. "/suggest [영역 또는 카테고리]", "개선할 거 찾아줘" 에 사용.
---

# /suggest — 개선 제안 만들기

입력: `$ARGUMENTS` — 범위 (예: 모듈 경로, 카테고리, 화면 이름). 없으면 카테고리 하나를 골라 진행하고 무엇을 골랐는지 알린다.
devflow 폴더: `{{DEVFLOW}}` (도구·데이터. 소스 저장소 안에 파일을 만들지 않는다)

## 0. 설정 읽기
```bash
python3 -I {{DEVFLOW}}/bin/jira_fetch.py --config
```
`repo` 가 분석할 저장소, `categories` 가 쓸 카테고리 목록이다. `repo` 가 비어 있으면 멈추고 대시보드(`python3 {{DEVFLOW}}/server.py` → http://127.0.0.1:4100) **설정** 탭에서 소스 폴더를 지정하라고 안내한다.

## 절대 규칙
- **코드를 수정하지 않는다. Jira 를 만들지 않는다** (티켓은 사용자가 직접 생성). 브랜치도 만들지 않는다.
- 제안마다 실제 코드 근거(`file:line`)가 있어야 한다. 근거 없는 일반론("테스트를 늘리세요") 금지.
- 한 번에 3~8개. 많이보다 정확하게. 효과·위험이 불분명하면 `risk` 에 적는다.
- `category` 는 설정의 `categories` 중 하나만 쓴다.

## 절차
1. `{{DEVFLOW}}/data/suggestions.json` 을 읽는다 (없으면 `{"items": []}`). 이미 있는 제안(같은 문제·같은 위치)은 다시 만들지 않는다.
2. 범위의 코드를 조사한다. 넓으면 Explore 서브에이전트로 탐색해도 된다. 찾을 것의 예:
   - 메인 스레드 블로킹(동기 I/O 등), 누수 위험 리스너/콜백, 강제 언래핑·널 가능 지점
   - 지원 종료(deprecated) API, 같은 로직의 중복 구현, 작고 독립적인 화면의 최신 UI 프레임워크 전환 후보
   - 빌드 설정 개선(불필요한 의존성, 설정 중복), 접근성 누락(대체 텍스트, 포커스 순서)
3. 각 제안을 아래 형식으로 `items` 끝에 추가해 저장한다 (기존 항목·status 는 건드리지 않는다):
```json
{
  "id": "S-YYYYMMDD-01",
  "title": "짧은 제목",
  "project": "<repo 폴더 이름>",
  "category": "<categories 중 하나>",
  "priority": "high | medium | low",
  "effort": "S | M | L",
  "problem": "무엇이 문제인가 (현상/위험)",
  "evidence": [{"file": "path/to/File.kt", "line": 120, "note": "근거 설명"}],
  "proposal": "어떻게 바꿀 것인가",
  "impact": "기대 효과 (측정 가능하면 지표)",
  "risk": "부작용/확인 필요 사항",
  "jiraDraft": {
    "summary": "[영역] 제목",
    "description": "배경\n- ...\n\n작업 내용\n1. ...\n\n완료 조건\n- ...\n\n참고 코드\n- 파일:라인"
  },
  "status": "proposed",
  "jiraKey": null,
  "createdAt": "YYYY-MM-DD",
  "note": ""
}
```
   - `id` 는 날짜 + 순번, 기존 id 와 겹치지 않게.
   - JSON 은 Python 으로 읽고-추가-저장해 깨지지 않게 한다 (`json.load` → append → `json.dump(ensure_ascii=False, indent=2)`).
4. 표로 요약(제목, 카테고리, 우선순위, 규모)하고, 검토는 대시보드 **개선 제안** 탭에서 한다고 안내한다.

## 이후 흐름 (참고)
대시보드에서 채택 → Jira 초안 복사 → **Jira 직접 생성** → 대시보드에 키 입력 → `/jira <URL>` 로 작업.
