# -*- coding: utf-8 -*-
import html, pathlib, json, sys
OUT = pathlib.Path(__file__).parent

# ---------- shared head ----------
# Layout: 720px reading column, full-width figure band for each diagram, utilitarian memo treatment.
CSS = """
<style>
:root{
  --bg:#f5f7f9; --paper:#ffffff; --fg:#1b2731; --muted:#5b6b78; --line:#d6dde3; --soft:#eaeff3;
  --accent:#0f6e8c; --warn:#b4452c;
  --search:#1e7f8f; --answer:#a86b0a; --metrics:#6a58b5; --judge:#b5436e; --platform:#4b6578; --skeleton:#7a7f85; --docs:#8a7f5a;
  --sans:"IBM Plex Sans KR",-apple-system,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
}
@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]){
  --bg:#111920; --paper:#18222b; --fg:#e3e9ee; --muted:#9fb0bd; --line:#2d3a45; --soft:#1f2b35;
  --accent:#5fb6d1; --warn:#e8846c;
  --search:#2a97a8; --answer:#c48a2a; --metrics:#8a79d6; --judge:#d05f8b; --platform:#6c8699; --skeleton:#8d939a; --docs:#a89a6c;
  color-scheme:dark } }
:root[data-theme="dark"]{
  --bg:#111920; --paper:#18222b; --fg:#e3e9ee; --muted:#9fb0bd; --line:#2d3a45; --soft:#1f2b35;
  --accent:#5fb6d1; --warn:#e8846c;
  --search:#2a97a8; --answer:#c48a2a; --metrics:#8a79d6; --judge:#d05f8b; --platform:#6c8699; --skeleton:#8d939a; --docs:#a89a6c;
  color-scheme:dark }
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);font-family:var(--sans);line-height:1.6;
  padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:0 48px}
.wrap{max-width:1000px;margin:0 auto}
header.top{padding-block:28px 8px;border-bottom:1px solid var(--line);margin-bottom:24px}
.eyebrow{font-family:var(--mono);font-size:11.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
h1{font-size:clamp(24px,4vw,34px);line-height:1.2;margin:.3em 0 .35em;text-wrap:balance;font-weight:700}
h2{font-size:20px;margin:40px 0 10px;text-wrap:balance}
h3{font-size:15.5px;margin:22px 0 6px}
p,li{max-width:70ch}
.lede{color:var(--muted);font-size:15px;margin:0}
code,.mono{font-family:var(--mono);font-size:.92em}
code{background:var(--soft);padding:1px 5px;border-radius:4px}
figure{margin:16px 0 0}
.fig{background:var(--paper);border:1px solid var(--line);border-radius:8px;padding:14px 10px 6px;overflow-x:auto}
.fig svg{display:block;min-width:720px;max-width:100%;height:auto;margin:0 auto;font-family:var(--sans)}
figcaption{font-size:13px;color:var(--muted);margin:8px 4px 0;max-width:none}
svg text{fill:currentColor;font-size:12px}
svg .t{font-weight:600;font-size:12.5px}
svg .f{font-family:var(--mono);font-size:12px;font-weight:500}
svg .s{font-size:10.5px;fill:var(--muted)}
svg .lbl{font-size:10.5px;fill:var(--muted)}
svg .box rect{fill:var(--paper);stroke:currentColor;stroke-width:1.1;rx:5}
svg .box.search rect{fill:var(--search);stroke:none} svg .box.answer rect{fill:var(--answer);stroke:none}
svg .box.metrics rect{fill:var(--metrics);stroke:none} svg .box.judge rect{fill:var(--judge);stroke:none}
svg .box.platform rect{fill:var(--platform);stroke:none} svg .box.skeleton rect{fill:var(--skeleton);stroke:none}
svg .box.docs rect{fill:var(--docs);stroke:none}
svg .box.search text,svg .box.answer text,svg .box.metrics text,svg .box.judge text,svg .box.platform text,svg .box.skeleton text,svg .box.docs text{fill:#fff}
svg .box.search .s,svg .box.answer .s,svg .box.metrics .s,svg .box.judge .s,svg .box.platform .s,svg .box.skeleton .s,svg .box.docs .s{fill:rgba(255,255,255,.85)}
svg .ar{fill:none;stroke:currentColor;stroke-width:1.2}
svg .ar.dash{stroke-dasharray:4 3;stroke:var(--muted)}
svg .ar.ban{stroke:var(--warn);stroke-dasharray:5 3;stroke-width:1.4}
svg .band rect{fill:var(--soft);stroke:var(--line);rx:6}
svg .col rect{fill:var(--paper);stroke:var(--line);rx:8}
svg .milestone rect{fill:var(--accent);rx:3}
svg .milestone text{fill:#fff;font-weight:600;font-size:10.5px}
svg .freeze{stroke:var(--warn);stroke-width:1.4;stroke-dasharray:5 3}
svg .grid{stroke:var(--line);stroke-width:1}
table{border-collapse:collapse;width:100%;font-size:14px;margin-top:10px}
th,td{text-align:left;vertical-align:top;padding:8px 10px;border-bottom:1px solid var(--line)}
th{font-size:12px;letter-spacing:.04em;color:var(--muted);font-weight:600}
td.num{font-variant-numeric:tabular-nums;text-align:right}
.tbl{overflow-x:auto}
.chip{display:inline-block;font-family:var(--mono);font-size:11.5px;color:#fff;padding:1px 7px;border-radius:4px;line-height:1.5}
.chip.search{background:var(--search)}.chip.answer{background:var(--answer)}.chip.metrics{background:var(--metrics)}
.chip.judge{background:var(--judge)}.chip.platform{background:var(--platform)}.chip.skeleton{background:var(--skeleton)}.chip.docs{background:var(--docs)}
.chip.iface{background:var(--warn)}
.legend{display:flex;flex-wrap:wrap;gap:8px 14px;font-size:12.5px;color:var(--muted);margin-top:8px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin-top:14px}
.card{display:block;background:var(--paper);border:1px solid var(--line);border-radius:8px;padding:14px 16px;color:inherit;text-decoration:none;min-width:0}
.card:hover,.card:focus-visible{border-color:var(--accent);outline:none}
.card b{display:block;font-size:15.5px;margin-bottom:4px}
.card span{font-size:13px;color:var(--muted)}
.note{border-left:3px solid var(--accent);padding:6px 12px;background:var(--paper);font-size:14px;margin:14px 0}
.note.warn{border-color:var(--warn)}
pre.tree{font-family:var(--mono);font-size:12.5px;line-height:1.55;background:var(--paper);border:1px solid var(--line);border-radius:8px;padding:14px 16px;overflow-x:auto;margin:12px 0 0}
pre.tree i{font-style:normal;color:var(--muted)}
ol.steps{padding-left:1.3em}
ol.steps li{margin:4px 0}
.two{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:18px}
.two>div{min-width:0}
nav.back{font-size:13px;margin-top:10px}
a{color:var(--accent)}
footer{margin-top:48px;font-size:12.5px;color:var(--muted);border-top:1px solid var(--line);padding-top:12px}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}

body::before{content:"";position:fixed;inset:0 0 auto;height:env(safe-area-inset-top,0px);z-index:10;background:var(--bg)}
nav.agenda{position:sticky;top:env(safe-area-inset-top,0px);z-index:5;background:var(--bg);border-bottom:1px solid var(--line);margin:0 0 8px;padding:8px 0;display:flex;gap:6px;overflow-x:auto;scrollbar-width:none}
nav.agenda a{flex:0 0 auto;font-size:12.5px;padding:4px 10px;border:1px solid var(--line);border-radius:999px;color:var(--fg);text-decoration:none;background:var(--paper);white-space:nowrap}
nav.agenda a:hover,nav.agenda a:focus-visible{border-color:var(--accent);outline:none}
section.item{padding:28px 0 8px;border-top:1px solid var(--line);scroll-margin-top:64px}
section.item:first-of-type{border-top:0}
.q{font-size:clamp(20px,3vw,26px);margin:4px 0 6px;text-wrap:balance}
.say{font-size:15.5px;max-width:72ch;margin:0 0 12px}
.grid4{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-top:10px}
.tile{background:var(--paper);border:1px solid var(--line);border-radius:8px;padding:12px 14px;min-width:0}
.tile b{display:block;margin-bottom:3px}
.tile span{font-size:13px;color:var(--muted)}
.check{list-style:none;padding:0;margin:10px 0 0;display:grid;gap:8px}
.check li{display:flex;gap:10px;align-items:flex-start;background:var(--paper);border:1px solid var(--line);border-radius:8px;padding:10px 12px;font-size:14.5px}
.check li::before{content:"";flex:0 0 18px;height:18px;border:1.6px solid var(--muted);border-radius:4px;margin-top:3px}
.steps2{counter-reset:s;display:grid;gap:10px;margin-top:10px}
.step{display:grid;grid-template-columns:32px 1fr;gap:10px;align-items:start;background:var(--paper);border:1px solid var(--line);border-radius:8px;padding:10px 12px}
.step::before{counter-increment:s;content:counter(s);width:28px;height:28px;border-radius:50%;background:var(--accent);color:#fff;font-weight:700;display:flex;align-items:center;justify-content:center;font-size:13px}
.step>div{min-width:0}
.step b{display:block;margin-bottom:2px}
.step p{margin:2px 0;font-size:14px}
pre.cmd{font-family:var(--mono);font-size:12.5px;line-height:1.6;background:var(--soft);border:1px solid var(--line);border-radius:6px;padding:10px 12px;overflow-x:auto;margin:6px 0 0}
pre.cmd i{font-style:normal;color:var(--muted)}
.appendix{font-size:13.5px;color:var(--muted)}
.kv{display:grid;grid-template-columns:max-content 1fr;gap:4px 14px;font-size:14px;margin-top:8px}
.kv b{color:var(--muted);font-weight:500}
</style>
"""
FONT = '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500&display=swap">'

def head(title):
    return f'<title>{html.escape(title)}</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n{FONT}\n{CSS}\n'

FOOT = '<footer>출처: <code>README.md</code>, <code>docs/work-plan.md</code>, <code>docs/specs/*.md</code>, <code>docs/adr/*.md</code>, <code>AGENTS.md</code>, GitHub Issue #8–#47 · 기준일 2026-11-05(main 7f4bd7f). 문서가 바뀌면 이 페이지가 아니라 레포 문서가 기준이다.</footer>'

# ---------- svg helpers ----------
DEFS = '<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="currentColor"/></marker><marker id="am" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="var(--muted)"/></marker><marker id="ab" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="var(--warn)"/></marker></defs>'

def box(x,y,w,h,title,sub=None,cls="",mono=True):
    tc = "f" if mono else "t"
    ty = y+h/2+ (4 if sub is None else -3)
    s = f'<g class="box {cls}"><rect x="{x}" y="{y}" width="{w}" height="{h}"/>'
    s += f'<text class="{tc}" x="{x+w/2}" y="{ty}" text-anchor="middle">{html.escape(title)}</text>'
    if sub: s += f'<text class="s" x="{x+w/2}" y="{ty+15}" text-anchor="middle">{html.escape(sub)}</text>'
    return s+'</g>'

def arrow(pts,label=None,lx=None,ly=None,cls="",anchor="middle",marker="a"):
    d = " ".join(f"{p[0]},{p[1]}" for p in pts)
    s = f'<polyline class="ar {cls}" points="{d}" marker-end="url(#{marker})"/>'
    if label:
        if lx is None:
            (x1,y1),(x2,y2)=pts[0],pts[-1]; lx=(x1+x2)/2; ly=(y1+y2)/2-6
        s += f'<text class="lbl" x="{lx}" y="{ly}" text-anchor="{anchor}">{html.escape(label)}</text>'
    return s

def text(x,y,t,cls="lbl",anchor="start"):
    return f'<text class="{cls}" x="{x}" y="{y}" text-anchor="{anchor}">{html.escape(t)}</text>'

def svg(vb_w,vb_h,body,label):
    return f'<svg viewBox="0 0 {vb_w} {vb_h}" role="img" aria-label="{html.escape(label)}" xmlns="http://www.w3.org/2000/svg">{DEFS}{body}</svg>'

def figure(svgstr,cap):
    return f'<figure><div class="fig">{svgstr}</div><figcaption>{cap}</figcaption></figure>'

LEGEND = '<div class="legend"><span><span class="chip search">search</span> 윤승환</span><span><span class="chip answer">answer</span> 천희재</span><span><span class="chip metrics">metrics</span> 오주헌</span><span><span class="chip judge">judge</span> 김경민</span><span><span class="chip platform">platform</span> 김창동(리드)</span></div>'

pages = {}

# =====================================================================
# PAGE A: 요청 흐름과 영역 계약
# =====================================================================
# --- Diagram A1: service request path
W,H = 1040,390
b = []
bw,bh,y = 150,52,70
xs = [20,190,360,530,700,870]
b.append(box(xs[0],y,bw,bh,"사용자","FastAPI docs / 러너",cls="",mono=False))
b.append(box(xs[1],y,bw,bh,"POST /query","빈 질문·잘못된 mode는 422",cls="platform"))
b.append(box(xs[2],y,bw,bh,"run_query()","request_id(번호표) 생성",cls="platform"))
b.append(box(xs[3],y,bw,bh,"retrieve()","조각 k개 찾기 · mode",cls="search"))
b.append(box(xs[4],y,bw,bh,"build_context()","S1,S2 번호 · 토큰 한도",cls="answer"))
b.append(box(xs[5],y,bw,bh,"generate()","프롬프트 · JSON 검증",cls="answer"))
ay = y+22
labels = ["question, mode", "QueryRequest", "query", "list[RetrievedChunk]", "list[ContextChunk]"]
for i in range(5):
    b.append(arrow([(xs[i]+bw,ay),(xs[i+1],ay)], labels[i], lx=(xs[i]+bw+xs[i+1])/2, ly=ay-10))
# return LLMOutput+citations to run_query
b.append(arrow([(900,y+bh),(900,150),(430,150),(430,y+bh)], "LLMOutput + list[Citation]  (source_ids ⊆ 문맥 ID 검증 후)", lx=665, ly=144))
# response to client
b.append(arrow([(400,y+bh),(400,200),(90,200),(90,y+bh)], "QueryResponse · status / answer / reason / citations", lx=240, ly=194))
b.append(text(240,214,"status ∈ answered · needs_clarification · abstained · error(코드가 정함)",anchor="middle"))
# llm.call and model
b.append(arrow([(980,y+bh),(980,210)], "messages · kind=service", lx=988, ly=170, anchor="start"))
b.append(box(870,210,bw,bh,"platform.llm.call()","timeout·재시도·토큰·시간",cls="platform"))
b.append(arrow([(940,262),(940,300)]))
b.append(box(870,300,bw,bh,"gpt-6-luna","발제 지정 생성 모델",cls="",mono=True))
b.append(text(945,375,"llm.call()이 유일한 LLM 진입점",anchor="middle"))
# Langfuse band
b.append(f'<g class="band"><rect x="20" y="290" width="720" height="70"/></g>')
b.append(text(380,314,"Langfuse 트레이스 — request_id 하나로 묶임",cls="t",anchor="middle"))
b.append(text(380,333,"스팬 retrieve → build_context → generate → validate · 실제 모델 입출력 · 토큰 · 시간 · 비밀값 제외",anchor="middle"))
b.append(text(380,349,"retrieve 결과와 build_context 결과를 둘 다 남겨 “못 찾음”과 “찾았지만 잘림”을 구분",anchor="middle"))
b.append(arrow([(415,y+bh),(415,290)], "tracing.span()", lx=422, ly=250, anchor="start", cls="dash", marker="am"))
b.append(arrow([(870,236),(800,236),(800,325),(740,325)], "generation 기록", lx=806, ly=290, anchor="start", cls="dash", marker="am"))
svgA1 = svg(W,H,"".join(b),"질문이 /query로 들어와 platform, search, answer를 거쳐 응답으로 돌아오는 경로와, 모든 단계가 request_id 하나로 Langfuse에 남는 구조")

# --- Diagram A2: evaluation loop
W,H = 1090,380
b=[]
bw,bh = 150,52
r1,r2,r3 = 40,180,310
b.append(box(20,r1,bw,bh,"evaluation/*.json","질문 · 정답 · 채점 기준",cls=""))
b.append(box(200,r1,bw,bh,"metrics.loader","질문과 정답을 분리",cls="metrics"))
b.append(box(380,r1,bw,bh,"metrics.run","질문 × 3방식 실행",cls="metrics"))
b.append(box(560,r1,bw,bh,"platform.run_query()","API와 같은 길",cls="platform"))
b.append(box(740,r1,bw,bh,"RunRecord","<mode>.jsonl 한 줄씩",cls="metrics"))
b.append(box(200,r2,bw,bh,"GroundTruth","정답 문서 · 기대 동작 · 기준",cls="metrics"))
b.append(box(740,r2,bw,bh,"judge.score()","RAGAS · Judge 4항목",cls="judge"))
b.append(box(920,r2,bw,bh,"llm.call(kind=eval)","채점 호출은 따로 센다",cls="platform"))
b.append(box(380,r3,bw,bh,"Hit@k · Recall@k","정답 문서를 찾았나",cls="metrics"))
b.append(box(560,r3,bw,bh,"metrics.report","comparison.md (+CSV)",cls="metrics"))
b.append(box(740,r3,bw,bh,"EvalRecord","eval.jsonl",cls="judge"))
b.append(box(920,r3,bw,bh,"record_score()","점수를 Langfuse에",cls="platform"))
ay=r1+22
b.append(arrow([(170,ay),(200,ay)]))
b.append(arrow([(350,ay),(380,ay)],"id, question",lx=365,ly=ay-10))
b.append(arrow([(530,ay),(560,ay)],"question, mode",lx=545,ly=ay-10))
b.append(arrow([(710,ay),(740,ay)],"RunRecord",lx=725,ly=ay-10))
b.append(arrow([(275,r1+bh),(275,r2)],"정답 측만 분리",lx=268,ly=140,anchor="end"))
b.append(arrow([(815,r1+bh),(815,r2)],"runs (실패도 포함)",lx=822,ly=140,anchor="start"))
b.append(arrow([(350,r2+26),(740,r2+26)],"truths · 답변이 만들어진 뒤에만",lx=545,ly=r2-6))
b.append(arrow([(300,r2+bh),(300,270),(420,270),(420,r3)],"evidence_book_ids",lx=306,ly=262,anchor="start"))
b.append(arrow([(760,r1+bh),(760,125),(490,125),(490,r3)],"retrieved_book_ids",lx=496,ly=160,anchor="start"))
b.append(arrow([(890,r2+26),(920,r2+26)]))
b.append(arrow([(815,r2+bh),(815,r3)],"EvalRecord",lx=822,ly=280,anchor="start"))
b.append(arrow([(870,r2+bh),(870,280),(995,280),(995,r3)],"점수 붙이기",lx=932,ly=275))
b.append(arrow([(740,r3+26),(710,r3+26)],"question_id + mode 조인",lx=725,ly=r3-8))
b.append(arrow([(530,r3+26),(560,r3+26)]))
# ban
b.append(f'<polyline class="ar ban" points="300,{r2} 300,105 622,105" marker-end="url(#ab)"/>')
b.append(f'<circle cx="635" cy="105" r="11" fill="none" stroke="var(--warn)" stroke-width="1.6"/><line x1="627" y1="113" x2="643" y2="97" stroke="var(--warn)" stroke-width="1.6"/>')
b.append(f'<text x="652" y="101" class="lbl" style="fill:var(--warn)">금지: 정답·기준을</text><text x="652" y="115" class="lbl" style="fill:var(--warn)">run_query에 넣지 않음</text>')
svgA2 = svg(W,H,"".join(b),"평가 루프: metrics가 질문을 세 방식으로 run_query에 돌려 RunRecord를 만들고, judge가 GroundTruth와 대조해 EvalRecord를 만들고, metrics가 비교표로 합친다. GroundTruth는 run_query 입력에 들어가지 않는다")

pageA = head("질문이 답이 되는 과정") + f"""
<div class="wrap">
<header class="top"><div class="eyebrow">proj_3rd · kant_project_3 · 구조</div>
<h1>질문이 답이 되는 과정</h1>
<p class="lede">사용자가 질문을 보내면 다섯 영역이 어떤 순서로 손을 대는지, 그리고 세 검색 방식을 비교하는 실험은 그 위에서 어떻게 돌아가는지. 영역끼리 주고받는 데이터 모양은 <code>src/contracts.py</code> 한 파일에 모아 둔다.</p>
<nav class="back">← <a href="__INDEX__">킥오프 지도</a></nav></header>

<h2>1. 질문 하나가 들어와서 답이 나가기까지</h2>
<p>쉽게 말하면: 입구(<span class="chip platform">platform</span>)가 질문을 받아 번호표(<code>request_id</code>)를 붙이고, <span class="chip search">search</span>가 PDF에서 관련 조각을 찾아오고, <span class="chip answer">answer</span>가 그 조각만 보고 답을 쓰고, 다시 platform이 걸린 시간과 토큰을 재서 Langfuse에 남긴다.</p>
<p>실험을 돌리는 러너도 API와 똑같이 <code>run_query()</code> 함수를 부른다. 그래서 서비스 응답과 실험 결과가 같은 길을 지나고, 측정은 이 함수와 <code>llm.call()</code> 두 곳에만 있으면 된다. 다른 영역은 LLM을 직접 부르지 않는다.</p>
{figure(svgA1,"그림 1. 질문의 이동 경로. 윗줄이 가는 길, 아래 두 줄이 돌아오는 값. 색은 그 단계를 책임지는 사람. 회색 띠는 모든 단계가 번호표 하나로 Langfuse에 기록된다는 뜻.")}
{LEGEND}

<h2>2. 세 검색 방식을 같은 질문으로 돌려 점수 매기기</h2>
<p>쉽게 말하면: <span class="chip metrics">metrics</span>가 평가 질문을 naive · hybrid · hybrid_rerank로 세 번씩 돌려 결과를 한 줄씩 저장하고, <span class="chip judge">judge</span>가 그 결과를 정답과 대조해 점수를 매기고, 다시 metrics가 점수를 붙여 비교표를 만든다.</p>
<p>정답 파일은 채점에만 쓴다. 검색이나 프롬프트에 섞이면 시험지를 보고 시험을 치는 것이 되어 비교가 무의미해진다. 그래서 그림에 금지 경로를 따로 그렸다.</p>
{figure(svgA2,"그림 2. 실험이 돌아가는 순서. 붉은 점선은 절대 가면 안 되는 길. 채점용 LLM 호출은 따로 세어서 서비스 응답 시간·토큰 통계에 섞이지 않게 한다.")}

<h2>3. 영역끼리 주고받는 데이터: 누가 만들고 누가 쓰나</h2>
<p>아래 표가 영역 사이의 약속이다. 내 영역이 "만드는 쪽"이면 그 모양을 바꾸기 전에 "읽는 쪽" 담당자에게 먼저 말한다. 실제 정의는 <code>src/contracts.py</code>에 코드로 있고(뼈대 PR에서 생김), 바꾸는 PR은 제목 앞에 <code>[interface]</code>를 붙인다.</p>
<div class="tbl"><table>
<tr><th>타입 / 함수</th><th>만드는 쪽</th><th>읽는 쪽</th><th>핵심 규칙</th></tr>
<tr><td><code>ChunkMeta</code>, <code>RetrievedChunk</code>, <code>retrieve()</code></td><td><span class="chip search">search</span></td><td><span class="chip answer">answer</span> <span class="chip metrics">metrics</span></td><td>점수 내림차순 최대 k개. 결과 없으면 빈 목록. <code>chunk_id = "&lt;book_id&gt;-p&lt;page&gt;-c&lt;n&gt;"</code>, 첫 페이지 = 1. 없는 메타데이터를 만들지 않는다</td></tr>
<tr><td><code>ContextChunk</code>, <code>LLMOutput</code>, <code>Citation</code>, <code>build_context()</code>, <code>generate()</code></td><td><span class="chip answer">answer</span></td><td><span class="chip platform">platform</span> <span class="chip judge">judge</span></td><td><code>source_ids ⊆ 문맥 ID</code>가 아니면 재생성, 그래도 실패면 <code>ValidationFailed</code>. 문서명·페이지는 코드가 대응표로 변환, LLM이 만들지 않는다</td></tr>
<tr><td><code>QueryRequest</code>, <code>QueryResponse</code>, <code>run_query()</code>, <code>llm.call()</code>, <code>tracing.span()</code>, <code>record_score()</code></td><td><span class="chip platform">platform</span></td><td>전 영역</td><td>단일 경로. 측정 못 한 값은 <code>None</code>(0 아님). <code>error</code> 상태는 코드가 정하고 <code>citations=[]</code></td></tr>
<tr><td><code>RunRecord</code>, <code>GroundTruth</code></td><td><span class="chip metrics">metrics</span></td><td><span class="chip judge">judge</span></td><td>질문 하나 × 방식 하나. 실패 실행도 기록. <code>GroundTruth</code>는 채점과 검색 지표에만</td></tr>
<tr><td><code>EvalRecord</code>, <code>JudgeItem</code>, <code>TokenUsage</code>, <code>score()</code></td><td><span class="chip judge">judge</span></td><td><span class="chip metrics">metrics</span></td><td><code>null</code>을 0이나 1로 바꾸지 않는다. 해당 없음과 평가 불가를 이유로 구분. 세 방식에 같은 평가 모델·프롬프트</td></tr>
</table></div>

<h2>4. 짝: 내 변경이 바로 영향을 주는 사람</h2>
<p>위 표의 데이터를 직접 주고받는 두 사람이 짝이다. 서로 리뷰할 의무는 없다. 바꾸기 전에 알려주기만 하면 되고, 어떻게 알려줄지는 둘이 정한다. 리드는 <code>[interface]</code> PR을 머지할 때 짝이 알고 있는지만 묻는다.</p>
<div class="tbl"><table>
<tr><th>짝</th><th>오가는 것</th><th>그림</th></tr>
<tr><td><span class="chip search">search</span> ↔ <span class="chip answer">answer</span></td><td>조각(<code>RetrievedChunk</code>). 청킹 크기가 바뀌면 문맥 토큰 한도 계산이 바뀐다</td><td>그림 1, retrieve → build_context</td></tr>
<tr><td><span class="chip metrics">metrics</span> ↔ <span class="chip judge">judge</span></td><td>실행 결과(<code>RunRecord</code>, <code>GroundTruth</code>)와 채점 결과(<code>EvalRecord</code>)</td><td>그림 2, 세로 화살표 두 개</td></tr>
<tr><td><span class="chip platform">platform</span> ↔ <span class="chip metrics">metrics</span></td><td><code>run_query()</code> 호출과 <code>RunRecord</code>의 측정 필드(<code>latency_ms</code>, 토큰)</td><td>그림 2, metrics.run → run_query</td></tr>
</table></div>

<div class="note">뼈대(<code>contracts.py</code>, <code>config.py</code>, <code>naive</code> 1문항 end-to-end)는 리드가 11/6 오전까지 머지한다. 그때까지 머지가 안 되면 각자 spec의 인터페이스 절만 보고 mock으로 시작하고, 머지 후 리베이스한다.</div>
{FOOT}
</div>"""
pages["flow"] = pageA

# =====================================================================
# PAGE B: 레포 구조와 문서 체계
# =====================================================================
W,H = 1000,320
b=[]
bw,bh=170,56
b.append(box(20,40,bw,bh,"발제 원문 (Notion)","다르면 원문이 우선",cls="",mono=False))
b.append(box(230,40,bw,bh,"docs/requirements.md","+ evaluation.md · 발제 요약",cls="docs"))
b.append(box(440,40,bw,bh,"docs/adr/NNNN-*.md","왜 이렇게 결정했나 · 불변",cls="docs"))
b.append(box(650,40,bw,bh,"docs/specs/<영역>.md","지금 어떻게 동작하나 · 계속 갱신",cls="docs"))
b.append(box(440,190,bw,bh,"src/config.py","동결 설정 단일 출처 (11/10)",cls="platform"))
b.append(box(650,190,bw,bh,"src/contracts.py","영역 간 계약 = 코드",cls="platform"))
b.append(box(840,190,140,bh,"src/<영역>/","담당자 코드",cls="skeleton"))
ay=68
b.append(arrow([(190,ay),(230,ay)],"요약",lx=210,ly=ay-10))
b.append(arrow([(400,ay),(440,ay)],"제약",lx=420,ly=ay-10))
b.append(arrow([(610,ay),(650,ay)],"결정 →",lx=630,ly=ay-10))
b.append(arrow([(735,96),(735,190)],"인터페이스 절이 설명",lx=742,ly=145,anchor="start"))
b.append(arrow([(715,190),(715,96)]))
b.append(arrow([(525,96),(525,190)],"미정 값을 여기서 확정",lx=532,ly=145,anchor="start"))
b.append(arrow([(820,218),(840,218)],"import",lx=830,ly=208))
b.append(arrow([(610,218),(440+bw,218)]))
b.append(arrow([(820,96),(910,96),(910,190)],"기준 문서",lx=916,ly=150,anchor="start"))
# same-PR bracket
b.append('<rect x="430" y="20" width="560" height="245" rx="10" fill="none" stroke="var(--accent)" stroke-dasharray="6 4" stroke-width="1.3"/>')
b.append(text(440,290,"동작·구조를 바꾸는 PR은 이 안의 것들을 함께 바꾼다: 코드 + spec (+ 되돌리기 어려운 결정이면 새 ADR). PR 템플릿 체크 항목.",cls="lbl"))
b.append(text(700,32,"",cls="lbl"))
svgB = svg(W,H,"".join(b),"발제 원문이 requirements와 evaluation으로 요약되고, ADR이 결정을, spec이 현재 동작을, contracts.py가 계약을 담는다. 코드와 spec은 같은 PR에서 함께 바뀐다")

tree = """<pre class="tree">kant_project_3/
├── CLAUDE.md                 <i>에이전트가 처음 읽는 파일. branch-strategy, documentation을 끌어옴</i>
├── AGENTS.md                 <i>사람·에이전트 공통 규칙: 읽는 순서, 금지 사항</i>
├── README.md                 <i>프로젝트 입구. 팀·영역·흐름·스택. 설치·실행·기여는 미정(제출 전 작성)</i>
├── .env.example              <i>키 이름만. 실제 .env는 커밋 금지</i>
├── .github/
│   ├── CODEOWNERS            <i>* → @C-Designer. 리드 승인 없이는 머지 버튼이 안 열림</i>
│   └── pull_request_template.md   <i>변경 내용 / 확인 방법(실행 증거) / 체크 4개</i>
├── docs/
│   ├── requirements.md       <i>발제 요약: 필수 4과제, 데이터 규칙, API, 상태값, 완료 기준</i>
│   ├── evaluation.md         <i>채점 규칙: Hit@k·Recall@k, RAGAS, Judge 4항목, null, 운영 지표, 보안</i>
│   ├── work-plan.md          <i>역할, 일정(M0~M6), 리뷰·머지, Issue·보드 운영, 리스크</i>
│   ├── branch-strategy.md    <i>GitHub Flow, 룰셋, 커밋·PR 형식</i>
│   ├── documentation.md      <i>ADR·spec 규약</i>
│   ├── adr/
│   │   ├── 0000-template.md
│   │   ├── 0001-adr-and-spec-as-ssot.md      <i>문서 두 종류를 기준으로</i>
│   │   ├── 0002-areas-by-concern.md          <i>레이어가 아닌 관심사 5영역, 뼈대 먼저</i>
│   │   └── 0003-stack.md                     <i>pypdf·LangChain·E5·Qdrant·FastAPI·Langfuse·RAGAS</i>
│   └── specs/
│       ├── _template.md
│       ├── search.md  answer.md  metrics.md  judge.md  platform.md   <i>영역당 1개. 범위/동작/인터페이스/미정</i>
├── src/
│   ├── search/  answer/  metrics/  judge/  platform/   <i>지금은 README 1줄씩. 뼈대 머지 후 채움</i>
│   ├── api/                  <i>(뼈대에서 생김) FastAPI main.py, schemas.py</i>
│   ├── contracts.py          <i>(뼈대에서 생김) 공용 Pydantic 타입</i>
│   └── config.py             <i>(뼈대에서 생김) 동결 대상 설정</i>
├── data/shipping/            <i>git 제외. documents/*.pdf 15개, evaluation/*.json</i>
└── results/                  <i>(실행 후 생김) questions.json, runs/&lt;run_id&gt;/, comparison.md, review.md, security.md</i></pre>"""

pageB = head("레포에 무엇이 어디 있나") + f"""
<div class="wrap">
<header class="top"><div class="eyebrow">proj_3rd · kant_project_3 · 레포</div>
<h1>레포에 무엇이 어디 있나</h1>
<p class="lede">지금 레포는 코드가 거의 없고 문서가 전부다. 어떤 문서가 무엇을 정하는지, 코드가 생기면 어디에 들어가는지, 그리고 뭘 바꿀 때 어느 문서를 같이 고쳐야 하는지.</p>
<nav class="back">← <a href="__INDEX__">킥오프 지도</a></nav></header>

<h2>1. 파일 트리 (main 7f4bd7f 기준)</h2>
<p>회색 주석이 설명. <i>(뼈대에서 생김)</i>, <i>(실행 후 생김)</i>으로 표시한 것은 아직 없다.</p>
{tree}

<h2>2. 문서 세 종류가 각각 정하는 것</h2>
<p>쉽게 말하면: <code>requirements</code>·<code>evaluation</code>은 발제가 시킨 것, ADR은 우리가 왜 그렇게 하기로 했는지, spec은 내 영역이 지금 어떻게 동작하는지다. 코드는 spec을 따르고, 동작을 바꾸면 코드와 spec을 같은 PR에서 고친다.</p>
<p>담당자가 되면 제일 먼저 할 일은 자기 spec에서 "미정"이라고 적힌 칸을 실제 값으로 채우는 것이다. 그게 곧 팀에 공유되는 설계 문서다.</p>
{figure(svgB,"그림 1. 발제가 코드가 되는 길. ADR은 한 번 쓰면 안 고치고 생각이 바뀌면 새 번호로 쓴다. spec은 코드와 함께 계속 고친다. 점선 안은 한 PR에서 같이 움직이는 것들.")}

<div class="two">
<div><h3>작업 전에 읽는 순서 (AGENTS.md)</h3>
<ol class="steps">
<li><code>docs/branch-strategy.md</code> — 브랜치·PR 규칙</li>
<li><code>docs/requirements.md</code> — 무엇을 만드나, 발제의 고정 규칙</li>
<li>자기 영역 <code>docs/specs/&lt;영역&gt;.md</code> + <code>src/contracts.py</code></li>
<li>채점 관련 작업이면 <code>docs/evaluation.md</code></li>
</ol>
<p>에이전트(Claude Code, Codex)도 같은 순서다. <code>CLAUDE.md</code>가 1번과 문서 규약을 자동으로 끌어온다.</p></div>
<div><h3>문서별로 언제 고치나</h3>
<div class="tbl"><table>
<tr><th>문서</th><th>고치는 때</th></tr>
<tr><td>spec</td><td>동작·구조를 바꾸는 PR마다, 같은 PR에서. 미정을 확정했을 때</td></tr>
<tr><td>ADR</td><td>되돌리기 어려운 선택(스택, 데이터 구조, 인터페이스, 협업 규칙). 번호 = 마지막 + 1. 기존 ADR은 안 고침</td></tr>
<tr><td>README</td><td>설치·실행, Langfuse 확인법, 최종 선택, 기여 — 제출 전 각자 자기 절</td></tr>
<tr><td>requirements / evaluation</td><td>발제 원문과 다를 때만</td></tr>
<tr><td>work-plan</td><td>담당·일정·운영 방식이 바뀔 때</td></tr>
</table></div></div>
</div>

<h2>3. 내 폴더에서 지킬 것</h2>
<ul>
<li><b>영역 하나 = 담당 1명 = spec 1개 = <code>src/&lt;영역&gt;/</code> 1개.</b> 레이어가 아니라 "무엇의 품질을 책임지나"로 나눴다(ADR 0002).</li>
<li><b>다른 영역 폴더는 읽되 고치지 않는다.</b> 고쳐야 하면 담당자에게 Issue나 PR 코멘트로.</li>
<li><b>LLM 호출은 <code>platform.llm.call()</code>로만.</b> 직접 SDK를 부르면 측정과 트레이스가 빠진다.</li>
<li><b>동결 설정은 <code>config.py</code>에만.</b> k, 토큰 한도, 모델, timeout을 코드에 흩뿌리지 않는다.</li>
<li><b>테스트는 규칙을 고정하는 용도.</b> <code>None</code> 집계, <code>source_ids</code> 검증, <code>book_id</code> 파생 같은 발제 규칙만. 커버리지 목표 없음.</li>
<li><b>커밋 금지:</b> <code>data/</code>, <code>.env</code>, 키, 개인정보.</li>
</ul>
{FOOT}
</div>"""
pages["repo"] = pageB

# =====================================================================
# PAGE C: GitHub 운영 — Issue에서 머지까지
# =====================================================================
W,H = 1040,340
b=[]
cw,ch,cy = 225,250,60
cols = [("Todo",20),("In Progress",285),("Review",550),("Done",815)]
for name,x in cols:
    b.append(f'<g class="col"><rect x="{x}" y="{cy}" width="{cw}" height="{ch}"/></g>')
    b.append(text(x+cw/2,cy+22,name,cls="t",anchor="middle"))
def lines(x,y,arr,cls="lbl"):
    return "".join(text(x,y+i*16,t,cls=cls) for i,t in enumerate(arr))
b.append(lines(32,cy+48,["Issue #N 생성 (반나절~하루 단위)","· 라벨 = 영역 (search … platform, docs)","· 마일스톤 M1 / M3 / M6","· 담당자 1명","· 본문: 할 일 · 완료 조건 · 기준 문서","","작은 버그 하나는 Issue 없이 PR만 가능"]))
b.append(lines(297,cy+48,["git switch main && git pull","git switch -c <type>/<짧은-설명>","커밋  <type>: <설명>","git push -u origin <브랜치>","PR: 제목 <type>: … · 본문 템플릿","    Closes #N · 실행 명령·결과 캡처","contracts/config 변경 →","    [interface] + 짝 알림"],cls="lbl"))
b.append(lines(562,cy+48,["PR 올린 사람이 카드를 Review로 옮김","리드가 보는 4가지","① 돌아가는가 (실행 증거)","② spec·contracts와 맞는가, spec도 고쳤나","③ 키·개인정보·data/ 없는가","④ 에이전트 코드를 담당자가 설명 가능한가","새 push가 오면 이전 승인은 무효"]))
b.append(lines(827,cy+48,["리드가 Squash and merge","(룰셋: 리드 승인 없이는 버튼 안 열림)","원격 브랜치 자동 삭제","Issue 자동 닫힘","로컬: git switch main && git pull","       git branch -D <브랜치>","main 커밋 제목 = 커밋 1개면","    그 메시지, 아니면 PR 제목"]))
ay=cy-18
b.append(arrow([(245,ay+30),(285,ay+30)],"자동: PR 연결(Closes #N)",lx=265,ly=ay+20))
b.append(arrow([(510,ay+30),(550,ay+30)],"수동: 올린 사람",lx=530,ly=ay+20))
b.append(arrow([(775,ay+30),(815,ay+30)],"자동: 머지·닫힘",lx=795,ly=ay+20))
b.append(arrow([(0,ay+30),(20,ay+30)],"",))
b.append(text(20,ay+2,"자동: Issue 생성 → Todo",cls="lbl"))
# feedback loop from review to in progress
b.append(arrow([(600,cy+ch),(600,cy+ch+28),(400,cy+ch+28),(400,cy+ch)],"수정 요청 → 다시 push (승인 무효, 재리뷰)",lx=500,ly=cy+ch+22))
svgC = svg(W,H,"".join(b),"Project 보드의 네 열 Todo, In Progress, Review, Done과 각 열에서 하는 일. Review로 옮기는 것만 수동이고 나머지 이동은 자동이다")
# lite version for the meeting page: column names + who moves the card
W,H = 1040,230
b=[]
cw,ch,cy = 225,150,60
for name,x in cols:
    b.append(f'<g class="col"><rect x="{x}" y="{cy}" width="{cw}" height="{ch}"/></g>')
    b.append(text(x+cw/2,cy+26,name,cls="t",anchor="middle"))
b.append(lines(32,cy+54,["할 일 카드","Issue 만들면 자동으로 생김","라벨 = 영역, 마일스톤, 담당자 1명"]))
b.append(lines(297,cy+54,["브랜치에서 작업 중","PR 올리고 본문에 Closes #N","(안 움직이면 내가 옮긴다)"]))
b.append(lines(562,cy+54,["리드가 봐 주세요","PR 올린 사람이 카드를 여기로","수정 요청 → 같은 브랜치에 push"]))
b.append(lines(827,cy+54,["끝","리드가 Squash and merge","Issue 자동 닫힘, 브랜치 자동 삭제"]))
ay=cy-18
b.append(arrow([(245,ay+30),(285,ay+30)],"자동",lx=265,ly=ay+20))
b.append(arrow([(510,ay+30),(550,ay+30)],"수동: 내가",lx=530,ly=ay+20))
b.append(arrow([(775,ay+30),(815,ay+30)],"자동",lx=795,ly=ay+20))
b.append(text(20,ay+2,"Issue 생성 → Todo (자동)",cls="lbl"))
b.append(text(1030,ay+2,"GitHub 마일스톤은 M1·M3·M6 셋뿐. M0·M2·M4·M5는 일정표 이름",cls="lbl",anchor="end"))
svgC_lite = svg(W,H,"".join(b),"보드 네 칸과 카드를 누가 옮기는지. Review로 옮기는 것만 내가 직접 한다")

issues = [
 ("skeleton","M1 뼈대 (11/6)","C-Designer","김창동","#8 contracts.py · #9 config.py · #10 naive 1문항 E2E · #11 규칙 고정 테스트",4),
 ("search","M3 동결·전체 실행 (11/10)","yshzjq","윤승환","#12 데이터셋 검수·ingest-report · #13 청킹 · #14 E5·Qdrant 스키마 · #15 hybrid · #16 hybrid_rerank · #17 spec 갱신",6),
 ("answer","M3 동결·전체 실행 (11/10)","rjqnrll7-cmyk","천희재","#18 문맥 조립 · #19 프롬프트 v1 · #20 출력 검증·재생성 · #21 빈 결과·조건 누락 · #22 방어 프롬프트 · #23 spec 갱신",6),
 ("metrics","M3 동결·전체 실행 (11/10)","ohjuhun1119","오주헌","#24 로더 · #25 질문 선택 · #26 러너→RunRecord · #27 Hit@k·Recall@k · #30 spec 갱신",5),
 ("metrics","M6 제출 (11/13)","ohjuhun1119","오주헌","#28 운영 지표 집계 · #29 비교표",2),
 ("judge","M3 동결·전체 실행 (11/10)","kokoball-eval","김경민","#31 Judge 프롬프트 v1·파싱 · #32 null 규칙 테스트 · #33 RAGAS · #34 llm.call(eval)·record_score · #35 평가 모델 확정 · #37 spec 갱신",6),
 ("judge","M6 제출 (11/13)","kokoball-eval","김경민","#36 대표 사례 원문 대조 (results/review.md)",1),
 ("platform","M3 동결·전체 실행 (11/10)","C-Designer","김창동","#38 /query 오류 응답 · #39 llm.call 측정·eval 분리 · #40 Langfuse 스팬·record_score · #41 config.py 동결 · #45 spec 갱신",5),
 ("platform","M6 제출 (11/13)","C-Designer","김창동","#42 보안 비교 4개 · #43 README·교차 재실행 · #44 시연 녹화 백업",3),
 ("docs","M6 제출 (11/13)","C-Designer","김창동","#46 발표자료 뼈대 7장 · #47 팀 Notion 제출",2),
]
rows = "".join(f'<tr><td><span class="chip {a}">{a}</span></td><td>{m}</td><td>{n}<br><span class="mono" style="color:var(--muted)">@{g}</span></td><td>{t}</td><td class="num">{c}</td></tr>' for a,m,g,n,t,c in issues)

pageC = head("일을 받아서 main에 넣는 순서") + f"""
<div class="wrap">
<header class="top"><div class="eyebrow">proj_3rd · kant_project_3 · GitHub 운영</div>
<h1>일을 받아서 main에 넣는 순서</h1>
<p class="lede">할 일 하나는 Issue 하나, 바꾼 것 한 묶음은 PR 하나, main에 넣는 것은 리드만. Project 보드는 그 상태를 보여주는 창이다. 2026-11-05 기준 Issue 40개가 전부 열려 있고, 머지된 PR 8개는 모두 리드가 올린 문서 PR이다.</p>
<nav class="back">← <a href="__INDEX__">킥오프 지도</a></nav></header>

<h2>1. 카드 하나가 보드를 지나가는 길</h2>
<p>보드: <a href="https://github.com/users/C-Designer/projects/1">github.com/users/C-Designer/projects/1</a> (팀원 Write). 뷰 2개: <b>보드</b>(Status 열), <b>담당별</b>(Assignee 그룹 + 라벨·마일스톤). 리드가 매일 보고, In Progress에 이틀 넘게 있는 카드를 묻는다.</p>
{figure(svgC,"그림 1. Issue가 Todo에서 Done까지 가는 길과 각 칸에서 할 일. 칸 사이 이동 중 Review로 옮기는 것만 사람이 직접 한다. 리뷰에서 수정 요청이 오면 같은 브랜치에 다시 push하고 Review로 되돌린다.")}

<h2>2. GitHub이 대신 막아주는 것과 우리가 지키기로 한 것</h2>
<div class="two">
<div><h3>룰셋 <code>main-protection</code>이 강제</h3>
<div class="tbl"><table>
<tr><th>금지</th><th>대신</th></tr>
<tr><td><code>main</code> 직접 push (리드도)</td><td>브랜치 → PR</td></tr>
<tr><td><code>main</code> force push · 삭제</td><td>revert PR</td></tr>
<tr><td>승인 1 + 코드오너(<code>@C-Designer</code>) 승인 없이 머지</td><td>리드가 리뷰·승인·머지. 본인 PR은 룰셋 우회</td></tr>
<tr><td>새 push 후 이전 승인 유지</td><td>재승인</td></tr>
</table></div>
<p style="font-size:13px;color:var(--muted)">필수 status check는 없다(CI 없음). 그래서 PR 본문의 실행 증거가 CI 역할을 한다.</p></div>
<div><h3>팀 규칙 (GitHub은 못 막음)</h3>
<ul style="font-size:14px">
<li><b>머지는 리드만.</b> 승인 뒤 다른 사람이 버튼을 누르지 않는다</li>
<li><b>PR 하나에 목적 하나.</b> 반나절 단위. 하루 넘게 쌓이면 쪼갠다</li>
<li><b>브랜치 <code>&lt;type&gt;/&lt;짧은-설명&gt;</code>, 커밋·PR 제목 <code>&lt;type&gt;: &lt;설명&gt;</code>.</b> type: feat fix refactor docs test chore</li>
<li><b><code>[interface]</code>:</b> <code>contracts.py</code>·<code>config.py</code> 변경은 제목에 붙이고 짝에게 먼저 알림. 라벨 <span class="chip iface">interface</span></li>
<li><b>리드가 안 보는 것:</b> 스타일, 네이밍, 리팩터 제안. 메모만 남기고 막지 않는다</li>
<li><b>11/12 이후:</b> 버그 수정 PR만</li>
<li><b>남의 브랜치에 push하지 않는다.</b> 충돌은 올린 사람이 <code>git merge origin/main</code>으로</li>
</ul></div>
</div>

<h2>3. 지금 내 이름으로 열려 있는 Issue (전체 40개, #8–#47)</h2>
<p>마일스톤 3개: <a href="https://github.com/C-Designer/kant_project_3/milestone/1">M1 뼈대</a> 4개 · <a href="https://github.com/C-Designer/kant_project_3/milestone/2">M3 동결·전체 실행</a> 28개 · <a href="https://github.com/C-Designer/kant_project_3/milestone/3">M6 제출</a> 8개. 11/9까지 끝나야 하는 것은 전부 M3에 들어 있다. 영역별로 보려면 <a href="https://github.com/C-Designer/kant_project_3/issues">Issue 목록</a>에서 라벨로 필터.</p>
<div class="tbl"><table>
<tr><th>라벨</th><th>마일스톤</th><th>담당</th><th>Issue</th><th style="text-align:right">수</th></tr>
{rows}
<tr><td colspan="4"><b>합계</b> (전부 Open, 2026-11-05)</td><td class="num"><b>40</b></td></tr>
</table></div>
<p style="font-size:13.5px">모든 영역에 "spec 미정 항목 갱신" Issue가 하나씩 있다(#17 #23 #30 #37 #45). 담당자가 미정을 값으로 바꾸는 것이 곧 공유 문서가 되기 때문이다. 새 작업이 생기면 담당자가 Issue를 만들고 라벨·마일스톤을 붙인다(자동으로 보드에 들어감).</p>

<h2>4. PR을 올릴 때 채우는 칸 (<code>.github/pull_request_template.md</code>)</h2>
<div class="tbl"><table>
<tr><th>항목</th><th>채우는 것</th></tr>
<tr><td>변경 내용</td><td>무엇을 왜 바꿨는지</td></tr>
<tr><td>확인 방법</td><td>실행한 명령과 결과(캡처). 프롬프트 변경이면 정상·되묻기·보류 1문항씩</td></tr>
<tr><td>체크 4개</td><td>□ spec(·ADR) 같은 PR에서 갱신 · □ contracts/config 바꿨으면 [interface] + 짝 확인 · □ 키·개인정보·data/ 없음 · □ 에이전트 코드를 내가 설명 가능</td></tr>
</table></div>
<div class="note warn"><code>gh pr create --fill</code>은 쓰지 않는다(커밋 내용으로 본문이 채워진다). 에이전트로 비대화형 실행 시 템플릿을 채운 본문을 <code>--title</code>, <code>--body</code>로 넘긴다.</div>
{FOOT}
</div>"""
pages["github"] = pageC

# =====================================================================
# PAGE D: 8일 일정과 마일스톤
# =====================================================================
W,H = 1000,430
b=[]
x0,dw = 150,94
days = ["11/5 목","11/6 금","11/7 토","11/8 일","11/9 월","11/10 화","11/11 수","11/12 목","11/13 금"]
ms = {0:"M0",1:"M1",4:"M2",5:"M3",6:"M4",7:"M5",8:"M6"}
top=30
for i,d in enumerate(days):
    cx = x0+i*dw+dw/2
    b.append(text(cx,top,d,cls="t",anchor="middle"))
    if i in ms:
        if ms[i] in ("M1","M3","M6"):
            b.append(f'<g class="milestone"><rect x="{cx-16}" y="{top+8}" width="32" height="16"/><text x="{cx}" y="{top+20}" text-anchor="middle">{ms[i]}</text></g>')
        else:
            b.append(f'<rect x="{cx-16}" y="{top+8}" width="32" height="16" rx="3" fill="none" stroke="var(--muted)"/><text class="lbl" x="{cx}" y="{top+20}" text-anchor="middle">{ms[i]}</text>')
    b.append(f'<line class="grid" x1="{x0+i*dw}" y1="{top+30}" x2="{x0+i*dw}" y2="{H-60}"/>')
b.append(f'<line class="grid" x1="{x0+9*dw}" y1="{top+30}" x2="{x0+9*dw}" y2="{H-60}"/>')
# (start, end) 는 end 미포함: (1,4) = 11/6·11/7·11/8
rows_ = [
 ("리드 (뼈대)","platform",[(0,1.5,"뼈대 → 11/6 오전 머지")],[(1.5,9,"모든 PR 리뷰·머지, 보드 점검 (전 기간)")]),
 ("search","search",[(1,4,"청킹 v1 → hybrid → hybrid_rerank")],[(4,5,"rerank 11/9")]),
 ("answer","answer",[(2,5,"프롬프트 v1 · 검증·재생성 · 방어")],[(1,2,"mock")]),
 ("metrics","metrics",[(3,6,"지표 · 표 초안 · 질문 확정 · 전체 실행")],[(1,3,"mock으로 로더·러너"),(6,7,"비교표 완성")]),
 ("judge","judge",[(5,7,"자동 채점 · 원문 대조")],[(2,5,"프롬프트·null 테스트·RAGAS")]),
 ("platform","platform",[(1,5,"Langfuse · llm.call · 오류 응답 · 보안 스크립트"),(7,8,"재실행·녹화")],[(5,6,"보안 4개"),(8,8.54,"리허설")]),
 ("전원 공통","skeleton",[(5,7,"전체 실행 · 원문 대조 · 슬라이드"),(7,8,"발표본 최종")],[(8,8.54,"리허설")]),
]
ry=top+48; rh=30; gap=8
for name,cls,peaks,lights in rows_:
    b.append(text(x0-10,ry+rh/2+4,name,cls="t",anchor="end"))
    for s,e,l in lights:
        b.append(f'<g class="box {cls}" opacity=".38"><rect x="{x0+s*dw+2}" y="{ry+6}" width="{(e-s)*dw-4}" height="{rh-12}"/></g>')
        b.append(text(x0+s*dw+8,ry+rh/2+4,l,cls="s"))
    for s,e,l in peaks:
        b.append(f'<g class="box {cls}"><rect x="{x0+s*dw+2}" y="{ry}" width="{(e-s)*dw-4}" height="{rh}"/>')
        b.append(f'<text class="s" x="{x0+s*dw+8}" y="{ry+rh/2+4}" style="fill:#fff">{html.escape(l)}</text></g>')
    ry += rh+gap
# freeze lines
fx = x0+5*dw
b.append(f'<line class="freeze" x1="{fx}" y1="{top+30}" x2="{fx}" y2="{H-40}"/>')
b.append(f'<text class="lbl" x="{fx+4}" y="{H-44}" style="fill:var(--warn)">config.py 동결 (11/10 아침)</text>')
fx2 = x0+7*dw
b.append(f'<line class="freeze" x1="{fx2}" y1="{top+30}" x2="{fx2}" y2="{H-40}"/>')
b.append(f'<text class="lbl" x="{fx2+4}" y="{H-44}" style="fill:var(--warn)">버그만 · 이날 발표본까지 끝</text>')
fx3 = x0+8*dw+dw*0.54
b.append(f'<line class="freeze" x1="{fx3}" y1="{top+30}" x2="{fx3}" y2="{H-40}"/>')
b.append(f'<text class="lbl" x="{fx3-4}" y="{H-26}" text-anchor="end" style="fill:var(--warn)">리허설 → 13:00 제출 → 발표</text>')
b.append(text(x0,H-8,"진한 막대 = 그 영역의 피크(work-plan 기준). 연한 막대 = 그 밖의 계획된 작업. 색 채운 M1·M3·M6만 GitHub 마일스톤. 모임은 시간 될 때.",cls="lbl"))
svgD = svg(W,H,"".join(b),"11월 5일부터 13일까지 영역별 피크 기간과 마일스톤 M0~M6, 11/10 설정 동결선, 11/12 발표본 포함 최종 완료선, 11/13은 리허설과 13시 제출")

pageD = head("8일 동안 누가 언제 무엇을") + f"""
<div class="wrap">
<header class="top"><div class="eyebrow">proj_3rd · kant_project_3 · 일정</div>
<h1>8일 동안 누가 언제 무엇을</h1>
<p class="lede">2026-11-05(목)부터 11-13(금) 13:00 제출까지. 날짜마다 "이 날 끝에는 이게 돼 있어야 한다"로 읽으면 된다. 발표본까지 전부 목요일(11/12)에 끝내고, 금요일은 리허설과 제출만 한다. 모임 시간은 따로 정하지 않고 시간 될 때 모인다.</p>
<nav class="back">← <a href="__INDEX__">킥오프 지도</a></nav></header>

<h2>1. 누가 언제 가장 바쁜가</h2>
{figure(svgD,"그림 1. search가 가장 먼저 끝나고 judge가 가장 늦다. 11/10 아침에 설정을 잠근(동결) 뒤에는 비교 실험만 돌린다. 그 뒤 설정을 하나라도 바꾸면 실험을 전부 다시 돌려야 한다. 11/12에 발표본까지 끝내고 11/13은 리허설·제출만.")}
{LEGEND}

<h2>2. 날짜별로 이 날 끝에 돼 있어야 하는 것</h2>
<div class="tbl"><table>
<tr><th>날</th><th>M</th><th>이 날 끝에 돼 있어야 하는 것</th></tr>
<tr><td>11/5 목</td><td>M0</td><td>해운·Basic, 담당 확정(완료). 데이터 다운로드·PDF 15개 검수. 각자 로컬(Python, Qdrant). Langfuse 프로젝트. 발표 목차 합의. 리드가 뼈대 시작</td></tr>
<tr><td>11/6 금</td><td>M1</td><td><b>뼈대 머지.</b> 전원 로컬에서 <code>naive</code> 1문항 실행 확인. 각자 영역 첫 PR</td></tr>
<tr><td>11/7 토</td><td></td><td>search 청킹 v1·hybrid 초안 / answer 프롬프트 v1이 정상·되묻기·보류 각 1문항 통과 / metrics 로더·러너·Hit/Recall / judge 프롬프트 초안·null 테스트 / platform Langfuse 스팬·config</td></tr>
<tr><td>11/8 일</td><td></td><td>search hybrid 완성 / answer 출력 검증·재생성 / metrics 운영 지표·표 초안 / judge RAGAS·Judge 1문항 통과 / platform LLM 래퍼·오류 응답. 리드: 슬라이드 뼈대</td></tr>
<tr><td>11/9 월</td><td>M2</td><td>search hybrid_rerank / metrics 질문 목록 확정 / judge 평가 모델·프롬프트 확정 / platform 보안 비교 스크립트. <b>동결할 설정 합의</b></td></tr>
<tr><td>11/10 화</td><td>M3</td><td>아침 <code>config.py</code> <b>동결</b> → metrics 전체 실행 → judge 자동 채점 → platform 보안 4개. 실행·오류 분석은 5명이 질문 묶음으로 분담</td></tr>
<tr><td>11/11 수</td><td>M4</td><td>비교표 완성. 대표 사례 원문 대조(전원, 자기 영역 아닌 결과). 최종 구성 선택과 이유. 영역별 슬라이드</td></tr>
<tr><td>11/12 목</td><td>M5</td><td><b>기능 추가 금지, 버그 수정만.</b> 구현 안 한 팀원이 README대로 설치·실행 성공. 슬라이드 통합해 <b>발표본(PPTX + PDF) 최종 완료</b>. 시연 녹화 백업. 이날 끝에 제출물이 전부 갖춰져 있어야 한다</td></tr>
<tr><td>11/13 금</td><td>M6</td><td>오전 <b>리허설</b>(발표 연습, 시연 경로 점검). 팀 Notion에 저장소·발표자료 연결. <b>13:00 제출.</b> 오후 발표. 새 작업은 하지 않는다</td></tr>
</table></div>

<div class="two">
<div><h2>3. 11/10부터는 내 영역과 상관없이 전원이</h2>
<div class="tbl"><table>
<tr><th>일</th><th>내용</th></tr>
<tr><td>최종 실행</td><td>질문 묶음을 5명이 나눠 실행. 오류 나면 담당 영역에 Issue</td></tr>
<tr><td>원문 대조</td><td><b>자기 영역이 아닌 결과</b>를 PDF 원문과 대조. 1인 2~3건 → <code>results/review.md</code></td></tr>
<tr><td>README</td><td>각자 자기 영역 절: 실행 방법, 설정값, 한계, 기여</td></tr>
<tr><td>발표</td><td>각자 자기 영역 슬라이드를 11/11까지, 11/12에 통합해 발표본 완료. 목차 7장: ①문제·데이터 ②아키텍처·스택 ③3방식 비교 ④품질·보안 ⑤운영 지표·최종 선택 ⑥한계·실패 ⑦기여. 시연은 ③~④ 사이. 11/13은 리허설만</td></tr>
</table></div></div>
<div><h2>4. 일정이 밀리면 이 순서로 뺀다</h2>
<ol class="steps">
<li>평가 질문 수 축소 (예: 20 → 10). 발제는 수를 정하지 않는다</li>
<li>리랭커를 가장 작은 모델로, 또는 후보 수 축소</li>
<li>대표 사례 원문 대조를 영역당 1건으로</li>
<li><b>README 재실행 검증은 자르지 않는다.</b> 완료 기준 "다시 실행할 수 있는가"가 여기서 검증된다</li>
</ol>
<h3>리스크</h3>
<div class="tbl"><table>
<tr><th>리스크</th><th>대응</th></tr>
<tr><td>리랭커·E5 로컬 실행이 느리거나 안 됨</td><td>11/7까지 확인. 더 작은 모델로 교체, 조건 기록</td></tr>
<tr><td>프롬프트가 되묻기·보류를 못 가림</td><td>11/9 M2에서 각 1문항 이상 통과를 조건으로</td></tr>
<tr><td>동결 후 설정 변경 유혹</td><td>바꾸면 전체 재실행. 리드가 막는다</td></tr>
<tr><td>평가 LLM 비용·한도</td><td>질문 수를 비용 안에서. 채점 토큰은 별도 집계</td></tr>
<tr><td>재실행 실패</td><td>11/12 구현 안 한 사람이 README대로 설치</td></tr>
</table></div></div>
</div>

<div class="note">11/5 미팅에서 정할 spec 미정 항목: <code>k</code> 기본값, 평가 LLM, Langfuse Cloud/셀프호스트, Python 버전·패키지 관리 도구, 데이터 다운로드·PDF 검수 당번.</div>
{FOOT}
</div>"""
pages["schedule"] = pageD


# =====================================================================
# small SVGs for the meeting page
# =====================================================================
# what we build
W,H = 980,230
b=[]
b.append(box(20,40,170,56,"PDF 15개 · 360쪽","해운 · Basic · data/shipping/",cls="",mono=False))
b.append(box(230,40,170,56,"색인","청킹 → E5 임베딩 → Qdrant",cls="search"))
b.append(box(440,40,250,56,"질문 → 검색 → 답변 → 출처","gpt-6-luna · 문서명·페이지 · 되묻기·보류",cls="platform"))
b.append(box(730,40,230,56,"같은 질문 × 3방식 → 비교표","Hit/Recall · Faithfulness · Judge · 시간·토큰",cls="metrics"))
b.append(arrow([(190,68),(230,68)]))
b.append(arrow([(400,68),(440,68)]))
b.append(arrow([(690,68),(730,68)],"수십 번 반복",lx=710,ly=30))
for i,(m,sub) in enumerate([("naive","벡터 유사도만"),("hybrid","벡터 + 키워드"),("hybrid_rerank","hybrid 후 리랭커로 재정렬")]):
    b.append(box(440+i*0,140+i*0,0,0,"") if False else "")
xs3=[400,590,780]
for i,(m,sub) in enumerate([("naive","벡터 유사도만"),("hybrid","벡터 + 키워드 결합"),("hybrid_rerank","hybrid 후보를 리랭커로 재정렬")]):
    b.append(box(xs3[i],150,180,52,m,sub,cls="search"))
b.append(arrow([(565,96),(565,130),(490,130),(490,150)]))
b.append(arrow([(565,130),(680,130),(680,150)]))
b.append(arrow([(680,130),(870,130),(870,150)]))
b.append(text(380,135,"검색 방식만 바꿔 세 번 실행 (PDF·청크·임베딩·프롬프트·k는 동일)",anchor="end"))
b.append(text(20,150,"필수 4과제",cls="t"))
b.append(lines(20,172,["① PDF 근거로 답하고 출처 표시","② 세 방식 구현·비교·최종 선택","③ FastAPI + LangChain + Langfuse(필수)","④ 평가셋으로 품질·운영·보안 확인"]) if False else "")
for i,t in enumerate(["① PDF 근거로 답하고 문서명·페이지 표시","② 세 방식을 같은 조건으로 비교해 하나 선택","③ FastAPI + LangChain + Langfuse 로 한 요청에 연결","④ 평가셋으로 검색·답변·운영·보안 지표 확인"]):
    b.append(text(20,172+i*16,t))
svgWhat = svg(W,H,"".join(b),"PDF 15개를 색인하고, 질문에 검색·답변·출처로 응답하는 서비스를 세 검색 방식으로 돌려 비교표를 만든다")

# pairs
W,H = 720,240
b=[]
bw,bh=130,46
b.append(box(20,40,bw,bh,"search","윤승환",cls="search"))
b.append(box(200,40,bw,bh,"answer","천희재",cls="answer"))
b.append(box(400,40,bw,bh,"metrics","오주헌",cls="metrics"))
b.append(box(580,40,bw,bh,"judge","김경민",cls="judge"))
b.append(box(400,160,bw,bh,"platform","김창동 · 리드",cls="platform"))
b.append(arrow([(150,63),(200,63)],"조각(청크)",lx=175,ly=30))
b.append(arrow([(530,63),(580,63)],"실행 결과 ↔ 채점",lx=555,ly=30))
b.append(arrow([(465,160),(465,86)],"run_query() · 측정값",lx=472,ly=126,anchor="start"))
b.append(text(20,130,"짝 = 데이터를 직접 주고받는 둘. 바꾸기 전에 서로 알려준다.",cls="lbl"))
b.append(text(20,150,"리드 = platform 담당 + 모든 PR 리뷰·머지 + 보드 점검.",cls="lbl"))
b.append(text(20,170,"리뷰는 리드 혼자. 짝은 리뷰 의무 없음.",cls="lbl"))
b.append(text(20,206,"platform ↔ 나머지 전부: llm.call(), tracing.span() 같은 공용 함수를 제공",cls="lbl"))
svgPairs = svg(W,H,"".join(b),"다섯 영역과 담당자, 그리고 데이터를 직접 주고받는 짝 세 쌍: search와 answer, metrics와 judge, platform과 metrics")

# GitHub structure (for the beginner page)
W,H = 900,330
b=[]
b.append('<rect x="20" y="14" width="570" height="296" rx="10" fill="none" stroke="var(--line)"/>')
b.append(text(32,52,"저장소 github.com/C-Designer/kant_project_3",cls="t"))
b.append('<rect x="620" y="20" width="260" height="290" rx="10" fill="none" stroke="var(--line)"/>')
b.append(text(632,42,"Project 보드 (projects/1)",cls="t"))
b.append(box(40,62,200,60,"Issue #13","[search] 청킹 전략 결정·구현",cls="search"))
b.append(box(270,50,130,32,"라벨: search",cls="",mono=False))
b.append(box(270,90,130,32,"마일스톤: M3 (11/10)",cls="",mono=False))
b.append(box(270,130,130,32,"담당자: @yshzjq",cls="",mono=False))
b.append(arrow([(240,80),(270,66)])); b.append(arrow([(240,92),(270,106)])); b.append(arrow([(240,104),(270,146)]))
b.append(text(410,66,"← Issue에 붙는 것 3개",cls="lbl"))
b.append(text(410,80,"라벨: 영역으로 필터",cls="lbl"))
b.append(text(410,106,"마일스톤: 기한 있는 묶음",cls="lbl"))
b.append(text(410,120,"M1 4개 · M3 28개 · M6 8개",cls="lbl"))
b.append(text(410,146,"담당자: 항상 1명",cls="lbl"))
b.append(box(40,210,100,40,"main",cls="",mono=True))
b.append(box(180,210,150,40,"feat/chunking",cls="",mono=True))
b.append(box(370,200,200,60,"PR #N","본문에 Closes #13 · 리드 리뷰 → 머지",cls="platform"))
b.append(arrow([(140,230),(180,230)],"분기",lx=160,ly=220))
b.append(arrow([(330,230),(370,230)],"push",lx=350,ly=220))
b.append(arrow([(470,260),(470,285),(90,285),(90,250)],"Squash and merge (리드만)",lx=280,ly=279))
b.append(arrow([(470,200),(470,178),(140,178),(140,122)],"머지되면 Issue 자동 닫힘",lx=305,ly=192,cls="dash",marker="am"))
cols=[("Todo","Issue 만들면 자동"),("In Progress","PR 연결되면 자동"),("Review","PR 올린 사람이 수동으로"),("Done","머지·닫힘 시 자동")]
for i,(c,n) in enumerate(cols):
    y=58+i*60
    b.append(f'<g class="col"><rect x="636" y="{y}" width="228" height="48"/></g>')
    b.append(text(648,y+20,c,cls="t")); b.append(text(648,y+37,n,cls="s"))
    if i<3: b.append(arrow([(750,y+48),(750,y+60)]))
b.append(arrow([(140,62),(140,30),(600,30),(600,82),(636,82)],"카드로 자동 등장",lx=370,ly=26,cls="dash",marker="am"))
svgGH = svg(W,H,"".join(b),"저장소 안의 Issue에 라벨·마일스톤·담당자가 붙고, 작업 브랜치의 PR이 Closes로 Issue를 가리키며, 머지되면 Issue가 닫힌다. Project 보드는 Issue를 카드로 보여주는 별도 화면이다")

# =====================================================================
# PAGE M: 킥오프 진행 자료 (한 장)
# =====================================================================
def meeting(urls):
    u = lambda k: urls.get(k,"#")
    return head("proj_3rd 킥오프") + f"""
<div class="wrap">
<header class="top"><div class="eyebrow">KANT 3차 프로젝트 · kant_project_3 · 2026-11-05 킥오프 · 같이 보며 넘기는 자료</div>
<h1>proj_3rd 킥오프</h1>
<p class="lede">위에서 아래로 한 번 내려가면 끝. 안건마다 질문 하나, 그림 하나, 말할 것 세 줄. 더 깊은 내용은 각 안건 끝의 부록 링크.</p></header>
<nav class="agenda" aria-label="안건">
<a href="#s1">1 만드는 것</a><a href="#s2">2 누가 무엇을</a><a href="#s3">3 돌아가는 길</a><a href="#s4">4 비교 실험</a><a href="#s5">5 레포</a><a href="#s6">6 일하는 법</a><a href="#s7">7 일정</a><a href="#s8">8 오늘 정할 것</a>
</nav>

<section class="item" id="s1"><div class="eyebrow">안건 1 · 3분</div>
<h2 class="q">우리는 무엇을 만드나?</h2>
<p class="say">해운 회사 물류 담당자가 PDF 15개를 뒤지지 않고 물어보면, 근거 문서와 페이지를 붙여 답하는 서비스. 그리고 검색 방식 세 가지를 같은 질문으로 돌려 어느 것이 나은지 숫자로 보여주는 비교표.</p>
{figure(svgWhat,"그림. 왼쪽에서 오른쪽으로: 문서 → 색인 → 서비스 → 비교. 아래 세 상자가 비교 대상인 검색 방식. 나머지는 전부 같게 두고 검색만 바꾼다.")}
<div class="grid4">
<div class="tile"><b>제출</b><span>11/13(금) 13:00. 당일 오후 발표. 오늘부터 8일</span></div>
<div class="tile"><b>완료 기준</b><span>맞히는 수가 아니라 "다시 실행할 수 있는가"와 "모두가 자기 작업을 설명할 수 있는가"</span></div>
<div class="tile"><b>안 하는 것</b><span>대화 메모리, 화면 UI, 파인튜닝, 배포, OCR. 필수 4개 끝내기 전엔 선택 과제도 안 한다</span></div>
<div class="tile"><b>금지</b><span>정답 파일을 검색·프롬프트에 넣기, 키·데이터 커밋, 좋은 결과만 골라 싣기</span></div>
</div>
<p class="appendix">부록: <code>docs/requirements.md</code>(발제 요약), <code>docs/evaluation.md</code>(채점 규칙)</p>
</section>

<section class="item" id="s2"><div class="eyebrow">안건 2 · 3분</div>
<h2 class="q">누가 무엇을 맡나?</h2>
<p class="say">영역 다섯 개를 한 사람씩. 레이어(DB·API·화면)가 아니라 "무엇의 품질을 책임지나"로 나눴다. 전원이 에이전트로 코드를 쓰니 코드 양이 아니라 판단과 합치기가 병목이기 때문이다. 소통은 Slack <code>proj_3rd</code>, 모임은 시간 될 때 모이고 리드가 참석한다.</p>
{figure(svgPairs,"그림. 다섯 영역과 짝. 화살표가 있는 둘은 데이터를 직접 주고받으므로 바꾸기 전에 서로 알려준다.")}
<div class="tbl"><table>
<tr><th>영역</th><th>담당 · GitHub</th><th>한 줄로</th><th>가장 어려운 것</th></tr>
<tr><td><span class="chip search">search</span></td><td>윤승환<br><span class="mono" style="color:var(--muted)">@yshzjq</span></td><td>PDF를 조각내 색인하고, 질문에 맞는 조각을 세 방식으로 찾아준다</td><td>표·단위·적용일이 끊기지 않게 청킹</td></tr>
<tr><td><span class="chip answer">answer</span></td><td>천희재<br><span class="mono" style="color:var(--muted)">@rjqnrll7-cmyk</span></td><td>조각을 보고 답을 쓰고, 되물을지·보류할지 판단하고, 출처를 붙인다</td><td>프롬프트 튜닝은 끝이 없음</td></tr>
<tr><td><span class="chip metrics">metrics</span></td><td>오주헌<br><span class="mono" style="color:var(--muted)">@ohjuhun1119</span></td><td>질문 묶음을 세 방식으로 자동 실행하고 검색·운영 지표를 집계해 비교표를 만든다</td><td>None을 0으로 만들지 않는 집계</td></tr>
<tr><td><span class="chip judge">judge</span></td><td>김경민<br><span class="mono" style="color:var(--muted)">@kokoball-eval</span></td><td>답변을 정답과 대조해 채점한다(RAGAS, Judge 4항목). 대표 사례는 사람이 원문 확인</td><td>해당 없음/평가 불가 규칙의 함정</td></tr>
<tr><td><span class="chip platform">platform</span></td><td>김창동(리드)<br><span class="mono" style="color:var(--muted)">@C-Designer</span></td><td>뼈대, API, 공통 설정, LLM 호출 래퍼, Langfuse, README, 보안 비교, 시연. 그리고 모든 PR 리뷰·머지</td><td>platform이 밀리면 리뷰가 우선</td></tr>
</table></div>
<p class="appendix">부록: <a href="{u('flow')}">질문이 답이 되는 과정</a> 3·4절(주고받는 데이터와 짝) · <code>docs/adr/0002</code></p>
</section>

<section class="item" id="s3"><div class="eyebrow">안건 3 · 5분</div>
<h2 class="q">질문 하나는 어떻게 답이 되나?</h2>
<p class="say">입구(platform)가 질문을 받아 번호표를 붙이고, search가 조각을 찾고, answer가 그 조각만 보고 답을 쓰고, platform이 시간·토큰을 재서 Langfuse에 남긴다. 실험 러너도 같은 함수를 부른다.</p>
{figure(svgA1,"그림. 윗줄이 가는 길, 아래 두 줄이 돌아오는 값. 색은 책임자. 회색 띠는 모든 단계가 번호표 하나로 Langfuse에 남는다는 뜻.")}
<ul>
<li><b>왜 한 길인가.</b> API 응답과 실험 결과가 같은 코드를 지나야 비교가 공정하고, 측정 코드가 한 곳(<code>run_query</code>, <code>llm.call</code>)에만 있어도 된다.</li>
<li><b>LLM은 직접 부르지 않는다.</b> <code>platform.llm.call()</code>을 통해야 timeout·재시도·토큰·기록이 붙는다.</li>
<li><b>출처는 LLM이 만들지 않는다.</b> LLM은 <code>S1, S2</code> 같은 자료 번호만 쓰고, 코드가 문서명·페이지로 바꾼다. 없는 번호가 나오면 다시 만들게 한다.</li>
</ul>
<p class="appendix">부록: <a href="{u('flow')}">질문이 답이 되는 과정</a> · <code>docs/specs/platform.md</code></p>
</section>

<section class="item" id="s4"><div class="eyebrow">안건 4 · 5분</div>
<h2 class="q">세 방식은 어떻게 비교하나?</h2>
<p class="say">metrics가 고른 질문을 세 방식으로 돌려 결과를 한 줄씩 저장하고, judge가 정답과 대조해 점수를 매기고, metrics가 둘을 합쳐 표로 만든다. 정답 파일은 채점에만 쓴다.</p>
{figure(svgA2,"그림. 실험이 도는 순서. 붉은 점선이 절대 가면 안 되는 길: 정답을 검색이나 프롬프트에 넣는 것.")}
<div class="tbl"><table>
<tr><th>무엇을 재나</th><th>어떻게</th><th>담당</th></tr>
<tr><td>검색이 정답 문서를 찾았나</td><td>Hit@k(하나라도), Recall@k(몇 개나). 문서 단위, k는 세 방식 동일</td><td><span class="chip metrics">metrics</span></td></tr>
<tr><td>답이 찾은 자료에 근거했나</td><td>RAGAS Faithfulness. 입력은 실제 최종 문맥</td><td><span class="chip judge">judge</span></td></tr>
<tr><td>답이 맞나</td><td>LLM Judge 4항목: 사실·조건·근거·판단 각 0/1. 해당 없음·평가 불가는 null</td><td><span class="chip judge">judge</span></td></tr>
<tr><td>얼마나 걸리고 얼마나 쓰나</td><td>응답 시간, 오류율, 입·출력 토큰. 채점 호출은 따로 센다</td><td><span class="chip platform">platform</span> 측정 · <span class="chip metrics">metrics</span> 집계</td></tr>
<tr><td>공격 문장에 넘어가나</td><td>최종 구성 1개 × 보안 질문 2개 × 기본/방어 프롬프트 = 답변 4개</td><td><span class="chip platform">platform</span></td></tr>
</table></div>
<p class="appendix">부록: <code>docs/evaluation.md</code> · <code>docs/specs/metrics.md</code>, <code>judge.md</code></p>
</section>

<section class="item" id="s5"><div class="eyebrow">안건 5 · 3분</div>
<h2 class="q">레포에서 내 자리는 어디인가?</h2>
<p class="say">지금 레포는 문서가 전부다. 코드는 영역별 README 한 줄씩. 뼈대가 11/6 오전에 들어오면 각자 <code>src/&lt;내 영역&gt;/</code>에서 시작한다.</p>
<div class="two">
<div><h3>내가 손대는 곳</h3>
<div class="kv">
<b>코드</b><span><code>src/&lt;내 영역&gt;/</code> 안에서만</span>
<b>문서</b><span><code>docs/specs/&lt;내 영역&gt;.md</code>. "미정"을 값으로 채우는 것이 첫 작업</span>
<b>README</b><span>제출 전 내 영역 절(실행 방법·설정·한계·기여)</span>
<b>Issue</b><span>내 이름으로 열린 것. 새 작업은 내가 Issue를 만든다</span>
</div></div>
<div><h3>안 건드리는 곳</h3>
<div class="kv">
<b>남의 영역 폴더</b><span>읽기는 자유, 수정은 Issue나 PR 코멘트로 부탁</span>
<b><code>contracts.py</code> · <code>config.py</code></b><span>바꾸려면 PR 제목에 <code>[interface]</code> + 짝에게 먼저</span>
<b><code>data/</code> · <code>.env</code></b><span>절대 커밋하지 않는다. 키 이름만 <code>.env.example</code>에</span>
<b>ADR</b><span>고치지 않는다. 결정이 바뀌면 새 번호로</span>
</div></div>
</div>
<p class="appendix">부록: <a href="{u('repo')}">레포에 무엇이 어디 있나</a> (파일 트리, 문서 세 종류) · <code>AGENTS.md</code></p>
</section>

<section class="item" id="s6"><div class="eyebrow">안건 6 · 7분</div>
<h2 class="q">일은 어떻게 받아서 어떻게 넣나?</h2>
<p class="say">할 일 하나 = Issue 하나. 바꾼 것 한 묶음 = PR 하나. main에 넣는 것은 리드만. 보드는 그 상태를 보여주는 창이다. 할 일은 Issue에 라벨(영역)·마일스톤(기한 묶음)·담당자가 붙어 있고, GitHub 마일스톤은 M1(11/6)·M3(11/10)·M6(11/13) 셋뿐이다. GitHub가 처음이면 아래 부록의 안내를 미팅 뒤에 꼭 읽는다.</p>
{figure(svgC_lite,"그림. 카드 하나가 Todo에서 Done까지 가는 길. 칸 이동 중 Review로 옮기는 것만 내가 직접 한다.")}
<div class="steps2">
<div class="step"><div><b>Issue를 고른다</b><p>보드 상단 탭 "담당별"에서 내 이름 아래 카드. 본문에 할 일·완료 조건·기준 문서가 있다. 지금 내 Issue는 전부 M3(11/10까지) 아니면 M6(11/13까지).</p></div></div>
<div class="step"><div><b>최신 main에서 브랜치를 판다</b><p><code>git switch main && git pull</code> → <code>git switch -c feat/chunking</code></p></div></div>
<div class="step"><div><b>작업하고 커밋·push한다</b><p><code>git add &lt;파일&gt;</code> → <code>git commit -m "feat: 청킹 v1"</code> → <code>git push -u origin feat/chunking</code>. 에이전트로 해도 되지만 내가 설명할 수 있는 코드만.</p></div></div>
<div class="step"><div><b>반나절 단위로 PR을 올린다</b><p>제목 <code>feat: 청킹 v1</code>, 본문은 템플릿: 무엇을 왜 / 실행 명령과 결과 캡처 / 체크 4개 / 맨 아래 <code>Closes #13</code>(이게 있어야 Issue와 연결된다). 올린 뒤 보드 탭 "보드"에서 카드를 Review 칸으로 드래그한다(또는 카드 클릭 → Status를 Review로).</p></div></div>
<div class="step"><div><b>리드가 보고 머지한다</b><p>보는 것 4가지: 돌아가나(증거), spec과 맞나, 키·데이터 없나, 내가 설명할 수 있나. 스타일은 안 본다. 수정 요청이 오면 같은 브랜치에 push.</p></div></div>
<div class="step"><div><b>머지 뒤 정리</b><p>원격 브랜치는 자동 삭제. 로컬은 <code>git switch main && git pull && git branch -D feat/chunking</code></p></div></div>
</div>
<p class="appendix">부록: <a href="{u('guide')}">GitHub가 처음이라면</a> (처음 한 번 설정, 용어, 어디서 보나, 명령 복붙, PR 본문 예시, 캡처 붙이기, 자주 하는 실수) · <a href="{u('github')}">일을 받아서 main에 넣는 순서</a> (규칙 전체, Issue 40개 표)</p>
</section>

<section class="item" id="s7"><div class="eyebrow">안건 7 · 4분</div>
<h2 class="q">8일을 어떻게 쓰나?</h2>
<p class="say">11/6 뼈대, 11/9까지 각자 영역 완성, 11/10 아침 설정을 잠그고 전체 실행, 11/11 비교표, 11/12에 발표본까지 전부 끝, 11/13은 리허설하고 13:00 제출. 11/10부터는 영역과 상관없이 전원이 실행과 원문 대조에 참여한다.</p>
{figure(svgD,"그림. 진한 막대가 그 영역이 가장 바쁜 날. 붉은 선 세 개가 잠금(11/10)·발표본 포함 최종 완료(11/12)·제출(11/13 13:00). 금요일은 리허설만.")}
<div class="grid4">
<div class="tile"><b>11/6 (금) M1</b><span>뼈대 머지. 전원 로컬에서 naive 1문항 실행. 각자 첫 PR. 오전까지 안 들어오면 contracts.py만 보고 mock으로 시작</span></div>
<div class="tile"><b>11/9 (월) M2</b><span>세 방식·프롬프트·채점 파이프라인 완성. 잠글 설정 합의</span></div>
<div class="tile"><b>11/10 (화) M3</b><span>아침 config 잠금 → 전체 실행 → 자동 채점 → 보안 4개</span></div>
<div class="tile"><b>11/11 (수) M4</b><span>비교표 완성. 대표 사례 원문 대조(자기 영역 아닌 것). 최종 구성 선택. 영역별 슬라이드</span></div>
<div class="tile"><b>11/12 (목) M5 · 최종 완료</b><span>기능 추가 금지, 버그만. 구현 안 한 사람이 README대로 설치 성공. 슬라이드 통합해 발표본(PPTX+PDF)까지 끝. 시연 녹화</span></div>
<div class="tile"><b>11/13 (금) M6 · 리허설·제출</b><span>오전 리허설. 팀 Notion에 저장소·발표자료 연결. 13:00 제출. 오후 발표. 새 작업 없음</span></div>
</div>
<p class="appendix">부록: <a href="{u('schedule')}">8일 동안 누가 언제 무엇을</a> (날짜별 완료 상태, 밀리면 빼는 순서, 리스크) · <code>docs/work-plan.md</code></p>
</section>

<section class="item" id="s8"><div class="eyebrow">안건 8 · 10분</div>
<h2 class="q">오늘 정할 것과 오늘 할 것</h2>
<p class="say">정하면 담당자가 자기 spec의 "미정"을 지우고 값을 적는다. 그 PR이 각자의 첫 PR이어도 좋다.</p>
<div class="two">
<div><h3>미팅에서 정한다</h3>
<ul class="check">
<li><b>k 기본값</b>&nbsp;— 답 만들 때 쓰는 조각 수. 세 방식 공통 (search·answer·metrics 모두 영향)</li>
<li><b>평가 LLM</b>&nbsp;— 생성 모델과 같아도 됨. 비용이 질문 수를 정한다 (judge)</li>
<li><b>Langfuse Cloud vs 셀프호스트</b>&nbsp;— 팀 프로젝트 하나, 키는 각자 .env (platform)</li>
<li><b>Python 버전 · 패키지 도구 · Qdrant 실행 방식(docker/embedded)</b>&nbsp;— 전원이 같은 환경. 11/12 재설치 검증 대상. 10분 안에 못 정하면 리드가 오늘 저녁 Slack에 설치 명령 공지 (platform)</li>
<li><b>데이터 다운로드·PDF 15개 검수 당번</b>&nbsp;— 노션 수와 실제 파일 수 대조, 누락·실패 기록</li>
<li><b>발표 목차 7장 합의 · 발표 시간 공지 확인</b>&nbsp;— ①문제·데이터 ②아키텍처 ③비교 결과 ④품질·보안 ⑤운영·선택 ⑥한계 ⑦기여. 시간 미공지면 누가 확인하나</li>
</ul></div>
<div><h3>미팅 끝나고 오늘 각자</h3>
<ul class="check">
<li>GitHub 알림 켜기, Project 보드 열어 내 카드 확인 (<a href="https://github.com/users/C-Designer/projects/1">보드</a>). GitHub가 처음이면 <a href="{u('guide')}">안내</a>부터</li>
<li>레포 clone (<code>git clone https://github.com/C-Designer/kant_project_3.git</code>), Python·Qdrant 로컬 준비, <code>.env.example</code>을 복사해 <code>.env</code></li>
<li>내 영역 spec과 <code>docs/requirements.md</code> 읽기 (순서는 <code>AGENTS.md</code>)</li>
<li>노션 발제 페이지(링크는 <code>docs/requirements.md</code> 첫 줄)에서 ZIP을 받아 빈 폴더 <code>data/shipping/</code>에 풀기 → 안에 <code>documents/</code>(PDF 15개)와 <code>evaluation/</code>이 있어야 함. 커밋 금지</li>
<li>Langfuse: 운영 방식이 정해지면 리드가 팀 프로젝트를 만들고 초대 → 각자 키를 <code>.env</code>에</li>
<li>리드: 오늘 저녁 뼈대 시작, 11/6 오전 머지</li>
</ul></div>
</div>
</section>
{FOOT}
</div>"""
pages_dyn = {}

# =====================================================================
# PAGE G: GitHub가 처음이라면
# =====================================================================
def guide(urls):
    u = lambda k: urls.get(k,"#")
    return head("GitHub가 처음이라면") + f"""
<div class="wrap">
<header class="top"><div class="eyebrow">proj_3rd · kant_project_3 · GitHub 안내</div>
<h1>GitHub가 처음이라면</h1>
<p class="lede">이 팀에서 GitHub를 쓰는 방법만 적었다. 무엇이 무엇에 붙어 있나 → 용어 → 어디서 보나 → 처음 한 번 설정 → 내 하루 → PR 본문 예시 → 수정 요청·충돌 → 자주 하는 실수 → 새 Issue 만들기. 10분이면 읽는다.</p>
<nav class="back">← <a href="{u('meeting')}">킥오프 자료</a> · <a href="{u('index')}">지도</a></nav></header>

<h2>1. 한 장으로: 무엇이 무엇에 붙어 있나</h2>
<p>GitHub에는 "할 일"을 적는 Issue와 "바꾼 코드"를 올리는 PR이 있고, 둘은 <code>Closes #번호</code>로 이어진다. Project 보드는 Issue를 카드로 보여주는 별도 화면이라 Issue를 만들면 알아서 나타난다.</p>
{figure(svgGH,"그림. 왼쪽이 저장소 안의 것들, 오른쪽이 보드. Issue 하나에 라벨·마일스톤·담당자가 붙고, PR이 머지되면 Issue가 닫히면서 카드가 Done으로 간다.")}

<h2>2. 용어 9개</h2>
<div class="tbl"><table>
<tr><th>말</th><th>뜻</th><th>이 팀에서는</th></tr>
<tr><td><b>Issue</b></td><td>할 일 하나를 적은 글. 번호(#13)가 붙는다</td><td>반나절~하루 크기. 본문에 할 일·완료 조건·기준 문서. 지금 40개(#8~#47)가 열려 있다</td></tr>
<tr><td><b>라벨</b></td><td>Issue에 붙이는 색 태그</td><td>영역 이름 하나(<span class="chip search">search</span> <span class="chip answer">answer</span> <span class="chip metrics">metrics</span> <span class="chip judge">judge</span> <span class="chip platform">platform</span> <span class="chip skeleton">skeleton</span> <span class="chip docs">docs</span>). <span class="chip iface">interface</span>는 공용 파일을 바꿀 때 추가</td></tr>
<tr><td><b>마일스톤</b></td><td>기한이 있는 Issue 묶음. 진행률이 보인다</td><td>3개뿐: M1 뼈대(11/6) · M3 동결·전체 실행(11/10) · M6 제출(11/13). 11/9까지 끝낼 것은 전부 M3. 일정표의 M0·M2·M4·M5는 GitHub에 없다. GitHub에 등록된 기한 날짜는 전날(11/5·11/9·11/12)로 돼 있으니 제목의 날짜를 기준으로 본다</td></tr>
<tr><td><b>담당자</b>(Assignee)</td><td>그 Issue를 하는 사람</td><td>항상 1명. "담당별" 보드 뷰가 이걸로 묶는다</td></tr>
<tr><td><b>Project 보드</b></td><td>Issue를 칸(Status)별로 보여주는 칸반 화면</td><td>Todo → In Progress → Review → Done. Review로 옮기는 것만 내가 직접</td></tr>
<tr><td><b>브랜치</b></td><td>main을 복사해 따로 작업하는 줄기</td><td>이름 <code>&lt;type&gt;/&lt;짧은-설명&gt;</code>, 예 <code>feat/chunking</code>. main에는 직접 못 올린다(GitHub가 막음)</td></tr>
<tr><td><b>PR</b>(Pull Request)</td><td>"내 브랜치를 main에 넣어 주세요"라는 요청. 바뀐 내용과 설명이 같이 보인다</td><td>제목 <code>&lt;type&gt;: 설명</code>, 본문은 템플릿, <code>Closes #13</code>. 실행 증거 필수</td></tr>
<tr><td><b>리뷰 · 승인</b></td><td>다른 사람이 PR을 보고 Approve 또는 수정 요청</td><td>리드만 한다. 새로 push하면 승인이 사라져서 다시 봐야 한다</td></tr>
<tr><td><b>머지</b>(Squash and merge)</td><td>PR을 main에 합치기. Squash는 커밋 여러 개를 하나로</td><td>리드만 누른다. 머지되면 원격 브랜치 자동 삭제, Issue 자동 닫힘</td></tr>
</table></div>

<h2>3. 어디서 보나</h2>
<p>보드는 저장소의 Projects 탭이 아니라 리드 계정의 프로젝트라 링크로 간다. 상단 탭이 두 개: <b>보드</b>(Todo/In Progress/Review/Done 칸)와 <b>담당별</b>(사람별 묶음). 카드를 칸 사이로 옮길 때는 "보드" 탭이어야 한다.</p>
<div class="tbl"><table>
<tr><th>보고 싶은 것</th><th>여는 곳</th><th>필터 칸에 넣을 것</th></tr>
<tr><td>내 할 일</td><td><a href="https://github.com/users/C-Designer/projects/1">Project 보드</a> → 상단 탭 "담당별"</td><td>—</td></tr>
<tr><td>내 Issue만 목록으로</td><td><a href="https://github.com/C-Designer/kant_project_3/issues">Issues</a></td><td><code>is:open assignee:@me</code></td></tr>
<tr><td>내 영역 전체</td><td>Issues</td><td><code>is:open label:search</code> (영역 이름으로)</td></tr>
<tr><td>이번 마일스톤에 남은 것</td><td><a href="https://github.com/C-Designer/kant_project_3/milestones">Milestones</a> (Issues 탭 안의 "Milestones" 버튼) → M3 클릭</td><td>—</td></tr>
<tr><td>리뷰 기다리는 PR</td><td><a href="https://github.com/C-Designer/kant_project_3/pulls">Pull requests</a></td><td><code>is:open review:required</code></td></tr>
<tr><td>공용 파일 바꾸는 PR</td><td>Pull requests</td><td><code>label:interface</code></td></tr>
</table></div>

<h2>4. 처음 한 번만</h2>
<p>레포를 받고, 커밋에 이름을 붙이고, (쓰려면) GitHub 명령줄 도구 <code>gh</code>에 로그인한다. PR은 웹에서 만들어도 되므로 <code>gh</code>는 선택이다.</p>
<pre class="cmd">git clone https://github.com/C-Designer/kant_project_3.git
cd kant_project_3
git config user.name "내 이름"
git config user.email "GitHub 계정 이메일"
brew install gh && gh auth login      <i># 선택. 브라우저가 열리면 GitHub 로그인</i>
cp .env.example .env                  <i># 키는 여기만. 커밋되지 않는다</i></pre>

<h2>5. 내 하루 (Issue 하나 기준)</h2>
<div class="steps2">
<div class="step"><div><b>아침에 보드를 본다</b><p>"담당별" 탭에서 내 카드 중 Todo 하나를 고른다. 카드를 열면 Issue 본문이 보인다. 할 일·완료 조건·기준 문서를 읽는다. 카드는 Todo에 그대로 둬도 된다(PR을 올리고 본문에 <code>Closes #번호</code>가 있으면 In Progress로 옮겨진다. 안 움직이면 "보드" 탭에서 직접 끌어다 놓는다).</p></div></div>
<div class="step"><div><b>최신 main에서 브랜치를 만든다</b><p>main이 어제보다 바뀌었을 수 있으니 항상 pull부터.</p><pre class="cmd">git switch main
git pull
git switch -c feat/chunking      <i># type/짧은-설명. 영문 소문자, 하이픈</i></pre></div></div>
<div class="step"><div><b>작업하고 커밋한다</b><p>에이전트(Claude Code, Codex)로 해도 된다. 단, 내가 설명할 수 있는 코드만. 커밋 메시지는 PR 제목과 같은 형식.</p><pre class="cmd">git add src/search/chunking.py docs/specs/search.md
git commit -m "feat: 청킹 v1, 표·단위·적용일 보존"
git push -u origin feat/chunking</pre></div></div>
<div class="step"><div><b>PR을 올린다 (웹이 쉽다)</b><p>push 직후 저장소 첫 화면에 노란 띠 "Compare &amp; pull request"가 뜬다. 안 보이면 Pull requests 탭 → New pull request → compare를 내 브랜치로. 본문 칸에 템플릿이 자동으로 들어오니 채우고, 맨 아래 <code>Closes #13</code>. <b>캡처는 본문 입력창에 이미지를 드래그하거나 붙여넣으면 링크가 자동으로 생긴다.</b></p><p>명령줄로 하려면 (본문은 6절 예시를 레포 밖 파일, 예: <code>~/pr.md</code>에 써 둔다. 이미지는 PR 페이지에서 본문 오른쪽 ··· → Edit로 붙인다):</p><pre class="cmd">gh pr create --title "feat: 청킹 v1, 표·단위·적용일 보존" --body-file ~/pr.md</pre><p><code>gh pr create --fill</code>은 쓰지 않는다(템플릿이 사라진다).</p></div></div>
<div class="step"><div><b>카드를 Review로 옮긴다</b><p>보드 상단 탭을 "보드"로 바꾸고 내 카드를 Review 칸으로 드래그한다(또는 카드 클릭 → 오른쪽 패널 Status → Review). 이것만 자동이 아니다. 이 칸에 있으면 "리드가 봐 주세요"라는 뜻.</p></div></div>
<div class="step"><div><b>리드가 보고 머지한다</b><p>리드가 보는 4가지: ① 돌아가나(본문의 명령·캡처) ② spec·contracts와 맞나, spec도 고쳤나 ③ 키·개인정보·data/ 없나 ④ 내가 설명할 수 있나. 스타일·네이밍은 메모만 남기고 막지 않는다.</p></div></div>
<div class="step"><div><b>머지되면 정리한다</b><p>원격 브랜치와 Issue는 알아서 정리된다. 로컬만 지운다. Squash 머지라 <code>-d</code>가 아니라 <code>-D</code>.</p><pre class="cmd">git switch main
git pull
git branch -D feat/chunking</pre></div></div>
</div>

<h2>6. PR 본문 예시 (Issue #13 청킹)</h2>
<p>파일 이름과 쪽수는 예시다. 실제 PDF 이름으로 바꾼다.</p>
<pre class="cmd">## 변경 내용
표의 행·열 제목과 단위, 적용일이 한 청크에 남도록 청킹 규칙을 정했다 (크기 N, overlap M).
spec의 "청킹: 크기·overlap 미정"을 값으로 바꿨다.

## 확인 방법
python -m src.search.index --dataset data/shipping
→ data/shipping/ingest-report.json: 문서 15, 페이지 360, 청크 NNN, 실패 0
&lt;파일A&gt;.pdf 요율표 쪽 청크 캡처: (입력창에 이미지 붙여넣기)
&lt;파일B&gt;.pdf 정정 공지 쪽 청크 캡처: (입력창에 이미지 붙여넣기)

## 체크
- [x] 동작·구조가 바뀌었으면 관련 docs/specs/ 를 이 PR에서 갱신했다
- [ ] contracts.py나 config.py를 바꿨으면 제목에 [interface], 의존 영역 담당자 확인
- [x] 키·개인정보·data/가 들어가지 않았다
- [x] 에이전트가 쓴 부분을 내가 설명할 수 있다

Closes #13</pre>
<p style="font-size:13.5px">해당 없는 체크 칸(위의 [interface])은 비워 둔다. 프롬프트 파일을 바꾼 PR이면 "확인 방법"에 정상·되묻기·보류 질문 1개씩의 실행 결과를 붙인다.</p>

<h2>7. 리뷰에서 수정 요청이 오면</h2>
<p>같은 브랜치에서 고치고 push하면 PR에 자동으로 올라간다. 새 PR을 만들지 않는다. push하면 이전 승인이 사라지므로, PR 페이지 오른쪽 Reviewers의 C-Designer 옆 ↻(Re-request review)를 누르고 Slack <code>proj_3rd</code>에 한 줄 남긴다. 카드가 Review 칸 밖으로 나가 있으면 다시 Review로.</p>
<pre class="cmd">git add &lt;고친 파일&gt;
git commit -m "fix: 리뷰 반영, 각주가 끊기던 청크 수정"
git push</pre>

<h2>8. main이 먼저 바뀌어서 충돌이 나면</h2>
<p>PR 화면에 "This branch has conflicts"가 뜨면 올린 사람이 자기 브랜치에서 푼다. 남의 브랜치에는 push하지 않는다.</p>
<pre class="cmd">git switch feat/chunking       <i># 내 브랜치에서</i>
git fetch origin
git merge origin/main          <i># 충돌 난 파일을 열어 &lt;&lt;&lt;&lt; ==== &gt;&gt;&gt;&gt; 를 정리. VS Code면 Accept Current/Incoming 버튼</i>
git add &lt;정리한 파일&gt;
git commit --no-edit           <i># 편집기 안 열고 기본 메시지로 커밋</i>
git push</pre>

<h2>9. 자주 하는 실수</h2>
<div class="tbl"><table>
<tr><th>실수</th><th>무슨 일이 생기나</th><th>대신</th></tr>
<tr><td>main에서 바로 커밋·push</td><td>push가 거부된다(룰셋)</td><td>브랜치를 만들고 거기서. 이미 main에 커밋했다면 <code>git switch -c feat/x</code>로 옮긴 뒤 <code>git switch main && git reset --hard origin/main</code>으로 로컬 main을 원래대로</td></tr>
<tr><td><code>data/</code>나 <code>.env</code>를 add</td><td>PDF·키가 저장소에 남는다. 리드가 PR을 막는다</td><td><code>.gitignore</code>가 막아 주지만 <code>git add .</code> 대신 파일을 지정해서 add</td></tr>
<tr><td>PR 하나에 이틀치</td><td>리뷰가 느려지고 충돌이 커진다</td><td>반나절 단위로 쪼개서 올린다</td></tr>
<tr><td>실행 증거 없이 PR</td><td>리드가 돌려보낸다(CI가 없어서 증거가 CI 역할)</td><td>명령과 결과 캡처를 본문에</td></tr>
<tr><td>spec은 안 고치고 코드만</td><td>체크 항목 미충족으로 돌려보낸다</td><td>같은 PR에서 spec의 해당 줄을 고친다</td></tr>
<tr><td><code>contracts.py</code>를 조용히 바꿈</td><td>짝의 코드가 깨진다</td><td>제목에 <code>[interface]</code>, 라벨 interface, 짝에게 먼저 말하기</td></tr>
<tr><td>승인 떴다고 내가 머지 버튼</td><td>팀 규칙 위반(GitHub는 못 막음)</td><td>머지는 리드만</td></tr>
<tr><td><code>gh pr create --fill</code></td><td>본문이 커밋 메시지로 채워져 템플릿이 사라진다</td><td><code>--body-file ~/pr.md</code> 또는 웹에서 템플릿 채우기</td></tr>
<tr><td>PR 본문에 <code>Closes #N</code>을 안 씀</td><td>머지돼도 Issue가 안 닫히고 카드가 안 움직인다</td><td>본문 맨 아래 한 줄</td></tr>
<tr><td>머지 뒤 <code>git branch -d</code></td><td>"not fully merged" 오류(Squash라 그렇다)</td><td><code>-D</code></td></tr>
</table></div>

<h2>10. 에이전트(Claude Code · Codex)로 작업할 때</h2>
<ul>
<li>레포의 <code>CLAUDE.md</code>·<code>AGENTS.md</code>가 규칙을 알려주므로 에이전트도 같은 순서로 문서를 읽는다. 다른 영역 폴더는 고치지 말라고 돼 있다.</li>
<li>에이전트가 PR을 만들 때는 템플릿을 채운 본문을 <code>--title</code>, <code>--body</code>로 넘기게 한다.</li>
<li>머지 전에 내가 그 코드를 발표에서 설명할 수 있어야 한다. 설명 못 하면 머지하지 않는다(체크 ④).</li>
</ul>

<h2>11. 지금 내 이름으로 열린 Issue</h2>
<div class="tbl"><table>
<tr><th>라벨</th><th>마일스톤</th><th>담당</th><th>Issue</th><th style="text-align:right">수</th></tr>
{rows}
<tr><td colspan="4"><b>합계</b> (전부 Open, 2026-11-05)</td><td class="num"><b>40</b></td></tr>
</table></div>
<p style="font-size:13.5px">Issue보다 작은 수정(버그 하나)은 Issue 없이 PR만 올려도 된다. 리드가 매일 보드를 보고 In Progress에 이틀 넘게 있는 카드를 묻는다.</p>
<h3>새 Issue를 만들 때</h3>
<div class="steps2">
<div class="step"><div><b>Issues 탭 → New issue</b><p>제목은 기존 것처럼 <code>[search] 청킹 overlap 재조정</code> 식으로 영역을 앞에.</p></div></div>
<div class="step"><div><b>본문 세 칸</b><p><code>## 할 일</code> / <code>## 완료 조건</code>(체크박스) / <code>## 기준 문서</code>(내 spec 경로).</p></div></div>
<div class="step"><div><b>오른쪽 사이드바</b><p>Assignees = 나, Labels = 내 영역 하나, Milestone = M3 또는 M6. 그러면 보드 Todo에 자동으로 들어간다.</p></div></div>
</div>
{FOOT}
</div>"""

# =====================================================================
# INDEX
# =====================================================================
def make_index(urls):
    return head("proj_3rd 킥오프 지도") + f"""
<div class="wrap">
<header class="top"><div class="eyebrow">KANT 3차 프로젝트 · kant_project_3 · 2026-11-05 킥오프</div>
<h1>proj_3rd 킥오프 지도</h1>
<p class="lede">해운 분야 PDF 15개(360쪽)로 RAG 질의응답 서비스를 만들고, naive / hybrid / hybrid_rerank 세 검색 방식을 같은 조건으로 비교한다. 제출 <b>11/13(금) 13:00</b>, 당일 오후 발표. 오늘부터 8일.</p></header>

<h2>킥오프에서 같이 보는 것</h2>
<div class="cards">
<a class="card" href="{urls['meeting']}"><b>proj_3rd 킥오프</b><span>안건 8개를 위에서 아래로. 안건마다 질문 하나, 그림 하나, 말할 것 세 줄. 40분 분량</span></a>
<a class="card" href="{urls['guide']}"><b>GitHub가 처음이라면</b><span>Issue·라벨·마일스톤·보드·브랜치·PR이 어떻게 이어지는지, 내 하루, 명령 복붙, PR 본문 예시, 자주 하는 실수</span></a>
</div>

<h2>부록: 더 깊이 볼 네 장</h2>
<p>킥오프 자료의 각 안건 끝에서 링크로 이어진다. 나중에 자기 영역을 팔 때 다시 본다. 처음 보는 말은 맨 아래 풀이.</p>
<div class="cards">
<a class="card" href="{urls['flow']}"><b>1 · 질문이 답이 되는 과정</b><span>질문이 들어와 다섯 영역을 거쳐 답이 나가는 순서, 세 방식을 비교하는 실험이 돌아가는 순서, 영역끼리 주고받는 데이터와 짝</span></a>
<a class="card" href="{urls['repo']}"><b>2 · 레포에 무엇이 어디 있나</b><span>파일 트리, 문서 세 종류가 각각 정하는 것, 작업 전에 읽는 순서, 내 폴더에서 지킬 것</span></a>
<a class="card" href="{urls['github']}"><b>3 · 일을 받아서 main에 넣는 순서</b><span>보드 네 칸과 자동 이동, GitHub이 막는 것과 팀 약속, 내 이름의 Issue 목록, PR에 채울 칸</span></a>
<a class="card" href="{urls['schedule']}"><b>4 · 8일 동안 누가 언제 무엇을</b><span>영역별로 가장 바쁜 날, 날짜별 완료 상태, 11/10 설정 잠금, 전원이 함께 하는 일, 밀리면 빼는 순서</span></a>
</div>

<h2>팀과 영역</h2>
<p>영역은 레이어가 아니라 "무엇의 품질을 책임지나"로 나눴다. 영역 하나 = 담당 1명 = spec 1개 = <code>src/&lt;영역&gt;/</code>. 5명 전원이 에이전트로 개발하므로 코드 양이 아니라 판단과 통합이 병목이다.</p>
<div class="tbl"><table>
<tr><th>영역</th><th>담당 · GitHub</th><th>한 줄 책임</th><th>짝</th><th>피크</th></tr>
<tr><td><span class="chip search">search</span></td><td>윤승환 <span class="mono" style="color:var(--muted)">@yshzjq</span></td><td>검색 품질: 청킹·E5·Qdrant·3방식</td><td>answer</td><td>11/6~8</td></tr>
<tr><td><span class="chip answer">answer</span></td><td>천희재 <span class="mono" style="color:var(--muted)">@rjqnrll7-cmyk</span></td><td>답변 품질: 문맥·프롬프트·JSON 검증·출처</td><td>search</td><td>11/7~9</td></tr>
<tr><td><span class="chip metrics">metrics</span></td><td>오주헌 <span class="mono" style="color:var(--muted)">@ohjuhun1119</span></td><td>실험 자동화: 로더·러너·Hit/Recall·운영 지표·비교표</td><td>judge, platform</td><td>11/8~10</td></tr>
<tr><td><span class="chip judge">judge</span></td><td>김경민 <span class="mono" style="color:var(--muted)">@kokoball-eval</span></td><td>LLM 평가: RAGAS·Judge 4항목·null 규칙·원문 대조</td><td>metrics</td><td>11/10~11</td></tr>
<tr><td><span class="chip platform">platform</span></td><td>김창동(리드) <span class="mono" style="color:var(--muted)">@C-Designer</span></td><td>재현·관측·운영: 뼈대·FastAPI·config·llm.call·Langfuse·README·보안·시연 + 모든 PR 리뷰·머지</td><td>metrics</td><td>11/6~9, 11/12</td></tr>
</table></div>

<h2>오늘 상태</h2>
<ul>
<li><code>main</code>은 커밋 9개, 전부 문서. 코드는 영역별 README 1줄씩. 뼈대(<code>contracts.py</code>, <code>config.py</code>, naive E2E)는 리드가 11/6 오전까지 머지.</li>
<li>Issue 40개(#8~#47) 전부 Open. 마일스톤 M1 4 · M3 28 · M6 8. PR 8개 머지됨(모두 리드의 docs PR).</li>
<li>오늘 정할 것: <code>k</code> 기본값, 평가 LLM, Langfuse Cloud/셀프호스트, Python 버전·패키지 도구, 데이터 검수 당번, 발표 목차 7장 합의.</li>
</ul>

<h2>어디서 찾나</h2>
<div class="tbl"><table>
<tr><th>궁금한 것</th><th>보는 곳</th></tr>
<tr><td>무엇을 만들어야 하나, 발제 규칙</td><td><code>docs/requirements.md</code></td></tr>
<tr><td>어떻게 채점되나</td><td><code>docs/evaluation.md</code></td></tr>
<tr><td>내 영역이 지금 어떻게 동작해야 하나</td><td><code>docs/specs/&lt;영역&gt;.md</code> + <code>src/contracts.py</code></td></tr>
<tr><td>왜 이렇게 나눴나, 왜 이 스택인가</td><td><code>docs/adr/0002</code>, <code>0003</code></td></tr>
<tr><td>브랜치·PR·커밋 형식</td><td><code>docs/branch-strategy.md</code></td></tr>
<tr><td>일정·역할·리뷰·Issue 운영</td><td><code>docs/work-plan.md</code></td></tr>
<tr><td>진행 상황</td><td><a href="https://github.com/users/C-Designer/projects/1">Project 보드</a> · <a href="https://github.com/C-Designer/kant_project_3/issues">Issues</a></td></tr>
</table></div>

<h2>처음 보는 말 풀이</h2>
<div class="tbl"><table>
<tr><th>말</th><th>뜻</th></tr>
<tr><td>영역</td><td>한 사람이 책임지는 품질의 묶음. search(검색) · answer(답변) · metrics(실험 자동화) · judge(채점) · platform(뼈대·기록·운영). 폴더 <code>src/&lt;영역&gt;/</code>과 1:1</td></tr>
<tr><td>뼈대</td><td>리드가 11/6 오전까지 머지하는 최소 동작 코드. 질문 1개가 naive 검색으로 답까지 나오고 Langfuse에 기록되는 상태. 다들 이 위에서 자기 영역을 판다</td></tr>
<tr><td>spec</td><td><code>docs/specs/&lt;영역&gt;.md</code>. 내 영역이 지금 어떻게 동작하는지 적은 문서. "미정"을 값으로 채우는 것이 첫 작업</td></tr>
<tr><td>ADR</td><td><code>docs/adr/</code>. 되돌리기 어려운 결정을 왜 했는지 적은 문서. 한 번 쓰면 안 고치고, 바뀌면 새 번호로 쓴다</td></tr>
<tr><td>contracts.py</td><td>영역끼리 주고받는 데이터의 모양을 코드로 정한 파일. 여기를 바꾸면 PR 제목에 <code>[interface]</code>를 붙이고 짝에게 먼저 알린다</td></tr>
<tr><td>config.py · 동결</td><td>k, 토큰 한도, 모델, timeout 같은 공통 설정을 한 파일에. 11/10 아침에 잠그고(동결), 그 뒤로는 바꾸지 않는다. 바꾸면 실험 전부 재실행</td></tr>
<tr><td>짝</td><td>데이터를 직접 주고받는 두 영역. search↔answer, metrics↔judge, platform↔metrics. 바꾸기 전에 서로 알려준다</td></tr>
<tr><td>run_query()</td><td>질문 하나를 검색 → 답변 → 기록까지 처리하는 함수. API도 실험 러너도 이것을 부른다</td></tr>
<tr><td>RunRecord · EvalRecord</td><td>질문 하나 × 검색 방식 하나의 실행 결과 한 줄, 그리고 그에 대한 채점 결과 한 줄. metrics가 앞을 만들고 judge가 뒤를 만든다</td></tr>
<tr><td>Langfuse · request_id</td><td>질문마다 번호표(request_id)를 붙여 검색 결과·모델 입출력·시간·토큰을 한 화면에서 따라갈 수 있게 남기는 도구. 발제 필수</td></tr>
<tr><td>Hit@k · Recall@k</td><td>검색이 정답 문서를 하나라도 찾았나(Hit), 몇 개나 찾았나(Recall). k = 답 만들 때 쓴 상위 조각 수</td></tr>
<tr><td>RAGAS Faithfulness · Judge 4항목</td><td>답이 찾아온 자료에 근거했나(Faithfulness), 그리고 사실·조건·근거·판단이 각각 맞나(Judge, 0/1). 둘을 합산하지 않는다</td></tr>
<tr><td>null (해당 없음 / 평가 불가)</td><td>점수를 매길 대상이 없거나 채점이 실패한 경우. 0으로 바꾸지 않고 평균에서 뺀다</td></tr>
<tr><td>룰셋 · CODEOWNERS</td><td>GitHub 설정. main에 직접 push를 막고, 리드 승인이 없으면 머지 버튼이 안 열린다</td></tr>
<tr><td>Squash and merge</td><td>PR의 커밋 여러 개를 하나로 합쳐 main에 넣는 방식. 리드만 한다. 머지 뒤 로컬 브랜치는 <code>git branch -D</code>로 지운다</td></tr>
<tr><td>M0 ~ M6</td><td>날짜별 마일스톤. M1 뼈대(11/6) · M3 동결·전체 실행(11/10) · M6 제출(11/13)이 GitHub 마일스톤으로 등록돼 있다. 발표본까지 전부 M5(11/12)에 끝내고 금요일은 리허설과 제출만</td></tr>
</table></div>
{FOOT}
</div>"""

STANDALONE_HEAD = '<!doctype html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n<style>html,body{margin:0}body{font-size:14px}</style>\n'

def standalone(page):
    """아티팩트 모드 페이지(머리말 없이 title·style·본문)를 브라우저에서 바로 열리는 완전한 HTML로 감싼다."""
    head_part, body = page.split('<div class="wrap">', 1)
    return STANDALONE_HEAD + head_part + '</head>\n<body>\n<div class="wrap">' + body + '\n</body>\n</html>\n'

if __name__ == "__main__":
    # 사용법:
    #   python3 gen.py                      → 이 폴더에 독립 HTML 7장 (서로 상대 링크). 레포용.
    #   python3 gen.py --artifact '{json}'  → claude.ai 아티팩트용 (머리말 없음, 링크는 json의 URL)
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", help="아티팩트 URL json")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    names = ["index","meeting","guide","flow","repo","github","schedule"]
    if a.artifact:
        urls = json.loads(a.artifact); wrap = lambda x: x
    else:
        urls = {n: f"{n}.html" for n in names}; wrap = standalone
    idx = urls.get("index","#")
    for k,v in pages.items():
        (out/f"{k}.html").write_text(wrap(v.replace("__INDEX__",idx)),encoding="utf-8")
    (out/"index.html").write_text(wrap(make_index(urls)),encoding="utf-8")
    (out/"meeting.html").write_text(wrap(meeting(urls)),encoding="utf-8")
    (out/"guide.html").write_text(wrap(guide(urls)),encoding="utf-8")
    print("ok", "artifact" if a.artifact else "standalone", names)
