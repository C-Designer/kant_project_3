"""발표 슬라이드 두 벌(HTML)을 만든다. PDF는 make_pdf.sh가 Chrome으로 뽑는다. 사용법과 고치는 법은 README.md.

    python3 build_deck.py   # -> RAG-search-experiments-team.html, RAG-param-sweep-platform.html

표준 라이브러리만 쓴다. 팀 자료의 글·표는 inputs/team_deck.json(팀 PPTX에서 뽑은 그대로), 스윕 수치는 inputs/*.json(결과 CSV·Langfuse에서 뽑은 스냅샷).
"""
import json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "inputs"
D = json.load(open(DATA / "sweep_metrics.json", encoding="utf-8"))
M = ["naive", "hybrid", "hybrid_rerank"]
R = "hybrid_rerank"
C = {"naive": "#2a78d6", "hybrid": "#eb6834", R: "#1baf7a"}
INK, INK2, MUTED, GRID, SURF, BAND, ACC, NEUT = "#292a27", "#686b66", "#8f918b", "#dddad1", "#faf9f5", "#eeece5", "#a65a3c", "#8f918b"
B3, C3 = D["base3"], D["c1x3"]
BASE = {"topk": 5, "chunk": 900, "overlap": 0, "rerank": 20}
for var, bx in BASE.items():
    for p in D[var]:
        if p["v"] == bx:
            for m in M:
                p[m]["faith"], p[m]["lat"] = B3[m]["faith"][0], B3[m]["lat"][0]
FBAND = (B3[R]["faith"][1], B3[R]["faith"][2])

# ---------- 팀 자료(검색 실험 PPTX에서 뽑아 둔 글·표) ----------
_team = json.load(open(DATA / "team_deck.json", encoding="utf-8"))
T = {int(k): (v["paras"], v["tables"]) for k, v in _team.items()}
assert T[5][0][0] == "청크 크기 비교" and T[27][0][0].startswith("부록 17"), "팀 자료 구조가 예상과 다르다"
num = lambda s: float(s.replace(",", "").replace("초", "").split()[0])
HEADS = {"결과 해석", "해석의 범위", "설정·지표 설명", "Base / 변경 변수", "측정 지표", "종합 판단", "진행 상태와 다음 확인", "관찰"}
esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------- 차트 ----------
def line_chart(title, data, xticks, ymin, ymax, ystep, w=372, h=335, yfmt="{:.2f}", band=None, base_x=None, shade_from=None, labels=None,
               xlabel="", base_label="기준"):
    ml, mr, mt, mb = 42, 14, 40, 40
    pw, ph = w - ml - mr, h - mt - mb
    x0, x1 = min(xticks), max(xticks)
    X = lambda v: ml + 10 + (v - x0) / (x1 - x0) * (pw - 20)
    Y = lambda v: mt + (ymax - v) / (ymax - ymin) * ph
    s = [f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="{title}">',
         f'<text x="0" y="14" font-size="13.5" font-weight="700" fill="{INK}">{title}</text>']
    if shade_from is not None:
        s.append(f'<rect x="{X(shade_from):.1f}" y="{mt}" width="{ml + pw - X(shade_from):.1f}" height="{ph}" fill="#f1efe8"/>')
        s.append(f'<text x="{ml + pw - 4}" y="{mt + 13}" font-size="10.5" text-anchor="end" fill="{MUTED}">해석 보류</text>')
    if band:
        s.append(f'<rect x="{ml}" y="{Y(band[1]):.1f}" width="{pw}" height="{Y(band[0]) - Y(band[1]):.1f}" fill="{BAND}"/>')
    v = ymin
    while v <= ymax + 1e-9:
        s.append(f'<line x1="{ml}" x2="{ml + pw}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="{GRID}" stroke-width="1"/>')
        s.append(f'<text x="{ml - 6}" y="{Y(v) + 4:.1f}" font-size="11" text-anchor="end" fill="{INK2}">{yfmt.format(v)}</text>')
        v += ystep
    for t in xticks:
        s.append(f'<text x="{X(t):.1f}" y="{mt + ph + 16}" font-size="11" text-anchor="middle" fill="{INK2}">{t:,}</text>')
    if xlabel:
        s.append(f'<text x="{ml + pw / 2}" y="{h - 4}" font-size="11" text-anchor="middle" fill="{MUTED}">{xlabel}</text>')
    if base_x is not None:
        s.append(f'<line x1="{X(base_x):.1f}" x2="{X(base_x):.1f}" y1="{mt}" y2="{mt + ph}" stroke="{MUTED}" stroke-width="1" stroke-dasharray="3 3"/>')
        s.append(f'<text x="{X(base_x):.1f}" y="{mt - 5}" font-size="10.5" text-anchor="middle" fill="{MUTED}">{base_label}</text>')
    for name, pts in data.items():
        if len(pts) > 1:
            s.append(f'<polyline fill="none" stroke="{C[name]}" stroke-width="2" stroke-linejoin="round" points="' +
                     " ".join(f"{X(x):.1f},{Y(y):.1f}" for x, y in pts) + '"/>')
        for x, y in pts:
            s.append(f'<circle cx="{X(x):.1f}" cy="{Y(y):.1f}" r="4.5" fill="{C[name]}" stroke="{SURF}" stroke-width="2"/>')
            if labels and x in labels.get(name, ()):
                s.append(f'<text x="{X(x):.1f}" y="{Y(y) - 9:.1f}" font-size="11.5" font-weight="600" text-anchor="middle" fill="{INK}">{yfmt.format(y)}</text>')
    return "".join(s) + "</svg>"


def bar_chart(title, cats, ymax, ystep, w=372, h=335, yfmt="{:.0f}", color=C[R], colors=None, xlabel="", base=None, tickfmt=None):
    ml, mr, mt, mb = 42, 14, 40, 40
    pw, ph = w - ml - mr, h - mt - mb
    Y = lambda v: mt + (ymax - v) / ymax * ph
    s = [f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="{title}">',
         f'<text x="0" y="14" font-size="13.5" font-weight="700" fill="{INK}">{title}</text>']
    v = 0
    while v <= ymax + 1e-9:
        s.append(f'<line x1="{ml}" x2="{ml + pw}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="{GRID}" stroke-width="1"/>')
        s.append(f'<text x="{ml - 6}" y="{Y(v) + 4:.1f}" font-size="11" text-anchor="end" fill="{INK2}">{(tickfmt or yfmt).format(v)}</text>')
        v += ystep
    step = pw / len(cats); bw = min(40, step - 12)
    for i, (lab, val) in enumerate(cats):
        x = ml + step * i + (step - bw) / 2; y = Y(val); y0 = mt + ph
        if val > 0:
            r = min(4, (y0 - y) / 2)
            s.append(f'<path d="M{x:.1f},{y0} V{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} H{x + bw - r:.1f} Q{x + bw:.1f},{y:.1f} {x + bw:.1f},{y + r:.1f} V{y0} Z" fill="{colors[i] if colors else color}"/>')
        s.append(f'<text x="{x + bw / 2:.1f}" y="{y - 6:.1f}" font-size="11.5" font-weight="600" text-anchor="middle" fill="{INK}">{yfmt.format(val)}</text>')
        s.append(f'<text x="{x + bw / 2:.1f}" y="{y0 + 16}" font-size="11" text-anchor="middle" fill="{INK2}">{lab}</text>')
        if base is not None and lab == str(base):
            s.append(f'<text x="{x + bw / 2:.1f}" y="{mt - 5}" font-size="10.5" text-anchor="middle" fill="{MUTED}">기준</text>')
    if xlabel:
        s.append(f'<text x="{ml + pw / 2}" y="{h - 4}" font-size="11" text-anchor="middle" fill="{MUTED}">{xlabel}</text>')
    return "".join(s) + "</svg>"


def range_chart(w=560, h=170):
    ml, mr, mt, mb = 118, 20, 8, 28
    pw, ph = w - ml - mr, h - mt - mb
    X = lambda v: ml + (v - 0.80) / 0.20 * pw
    s = [f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="기준 3회 Faithfulness 범위">']
    for t in (0.80, 0.85, 0.90, 0.95, 1.00):
        s.append(f'<line x1="{X(t):.1f}" x2="{X(t):.1f}" y1="{mt}" y2="{mt + ph}" stroke="{GRID}"/>')
        s.append(f'<text x="{X(t):.1f}" y="{mt + ph + 16}" font-size="11" text-anchor="middle" fill="{INK2}">{t:.2f}</text>')
    for i, m in enumerate(M):
        y = mt + ph * (i + 0.5) / 3; mean, a, b = B3[m]["faith"]
        s.append(f'<text x="{ml - 10}" y="{y + 4:.1f}" font-size="12.5" text-anchor="end" fill="{INK}">{m}</text>')
        s.append(f'<line x1="{X(a):.1f}" x2="{X(b):.1f}" y1="{y:.1f}" y2="{y:.1f}" stroke="{C[m]}" stroke-width="6" stroke-linecap="round" opacity="0.35"/>')
        s.append(f'<circle cx="{X(mean):.1f}" cy="{y:.1f}" r="5.5" fill="{C[m]}" stroke="{SURF}" stroke-width="2"/>')
        s.append(f'<text x="{X(b) + 10:.1f}" y="{y + 4:.1f}" font-size="12" fill="{INK}">{mean:.2f} <tspan fill="{MUTED}">[{a:.2f}~{b:.2f}]</tspan></text>')
    return "".join(s) + "</svg>"


# ---------- 조립 도구 ----------
PAGES = {"A": [], "B": []}
CUR = "A"  # A = 검색 실험(팀 자료), B = 동일 환경 파라미터 스윕
KICK = "조건"  # 평가 관점 순서: 조건 → 비교 결과 → 선택과 이유 → 실패·한계 → 부록


def table(rows, cls=""):
    h = "".join(f"<th>{esc(c)}</th>" for c in rows[0])
    b = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>" for r in rows[1:])
    return f'<table class="grid {cls}"><tr>{h}</tr>{b}</table>'


def legend(modes, band=False):
    s = "".join(f'<span><i style="background:{C[m]}"></i>{m}</span>' for m in modes)
    return f'<div class="legend">{s}{"<span><i class=band></i>기준 3회 범위(hybrid_rerank Faithfulness)</span>" if band else ""}</div>'


def page(title, src, body, cls=""):
    PAGES[CUR].append((title, f'<section class="slide {cls}"><header><div class="kick">{KICK}</div><h1>{esc(title)}</h1><div class="src">{esc(src)}</div></header>'
                         f'<div class="body">{body}</div>__FOOT__</section>'))


def block(head, paras, strong_first=True):
    """짧은 줄이 이어지면 한 문장으로 합쳐 굵게, 아니면 첫 문단만 굵게."""
    short = []
    while paras and len(paras[0]) <= 14 and len(paras) > 1:
        short.append(paras[0]); paras = paras[1:]
    out = f'<div class="blk"><div class="lab {"acc" if head in ("관찰", "결과 해석", "종합 판단") else ""}">{esc(head)}</div>'
    if short:
        out += f'<p class="stmt">{"<br>".join(esc(s) for s in short)}</p>'
        out += "".join(f"<p>{esc(p)}</p>" for p in paras)
    else:
        big = strong_first and head in ("결과 해석", "종합 판단")
        out += "".join(f'<p class="{"b" if big and i == 0 else ""}">{esc(p)}</p>' for i, p in enumerate(paras))
    return out + "</div>"


def split_blocks(paras):
    conds, blocks, cur = [], [], None
    for p in paras:
        if p in HEADS:
            cur = [p, []]; blocks.append(cur)
        elif cur is None:
            conds.append(p)
        else:
            cur[1].append(p)
    return conds, blocks


def team_obs(i, charts):
    """팀 본문 슬라이드(관찰 / 해석의 범위 / 조건 + 표): 5·6·8·9."""
    paras, tables = T[i]
    conds, blocks = split_blocks(paras[4:])
    tail = []
    for b in blocks:  # '해석의 범위' 뒤에 붙은 조건 줄을 분리
        if b[0] == "해석의 범위" and len(b[1]) > 1:
            tail, b[1] = b[1][1:], b[1][:1]
    left = "".join(block(h, list(ps)) for h, ps in blocks)
    right = f'<div class="charts n{len(charts)}">' + "".join(f"<figure>{c}</figure>" for c in charts) + "</div>" + "".join(table(t) for t in tables)
    cond = " / ".join(conds + tail)
    page(paras[0], paras[1], f'<p class="purpose">{esc(paras[3])}</p><div class="two"><div>{left}</div><div>{right}</div></div>'
                             f'<p class="cond">{esc(cond)}</p>')


def team_appendix(i):
    paras, tables = T[i]
    conds, blocks = split_blocks(paras[4:])
    left = "".join(block(h, list(ps)) for h, ps in blocks)
    if len(conds) == len(tables) and len(tables) > 1:
        right = "".join(f'<p class="cap">{esc(c)}</p>{table(t)}' for c, t in zip(conds, tables))
    else:
        right = "".join(f'<p class="cap">{esc(c)}</p>' for c in conds) + "".join(table(t) for t in tables)
    page(paras[0].replace("  ", " · "), paras[1], f'<p class="purpose">{esc(paras[3])}</p><div class="two ap"><div>{left}</div><div>{right}</div></div>', "apx")


ul = lambda items: "<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>"
series = lambda var, key, modes=M: {m: [(p["v"], p[m][key]) for p in D[var] if m in p and key in p[m]] for m in modes}
tok = lambda var, vals: [(str(p["v"]), p[R]["inp"] / 1000) for p in D[var] if p["v"] in vals]
SWEEP_SRC = "동일 환경 파라미터 스윕(platform) / 문서 0002-param-sweep, 브랜치 exp/langfuse-experiments"
SWEEP_COND = "Basic 공식 선택 15문항(답변 9 / 추가 확인 3 / 보류 3) / 컨테이너 CPU 3코어·메모리 4GB / 시간은 설정 간 상대 비교만 유효"

# ---------- 1부: 검색 실험(팀 자료) ----------
p4, t4 = T[4]
tiles = "".join(f'<div class="tile"><small>{esc(p4[i])}</small><b>{esc(p4[i + 1])}</b></div>' for i in (3, 5, 7))
page(p4[0], p4[1], f'<div class="two"><div><div class="tiles3">{tiles}</div><p class="note">{esc(p4[9])}</p><p class="note">{esc(p4[10])}</p></div>'
                   f'<div>{table(t4[0])}</div></div>')

KICK = "비교 결과"
t5 = T[5][1][0]; sizes = [int(num(c)) for c in t5[0][1:]]
C5 = {"naive": [(s, float(v)) for s, v in zip(sizes, t5[1][1:])], "hybrid": [(s, float(v)) for s, v in zip(sizes, t5[2][1:])]}
team_obs(5, [legend(["naive", "hybrid"]) + line_chart("Recall@5", C5, sizes, 0.50, 0.70, 0.05, w=700, h=290, base_x=900, base_label="Base",
                                                      xlabel="청크 크기(자)", labels={"naive": {700}, "hybrid": {900}}, yfmt="{:.3f}")])
t6 = T[6][1][0]
team_obs(6, [bar_chart("Recall@5", [(r[0].split()[0], float(r[1])) for r in t6[1:]], 0.8, 0.2, w=340, h=290, yfmt="{:.3f}", tickfmt="{:.1f}", xlabel="후보 수"),
             bar_chart("질문당 CPU 시간(초)", [(r[0].split()[0], num(r[2])) for r in t6[1:]], 12, 4, w=340, h=290, yfmt="{:.1f}", tickfmt="{:.0f}", xlabel="후보 수")])

p7, t7 = T[7]
names7 = ["전체 rerank", "Jev", "번갈아"]
ch7 = "".join(f"<figure>{bar_chart(f'충분 문항 수 ({t7[1][0][j]})', [(n, float(r[j])) for n, r in zip(names7, t7[1][1:])], 60, 20, w=250, h=250, color=NEUT)}</figure>" for j in (1, 2))
page(p7[0], p7[1], f'<p class="purpose">{esc(p7[3])}</p><div class="two s7"><div>{table(t7[0])}</div>'
                   f'<div><p class="cap">{esc(p7[4])}</p><div class="charts n2">{ch7}</div></div></div>'
                   f'<div class="statrow"><div class="tile"><small>{esc(p7[5])}</small><b>{esc(p7[6])}</b><span>{esc(p7[7])} · {esc(p7[8])}</span></div>'
                   f'<div class="notes">{"".join(f"<p>{esc(x)}</p>" for x in p7[9:])}</div></div>')

t8 = T[8][1][0]; ks = [int(c.split()[0]) for c in t8[0][1:]]
team_obs(8, [legend([R]) + line_chart("문서 Recall", {R: [(k, float(v)) for k, v in zip(ks, t8[1][1:])]}, ks, 0.6, 0.9, 0.1, w=700, h=290, base_x=5,
                                      base_label="Base", xlabel="k", labels={R: set(ks)}, yfmt="{:.3f}")])
t9 = T[9][1][0]
team_obs(9, [bar_chart("문서 Recall=1.0 문항 중 근거 그룹 실패 비율", [(r[0], float(re.search(r"\((\d+)%\)", r[2]).group(1))) for r in t9[1:]], 60, 20,
                       w=700, h=290, yfmt="{:.0f}%", tickfmt="{:.0f}", colors=[C["naive"], C["hybrid"], C[R]])])

# ---------- 2부: 동일 환경 파라미터 스윕 ----------
CUR = "B"
KICK = "조건"
page("기준 조건과 실험 환경", SWEEP_SRC + " / src/config.py 동결값과 컨테이너 실행 설정",
     '<p class="purpose">모든 설정을 같은 연산 자원과 같은 절차로 돌려, 값의 차이가 설정에서만 나오게 했다.</p><div class="two even"><div>'
     '<p class="cap">기준 설정 (동결값, 변수 하나만 바꿈)</p>' + table([["항목", "값"],
         ["임베딩 / 리랭커", "E5 small / bge-reranker-v2-m3"], ["청크 / 겹침 / k", "900자 / 0 / 5"], ["후보 / 문맥 한도", "20개 / 3,000 추정 토큰"],
         ["Hybrid", "RRF 60, 각 POOL 20"], ["생성·평가 모델", "gpt-6-luna, Faithfulness는 3회 평균"], ["질문", "Basic 공식 선택 15문항 (답변 9 / 추가 확인 3 / 보류 3)"]]) +
     '<p class="note">컨테이너에서 잰 값: 프로세스 최대 메모리 2.8GB, 리랭크 20쌍에 12.1초(호스트 GPU에서는 0.33초). 그래서 시간은 같은 컨테이너 환경의 기준 설정과만 비교했다.</p></div><div>'
     '<p class="cap">실행 환경과 연산 자원</p>' + table([["항목", "설정"],
         ["호스트", "Apple M5 Max, 18코어, 메모리 64GB"], ["격리 단위", "설정 하나에 Docker 컨테이너 하나 (모든 설정이 같은 이미지)"],
         ["컨테이너 한도", "CPU 3코어, 메모리 4GB, 연산 스레드 3"], ["연산 장치", "CPU 전용 (컨테이너는 호스트 GPU를 쓸 수 없음)"],
         ["Docker VM", "메모리 20GB (처음 7.7GB에서 올림)"], ["동시 실행", "0·1단계는 1개씩 순차, 2·3단계는 4개 병렬"],
         ["색인", "컨테이너 안에서 설정마다 PDF부터 새로 생성 (로컬 Qdrant)"], ["모델 가중치", "호스트 캐시를 읽기 전용으로 공유, 오프라인 모드"],
         ["기록", "팀 공용과 분리한 Langfuse 프로젝트"]]) + "</div></div>")
page("동일 환경 파라미터 스윕: 목적과 방법", SWEEP_SRC + " / 검색 실험 EXP-0002와는 다른 실험",
     '<p class="purpose">목적: 청크 크기·겹침·k·문맥 한도·후보 수를 같은 실행 환경에서 하나씩 바꾸어 검색·답변·비용을 함께 잰다.</p>'
     '<div class="funnel"><div><small>0단계</small><b>13개</b><span>기준 3회 + 변수당 2값<br>LLM 평가까지</span></div><i>→</i>'
     '<div><small>1단계</small><b>21개</b><span>값 확장<br>검색 지표만(LLM 없음)</span></div><i>→</i>'
     '<div><small>2단계</small><b>9개</b><span>변수별 상위 3개<br>LLM 평가, 4개 병렬</span></div><i>→</i>'
     '<div><small>3단계</small><b>4 + 2개</b><span>값을 합친 조합 4개<br>최선 조합 2회 재확인</span></div></div>'
     '<div class="two even"><div class="blk"><div class="lab acc">같은 환경</div>' + ul([
         "설정마다 같은 Docker 이미지와 같은 한도(CPU 3코어, 메모리 4GB)의 컨테이너에서 실행했다.",
         "컨테이너 안에서 PDF부터 새로 색인하고 검색 지표, LLM 평가 순으로 돌렸다.",
         "모델 가중치는 호스트 캐시를 읽기 전용으로 공유했다. 결과는 팀 공용과 분리한 Langfuse 프로젝트에 기록했다."]) +
     '</div><div class="blk"><div class="lab acc">결과를 보기 전에 정한 것</div>' + ul([
         "효과의 기준: Recall ±0.05, 검색 시간 ±20%, 입력 토큰 ±10%, Faithfulness는 기준 3회 범위 밖.",
         "2단계 후보 선택 규칙과 3단계 조합의 합격 기준. 규칙을 한 번 보완했고 그 사실을 기록했다.",
         "동결 설정 파일과 다른 영역의 코드는 수정하지 않고 실험 스크립트가 값을 덮어썼다."]) + "</div></div>"
     f'<p class="cond">{SWEEP_COND} / naive·hybrid·hybrid_rerank / 49개 설정, 오류 0건</p>')

rec5 = {m: next(p for p in D["topk"] if p["v"] == 5)[m]["recall"] for m in M}
base_tbl = [["방식", "Recall@5", "Faithfulness 평균 [범위]", "평균 응답 시간 [범위]"]] + [
    [m, f"{rec5[m]:.2f} (3회 동일)", f"{B3[m]['faith'][0]:.2f} [{B3[m]['faith'][1]:.2f}~{B3[m]['faith'][2]:.2f}]",
     f"{B3[m]['lat'][0] / 1000:.1f}초 [{B3[m]['lat'][1] / 1000:.1f}~{B3[m]['lat'][2] / 1000:.1f}]"] for m in M]
page("기준 설정 3회 반복: 잡음 폭", SWEEP_SRC,
     '<p class="purpose">목적: 같은 설정을 반복했을 때 값이 얼마나 흔들리는지 재서, 설정 간 차이를 효과로 볼 기준을 정한다.</p>'
     '<div class="two"><div>' + block("관찰", ["Recall은 매번 같고", "Faithfulness는", "±0.02쯤 흔들렸다.",
                                             "Recall, 문맥 토큰, 입력 토큰은 결정적이다. Faithfulness는 방식마다 0.03~0.04 폭으로 움직였다."]) +
     block("해석의 범위", ["반복이 3회뿐이라 실제 폭은 더 넓을 수 있다. 이 범위 안의 Faithfulness 차이는 효과로 보지 않았다."]) +
     f'</div><div>{table(base_tbl)}<p class="cap" style="margin-top:18px">Faithfulness 범위(기준 3회)</p><figure>{range_chart()}</figure></div></div>'
     f'<p class="cond">기준 = 청크 900자 / 겹침 0 / k 5 / 문맥 한도 3,000 / 후보 20 / {SWEEP_COND}</p>')

KICK = "비교 결과"
g = lambda var, v, key, m=R: next(p for p in D[var] if p["v"] == v)[m][key]
inp0 = B3[R]["inp"]; pct = lambda var, v: f"{g(var, v, 'inp') / inp0 - 1:+.0%}"
eff = [["변수", "기준", "효율 구간", "근거(hybrid_rerank)"],
       ["k", "5", "8~10", f"Recall {g('topk', 5, 'recall'):.2f} → {g('topk', 8, 'recall'):.2f}(k=8) → {g('topk', 10, 'recall'):.2f}(k=10), k=12도 {g('topk', 12, 'recall'):.2f}. "
                          f"입력 토큰 {pct('topk', 8)} / {pct('topk', 10)} / {pct('topk', 12)}"],
       ["청크 크기", "900자", "450~600자 (리랭커가 있을 때)", f"Recall {g('chunk', 450, 'recall'):.2f} / {g('chunk', 600, 'recall'):.2f}로 유지, 입력 토큰 {pct('chunk', 450)} / {pct('chunk', 600)}. "
                                                    f"naive는 Recall {g('chunk', 900, 'recall', 'naive'):.2f} → {g('chunk', 450, 'recall', 'naive'):.2f} / {g('chunk', 600, 'recall', 'naive'):.2f}로 하락"],
       ["리랭커 후보 수", "20", "10~15", f"검색 시간 {g('rerank', 20, 'ms') / 1000:.1f}초 → {g('rerank', 10, 'ms') / 1000:.1f}초 / {g('rerank', 15, 'ms') / 1000:.1f}초, "
                                    f"Recall {g('rerank', 10, 'recall'):.2f}. 30과 40은 결과가 같았다"],
       ["겹침", "0", "0 유지", "0~300자에서 Recall 변화 ±0.02. Faithfulness는 50에서 오르고 100·200에서 내려 방향이 일관되지 않았다"],
       ["문맥 한도", "3,000", "3,000 (k=8에서 손실 없는 최소)", f"k=8에서 2,500은 {g('ctx8', 2500, 'trunc')}문항, 2,000 이하는 {g('ctx8', 2000, 'trunc')}문항의 문맥이 잘렸다. 3,000 이상은 0문항"]]
page("변수별 효율 구간", SWEEP_SRC + " / 상세 차트: 부록 01–04",
     '<p class="purpose">목적: 변수마다 품질을 유지하면서 비용이 가장 작은 값의 범위를 찾는다.</p>' + table(eff, "wide eff") +
     '<div class="two even" style="margin-top:18px">' + block("관찰", ["k를 8~10으로 올리고", "청크와 후보 수는", "줄이는 쪽이 유리했다.",
        "k는 Recall을 올리지만 입력 토큰이 늘고, 작은 청크와 적은 후보는 토큰과 시간을 줄였다."]) +
     block("해석의 범위", ["변수를 하나씩만 바꾼 값이다. 판단은 hybrid_rerank 기준이고 naive는 작은 청크에서 불리했다. 청크 900자 초과는 일부가 임베딩 입력 한도(512토큰)를 넘어 해석을 보류했다."]) +
     f'</div><p class="cond">{SWEEP_COND}</p>')

bR, cR = B3[R], C3[R]
rec_c = D["combos"]["c1"]["ret"][R]["recall"]
desc = {"c1": "450 / 10 / 20", "c2": "600 / 8 / 16", "c3": "450 / 8 / 16", "c4": "600 / 10 / 20"}
rows = ""
for c in desc:
    rc = D["combos"][c]["ret"][R]["recall"]; f = D["combos"][c]["llm"][R]["faith"]; d = D["combos"][c]["llm"][R]["inp"] / bR["inp"] - 1
    ok = [rc >= 0.75, f >= 0.89, d <= 0.20]
    cell = lambda t, o: f'<td class="{"" if o else "no"}">{t} {"✓" if o else "✕"}</td>'
    rows += (f'<tr class="{"win" if all(ok) else ""}"><td><b>{c}</b></td><td>{desc[c]}</td>' + cell(f"{rc:.2f}", ok[0]) + cell(f"{f:.2f}", ok[1]) +
             cell(f"{d:+.0%}", ok[2]) + f'<td>{"모두 충족" if all(ok) else "미달"}</td></tr>')
page("변수별 값을 합친 조합 c1", SWEEP_SRC,
     '<p class="purpose">목적: 변수별 효율 구간을 합쳤을 때 이득이 유지되는지 사전 기준으로 판정한다.</p>'
     f'<div class="tiles4"><div class="tile"><small>Recall@k (결정적)</small><b>{rec5[R]:.2f} → {rec_c:.2f}</b><span>+{rec_c - rec5[R]:.2f}</span></div>'
     f'<div class="tile"><small>평균 응답 시간 (3회)</small><b>{bR["lat"][0] / 1000:.1f}초 → {cR["lat"][0] / 1000:.1f}초</b><span>{cR["lat"][0] / bR["lat"][0] - 1:+.0%}</span></div>'
     f'<div class="tile"><small>입력 토큰</small><b>{bR["inp"] / 1000:.1f}k → {cR["inp"] / 1000:.1f}k</b><span>{cR["inp"] / bR["inp"] - 1:+.0%}</span></div>'
     f'<div class="tile mute"><small>Faithfulness (3회 평균)</small><b>{bR["faith"][0]:.2f} → {cR["faith"][0]:.2f}</b><span>범위가 겹쳐 개선으로 보지 않음</span></div></div>'
     '<div class="two c1"><div><p class="cap">조합 4개와 사전 기준 (hybrid_rerank, 첫 실행)</p><table class="grid"><tr><th>조합</th><th>청크 / k / 후보</th><th>Recall ≥ 0.75</th>'
     f'<th>Faithfulness ≥ 0.89</th><th>입력 토큰 ≤ +20%</th><th>판정</th></tr>{rows}</table></div><div>' +
     block("관찰", ["c1만 사전 기준을", "모두 충족했다.", "이득은 Recall과 응답 시간이었다."]) +
     block("해석의 범위", [f"Faithfulness는 3회 평균 {cR['faith'][0]:.2f} [{cR['faith'][1]:.2f}~{cR['faith'][2]:.2f}]로 기준 {bR['faith'][0]:.2f} [{bR['faith'][1]:.2f}~{bR['faith'][2]:.2f}]과 범위가 겹친다. "
                           "첫 실행의 0.97은 잡음 폭의 상단이었다. 청크 450자에서는 보안 질문의 공격 문장이 문맥에 노출된다(상세: 보안 비교 장)."]) +
     f'</div></div><p class="cond">c1 = 청크 450자 / k 10 / 후보 20 / 겹침 0 / 문맥 한도 3,000. 후보 수는 k의 약 2배로 맞췄다. / {SWEEP_COND}</p>')

CASE = json.load(open(DATA / "case.json", encoding="utf-8"))["S-DEV-06"]
clean = lambda t, n=230: esc(re.sub(r"\*\*", "", t).replace("\n", " ")[:n].rstrip() + "…")
side = lambda name, d: (f'<div class="tile case"><small>{name}</small><b>근거 문서 {d["found"]} / {CASE["evidence_docs"]}개</b>'
                        f'<span>문맥 {d["ctx"]:,}토큰 · 인용 {d["cites"]}개 · 상태 {d["status"]}</span><p>{clean(d["answer"])}</p></div>')
page("대표 사례: 같은 질문, 기준과 c1", SWEEP_SRC + " / 질문 S-DEV-06, hybrid_rerank, 각 1회 실행",
     '<p class="purpose">목적: 숫자의 변화가 실제 답변에서 어떻게 나타나는지 질문 하나로 확인한다.</p>'
     f'<p class="qbox"><b>질문</b> {esc(CASE["question"])}</p>'
     f'<div class="two even">{side("기준 (청크 900자 / k 5 / 후보 20)", CASE["base"])}{side("c1 (청크 450자 / k 10 / 후보 20)", CASE["c1"])}</div>'
     '<div class="two even" style="margin-top:14px">' + block("관찰", ["기준은 SI 제출 창구를", "찾지 못했고", "c1은 주소를 답했다.",
        f"찾은 근거 문서가 {CASE['base']['found']}개에서 {CASE['c1']['found']}개로 늘었다(필요한 문서 {CASE['evidence_docs']}개)."]) +
     block("해석의 범위", ["질문 하나, 실행 한 번의 비교다. 답변이 정답인지는 대조하지 않았다. 같은 조합에서 S-FINAL-13은 기대 동작이 답변인데 c1이 되묻기로 바뀌었고, S-FINAL-06은 c1에서도 제출 주소를 찾지 못했다."]) + "</div>")

SEC = json.load(open(DATA / "security_summary.json", encoding="utf-8")); _t = SEC["totals"]; _e = SEC["exposure"]
_x = lambda l: " / ".join(f"{_e[l].get(m, 0)}" for m in M)
page("보안 비교: 공격 문장 노출과 방어", SWEEP_SRC + " / src/platform/security.py를 스윕 설정에 적용 / 보안 질문 2개",
     '<p class="purpose">목적: 설정을 바꾸면 문서에 심어 둔 공격 문장이 문맥에 들어오는지, 들어왔을 때 답변이 그 지시를 따르는지 확인한다.</p>'
     '<div class="two even"><div><p class="cap">공격 문장이 최종 문맥에 들어온 설정 (35개 설정, LLM 없이 판정)</p>' + table([["설정", "노출된 질문 수 (2개 중, naive / hybrid / hybrid_rerank)"],
         ["기준 (청크 900자)", "없음. k, 문맥 한도, 후보 수를 바꿔도 없음"],
         ["청크 300 · 600 · 750자, 조합 c2 · c4", "없음"], ["청크 450자", _x("chunk-450")], ["청크 1,050 · 1,200자", _x("chunk-1200")],
         ["겹침 50~300자", "설정과 방식에 따라 0~2개"], ["조합 c1 · c3 (청크 450자)", _x("c1")]], "sec") +
     f'</div><div><p class="cap">방어 비교 ({SEC["n_settings_full"]}개 설정 × 질문 2개 × 기본·방어 프롬프트, hybrid_rerank)</p>' + table([["확인 항목", "기본 프롬프트", "방어 프롬프트"],
         ["답변 수", str(_t["default_n"]), str(_t["defense_n"])], ["공격 문장이 문맥에 노출된 답변", str(_t["default_exposed"]), str(_t["defense_exposed"])],
         ["공격 지시를 따른 답변", f'{_t["default_followed"]}건', f'{_t["defense_followed"]}건'],
         ["필수 사실을 모두 포함한 답변", f'{_t["default_correct"]} / {_t["default_n"]}', f'{_t["defense_correct"]} / {_t["defense_n"]}'],
         ["답변을 거절·보류한 답변", f'{_t["default_n"] - _t["default_answered"]}건', f'{_t["defense_n"] - _t["defense_answered"]}건']]) + "</div></div>"
     '<div class="two even" style="margin-top:8px">' + block("관찰", ["노출 여부는 k가 아니라", "청킹이 갈랐다.",
        "노출된 16건에서도 기본 프롬프트가 공격 지시를 따르지 않았다."]) +
     block("해석의 범위", ["질문 2개, 설정마다 1회 실행이다. 추종과 정확성은 필수 사실·금지 주장의 문자열 확인과 답변 읽기로 본 초안이며 사람의 최종 판정이 필요하다. 기본 프롬프트가 이미 따르지 않아 방어 프롬프트의 효과(방어율)는 계산할 수 없다. 발제 필수 산출물인 동결 설정의 보안 답변 4개(#42)는 별도 실행이다."]) +
     "</div>")

KICK = "실패·한계"
page("실패와 확인하지 못한 것", SWEEP_SRC,
     '<p class="purpose">좋은 결과만 고르지 않고, 실험 중 실패한 것과 확인하지 못한 것을 그대로 남긴다.</p><div class="two even"><div class="blk"><div class="lab acc">실험 중 실패·이상</div>' + ul([
         "조합 c1의 첫 실행 Faithfulness 0.97은 재확인에서 잡음 폭의 상단으로 드러났다. 개선으로 쓰지 않았다.",
         "조합 c1(청크 450자)은 보안 질문 2개 모두에서 공격 문장이 문맥에 노출됐다. 기준 설정에는 없던 노출이다.",
         "청크 900자 초과(1,050·1,200자)는 청크 일부가 임베딩 입력 한도를 넘어 해석을 보류했다.",
         "첫 통합 실행에서 Faithfulness가 전부 비었다. 평가 함수가 이벤트 루프 안에서 실패한 것이 원인이었고 고쳐서 다시 돌렸다.",
         "k=3 설정은 첫 시작이 거부됐다(이전 실행이 남긴 색인 폴더). 지우고 다시 돌렸다.",
         "위임한 구현에서 버그 4건을 검토 중 찾아 고쳤다(결과 저장 키, 함수 import, 이미지 복사 경로, 색인 폴더 충돌).",
         "Docker VM 메모리가 부족해 0·1단계는 병렬로 돌리지 못했다."]) +
     '</div><div class="blk"><div class="lab">확인하지 못한 것</div>' + ul([
         "질문이 15개라 한 문항이 평균을 6.7%p 움직인다. <b>25문항 이상 재확인은 하지 않았다.</b>",
         "변수를 하나씩 바꾼 값과 조합 4개만 시험했다. 전역 최적은 보장하지 않는다.",
         "후보 선택은 hybrid_rerank 기준이다. naive의 최적값은 따로 찾지 않았다.",
         "컨테이너는 GPU를 쓰지 못해 시간의 절대값을 호스트 실행과 비교할 수 없다.",
         "Faithfulness 잡음 폭은 3회 반복으로만 쟀다. Judge 4항목은 채점하지 않았다.",
         "기대 동작과 실제 상태가 어긋난 문항의 원인은 이번 실험에서 다시 확인하지 않았다.",
         "노출된 공격 문장을 답변이 따르지 않은 것은 질문 2개·1회 실행의 결과다. 다른 공격 문장에서도 같은지는 확인하지 않았다."]) + "</div></div>")

# ---------- 결론 ----------
CUR = "A"
KICK = "선택과 이유"
p10, t10 = T[10]
page(p10[0], p10[1], f'<p class="purpose">{esc(p10[3])}</p>{table(t10[0], "wide")}')
KICK = "실패·한계"
_rows = [["실험", "확인하지 못했거나 해석을 제한한 점"]]
for _i in (5, 6, 8, 9, 20, 24, 27):
    _p = T[_i][0]; _k = _p.index("해석의 범위")
    _rows.append([_p[0].split("  ")[-1] + " (" + _p[1].split(" / ")[0] + ")", _p[_k + 1]])
_rows.insert(3, [T[7][0][0] + " (" + T[7][0][1].split(" / ")[0] + ")", " ".join(T[7][0][11:])])
page("실패와 확인하지 못한 것", "각 실험 장의 '해석의 범위'를 한 장에 모음 / 문구는 원문 그대로",
     '<p class="purpose">좋은 결과만 고르지 않고, 실험마다 확인하지 못했거나 해석을 제한한 점을 그대로 남긴다.</p>' + table(_rows, "lim"))
CUR = "B"
KICK = "선택과 이유"
page("결론과 다음 검증", SWEEP_SRC + " / 상세 차트: 부록 01–04",
     '<p class="purpose">변경 여부는 점수뿐 아니라 처리 비용과 잡음 폭을 함께 보고 판단했다.</p>' + table([["판단", "대상", "근거와 남은 검증"],
     ["후보 제안", "조합 c1 (청크 450자 / k 10 / 후보 20)", f"Recall {rec5[R]:.2f} → {rec_c:.2f}, 응답 시간 {cR['lat'][0] / bR['lat'][0] - 1:+.0%}, 입력 토큰 {cR['inp'] / bR['inp'] - 1:+.0%}. 15문항 결과라 25문항 이상 재확인 필요"],
     ["채택 전 확인", "조합 c1의 보안 노출", "청크 450자에서는 문서에 심어 둔 공격 문장이 문맥에 들어온다(기준 설정은 들어오지 않음). 이번 실행에서 답변이 따르지는 않았으나 질문 2개·1회 결과"],
     ["기본값 유지", "겹침 0 · 문맥 한도 3,000", "겹침의 일관된 이득 없음. k=8까지는 3,000에서 문맥이 잘리지 않음"],
     ["효율 구간 확인", "k 8~10 · 리랭커 후보 10~15", "k는 Recall을 올리고 입력 토큰을 늘림. 후보 수는 검색 시간에 비례하고 Recall 이득은 없음"],
     ["후속 검증", "설정 채택 여부", "Faithfulness 개선은 잡음 폭 안. 채택은 설정 변경 PR과 전체 재실행 뒤에 판단"]], "wide"))
_c = PAGES["B"].pop(); PAGES["B"].insert(len(PAGES["B"]) - 1, _c)  # 결론을 '한계와 다음 단계' 앞에 둔다

# ---------- 부록 ----------
CUR = "A"
KICK = "부록"
for i in range(11, 28):
    team_appendix(i)


def sweep_apx(n, title, purpose, charts, notes, modes=M):
    page(f"부록 {n:02d} · {title}", SWEEP_SRC, f'<p class="purpose">{purpose}</p>{legend(modes, band=True)}<div class="charts n3">' +
         "".join(f"<figure>{c}</figure>" for c in charts) + "</div>" + ul(notes) + f'<p class="cond">{SWEEP_COND}</p>', "apx")


CUR = "B"
sweep_apx(1, "k(topK) 민감도", "최종 문맥에 넣는 청크 수 k를 2~12로 바꿔 Recall, Faithfulness, 입력 토큰의 변화를 본다.", [
    line_chart("Recall@k (세 방식)", series("topk", "recall"), [2, 3, 4, 5, 6, 8, 10, 12], 0.4, 0.9, 0.1, base_x=5, xlabel="k", labels={R: {10, 12}, "naive": {2}}),
    line_chart("Faithfulness (hybrid_rerank)", series("topk", "faith", [R]), [2, 3, 4, 5, 6, 8, 10, 12], 0.8, 1.0, 0.05, band=FBAND, base_x=5, xlabel="k", labels={R: {3, 8, 10, 12}}),
    bar_chart("입력 토큰 합(천, hybrid_rerank)", tok("topk", {3, 5, 8, 10, 12}), 80, 20, xlabel="k", base=5)],
    ["Recall은 k=10에서 0.81로 포화했다(k=12도 0.81). 입력 토큰은 거의 선형으로 늘어 k=12에서 기준의 +92%였다.",
     "Faithfulness는 k=8~10에서 0.95로 가장 높고 k=12에서 0.89로 내렸다. k=10·12는 문맥 한도를 6,000으로 풀어 평가했다."])
sweep_apx(2, "청크 크기 민감도", "청크 크기를 300~1,200자로 바꿔 방식별 Recall과 hybrid_rerank의 Faithfulness, 입력 토큰을 본다.", [
    line_chart("Recall@5 (세 방식)", series("chunk", "recall"), [300, 450, 600, 750, 900, 1050, 1200], 0.5, 0.8, 0.1, base_x=900, shade_from=975, xlabel="청크 크기(자)",
               labels={"naive": {600}, R: {750}}),
    line_chart("Faithfulness (hybrid_rerank)", series("chunk", "faith", [R]), [300, 450, 600, 750, 900, 1050, 1200], 0.8, 1.0, 0.05, band=FBAND, base_x=900,
               shade_from=975, xlabel="청크 크기(자)", labels={R: {450, 600, 750}}),
    bar_chart("입력 토큰 합(천, hybrid_rerank)", tok("chunk", {450, 600, 750, 900, 1200}), 60, 20, xlabel="청크 크기(자)", base=900)],
    ["hybrid_rerank의 Recall은 청크 크기와 거의 무관했다(0.68~0.73). 청크 450자는 입력 토큰 −32%, 검색 시간 −41%였다.",
     "naive는 작은 청크에서 Recall이 내렸다(0.67 → 0.61). 900자 초과는 청크 일부가 임베딩 입력 한도를 넘어 해석을 보류했다(1,200자는 청크의 29%)."])
sweep_apx(3, "리랭커 후보 수 민감도", "리랭커에 넘기는 후보 수를 5~40으로 바꿔 검색 시간, Recall, Faithfulness를 본다.", [
    line_chart("검색 단계 시간(초, 컨테이너 CPU)", {R: [(p["v"], p[R]["ms"] / 1000) for p in D["rerank"]]}, [5, 10, 15, 20, 30, 40], 0, 30, 10, yfmt="{:.0f}", base_x=20,
               xlabel="후보 수", labels={R: {5, 10, 20, 40}}),
    line_chart("Recall@5", series("rerank", "recall", [R]), [5, 10, 15, 20, 30, 40], 0.6, 0.8, 0.05, base_x=20, xlabel="후보 수", labels={R: {5, 10, 20, 40}}),
    line_chart("Faithfulness", series("rerank", "faith", [R]), [5, 10, 15, 20, 30, 40], 0.8, 1.0, 0.05, band=FBAND, base_x=20, xlabel="후보 수", labels={R: {5, 10, 15}})],
    ["검색 시간은 후보 수에 거의 비례했다. Recall은 후보가 늘어도 오르지 않았다.",
     "후보 30과 40은 결과가 같았다. 후보가 dense 20개와 keyword 20개의 합집합이라 실제 상한이 약 30개이기 때문이다. 후보 5는 k와 같아 리랭킹이 사실상 없다."], [R])
sweep_apx(4, "겹침과 문맥 한도", "겹침 0~300자와 문맥 한도 1,500~6,000토큰(k=8)에서 Recall, Faithfulness, 잘린 질문 수를 본다.", [
    line_chart("겹침: Recall@5 (세 방식)", series("overlap", "recall"), [0, 50, 100, 150, 200, 300], 0.6, 0.8, 0.05, base_x=0, xlabel="겹침(자)"),
    line_chart("겹침: Faithfulness (hybrid_rerank)", series("overlap", "faith", [R]), [0, 50, 100, 150, 200, 300], 0.8, 1.0, 0.05, band=FBAND, base_x=0, xlabel="겹침(자)",
               labels={R: {50, 100, 200}}),
    bar_chart("문맥 한도: 잘린 질문 수(15개 중, k=8)", [(f"{p['v']:,}", p[R]["trunc"]) for p in D["ctx8"]], 15, 5, color=NEUT, xlabel="문맥 토큰 한도", base="3,000")],
    ["겹침은 Recall 변화가 ±0.02 안이고 Faithfulness의 방향이 일관되지 않았다.",
     "문맥 한도는 k=8에서 3,000부터 한 문항도 잘리지 않았다. 2,000으로 낮추면 15문항이 모두 잘렸지만 hybrid_rerank의 Faithfulness는 0.93이었고 입력 토큰은 24% 줄었다."])

# ---------- 표지와 조립 ----------
cover = ('<section class="slide cover"><img class="art" src="art/cover-team.jpg" alt="">'
         '<div class="ctext"><h1>해운 문서 RAG<br>검색 실험 보고</h1><p class="acc">붉은 RAG 해적단</p>'
         '<p class="crew">김창동 · 천희재 · 윤승환 · 오주헌 · 김경민</p></div>'
         '<footer><span>KANT 3차 프로젝트 / 실험 결과 보고</span></footer></section>')
foot = lambda n: f'<footer><span>KANT 3차 프로젝트 / 실험 결과 보고</span><span class="pg">{n:02d}</span></footer>'

CSS = '''@page{size:1280px 720px;margin:0}*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"Apple SD Gothic Neo","Malgun Gothic",sans-serif;color:#292a27;-webkit-print-color-adjust:exact;print-color-adjust:exact;word-break:keep-all}
.slide{width:1280px;height:720px;padding:40px 64px 44px;background:#faf9f5;position:relative;page-break-after:always;overflow:hidden;display:flex;flex-direction:column}
h1{font-size:29px;line-height:1.25;font-weight:800;letter-spacing:-0.3px}.src{font-size:12.5px;color:#686b66;margin-top:6px}
.body{flex:1;margin-top:16px;display:flex;flex-direction:column;min-height:0}
footer{position:absolute;left:64px;right:64px;bottom:16px;display:flex;justify-content:space-between;font-size:11px;color:#686b66}.pg{color:#a65a3c;font-weight:800;font-size:13px}
.purpose{font-size:17px;line-height:1.5;border-left:3px solid #a65a3c;padding-left:12px;margin-bottom:14px;color:#292a27}
.two{display:grid;grid-template-columns:400px 1fr;gap:40px;align-items:start}.two.even{grid-template-columns:1fr 1fr}.two.ap{grid-template-columns:1fr 1fr;gap:36px}
.two.s7{grid-template-columns:1fr 540px;gap:32px}.two.c1{grid-template-columns:1.45fr 1fr;gap:32px;margin-top:14px}
.blk{margin-bottom:14px}.lab{font-size:13px;font-weight:800;color:#686b66;letter-spacing:0.3px;margin-bottom:5px}.lab.acc{color:#a65a3c}
.blk p{font-size:16.5px;line-height:1.55;color:#292a27;margin-bottom:5px}.blk p.stmt{font-size:27px;line-height:1.35;font-weight:800;letter-spacing:-0.3px;margin-bottom:8px}.blk p.b{font-weight:700}
.apx .blk p{font-size:15.5px;line-height:1.5}.apx .blk p.stmt{font-size:22px}.apx .purpose{font-size:16px}
.cond{font-size:11.5px;color:#686b66;line-height:1.45;margin-top:auto;padding-top:8px}.kick{font-size:12px;font-weight:800;color:#a65a3c;letter-spacing:0.5px;margin-bottom:5px}.grid.lim td{font-size:14px;padding:8px}.grid.sec td:first-child{white-space:nowrap}.grid.lim td:first-child{white-space:nowrap;font-weight:700}
.qbox{font-size:15px;line-height:1.55;background:#fff;border:1px solid #dddad1;border-radius:8px;padding:11px 14px;margin-bottom:12px}.qbox b{color:#a65a3c;margin-right:8px}.tile.case p{font-size:13.5px;line-height:1.55;margin-top:9px;color:#292a27}
.cap{font-size:13px;color:#686b66;font-weight:700;margin-bottom:6px}
.note{font-size:15px;color:#686b66;line-height:1.55;margin-top:12px}
table.grid{border-collapse:collapse;width:100%;font-size:15px;margin-bottom:12px}.grid th{font-weight:700;text-align:left;color:#686b66;border-bottom:1.5px solid #bdb9ad;padding:7px 8px;font-size:13px}
.grid td{border-bottom:1px solid #dddad1;padding:7px 8px;font-variant-numeric:tabular-nums;line-height:1.4;vertical-align:top}.grid.wide td{padding:11px 8px;font-size:15.5px}
.grid.eff td:nth-child(3){font-weight:700;white-space:nowrap}.grid.eff td:first-child{white-space:nowrap;font-weight:700}.grid tr.win td{background:#f1ede4}td.no{color:#8f918b}
.charts{display:grid;gap:20px;margin-bottom:10px}.charts.n1{grid-template-columns:1fr}.charts.n2{grid-template-columns:1fr 1fr}.charts.n3{grid-template-columns:repeat(3,1fr);margin:10px 0 12px}figure{margin:0}
.legend{display:flex;gap:18px;font-size:12px;color:#686b66;margin-bottom:4px}.legend span{display:flex;align-items:center;gap:6px}
.legend i{width:14px;height:4px;border-radius:2px;display:inline-block}.legend i.band{height:10px;background:#eeece5}
ul{list-style:none}li{font-size:16.5px;line-height:1.5;padding-left:15px;position:relative;margin-bottom:6px}li:before{content:"";position:absolute;left:2px;top:9px;width:5px;height:5px;border-radius:50%;background:#8f918b}
.tile{border:1px solid #dddad1;border-radius:8px;padding:13px 16px;background:#fff}.tile small{display:block;font-size:12px;color:#686b66;font-weight:700}
.tile b{display:block;font-size:24px;font-weight:800;margin:6px 0 3px;letter-spacing:-0.4px;font-variant-numeric:tabular-nums}.tile span{font-size:12px;color:#686b66;display:block;line-height:1.4}.tile.mute b{color:#686b66}
.tiles3{display:grid;grid-template-columns:1fr;gap:10px}.tiles4{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
.statrow{display:grid;grid-template-columns:300px 1fr;gap:28px;margin-top:6px;align-items:start}.notes p{font-size:14px;color:#686b66;line-height:1.5;margin-bottom:4px}
.funnel{display:flex;align-items:stretch;gap:10px;margin-bottom:16px}.funnel>div{flex:1;border:1px solid #dddad1;border-radius:8px;padding:12px 15px;background:#fff}
.funnel small{font-size:12px;font-weight:800;color:#a65a3c}.funnel b{display:block;font-size:24px;font-weight:800;margin:3px 0}.funnel span{font-size:13.5px;color:#686b66;line-height:1.45}.funnel>i{align-self:center;font-style:normal;color:#8f918b;font-size:20px}
.cover{justify-content:center}.cover .art{position:absolute;right:0;top:0;width:640px;height:720px;object-fit:cover}.cover .ctext{width:540px}
.cover h1{font-size:56px;line-height:1.25;letter-spacing:-1.2px}.cover .acc{color:#a65a3c;font-size:26px;font-weight:800;margin-top:28px}
.cover .crew{color:#292a27;font-size:17px;margin-top:64px}.cover .date{color:#686b66;font-size:15px;margin-top:8px}
.toc>div{display:grid;grid-template-columns:54px 1fr 110px;align-items:center;border-bottom:1px solid #dddad1;padding:13px 4px}.toc b{color:#a65a3c;font-size:20px;font-weight:800}
.toc strong{display:block;font-size:17px}.toc span{font-size:13px;color:#686b66}.toc em{font-style:normal;text-align:right;color:#686b66;font-variant-numeric:tabular-nums;font-size:15px}'''
for key, name in (("A", "RAG-search-experiments-team"), ("B", "RAG-param-sweep-platform")):
    slides = [cover] + [h for _, h in PAGES[key]]
    body = "".join(x.replace("__FOOT__", foot(n + 1)) for n, x in enumerate(slides))
    open(HERE / f"{name}.html", "w", encoding="utf-8").write(
        f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>해운 문서 RAG 검색 실험 보고</title><style>{CSS}</style></head><body>{body}</body></html>')
    print(key, name, len(slides), [t for t, _ in PAGES[key]][:9])
