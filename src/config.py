"""동결 대상 설정의 단일 출처. k, 토큰 한도, 모델, timeout 같은 값을 다른 곳에 두지 않는다.

# TODO(미정) 표시는 뼈대용 잠정값이다. 11/10 아침 동결 전에 각 담당이 확정하고, 동결 후 변경은 [interface] PR + 전체 재실행.
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
CHUNK_SIZE = 800  # TODO(미정, #13) 글자 수
CHUNK_OVERLAP = 100  # TODO(미정, #13)
EMBEDDING_MODEL = "intfloat/multilingual-e5-small"  # TODO(미정, #14) 로컬 E5 계열
QDRANT_URL = os.environ.get("QDRANT_URL") or None  # 팀 VM의 Qdrant 서버 (확정, #58). 없으면 아래 로컬 폴더로 대체
QDRANT_PATH: Path | None = DATA_DIR / "qdrant"  # QDRANT_URL이 없을 때만 쓰는 로컬 저장소. None이면 메모리 (테스트용)
COLLECTION = "shipping_chunks"  # TODO(미정, #14)

# 하이브리드·리랭커 (hybrid, hybrid_rerank 구현 시 채운다)
HYBRID_FUSION: str | None = None  # TODO(미정, #15)
RERANKER_MODEL: str | None = None  # TODO(미정, #16)
RERANK_CANDIDATES: int | None = None  # TODO(미정, #16)

# 생성
GENERATION_MODEL = "gpt-6-luna"
GENERATION_TEMPERATURE: float | None = None  # gpt-6-luna는 기본값(1) 외 거부. None이면 모델에 보내지 않는다
CONTEXT_TOKEN_LIMIT = 3000  # TODO(미정, #18) 입력 문맥 토큰 한도
LLM_TIMEOUT_SEC = 30.0  # TODO(미정, #39)
LLM_MAX_RETRIES = 2  # TODO(미정, #39) 호출 실패 시 재시도 횟수
REGENERATE_MAX = 1  # TODO(미정, #20) 출력 검증 실패 시 재생성 횟수

# 평가
EVAL_MODEL: str | None = "gpt-6-luna"  # 확정 (#58). None이면 평가 호출은 거부된다

# 기록 (선택)
RUN_LOG_PATH: Path | None = None  # 지정하면 run_query가 RunRecord를 JSONL로 덧붙인다


def env(name: str) -> str | None:
    """환경 변수 읽기. 없으면 None (빈 문자열도 None)."""
    return os.environ.get(name) or None
