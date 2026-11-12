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
    p.add_argument("--gpu-fraction", type=float, default=0.5, help="프로세스당 GPU 메모리 비율(8GB x 0.5 = 4GB)")
    p.add_argument("--workers", type=int, default=24, help="답변 호출 병렬 수(키를 공유하면 12)")
    p.add_argument("--ragas-workers", type=int, default=8)
    p.add_argument("--limit-q", type=int, default=0, help="시험 실행용: 세트마다 앞의 N문항만")
    p.add_argument("--no-auto-torch", action="store_true")
    return p.parse_args()


A = parse()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows 콘솔(cp949)에서 한글이 깨지지 않게
# --- torch를 불러오기 전에 장치·스레드 한도를 건다 -----------------------------------------
if A.device == "cpu":
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_v] = str(A.threads)
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
if A.device == "cuda" and torch.cuda.is_available():
    torch.cuda.set_per_process_memory_fraction(A.gpu_fraction)

from src import config  # noqa: E402
from src.answer import chain  # noqa: E402
from src.answer.context import build_context, count_tokens  # noqa: E402
from src.platform import llm  # noqa: E402
from src.search import chunking, embed, index, keyword, rerank, retrieve, store  # noqa: E402

DATA = ROOT / "data" / "shipping"
OUT = Path(A.out)
KS = sorted({int(x) for x in A.k.split(",")})
SIZES = [int(x) for x in A.sizes.split(",")]
PCTS = [int(x) for x in A.pcts.split(",")]
KMAX = 11
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
    for m in MODES:
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
    pq = [any(hit_pq(c, e) for e in g for c in chunks) for g in groups]
    return dict(
        recall_book=len(got & ref) / len(ref), hit=bool(got & ref),
        recall_pq=sum(pq) / len(pq), all_pq=all(pq),
        all_book=all(any(c.metadata.book_id == e["book_id"] for e in g for c in chunks) for g in groups),
    )


def ks_for(size, pct):
    return sorted(set(KS) | ({BASE[2]} if (size, pct) == BASE[:2] else set()))


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
    )
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
def stage_retrieval(ev):
    for size, pct in settings():
        path = OUT / "retrieval" / f"{size}_{pct}.json"
        if path.exists():
            continue
        chunks_total = build(size, pct)
        ks = ks_for(size, pct)
        res = {"size": size, "pct": pct, "overlap_chars": _OV, "chunks_total": chunks_total, "ks": ks, "modes": {}, "chunks": {}}
        for mode in MODES:
            rows = {}
            for qid, q in ev.items():
                t0 = time.perf_counter()
                full = retrieve.retrieve(q["question"], mode, KMAX)
                retr_s = time.perf_counter() - t0  # retrieve() 시작부터 청크 목록이 돌아올 때까지
                per_k = {}
                for k in ks:
                    top = full[:k]
                    used = top[: len(build_context(top, token_limit=config.CONTEXT_TOKEN_LIMIT))]
                    per_k[k] = dict(ids=[c.metadata.chunk_id for c in used], n_top=len(top), n_used=len(used),
                                    tok_sum=sum(count_tokens(c.text) for c in top), m=retrieval_metrics(q["gold"], used))
                    for c in used:
                        res["chunks"][c.metadata.chunk_id] = dict(book_id=c.metadata.book_id, file_name=c.metadata.file_name, page=c.metadata.page, text=c.text)
                rows[qid] = dict(retrieval_s=round(retr_s, 5), k=per_k)
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
                for k in want:
                    d = r["modes"][mode][qid]["k"][str(k)]
                    ctx = build_context([_as_chunk(c, chunks[c]) for c in d["ids"]], token_limit=config.CONTEXT_TOKEN_LIMIT)
                    jobs.setdefault((qid, tuple(d["ids"])), (q["question"], ctx))
                    recs.append(dict(mode=mode, qid=qid, k=k, chunk_ids=d["ids"], source_map={c.source_id: cid for c, cid in zip(ctx, d["ids"])}))
        keys = list(jobs)
        with ThreadPoolExecutor(A.workers) as ex:
            results = dict(zip(keys, ex.map(answer_job, [jobs[k] for k in keys])))
        for rec in recs:
            res, err = results[(rec["qid"], tuple(rec["chunk_ids"]))]
            answer_fields(rec, res, err, ev[rec["qid"]]["gold"], chunks)
        n_err = sum(1 for x in results.values() if x[1])
        rate = n_err / len(results)
        if rate > 0.05:
            log(f"[답변] 크기 {size} {pct}%: 오류 {n_err}/{len(results)}({rate:.0%})가 5%를 넘어 저장하지 않는다. 429·인터넷을 확인하고 --workers를 낮춰 다시 실행한다")
            continue
        save_json(path, dict(size=size, pct=pct, chunks=chunks, records=recs, calls=len(results), errors=n_err))
        log(f"[답변] 크기 {size} 오버랩 {pct}% 끝: 호출 {len(results)}, 오류 {n_err}")


def _as_chunk(cid, c):
    from src.contracts import ChunkMeta, RetrievedChunk

    return RetrievedChunk(text=c["text"], score=0.0, metadata=ChunkMeta(chunk_id=cid, book_id=c["book_id"], file_name=c["file_name"], page=c["page"]))


# --- 단계 3: 전체 시간(직렬) -------------------------------------------------------------------
def e2e_run(ev, mode, k, tag):
    rows = []
    for qid, q in ev.items():
        t0 = time.perf_counter()
        chunks = retrieve.retrieve(q["question"], mode, k)
        t1 = time.perf_counter()
        ctx = build_context(chunks, token_limit=config.CONTEXT_TOKEN_LIMIT)
        t2 = time.perf_counter()
        row = dict(qid=qid, k=k, retrieval_s=t1 - t0, context_s=t2 - t1)
        _tl.n = 0
        try:
            with llm.usage_scope() as u:
                out, _ = chain.generate(q["question"], ctx)
            t3 = time.perf_counter()
            row.update(status=out.status, llm_s=t3 - t2, total_s=t3 - t0, input_tokens=u.input_tokens,
                       output_tokens=u.output_tokens, llm_ms_usage=u.latency_ms, llm_calls=_tl.n, error=None)
        except Exception as e:
            row.update(llm_s=time.perf_counter() - t2, total_s=time.perf_counter() - t0, error=f"{type(e).__name__}: {str(e)[:150]}")
        rows.append(row)
    return rows


def stage_e2e(ev):
    def anchor(name):
        path = OUT / "e2e" / f"anchor_{name}.json"
        if path.exists():
            return
        build(500, 0)
        save_json(path, dict(setting="500/0%/hybrid_rerank/k=10", run_at=time.strftime("%H:%M:%S"), rows=e2e_run(ev, "hybrid_rerank", 10, name)))
        log(f"[전체 시간] 앵커 {name} 끝")

    anchor("start")
    for size in SIZES:
        path = OUT / "e2e" / f"{size}_0.json"
        if path.exists():
            continue
        build(size, 0)
        rows = {}
        for k in KS:
            rows[str(k)] = e2e_run(ev, "hybrid_rerank", k, f"{size}/{k}")
        save_json(path, dict(size=size, pct=0, mode="hybrid_rerank", rows=rows))
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

    odd = {qid for qid, q in ev.items() if q["idx"] % 2 == 0}  # 세트마다 홀수 번째 문항(1, 3, 5, ...)
    targets = [(z, 0, k) for z in (500, 900) if z in SIZES for k in KS] + [BASE]
    for size, pct, k in dict.fromkeys(targets):
        apath = OUT / "answers" / f"{size}_{pct}.json"
        if not apath.exists():
            sys.exit(f"먼저 answers 단계를 돌려야 한다: {apath}")
        a = load_json(apath)
        for mode in MODES:
            path = OUT / "ragas" / f"{mode}_{size}_{pct}_k{k}.json"
            if path.exists():
                continue
            recs = [r for r in a["records"] if r["mode"] == mode and r["k"] == k and r["qid"] in odd and r.get("answer")]
            jobs = [(ev[r["qid"]]["question"], [a["chunks"][c]["text"] for c in r["chunk_ids"]], r["answer"]["answer"]) for r in recs]
            with ThreadPoolExecutor(A.ragas_workers) as ex:
                res = list(ex.map(score, jobs))
            save_json(path, dict(mode=mode, size=size, pct=pct, k=k, n=len(recs), qids=[r["qid"] for r in recs], results=res))
            log(f"[RAGAS] {mode} 크기 {size} 오버랩 {pct}% k={k} 끝 (n={len(recs)})")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ev = load_questions()
    log(f"문항 {len(ev)}개, k={KS}, 크기={SIZES}, 오버랩={PCTS}, 단계={STAGES}")
    for st in STAGES:
        {"check": lambda: stage_check(), "retrieval": lambda: stage_retrieval(ev), "answers": lambda: stage_answers(ev),
         "e2e": lambda: stage_e2e(ev), "ragas": lambda: stage_ragas(ev)}[st]()
    log("DONE")


if __name__ == "__main__":
    main()
