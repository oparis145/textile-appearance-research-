"""Build the Korean research report from executed data, not mock outputs.

Additional document dependencies: reportlab==4.4.9, fonttools==4.61.1.
Set TEXTILE_REPORT_FONT_DIR to a folder containing NotoSansKR-400.ttf and
NotoSansKR-700.ttf, obtainable from the SIL-OFL Noto Sans Korean family.
The delivered PDF embeds the glyphs it uses; opening it needs no local font.
"""
from __future__ import annotations
import io
import json
import os
import re
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
from PIL import Image as PILImage
from matplotlib.mathtext import math_to_image
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, PageBreak,
                               Table, TableStyle, Image, KeepTogether)
from reportlab.graphics.shapes import Drawing, Rect, Line, Polygon, String

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "report"
FONT = Path(os.environ.get("TEXTILE_REPORT_FONT_DIR", ROOT.parent / ".report_fonts"))
pdfmetrics.registerFont(TTFont("KR", str(FONT / "NotoSansKR-400.ttf")))
pdfmetrics.registerFont(TTFont("KRB", str(FONT / "NotoSansKR-700.ttf")))
pdfmetrics.registerFontFamily("KR", normal="KR", bold="KRB", italic="KR", boldItalic="KRB")

INK = colors.HexColor("#182b3a")
TEAL = colors.HexColor("#087f8c")
BLUE = colors.HexColor("#31588a")
LIGHT = colors.HexColor("#edf4f7")
ORANGE = colors.HexColor("#a96213")
W, H = A4
FW = W - 96
S = getSampleStyleSheet()
S.add(ParagraphStyle("BodyKR", fontName="KR", fontSize=9.5, leading=15.0,
                     textColor=INK, spaceAfter=8, wordWrap="CJK"))
S.add(ParagraphStyle("SmallKR", parent=S["BodyKR"], fontSize=8, leading=11.6, spaceAfter=5))
S.add(ParagraphStyle("CaptionKR", parent=S["BodyKR"], fontSize=8, leading=11.5,
                     textColor=colors.HexColor("#50616e"), spaceAfter=10))
S.add(ParagraphStyle("H1KR", parent=S["BodyKR"], fontName="KRB", fontSize=21,
                     leading=29, spaceAfter=12))
S.add(ParagraphStyle("H2KR", parent=S["BodyKR"], fontName="KRB", fontSize=12.5,
                     leading=18, spaceBefore=7, spaceAfter=8, textColor=TEAL))
S.add(ParagraphStyle("Kicker", parent=S["BodyKR"], fontName="KRB", fontSize=9,
                     leading=14, textColor=TEAL, spaceAfter=8))
S.add(ParagraphStyle("CodeKR", parent=S["BodyKR"], fontName="Courier", fontSize=7.8,
                     leading=11.5, leftIndent=9, rightIndent=7, backColor=LIGHT,
                     borderPadding=8, spaceBefore=3, spaceAfter=9, wordWrap="LTR"))


def load(name):
    return json.loads((ROOT / "data" / name).read_text())


F = load("fabric_metrics.json")
B = load("fiber_wave_gaussian_beam_metrics.json")
M = load("meta_metrics.json")
V = load("render_validation_metrics.json")
TEST = load("final_test_summary.json") if (ROOT/"data/final_test_summary.json").exists() else {}
STORY = []


def p(text, style="BodyKR"):
    supers="⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻"
    text=re.sub("["+supers+"]+",lambda m:"<super>"+m.group().translate(str.maketrans(supers,"0123456789+-"))+"</super>",text)
    subs="₀₁₂₃₄₅₆₇₈₉ᵢₙₓ"
    text=re.sub("["+subs+"]+",lambda m:"<sub>"+m.group().translate(str.maketrans(subs,"0123456789inx"))+"</sub>",text)
    return Paragraph(text, S[style])


def add(text, style="BodyKR"):
    STORY.append(p(text, style))


def title(number, text, subtitle=None):
    if STORY:
        STORY.append(PageBreak())
    add(f"TEXTILE OPTICAL SIMULATION / {number}", "Kicker")
    add(text, "H1KR")
    if subtitle:
        add(subtitle, "CaptionKR")


def sub(text):
    add(text, "H2KR")


def table(headers, rows, widths=None, small=False):
    style = "SmallKR" if small else "BodyKR"
    cells = [[p(escape(str(x)).replace("\n", "<br/>"), style) for x in headers]]
    cells += [[p(escape(str(x)).replace("\n", "<br/>"), style) for x in row] for row in rows]
    t = Table(cells, colWidths=widths, hAlign="LEFT", repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
        ("TEXTCOLOR", (0, 0), (-1, 0), INK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, 0), .7, TEAL),
        ("LINEBELOW", (0, 1), (-1, -1), .25, colors.HexColor("#d8e2e8")),
    ]))
    STORY.extend([t, Spacer(1, 8)])


def fig(relative, caption, maxh=290, width=FW):
    path = ROOT / relative
    with PILImage.open(path) as a:
        iw, ih = a.size
    scale = min(width/iw, maxh/ih)
    STORY.append(Image(str(path), width=iw*scale, height=ih*scale, hAlign="CENTER"))
    STORY.append(Spacer(1, 5))
    add(caption, "CaptionKR")


def eq(expression, maxwidth=FW-10, maxheight=62):
    expression=re.sub(r"\\(mathbf|mathcal|boldsymbol|overline)\s*(\\[A-Za-z]+|[A-Za-z])",
                      lambda m: "\\"+m.group(1)+"{"+m.group(2)+"}", expression)
    stream = io.BytesIO()
    math_to_image("$" + expression + "$", stream, dpi=210, format="png", color="#182b3a")
    stream.seek(0)
    with PILImage.open(stream) as a:
        iw, ih = a.size
    stream.seek(0)
    scale = min(maxwidth/iw, maxheight/ih, .43)
    STORY.extend([Image(stream, width=iw*scale, height=ih*scale, hAlign="CENTER"), Spacer(1, 10)])


def code(lines):
    add("<br/>".join(escape(s).replace(" ", "&nbsp;") for s in lines), "CodeKR")


def flow():
    d = Drawing(FW, 308)
    nodes = {
        "p": (160, 267, 178, 31, ["통제 파라미터", "기하 · 굴절률 · 조명"]),
        "w": (0, 197, 149, 44, ["M1  2D Maxwell", "단일 · 묶음 · Gaussian beam"]),
        "r": (0, 115, 149, 43, ["M2  2D power rays", "Fresnel · 다중 경로"]),
        "s": (0, 32, 149, 42, ["M3  각도 분포 압축", "독립 ray 표본 검증"]),
        "g": (179, 197, 142, 44, ["M4  3D 섬유 · 직조", "연속 곡선 분리 인증"]),
        "v": (350, 197, 149, 44, ["M5  3D path tracing", "Chiang2016 BCSDF"]),
        "a": (179, 115, 142, 43, ["M6  binary gap → FFT", "직접 공극 회절"]),
        "c": (350, 115, 149, 43, ["M7  카메라 측정", "MTF · 픽셀 · 잡음"]),
        "d": (179, 32, 142, 42, ["M9  유한 각도 검출", "파동 · ray 차이와 잡음"]),
        "m": (350, 32, 149, 42, ["M8  외부 위상 pupil", "PSF → H · 별도 진단"]),
    }
    def arrow(x1,y1,x2,y2,dashed=False):
        line=Line(x1,y1,x2,y2,strokeColor=BLUE,strokeWidth=1.15)
        if dashed: line.strokeDashArray=[4,3]
        d.add(line)
        v=np.array([x2-x1,y2-y1],float);v/=np.linalg.norm(v)
        q=np.array([x2,y2])-6*v;side=np.array([-v[1],v[0]])*2.8
        d.add(Polygon([x2,y2,*(q+side),*(q-side)],fillColor=BLUE,strokeColor=BLUE))
    arrow(194,267,85,243);arrow(249,267,249,243);arrow(306,267,417,243)
    arrow(73,197,73,160,True);arrow(73,115,73,77)
    arrow(149,124,232,77)
    arrow(321,219,348,219);arrow(250,197,250,160);arrow(425,197,425,160)
    for key,(x,y,w,h,lines) in nodes.items():
        d.add(Rect(x,y,w,h,rx=5,ry=5,fillColor=LIGHT,strokeColor=colors.HexColor("#b9ceda"),strokeWidth=.7))
        for j,line in enumerate(lines):
            d.add(String(x+w/2,y+h-14-j*13,line,fontName="KRB" if j==0 else "KR",fontSize=8.1,textAnchor="middle",fillColor=INK))
    d.add(String(80,174,"동일 기하 비교",fontName="KR",fontSize=7,fillColor=BLUE))
    return d


title("01", "섬유에서 원단 영상까지\n광학 시뮬레이션 연구", "실행 결과와 수학·알고리즘·검증 기록 | 2026-10-10 | 염색·퇴색 제외")
add("<b>연구 목적</b>은 제품사진의 픽셀 수를 늘리는 것만으로 설명되지 않는 원단 외관 차이를, 섬유·직조의 광학 반응과 실제 관측 조건으로 나누어 이해하는 것이다. 이번 작업은 그 목적을 위한 실행 가능한 순방향 모델과 수치 검증 기반을 만들었다.")
sub("이번에 실제로 한 일")
add("원형 섬유의 정확한 2D 전자기 해, 같은 섬유 묶음의 광선 수송, Gaussian beam 조사, 각도 분포 압축, 명시적 섬유 기하, 세 직조의 3D 반사·역광 렌더, 직접 공극 회절, 카메라 MTF·픽셀·잡음, 이상적 외부 위상 pupil을 구현하고 실행했다. 모델별 원시 배열과 seed, 설정, 테스트, 독립 검산을 보존했다.")
table(["실행 결과", "이 결과가 말해 주는 것"], [
    ["동일 원단 재료 입력에서 평직·능직·수자직 영상 차이", "직조와 광원 방향을 분리한 통제 실험이 가능하다."],
    ["Gaussian beam 중심과 가장자리에서 다른 파동/광선 차이", "공간적 조사 위치와 방향 분포를 함께 평가해야 한다."],
    ["대칭 4초점 rank 2 → 비대칭 비교 설계 rank 4", "초점 수와 독립 정보 수는 같지 않다."],
    ["보존·수렴·기하·렌더·검출기 검산 및 실패 기록", "수치 정확도와 실물 검증을 구분할 기반을 확보했다."],
], [215, FW-215])
sub("현재 성과의 경계")
add("이는 <b>검증된 범위가 명시된 모듈들의 연구 프로토타입</b>이다. 정확한 2D Maxwell 해가 원단 3D BSDF에 직접 들어가는 통합 모델은 아니다. 실측 섬유 상수, 특정 실크·코튼·큐프라·린넨·혼방 피팅, 실제 카메라 보정, 제작된 메타표면, 촉감·역학·염색 공정은 검증하지 않았다. 이 경계를 숨기면 시뮬레이션의 정교함을 실물 재현성으로 잘못 해석하게 된다.")
add("수치 그림은 직접 계산한 결과다. 원단 path-tracing 영상의 무작위 grain에는 Monte Carlo 오차가 포함된다. 생성형 텍스처나 파동 speckle을 합성한 영상이 아니다.", "CaptionKR")

title("02", "모듈 구조와 실제 데이터 연결")
STORY.append(flow())
add("실선은 실행된 데이터 경로, 점선은 동일 기하에 대한 비교다. M6 회절 결과는 M5 영상에 더하지 않았다. M8은 외부 측정 광학의 독립 진단이다. Gaussian 파동/광선 분포를 유한 각도 검출기에 넣는 추가 분석은 M9에서 다룬다.", "CaptionKR")
table(["공유하는 것", "그대로 옮겨 쓰면 안 되는 것"], [
    ["굴절률·반지름·간격·조사 조건을 명시한 기준 실험", "2D 단면적을 3D 반사 확률로 취급"],
    ["동일한 실제 spline geometry를 렌더와 visibility에 사용", "공극 회절을 기존 직접 투과 위에 추가"],
    ["선형 radiance 배열을 카메라 단계로 전달", "표시용 PNG 밝기를 에너지로 적분"],
    ["비간섭 성분의 파장·각도별 검출 power", "위상 관계가 있는 성분을 독립 강도로 처리"],
], [222, FW-222], small=True)
add("최종 목표의 순방향식은 아래처럼 정의할 수 있다. θ는 직물 구조·광학 파라미터, L은 조명, F는 산란·렌더 모델, A는 카메라/외부 광학의 측정 연산자다. 이번에는 각 연산자의 일부와 연결 경계를 수치적으로 검토했다.")
eq(r"\mathbf y=\mathcal A_{\mathrm{optics,camera}}\!\left[\mathcal F(\boldsymbol\theta,L)\right]+\boldsymbol\epsilon")

title("03", "핵심 문헌과 구현 관계")
table(["원 연구·공개 자료", "이번 구현과의 관계"], [
    ["[1] Yu et al. 2025\nRay–Wave Hybrid Cloth", "좁은 beam, ply 평균 광선 응답, 파동 기반 변동, 공극 회절을 결합하는 구조를 검토했다. 논문 전체 구현을 재현하지 않았다."],
    ["[2] Xia et al. 2020\nWaveOpticsFiber / BEM", "파동 섬유 산란·단면적 개념과 공개 코드를 검토했다. 여기서는 원형 섬유의 독립 T-matrix 기준해를 구현했다. 원 코드 빌드는 하지 않았다."],
    ["[3] Chiang et al. 2016\nNear-field fiber BCSDF", "Mitsuba 3.9.1에 구현된 모델을 실제 3D 섬유 path tracing에 사용했다. 반지름 정규화된 흡수 경로를 원 소스로 확인했다."],
    ["[4] Tang et al. 2024\nReflection–Transmission Photo Pair", "반사·투과를 함께 사용하는 coarse appearance/역추정 비교군으로 검토했다. 학습·실물 복원은 실행하지 않았다."],
    ["[5] MetaSpectra+ 2026", "실제 다층·분산 설계가 단순 다초점 phase pupil과 다름을 검토했다. 소자·재구성 네트워크 재현은 하지 않았다."],
], [172, FW-172])
sub("문헌을 읽고 선택한 구현 원칙")
add("Yu 논문이 다루는 전체 3D 모델에는 fitted angular kernels, ply 간 수송, 파동으로 보정한 구조적 변동과 local aperture 모델이 포함된다. 이번 계산은 이 모든 단계를 임의의 혼합 비율로 잇는 대신, 독립 검산 가능한 수준별 기준 모델을 만들고 어느 조건에서 차이가 남는지 확인한다. [1]")
add("비원형·비스듬한 실제 섬유까지 확장하려면 BEM이나 적절한 full-wave/physical-optics 해법이 필요하다. 원형·평행 섬유 해는 이 확장의 신뢰할 수 있는 기준 문제 역할을 한다. [2, 6]")
add("논문 PDF와 저장소의 읽은 범위·미실행 항목은 notes/ray_wave_literature.md 및 notes/meta_optics.md에 기록했다. 저자들의 결과와 이번 수치를 같은 실험의 재현값으로 비교하지 않는다.", "CaptionKR")

title("04", "M1 — 단일 섬유 Maxwell 모델")
add("섬유는 z축으로 무한한 원형·등방·비자성 유전체다. 주변 굴절률은 1, 시간 의존성은 exp(−iωt), outgoing field는 Hankel 1종을 사용한다. 수동 굴절률은 m=n+iκ, κ≥0이다. Ez와 Hz를 구분해 TE/TM 명칭의 혼선을 피한다. 길이와 단면적 단위는 μm이다.")
eq(r"u_i=e^{ikr\cos(\phi-\alpha)}=\sum_{n=-\infty}^{\infty}i^n e^{-in\alpha}J_n(kr)e^{in\phi}")
add("x=ka, k=2π/λ라 두면, 내부장과 외부장의 경계 연속 조건으로 모드별 산란 계수 tₙ를 구한다. Ez에서는 γ=m, Hz에서는 γ=1/m이며, 후자의 미분 경계 조건에는 유전율 역수가 들어간다.")
eq(r"t_n=\frac{\gamma J'_n(mx)J_n(x)-J'_n(x)J_n(mx)}{H_n^{(1)\prime}(x)J_n(mx)-\gamma H_n^{(1)}(x)J'_n(mx)}")
eq(r"C_{\rm sca}=\frac{4}{k}\sum_n|t_n|^2,\quad C_{\rm ext}=-\frac{4}{k}\Re\sum_n t_n,\quad C_{\rm abs}=C_{\rm ext}-C_{\rm sca}")
add("이 부호는 현재 tₙ 정의와 연결된다. 산란 단면적은 단위 축 길이당 μm이며 무차원 반사율이 아니다. 산란 단면적이 기하학적 폭보다 커도 곧바로 에너지 위반은 아니다. 전방의 입사장–산란장 간섭이 extinction에 포함되기 때문이다.")
sub("수치 검증")
table(["검사", "실행한 기준"], [
    ["작은 입자 한계", "Ez/Hz 각각의 독립 Rayleigh 점근식"],
    ["경계 조건", "실제 복소장 및 가중 법선 미분의 연속성"],
    ["전력과 수동성", "각도 적분 Csca, optical theorem Cext, 흡수 비교"],
    ["x = 0.01~150, 100점", "두 편광에서 무손실 최대 보존 상대 잔차 5.81×10⁻¹³"],
], [175, FW-175], small=True)
add("비원형 단면, 복굴절, 섬유 표면 거칠기, 유한 길이, 기울어진 입사와 실제 n(λ)는 현재 기준해 밖이다. 광학 크기 x를 바꾸는 실험은 파장 효과를 검토할 수 있지만, 고정 합성 굴절률을 실제 IR 섬유 상수로 해석해서는 안 된다.", "CaptionKR")

title("05", "M1 — 섬유 묶음의 다중 파동 결합")
add("각 원통의 outgoing Hankel 모드를 다른 원통의 regular Bessel 모드로 Graf translation하여 결합 선형계를 푼다. 단일 섬유 강도를 단순 합산하지 않으므로 반복 전자기 상호작용이 포함된다. 높은 모드의 동적 범위를 줄이기 위해 표면 Hankel 값으로 미지수를 스케일하며, 이는 정칙한 변수 변환이지 손실이나 정규화가 아니다.")
eq(r"b_{jn}=t_{jn}\left[c^{\rm inc}_{jn}+\sum_{\ell\ne j}\sum_m G_{jn,\ell m}b_{\ell m}\right]")
eq(r"G_{jn,\ell m}=H_{m-n}^{(1)}(k|\mathbf c_j-\mathbf c_\ell|)e^{i(m-n)\beta_{j\ell}}")
fig("data/fiber_wave_cluster_field.png", "실제로 계산한 작은 7개 원통 묶음의 복소장. |Ez|²는 전기장 한 성분의 크기 제곱이며 전체 전자기 에너지 밀도와 동일하지 않다.", maxh=285)
add("<b>리뷰에서 얻은 중요한 반례:</b> 낮은 모드 차수 N=4는 에너지 잔차가 약 3.4×10⁻¹⁷인데도 수렴한 각도 분포와 상대 L2 차이가 7.42%였다. 따라서 보존만 확인하면 부족하다. N=14에서는 같은 지표가 약 5.54×10⁻¹²로 줄었다.")
add("독립 검산은 Graf 항을 직접 공간장에서 확인하고, 내부 Joule 흡수 체적 적분을 경계 flux 및 전역 Cext−Csca와 비교했다. 또한 좌표 이동·회전·상반성·모든 길이의 스케일 변화에 대한 응답을 확인했다. 상세식과 테스트는 notes/fiber_wave.md 및 review_wave_module.md에 있다.", "CaptionKR")

title("06", "M2 — 광선으로 섬유 묶음의 전력 수송")
add("원형 섬유와 ray의 정확한 양의 교차를 찾고, 각 경계에서 Fresnel 반사/굴절을 표본화한다. 광선은 power를 운반한다. 방사휘도 Jacobian용 η²를 추가로 곱하지 않는다. 비편광 입력은 Ez/Hz를 동등 확률로 뽑되 경로 전체에서 선택한 편광을 유지한다.")
eq(r"R_s=\left(\frac{n_i c_i-n_t c_t}{n_i c_i+n_t c_t}\right)^2,\qquad R_p=\left(\frac{n_t c_i-n_i c_t}{n_t c_i+n_i c_t}\right)^2")
eq(r"w'=w e^{-\mu_a\ell},\qquad 1=R+T_{\rm hit}+T_{\rm direct}+A+E_{\rm residual}")
add("흡수는 내부 chord 길이에 따른 Beer 감쇠로 누적하고, 최대 교차 횟수에 도달한 잔여 power와 수치 실패를 별도로 기록한다. 이를 투과에 강제로 넣거나 합계 1에 맞추지 않는다.")
table(["합성 묶음", "후방 R", "전방 합계 T", "조건"], [
    ["1 fiber", "0.08590", "0.91410", "a=5 μm, n=1.55"],
    ["7 fibers", "0.19490", "0.80510", "gap=0.4 μm"],
    ["19 fibers", "0.27929", "0.72071", "무손실, 비편광"],
    ["19 fibers + 고정 흡수", "0.15058", "0.35220", "μa=0.02 μm⁻¹, A=0.49722"],
], [105,78,94,FW-277], small=True)
add("묶음별 입사 beam 폭은 해당 기하의 투영 폭이므로 서로 다른 실험의 R은 각자의 입사 power로 정규화된다. 위 표는 특정 실제 원단의 반사율 표가 아니다.", "CaptionKR")
sub("다른 알고리즘으로 확인")
add("단일 원통은 교차 코드를 쓰지 않는 Debye 경로별 굴절각·가중치 적분과 비교했다. 20만 ray에서 CDF 최대 차이는 Ez 0.001314, Hz 0.001934, 비편광 0.002389였다. 32개 seed의 2천/1만/5만 ray 실험에서 실제 표본 산포가 1/√N 크기와 보고한 표준오차에 일치하는지 확인했다.")
add("이 모듈의 전체 기준 실험은 3,784,000 incident rays와 독립 결정론적 경로 적분을 포함한다. 별도의 Gaussian 비교에서는 1,500,000 rays를 계산했다.", "CaptionKR")

title("07", "같은 기하에서 파동과 광선을 비교")
add("반지름 5 μm, 간격 0.4 μm, n=1.55의 7개 원통으로 두 모델을 맞췄다. 450/550/650 nm와 정규 배열+두 개의 미세 위치 교란을 비교했다. 파동 단면적과 ray가 만난 출사 power의 전방 정의가 다르므로, 전방 ±6°를 제외한 동일 2° 구간에서 절대 각도 단면적을 비교했다.")
fig("data/fiber_wave_textile_matched.png", "각도 밀도를 임의로 같게 정규화하지 않았다. 파동의 미세 구조와 ray의 차이가 평균 후에도 일부 남는다. 이 그림은 지정된 3×3 합성 ensemble의 비교다.", maxh=360)
table(["지표", "Ez", "Hz"], [
    ["전방 제외 각도 분포 상대 L2", "0.5064", "0.5465"],
    ["파동 후방 단면적 [μm]", "7.3946", "5.3872"],
    ["ray 후방 단면적 [μm]", "6.8365", "4.0948"],
    ["ray 후방 상대 차이", "−7.55%", "−23.99%"],
], [259,120,FW-379], small=True)
add("18개 파동 조건 모두에 모드 수렴 gate를 적용했다. 최대 angular L2 변화는 9.19×10⁻⁸ 이하였다. 따라서 위 큰 차이를 원통 모드 차수 부족으로 설명하기 어렵다. 다만 이 실험은 저자의 Gaussian beam·다수 instance·twisted ply 조건과 다르므로 원 논문 평균 일치 결과의 반증으로 해석하지 않는다. [1]", "CaptionKR")

title("08", "Gaussian beam — 유한 입사 전력의 기준")
add("무한 평면파 단면적 비교를 보완하기 위해 전방 전파 angular spectrum의 복소 진폭을 합친 Gaussian beam을 구현했다. 진폭의 1/e 반지름 w₀=10 μm이며, 대응하는 paraxial ray irradiance 표준편차는 5 μm다. 파동은 약 0.50° rms 각도 발산을 포함하지만 비교 ray는 평행하다는 차이도 남긴다.")
eq(r"u_i(x,y)=\int_{-k}^{k}\frac{dq}{2\pi}A(q)e^{i[k_x(x-x_0)+q(y-y_0)]},\quad k_x=\sqrt{k^2-q^2}")
eq(r"A(q)=\sqrt{\pi}w_0e^{-w_0^2q^2/4},\qquad P_i=\int_{-k}^{k}\frac{dq}{2\pi}\frac{k_x}{k}|A(q)|^2")
add("kₓ/k는 x방향 Poynting flux에 필요하다. 550 nm에서 Pᵢ=12.5326611749 μm인 정규화 flux를 얻었고, 다른 x평면의 수치 Poynting 선적분과 독립 비교했다.")
eq(r"R=\frac{P_{\rm backward}}{P_i},\qquad A=\frac{P_{\rm local\ absorption}}{P_i},\qquad T=1-R-A")
add("여기서 T는 전방의 입사장–산란장 간섭을 포함하는 보존식으로 산출한다. forward scattered power를 T라 부르지 않는다. 따라서 R+T+A=1은 이 T 정의상 자동 성립하며, 이를 별도의 독립 보존 테스트로 세지 않았다.")
table(["실제로 발견한 수치 실패", "수정·확인"], [
    ["source quadrature 24점에서 가짜 tail power 약 4.62%", "48/64/96점, 두 선적분 평면에서 수렴"],
    ["backward 적분 256점에서 중앙 Ez R 약 1.95% 차이", "512→1024점에서 ≤2.75×10⁻¹⁴ 상대 변화"],
    ["7개 광학 크기 원통의 모드 truncation", "N=91→99에서 각도 L2 변화 ≤4.94×10⁻¹⁰"],
], [264,FW-264], small=True)

title("09", "빔 위치와 ‘총광량 대 각도’의 차이")
rows=[]
for r in B["cases"]:
    rows.append([r["polarization"], f'{r["offset_um"]:.0f}', f'{r["R_wave"]:.6f}', f'{r["R_ray"]:.6f}', f'{100*r["R_ray_relative_discrepancy"]:+.2f}%'])
table(["편광", "y₀ [μm]", "파동 R", "ray R", "ray 상대 차이"], rows, [56,74,106,106,FW-342], small=True)
add("각 조건 250,000 rays이며 R의 Monte Carlo 표준오차는 0.000626~0.000887이다. 중앙 Ez/Hz의 R 차이는 각각 2.12/2.91 표준오차다. 표의 소수 자릿수 전체가 통계적 정밀도를 뜻하지 않는다.","CaptionKR")
fig("data/fiber_wave_gaussian_backward_profiles.png", "같은 2° backward angular bins. 총 R이 가까운 중앙 beam에서도 각도 분포는 상당히 다르다. 이 결과는 coherent monochromatic 실험이며 보통 조명에서의 가시성은 별도 관측 연산자를 적용해야 한다.", maxh=315)
add("중앙에서는 총 R의 차이가 Ez 0.70%, Hz 1.35%였지만 각도 분포 상대 L2는 각각 0.481, 0.543이었다. 빔을 y₀=10 μm로 옮기면 총 R 차이도 −7.01%, −14.60%로 커졌다. <b>전체 반사량의 일치는 광택의 방향 분포 일치를 보장하지 않는다.</b>")
add("따라서 모델 선택은 총 반사율 하나로 판단하지 않고, 실제 광원·검출기의 평균을 거친 각도 신호와 잡음 수준에서 평가해야 한다. 이것은 이번 계산에서 도출한 연구 방향이며 실물에 대한 검증 결과는 아니다.", "CaptionKR")

title("10", "M3 — 각도 분포를 압축하는 모델")
add("유한 ray 표본에서 얻은 2D 각도 밀도를 비음수 von Mises 혼합으로 맞췄다. 혼합 가중치와 각 성분은 정규화되며, 직접 forward delta·흡수·잔여 power는 별도 항으로 남긴다. 밀도 fitting 때문에 총 power가 바뀌지 않는다.")
eq(r"q(\theta)=\sum_{j=1}^{K}\pi_j\frac{e^{\kappa_j\cos(\theta-\mu_j)}}{2\pi I_0(\kappa_j)},\quad \pi_j\geq0,\quad\sum_j\pi_j=1")
fig("data/ply_ray_surrogate_overview.png", "같은 기하에서 학습 20만 ray와 검증 20만 ray를 독립 seed로 생성했다. 각도 오차와 두 원시 histogram 사이의 유한 표본 차이를 함께 표시했다.", maxh=235)
table(["성분 수 K", "검증 JS [nats]", "검증 CDF 최대 차이", "예측 후방 power"], [
    [1,"0.069657","0.120204","0.250316"],
    [4,"0.009175","0.012457","0.281836"],
    [8,"0.006100","0.004676","0.275226"],
    [16,"0.004059","0.004740","0.279455"],
], [78,129,150,FW-357], small=True)
add("검증 ray의 후방 power는 0.278745이다. 두 독립 원시 histogram의 JS는 0.000452로, fitting 오차는 여전히 유한 표본 기준보다 크다. 4/8/16 성분은 설정한 600회 반복 한도에 도달했다. 수렴이나 전역 최적점을 얻었다고 주장하지 않는다.")
add("이 모델은 압축 효율을 보기 위한 2D 확률 밀도이며 3D BSDF가 아니다. 원 논문의 ASG 모델, incident-angle block joint fitting, wave-calibrated fluctuations와 구분한다. [1]", "CaptionKR")

title("11", "M4 — 섬유·실·직조의 실제 3D 기하")
add("실 중심선 c(s)에 회전 최소화 프레임 u(s), v(s)를 만들고, ply와 fiber를 그 프레임에서 감는다. Frenet frame의 곡률 0 특이점을 피했다. 직조 행렬의 over/under 높이는 C¹ smoothstep으로 연결하며 실제 렌더는 cubic B-spline 섬유를 교차한다.")
eq(r"\mathbf p_f(s)=\mathbf c_p(s)+q_u(s)\mathbf u_p(s)+q_v(s)\mathbf v_p(s),\quad \phi_f(s)=2\pi\tau_f s")
fig("figures/fabric_geometry.png", "같은 섬유 packing으로 평직, balanced 2/2 능직, 5-end 4/1 warp-faced 수자직을 만들었다. 그림 아래는 각 yarn의 실제 37개 fiber 중심선이다.", maxh=300)
table(["기하 입력", "실행 값"], [
    ["각 방향 yarn / 총 섬유", "10 + 10 yarns / 740 fibers"],
    ["섬유 반지름 / yarn pitch", "4 μm / 200 μm"],
    ["packing·twist", "37 fibers/yarn, 횡단 타원 scale 1.35/0.60, fiber twist 0.7/mm"],
    ["spline controls / patch 폭", "196,100 / 2 mm"],
], [193,FW-193], small=True)
add("현재 기준 렌더는 1-ply yarn이다. 코드는 2/3-ply 기하 입력도 지원하지만 그 전체 원단 광학 결과를 기준 실험으로 실행하지 않았다. 같은 평면에서의 분리 조건은 필요한 사전 검사이며, 3D 곡선의 실제 분리 인증을 대체하지 않는다.", "CaptionKR")

title("12", "기하 리뷰 — 교차 높이만 맞으면 충분한가?")
add("초기 packing에서는 warp/weft의 over-under 순서를 맞췄는데도 교차점 사이의 비스듬한 섬유가 겹쳤다. 접촉이 없는 유전체 fiber BSDF를 사용하면서 기하가 겹치면 산란 모델 자체와 일치하지 않는다. 이를 그림의 흠으로 취급하지 않고 실제 기하 오류로 고쳤다.")
sub("연속 B-spline의 보수적 분리 인증")
add("각 cubic B-spline segment를 cubic Bézier control points로 바꾼다. 곡선이 control hull 안에 있다는 성질을 이용해 endpoint chord 주위의 capsule 반지름을 늘려 곡선 전체를 감싼다. 두 capsule의 하한 거리가 양수이면 그 안의 서로 다른 섬유 표면도 분리된다. KD-tree 검색에서 생략한 쌍에도 삼각부등식에 따른 거리 하한을 적용했다.")
eq(r"d_{\rm surface}\geq d(\overline{P_0P_3},\overline{Q_0Q_3})-(a_P+e_P)-(a_Q+e_Q)")
table(["직조", "최소 표면 간격 하한", "검사 segment 수", "미해결 쌍"], [
    [name.capitalize(), f'{1000*F["geometry"][name]["clearance_certificate"]["minimum_clearance_lower_bound_mm"]:.4f} μm',
     f'{F["geometry"][name]["clearance_certificate"]["segments"]:,}', "0"] for name in ("plain","twill","satin")
], [88,161,145,FW-394], small=True)
add("모든 서로 다른 fiber 쌍을 대상으로 한 보수적 certificate이며, 같은 fiber의 자기 교차까지 포함한 증명은 아니다. 초기 곡선의 수치 샘플링만으로 연속 기하를 검증했다고 주장하지 않는다.")
sub("독립 검산")
add("segment–segment 거리를 별도의 bounded least-squares 풀이와 250개 쌍에서 비교해 최대 3.62×10⁻¹² mm 차이를 확인했다. B-spline→Bézier 항등식은 5.55×10⁻¹⁷ mm 수준에서 일치했다. 다만 실제 제조 과정의 장력·압축·변형이나 접촉력을 푼 것은 아니다.")
add("이 모듈은 ‘가능한 통제 기하’를 제공한다. 실물 모델로 바꾸려면 현미경/단면/3D 측정으로 fiber packing·flattening·twist·hairiness를 검증해야 한다.", "CaptionKR")

title("13", "M5 — 세 직조의 실제 광선 렌더")
fig("figures/fabric_contact_sheet.png", "행: 평직·능직·수자직. 열: 앞쪽 광원 방위 0°·90°·뒤쪽 diffuse hemisphere. 256²×192 spp, 동일 n=1.55·μa=2 mm⁻¹·roughness·표시 exposure=0.5. 밝기 grain은 유한 Monte Carlo 오차를 포함한다.", maxh=479)
rows=[]
for name in ("plain","twill","satin"):
    a=F["renders"][name+"_front_x"]["mean_linear"]
    b=F["renders"][name+"_front_y"]["mean_linear"]
    rows.append([name,f"{a:.5f}",f"{b:.5f}",f"{a/b:.3f}"])
table(["직조", "front 0° 평균", "front 90° 평균", "0°/90°"], rows, [84,145,145,FW-374], small=True)
add("이 평균은 카메라의 선형 radiance 평균이지 반구 R/T가 아니다. 수자직의 두 조명 응답 비 1.368은 이 합성 기하와 두 조명에서 계산한 값이며 모든 수자직의 고유 상수가 아니다.", "CaptionKR")

title("14", "M5 검증 — 경로 깊이와 furnace")
add("3D 모델은 Chiang2016의 near-field dielectric fiber BCSDF를 실제 곡선 기하와 결합했다. 내부 섬유 경로를 효율적으로 집약하는 ray 근사이며 전자기 위상을 추적하지 않는다. Mitsuba 3.9.1의 원 소스에서 내부 chord가 반지름 단위로 정규화되어 있음을 확인해 σa(shader)=μa×radius로 입력했다. [3, 7]")
vg=V.get("furnace_depth_groups", {})
rows=[]
for depth in (2,4,8,16,32,-1):
    g=vg.get(str(depth),{})
    rows.append(["unlimited" if depth==-1 else str(depth), f'{g.get("fully_covered_mean",float("nan")):.6f}', str(g.get("n_seeds","진행 로그 참조"))])
table(["최대 경로 깊이", "16개 subpixel rays가 모두 hit한 픽셀 평균", "seed 수"], rows, [122,264,FW-386], small=True)
add("무손실 원단을 radiance=1의 균일 환경으로 둘러싼 white furnace에서 가려진 영역도 1에 가까워야 한다. 여기서 covered는 4×4 subpixel camera rays 16개가 모두 fiber에 hit한 6,574개 픽셀을 뜻한다. 이는 연속 pixel 면적의 coverage 인증이 아니다. 얕은 경로 깊이는 다중 산란을 누락한다. 기준 렌더는 max_depth=−1과 Russian roulette를 사용한다.")
g=vg.get("-1",{})
add(f'무제한에서 전체 평균은 {g.get("full_mean",float("nan")):.6f}, 위 covered mask 평균은 {g.get("fully_covered_mean",float("nan")):.6f}였다. 후자의 seed 표준오차는 {g.get("fully_covered_mean_seed_se",float("nan")):.6f}다. 약 0.14%의 deficit은 이 표준오차보다 크므로 ‘수치적으로 정확히 1’ 또는 ‘오직 MC 오차’라고 부르지 않는다. 원인별 잔차 분해는 남아 있다.')
add("별도의 실제 앞조명 96² 영상에서 64/256/1024 spp의 독립 2048 spp 기준 대비 pixel RMSE는 0.20472/0.10566/0.06235였다. variance×spp는 2.5707/2.5185/2.6279로 1/N 분산 감소를 지지한다. 기준 영상 자체에도 잡음이 있어 그 분산을 비교식에 포함했다. 수렴을 확인했어도 낮은 spp 영상을 무잡음 ground truth로 쓰면 안 된다.","SmallKR")
if (ROOT/"data/render_validation_overview.png").exists():
    fig("data/render_validation_overview.png", "35개 실제 렌더 case의 검증 기록. covered는 16점 ray mask이며 기하의 continuous spline separation certificate와 다른 검사다. 큰 원본 그림과 잔차는 data에 보존했다.", maxh=157)

title("15", "M6 — 공극의 회절과 광원 평균")
add("실제 spline geometry에 normal rays를 쏘아 열린 pixel을 1, 막힌 pixel을 0으로 한 binary mask를 만들었다. 이를 두께 0의 불투명 aperture로 취급해 Fraunhofer FFT를 계산한다. 섬유를 통과한 위상·흡수·굴절은 이 성분에 포함되지 않는다.")
eq(r"U(f_x,f_y)=\mathcal F\{a(x,y)u_i(x,y)\},\qquad P_j\propto |U_j|^2")
add("FFT와 incident field의 이산 norm으로 power를 정규화해 point-source 전력 합이 열린 공극의 투과 power가 되게 했다. 서로 독립인 λ와 광원 위치는 intensity로 평균한다. source Gaussian blur는 소각·고정 마스크 근사이며, 두꺼운 원단의 각도별 silhouette 변화를 다시 교차 계산한 것은 아니다.")
fig("data/aperture_gap_source_sweep.png", "유한 마스크 회절의 광원 크기 평균. 이는 직접 공극 성분에 대한 계산이며 실제 원단 전체 투과율이나 보통 조명의 사진 자체가 아니다.", maxh=245)
table(["이상화 정사각 공극 폭", "직접 T", "±0.5° 원뿔 내 / T, 점광원", "같은 값, 광원 σ=1°"], [
    ["10 μm", "0.00610", "8.039%", "4.585%"],
    ["30 μm", "0.05493", "50.016%", "8.922%"],
    ["80 μm", "0.39063", "84.473%", "10.642%"],
], [96,76,177,FW-349], small=True)
add("이 표는 pitch 128 μm, 세 파장 동등 power의 이상화 구멍 배열이다. 실제 세 기하의 projected open fraction은 각각 약 0.14256, 0.15370, 0.15453이었다. 합성 섬유를 통해 나오는 빛은 이 비율에 포함되지 않는다.")
sub("향후 ray–wave 결합의 에너지 조건")
eq(r"K_{\rm hybrid}=K_{\rm ray}-T_{\rm direct}\delta(\omega-\omega_i)+G_{\rm gap},\quad \int G_{\rm gap}\,d\omega=T_{\rm direct}")
add("현재는 위 교체를 3D renderer에 구현하지 않고 공극 결과를 별도로 저장했다. 기존 직접 ray 투과에 회절을 추가하면 같은 power를 두 번 계산하게 된다.", "CaptionKR")

title("16", "M7 — 4K보다 먼저 명시할 광학 조건")
add("카메라 모듈은 선형 radiance에 원형 pupil의 incoherent OTF를 적용하고, pixel 면적 평균 후 Poisson shot noise와 read noise를 추가한다. 실제 렌즈 PSF/QE를 피팅한 카메라가 아니라 해석적으로 검산 가능한 측정 모델이다.")
eq(r"H(\nu)=\frac{2}{\pi}\left[\cos^{-1}\nu-\nu\sqrt{1-\nu^2}\right],\quad \nu=\frac{f}{2\mathrm{NA}/\lambda},\quad 0\leq\nu<1")
eq(r"\mu_j=g A_j\overline L_j,\qquad Y_j\sim\mathrm{Poisson}(\mu_j)+\mathcal N(0,\sigma_r^2)")
fig("figures/camera_comparison.png", "같은 0.8 mm field의 실제 macro render에서 재계산. μm/pixel은 물체면 환산값이며 NA 비교는 수집 후 검출 광자 밀도를 맞춘 조건이다. 실제 고정 노출 NA² throughput은 자동 적용하지 않는다.", maxh=352)
add("같은 512×512 grid에서도 NA 0.02/0.04/0.08의 optical cutoff는 0.0727/0.1455/0.2909 μm⁻¹로 다르다. 공간 해상도는 pixel 개수뿐 아니라 field of view, NA, 파장, 광량과 함께 정해야 한다. 반면 angular response와 재조명 정보는 단일 spatial grid를 촘촘히 만드는 것만으로 측정되지 않는다.")
add("큰 effective pixel은 전자를 더 모아 추가 검출기 잡음을 줄이지만 미세 구조를 평균한다. read noise는 최종 pixel당 한 번이므로 이는 pre-read 집계/큰 pixel 모델이며, 이미 읽은 작은 pixel의 단순 software binning과 다르다.", "CaptionKR")

title("17", "M7 검증과 카메라 해석의 한계")
table(["검증", "실행 결과 / 해석"], [
    ["MTF 독립 계산", "원형 pupil overlap의 기하 적분과 일치; 회전 grating과 box pixel response도 비교"],
    ["입사·검출 광자 예산", "동일 물체면 영역, bin1/2/4에서 총 기대 전자 수 일치"],
    ["64개 독립 seed 분산", "예측 대비 약 1.00055 / 1.00012 / 0.99785"],
    ["검은 입력", "read noise의 음수 추정값을 유지해 black-level clipping bias 방지"],
    ["Full well", "포화 전 분석 분산과 포화 후 실제 분산을 구분; 기본 6개 조건은 포화 0"],
    ["실제 macro FFT padding", "pad32→128 상대 L2: NA 0.02에서 0.171%, NA 0.08에서 0.0401%"],
], [178,FW-178], small=True)
sub("출력 sampling은 따로 확인")
table(["NA 0.04", "출력 pitch", "출력 Nyquist", "cutoff 0.14545 대비"], [
    ["bin1", "1.5625 μm", "0.320 μm⁻¹", "높음"],
    ["bin2", "3.125 μm", "0.160 μm⁻¹", "높음"],
    ["bin4", "6.25 μm", "0.080 μm⁻¹", "낮음; aliasing 가능"],
    ["bin8", "12.5 μm", "0.040 μm⁻¹", "낮음; aliasing 가능"],
], [80,121,135,FW-336], small=True)
add("입력 512 grid가 cutoff를 표본화한다는 부등식은 최종 grid가 alias-free임을 뜻하지 않는다. 또한 입력 렌더 자체가 box pixel 적분과 유한 MC 표본을 거쳤다. 따라서 저장된 noiseless는 ‘추가 detector noise 이전’이고, 연속 장면의 정확한 무잡음 기준 영상은 아니다.")
add("보고한 noise RMSE 0.05989→0.02602→0.01248→0.00617은 각 출력의 blurred/binned 기준 대비 추가 잡음이다. 낮은 RMSE가 손실된 texture의 복원이나 실물 재현 개선을 뜻하지 않는다. 색이 없는 입력의 RGB noise가 만든 유색 grain을 염료 스펙트럼으로 읽어서는 안 된다.")

title("18", "M8 — 이상적 외부 pupil의 측정 시뮬레이션")
add("메타표면 제작을 대신했다고 주장하지 않으면서 측정 기능을 시험하기 위해, 지름 50 μm·f=250 μm의 phase-only pupil을 정의했다. 550 nm에서 설계한 위상을 파장에 독립적으로 유지한다고 가정하고, 450/550/650 nm와 x축 −1/0/+1° 입사에 대해 복소장을 전파했다. η=0.8은 임의의 전달 손실이다.")
eq(r"t(x,y)=\sqrt{\eta}\,P(x,y)e^{i\phi(x,y)},\qquad U_z=\mathcal F^{-1}\!\left[\mathcal F\{U_0t\}e^{-i\pi\lambda z(f_x^2+f_y^2)}\right]")
eq(r"H_{iq}=\int_{\Omega_i}|U_z^{(q)}|^2\,dA,\qquad \mathbf y=H\mathbf s,\quad H\geq0,\quad\sum_iH_{iq}\leq\eta")
add("9개 입력 상태 각각은 pupil로 들어오는 단위 optical power다. 네 원형 ROI의 적분값을 H로 쌓았다. intensity 연산식은 서로 비간섭인 입력 성분에 적용된다. photon count로 바꾸려면 파장별 QE와 λ/(hc)를 추가해야 한다.")
fig("data/meta_psf_wavelength_angle.png", "실제 전파로 계산한 아홉 PSF와 고정 ROI. 파장·각도 변화는 위치 이동과 defocus를 함께 만든다. 물리적 meta-atom의 분산·편광 누설은 아직 포함하지 않았다.", maxh=370)
add("실제 분광·편광 시스템에서는 층별 분산, 편광, 굴절 렌즈와 relay까지 설계한다. 단순한 다초점 pupil을 그 시스템과 동일시하지 않는다. [5]", "CaptionKR")

title("19", "M8 결과 — 네 초점의 정보는 몇 차원인가?")
fig("data/meta_symmetry_ablation.png", "동일 pupil·η·총 ROI 면적에서 대칭 4초점과 하나의 비대칭 배치를 실제로 비교했다. 비대칭 배치는 최적화 결과가 아니다.", maxh=366)
table(["지표", "대칭", "비대칭 비교 설계"], [
    ["H 크기 / 수치 rank", "4×9 / 2", "4×9 / 4"],
    ["임의 9개 혼합의 nullspace 차원", "7", "5"],
    ["550 nm, 정면에서 ROI 포집 power", "0.447869", "0.508588"],
    ["비영 특잇값 condition number", "3.30 (2개만)", "17.21 (4개)"],
], [231,113,FW-344], small=True)
add("대칭 모델은 x 방향만 바꾸는 입력군에서 위/아래 ROI 응답이 중복되어 두 개의 독립 조합만 측정했다. 비대칭화로 네 조합을 얻었어도 9개의 임의 입력을 유일하게 복원할 수는 없다. rank는 분류 정확도나 알려진 저차원 파라미터의 오차와도 같은 양이 아니다.")
add("메타표면의 목표를 초점 개수로 정하기보다 직물 파라미터에 민감한 Jacobian과 광자 잡음을 함께 고려해야 한다는 근거를 준다. 이는 계산으로 확인한 한 설계 가족의 관측이며, 기존 광학 대비 실물 측정 우위의 입증은 아니다.", "CaptionKR")

title("20", "M8 검증 — 효율과 모델 오차를 분리")
table(["검증·변경", "실제 결과"], [
    ["Airy 첫 원반", "단일 초점 η=1 검산: power 0.837785; 해석값 약 0.8378"],
    ["Airy profile", "7 μm 내 정규화 강도 최대 절대 차이 0.004307"],
    ["Fresnel power identity", "최대 상대 잔차 4.16×10⁻¹⁶"],
    ["padding 2→4", "설계점 네 ROI power 약 0.003% 변화"],
    ["실제 dx 0.5→0.25 μm", "약 0.52% 변화"],
    ["Fresnel 대 scalar angular spectrum", "설계점 네 ROI power 약 0.081% 차이"],
    ["홀수→짝수 grid padding", "좌표 원점 이동을 발견·수정하고 회귀 테스트 추가"],
], [232,FW-232], small=True)
sub("위상 양자화도 실제 전파")
table(["네 초점 phase levels", "ROI 포집 incident-power fraction"], [
    ["2", "0.173346"], ["4", "0.364934"], ["8", "0.425903"], ["16", "0.442275"], ["연속 위상", "0.447869"],
], [232,FW-232], small=True)
add("위상 양자화는 총 scalar 전달 power를 임의로 줄이지 않고 센서상의 분포를 바꾼다. 단일 초점의 1개 ROI는 0.675569를 모았지만 네 초점과 총 ROI 면적이 다르므로 그 수치를 공정한 단일 렌즈 대 메타표면 성능 비교로 읽지 않는다.")
add("고차 회절 성분 중 10° 바깥 sampled pupil spectrum power는 450/550/650 nm에서 0.127/0.171/0.222였다. 중앙 ROI 확인만으로 먼 ghost의 정확도를 보장하지 않는다. 나노구조 Maxwell·편광/Jones 응답·제작 공차·실제 효율은 별도 소자 모델이 필요하다.", "CaptionKR")

if (ROOT/"data/angular_measurement_metrics.json").exists():
    title("21", "M9 — 각도 신호가 잡음 뒤에도 남는가?")
    add("기존 Gaussian beam의 실제 파동/광선 각도 power를 후방의 유한 detector sectors로 적분했다. 반구 전체를 하나로 합치는 경우와 6/18/90개로 나누는 경우를 비교한다. 동일 반구를 분할하므로 수집 각도 범위가 늘어나지 않는다. 기대 입사 photon 수를 지정한 Poisson 측정을 사용하며, 공간 픽셀 수·사람 지각·실제 metasurface 성능과 구분한다.")
    eq(r"\mu_i=N p_i,\qquad D_{\rm KL}(P_{\mu}\Vert P_{\nu})=\sum_i\left[\mu_i\log\frac{\mu_i}{\nu_i}+\nu_i-\mu_i\right]")
    add("알려진 입사 power에서는 총 R 차이와 분포 차이를 함께 관측할 수 있다. 알 수 없는 gain을 허용하면 총광량 차이를 흡수할 수 있으므로 각도 shape만으로 구분할 수 있는지를 별도로 확인해야 한다. 입력 ray histogram 자체도 25만 ray의 유한 표본이므로 높은 photon 수에서 그 수치 잡음을 물리적 정보로 확대하면 안 된다.")
    AM=load("angular_measurement_metrics.json")
    mc=next(x for x in AM["monte_carlo"] if x["label"]=="Ez_offset0")
    table(["중앙 Ez: 각도 채널 수", "알려진 N의 균형 오류율", "gain을 버린 shape-only"],[[k,f'{100*mc["sectors"][k]["known_N"]["balanced_error_fraction"]:.2f}%',f'{100*mc["sectors"][k]["profile_gain"]["balanced_error_fraction"]:.2f}%'] for k in ("1","6","18","90")],[167,170,FW-337],small=True)
    fig("data/angular_measurement_errors.png","가설별 40,000회 독립 Poisson 관측, 기대 입사 photon N=100, QE=1, read noise=0. 중앙 Ez의 기대 검출 후방 photon은 약 26.7개다. 서로 다른 물리적 재질을 분류한 결과가 아니다.",maxh=218)
    add("같은 수집 반구를 분할해도 각도 정보가 보존되면 두 모형의 구분이 좋아졌다. 그러나 두 입력은 Gaussian wave의 발산과 평행 ray라는 차이도 가지므로 ‘파동 효과만’ 분리 검출한 실험이 아니다. 실제 효율·read noise·부분 코히런스·표면 변동을 넣은 측정에서는 다시 평가해야 한다.","CaptionKR")

title("22", "테스트·리뷰 기록과 남은 위험")
if TEST:
    add(f'<b>최종 통합 실행:</b> {TEST.get("tests_run", "로그 참조")} tests, failures={TEST.get("failures", "로그 참조")}, errors={TEST.get("errors", "로그 참조")}, skipped={TEST.get("skipped", "로그 참조")}. 구체적인 결과와 실행 환경은 data/final_test_summary.json 및 data/final_tests.log에 있다.')
table(["발견한 문제", "처리와 현재 해석"], [
    ["모드 보존만으로 파동 정확성을 판단", "각도 수렴·경계·흡수 독립 검산 추가; 낮은 차수의 오차 보존"],
    ["낮은 source/각도 quadrature", "Gaussian tail·후방 적분 오차를 발견하고 해상도 증가"],
    ["대각 섬유 기하 겹침", "pitch 조정 + continuous spline separation certificate"],
    ["흡수 계수의 scene unit 가정", "Mitsuba 원 소스 확인 후 μa×radius 변환"],
    ["유한 경로 깊이의 누락", "무제한 경로 사용, depth별 deficit 저장"],
    ["공극 mask 면적 비율과 진폭의 혼동", "preview 함수 경고; 본 FFT는 binary visibility 사용"],
    ["카메라 좌표·NA 광량·Nyquist 혼동", "object-space/post-collection/output sampling 구분"],
    ["여러 초점 = 여러 독립 측정 가정", "실제 H의 rank와 nullspace 확인"],
    ["압축 최적화가 완료됐다는 과장", "반복 한도 도달과 독립 검증 오차를 명시"],
], [220,FW-220], small=True)
add("통과한 테스트는 지정한 단위·기하·모델·샘플링 조건의 검산이다. 실측 비교, broadband colorimetric 검증, 실제 광원의 부분 코히런스, 비원형/복굴절/잔털과 3D wave coupling은 남아 있다. 단일 원단의 인접 patch가 학습·평가에 섞이는 검증 누수 문제는 향후 실물 데이터 분할에서 별도로 막아야 한다.")

title("23", "연구 목적 업데이트 — 관측 가능한 외관 오차")
add("원래 목표는 화면에서 원단을 실제보다 잘못 예상하는 문제를 줄이는 것이다. 이번 결과를 바탕으로 첫 논문의 질문은 <b>‘광선 기반 외관 모델의 오차 중, 제한된 광원·각도·광자 예산에서 관측되는 성분을 찾아 측정하고 새 조명의 외관 예측을 개선할 수 있는가?’</b>로 잡는 편이 구체적이다.")
sub("측정 설계에 사용할 목적함수")
eq(r"\Delta\mathbf y=\mathcal A\!\left[K_{\rm wave}-K_{\rm ray}\right],\qquad d^2\simeq\Delta\mathbf y^T\Sigma^{-1}\Delta\mathbf y")
add("위 d²는 Gaussian noise 근사에서의 가시성 지표다. 낮은 photon 수에서는 Poisson likelihood를 직접 써야 한다. 차이의 큰 모드를 무조건 측정하는 대신 실제 조명·수집 aperture·sampling을 지난 신호로 계산한다. 광원 gain·위치·원단 방향 같은 nuisance parameter도 함께 넣어야 한다.")
eq(r"J=\frac{\partial\boldsymbol\mu}{\partial\boldsymbol\theta},\qquad \mathcal I=J^T\mathrm{diag}(1/\boldsymbol\mu)J")
add("독립 Poisson count의 Fisher 정보는 국소 식별 가능성에 유용하다. read noise가 더해지면 위 식 그대로 쓰지 말고 실제 likelihood 또는 타당한 분산 근사를 적용해야 한다. rank가 낮거나 파라미터 민감도가 잡음보다 작으면 많은 PSF를 만들어도 복원이 불안정하다.")
sub("다음 연결의 우선순위")
table(["순서", "검증 가능한 다음 산출물"], [
    ["1. 관측 범위", "실제 광원 크기·파장·patch 위치·collection angle을 정한 측정 연산자"],
    ["2. 모델 bridge", "direct power 교체·편광·입사각·3D angular measure가 맞는 effective kernel"],
    ["3. 광학 설계", "균등/선택 angular channels와 기존 lens/grating 대 meta pupil의 공정 비교"],
    ["4. 실물 검증", "현미경 기하·n(λ)·반사/투과와 독립 원단·미관측 조명 외관 비교"],
], [114,FW-114], small=True)
add("IR은 확보 가능한 실제 광학 상수와 검출 대역에 맞춰 같은 관측 모델에서 추가 정보량을 계산한 후 연결한다. 염색·퇴색·촉감 확장은 이 광학 체계가 검증된 다음으로 둔다. 현재 시뮬레이션은 IR이 VIS보다 우월하거나 메타표면이 기존 광학보다 우월하다고 입증하지 않았다.", "CaptionKR")

title("24", "재현 방법과 산출물 읽기")
code(["cd textile_lab", "python -m pip install -r requirements.txt", "python run_all.py --stages tests", "python run_all.py --stages wave ray match beam measurement", "python run_all.py --stages surrogate aperture meta", "python run_all.py --stages fabric render-checks"])
add("전체 runner는 단계별 명령·시간·exit code를 data/reproduction_logs에 남긴다. Python 3.12.14 / Mitsuba 3.9.1 / LLVM CPU에서 실행했다. Mitsuba의 해당 version을 고정한 이유는 흡수 단위의 원 소스 감사 결과와 일치시키기 위해서다.")
table(["폴더·파일", "용도"], [
    ["textile_sim/", "각 광학 모듈과 명시적 단위·API"],
    ["tests/", "해석해·극한값·보존·수렴·모듈 인터페이스 검사"],
    ["data/*.json", "선택한 파라미터, 계산 지표, 검증 결과, seed"],
    ["data/*.npz, figures/*_linear.npy", "표시 변환 이전의 복소장·각도 밀도·PSF·선형 영상"],
    ["figures/ 및 data/*.png", "실제 계산에서 그린 설명용 그림"],
    ["notes/", "세부 수식, 문헌 검토, 독립 리뷰, 가정과 미구현 경계"],
    ["references/Mitsuba_hair.cpp + LICENSE", "단위 감사에 사용한 고정된 외부 원문 소스와 라이선스"],
], [213,FW-213], small=True)
add("재계산은 같은 이름의 산출물을 갱신한다. 기존 결과를 비교 기준으로 보존하려면 별도 작업 폴더에서 실행한다. math/geometry 실험은 대체로 CPU 계산이고, 전체 원단 및 수렴 렌더가 상대적으로 시간을 사용한다. runner --quick-fabric은 점검용이며 배포한 기준 결과의 품질을 재현하지 않는다.")
add("사용자는 완성된 PDF, 코드, 원시 결과, 그림을 한 묶음에서 확인할 수 있다. 그림만으로 해석이 어려운 경우 먼저 JSON의 물리량 이름·단위·광원 조건을 확인한다. 전체 보고서의 결과는 실측이 아니라 명시된 합성 모델의 계산이다.", "CaptionKR")

title("25", "참고문헌과 원 소스")
refs=[
    ("[1] Yunchen Yu, Bruce Walter, Steve Marschner, Andrea Weidlich. Realistic Cloth Rendering with a Ray-Wave Hybrid Shading Model. ACM TOG / SIGGRAPH Asia, 2025.", "https://doi.org/10.1145/3763359", "https://blaire9989.github.io/assets/3_RayWaveFabric/project.html"),
    ("[2] Mengqi Xia et al. A Wave Optics Based Fiber Scattering Model. ACM TOG / SIGGRAPH Asia, 2020.", "https://doi.org/10.1145/3414685.3417841", "https://github.com/mandyxmq/WaveOpticsFiber"),
    ("[3] Matt Jen-Yuan Chiang, Benedikt Bitterli, Chuck Tappan, Brent Burley. A Practical and Controllable Hair and Fur Model for Production Path Tracing. Eurographics, 2016.", "https://media.disneyanimation.com/uploads/production/publication_asset/152/asset/eurographics2016Fur_Smaller.pdf", ""),
    ("[4] Tang et al. Woven Fabric Capture with a Reflection-Transmission Photo Pair. SIGGRAPH Conference, 2024.", "https://doi.org/10.1145/3641519.3657410", "https://github.com/lxtyin/FabricBTDF-Recovery"),
    ("[5] Liu, Xu, Guo. MetaSpectra+: A Compact Broadband Metasurface Camera for Snapshot Hyperspectral+ Imaging. CVPR, 2026.", "https://meta-imaging.qiguo.org/", "https://github.com/guo-research-group/MetaSpectra-plus"),
    ("[6] NIST Digital Library of Mathematical Functions, §10.23, Bessel/Hankel addition theorems; Watanabe et al., circular-cylinder transition-matrix formulation, Optics Express 20, 10646–10657 (2012).", "https://dlmf.nist.gov/10.23", "https://doi.org/10.1364/OE.20.010646"),
    ("[7] Mitsuba renderer, v3.9.1. Versioned hair BSDF source used for the absorption-unit audit; software and dependencies retain their own licenses.", "https://github.com/mitsuba-renderer/mitsuba3", "https://raw.githubusercontent.com/mitsuba-renderer/mitsuba3/v3.9.1/src/bsdfs/hair.cpp"),
    ("[8] Xia et al. A Practical Wave Optics Reflection Model for Hair and Fur, 2023. Public simulation/fitting repository reviewed as a possible irregular-fiber extension; not executed.", "https://github.com/mandyxmq/WaveFiber3d", ""),
]
for desc,*urls in refs:
    add(escape(desc),"SmallKR")
    for url in urls:
        if url:
            add(f'<link href="{escape(url)}" color="#31588a">{escape(url)}</link>',"CaptionKR")
    STORY.append(Spacer(1,4))
add("문헌의 공개 상태와 버전은 2026-10-10 확인 기준이다. 자료마다 실제로 읽거나 실행한 범위를 개별 노트에 남겼다. 외부 모델의 검증을 이번의 다른 기하·광원·소자 설계에 자동 적용하지 않았다.", "CaptionKR")


def decorate(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#d1dfe6"))
    canvas.setLineWidth(.5)
    canvas.line(48, 41, W-48, 41)
    canvas.setFont("KR", 7)
    canvas.setFillColor(colors.HexColor("#667985"))
    canvas.drawString(48, 28, "실행된 합성 광학 모델 · 수치 검증과 실물 검증을 구분")
    canvas.drawRightString(W-48, 28, f"2026-10-10  /  {doc.page}")
    canvas.restoreState()


OUT.mkdir(exist_ok=True)
path=OUT/"textile_optical_simulation_report_ko.pdf"
doc=SimpleDocTemplate(str(path),pagesize=A4,rightMargin=48,leftMargin=48,
                      topMargin=43,bottomMargin=57,title="섬유에서 원단 영상까지: 광학 시뮬레이션 연구",
                      author="Textile Optical Simulation Lab",pageCompression=1)
doc.build(STORY,onFirstPage=decorate,onLaterPages=decorate)
print(path)
