# 작업 계획과 역할 분담

제출 2026-11-13 (금) 13:00. 오늘(11/5)부터 8일. 요구사항은 [requirements.md](requirements.md), 채점은 [evaluation.md](evaluation.md), 영역 정의는 [ADR 0002](adr/0002-areas-aligned-to-brief.md).

담당자 칸은 11/5 미팅에서 채운다. 채우면 이 문서와 README를 같은 PR로 갱신한다.

## 팀

| 이름 | 역할 |
|---|---|
| 김창동 | 리드. 구현은 하지 않는다. Issue·Project로 진행 추적, 인터페이스 변경 조정, PR 리뷰 흐름, 일정, README·발표자료 통합, 팀 Notion 제출 |
| 천희재 | 실무 (영역 미정) |
| 윤승환 | 실무 (영역 미정) |
| 오주헌 | 실무 (영역 미정) |
| 김경민 | 실무 (영역 미정) |

## 분담 원칙

1. **영역 = 사람.** 실무 4명이 `ingestion`, `retrieval`, `service`, `evaluation`을 하나씩 맡는다. `observability`는 작아서(Langfuse 연동 하루) `service` 담당이 함께 든다.
2. **인터페이스를 먼저 고정한다.** 각 spec의 "인터페이스" 절(청크 레코드, `retrieve()`, `/query`, `answer()`, 실행 레코드)이 계약이다. 이게 있어야 각자 mock으로 병렬 작업이 된다. 바꾸려면 의존 영역 담당자가 PR에 확인을 남긴다.
3. **질문 하나가 끝까지 먼저.** 발제 권장대로 11/7(토) 저녁까지 `naive` 1문항 end-to-end(색인 → 검색 → 생성 → 출처 → Langfuse)가 돈다. 그 뒤에 `hybrid`, `hybrid_rerank`, 평가가 올라간다.
4. **공통 설정 동결일을 정한다.** 11/10(화) 아침에 k, 문맥 한도, 프롬프트, 생성 설정을 동결하고 그 뒤로는 비교 실행만 한다. 동결 후 바꾸면 전체 재실행이다.
5. **모든 팀원이 실행과 오류 분석에 참여한다.** 발제 평가 항목이다. 최종 실행과 대표 사례 원문 대조는 영역과 무관하게 나눠 맡는다.
6. **리드는 코드를 쓰지 않는다.** 대신 매일 Project 보드를 보고 막힌 Issue를 당일 안에 푼다(담당 재배정, 범위 축소, 의사결정).

## 분담안

### A안 (권장): 영역별 1인

| 영역 | 담당 | 주 작업 | 작업량 | 의존 |
|---|---|---|---|---|
| `ingestion` | | PDF 추출, 청킹, E5 임베딩, Qdrant 색인, 누락·실패 리포트 | 중. Basic이면 11/6 안에 1차 완료 가능 | 데이터셋 |
| `retrieval` | | `naive` → `hybrid`(키워드+결합) → `hybrid_rerank`(리랭커). k 통일 | 중상. 리랭커 모델 선택·로컬 실행이 변수 | `ingestion` 컬렉션 |
| `service` + `observability` | | FastAPI, 프롬프트, 출력 JSON 검증, 자료 ID 매핑, 오류·timeout·재시도, Langfuse 트레이스 | 중상. 프롬프트 품질이 답변 품질을 좌우 | `retrieval` 시그니처(초기엔 mock) |
| `evaluation` | | 질문 선택, 일괄 실행 러너, Hit/Recall, RAGAS, Judge, 운영 지표 집계, 보안 4개, 비교표 생성 | 상. 가장 크고 발표 근거가 여기서 나옴 | `service.answer()`(초기엔 mock) |

왜 이 조합인가: 네 영역의 의존이 한 방향(ingestion → retrieval → service → evaluation)이라 인터페이스만 맞추면 동시에 시작할 수 있다. `evaluation`이 가장 크므로 **평가 자동화나 데이터 다루기에 익숙한 사람**에게, `service`는 **프롬프트·API 경험 있는 사람**에게 주는 게 좋다.

### B안: 앞뒤 페어

| 페어 | 담당 | 범위 |
|---|---|---|
| 검색 페어 | , | `ingestion` + `retrieval`. 한 사람이 색인·naive, 다른 사람이 hybrid·rerank |
| 서비스 페어 | , | `service` + `observability` + `evaluation` 러너. 한 사람이 API·프롬프트, 다른 사람이 Langfuse·러너·지표 |

장점: 같은 데이터·같은 컬렉션을 만지는 사람끼리 묶여 조율이 빠르다. 단점: `evaluation`(RAGAS·Judge·보안·비교표)이 11/9 이후로 밀린다. 팀원 경험 편차가 크면 B안.

### 영역과 무관하게 전원이 나눠 맡는 것 (11/10~)

| 일 | 내용 |
|---|---|
| 최종 실행 | 질문 × 3방식 실행과 평가 실행. 오류 나면 담당 영역에 Issue |
| 대표 사례 원문 대조 | 좋아진·나빠진 사례를 PDF 원문과 대조해 이유 작성. 1인 2~3건 |
| 보안 4개 해석 | 공격 노출·추종·정확성·과잉 거절 기록 |
| README 각자 절 | 자기 영역 실행 방법, 설정값, 한계, 기여 |
| 발표자료 | 리드가 뼈대, 각자 자기 영역 슬라이드 |

## 일정

| 날 | 마일스톤 | 내용 |
|---|---|---|
| 11/5 (목) | **M0 킥오프** | 미팅: 분야·난이도 결정, 담당 확정, 각 spec 미정 항목 1차 결정, 데이터 다운로드·검수(PDF 수 대조), Langfuse 프로젝트 생성, `.env.example`, 각자 로컬 환경(Python, Qdrant) 확인 |
| 11/6 (금) ~ 11/7 (토) | **M1 1문항 E2E** | 각 영역 1차 구현. 11/7 저녁: `naive`로 질문 1개 → 답변 + 출처 + Langfuse 트레이스 확인 |
| 11/8 (일) ~ 11/9 (월) | **M2 3방식 + 러너** | `hybrid`, `hybrid_rerank` 연결. 평가 러너로 질문 N개 × 3방식 실행. Hit/Recall 계산. RAGAS·Judge 1문항 통과. 평가 질문 목록 확정 |
| 11/10 (화) | **M3 동결·전체 실행** | 아침에 공통 설정 동결 → 전체 실행 → 자동 채점 → 운영 지표 집계. 보안 4개 실행 |
| 11/11 (수) | **M4 분석** | 비교표 완성, 대표 사례 원문 대조, 최종 구성 선택과 이유, 한계 정리. 자동 채점 오류 사람 확인 |
| 11/12 (목) | **M5 재실행·문서** | 깨끗한 환경에서 README대로 설치·실행 검증(다른 팀원이 수행). 발표자료 초안·리허설 1회 |
| 11/13 (금) 오전 | **M6 제출** | 최종 리허설, 팀 Notion에 저장소·발표자료(PPTX + PDF) 연결, 13:00 전 백오피스 제출 |

여유가 없다. 11/9까지 M2가 안 되면 11/10에 범위를 줄인다(질문 수 축소, 리랭커 단순화). 선택 과제는 M4 이후에만 논의한다.

## GitHub Issue · Project 운영

- **Issue = 작업 단위.** 영역 라벨(`ingestion`, `retrieval`, `service`, `evaluation`, `observability`, `docs`) + 마일스톤(M0~M6). 담당자 1명. PR 본문에 `Closes #N`.
- **Project 보드** 열: Backlog / This milestone / In progress / Review / Done. 리드가 매일 아침 확인하고 막힌 것은 당일 처리.
- **PR**은 [branch-strategy.md](branch-strategy.md)대로. 동작이나 인터페이스를 바꾸면 같은 PR에서 spec 갱신([documentation.md](documentation.md)).
- 인터페이스 변경은 Issue 제목 앞에 `[interface]`를 붙이고 의존 영역 담당자를 멘션한다.

### 초기 Issue 골격 (M0 직후 리드가 생성)

`ingestion`
- [ ] 데이터셋 폴더 구조·PDF 수 검수, `ingest-report.json` 형식 확정
- [ ] pypdf 추출 + 페이지 보존
- [ ] 청킹 전략 결정·구현 (크기, overlap, 표 보존)
- [ ] E5 모델명 확정, 임베딩
- [ ] Qdrant 컬렉션 스키마 확정 (dense + sparse 여부), 색인 명령
- [ ] spec 미정 항목 갱신

`retrieval`
- [ ] `retrieve()` 시그니처 구현 + `naive`
- [ ] 키워드 검색 방식 결정 (BM25 / sparse) + `hybrid` 결합(RRF 등)
- [ ] 리랭커 모델 선택, 로컬 실행 확인, `hybrid_rerank`
- [ ] 검색 스팬 기록 연결
- [ ] spec 미정 항목 갱신

`service` + `observability`
- [ ] FastAPI `/health`, `/query`, Pydantic 스키마, 422 처리
- [ ] 문맥 조립: 자료 ID 부여, 대응표, 토큰 한도
- [ ] 프롬프트 v1 (판단 순서, JSON 출력), `prompts/` 파일화
- [ ] LLM 호출 + timeout·재시도 + 출력 검증 + `error` 상태
- [ ] `answer()`, `answer_with_context(defense=)` 내부 함수
- [ ] Langfuse 트레이스·스팬·generation·score 연결, `eval` 트레이스 분리
- [ ] `.env.example`, Langfuse 확인 방법 README 절
- [ ] spec 미정 항목 갱신

`evaluation`
- [ ] 평가 JSON 로더 (`evidence_groups`, `expected_action`)
- [ ] 질문 선택 기준·목록 (`results/questions.json`)
- [ ] 일괄 실행 러너 → 실행 레코드 JSONL
- [ ] Hit@k, Recall@k (해당 없음 처리)
- [ ] RAGAS Faithfulness 연동 (해당 없음 처리)
- [ ] Judge 프롬프트·4항목 채점·null 처리
- [ ] 운영 지표 집계 (정상 평균·건수, 오류율, 토큰 합계·확인 수, 채점 호출 분리)
- [ ] 보안 비교 4개 (문맥 저장 → 기본/방어)
- [ ] 비교표 생성 (`results/comparison.md`)
- [ ] spec 미정 항목 갱신

`docs` (리드)
- [ ] 분야·난이도 결정 기록 (requirements.md)
- [ ] 담당자 확정 기록 (이 문서, README)
- [ ] README 설치·실행 절 뼈대
- [ ] 발표자료 뼈대
- [ ] 팀 Notion 페이지에 저장소 연결

## 11/5 미팅 안건

1. 분야·난이도 (Basic 권장: 8일 일정, 15 PDF면 색인·재실행 부담이 작고 최고 평가 가능)
2. 담당 확정 (A안 / B안)
3. spec 미정 항목 중 오늘 정할 것: k 기본값, 평가 LLM, Langfuse Cloud/셀프호스트, Python 버전·패키지 관리
4. 데이터 다운로드와 PDF 수 검수 당번
5. 매일 체크인 방식(Slack `proj_3rd`, 시간)

## 리스크

| 리스크 | 대응 |
|---|---|
| 리랭커·E5 로컬 실행이 느리거나 안 됨 | 11/7까지 확인. 안 되면 더 작은 모델로 교체, 조건 기록 |
| 프롬프트가 되묻기·보류를 못 가림 | 11/9 M2에서 추가 확인·보류 문항 각 1개 이상 통과를 조건으로 |
| 동결 후 설정 변경 유혹 | 바꾸면 전체 재실행. 리드가 막는다 |
| 평가 LLM 비용·한도 | 질문 수를 비용 안에서 정한다. 채점 토큰은 별도 집계 |
| 재실행 실패 | 11/12에 구현 안 한 사람이 README대로 설치 |
