# Recall(재현율) 쉽게 이해하기

문맥 한도 실험(EXP-0020~0023)의 검색 지표 Recall과 Hit를 처음 보는 사람이 읽도록 정리한 문서다. 계산 코드는 `src/metrics/retrieval_metrics.py`(공식)와 `scripts/experiments/search/grid_kset.py`의 `retrieval_metrics`(3단계, 그룹 단위)다. 공식 정의는 [docs/evaluation.md](../../../docs/evaluation.md)에 있다.

## 1. 한 줄 요약

> **Recall = 정답 자료 중에서 검색이 실제로 가져온 비율**

도서관 사서에게 "이 질문에 답하려면 책 A와 책 B가 필요하다"고 했는데 가져온 책 더미에 A만 있으면 Recall은 2권 중 1권이라 **0.5**다. 답변이 절반만 맞았다는 뜻이 아니라 **필요한 자료를 얼마나 빠짐없이 가져왔나**를 재는 값이다.

## 2. 용어

| 용어 | 뜻 | 예 |
|---|---|---|
| 골든 문항 | 정답을 아는 평가용 질문 | "선박 평형수 규정은?" |
| 근거(evidence) | 답하려면 찾아야 하는 문서·쪽·인용문 | `SB01` 문서의 18쪽 |
| `book_id` | 문서 번호 | `SB01`, `SB14` |
| `page` | 쪽 번호 | 18 |
| `quote` | 근거 문장 원문 | "…평형수는 …" |
| 청크 | 문서를 잘라 놓은 조각(검색 단위) | `SB01-p18-c1` |
| k | 검색이 가져오는 청크 수 | k=5면 5개 |
| 문맥 한도 | LLM에게 넘길 수 있는 토큰 상한(3000 등) | 넘치면 뒤 청크는 빠진다 |

## 3. 근거 그룹: 대안이 있다

근거는 **그룹**으로 묶여 있고, 그룹 안의 항목은 **대안**이다. 하나만 찾아도 그 그룹은 충족이다.

```
evidence_groups = [
   [ SB01 18쪽 , SB14 7쪽 ],   ← 그룹1: 둘 중 하나만 찾으면 충족
   [ SB06 3쪽 ]                ← 그룹2: 이것은 꼭 찾아야 함
]
```

근거가 있는 56문항 중 49문항에 이런 대안이 있다.

## 4. Recall을 3단계로 나눠 본다

같은 검색 결과를 얼마나 엄격하게 보느냐에 따라 세 가지로 계산한다.

| 단계 | 이름 | "찾았다"의 기준 | 엄격함 |
|---|---|---|---|
| ① | Recall(문서) | `book_id`만 맞으면 | 느슨 |
| ② | Recall(쪽) | `book_id`와 `page`가 둘 다 맞으면 | 중간 |
| ③ | Recall(쪽+인용문) | 쪽이 맞고 청크 본문에 `quote`가 들어 있으면 | 엄격 |

그룹 단위로 볼 때 ③ ≤ ②다. ③은 ②에 조건 하나를 더한 것이기 때문이다. ①은 대안을 모두 세는 공식 정의라 그룹 단위 값과 직접 비교하지 않는다(5절).

### ① Recall(문서): 발제의 공식 정의

```
Recall(문서) = |찾은 문서 ∩ 근거 문서 전체| ÷ |근거 문서 전체|
```

```python
def hit_recall(evidence_book_ids, retrieved_book_ids, k):
    evidence = set(evidence_book_ids)              # 정답 문서 집합
    if not evidence:
        return RetrievalScore(None, None, "참고 근거 문서 목록이 비어 있다")

    found = evidence & set(retrieved_book_ids[:k]) # 정답 ∩ 검색된 문서
    return RetrievalScore(
        hit=1 if found else 0,                     # 하나라도 찾았나
        recall=len(found) / len(evidence),         # 찾은 비율
    )
```

**주의: 공식은 대안을 전부 센다.** 위 그룹 예시의 근거 문서는 `{SB01, SB14, SB06}` 3개다. 검색이 `SB01`과 `SB06`만 가져와도 그룹 둘 다 충족했지만 점수는 2/3 = 0.67이다. 그래서 대안이 있는 문항에서는 실제보다 낮게 나온다.

### ② Recall(쪽): 그룹 단위

```
Recall(쪽) = 충족한 그룹 수 ÷ 전체 그룹 수
```

```python
pg = [any(c.metadata.book_id == e["book_id"] and c.metadata.page == e["page"]
          for e in g for c in chunks)              # g = 한 그룹, e = 그 안의 대안
      for g in groups]
recall_page = sum(pg) / len(pg)
```

- 그룹마다 "대안 중 하나라도, 가져온 청크 중 하나라도" 문서와 쪽이 일치하면 충족이다.
- 위 예시에서 `SB01` 18쪽과 `SB06` 3쪽을 찾았다면 그룹 2개 모두 충족이라 1.0이다.
- 문서는 맞고 쪽이 틀리면 ①은 맞고 ②는 틀린다.

### ③ Recall(쪽+인용문): 가장 엄격

```
Recall(쪽+인용문) = (쪽이 맞고 청크 본문에 quote 앞 40자가 든 그룹 수) ÷ 전체 그룹 수
```

```python
def hit_pq(c, e):   # c = 청크, e = 근거 하나
    return (c.metadata.book_id == e["book_id"]
            and c.metadata.page == e["page"]
            and ns(e["quote"])[:40] in ns(c.text))   # ns = 공백과 '|'를 지운 문자열

pq = [any(hit_pq(c, e) for e in g for c in chunks) for g in groups]
recall_pq = sum(pq) / len(pq)
```

- 같은 쪽이어도 청크가 그 쪽의 다른 부분이면 불충족이다. 정답 문장이 실제로 청크에 들어 있어야 한다.
- 청크 크기를 바꾸면 가장 민감하게 변하는 지표다.

## 5. Hit: "하나라도 찾았나" (문항당 0 또는 1)

Recall이 "얼마나 찾았나"라면 Hit는 "하나라도 찾았나"다. 같은 3단계로 계산한다.

```python
hit      = bool(got & ref)   # 문서: 정답 문서와 겹치는 것이 하나라도
hit_page = any(pg)           # 쪽: 그룹 중 하나라도 쪽이 맞음
hit_pq   = any(pq)           # 쪽+인용문: 그룹 중 하나라도 인용문까지 맞음
```

## 6. 전체 계산 코드 (`grid_kset.py`의 `retrieval_metrics`)

```python
def retrieval_metrics(gold, chunks):
    """chunks = 문맥 한도에 실제로 들어간 앞부분 청크. 근거 그룹이 없으면 None."""
    groups = groups_of(gold)
    if not groups:
        return None
    ref = set().union(*[{e["book_id"] for e in g} for g in groups])  # 모든 대안 문서
    got = {c.metadata.book_id for c in chunks}
    pq = [any(hit_pq(c, e) for e in g for c in chunks) for g in groups]
    pg = [any(c.metadata.book_id == e["book_id"] and c.metadata.page == e["page"]
              for e in g for c in chunks) for g in groups]
    return dict(
        recall_book=len(got & ref) / len(ref), hit=bool(got & ref),    # ① 문서(공식)
        hit_page=any(pg), hit_pq=any(pq),                              # Hit 쪽, 쪽+인용문
        recall_page=sum(pg) / len(pg), all_page=all(pg),               # ② 쪽
        recall_pq=sum(pq) / len(pq), all_pq=all(pq),                   # ③ 쪽+인용문
        all_book=all(any(c.metadata.book_id == e["book_id"]
                         for e in g for c in chunks) for g in groups), # 모든 그룹 충족
    )
```

`all_*`는 "모든 그룹을 충족했는가"(0/1)이고, 결과 표의 "모든그룹 충족률"이 이 값의 평균이다.

## 7. 실제 예 (`development/S-DEV-01`)

- 골든 근거 문서는 `SB01`, `SB14`다(한 그룹 안의 대안).
- 가져온 문서는 `SB01` 하나다.
- Recall(문서)은 1/2 = **0.50**이다. 대안 `SB14`를 안 가져왔다고 깎인다.
- 쪽+인용문(그룹)은 **1.00**이다. 그룹이 하나뿐이고 `SB01` 청크에 정답 문장이 있었다.

공식 Recall은 0.5인데 실제로는 정답 근거를 찾은 경우다. 이런 문항이 많아서 공식 값이 낮게 보인다.

## 8. 읽을 때 기억할 것

1. 근거가 없는 문항(보류·되묻기 등)은 점수가 `None`이고 분모에서 빠진다. 그래서 72문항 중 **68문항**으로 평균을 낸다.
2. 문맥 한도에서 밀려난 청크는 못 찾은 것으로 친다. LLM이 못 보기 때문이다.
3. ①이 발제의 **공식 지표**다. ②, ③과 "그룹 단위" 값은 대안을 공정하게 보려고 만든 **보조 지표**다.
4. ③의 "quote 앞 40자"는 우리가 정한 기준이다. 청크 경계에서 quote가 잘리거나 표기가 다르면 실제로 찾았어도 놓친 것으로 나올 수 있다.
5. Recall이 높아도 답변이 맞다는 보장은 없다(`docs/evaluation.md`).
6. EXP-0014 분석에서 Recall 개선은 대부분 k를 키운 효과였다([0024 분석](../../../docs/experiments/search/0024-recall-analysis-best-settings.md)).

## 9. 결과 표의 "폴더" 열

`merge_grid_results.py`는 여러 노트북의 결과 폴더를 `--in`으로 받아 한 표로 합친다. 표의 "폴더" 열은 그 값이 어느 결과 폴더(노트북)에서 왔는지 보여 준다. 본 실행에서는 `laptop1`~`laptop4`가 나온다.
