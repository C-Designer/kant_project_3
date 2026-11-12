"""청크 크기 x 오버랩 x k 격자 실험을 한 노트북에서 돌린다 (EXP-0016~0019 담당별 실행 스크립트, 탐색용).

저장소 루트에서 실행한다. 다른 폴더·개인 경로는 필요 없다.

    uv run python scripts/experiments/search/grid_kset.py --k 4,11 --out results/exp0016/laptop1

단계(--stages, 쉼표로 여러 개. 기본 all = check,retrieval,answers,e2e,ragas):
    check      환경 점검 + 모델 설치(없으면 내려받음) + GPU 메모리 상한 점검. env.json 저장
    retrieval  색인 + 검색 지표(Hit·Recall) + 검색 시간. LLM 호출 없음
    answers    답변 행동 일치율, 토큰 (병렬 --workers)
    e2e        전체 시간(retrieve~답변). LLM 직렬. 크기 전부 x hybrid_rerank x --k + 앵커
    ragas      RAGAS faithfulness(3회 평균). 외부 LLM 호출만, 병렬 --ragas-workers
끝난 설정은 파일로 남고 다시 실행하면 건너뛴다(이어하기). 인터넷이 끊겨도 같은 명령으로 이어서 돈다.

GPU torch가 없으면 `uv run --with torch==2.15.0+cu132 --index https://download.pytorch.org/whl/cu132`로 스스로 다시 실행한다(`--no-auto-torch`로 끔).
저장소 코드(src/)는 고치지 않는다. 오버랩은 저장소 청킹이 지원하지 않아(overlap!=0이면 ValueError) 이 스크립트 안에서 chunk_pages를 감싸 구현한다.
"""
import argparse
import importlib.metadata as md
import os
import shutil
import subprocess
import sys

TORCH_PIN = "torch==2.15.0+cu132"
TORCH_INDEX = "https://download.pytorch.org/whl/cu132"
MODES = ("naive", "hybrid", "hybrid_rerank")
SETS = ("development", "additional", "expansion_validation")
BASE = (900, 0, 5)  # 확정값: 크기, 오버랩%, k


def parse():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--k", required=True, help="이 담당의 k 목록, 예: 4,11")
    p.add_argument("--out", required=True, help="결과 폴더, 예: results/exp0016/laptop1")
    p.add_argument("--stages", default="all")
    p.add_argument("--sizes", default="100,200,300,400,500,600,700,800,900")
    p.add_argument("--pcts", default="0,10,20")
    p.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    p.add_argument("--threads", type=int, default=8)
    p.add_argument("--cpu-cores", type=int, default=0, help="프로세스가 쓸 수 있는 논리 코어 수(0이면 --threads와 같게). 스레드 수와 별개로 코어 자체를 제한한다")
    p.add_argument("--min-free-ram-gb", type=float, default=8.0, help="시작 전 여유 RAM이 이보다 적으면 중단")
    p.add_argument("--allow-battery", action="store_true", help="배터리로 실행(시간 측정이 흔들리므로 비권장)")
    p.add_argument("--expect-gpu", default="RTX 5060", help="노트북 사이 비교를 위해 GPU 이름에 이 글이 들어 있어야 한다(빈 값이면 검사 안 함)")
    p.add_argument("--expect-fingerprint", default="", help="기준 노트북의 환경 지문(env.json의 env_fingerprint). 주면 다르면 시작 전에 중단한다")
    p.add_argument("--gpu-fraction", type=float, default=0.5, help="프로세스당 GPU 메모리 비율(8GB x 0.5 = 4GB)")
    p.add_argument("--workers", type=int, default=24, help="답변 호출 병렬 수(키를 공유하면 12)")
    p.add_argument("--ragas-workers", type=int, default=8)
    p.add_argument("--limit-q", type=int, default=0, help="시험 실행용: 세트마다 앞의 N문항만")
    p.add_argument("--modes", default="naive,hybrid,hybrid_rerank")
    p.add_argument("--context-max", default="3000", help="문맥 토큰 한도 목록, 예: 3000,3400,3800,4200 (기본은 저장소 확정값 3000 하나)")
    p.add_argument("--k-order", choices=("asc", "desc"), default="asc", help="k를 도는 순서. desc = 큰 k부터")
    p.add_argument("--e2e-modes", default="hybrid_rerank", help="직렬 전체 시간(검색~LLM 답변)을 재는 방식 목록. 방식마다 시간이 그만큼 더 걸린다")
    p.add_argument("--e2e-workers", type=int, default=1, help="전체 시간 측정에서 LLM 호출을 동시에 내보내는 수. 1 = 직렬(단독 호출 시간). 검색은 항상 직렬. 2 이상이면 LLM 시간에 동시 호출 부하가 섞인다")
    p.add_argument("--ragas-sizes", default="500,900", help="faithfulness를 재는 청크 크기 목록")
    p.add_argument("--ragas-sample", choices=("odd", "all"), default="odd", help="odd = 세트마다 홀수 번째 문항만, all = 전체")
    p.add_argument("--no-auto-torch", action="store_true")
    return p.parse_args()


A = parse()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows 콘솔(cp949)에서 한글이 깨지지 않게
# --- torch를 불러오기 전에 장치·스레드 한도를 건다 -----------------------------------------
if A.device == "cpu":
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[_v] = str(A.threads)  # BLAS·numexpr 등 torch 밖의 스레드 풀도 같은 한도로
for _v in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST", "QDRANT_URL", "QDRANT_API_KEY"):
    os.environ[_v] = ""  # 메모리 Qdrant만 쓴다. 공용 Qdrant에 색인하지 않는다
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

if A.device == "cuda" and not A.no_auto_torch and not os.environ.get("GRID_REEXEC"):
    try:
        has_cuda_build = "+cu" in md.version("torch")
    except md.PackageNotFoundError:
        has_cuda_build = False
    if not has_cuda_build:
        if not shutil.which("uv"):
            sys.exit("GPU용 torch가 없고 uv도 없다. uv를 설치하거나 --device cpu로 돌린다.")
        print(f"GPU용 torch가 없어 {TORCH_PIN}로 다시 실행한다(처음 한 번 내려받는다)", flush=True)
        os.environ["GRID_REEXEC"] = "1"
        cmd = ["uv", "run", "--with", TORCH_PIN, "--index", TORCH_INDEX, "python", *sys.argv]
        sys.exit(subprocess.call(cmd))

import asyncio  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import pickle  # noqa: E402
import platform as pf  # noqa: E402
import re  # noqa: E402
import statistics  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import warnings  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import torch  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
torch.set_num_threads(A.threads)
try:
    torch.set_num_interop_threads(min(A.threads, 4))
except RuntimeError:
    pass  # 이미 병렬 작업이 시작된 뒤에는 바꿀 수 없다
if A.device == "cuda" and torch.cuda.is_available():
    torch.cuda.set_per_process_memory_fraction(A.gpu_fraction)


# --- 컴퓨팅 한도: 걸고, 걸렸는지 다시 읽어 확인하고, 실행 중 사용량을 남긴다 ------------------------------------
import ctypes  # noqa: E402


def limit_cpu_cores(n):
    """프로세스를 첫 n개 논리 코어에만 묶는다(자식 프로세스도 상속). 반환: 실제 적용된 코어 수(못 걸면 None)."""
    total = os.cpu_count() or n
    if n >= total:
        return total
    try:
        if os.name == "nt":
            k32 = ctypes.windll.kernel32
            k32.GetCurrentProcess.restype = ctypes.c_void_p
            h = k32.GetCurrentProcess()
            k32.SetProcessAffinityMask(ctypes.c_void_p(h), ctypes.c_size_t((1 << n) - 1))
            pm, sm = ctypes.c_size_t(), ctypes.c_size_t()
            k32.GetProcessAffinityMask(ctypes.c_void_p(h), ctypes.byref(pm), ctypes.byref(sm))
            return bin(pm.value).count("1")
        os.sched_setaffinity(0, set(range(n)))
        return len(os.sched_getaffinity(0))
    except Exception:
        return None


def mem_gb():
    """(이 프로세스 최대 메모리 GB, 시스템 여유 메모리 GB). 못 구하면 None."""
    try:
        if os.name == "nt":
            class PMC(ctypes.Structure):
                _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong), ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

            class MEM(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong), ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]

            pmc = PMC()
            pmc.cb = ctypes.sizeof(PMC)
            ctypes.windll.kernel32.GetCurrentProcess.restype = ctypes.c_void_p
            ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.c_void_p(ctypes.windll.kernel32.GetCurrentProcess()), ctypes.byref(pmc), pmc.cb)
            m = MEM()
            m.dwLength = ctypes.sizeof(MEM)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return round(pmc.PeakWorkingSetSize / 1e9, 2), round(m.ullAvailPhys / 1e9, 1)
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024 / 1e9  # Linux는 KB
        return round(peak, 2), round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_AVPHYS_PAGES") / 1e9, 1)
    except Exception:
        return None, None


def gpu_sample():
    """nvidia-smi로 GPU 온도·클럭·전력·스로틀 사유를 한 번 읽는다(시간 측정이 열·전력 제한에 흔들렸는지 보려는 기록)."""
    try:
        o = subprocess.run(["nvidia-smi", "--query-gpu=temperature.gpu,clocks.sm,power.draw,utilization.gpu,clocks_throttle_reasons.active",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10).stdout.split(",")
        reasons = int(o[4].strip(), 16)
        return dict(temp_c=float(o[0]), sm_mhz=float(o[1]), power_w=float(o[2]), util=float(o[3]), throttle_hex=hex(reasons),
                    thermal_or_hw_slowdown=bool(reasons & (0x8 | 0x20 | 0x40 | 0x80 | 0x100)))  # 하드웨어 감속·열 제한 비트
    except Exception:
        return None


CPU_CORES = A.cpu_cores or A.threads
APPLIED_CORES = limit_cpu_cores(CPU_CORES)

from src import config  # noqa: E402
from src.answer import chain  # noqa: E402
from src.answer.context import build_context, count_tokens  # noqa: E402
from src.platform import llm  # noqa: E402
from src.search import chunking, embed, index, keyword, rerank, retrieve, store  # noqa: E402

DATA = ROOT / "data" / "shipping"
OUT = Path(A.out)
KS = sorted({int(x) for x in A.k.split(",")}, reverse=A.k_order == "desc")  # 이후 모든 단계가 이 순서로 k를 돈다
SIZES = [int(x) for x in A.sizes.split(",")]
PCTS = [int(x) for x in A.pcts.split(",")]
MODES = tuple(A.modes.split(","))
E2E_MODES = tuple(A.e2e_modes.split(","))
CTXS = sorted({int(x) for x in A.context_max.split(",")}, reverse=True)  # 큰 한도부터(= 한도 없음에 가까운 쪽이 기준)
RAGAS_SIZES = [int(x) for x in A.ragas_sizes.split(",")]
KMAX = 11
assert KMAX >= max(KS), "KMAX보다 큰 k는 지원하지 않는다"
STAGES = ["check", "retrieval", "answers", "e2e", "ragas"] if A.stages == "all" else A.stages.split(",")
ns = lambda s: re.sub(r"[\s|]+", "", s)  # noqa: E731
STATUS_OF = {"answer": "answered", "clarify": "needs_clarification", "abstain": "abstained"}
T0 = time.time()


def log(msg):
    print(f"[{time.time() - T0:6.0f}s] {msg}", flush=True)


def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8", newline="\n")
    tmp.replace(path)  # 쓰다 끊겨도 반쪽 파일이 남지 않게


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


# --- 오버랩(저장소 청킹은 지원하지 않으므로 여기서 구현) --------------------------------------
_OV = 0
_orig_chunk_pages = chunking.chunk_pages


def _chunk_pages_ov(file_name, pages, *, size, overlap):
    out = _orig_chunk_pages(file_name, pages, size=size, overlap=0)
    if not _OV:
        return out
    res = []
    for i, (text, meta) in enumerate(out):
        if i and out[i - 1][1].book_id == meta.book_id and out[i - 1][1].page == meta.page:
            head, nl, body = text.rpartition("\n")
            tail = out[i - 1][0].rpartition("\n")[2][-_OV:]  # 겹침은 앞 청크의 겹침 전 본문 기준
            sp = tail.find(" ")
            if 0 <= sp < len(tail) - 1:
                tail = tail[sp + 1:]  # 단어 중간에서 시작하지 않게
            text = head + nl + tail + body
        res.append((text, meta))
    return res


chunking.chunk_pages = _chunk_pages_ov

# --- 문서 임베딩 캐시(같은 글은 다시 계산하지 않음. 결과는 캐시와 무관) -----------------------------
EMB_PATH = OUT / "emb_cache.pkl"
_cache = pickle.loads(EMB_PATH.read_bytes()) if EMB_PATH.exists() else {}
_orig_embed = embed.embed_passages


def _cached_embed(texts):
    keys = [hashlib.sha1(f"{config.EMBEDDING_MODEL}|{t}".encode()).hexdigest() for t in texts]
    miss = [i for i, k in enumerate(keys) if k not in _cache]
    if miss:
        for i, v in zip(miss, _orig_embed([texts[i] for i in miss])):
            _cache[keys[i]] = np.asarray(v, dtype=np.float32)
    return [_cache[k].tolist() for k in keys]


embed.embed_passages = _cached_embed


def build(size, pct):
    """크기·오버랩 설정으로 메모리 Qdrant에 색인하고 모델을 미리 불러 로딩 시간을 시간 측정에서 뺀다."""
    global _OV
    _OV = round(size * pct / 100)
    config.CHUNK_SIZE = size
    config.EMBEDDING_MODEL = "intfloat/multilingual-e5-small"
    config.QDRANT_URL = None
    config.QDRANT_PATH = None
    embed._model = None
    store.reset_client()
    keyword.reset()
    config.RERANK_CANDIDATES = 20  # POOL 20 고정 (hybrid: 각 20개, hybrid_rerank: 후보 20개)
    retrieve.POOL = 20
    rep = index.build_index(DATA / "documents")
    if rep["failed"]:
        raise RuntimeError(f"색인 실패: {rep['failed']}")
    OUT.mkdir(parents=True, exist_ok=True)
    EMB_PATH.write_bytes(pickle.dumps(_cache))
    keyword.reset()
    for m in {*MODES, "hybrid_rerank"}:  # e2e 단계가 hybrid_rerank를 쓰므로 항상 준비
        retrieve.retrieve("준비 질문", m, 5)
    return rep["chunks"]


# --- 질문 --------------------------------------------------------------------------------------
def load_questions():
    ev = {}
    for s in SETS:
        qs = load_json(DATA / "evaluation" / f"{s}_questions.json")
        ans = {a["id"]: a for a in load_json(DATA / "evaluation" / f"{s}.json")}
        if A.limit_q:
            qs = qs[: A.limit_q]
        for i, q in enumerate(qs):
            ev[f"{s}/{q['id']}"] = dict(set=s, idx=i, question=q["question"], gold=ans[q["id"]])
    # 보고서용: 질문과 골든(정답 문장 reference_answer, 필수 사실, 금지 주장, 근거 quote). 채점·보고에만 쓰고 검색·답변에는 넣지 않는다
    save_json(OUT / "questions.json", {qid: dict(
        set=q["set"], question=q["question"], expected_action=q["gold"]["expected_action"],
        reference_answer=q["gold"].get("reference_answer"), required_facts=q["gold"].get("required_facts", []),
        forbidden_claims=q["gold"].get("forbidden_claims", []), grading_notes=q["gold"].get("grading_notes"),
        evidence_groups=[[dict(book_id=e["book_id"], page=e["page"], quote=e["quote"]) for e in g] for g in groups_of(q["gold"])],
    ) for qid, q in ev.items()})
    return ev


def groups_of(gold):
    return [g for g in gold.get("evidence_groups", []) if g]


def hit_pq(c, e):
    return c.metadata.book_id == e["book_id"] and c.metadata.page == e["page"] and ns(e["quote"])[:40] in ns(c.text)


def retrieval_metrics(gold, chunks):
    """chunks = 3000토큰 한도에 들어간 앞부분. 근거 그룹이 없으면 None."""
    groups = groups_of(gold)
    if not groups:
        return None
    ref = set().union(*[{e["book_id"] for e in g} for g in groups])
    got = {c.metadata.book_id for c in chunks}
    pq = [any(hit_pq(c, e) for e in g for c in chunks) for g in groups]  # 쪽 + 인용문(앞 40자)
    pg = [any(c.metadata.book_id == e["book_id"] and c.metadata.page == e["page"] for e in g for c in chunks) for g in groups]  # 문서 + 쪽(인용문은 안 봄)
    return dict(
        recall_book=len(got & ref) / len(ref), hit=bool(got & ref),  # 문서(book_id): 공식 정의(모든 그룹의 모든 대안 문서)
        hit_page=any(pg), hit_pq=any(pq),  # Hit 3단계: 문서(hit) / 쪽 / 쪽+인용문 중 하나라도 찾았는가
        recall_page=sum(pg) / len(pg), all_page=all(pg),  # 쪽(book_id+page): 그룹 단위
        recall_pq=sum(pq) / len(pq), all_pq=all(pq),  # 쪽+인용문: 그룹 단위
        all_book=all(any(c.metadata.book_id == e["book_id"] for e in g for c in chunks) for g in groups),  # 문서 모든그룹(그룹마다 대안 하나면 충족)
    )


def ks_for(size, pct):
    """이 설정에서 보는 k(--k-order 순서 유지). 확정값 설정(900자·0%)에는 기준 k=5를 덧붙인다."""
    return KS + ([BASE[2]] if (size, pct) == BASE[:2] and BASE[2] not in KS else [])


def settings():
    s = [(z, p) for z in SIZES for p in PCTS]
    if BASE[:2] not in s:
        s.append(BASE[:2])
    return s


# --- 단계 0: 점검·설치 ------------------------------------------------------------------------
def git(*a):
    try:
        return subprocess.run(["git", *a], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    except OSError:
        return ""


def ensure_models():
    from huggingface_hub import snapshot_download

    for repo in (config.EMBEDDING_MODEL, config.RERANKER_MODEL):
        try:
            snapshot_download(repo, local_files_only=True)
            log(f"모델 있음: {repo}")
            continue
        except Exception:
            pass
        for attempt in range(1, 4):
            try:
                log(f"모델 내려받는 중: {repo} (시도 {attempt}/3)")
                snapshot_download(repo)
                break
            except Exception as e:
                log(f"내려받기 실패: {type(e).__name__}: {str(e)[:150]}")
                if attempt == 3:
                    sys.exit(f"모델 {repo}를 받지 못했다. 인터넷 연결을 확인하고 같은 명령을 다시 실행한다.")
                time.sleep(10 * attempt)


def hw_info():
    """computing_env: 노트북 사양·전원 상태를 최대한 자동으로 남긴다(못 구한 값은 None)."""
    info = dict(cpu_name=None, ram_total_gb=None, power_plan=None, on_ac_power=None)
    try:
        if os.name == "nt":
            ps = lambda c: subprocess.run(["powershell", "-NoProfile", "-Command", c], capture_output=True, text=True, timeout=20).stdout.strip()  # noqa: E731
            info["cpu_name"] = ps("(Get-CimInstance Win32_Processor).Name") or None
            ram = ps("(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory")
            info["ram_total_gb"] = round(int(ram) / 1e9, 1) if ram.isdigit() else None
            info["power_plan"] = subprocess.run(["powercfg", "/getactivescheme"], capture_output=True, text=True, timeout=10).stdout.strip() or None
            ac = ps("(Get-CimInstance -Namespace root/WMI -ClassName BatteryStatus -ErrorAction SilentlyContinue | Select-Object -First 1).PowerOnline")
            info["on_ac_power"] = {"True": True, "False": False}.get(ac)
        else:
            info["cpu_name"] = pf.processor() or None
            info["ram_total_gb"] = round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9, 1)
    except Exception:
        pass
    return info


def identity():
    """노트북 사이에 **같아야 하는 것**을 모은다(소프트웨어 버전, 모델 판본, 데이터·프롬프트 지문, 고정 설정, 컴퓨팅 한도).
    시간처럼 실행마다 달라지는 값은 넣지 않는다. 이 사전을 해시한 것이 환경 지문(env_fingerprint)이다."""
    from urllib.parse import urlparse

    from huggingface_hub import snapshot_download

    def ver(n):
        try:
            return md.version(n)
        except md.PackageNotFoundError:
            return None

    def sha(paths):
        h = hashlib.sha256()
        for p in sorted(paths):
            h.update(p.name.encode())
            h.update(hashlib.sha256(p.read_bytes()).digest())
        return h.hexdigest()[:12]

    def rev(repo):
        try:
            return Path(snapshot_download(repo, local_files_only=True)).name[:12]  # HF 스냅샷 폴더 이름 = 모델 커밋 해시
        except Exception:
            return None

    try:
        driver = subprocess.run(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"], capture_output=True, text=True, timeout=10).stdout.strip()
    except OSError:
        driver = None
    host = urlparse(config.env("OPENAI_BASE_URL") or "").hostname
    names = ("RERANKER_MODEL", "EMBEDDING_MODEL", "GENERATION_MODEL", "EVAL_MODEL", "CONTEXT_TOKEN_LIMIT", "LLM_TIMEOUT_SEC", "LLM_MAX_RETRIES", "REGENERATE_MAX", "FAITHFULNESS_REPEATS")
    return dict(
        python=sys.version.split()[0], torch=torch.__version__, cuda_runtime=torch.version.cuda, nvidia_driver=driver,
        packages={n: ver(n) for n in ("sentence-transformers", "transformers", "huggingface-hub", "ragas", "numpy", "qdrant-client", "langchain-core", "langchain-openai", "pypdf")},
        uv_lock=sha([ROOT / "uv.lock"]) if (ROOT / "uv.lock").exists() else None,
        documents=sha(list((DATA / "documents").glob("*.pdf"))), evaluation=sha(list((DATA / "evaluation").glob("*.json"))),
        prompts=sha(list((ROOT / "src" / "answer" / "prompts").glob("*.md"))),
        search_answer_code=sha(list((ROOT / "src" / "search").glob("*.py")) + list((ROOT / "src" / "answer").glob("*.py"))),  # BM25(keyword.py)·청킹·검색·답변 코드. 커밋이 같아도 로컬에서 고친 경우를 잡는다
        model_revisions={config.EMBEDDING_MODEL: rev(config.EMBEDDING_MODEL), config.RERANKER_MODEL: rev(config.RERANKER_MODEL)},
        config={n: getattr(config, n, None) for n in names},
        llm_endpoint=hashlib.sha1(host.encode()).hexdigest()[:8] if host else None,  # 접속 주소는 그대로 적지 않고 해시만
        code_commit=git("rev-parse", "--short", "HEAD"), src_modified=bool(git("status", "--porcelain", "--", "src")),
        gpu=torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        gpu_total_gb=round(torch.cuda.get_device_properties(0).total_memory / 1e9, 1) if torch.cuda.is_available() else None,
        gpu_fraction=A.gpu_fraction, threads=A.threads, cpu_cores=CPU_CORES, answer_workers=A.workers, ragas_workers=A.ragas_workers, e2e_workers=A.e2e_workers,
    )


def stage_check():
    problems = []
    cuda = torch.cuda.is_available()
    if A.device == "cuda" and not cuda:
        problems.append("--device cuda인데 CUDA를 쓸 수 없다(드라이버·torch 빌드 확인)")
    for need in ("documents",):
        if not (DATA / need).exists():
            problems.append(f"data/shipping/{need}가 없다(데이터는 별도 전달)")
    for s in SETS:
        for f in (f"{s}.json", f"{s}_questions.json"):
            if not (DATA / "evaluation" / f).exists():
                problems.append(f"data/shipping/evaluation/{f}가 없다")
    if not (config.env("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")):
        problems.append("OPENAI_API_KEY가 없다(.env 확인). answers·e2e·ragas 단계에 필요하다")
    free = shutil.disk_usage(OUT.parent if OUT.parent.exists() else ROOT).free / 1e9
    if free < 5:
        problems.append(f"디스크 여유가 {free:.1f}GB뿐이다(5GB 이상 권장)")
    ensure_models()
    env = dict(
        run_at=time.strftime("%Y-%m-%d %H:%M:%S"), git_commit=git("rev-parse", "--short", "HEAD"),
        git_dirty=bool(git("status", "--porcelain", "--", "src")), os=pf.platform(), cpu=pf.processor(),
        cpu_count=os.cpu_count(), torch=torch.__version__, cuda=cuda, threads=A.threads,
        gpu=torch.cuda.get_device_name(0) if cuda else None,
        gpu_total_gb=round(torch.cuda.get_device_properties(0).total_memory / 1e9, 1) if cuda else None,
        gpu_fraction=A.gpu_fraction if cuda else None, k=KS, sizes=SIZES, pcts=PCTS,
        workers=A.workers, ragas_workers=A.ragas_workers, limit_q=A.limit_q, disk_free_gb=round(free, 1),
        context_max=CTXS, modes=list(MODES), k_order=A.k_order, ragas_sizes=RAGAS_SIZES, ragas_sample=A.ragas_sample,
        **hw_info(),
    )
    # 컴퓨팅 한도가 실제로 걸렸는지 확인(말로만이 아니라 다시 읽은 값)
    env.update(cpu_cores_requested=CPU_CORES, cpu_cores_applied=APPLIED_CORES, torch_threads=torch.get_num_threads(), gpu_at_start=gpu_sample())
    if CPU_CORES < (os.cpu_count() or CPU_CORES) and (APPLIED_CORES is None or APPLIED_CORES > CPU_CORES):
        problems.append(f"CPU 코어 제한({CPU_CORES}개)을 걸지 못했다(적용된 코어 {APPLIED_CORES}). 관리자 권한·보안 프로그램을 확인하거나 --cpu-cores를 전체 코어 수로 둔다")
    _, free_ram = mem_gb()
    env["free_ram_gb_at_start"] = free_ram
    if free_ram is not None and free_ram < A.min_free_ram_gb:
        problems.append(f"여유 RAM이 {free_ram}GB뿐이다({A.min_free_ram_gb}GB 이상 필요). 다른 앱을 끈다")
    idn = identity()
    env["identity"] = idn
    env["env_fingerprint"] = hashlib.sha1(json.dumps(idn, sort_keys=True, default=str).encode()).hexdigest()[:12]
    log(f"환경 지문: {env['env_fingerprint']}  (4대 노트북이 모두 같아야 한다. 다르면 합친 표에 ⚠로 표시된다)")
    if A.expect_fingerprint and A.expect_fingerprint != env["env_fingerprint"]:
        problems.append(f"환경 지문이 기준({A.expect_fingerprint})과 다르다(현재 {env['env_fingerprint']}). env.json의 identity를 기준 노트북과 비교해 다른 항목을 맞춘다")
    if A.expect_gpu and cuda and A.expect_gpu.lower() not in (env.get("gpu") or "").lower():
        problems.append(f"GPU가 기준과 다르다(현재 '{env.get('gpu')}', 기준 '{A.expect_gpu}'). 노트북 사이 시간 비교를 위해 같은 GPU에서만 돌린다(바꾸려면 --expect-gpu)")
    if env.get("on_ac_power") is False and not A.allow_battery:
        problems.append("배터리로 실행 중이다. 전원을 연결한다(성능·시간 측정이 흔들린다. 시험이면 --allow-battery)")
    if env.get("power_plan") and not re.search(r"고성능|최고|High performance|Ultimate|Performance", env["power_plan"], re.I):
        env["power_plan_warning"] = "전원 계획이 최고 성능이 아닌 것 같다. Windows 설정에서 전원 모드를 '최고 성능'으로 바꾸는 것을 권한다"
        log("경고: " + env["power_plan_warning"])
    if cuda:
        try:
            util = int(subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                                      capture_output=True, text=True).stdout.split()[0])
            env["gpu_util_at_start"] = util
            if util >= 5:
                problems.append(f"시작 전 GPU 사용률이 {util}%다(5% 미만이어야 시간이 흔들리지 않는다). 다른 GPU 작업을 끈다")
        except (OSError, ValueError, IndexError):
            pass
        # 메모리 상한 점검: 리랭커를 올리고 900자 글 20개(후보 수)를 한 번 채점한다
        torch.cuda.reset_peak_memory_stats()
        try:
            rerank._get_model().predict([("질문", "가" * 900)] * config.RERANK_CANDIDATES, batch_size=8)
            peak = torch.cuda.max_memory_allocated() / 1e9
            env["gpu_peak_gb_rerank"] = round(peak, 2)
            log(f"리랭커 점검 통과: GPU 최대 사용 {peak:.2f}GB (상한 {env['gpu_total_gb'] * A.gpu_fraction:.1f}GB)")
        except torch.cuda.OutOfMemoryError:
            problems.append(f"GPU 메모리 상한 {A.gpu_fraction}에서 리랭커가 메모리 부족이다. --gpu-fraction을 올린다")
    save_json(OUT / "env.json", env)
    if problems:
        sys.exit("점검 실패:\n- " + "\n- ".join(problems))
    log(f"점검 통과 -> {OUT / 'env.json'}")


# --- 단계 1: 검색 지표·검색 시간 ---------------------------------------------------------------
def pipeline_stages(question, mode):
    """retrieve()와 같은 순서로 단계마다 후보를 기록한다(청크 선별 과정): E5 후보 -> BM25 후보 -> RRF -> 리랭크 -> 최종.
    각 항목은 [chunk_id, 점수]. 최종 목록이 retrieve() 결과와 같은지는 호출한 쪽에서 same_as_retrieve로 남긴다."""
    ids = lambda cs: [[c.metadata.chunk_id, round(float(c.score), 5)] for c in cs]  # noqa: E731
    pc = time.perf_counter
    ms = {}  # 내부 단계 시간(ms). retrieve()와 같은 연산을 같은 순서로 한 번 더 돌려 잰 값이다(모델은 미리 불러 둠)
    t = pc()
    if mode == "naive":
        d = retrieve._dense(question, KMAX)
        ms["dense_ms"] = (pc() - t) * 1000  # 질문 임베딩 + 벡터 검색
        return dict(dense=ids(d), final=ids(d), stage_ms={k_: round(v, 2) for k_, v in ms.items()})
    d = retrieve._dense(question, retrieve.POOL)
    ms["dense_ms"] = (pc() - t) * 1000
    t = pc()
    b = retrieve._keyword(question, retrieve.POOL)
    ms["bm25_ms"] = (pc() - t) * 1000
    t = pc()
    if mode == "hybrid":
        f_ = retrieve._rrf([d, b], KMAX)
        ms["rrf_ms"] = (pc() - t) * 1000
        return dict(dense=ids(d), bm25=ids(b), final=ids(f_), stage_ms={k_: round(v, 2) for k_, v in ms.items()})
    cands = retrieve._rrf([d, b], config.RERANK_CANDIDATES)
    ms["rrf_ms"] = (pc() - t) * 1000
    t = pc()
    f_ = rerank.rerank(question, cands, KMAX)
    ms["rerank_ms"] = (pc() - t) * 1000
    return dict(dense=ids(d), bm25=ids(b), rrf=ids(cands), final=ids(f_), stage_ms={k_: round(v, 2) for k_, v in ms.items()})


def stage_retrieval(ev):
    for size, pct in settings():
        path = OUT / "retrieval" / f"{size}_{pct}.json"
        if path.exists():
            continue
        chunks_total = build(size, pct)
        ks = ks_for(size, pct)
        res = {"size": size, "pct": pct, "overlap_chars": _OV, "chunks_total": chunks_total, "ks": ks, "ctxs": CTXS, "modes": {}, "chunks": {}}
        for mode in MODES:
            rows = {}
            for qid, q in ev.items():
                t0 = time.perf_counter()
                full = retrieve.retrieve(q["question"], mode, KMAX)
                retr_s = time.perf_counter() - t0  # retrieve() 시작부터 청크 목록이 돌아올 때까지
                top_ids = [c.metadata.chunk_id for c in full]
                stages = pipeline_stages(q["question"], mode)  # 선별 과정 기록(시간에는 넣지 않음)
                stages["same_as_retrieve"] = [x[0] for x in stages["final"]] == top_ids
                for c in full:  # 밀려난 청크도 본문을 남긴다(보고서에서 보여주기 위해)
                    res["chunks"][c.metadata.chunk_id] = dict(book_id=c.metadata.book_id, file_name=c.metadata.file_name, page=c.metadata.page, text=c.text)
                per_k = {}
                for k in ks:
                    top = full[:k]
                    by_ctx = {}
                    for lim in CTXS:
                        used = top[: len(build_context(top, token_limit=lim))]
                        by_ctx[str(lim)] = dict(ids=[c.metadata.chunk_id for c in used], n_used=len(used), m=retrieval_metrics(q["gold"], used))
                    per_k[k] = dict(n_top=len(top), tok_sum=sum(count_tokens(c.text) for c in top), ctx=by_ctx)
                rows[qid] = dict(retrieval_s=round(retr_s, 5), top_ids=top_ids, stages=stages, k=per_k)
            res["modes"][mode] = rows
        save_json(path, res)
        log(f"[검색] 크기 {size} 오버랩 {pct}%({_OV}자) 청크 {chunks_total} 끝")


# --- 단계 2: 답변(병렬) ----------------------------------------------------------------------
_tl = threading.local()
_orig_call = llm.call


def _counted_call(*a, **kw):
    _tl.n = getattr(_tl, "n", 0) + 1  # 재생성 횟수 세기용
    return _orig_call(*a, **kw)


llm.call = _counted_call


def answer_job(job):
    question, ctx = job
    last = None
    for attempt in range(2):  # 호출 실패는 한 번 더 시도(그 안에서도 platform이 재시도)
        _tl.n = 0
        t0 = time.perf_counter()
        try:
            with llm.usage_scope() as u:
                out, _ = chain.generate(question, ctx)
            return dict(answer=out.model_dump(), input_tokens=u.input_tokens, output_tokens=u.output_tokens,
                        llm_ms=u.latency_ms, wall_s=round(time.perf_counter() - t0, 3), llm_calls=_tl.n), None
        except Exception as e:
            last = f"{type(e).__name__}: {str(e)[:200]}"
            time.sleep(2)
    return None, last


def answer_fields(rec, res, err, gold, cids_chunks):
    rec["answer"], rec["error"] = (res["answer"] if res else None), err
    if not res:
        return
    rec.update({k: res[k] for k in ("input_tokens", "output_tokens", "llm_ms", "wall_s", "llm_calls")})
    exp = gold["expected_action"]
    rec["expected"] = exp
    rec["status_match"] = res["answer"]["status"] == STATUS_OF.get(exp, exp)
    gold_docs = {e["book_id"] for g in groups_of(gold) for e in g}
    if gold_docs:
        cited = {cids_chunks[rec["source_map"][s]]["book_id"] for s in res["answer"]["source_ids"] if s in rec["source_map"]}
        rec["cites_gold_doc"] = bool(cited & gold_docs)


def stage_answers(ev):
    for size, pct in settings():
        rpath = OUT / "retrieval" / f"{size}_{pct}.json"
        path = OUT / "answers" / f"{size}_{pct}.json"
        if path.exists():
            continue
        if not rpath.exists():
            sys.exit(f"먼저 retrieval 단계를 돌려야 한다: {rpath}")
        r = load_json(rpath)
        chunks = r["chunks"]
        want = ks_for(size, pct)
        recs, jobs = [], {}
        for mode in MODES:
            for qid, q in ev.items():
                row = r["modes"][mode][qid]
                for k in want:
                    for lim in CTXS:
                        d = row["k"][str(k)]["ctx"][str(lim)]
                        ctx = build_context([_as_chunk(c, chunks[c]) for c in d["ids"]], token_limit=lim)
                        # 한도가 달라도 최종 청크 목록이 같으면 답변을 한 번만 만든다
                        jobs.setdefault((qid, tuple(d["ids"])), (q["question"], ctx))
                        recs.append(dict(mode=mode, qid=qid, k=k, ctx=lim, chunk_ids=d["ids"], top_ids=row["top_ids"][:k],
                                         dropped_ids=[c for c in row["top_ids"][:k] if c not in d["ids"]],
                                         source_map={c.source_id: cid for c, cid in zip(ctx, d["ids"])}))
        keys = list(jobs)
        with ThreadPoolExecutor(A.workers) as ex:
            results = dict(zip(keys, ex.map(answer_job, [jobs[k] for k in keys])))
        failed = [k_ for k_ in keys if results[k_][1]]
        if len(failed) / len(keys) > 0.05 and A.workers > 2:  # 429·timeout이 많으면 병렬 수를 절반으로 줄여 실패한 호출만 다시 한다
            half = max(2, A.workers // 2)
            log(f"[답변] 크기 {size} {pct}%: 실패 {len(failed)}/{len(keys)}. 병렬 {A.workers} -> {half}로 줄여 실패한 호출만 다시 한다")
            with ThreadPoolExecutor(half) as ex:
                results.update(zip(failed, ex.map(answer_job, [jobs[k_] for k_ in failed])))
        for rec in recs:
            res, err = results[(rec["qid"], tuple(rec["chunk_ids"]))]
            answer_fields(rec, res, err, ev[rec["qid"]]["gold"], chunks)
        n_err = sum(1 for x in results.values() if x[1])
        rate = n_err / len(results)
        if rate > 0.05:
            log(f"[답변] 크기 {size} {pct}%: 오류 {n_err}/{len(results)}({rate:.0%})가 5%를 넘어 저장하지 않는다. 429·인터넷을 확인하고 --workers를 낮춰 다시 실행한다")
            continue
        save_json(path, dict(size=size, pct=pct, records=recs, calls=len(results), errors=n_err))  # 청크 본문은 retrieval 파일에 있다
        log(f"[답변] 크기 {size} 오버랩 {pct}% 끝: 호출 {len(results)}, 오류 {n_err}")


def _as_chunk(cid, c):
    from src.contracts import ChunkMeta, RetrievedChunk

    return RetrievedChunk(text=c["text"], score=0.0, metadata=ChunkMeta(chunk_id=cid, book_id=c["book_id"], file_name=c["file_name"], page=c["page"]))


# --- 단계 3: 전체 시간(직렬) -------------------------------------------------------------------
def _llm_cell(question, ctx):
    """LLM 답변 한 번의 시간·토큰. 이 함수 안의 시간만 `llm_s`로 잰다(스레드에서 불러도 호출마다 따로 잰다)."""
    _tl.n = 0
    t = time.perf_counter()
    try:
        with llm.usage_scope() as u:
            out, _ = chain.generate(question, ctx)
        return dict(status=out.status, llm_s=time.perf_counter() - t, input_tokens=u.input_tokens, output_tokens=u.output_tokens,
                    llm_ms_usage=u.latency_ms, llm_calls=_tl.n, error=None)
    except Exception as e:
        return dict(llm_s=time.perf_counter() - t, error=f"{type(e).__name__}: {str(e)[:150]}")


def e2e_run(ev, mode, k, lims, workers=1):
    """문항마다 retrieve() + 문맥 조립 + LLM 답변 시간을 잰다. **검색은 항상 직렬**(노트북 GPU를 나눠 쓰면 검색 시간이 부풀기 때문).
    LLM 호출은 workers=1이면 직렬(단독 호출 시간), workers>1이면 그만큼 동시에 내보낸다(그때 llm_s는 동시 호출 부하가 섞인 값이다).
    한도가 여러 개면 가장 큰 한도는 전 문항, 나머지는 문맥이 달라진 문항만 답변을 다시 만든다
    (문맥이 같으면 같은 호출이므로 `same_as`로 가리키고 시간은 큰 한도 값을 쓴다). total_s = 검색 + 문맥 + LLM."""
    rows, jobs = [], []
    lims = sorted(lims, reverse=True)

    def run_job(j):
        cell, question, ctx, retr_s = j
        cell.update(_llm_cell(question, ctx))
        cell["total_s"] = retr_s + cell["context_s"] + cell["llm_s"]

    for qid, q in ev.items():
        t0 = time.perf_counter()
        chunks = retrieve.retrieve(q["question"], mode, k)
        row = dict(qid=qid, k=k, retrieval_s=time.perf_counter() - t0, ctx={})
        base_ids = None
        mine = []
        for lim in lims:
            ta = time.perf_counter()
            ctx = build_context(chunks, token_limit=lim)
            ctx_s = time.perf_counter() - ta
            ids = [c.metadata.chunk_id for c in ctx]
            if base_ids is not None and ids == base_ids:
                row["ctx"][str(lim)] = dict(same_as=lims[0])
                continue
            base_ids = base_ids or ids
            cell = dict(n_used=len(ctx), context_s=ctx_s)
            row["ctx"][str(lim)] = cell
            mine.append((cell, q["question"], ctx, row["retrieval_s"]))
        rows.append(row)
        if workers == 1:
            for j in mine:  # 직렬: 이 문항의 LLM 호출이 끝난 뒤에 다음 문항의 검색을 한다
                run_job(j)
        else:
            jobs += mine
    if jobs:
        with ThreadPoolExecutor(workers) as ex:
            list(ex.map(run_job, jobs))
    return rows


def stage_e2e(ev):
    def anchor(name):
        path = OUT / "e2e" / f"anchor_{name}.json"
        if path.exists():
            return
        build(500, 0)
        save_json(path, dict(setting="500/0%/hybrid_rerank/k=10/ctx=3000", run_at=time.strftime("%H:%M:%S"), rows=e2e_run(ev, "hybrid_rerank", 10, [3000])))
        log(f"[전체 시간] 앵커 {name} 끝")

    anchor("start")
    for size in SIZES:
        path = OUT / "e2e" / f"{size}_0.json"
        if path.exists():
            continue
        build(size, 0)
        g0, by_mode = gpu_sample(), {m_: {} for m_ in E2E_MODES}
        for k in KS:
            for m_ in E2E_MODES:  # 같은 k에서 방식을 번갈아 돌려 시간대 흔들림이 한 방식에 몰리지 않게 한다
                by_mode[m_][str(k)] = e2e_run(ev, m_, k, CTXS, A.e2e_workers)
        g1 = gpu_sample()
        save_json(path, dict(size=size, pct=0, ctxs=CTXS, e2e_workers=A.e2e_workers, modes=by_mode, gpu_start=g0, gpu_end=g1))
        if g1 and g1.get("thermal_or_hw_slowdown"):
            log(f"경고: 크기 {size} 직렬 시간 측정 중 GPU 열·하드웨어 감속 신호({g1['throttle_hex']}, {g1['temp_c']}C). 시간이 느리게 나왔을 수 있다")
        log(f"[전체 시간] 크기 {size} 끝")
    anchor("end")


# --- 단계 4: RAGAS ---------------------------------------------------------------------------
def stage_ragas(ev):
    """RAGAS는 faithfulness만 채점한다(3회 평균). 외부 LLM 호출뿐이라 GPU를 쓰지 않는다."""
    warnings.filterwarnings("ignore")
    from ragas import SingleTurnSample
    from ragas.run_config import RunConfig

    from src.judge import ragas_eval as re_

    nan_none = lambda x: None if x is None or (isinstance(x, float) and math.isnan(x)) else float(x)  # noqa: E731

    def score(job):
        q, contexts, answer = job
        sample = SingleTurnSample(user_input=q, response=answer, retrieved_contexts=contexts or ["(검색 자료 없음)"])
        vals, errs, tin, tout = [], [], 0, 0
        for _ in range(config.FAITHFULNESS_REPEATS):
            rec = re_._make_recorded_llm(llm.call)
            rec.set_run_config(RunConfig(max_retries=1, max_wait=1))
            try:
                v = nan_none(asyncio.run(re_._make_metric(rec).single_turn_ascore(sample)))
                if v is not None:
                    vals.append(v)
            except Exception as e:
                errs.append(f"{type(e).__name__}: {str(e)[:100]}")
            tin += rec.usage.input or 0
            tout += rec.usage.output or 0
        return dict(faithfulness=statistics.mean(vals) if vals else None, n_runs=len(vals), errors=errs, tokens_in=tin, tokens_out=tout)

    keep = {qid for qid, q in ev.items() if A.ragas_sample == "all" or q["idx"] % 2 == 0}  # odd: 세트마다 홀수 번째 문항(1, 3, 5, ...)
    targets = [(z, 0, k) for z in RAGAS_SIZES if z in SIZES for k in KS] + [BASE]
    for size, pct, k in dict.fromkeys(targets):
        apath = OUT / "answers" / f"{size}_{pct}.json"
        if not apath.exists():
            sys.exit(f"먼저 answers 단계를 돌려야 한다: {apath}")
        a = load_json(apath)
        chunks = load_json(OUT / "retrieval" / f"{size}_{pct}.json")["chunks"]
        for mode in MODES:
            path = OUT / "ragas" / f"{mode}_{size}_{pct}_k{k}.json"
            if path.exists():
                continue
            recs = [r for r in a["records"] if r["mode"] == mode and r["k"] == k and r["qid"] in keep and r.get("answer")]
            # 한도가 달라도 (문항, 청크 목록)이 같으면 답변과 점수가 같으므로 한 번만 채점한다
            uniq = {}
            for r in recs:
                uniq.setdefault((r["qid"], tuple(r["chunk_ids"])), (ev[r["qid"]]["question"], [chunks[c]["text"] for c in r["chunk_ids"]], r["answer"]["answer"]))
            keys = list(uniq)
            with ThreadPoolExecutor(A.ragas_workers) as ex:
                scored = dict(zip(keys, ex.map(score, [uniq[x] for x in keys])))
            by_ctx = {}
            for r in recs:
                by_ctx.setdefault(str(r["ctx"]), dict(qids=[], results=[]))
                by_ctx[str(r["ctx"])]["qids"].append(r["qid"])
                by_ctx[str(r["ctx"])]["results"].append(scored[(r["qid"], tuple(r["chunk_ids"]))])
            save_json(path, dict(mode=mode, size=size, pct=pct, k=k, scored=len(keys), by_ctx=by_ctx))
            log(f"[RAGAS] {mode} 크기 {size} 오버랩 {pct}% k={k} 끝 (채점 {len(keys)}건, 한도 {len(by_ctx)}개에 재사용)")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ev = load_questions()
    log(f"문항 {len(ev)}개, k={KS}, 크기={SIZES}, 오버랩={PCTS}, 단계={STAGES}")
    usage_path = OUT / "usage.json"
    usage = load_json(usage_path) if usage_path.exists() else {}
    for st in STAGES:
        t_st = time.time()
        {"check": lambda: stage_check(), "retrieval": lambda: stage_retrieval(ev), "answers": lambda: stage_answers(ev),
         "e2e": lambda: stage_e2e(ev), "ragas": lambda: stage_ragas(ev)}[st]()
        peak_proc, free_ram = mem_gb()
        gpu_peak = round(torch.cuda.max_memory_allocated() / 1e9, 2) if torch.cuda.is_available() else None
        usage[st] = dict(elapsed_s=round(time.time() - t_st), proc_peak_gb=peak_proc, free_ram_gb_after=free_ram, gpu_peak_gb=gpu_peak, gpu_end=gpu_sample())
        save_json(usage_path, usage)  # 단계별 최대 메모리·GPU 사용량·종료 시점 GPU 상태(열·전력 제한 여부)
        cap = (torch.cuda.get_device_properties(0).total_memory / 1e9 * A.gpu_fraction) if torch.cuda.is_available() else None
        if cap and gpu_peak and gpu_peak > cap:
            log(f"경고: GPU 최대 사용 {gpu_peak}GB가 상한 {cap:.1f}GB를 넘었다")
    log("DONE")


if __name__ == "__main__":
    main()
