"""Build the v0.3 Korean technical report from executed, versioned artifacts.

No simulation is performed by this report generator. It loads the recorded JSON
and PNG results, including the latest integrated test summary. Set
TEXTILE_REPORT_FONT_DIR to a directory containing NotoSansKR-400.ttf and
NotoSansKR-700.ttf, or put them in ../.report_fonts relative to the repository.
"""
from __future__ import annotations
import io
import json
import os
import re
import math
from pathlib import Path
from xml.sax.saxutils import escape
import numpy as np
from PIL import Image as PILImage
import matplotlib
matplotlib.use("Agg")
from matplotlib.mathtext import math_to_image
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, Image
from reportlab.graphics.shapes import Drawing, Rect, Line, Polygon, String
ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/"report"/"fabric_engine_v3_report_ko.pdf"
FONT=Path(os.environ.get("TEXTILE_REPORT_FONT_DIR",ROOT.parent/".report_fonts"))
VERSION="0.3.0"
DATE="2026-10-11"
REPO="https://github.com/Phill-lms/textile-optics-engine"
INK=colors.HexColor("#182b3a")
TEAL=colors.HexColor("#087f8c")
BLUE=colors.HexColor("#31588a")
LIGHT=colors.HexColor("#edf4f7")
PALE=colors.HexColor("#f5f8fa")
ORANGE=colors.HexColor("#aa661b")
GRAY=colors.HexColor("#516774")
W,H=A4
FW=W-96
pdfmetrics.registerFont(TTFont("KRv3",str(FONT/"NotoSansKR-400.ttf")))
pdfmetrics.registerFont(TTFont("KRBv3",str(FONT/"NotoSansKR-700.ttf")))
pdfmetrics.registerFontFamily("KRv3",normal="KRv3",bold="KRBv3",italic="KRv3",boldItalic="KRBv3")
S=getSampleStyleSheet()
S.add(ParagraphStyle("BodyV3",fontName="KRv3",fontSize=9.35,leading=14.8,textColor=INK,spaceAfter=8,wordWrap="CJK"))
S.add(ParagraphStyle("SmallV3",parent=S["BodyV3"],fontSize=8.1,leading=11.8,spaceAfter=5))
S.add(ParagraphStyle("CaptionV3",parent=S["BodyV3"],fontSize=8.1,leading=11.6,textColor=GRAY,spaceAfter=9))
S.add(ParagraphStyle("H1V3",parent=S["BodyV3"],fontName="KRBv3",fontSize=21,leading=29,spaceAfter=12))
S.add(ParagraphStyle("H2V3",parent=S["BodyV3"],fontName="KRBv3",fontSize=12,leading=17.5,spaceBefore=6,spaceAfter=7,textColor=TEAL))
S.add(ParagraphStyle("KickerV3",parent=S["BodyV3"],fontName="KRBv3",fontSize=8.5,leading=13,textColor=TEAL,spaceAfter=8))
S.add(ParagraphStyle("CoverV3",parent=S["BodyV3"],fontName="KRBv3",fontSize=29,leading=39,spaceAfter=14))
S.add(ParagraphStyle("CodeV3",fontName="Courier",fontSize=7.45,leading=11,textColor=INK,backColor=LIGHT,leftIndent=8,rightIndent=7,borderPadding=8,spaceBefore=4,spaceAfter=9,wordWrap="LTR"))
S.add(ParagraphStyle("RefV3",parent=S["BodyV3"],fontSize=8,leading=11.5,spaceAfter=10))
def read_json(relative):
 return json.loads((ROOT/relative).read_text(encoding="utf-8"))
TEST=read_json("data/final_test_summary.json")
MECH=read_json("data/mechanics_v3/optical_pair/pair_metrics.json")
TWO=read_json("data/mechanics_v3/two_ply/pair_metrics.json")
OPT=read_json("data/optical_v3/optical_scale_metrics.json")
MESH=read_json("data/mechanics_v3/mesh_refinement.json")
BEAM=read_json("data/mechanics_v3/beam_benchmark.json")
SWEEP=read_json("data/mechanics_v3/parameter_sweeps.json")
STORY=[]
PAGE_TITLES=[]

def p(text, style="BodyV3"):
    text = text.replace("ᵀ", "<super>T</super>")
    supers = "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻"
    subs = "₀₁₂₃₄₅₆₇₈₉ᵢₙₓ"
    text = re.sub("[" + supers + "]+", lambda m: "<super>" + m.group().translate(
        str.maketrans(supers, "0123456789+-")) + "</super>", text)
    text = re.sub("[" + subs + "]+", lambda m: "<sub>" + m.group().translate(
        str.maketrans(subs, "0123456789inx")) + "</sub>", text)
    return Paragraph(text, S[style])


def add(text, style="BodyV3"):
    STORY.append(p(text, style))


def title(number, text, subtitle=""):
    if STORY:
        STORY.append(PageBreak())
    PAGE_TITLES.append(text)
    add(f"FABRIC ENGINE / v{VERSION} / {number:02d}", "KickerV3")
    add(text, "H1V3")
    if subtitle:
        add(subtitle, "CaptionV3")


def sub(text):
    add(text, "H2V3")


def table(headers, rows, widths=None, small=True):
    st = "SmallV3" if small else "BodyV3"
    values = [headers] + rows
    cells = [[p(escape(str(c)).replace("\n", "<br/>"), st) for c in row] for row in values]
    t = Table(cells, colWidths=widths, hAlign="LEFT", repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, 0), .8, TEAL),
        ("LINEBELOW", (0, 1), (-1, -1), .25, colors.HexColor("#d6e0e6")),
    ]))
    STORY.extend([t, Spacer(1, 7)])


def callout(head, body):
    t = Table([[p(head, "H2V3")], [p(body)]], colWidths=[FW], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE),
        ("LINEBEFORE", (0, 0), (0, -1), 3, TEAL),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 9),
    ]))
    STORY.extend([t, Spacer(1, 9)])


def equation(expr, maxh=43):
    expr = re.sub(r"(\\(?:mathbf|mathcal|mathrm))\s+([A-Za-z])", r"\1{\2}", expr).replace(r"\sqrt2", r"\sqrt{2}")
    buf = io.BytesIO()
    math_to_image("$" + expr + "$", buf, dpi=210, format="png", color="#182b3a")
    buf.seek(0)
    with PILImage.open(buf) as im:
        iw, ih = im.size
    scale = min((FW - 12) / iw, maxh / ih, 72 / 165)
    buf.seek(0)
    pic = Image(buf, width=iw * scale, height=ih * scale)
    pic.hAlign = "CENTER"
    STORY.extend([Spacer(1, 3), pic, Spacer(1, 10)])


def fig(relative, caption, maxh=295, width=FW):
    path = ROOT / relative
    with PILImage.open(path) as im:
        iw, ih = im.size
    scale = min(width / iw, maxh / ih)
    pic = Image(str(path), width=iw * scale, height=ih * scale)
    pic.hAlign = "CENTER"
    STORY.append(pic)
    add(caption, "CaptionV3")


def code(text):
    add(escape(text).replace("\n", "<br/>"), "CodeV3")



def arrow(d,x1,y1,x2,y2,color=GRAY,dashed=False):
    ln=Line(x1,y1,x2,y2,strokeColor=color,strokeWidth=1.1)
    if dashed: ln.strokeDashArray=[3,3]
    d.add(ln)
    a=math.atan2(y2-y1,x2-x1); c=math.cos(a); s=math.sin(a)
    d.add(Polygon([x2,y2,x2-6*c+3*s,y2-6*s-3*c,x2-6*c-3*s,y2-6*s+3*c],fillColor=color,strokeColor=color))

def box(d,x,y,w,h,top,bottom="",fill=LIGHT,stroke=TEAL):
    d.add(Rect(x,y,w,h,rx=5,ry=5,fillColor=fill,strokeColor=stroke,strokeWidth=.8))
    d.add(String(x+w/2,y+h/2+(7 if bottom else -3),top,fontName="KRBv3",fontSize=9.7,textAnchor="middle",fillColor=INK))
    if bottom: d.add(String(x+w/2,y+h/2-10,bottom,fontName="KRv3",fontSize=8,textAnchor="middle",fillColor=GRAY))

def architecture():
    d=Drawing(FW,285); bw=148; xs=[0,(FW-bw)/2,FW-bw]
    for x,head,detail in zip(xs,["직조·원사 설계","합성 / 실측 재료","관측 조건"],["draft · pitch · twist","n(λ), κ(λ), EA, B","조명 · 카메라 · 파장"]):
        box(d,x,233,bw,44,head,detail)
    box(d,0,158,234,49,"원사 높이 평형","고정 track · 인장 · 작은 기울기")
    box(d,FW-234,158,210,49,"Fiber - Ply - Yarn 계층","현재 중심선에 명시적 섬유 재생성")
    arrow(d,74,233,74,207); arrow(d,249,233,196,207); arrow(d,249,233,355,207); arrow(d,234,182,FW-234,182)
    box(d,0,78,234,49,"광학 축약 진단","투영 면적 → 계층별 SGGX")
    box(d,FW-234,78,234,49,"개별 섬유 광선 수송","Mitsuba · 파장별 실제 렌더링")
    arrow(d,355,158,355,127); arrow(d,310,158,117,127)
    route=[(FW-74,233),(FW-74,219),(FW-11,219),(FW-11,141),(FW-74,141)]
    for (x1,y1),(x2,y2) in zip(route[:-1],route[1:]):
        d.add(Line(x1,y1,x2,y2,strokeColor=GRAY,strokeWidth=1.1))
    arrow(d,FW-74,141,FW-74,127)
    box(d,0,0,234,48,"정규화·식별·기하 검사","수식 반례 · held-out 방향 · SHA")
    box(d,FW-234,0,234,48,"분광 관측·평가","CIE XYZ · seed 구간 · 새 관측 설계")
    arrow(d,117,78,117,48); arrow(d,355,78,355,48)
    STORY.append(d); STORY.append(Spacer(1,10))

def citation_note(text): add(text,"CaptionV3")

def footer(canvas,doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#d6e0e6")); canvas.line(48,43,W-48,43)
    canvas.setFillColor(GRAY); canvas.setFont("KRv3",7.3)
    canvas.drawString(48,29,"TEXTILE OPTICS ENGINE  /  v0.3.0  /  2026-10-11")
    canvas.drawRightString(W-48,29,f"{doc.page:02d}")
    canvas.restoreState()

# 01: cover, with an explicit achieved scope.
title(1,"원사에서 직물까지","실행한 모델·수치 결과·검증을 묶은 연구 엔진 보고서")
add("원사 평형과 계층 기하를<br/>분광 외관에 연결하다","CoverV3")
add("Fiber → Ply → Yarn → Weave → Fabric · v0.3.0","H2V3")
add("목표는 원단의 사진을 더 선명하게 만드는 것에서 나아가, 조명과 관찰 방향이 바뀔 때 재질의 모습이 어떻게 달라지는지 예측하는 것이다. 이번 버전은 원사의 장력·굽힘에 따라 달라지는 기하를 실제 섬유 모델에 전달하고, 그 차이를 방향 통계와 분광 광선 추적으로 계산했다.")
architecture()
table(["이번에 실제 수행한 것","결과의 의미"],[
    ["축소 원사 높이 평형 + 명시적 fiber 재생성","기계 파라미터 → 기하 → 광학 관측의 실행 경로 확보"],
    [f"{OPT['actual_explicit_fiber_render_count']}회 파장별 개별 섬유 렌더링","64×64, 32 spp, 독립 seed 4개; 합성 재료의 반사·투과 관측"],
    ["계층별 SGGX fitting + 독립 리뷰","방향 정보 축약 오차와 수치 주장에 필요한 조건을 분리"],
],[224,FW-224])
add("염색·퇴색은 제외했다. 실제 실크·코튼·큐프라·린넨의 물성 교정, 전체 의류 drape, 완전한 3D 파동 수송, 메타표면 제작과 성능 입증은 후속 단계다. 이 경계는 구현 부족을 감추는 항목이 아니라 다음 실험을 정의하는 기준이다.","CaptionV3")

# 02: purpose.
title(2,"연구 목적의 업데이트")
callout("측정하고 싶은 것은 ‘변화에 대한 외관 반응’", "같은 직조라도 원사 장력·굽힘·꼬임·미세 배치가 다르면 방향별 광택과 비침이 달라질 수 있다. 원단을 설명하는 계층 모델에서 이 변화가 어디에서 생기는지 추적하고, 적은 관측으로 그 차이를 복원할 수 있는지 평가한다.")
add("4K 촬영은 공간 sampling을 늘리는 유효한 기준선이다. 하지만 하나의 조명·시점에서 더 많은 픽셀을 얻는 일과, 조명·시점·파장 변화에 대한 반응을 관측하는 일은 서로 다른 정보를 더한다. 첫 연구는 고해상도와 다중조명을 충분히 갖춘 RGB 기준계가 남기는 오차를 대상으로 해야 한다.")
table(["사용자가 알고 싶은 것","모델이 설명해야 할 것","이번 상태"],[
    ["방향성 광택·광택 폭","fiber 방향, 표면 수송, 가림","기하 + ray 계산 실행"],
    ["직조 대비·보풀의 외관","공간 배치, twist, irregularity","계층 생성; 실제 재료 교정 전"],
    ["역광의 비침·색 변화","공극, 흡수, 투과 수송","합성 R/T 분광 관측 실행"],
    ["silk/cotton/cupra 느낌","실측 구조·광학·기계 파라미터","소재별 검증 전"],
    ["촉감·마찰·접촉 냉감","독립 물성·지각 기준","이번 범위에 없음"],
],[120,217,FW-337])
sub("이번 버전의 연구 질문")
add("<b>동일한 직조 순서에서 원사의 인장·굽힘 파라미터를 바꾸면, 평형 기하와 방향별 광학 반응이 어떻게 바뀌는가? Fiber부터 fabric까지 정보를 합칠 때, 어느 수준의 방향 구조를 유지해야 정해진 관측 오차를 줄일 수 있는가?</b>")
sub("앞으로 논문 기여가 될 수 있는 질문")
add("기하 변화와 흡수·roughness 변화가 RGB 기준계에서 혼동되는 구체적인 조건을 찾고, 그 혼동을 푸는 최소 추가 관측을 설계한다. 메타표면은 그 관측을 실제 효율·광량·부피 제약 아래 구현하는 단계다. ‘메타표면을 썼다’ 자체보다, 어떤 불확실성을 얼마나 줄였는지가 기여의 중심이다.")
citation_note("근거 범위: 실제 v3 실행 결과는 [D1-D4]. R/T 관측 및 미세 계층 외관의 설계 근거는 [R1-R3, R8-R11]. 4K와 추가 관측의 비교는 아직 수행 전이다.")

# 03: modules.
title(3,"모듈별 설계와 데이터 계약")
architecture()
table(["모듈 / 파일","입력 → 출력","검증 책임"],[
    ["위상 · weave_draft.py","binary crossing → 명시적 draft","warp/weft 축·bit convention"],
    ["기하 · hierarchy.py","fiber/ply/yarn spec → polyline 계층","호길이·RMF·sampling·간격"],
    ["평형 · weave_mechanics.py","draft + EA/B/rest length → z","convex domain·KKT·state binding"],
    ["공통 광학 · optical_scene.py","기하 + 재료 → optical scene","단위·ID·section/export 유효성"],
    ["축약 · optical_lod.py","선분 → 투영값/SGGX/XYZ","가산성·rank·정규화·observer"],
    ["실행 · run_engine_v3.py","선택 stage + input/output 경로","재현·hash·완료/실패 상태"],
],[173,181,FW-354])
add("기하와 재료를 한 RGB texture로 합치지 않는다. 동일한 OpticalScene에 개별 fiber 반지름과 material ID를 남겨 후속 wave, ray, 집계 모델이 같은 기준 입력을 소비하도록 했다. 선택한 단계의 결과가 존재한다는 것과 해당 단계가 이번에 계산됐다는 것도 실행 manifest에서 구별한다.")
citation_note("실행 가능한 기존 2D 원통 Maxwell·ray adapter는 v0.2에서 유지한다. v0.3가 임의 곡률의 3D fiber를 그 solver에 자동 전달하는 것은 아니다. 상세 계약: docs/ARCHITECTURE.md와 notes/optical_scale_v3.md.")

# 04: hierarchy and draft.
title(4,"Low level → High level: 무엇을 보존하는가")
table(["계층","필수 정보","v0.3에서의 역할"],[
    ["Material / fiber constituent","복소 n(λ)+iκ(λ), 출처, 유효 역학","합성 스펙트럼과 유효 원사 강성은 별도 입력"],
    ["Fiber","중심선, 반지름, 재료 ID, 부모 ID","광학 수송의 명시적 구성 단위"],
    ["Ply","fiber 집합, packing, signed twist","여러 fiber를 부모 호길이에 맞춰 배치"],
    ["Yarn","ply 집합, ply twist, yarn 중심선","평형 solver가 높이 중심선을 공급"],
    ["Weave","교차 순서, pitch, 경·위사 설정","선형 위상·간격 제약을 정의"],
    ["Finite fabric patch","경계, 반복수, 전체 기하·통계","실제 전후 기하 및 분광 관측 단위"],
    ["전체 의류 / 거시 외관","drape, 변형 운반, BSDF/LOD","후속 모듈; 현재 finite patch와 구분"],
],[115,182,FW-297])
sub("Twist의 기준은 부모의 실제 호길이")
equation(r"\phi(s)=\phi_0+2\pi\tau s,\qquad \mathbf f(s)=\mathbf c(s)+u(s)\mathbf n(s)+v(s)\mathbf b(s)",43)
add("τ의 부호가 S/Z 방향을 표현하고, s는 현재 부모 중심선의 실제 호길이다. Rotation-minimizing frame은 부모가 구부러질 때 불필요한 frame twist를 줄인다. Migration·waviness·loop 생성 기능은 v0.2에서 유지하되, 이들이 역학적으로 평형을 이룬다는 주장은 하지 않는다. [R4, R5]")
sub("직조를 바꿀 때 가장 쉽게 틀리는 계약")
add("이 저장소는 행=weft, 열=warp, 1=warp over이다. 경사·위사를 물리적으로 교환하면 단순 전치가 아니라 <b>1 - matrix.T</b>가 필요하다. Weavecraft/Leaf의 일부 card convention은 1=weft over이므로 importer가 bit를 변환해야 한다. 이름만 바꾸면 교차 위상이 뒤집힌다. [R6, R7]")
callout("다층 직조는 binary matrix를 확장하는 문제만은 아니다", "Weavecraft의 3D block처럼 교차별 ordered stack, 지속적인 yarn ID와 연결, wraparound 및 경계 조건이 필요하다. 현재 single-layer orthogonal draft는 이 다층 위상을 이미 지원한다고 표시하지 않는다.")

# 05: research map.
title(5,"논문과 코드에서 바뀐 설계 판단")
add("첨부 FabricGen 및 Tang R/T 논문에서 출발해, 참조 계보와 관련된 역학·광학 모델의 실제 표현 차이를 확인했다. 논문의 아이디어를 읽은 수준, 공식을 독립 구현한 수준, 원저자 시스템을 실행한 수준은 서로 다르다.")
table(["연구","확인한 핵심","본 엔진의 대응"],[
    ["Weavecraft / Leaf [R6,R7]","ordered yarn stacks, spline rod, 장력·경계","binary topology + 제한된 높이 평형; 전체 알고리즘 재현 아님"],
    ["Discrete Elastic Rods [R5]","material frame, 곡률·비틀림 에너지","small-slope height bending으로 범위 명시"],
    ["Tang R/T / FabricGen [R1,R2]","반사·투과, implicit appearance 계층","명시적 fiber scene과 관측 연결; inverse network 미실행"],
    ["SGGX / SpongeCake [R9,R10]","투영 정규화, 이방성 소광·층 수송","정규화 수학 구현; 전체 fabric BSDF와 구분"],
    ["Yang SGGX fitting [R11]","footprint별 yarn NDF의 multi-SGGX fit","직물 SGGX/계층 fitting 자체의 신규성은 주장하지 않음"],
    ["Yu ray-wave [R12]","평균 ray, wave variation, aperture 회절","영역별 모델 분리; hybrid shader 완전 재현 전"],
],[135,178,FW-313])
sub("검증한 인용 연결")
add("Leaf 2018 → Weavecraft 2020, Montazeri 2020 → Tang 2024 → FabricGen 2026, Tang 2024 → Li의 Fiber-level Capture → FabricGen의 연결을 원문 bibliography/본문에서 확인했다. SGGX → SpongeCake → Tang의 광학 계보도 확인했다. 화살표는 ‘뒤 논문이 앞 논문을 인용함’을 뜻한다.")
add("FabricGen을 인용하는 독립적인 후속 논문은 이번 한정 검색에서 원문 bibliography로 확인하지 못했다. Yang 2026의 호 발행 연도만으로 Tang/FabricGen의 후속이라고 연결하지 않았다. Yang의 full publisher PDF와 구현은 확인 범위 밖이며, publisher abstract/metadata에 근거해 직접 중복 가능성을 기록했다.","SmallV3")
sub("공식 GitHub와 재사용 범위")
add("Tang 공식 FabricBTDF-Recovery는 특정 revision과 GPL-3.0을 확인했다. TexGen 인터페이스와 라이선스도 검토했다. 이 코드들을 새 모듈에 복사하지 않았다. FabricGen/Weavecraft의 웹사이트 템플릿 링크나 동명 저장소를 방법 구현으로 취급하지 않았으며, 확인되지 않은 방법 코드를 실행했다고 주장하지 않는다.","SmallV3")
citation_note("열람 절·원문 hash·코드 revision·누락 범위는 notes/literature_engine_v2.md 및 notes/literature_engine_v3.md에 기록했다.")

# 06: mechanics input/domain.
title(6,"원사 역학: 변수·단위·경계")
add("기존 기하 생성기는 교차 위아래 순서를 만족하는 곡선을 만들었다. v0.3는 그 순서를 만족하는 여러 곡선 중, 선언한 원사 에너지가 작은 높이 배치를 계산한다. 평면상의 track은 고정되고, 미지수는 track 위 샘플의 높이 z다.")
equation(r"\mathbf c_j^w(y)=(x_j,y,z_j^w(y)),\qquad \mathbf c_i^f(x)=(x,y_i,z_i^f(x))",43)
table(["기호 / 입력","단위","정의와 제약"],[
    ["h, z, l₀","mm","projected interval, height, rest interval"],
    ["EA / axial_stiffness_N","N","유효 축방향 강성; 실측 식별 전"],
    ["B / bending_stiffness_N_mm2","N mm²","유효 굽힘 강성; fiber modulus와 동일시하지 않음"],
    ["r / rest_fraction","1","l₀ = rh; 0 < r ≤ 1; 최적화 중 고정"],
    ["E, gradient, Hessian","N mm / N / N mm⁻¹","차원 공변성과 독립 차분으로 검사"],
    ["source / data_status","문자열","synthetic / measured / literature 출처"],
],[169,99,FW-268])
sub("끝점과 pretension")
add("첫·마지막 교차점 밖에 padding을 두고, 두 끝의 높이를 0으로 고정한다. 끝 회전은 자유인 simply-supported graph 근사다. 경계 영향이 존재하므로 무한 주기 원단의 해로 읽으면 안 된다. 현재 기하는 finite patch이며 임의 반복 타일의 연속성을 보증하지 않는다.")
equation(r"\epsilon_{\mathrm{flat}}=\frac{1}{r}-1,\qquad r=\frac{1}{1+\epsilon_{\mathrm{flat}}}",40)
add("rest_fraction=0.99는 정확히 1% engineering strain이 아니다. 1%를 지정하려면 r=1/1.01로 변환한다. Weavecraft의 strain-balancing처럼 현재 길이에 따라 rest length를 반복 갱신하는 알고리즘도 이번에는 사용하지 않았다. [R6]")
callout("역학 범위", "고정 track의 인장 영역 + 작은 기울기 굽힘 + 보수적 envelope 제약이다. 압축 buckling, yarn sliding, material-frame twist, 마찰·접촉압, 단면 압착과 garment drape는 계산하지 않는다. 이 제한이 convex 수치 검증의 전제다.")

# 07: energies.
title(7,"에너지·미분·Convexity")
add("한 segment에서 d=z<sub>k+1</sub>-z<sub>k</sub>, 실제 길이 l=√(h²+d²)이다. 축방향 quadratic strain law에서 평평한 기준의 상수 에너지만 뺀 excess energy를 최소화한다. 상수 제거는 힘이나 평형을 바꾸지 않는다.")
equation(r"E_s=\sum_k\frac{EA}{2\ell_{0,k}}\left[(\ell_k-\ell_{0,k})^2-(h_k-\ell_{0,k})^2\right]",45)
equation(r"q=\frac{EA}{\ell_0}\left(1-\frac{\ell_0}{\ell}\right)d,\qquad q'=\frac{EA}{\ell_0}\left(1-\frac{\ell_0h^2}{\ell^3}\right)\geq0",43)
add("l ≥ h ≥ l₀이므로 q′ ≥ 0이다. 압축 가능한 rest_fraction > 1을 거부하는 이유가 이 부등식에 있다. 수치 계산은 l-h=d²/(l+h)를 이용해 거의 평평한 상태에서 큰 값의 뺄셈을 피한다.")
equation(r"E_b=\frac{B}{2h^3}\|D_2z\|^2,\quad \nabla E=D_1^Tq+\frac{B}{h^3}D_2^TD_2z",44)
equation(r"H=D_1^T\mathrm{diag}(q')D_1+\frac{B}{h^3}D_2^TD_2",37)
add("D₁과 D₂는 고정 끝점을 반영한 1차·2차 차분이다. 각 Hessian 항은 PSD이며 높이 제약은 선형이다. 양의 B와 고정 끝점을 가진 본 예제는 엄격한 convex 문제를 구성한다. 작은 KKT 잔차는 이 이산 모델의 평형 근거이며 실물 정확도 인증은 아니다.")
sub("작은 기울기의 물리적 오차를 숨기지 않는다")
equation(r"\kappa^2\,ds=\frac{[z''(x)]^2}{(1+[z'(x)]^2)^{5/2}}\,dx",37)
add(f"평형 광학 fixture의 최대 기울기는 {MECH['equilibrium']['relaxed']['constraints']['max_abs_slope']:.5f}이며, 두 연속체 integrand의 비율 진단 (1+L²)^(5/2)-1은 {100*MECH['equilibrium']['relaxed']['constraints']['small_slope_bending_integrand_overestimate_bound']:.2f}%다. 이는 모델의 근사 크기를 경고하는 진단이다. 이산 곡률, 중심선 위치 또는 영상의 오차 상한이 아니다.","SmallV3")
sub("차원 scaling과 경계 stencil도 따로 검증")
equation(r"(h,z,B)\mapsto(ah,az,a^2B)\quad\Rightarrow\quad(E,g,H)\mapsto(aE,g,H/a)",42)
add("EA와 r을 고정하고 길이와 B를 함께 바꾸면 위 similarity가 성립한다. 유한 진폭에서 실제 energy·gradient·Hessian이 이 관계를 따르는지 독립 시험했다. 또한 pinned-end sine mode로 2차 차분의 경계와 두 강성 계수를 분리 확인했다.","SmallV3")
equation(r"\mu_k=4\sin^2\frac{k\pi}{2(n+1)},\qquad\lambda_k=\frac{EA(1-r)}{rh}\mu_k+\frac{B}{h^3}\mu_k^2",43)
citation_note("유도와 구현: notes/weave_mechanics_v3.md §§3-4; 독립 검증: notes/review_engine_v3.md. 유한 회전·material frame과의 차이: DER [R5].")

# 08: constraints/proof/solver.
title(8,"교차 순서에서 실제 간격 하한까지")
add("교차점의 수직 높이차만으로 두 원사가 분리됐다고 판단하면, 기울어진 segment에서 실패할 수 있다. 각 원사의 height graph에 Lipschitz 상한 L을 부여하고 이를 교차 제약과 함께 사용한다.")
equation(r"|z_{k+1}-z_k|\leq Lh,\qquad \sigma(z_w-z_f)\geq D",40)
equation(r"D=(R_w+R_f+g)\sqrt{1+L_w^2+L_f^2}",37)
add("σ는 draft에서 정한 위아래 부호, R은 yarn envelope 반지름, g는 요구 간격이다. 교차점에서 projected displacement u,v만큼 떨어진 임의의 점 쌍에 삼각부등식과 Cauchy-Schwarz를 적용한다.")
equation(r"D\leq|\Delta z|+L_w|u|+L_f|v|\leq\sqrt{1+L_w^2+L_f^2}\sqrt{u^2+v^2+\Delta z^2}",42)
add("따라서 모든 서로 직교하는 두 track의 중심선 거리는 D/√(1+L<sub>w</sub>²+L<sub>f</sub>²) 이상이다. 같은 family의 평행 track은 pitch ≥ 2R+g를 별도로 확인한다. 이 제약은 보수적 기하 envelope 조건이며, 실제 압력·마찰·접촉 면적을 계산하는 법칙이 아니다.")
sub("해석적 gradient와 독립 최적성 확인")
table(["순서","수행 내용"],[
    ["조건화","초기 Hessian Cholesky whitening; 실패 시 identity fallback"],
    ["최적화","SLSQP + analytic gradient + Az ≥ b의 선형 제약"],
    ["독립 KKT","active inequality의 비음수 multiplier를 NNLS로 추정"],
    ["합격 검사","stationarity, complementarity, feasibility, 에너지 감소"],
    ["export 재검사","problem/spec SHA + solved-height SHA; KKT와 에너지 다시 계산"],
],[89,FW-89])
add("독립 리뷰에서 ‘틀린 상태에 붙은 오래된 equilibrium 인증’과 ‘위반된 slope 상한으로 계산한 간격 인증’을 실제 반례로 발견해 수정했다. export는 오래된 diagnostic dictionary를 신뢰하지 않으며, slope 전제가 깨지면 해당 configured certificate를 반환하지 않는다.","SmallV3")
citation_note("증명·회귀·잔차의 범위: notes/review_engine_v3.md; 이 제약과 개별 fiber clearance audit는 서로 다른 검사다.")

# 09: mechanics actual.
title(9,"실행 결과: 원사 평형이 기하를 바꾼다")
add("광학 전달용 시편은 3×3 평직, 6 yarn, yarn당 1 ply×7 fiber다. Fiber 반지름 3 μm, yarn pitch 0.24 mm이며, 경·위사에 별도 synthetic 재료 ID를 부여했다. EA=0.02 N, B<sub>w</sub>/B<sub>f</sub>=10, r<sub>w</sub>=0.985, r<sub>f</sub>=0.995인 합성 fixture다.")
E=MECH['equilibrium']; I=E['initial']; R=E['relaxed']
table(["관측량","초기 feasible 기하","축소 모델 평형"],[
    ["Excess energy [N mm]",f"{E['initial_energy_excess_N_mm']:.7e}",f"{E['final_energy_excess_N_mm']:.7e}"],
    ["Warp crimp",f"{100*I['families']['warp']['crimp_ratio']:.6f}%",f"{100*R['families']['warp']['crimp_ratio']:.6f}%"],
    ["Weft crimp",f"{100*I['families']['weft']['crimp_ratio']:.6f}%",f"{100*R['families']['weft']['crimp_ratio']:.6f}%"],
    ["Fiber 전체 길이 [mm]",f"{MECH['initial']['total_fiber_length_mm']:.7f}",f"{MECH['relaxed']['total_fiber_length_mm']:.7f}"],
    ["Cylinder-volume proxy [mm³]",f"{MECH['initial']['cylinder_volume_proxy_mm3']:.9f}",f"{MECH['relaxed']['cylinder_volume_proxy_mm3']:.9f}"],
],[181,158,FW-339])
fig("figures/mechanics_v3/mechanics_to_geometry.png","실제로 계산한 원사 높이, tangent second moment 변화 및 최적화 경과. 좌·우 상단은 경·위사 중심선이며 회색 점선은 초기 기하다. 섬유 재생성은 이 중심선 결과를 입력으로 사용한다.",maxh=290)
add(f"이 fixture의 에너지는 {100*E['energy_reduction_fraction']:.4f}% 감소했다. 최대 제약 위반은 {E['kkt']['max_constraint_violation_mm']:.2e} mm, stationarity infinity norm은 {E['kkt']['stationarity_inf_N']:.2e} N이었다. 두 family의 crimp가 서로 다른 방향으로 이동하는 현상이 이후 조명별 광학 차이를 만드는 입력이 됐다.","SmallV3")
citation_note("수치 출처 [D1]: data/mechanics_v3/optical_pair/pair_metrics.json. 에너지 감소율은 해당 초기화 대비 수치 최적화 지표이며, 원단 품질 또는 실물 일치도 점수가 아니다.")

# 10: verification actual.
title(10,"파라미터 sweep와 실제 mesh 수렴")
fig("figures/mechanics_v3/mechanics_validation.png","좌상: 경·위사 B ratio만 변화. 우상: warp flat-state engineering prestrain만 변화. 좌하: 실제 4→8→16 mechanical grid. 우하: 독립 해석적 beam 기준해.",maxh=330)
add("B ratio 증가와 warp pretension 증가는 이 fixture에서 warp crimp를 줄이고 weft crimp를 키웠다. 두 sweep을 분리해 강성 변화와 rest length 변화의 영향을 혼동하지 않았다. Plain·2/1 twill·2×2 basket의 4×4 패치도 실제 최적화했으며, 위상마다 다른 경계·초기 문제의 에너지 감소를 우열로 해석하지 않았다.")
table(["기계 grid 비교","RMS 높이 차이","최대 높이 차이","에너지 차이"],[
    [f"{d['coarse_segments_per_crossing']} → {d['fine_segments_per_crossing']}",f"{1000*d['rms_interpolated_height_difference_mm']:.5f} μm",f"{1000*d['max_interpolated_height_difference_mm']:.5f} μm",f"{100*d['relative_energy_difference']:.4f}%"] for d in MESH['comparisons']
],[105,131,132,FW-368])
equation(r"z(x)=\frac{qx(L^3-2Lx^2+x^3)}{24B}",38)
add("Simply-supported beam에서 EA=0, uniform load q를 두고 위 해석해와 차분 helper를 비교했다. 12/24/48/96 elements의 최대 변위 오차는 약 1.0e-5 / 2.5e-6 / 6.25e-7 / 1.56e-7 mm로 2차 수렴했다. 이 helper benchmark가 일반 분포하중·중력 drape API의 구현을 뜻하지는 않는다.","SmallV3")
citation_note("수치 출처 [D1]: parameter_sweeps.json, mesh_refinement.json, beam_benchmark.json. 광학 시편은 8 segments/crossing을 사용했다. 16-grid도 continuum 참값이 아니다.")

# 11: physical boundary at regeneration.
title(11,"기하 → 광학: 보존한 것과 변한 것")
add("평형 결과는 v0.2의 public yarn 생성기로 들어간다. 추가 subdivision은 mechanical polyline 위의 샘플 수만 늘리며, 이 단계에서 조용히 spline으로 바꾸지 않는다. OpticalScene은 다시 material ID·부모 관계·반지름·단위를 확인한다.")
code("problem = ReducedWeaveProblem(spec)\nresult = solve_equilibrium(problem)\ngeometry = build_relaxed_hierarchy(\n    problem, result, warp_yarn, weft_yarn, subdivisions=6)\naudit_clearance(geometry)\nscene = from_hierarchy(geometry, materials)")
callout("동일한 ID는 동일한 material point를 뜻하지 않는다", "변한 yarn 중심선에 fiber를 다시 구성한다. 부모의 현재 호길이당 twist를 유지하므로 fiber 길이·부피 proxy가 달라질 수 있다. 질량·strain·twist를 보존하는 실제 섬유 변형 모델은 아니다. 모든 기하에 fiber_material_points_conserved=False를 기록했다.")
table(["전후 비교","실제 변화 / 검사","해석"],[
    ["전체 fiber 길이",f"{100*OPT['fiber_material_volume_relative_change']:+.6f}%","고정 반지름이므로 부피 proxy도 같은 비율"],
    ["Warp / weft 길이","-0.573576% / +0.662060%","작은 총량 변화가 family별 재분배를 없애지 않음"],
    ["구성 / 재료 / 관측계","동일 fiber ID·radius·material·rig","영상 차이는 재생성된 기하 전체에 귀속"],
    ["Multi-ply 별도 예제",f"{TWO['relaxed']['fiber_count']} fibers; 2 plies × 7 / yarn","기하 연결 실증; constituent stress transfer 아님"],
],[127,172,FW-299])
sub("Spline export의 충돌 위험도 별도로 계산")
table(["상태","Polyline 간격 하한","Export 후 간격 하한"],[
    [label,f"{1000*OPT[k+'_exported_clearance_budget']['source_clearance_lower_bound_mm']:.5f} μm",f"{1000*OPT[k+'_exported_clearance_budget']['exported_clearance_lower_bound_mm']:.5f} μm"] for k,label in [('initial','초기'),('relaxed','평형')]
],[94,194,FW-288])
add("서로 다른 fiber 간격에서 양쪽 curve의 smoothing·float32 저장 변위 상한을 차감했다. 남은 양의 하한은 이 exporter가 fiber들을 겹치게 만들지 않는다는 기하 근거다. 같은 fiber의 self-contact나 하이라이트·영상 오차 상한을 보증하지 않는다.","SmallV3")

# 12: projection counterexample.
title(12,"방향 통계: 평균 tensor만으로 충분한가")
add("기하를 단순한 tangent second moment로 압축하면, 실제 방향 반응을 정하는 고차 정보가 사라질 수 있다. 먼저 개별 원통 선분의 옆면 투영 면적을 합산한 기준량을 정의했다.")
equation(r"g(\omega)=\frac{1}{V}\sum_j2r_jL_j\sqrt{1-(t_j\cdot\omega)^2},\qquad [g]=\mathrm{mm}^{-1}",43)
add(f"두 상태와 모든 group에 공통 평균 부피 V={OPT['common_averaging_volume_mm3']:.8f} mm³를 사용했다. 초기·평형 union bounding box에서 얻은 값이다. 같은 V를 쓰므로 g<sub>all</sub>=Σg<sub>group</sub>가 정확히 성립한다. 각 yarn의 별도 부피로 정규화한 값들을 단순 합산하면 이 계약이 깨진다.")
sub("동일 second moment, 다른 비선형 방향 반응")
equation(r"\mathcal T_A=\{e_x,e_y\},\qquad\mathcal T_B=\{(e_x+e_y)/\sqrt2,(e_x-e_y)/\sqrt2\}",41)
equation(r"Q_A=Q_B=\mathrm{diag}(1/2,1/2,0),\quad \tilde g_A(e_x)=0.5,\quad\tilde g_B(e_x)=1/\sqrt2",43)
add("같은 rL weight를 가진 방향 집합의 second moment는 같지만, 총 선분 weight로 정규화한 투영 면적은 0.5와 0.70710678이다. 동일한 평균 tensor에서 방향 응답을 유일하게 복원할 수 없다는 독립 수학 반례다. 이 두 기하의 고해상도 RGB 사진이 동일하다는 주장이나 새로운 SGGX 이론의 발견으로 읽으면 안 된다.")
sub("이 기준량이 포함하지 않는 것")
table(["포함","제외"],[
    ["segment 길이·반지름·접선의 비선형 방향 함수","끝면·joint 중복·projected silhouette의 겹침"],
    ["동일 부피에서 group 가산성","가림·공간 상관·multiple scattering"],
    ["길이 scaling과 subdivision 불변성","실측 소광계수·투과율·회절·fabric BSDF"],
],[244,FW-244])
add("따라서 다음 SGGX fitting의 오차는 이 unoccluded line-element statistic의 압축 오차다. 투영 오차가 작으면 영상도 정확하다고 결론 내리지 않는다. 집계 수송 모델을 만들 때는 위 제외 항목을 별도 근사하고 개별 섬유 렌더와 검증해야 한다. [R9,R10]")

# 13: SGGX fit results.
title(13,"계층별 SGGX 축약: 실제 수치 비교")
equation(r"\hat g_S(\omega)=\sqrt{\omega^TS\omega},\quad S\succ0,\quad\min_S\sum_iw_i[\hat g_S(\omega_i)-g(\omega_i)]^2",46)
add("log-Cholesky 좌표로 SPD를 유지한다. g²의 선형 fitting은 초기화에만 쓰고, 최종 목표는 g의 잔차다. 이 구현은 density scale을 S에 흡수했으므로 S의 단위는 mm⁻²다. 무차원 shape와 별도 density를 쓰는 convention과 혼용하지 않는다. [R9,R10]")
labels={'all':'Fabric 전체 1개','family':'경·위사 2개','yarn':'Yarn 6개','ply':'Ply 6개'}
table(["보존 수준","매개변수","초기 상대 RMSE","평형 상대 RMSE"],[
    [labels[d['level']],d['parameters'],f"{100*d['heldout_relative_rmse']:.4f}%",f"{100*OPT['projection_fits']['relaxed']['levels'][i]['heldout_relative_rmse']:.4f}%"] for i,d in enumerate(OPT['projection_fits']['initial']['levels'])
],[148,80,134,FW-362])
fig("figures/optical_v3/projected_area_lod.png","96개 학습 방향, 겹치지 않는 1,200개 평가 방향. 동일 합성 기하의 방향 보간·축약 오차이며, 새로운 원단에 대한 일반화 오차가 아니다.",maxh=260)
add("이 fixture에서는 두 family를 보존한 단계의 이득이 크다. 더 많은 yarn fitting은 개선되지 않았고, 평형 상태에서는 아주 조금 더 나빴다. Group별 잔차의 상쇄·누적 때문에 세분화가 항상 단조 개선을 보장하지 않는다. Yarn당 1 ply이므로 yarn/ply 행은 같은 분할이며 독립 ply-scale 개선을 증명하지 않는다.","SmallV3")
add("각도 설계 [x²,y²,z²,2xy,2xz,2yz]의 rank가 6 미만이면 fit를 거절한다. 같은 한 방향을 반복 관측해 잔차가 작아져도 6개 계수를 식별할 수 없기 때문이다. condition number와 SPD floor도 저장한다.","SmallV3")

# 14: normal/phase and transport.
title(14,"정규화와 광학 엔진의 실제 역할")
equation(r"D_S(m)=\frac{1}{\pi\sqrt{\det S}(m^TS^{-1}m)^2},\quad \int_{S^2}(\omega\cdot m)_+D_S(m)\,dm=\sigma(\omega)",47)
add("SGGX normal density D는 구면에서 적분 1인 일반 확률밀도가 아니다. 입사 방향에 대한 visible-normal density를 투영 면적으로 나누어 정규화해야 한다. 두 방향을 산란점에서 바깥쪽으로 향하게 정의할 때 이상적인 반사 microflake는 다음 식을 따른다. [R9,R10]")
equation(r"p(\omega_o|\omega_i)=\frac{D(h)}{4\sigma(\omega_i)},\quad h=\frac{\omega_i+\omega_o}{\|\omega_i+\omega_o\|}",42)
equation(r"\sigma(\omega_i)p(\omega_o|\omega_i)=\sigma(\omega_o)p(\omega_i|\omega_o)",37)
add("위상함수 단독의 대칭을 강제하면 이방성 소광을 잘못 다룬다. 미래 group mixture도 입사 방향별 σ<sub>k</sub>/Σσ<sub>j</sub>로 가중해야 한다. Arithmetic matrix 평균의 √(ωᵀSω)는 projected area의 선형 mixture와 같지 않으며 이 차이도 독립 반례로 테스트했다.")
sub("이번 외관 영상의 기준은 개별 fiber")
add("v0.3의 실제 영상은 이 SGGX phase를 cloth shader로 사용한 결과가 아니다. Mitsuba 3.9.1 hair transport에 실제 fiber curve를 넣고, 파장별 재료를 갱신해 계산했다. 광학 축약의 수학과 실제 섬유 기준 렌더를 분리해 이후 aggregate BSDF 검증의 기준을 만들었다. [R13]")
equation(r"\mu_a(\lambda_0)=\frac{4\pi\kappa}{\lambda_0},\quad\eta_{\mathrm{shader}}=n/n_b,\quad\sigma_{a,\mathrm{shader}}=\mu_a r",40)
add("진공 파장 λ₀를 mm로 맞추어 μ<sub>a</sub>의 단위를 mm⁻¹로 만든다. Hair의 radius-normalized absorption convention은 pinned source에서 확인한 v0.2 계약을 유지한다. n의 실수 Fresnel와 Beer 흡수를 사용하는 광선 근사이며, 복소 Fresnel의 모든 효과를 계산하는 Maxwell 해석은 아니다.","SmallV3")
add("Cached scene의 파장 갱신 결과를 같은 seed의 새 scene 결과와 비교하는 실제 renderer 테스트를 추가했다. 세 RGB 채널이 같은 scalar 응답인지 확인한 뒤 파장별 응답을 별도로 보존한다. RGB의 세 채널을 임의의 세 파장으로 치환한 계산이 아니다.","SmallV3")

# 15: experimental settings and observer.
title(15,"분광 관측: 실제 계산한 조건")
table(["항목","설정"],[
    ["기하","초기 / 평형, 각각 42 fiber · 8,064 segment"],
    ["관측","동일 정면 camera, 동일 world transform·source·pixel size"],
    ["반사 조명","elevation 40°, azimuth 0° 및 90°, halfwidth 7°"],
    ["투과 조명","elevation 55°, azimuth 45°, halfwidth 7°"],
    ["기본 파장","380-780 nm, 25 nm 간격 17개"],
    ["렌더 예산","64×64, 32 samples/pixel, 독립 seed 4개"],
    ["추가 수렴","반사 azimuth 0°에서 16 midpoint 파장 추가 → 12.5 nm"],
],[117,FW-117])
add(f"기본 2×3×17×4=408회, 추가 2×16×4=128회로 <b>{OPT['actual_explicit_fiber_render_count']}회</b>의 실제 개별 섬유 렌더를 수행했다. Lambertian radiometric benchmark 1회는 별도다. 파장별 원본 radiance 배열과 seed를 보존한다.")
equation(r"[X,Y,Z]_x^T=\frac{\int_{380}^{780}R_x(\lambda)E(\lambda)[\bar x,\bar y,\bar z]^T\,d\lambda}{\int_{380}^{780}E(\lambda)\bar y(\lambda)\,d\lambda}",54)
add("R<sub>x</sub>는 단위 source radiance에서 계산한 스칼라 응답이다. 렌더 파장 사이를 선형 보간하고 공식 CIE 1931 2° 관측자의 1 nm 표를 적분한다. 분모는 단위 응답의 Y=1을 만드는 정규화다. 광원은 3000 K와 6500 K Planck 스펙트럼이며, <b>6500 K Planck는 D65가 아니다.</b> [R14]")
add("표시 그림은 fixed exposure 0.7, chromatic adaptation 없이 생성했다. 합성 n(λ), κ(λ)로 계산한 색을 실크·면 등의 실제 색으로 부르지 않는다. 모니터의 color gamut, viewing adaptation과 실제 camera spectral sensitivity 교정도 이 실험에 포함되지 않았다.","SmallV3")
callout("VIS와 IR의 연결", "현재 외관 관측은 VIS에 직접 대응한다. IR은 별도 파장 범위의 유효 optical constants, source·detector와 실측 기준을 넣어야 한다. 같은 구조 엔진은 재사용할 수 있지만, VIS 파라미터나 CIE 관측자를 IR에 그대로 적용할 수는 없다.")

# 16: complete image panel.
title(16,"초기·평형 원단의 실제 분광 외관")
fig("figures/optical_v3/spectral_geometry_comparison.png","열: 두 반사 조명과 한 투과 조명. 행: 초기/평형 × 3000/6500 K Planck. 동일 노출을 유지한 실제 64×64 렌더의 관측자 적분이다. 4K 제품 사진이나 실물 validation은 아니며, 합성 기하·재료 조건에서 방향 반응의 변화를 확인하는 계산 fixture다.",maxh=622)

# 17: numerical findings and MC.
title(17,"핵심 결과: 반사는 분리, 투과는 미해결")
LIGHT_LABELS={'reflection_warp':'반사 0°','reflection_weft':'반사 90°','transmission_diag':'투과 45°'}
table(["조명","Planck","평균 Y 변화","절대 ΔY의 95% seed-paired 구간"],[
    [LIGHT_LABELS[d['light']],f"{d['temperature_kelvin']} K",f"{100*d['relative_mean_Y_change']:+.2f}%",f"[{d['xyz_interval']['interval_low'][1]:+.6f}, {d['xyz_interval']['interval_high'][1]:+.6f}]"] for d in OPT['paired_observation_comparisons']
],[75,71,97,FW-243])
add("원사 평형 뒤 재생성된 기하가 두 반사 조명에서 서로 반대 부호의 평균 응답을 만들었다. 투과 채널의 작은 변화는 현 Monte Carlo 예산에서 0과 구분되지 않는다. ‘모든 채널이 유효하다’는 해석은 이 결과와 맞지 않는다.")
fig("figures/optical_v3/spectral_response_uncertainty.png","파장별 반응과 독립 seed의 반복 불확실성. 픽셀이나 서로 연관된 파장을 독립 표본으로 세지 않았다.",maxh=266)
add("각 seed의 영상 평균 XYZ를 먼저 계산하고, 같은 seed를 전후 기하에 pairing해 4개 Δ값에 Student-t 95% 구간을 적용했다. 이 구간은 MC 재현성만 나타내며 실제 원단, 모델, calibration, mechanical grid와 spectral grid 오차를 포함하지 않는다. 4개 seed로 분포의 일반성까지 검증한 것은 아니다.","SmallV3")
add("이 영상 차이를 tangent만의 효과라고 부를 수도 없다. Family별 fiber 길이와 coverage가 함께 변하는 재생성 비교다. 다음 실험에서 material-coordinate 운반과 광학 sampling을 통제해야 인과적 설명을 더 좁힐 수 있다.","SmallV3")

# 18: error budgets and tests.
title(18,"오차 예산과 독립 리뷰")
table(["25 → 12.5 nm, 반사 0°","3000 K XYZ 차이","6500 K XYZ 차이"],[
    [label]+[f"{100*next(d['coarse_25nm_vs_fine_12p5nm_relative_XYZ_mean_error'] for d in OPT['spectral_12p5nm_refinement'] if d['state']==state and d['temperature_kelvin']==T):.5f}%" for T in (3000,6500)] for state,label in [('initial','초기'),('relaxed','평형')]
],[186,156,FW-342])
add("중간 파장을 실제 추가한 수렴 비교다. 12.5 nm도 참값이 아니고 파장별 MC noise가 남는다. 다른 두 조명은 저장된 파장에서 50/25 nm만 비교했다. 범위 밖 photopic source weight 약 4.1-4.5e-6은 광원·관측자의 적분량 진단이며, 임의의 누락 재료 응답까지 포함한 색 오차 상한은 아니다.","SmallV3")
lam=OPT['lambertian_radiometric_benchmark']
add(f"독립 100×100 면적 quadrature의 Lambertian center radiance {lam['expected_center_radiance']:.8f}와 renderer 중심 2×2 pixel 평균 {lam['rendered_center_block_mean']:.8f}의 상대 차이는 {100*lam['relative_error']:.5f}%였다. 관측계·정규화 검사이며 hair BSDF의 실물 정확도 검증은 아니다.","SmallV3")
sub("독립 리뷰가 발견하고 수정한 실제 결함")
table(["발견","수정 및 회귀"],[
    ["식별 불가능한 각도 fit가 success","weighted quadratic design rank < 6 거절; 반복·평면 방향 반례"],
    ["다른 높이/강성에 stale equilibrium 인증","problem 및 solved-height SHA binding; export에서 KKT 재계산"],
    ["slope 위반 상태의 잘못된 간격 인증","configured bound를 전제 충족 시에만 반환; 관측 slope 별도 보고"],
],[185,FW-185])
sub("현재 통합 테스트 기록")
status="전체 통과" if not TEST['failures'] and not TEST['errors'] else "실패 포함: 최종 원인 분석 필요"
add(f"<b>{TEST['tests_run']} tests / failures {TEST['failures']} / errors {TEST['errors']} / skipped {TEST['skipped']} · {status}</b>. 이 숫자는 generator 실행 시 data/final_test_summary.json에서 읽는다. 구현자 mechanics 17개·optical 20개와 별도 리뷰 12개를 포함하며, 최종 runner 테스트에 따라 총 개수는 늘어날 수 있다.")
add("검증은 scalar 에너지와 독립 미분, beam sine eigenmode, 차원 scaling, asymmetric family exchange, projection 가산성, SGGX 정규화·reciprocity, observer 적분, 실제 renderer 파장 갱신 등이다. 통합 실행에서 family-exchange 위치 오차가 기존 허용값을 넘은 사례를 재검토했다. E/gradient/Hessian의 좌표 교환 공변성을 추가 검사하고 solver stationarity를 1e-10으로 강화했다. 기존 위치 허용값을 유지한 채 오차가 4.77e-9에서 6.89e-11 mm로 줄었다. Test 개수 자체가 실물 검증 횟수는 아니다.","SmallV3")
citation_note("수치 근거 [D2-D4]. 테스트 소스 SHA와 실패 상세는 통합 JSON에 남긴다. 이전에 통과한 log가 이후 수정된 코드의 검증을 대신하지 않는다.")

# 19: research next step with external meta.
title(19,"다음 논문: 기하·재료 혼동을 푸는 관측")
callout("구체적인 가설", "직조의 slope/crimp 변화와 fiber roughness/흡수 변화가 좋은 RGB 기준계에서 혼동되는 경우, 소수의 추가 각도·각도-분광 관측이 미관측 조명의 외관 예측을 개선할 수 있는가? 이번 엔진은 그 가설을 시험할 입력과 기준 광학 계산을 준비했다.")
add("반응의 미분이 크다는 것만으로 좋은 측정이라고 판단하지 않는다. Brightness·roughness·흡수의 변화도 같은 관측 차이를 만들 수 있기 때문이다. Geometry θ<sub>g</sub>와 nuisance θ<sub>n</sub>를 구분하고, 선택한 잡음으로 whiten한 local Jacobian을 비교하는 진단을 후속으로 제안한다.")
equation(r"F_{g\mid n}=J_g^T(I-J_nJ_n^+)J_g",43)
add("Moore-Penrose inverse를 사용한 nuisance projection이며, 명시적인 local Gaussian noise model 아래의 정보 진단이다. 전역 inverse uniqueness를 보장하지 않는다. v0.3에서 이 Fisher 실험이나 최적 측정의 우위까지 계산한 것은 아니다.")
equation(r"y_m=\iint h_m(\lambda,\omega)L(\lambda,\omega;\theta)\,d\omega\,d\lambda+\epsilon_m",43)
table(["단계","실행할 일","필요한 판단 근거"],[
    ["1 · 모델 오차","실측 원사 높이·radius·장력·B와 synthetic family 비교","경계·slope·재료 좌표 운반 오차 분리"],
    ["2 · 광학 교정","한 소재·몇 직조의 R/T·각도·분광 기준 측정","실물과 새로운 조명에서 외관 오차"],
    ["3 · 측정 선택","강한 multi-light RGB와 같은 photon/time budget","nuisance를 통제한 추가 정보의 실제 이득"],
    ["4 · 메타광학","실현 가능한 hₘ, throughput·cross-talk를 포함","기존 렌즈/격자 대비 전체 시스템 장점"],
],[76,204,FW-280])
add("광원과 기존 detector 사이의 외부 메타광학을 대상으로 한다. 소자 두께만 줄이는 비교보다 relay·mount·sensor까지 포함한 부피, 촬영 수·시간, 광효율·노이즈를 보고해야 한다. IR은 독립 시편에서 VIS/RGB에 없는 정보를 주는지 검증한 뒤 붙인다. 염색·퇴색은 이 과정과 분리해 후속으로 유지한다.","SmallV3")

# 20: reproduce.
title(20,"실행·재현·버전 관리")
add(f"Private 연구 저장소: <link href='{REPO}' color='#31588a'>{REPO}</link><br/>v0.1 baseline과 v0.2 계층/bridge를 보존한 상태에서 v0.3 결과를 추가한다. 실제 원격 commit·tag·동기화 상태는 WORK_LOG와 GitHub history를 기준으로 확인한다.","SmallV3")
sub("계산 경로와 evidence audit를 구분")
code("# Existing evidence: no new mechanics or spectral renders\npython run_engine_v3.py --stages verify \\\n  --output data/engine_v3_runs/audit_001\n\n# New projection computation, no experiment image renders\npython run_engine_v3.py --stages optics verify --no-render \\\n  --output data/engine_v3_runs/projection_001\n\n# Full experiment; use a fresh output directory\nOPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \\\npython run_engine_v3.py --stages mechanics optics verify tests \\\n  --output data/engine_v3_runs/full_001")
add("--dry-run은 실행 계획을 출력하고 쓰기 작업을 하지 않는다. --input-data는 생략한 upstream 단계의 기존 자료 위치를 지정하며 기본은 data다. --no-render는 optical 실험의 image renders를 제외하지만, tests를 함께 지정하면 일부 작은 renderer unit test는 실행될 수 있다. 저장된 536회 렌더 결과를 no-render 실행 결과로 바꾸어 표시하지 않는다.","SmallV3")
table(["경로","담긴 내용"],[
    ["examples/mechanics/","재현 가능한 합성 원사·직조 설정"],
    ["data/mechanics_v3/","평형·전후 NPZ/JSON·sweep·refinement·binding audit"],
    ["data/optical_v3/","실제 raw radiance·fit 배열·scene·observer·metrics"],
    ["notes/*_v3.md","유도·문헌·독립 리뷰·구현 범위"],
    ["tests/test_*v3* / final_test_summary.json","독립 반례·통합 실행 결과와 소스 hash"],
    ["report/build_engine_v3_report.py","저장된 결과를 읽는 이 보고서 생성기"],
],[225,FW-225])
add("별도의 새 출력 폴더에서 mechanics → optics → verify를 --no-render로 실제 재실행했다. 단계별 시간은 25.31 / 3.69 / 2.60 s, image render 수는 0이다. 이 경로의 발췌 log·manifest·검사 결과는 data/validation_v3/no_render_integration/에 있다. 원래 536회 분광 렌더의 재실행으로 표시하지 않는다. 최종 source와 저장된 536회 결과의 hash·수치 일치는 data/engine_v3_final_artifact_audit/의 별도 audit로 확인한다.","SmallV3")
add("각 실험은 config/seed → source SHA → geometry audit → scene/export → raw 관측 → metrics/figure를 연결한다. 시작·종료 source hash를 비교해 실행 도중 코드 변경을 감지한다. 실패한 실행은 실패 상태와 사유를 남기며, 성공한 이전 run의 결과로 덮어 설명하지 않는다.","SmallV3")

# 21: bibliography, geometry/mechanics.
title(21,"1차 자료: 계층·구조·역학", "문헌의 읽은 범위와 구현/미구현 구분을 함께 보존한다.")
refs1=[
("[R1] Tang et al. FabricGen: Microstructure-Aware Woven Fabric Generation. CVPR 2026.","https://lxtyin.ac.cn/projects/fabricgen/","사용자 제공 본문 전체를 v0.2에서 검토. arXiv:2603.07240. Implicit geometry/appearance, network·dataset의 별도 범위를 확인했다."),
("[R2] Tang et al. Woven Fabric Capture with a Reflection-Transmission Photo Pair. SIGGRAPH 2024. DOI 10.1145/3641519.3657410.","https://arxiv.org/abs/2406.19398v3","사용자 제공 v3 본문·supplement, 공식 github.com/lxtyin/FabricBTDF-Recovery를 검토. 공식 코드 revision 67150eeca9f28b85f8fe21d40d888d34bd4d3b25, GPL-3.0. 전체 capture 재현은 아님."),
("[R3] Montazeri et al. A Practical Ply-Based Appearance Model of Woven Fabrics. TOG 2020. DOI 10.1145/3414685.3417777.","https://projects.shuangz.com/practical_cloth-sa20/practical_cloth-sa20-ld.pdf","§§3.1-3.3의 crossing, slope distribution과 ply appearance. v0.2 기술 검토를 유지했다."),
("[R4] Wang et al. Computation of Rotation Minimizing Frames. TOG 2008. DOI 10.1145/1330511.1330513.","https://www.microsoft.com/en-us/research/publication/computation-rotation-minimizing-frames/","Double-reflection RMF의 계층 기하 구현 근거. 해석적 helix 및 부모 호길이 convention과 함께 시험했다."),
("[R5] Bergou et al. Discrete Elastic Rods. TOG 2008. DOI 10.1145/1360612.1360662.","https://www.cs.columbia.edu/cg/pdfs/143-rods.pdf","저자 PDF 12쪽. §4.1-4.2의 framed curve, bending/twist, discrete curvature를 읽었다. v3 height-only solver와 full DER의 차이를 명시했다."),
("[R6] Wu et al. Weavecraft: An Interactive Design and Simulation Tool for 3D Weaving. TOG 2020. DOI 10.1145/3414685.3417865.","https://www.antequ.net/assets/projects/weavecraft/weavecraft.pdf","저자 PDF 16쪽. §§4-5 및 Appendix A를 확인. Ordered stacks, Leaf 기반 spline rods, strain balancing, 경계·압착 한계를 조사했다."),
("[R7] Leaf et al. Interactive Design of Periodic Yarn-Level Cloth Patterns. TOG 2018.","https://graphics.stanford.edu/projects/yarnsim/","저자 PDF 15쪽의 §§3-5, scale 및 부록 설명을 검토. 공식 pattern/control-point data는 재사용하지 않았다. GPU simulator 재현은 아님."),
("[R8] Li et al. Fiber-level Woven Fabric Capture. 2024 preprint / TOG 2026. DOI 10.1145/3816036.","https://www.rendering-zixuan.com/paper_pages/FiberFabric/","arXiv:2409.06368v1 §2.2에서 Tang R/T의 직접 인용과 fiber-level 결합 제안을 확인. 현재 저자 publication page도 확인했다."),
]
for head,url,note in refs1:
    add(f"<b>{escape(head)}</b><br/><link href='{url}' color='#31588a'>{escape(url)}</link><br/>{escape(note)}","RefV3")

# 22: bibliography optical + evidence provenance.
title(22,"1차 자료: 광학·관측·실행 근거")
refs2=[
("[R9] Heitz et al. The SGGX Microflake Distribution. TOG 2015.","https://research.nvidia.com/sites/default/files/pubs/2015-08_The-SGGX-microflake/sggx.pdf","저자 PDF 11쪽, §§3-5의 projected area, SPD/NDF와 filtering을 확인. 공식을 독립 구현했다."),
("[R10] Wang et al. SpongeCake: A Layered Microflake Surface Appearance Model. DOI 10.1145/3546940.","https://wangningbei.github.io/2022/SpongeCake.html","저자 preprint 17쪽의 §§3-4. 방향별 소광, phase, layer와 multiple-scattering 근사의 차이를 확인. full shader 미재현."),
("[R11] Yang et al. Real-time Woven Fabric Rendering Using SGGX Fitting. CVM 12(1):159-171, 2026. DOI 10.26599/CVM.2025.9450445.","https://www.sciopen.com/article/10.26599/CVM.2025.9450445?issn=2096-0433","Publisher abstract·날짜·license만 확인; full PDF·코드 미실행. Multi-SGGX와 footprint yarn NDF의 직접적인 선행 중복을 기록했다."),
("[R12] Yu et al. Realistic Cloth Rendering with a Ray-Wave Hybrid Shading Model. TOG 2025. DOI 10.1145/3763359.","https://blaire9989.github.io/assets/3_RayWaveFabric/project.html","사용자가 지정한 중심 참고 연구. Mean ray / wave variation / aperture diffraction의 구분을 유지한다. v3 광선 spectral sweep을 hybrid shader 재현으로 부르지 않는다."),
("[R13] Mitsuba 3.9.1 pinned implementation.","https://github.com/mitsuba-renderer/mitsuba3/tree/v3.9.1","hair.cpp, bsplinecurve.cpp, render/microflake.h convention을 확인. 실제 renderer 실행. Hair 모델은 물성 미교정 synthetic fiber에 적용했다."),
("[R14] CIE 2019, CIE 1931 2° colour-matching functions. DOI 10.25039/CIE.DS.xvudnb9b.","https://cie.co.at/datatable/cie-1931-colour-matching-functions-2-degree-observer","공식 1 nm CSV 원본 24,021 bytes. CC BY-SA 4.0 및 metadata를 data/optical_v3/cie/에 보존했다. CSV SHA-256: fa663e3535a7e0763a745993a1f0a192eb0275ac46ad2d1befd7626841e713c1."),
]
for head,url,note in refs2:
    add(f"<b>{escape(head)}</b><br/><link href='{url}' color='#31588a'>{escape(url)}</link><br/>{escape(note)}","RefV3")
sub("이 보고서의 실행 근거")
add("[D1] data/mechanics_v3/ 및 notes/weave_mechanics_v3.md.<br/>[D2] data/optical_v3/optical_scale_metrics.json 및 raw NPZ/PNG.<br/>[D3] notes/review_engine_v3.md와 tests/test_v3_independent_review.py.<br/>[D4] data/final_test_summary.json 및 대응 통합 테스트 log.","SmallV3")
add("[D1-D4]는 이 저장소의 합성 계산·수치 검사 결과다. 원문 PDF와 제3자 코드의 저작권은 각 권리자에게 있으며, 읽은 공식 코드를 새 모듈에 복사하지 않았다. 사용자 첨부 PDF는 별도 provenance/hash 기록으로 보존한다. 원저자 방법 전체의 실행과 본 엔진의 독립 구현을 구분했다.","CaptionV3")


def main():
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    doc=SimpleDocTemplate(str(OUTPUT),pagesize=A4,leftMargin=48,rightMargin=48,topMargin=40,bottomMargin=51,
        title="원사에서 직물까지: 원사 평형과 계층 기하의 분광 외관 v0.3.0",
        author="Textile Optics Engine research workspace",subject="실행한 v3 모델, 수학, 결과, 검증과 다음 연구 설계",pageCompression=1)
    doc.build(STORY,onFirstPage=footer,onLaterPages=footer)
    print(str(OUTPUT))
    print(json.dumps({"planned_pages":len(PAGE_TITLES),"version":VERSION,"tests_run":TEST['tests_run'],"failures":TEST['failures'],"errors":TEST['errors'],"figures_from_saved_artifacts":True},ensure_ascii=False))

if __name__=="__main__": main()
