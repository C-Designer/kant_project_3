"""동결 대상 설정의 단일 출처. k, 토큰 한도, 모델, timeout 같은 값을 다른 곳에 두지 않는다.

# TODO(미정) 표시는 뼈대용 잠정값이다. 11/9 아침 동결 전에 각 담당이 확정하고, 동결 후 변경은 [interface] PR + 전체 재실행.
키는 환경 변수(.env)로만 읽는다. 값을 이 파일에 쓰지 않는다.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "shipping"
DOCUMENTS_DIR = DATA_DIR / "documents"  # 색인 대상은 여기의 *.pdf뿐. evaluation/은 읽지 않는다
INGEST_REPORT_PATH = DATA_DIR / "ingest-report.json"

# 검색 (세 방식 공통)
K = 5  # 확정 (2026-11-05 킥오프)
CHUNK_SIZE = 900  # 확정(Basic, 개발용·추가 질문 비교). 쪽이 이보다 길면 문장 끝에서 균등 분할
CHUNK_OVERLAP = 0  # 확정. 겹침은 지원하지 않는다(0이 아니면 chunk_pages가 거부)
EMBEDDING_MODEL = "intfloat/multilingual-e5-small"  # TODO(미정, #14) 로컬 E5 계열
QDRANT_URL = os.environ.get("QDRANT_URL") or None  # Mac Studio의 공용 Qdrant 서버. 없으면 아래 로컬 폴더로 대체
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY") or None  # 공용 Qdrant 접속 키. 서버 Mac은 비워 두고 인증 프록시가 키를 붙인다
QDRANT_PATH: Path | None = DATA_DIR / "qdrant"  # QDRANT_URL이 없을 때만 쓰는 로컬 저장소. None이면 메모리 (테스트용)
COLLECTION = "shipping_chunks"  # TODO(미정, #14)
QDRANT_TIMEOUT_SEC = 40  # 공용 Qdrant 한 번 호출의 제한 시간(초). 정하지 않으면 HTTP 기본값(약 5초)이 적용돼 서버가 한 번 느리면 요청이 실패한다(#106)
QDRANT_MAX_RETRIES = 2  # 시간 초과·502·503·504일 때만 다시 시도하는 횟수. 401·404는 재시도하지 않는다(#106)

# 하이브리드·리랭커 (hybrid, hybrid_rerank 구현 시 채운다)
HYBRID_FUSION = "rrf"  # 확정. 순위 합치기(RRF). 상수(K=60)와 후보 수(POOL=20)는 retrieve.py
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"  # 확정. 한국어를 포함한 다국어 cross-encoder
RERANK_CANDIDATES = 20  # 확정. hybrid가 리랭커에 넘기는 후보 수

# 생성
GENERATION_MODEL = "gpt-6-luna"
GENERATION_TEMPERATURE: float | None = None  # gpt-6-luna는 기본값(1) 외 거부. None이면 모델에 보내지 않는다
CONTEXT_TOKEN_LIMIT = 3000  # 확정 (#18). 입력 문맥 토큰 한도(count_tokens 추정치). Basic k=5 실측 최대 1,857이라 잘리지 않는 안전 한도
LLM_TIMEOUT_SEC = 30.0  # 확정 (platform, 2026-11-09). 호출 1회의 timeout
LLM_MAX_RETRIES = 2  # 확정 (platform, 2026-11-09). 호출 실패 시 재시도 횟수
REGENERATE_MAX = 1  # TODO(미정, #20) 출력 검증 실패 시 재생성 횟수

# 평가
EVAL_MODEL: str | None = "gpt-6-luna"  # 확정 (#58). None이면 평가 호출은 거부된다
FAITHFULNESS_REPEATS = 3  # Faithfulness를 몇 번 채점해 평균낼지. gpt-6-luna는 temperature를 못 고정해 같은 답안도 값이 흔들린다. 세 방식에 같은 값

# 트레이스
TRACE_USER = os.environ.get("TRACE_USER") or None  # Langfuse user_id로 쓰는 각자의 이름·별칭. API 요청은 Cloudflare Access 로그인 계정을 쓴다

# 기록 (선택)
RUN_LOG_PATH: Path | None = None  # 지정하면 run_query가 RunRecord를 JSONL로 덧붙인다


def env(name: str) -> str | None:
    """환경 변수 읽기. 없으면 None (빈 문자열도 None)."""
    return os.environ.get(name) or None
