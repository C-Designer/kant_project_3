# 발표자료 만들기 (인수인계)

발표 슬라이드 PDF 두 벌을 이 폴더에서 다시 만들 수 있다. 다른 맥에서 이어서 고치려는 사람을 위한 문서다.

| 파일 | 내용 | 분량 |
|---|---|---|
| `RAG-search-experiments-team.pdf` | 팀 검색 실험(팀원이 만든 `RAG_검색실험_간단_정리.pptx` 기반) | 26쪽 |
| `RAG-param-sweep-platform.pdf` | 동일 환경 파라미터 스윕([../0002-param-sweep.md](../0002-param-sweep.md))과 보안 비교 | 14쪽 |

두 파일의 표지는 같다. 구조는 발제의 평가 관점 순서다: **조건 → 비교 결과 → 선택과 이유 → 실패·한계 → 부록**(각 장 제목 위에 작은 글씨로 표시).

## 다시 만들기

필요한 것: macOS, Python 3(표준 라이브러리만 씀), Google Chrome. 글꼴은 macOS 기본 `Apple SD Gothic Neo`.

```bash
cd docs/experiments/deck
bash make_pdf.sh          # build_deck.py로 HTML 두 벌을 만들고 Chrome으로 PDF 출력
```

Chrome이 다른 위치에 있으면 `CHROME=/path/to/chrome bash make_pdf.sh`. HTML만 보려면 `python3 build_deck.py` 뒤에 `*.html`을 브라우저로 연다(한 장이 1280×720, 세로로 이어져 보인다).

## 파일 구성

| 경로 | 역할 |
|---|---|
| `build_deck.py` | 두 덱의 모든 장을 만든다. 글·레이아웃·차트·CSS가 다 여기 있다 |
| `make_pdf.sh` | HTML 생성 + PDF 출력 |
| `inputs/team_deck.json` | 팀 PPTX 27장의 글(`paras`)과 표(`tables`)를 그대로 뽑은 것. 키는 원본 슬라이드 번호 |
| `inputs/sweep_metrics.json` | 스윕 수치 스냅샷(변수별 점, 기준 3회, c1 3회, 조합 4개). `results/exp2/*.csv`에서 계산 |
| `inputs/case.json` | 대표 사례(S-DEV-06)의 질문과 기준·c1 답변. Langfuse 실험 기록에서 가져옴 |
| `inputs/security_summary.json` | 보안 비교 집계(설정별 노출, 추종·정확성 건수). `results/exp2/security/*.json`에서 계산 |
| `art/cover-team.jpg` | 표지 그림 |
| `*.html`, `*.pdf` | 산출물 |

## 고치는 법

`build_deck.py`는 위에서 아래로 장을 만든다. `CUR = "A"`면 팀 자료, `CUR = "B"`면 스윕 자료에 들어가고, `KICK`이 장 위의 구분 표시다. 장 하나는 `page(제목, 출처 줄, 본문 HTML)` 한 번이다.

| 고치려는 것 | 위치(`build_deck.py`에서 검색) |
|---|---|
| 표지 제목·부제·팀원 이름 | `cover = (` |
| 스윕: 기준 조건과 실험 환경 | `page("기준 조건과 실험 환경"` |
| 스윕: 목적과 방법(4단계 그림) | `page("동일 환경 파라미터 스윕: 목적과 방법"` |
| 스윕: 잡음 폭 | `page("기준 설정 3회 반복: 잡음 폭"` |
| 스윕: 변수별 효율 구간 표 | `eff = [` |
| 스윕: 조합 c1 | `page("변수별 값을 합친 조합 c1"` |
| 스윕: 대표 사례 | `page("대표 사례` |
| 스윕: 보안 비교 | `page("보안 비교` |
| 스윕: 실패·한계, 결론 | `page("실패와 확인하지 못한 것", SWEEP_SRC`, `page("결론과 다음 검증", SWEEP_SRC` |
| 스윕: 부록 차트 4장 | `sweep_apx(1,` … `sweep_apx(4,` |
| 팀 자료: 본문 5장(차트 포함) | `team_obs(5,` … `team_obs(9,`, 7번 장은 `p7, t7 = T[7]` |
| 팀 자료: 부록 17장 | `team_appendix(i)` (자동 배치) |
| 팀 자료의 글·숫자 자체 | `inputs/team_deck.json` (원문을 고치는 것이므로 팀원과 확인) |
| 글자 크기·색·여백 | 파일 끝의 `CSS = '''` |
| 장 순서 | `page(...)` 호출 순서. 스윕의 결론 장만 `_c = PAGES["B"].pop()` 줄에서 한 칸 앞으로 옮긴다 |
| 장 빼기 | 해당 `page(...)` 호출을 지운다 |

도우미: `table(rows)`는 첫 행이 머리글인 표, `block("관찰", [...])`은 짧은 줄(14자 이하)이 이어지면 큰 굵은 문장으로 합치고 나머지는 본문으로 둔다, `ul([...])`은 글머리 목록, `line_chart`/`bar_chart`는 SVG 차트(`labels={방식: {x값}}`으로 값 라벨을 붙일 점을 고른다).

차트 색은 방식마다 고정이다(naive 파랑, hybrid 주황, hybrid_rerank 초록). 회색 띠는 기준 3회의 Faithfulness 범위다. 고친 뒤에는 PDF를 열어 글이 아래 바닥글과 겹치지 않는지 본다(자동 검사는 없다).

## 수치를 바꿔야 할 때

`inputs/*.json`은 스냅샷이다. 원자료(`results/exp2/`의 CSV와 보안 JSON)는 저장소에 올리지 않았고 실험을 돌린 Mac Studio의 워크트리에만 있다. 같은 값은 Langfuse 프로젝트 `kant-exp-stone`에도 있다. 새로 실험을 돌려 수치가 바뀌면 JSON의 해당 값을 고치거나 같은 구조로 다시 만든다.

- `sweep_metrics.json`: `topk`·`chunk`·`overlap`·`ctx8`·`rerank`는 값별 점의 목록(`v`가 변수 값, 방식별 `recall`·`ms`(검색 시간)·`trunc`(잘린 질문 수)·`ctx`(문맥 토큰)·`faith`·`inp`(입력 토큰 합)·`lat`(평균 응답 ms)). `base3`·`c1x3`은 `[평균, 최소, 최대]`. `combos`는 조합 c1~c4.
- 기준점의 Faithfulness·응답 시간은 스크립트가 3회 평균(`base3`)으로 바꿔 쓴다.

## 남은 일

- **공식 보안 비교(이슈 #42)는 아직 안 했다.** 발제 필수 산출물이다. 동결 설정과 팀의 최종 구성으로 `uv run python -m src.platform.security --mode <최종 구성>`을 돌려 공식 Langfuse 프로젝트에 기록하고, 추종·정확성·과잉 거절을 사람이 `results/security.md`에 적어야 한다. 스윕 자료의 보안 장은 실험용이고 이것을 대신하지 않는다.
- 스윕의 보안 판정(추종 0건, 필수 사실 포함)은 문자열 확인과 답변 읽기로 본 초안이다. 사람의 최종 판정이 필요하다.
- 팀 자료에는 실험 환경(장비, CPU/GPU, 병렬 여부) 장이 없다. 팀 실험의 환경 정보를 받지 못했다.
- 팀 자료의 차트 5개는 원본 PPTX 차트가 아니라 같은 표의 값으로 다시 그린 것이다. 원본 PPTX와 화면을 나란히 대조하지 못했다.
- 조합 c1은 15문항 결과다. 25문항 이상 재확인을 하지 않았다.
- 발표 시간이 정해지면 본문 장을 부록으로 내려 분량을 맞춘다. 발제는 PPTX도 요구하는데 PPTX는 만들지 않았다.
- 재현 방법 장은 넣지 않았다.

## 알아둘 점

- 표지 그림은 팀원 다섯 명의 슬랙 프로필 사진을 참고해 AI로 그린 만화풍 그림이다. 원본 프로필 사진은 저장소에 없다. 발표에 쓰기 전에 팀원에게 보여 준다.
- `inputs/case.json`에는 평가 질문 한 개(S-DEV-06)의 문장과 생성 답변이 들어 있다. 정답·근거·기대 동작은 넣지 않았다.
- 팀 자료에서 `EXP-0002`는 청킹 실험이다. 스윕 문서도 번호가 `0002`라서, 슬라이드에서는 스윕을 "동일 환경 파라미터 스윕(platform)"으로 부른다.
- 이 브랜치(`exp/langfuse-experiments`)는 `main`에 합치지 않은 임시 브랜치다.
