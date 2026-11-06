"""운영 지표 집계 (발제 STEP 7, docs/evaluation.md).

측정값은 `platform`이 RunRecord에 남긴 것을 읽을 뿐이다.
- 정상 요청 = status != "error" (추가 확인·보류는 오류가 아니다).
- None(측정 못 함)은 분모에서 빼고, 전부 None이면 합계·평균도 None. 0으로 바꾸지 않는다.
- 평가(RAGAS·Judge) 호출의 시간·토큰은 RunRecord에 없으므로 여기에 섞이지 않는다.
- 빈 질문·모의 오류·보안 비교는 일반 오류율에 섞지 않는다. 호출하는 쪽에서 미리 걸러서 넘긴다.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from src.contracts import RunRecord


@dataclass(frozen=True)
class OpsSummary:
    retrieval_mode: str
    total: int  # 전체 일반 평가 요청 수
    ok_count: int  # 정상 처리 요청 수 (answered / needs_clarification / abstained)
    error_count: int  # 재시도 후에도 시스템 오류로 끝난 요청 수
    error_rate_pct: float | None  # error_count / total * 100
    ok_latency_mean_ms: float | None  # 정상 요청 평균 응답 시간
    ok_latency_known: int  # 위 평균에 쓴(시간을 잰) 정상 요청 수
    error_latency_mean_ms: float | None  # 실패 요청 시간도 따로 기록
    input_tokens_sum: int | None
    input_tokens_known: int  # 입력 토큰 사용량을 확인한 요청 수
    output_tokens_sum: int | None
    output_tokens_known: int


def _mean(values: list[int]) -> float | None:
    return sum(values) / len(values) if values else None


def _sum_known(values: Iterable[int | None]) -> tuple[int | None, int]:
    known = [v for v in values if v is not None]
    return (sum(known) if known else None), len(known)


def summarize_ops(records: Iterable[RunRecord]) -> dict[str, OpsSummary]:
    by_mode: dict[str, list[RunRecord]] = defaultdict(list)
    for r in records:
        by_mode[r.retrieval_mode].append(r)

    out: dict[str, OpsSummary] = {}
    for mode, rows in by_mode.items():
        ok = [r for r in rows if r.status != "error"]
        failed = [r for r in rows if r.status == "error"]
        ok_latencies = [r.latency_ms for r in ok if r.latency_ms is not None]
        err_latencies = [r.latency_ms for r in failed if r.latency_ms is not None]
        in_sum, in_known = _sum_known(r.input_tokens for r in rows)
        out_sum, out_known = _sum_known(r.output_tokens for r in rows)
        out[mode] = OpsSummary(
            retrieval_mode=mode,
            total=len(rows),
            ok_count=len(ok),
            error_count=len(failed),
            error_rate_pct=len(failed) / len(rows) * 100,
            ok_latency_mean_ms=_mean(ok_latencies),
            ok_latency_known=len(ok_latencies),
            error_latency_mean_ms=_mean(err_latencies),
            input_tokens_sum=in_sum,
            input_tokens_known=in_known,
            output_tokens_sum=out_sum,
            output_tokens_known=out_known,
        )
    return out
