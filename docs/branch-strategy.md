# 브랜치 전략

`main`과 짧게 쓰는 작업 브랜치만 사용한다 (GitHub Flow). 모든 변경은 PR로 `main`에 들어간다.

## GitHub이 강제하는 규칙

`main`에는 룰셋 `main-protection`이 걸려 있다.

| 금지 | 대신 |
|---|---|
| `main`에 직접 push | 작업 브랜치에서 PR로 머지 |
| `main`에 force push | 이미 머지된 내용은 revert PR로 되돌림 |
| `main` 브랜치 삭제 | - |
| 리드 승인 없이 머지 | 리드가 리뷰·승인·머지 |

- 필수 승인 1명 + 코드오너 리뷰 필수. `.github/CODEOWNERS`가 모든 경로를 리드(`@C-Designer`)로 지정하므로 **리드 승인 없이는 머지 버튼이 열리지 않는다.**
- 새 push가 오면 이전 승인은 무효가 된다.
- 리드(저장소 관리자)는 PR에서만 규칙을 우회할 수 있다(본인 PR 머지용). 직접 push는 리드도 막힌다.
- GitHub이 못 막는 것: 리드가 승인한 뒤 다른 사람이 머지 버튼을 누르는 것. **머지는 리드만 한다**는 팀 규칙이다.
- 필수 status check는 없다(CI 없음).

## 팀 규칙

GitHub이 강제하지 않는 약속이다.

- **브랜치 이름:** `<type>/<짧은-설명>` (영문 소문자, 하이픈 구분). 예: `feat/login-form`
- **PR 하나에 목적 하나:** 크기가 커지면 PR을 나눈다.
- **PR 제목:** `<type>: <설명>`. 예: `feat: 로그인 폼 추가`
- **머지는 리드만:** 팀원은 PR을 올리고 리드 리뷰를 기다린다. 리드가 Squash and merge로 머지한다.
- **PR 본문에 실행 증거:** 명령과 결과(캡처). 리드가 그것으로 리뷰한다.
- **머지 후:** 원격 브랜치는 자동 삭제된다. 로컬 브랜치는 직접 지운다 (Squash 머지라 `-D`가 필요하다).
- **남의 브랜치:** 담당자와 합의 없이 push하지 않는다.

| type | 용도 |
|---|---|
| `feat` | 기능 추가 |
| `fix` | 버그 수정 |
| `refactor` | 동작 변경 없는 코드 개선 |
| `docs` | 문서 |
| `test` | 테스트 |
| `chore` | 빌드, 설정 등 기타 |

## 커밋 메시지

형식은 `<type>: <설명>`이고, type은 위 표와 같다. 설명은 무엇을 왜 바꿨는지 한 줄로 쓴다.

```
fix: 만료된 토큰으로 로그인되는 문제 수정
```

Squash 머지 시 `main`에 남는 커밋 제목은 커밋이 1개인 PR이면 그 커밋 메시지, 2개 이상이면 PR 제목이다. 그래서 커밋 메시지와 PR 제목 모두 이 형식을 지킨다.

## 작업 흐름

```bash
# 최초 1회
git clone https://github.com/C-Designer/kant_project_3.git
cd kant_project_3

# 작업 시작: 항상 최신 main에서 분기
git switch main
git pull
git switch -c feat/login-form

# 작업 후 push, PR 생성
git add <파일>
git commit -m "feat: 로그인 폼 추가"
git push -u origin feat/login-form
gh pr create

# 이후는 리드가 리뷰·머지. 머지되면 로컬 정리
git switch main && git pull && git branch -D feat/login-form
```

`gh` 대신 GitHub 웹에서 PR을 만들어도 된다.

PR 본문은 템플릿(`.github/pull_request_template.md`)을 채워서 작성한다. `gh pr create --fill`은 커밋 내용으로 본문을 채우므로 쓰지 않는다. 에이전트처럼 비대화형으로 실행할 때는 템플릿 항목을 채운 본문을 `--title`, `--body`로 넘긴다.

## main 변경 반영과 충돌 해결

작업 중 `main`이 바뀌었으면 작업 브랜치에 merge한다. 충돌은 PR을 올린 사람이 자기 브랜치에서 해결한다.

```bash
git fetch origin
git merge origin/main
```

Squash 머지라 이 merge 커밋은 `main` 히스토리에 남지 않는다.
