"""Build the Korean v0.2.0 report from the saved, executed v2 artifacts.

This generator is independent of build_report.py and never overwrites the v1 PDF.
Run from any working directory with the project dependencies plus ReportLab,
Pillow and matplotlib available. Noto Sans KR font files are expected in
TEXTILE_REPORT_FONT_DIR, or in ../.report_fonts relative to the repository.
All quantitative tables are loaded from the saved JSON artifacts. This script
does not run geometry generation, ray tracing, wave solvers, or renderer jobs.
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
import matplotlib
matplotlib.use("Agg")
from matplotlib import pyplot as plt
from matplotlib.mathtext import math_to_image
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, Image,
    KeepTogether,
)
from reportlab.graphics.shapes import Drawing, Rect, Line, Polygon, String


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "report" / "fabric_engine_v2_report_ko.pdf"
FONT = Path(os.environ.get("TEXTILE_REPORT_FONT_DIR", ROOT.parent / ".report_fonts"))
VERSION = "0.2.0"
DATE = "2026-10-11"
REPO = "https://github.com/Phill-lms/textile-optics-engine"
INK = colors.HexColor("#182b3a")
TEAL = colors.HexColor("#087f8c")
BLUE = colors.HexColor("#31588a")
LIGHT = colors.HexColor("#edf4f7")
PALE = colors.HexColor("#f5f8fa")
ORANGE = colors.HexColor("#aa661b")
GRAY = colors.HexColor("#516774")
W, H = A4
FW = W - 96

pdfmetrics.registerFont(TTFont("KRv2", str(FONT / "NotoSansKR-400.ttf")))
pdfmetrics.registerFont(TTFont("KRBv2", str(FONT / "NotoSansKR-700.ttf")))
pdfmetrics.registerFontFamily("KRv2", normal="KRv2", bold="KRBv2", italic="KRv2", boldItalic="KRBv2")
S = getSampleStyleSheet()
S.add(ParagraphStyle("BodyV2", fontName="KRv2", fontSize=9.25, leading=14.4,
                    textColor=INK, spaceAfter=8, wordWrap="CJK"))
S.add(ParagraphStyle("SmallV2", parent=S["BodyV2"], fontSize=8.0, leading=11.5, spaceAfter=5))
S.add(ParagraphStyle("CaptionV2", parent=S["BodyV2"], fontSize=8.0, leading=11.6,
                    textColor=GRAY, spaceAfter=9))
S.add(ParagraphStyle("H1V2", parent=S["BodyV2"], fontName="KRBv2", fontSize=20.5,
                    leading=28, spaceAfter=12))
S.add(ParagraphStyle("H2V2", parent=S["BodyV2"], fontName="KRBv2", fontSize=12.2,
                    leading=17.5, spaceBefore=6, spaceAfter=7, textColor=TEAL))
S.add(ParagraphStyle("KickerV2", parent=S["BodyV2"], fontName="KRBv2", fontSize=8.6,
                    leading=13, textColor=TEAL, spaceAfter=8))
S.add(ParagraphStyle("CoverV2", parent=S["BodyV2"], fontName="KRBv2", fontSize=29,
                    leading=39, spaceAfter=14))
S.add(ParagraphStyle("CodeV2", fontName="Courier", fontSize=7.6, leading=11.0,
                    textColor=INK, backColor=LIGHT, leftIndent=8, rightIndent=7,
                    borderPadding=8, spaceBefore=4, spaceAfter=9, wordWrap="LTR"))
S.add(ParagraphStyle("RefV2", parent=S["BodyV2"], fontSize=7.7, leading=10.7, spaceAfter=8))


def read_json(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


TEST = read_json("data/final_test_summary.json")
if TEST["failures"] or TEST["errors"]:
    raise RuntimeError("The report's passed-test interpretation requires a successful saved test run.")
OPT = read_json("data/optical_bridge_v2/optical_bridge_metrics.json")
STAT = read_json("data/optical_bridge_v2/fabric_microstructure.json")
REFINE = read_json("data/hierarchy_v2/sampling_refinement_metrics.json")
CASES = [
    ("plain_single_ply", "평직 · 1 ply"),
    ("twill_two_ply", "능직 · 2 plies"),
    ("basket_rectangular_three_ply", "바스켓 · 3 plies"),
    ("twill_migration_waviness", "능직 · migration/waviness"),
    ("twill_loop_excursions", "능직 · loop 추가"),
]
GEOM = {k: read_json(f"data/hierarchy_v2/{k}/hierarchy_metrics.json") for k, _ in CASES}
STORY = []
PAGE_TITLES = []


def p(text, style="BodyV2"):
    text = text.replace("ᵀ", "<super>T</super>")
    supers = "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻"
    subs = "₀₁₂₃₄₅₆₇₈₉ᵢₙₓ"
    text = re.sub("[" + supers + "]+", lambda m: "<super>" + m.group().translate(
        str.maketrans(supers, "0123456789+-")) + "</super>", text)
    text = re.sub("[" + subs + "]+", lambda m: "<sub>" + m.group().translate(
        str.maketrans(subs, "0123456789inx")) + "</sub>", text)
    return Paragraph(text, S[style])


def add(text, style="BodyV2"):
    STORY.append(p(text, style))


def title(number, text, subtitle=""):
    if STORY:
        STORY.append(PageBreak())
    PAGE_TITLES.append(text)
    add(f"FABRIC ENGINE / v{VERSION} / {number:02d}", "KickerV2")
    add(text, "H1V2")
    if subtitle:
        add(subtitle, "CaptionV2")


def sub(text):
    add(text, "H2V2")


def table(headers, rows, widths=None, small=True):
    st = "SmallV2" if small else "BodyV2"
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
    t = Table([[p(head, "H2V2")], [p(body)]], colWidths=[FW], hAlign="LEFT")
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
    add(caption, "CaptionV2")


def code(text):
    add(escape(text).replace("\n", "<br/>"), "CodeV2")


def irregularity_figure():
    """Plot the other two saved cases; no new geometry is generated here."""
    figure = plt.figure(figsize=(10, 3.5), layout="constrained")
    for col, (key, label) in enumerate([
        ("twill_migration_waviness", "Twill + migration + waviness"),
        ("twill_loop_excursions", "Same family + local loop excursions"),
    ]):
        ax = figure.add_subplot(1, 2, col + 1, projection="3d")
        base = ROOT / "data/hierarchy_v2" / key
        provenance = read_json(str(base.relative_to(ROOT) / "hierarchy_geometry.json"))["fiber_provenance"]
        with np.load(base / "hierarchy_geometry.npz", allow_pickle=False) as data:
            pts, offsets = data["fibers"], data["fiber_offsets"]
            for j, meta in enumerate(provenance):
                xyz = pts[offsets[j]:offsets[j + 1], :3]
                ax.plot(xyz[:, 0], xyz[:, 1], xyz[:, 2],
                        color="#31588a" if meta["family"] == "warp" else "#cc9349",
                        lw=.40, alpha=.65)
        ax.set_title(label + "\n140 explicit fibers", fontsize=9, pad=3)
        ax.set_xlabel("x [mm]", fontsize=7, labelpad=-1)
        ax.set_ylabel("y [mm]", fontsize=7, labelpad=-1)
        ax.set_zlabel("z [mm]", fontsize=7, labelpad=-2)
        ax.tick_params(labelsize=6, pad=0)
        ax.view_init(elev=27, azim=-56)
        ax.set_box_aspect((1, .82, .23))
    buf = io.BytesIO()
    figure.savefig(buf, format="png", dpi=180, facecolor="white")
    plt.close(figure)
    buf.seek(0)
    with PILImage.open(buf) as im:
        iw, ih = im.size
    scale = min(FW / iw, 175 / ih)
    buf.seek(0)
    pic = Image(buf, width=iw * scale, height=ih * scale)
    pic.hAlign = "CENTER"
    STORY.append(pic)
    add("저장된 추가 두 예제의 실제 중심선. 축별 표시 비율은 가독성을 위해 조정했다. 작은 migration·loop 차이는 이 축척에서 미세하므로 간격·길이·sampling 지표로 함께 확인한다. 선의 표시 두께는 반지름과 다르다.", "CaptionV2")


def arrow(d, x1, y1, x2, y2, color=GRAY, dashed=False):
    ln = Line(x1, y1, x2, y2, strokeColor=color, strokeWidth=1.25)
    if dashed:
        ln.strokeDashArray = [3, 3]
    d.add(ln)
    import math
    a = math.atan2(y2 - y1, x2 - x1)
    ca, sa = math.cos(a), math.sin(a)
    points = [x2, y2, x2 - 6 * ca + 3 * sa, y2 - 6 * sa - 3 * ca,
              x2 - 6 * ca - 3 * sa, y2 - 6 * sa + 3 * ca]
    d.add(Polygon(points, fillColor=color, strokeColor=color))


def box(d, x, y, w, h, top, bottom="", fill=LIGHT, stroke=TEAL):
    d.add(Rect(x, y, w, h, rx=6, ry=6, fillColor=fill, strokeColor=stroke, strokeWidth=.8))
    d.add(String(x + w / 2, y + h / 2 + (7 if bottom else -3), top,
                 fontName="KRBv2", fontSize=10, textAnchor="middle", fillColor=INK))
    if bottom:
        d.add(String(x + w / 2, y + h / 2 - 10, bottom,
                     fontName="KRv2", fontSize=8, textAnchor="middle", fillColor=GRAY))


def architecture():
    d = Drawing(FW, 284)
    cw = 146
    xs = [0, (FW - cw) / 2, FW - cw]
    for x, label, detail in zip(xs, ["직조·원사 설정", "실측/합성 재료", "관측·검증 설계"],
                               ["draft · twist · radius", "n(λ), κ(λ), provenance", "조명 · 각도 · 파장"]):
        box(d, x, 229, cw, 48, label, detail)
    box(d, 15, 145, 191, 55, "계층 기하 + 전역 검사", "fiber → ply → yarn → patch")
    box(d, 278, 145, 206, 55, "OpticalScene", "불변 입력 · 단위 · ID · hash")
    arrow(d, xs[0] + cw / 2, 229, 108, 200)
    arrow(d, xs[1] + cw / 2, 229, 365, 200)
    arrow(d, 206, 172, 278, 172)
    arrow(d, xs[2] + cw / 2, 229, 411, 200)
    labels = [("2D 국소 기준해", "유효 단면 → Maxwell / ray"),
              ("3D 개별 섬유 수송", "변환 오차 → Mitsuba"),
              ("구조 통계 / 후속 집계", "방향 · 길이 · 투영면적")]
    for x, (label, detail) in zip(xs, labels):
        box(d, x, 56, cw, 56, label, detail)
    arrow(d, 315, 145, xs[0] + cw / 2, 112)
    arrow(d, 364, 145, xs[1] + cw / 2, 112)
    arrow(d, 428, 145, xs[2] + cw / 2, 112)
    d.add(String(FW / 2, 18, "공통 provenance로 결과 비교 → 근사 오차와 측정 정보의 가치 평가",
                 fontName="KRv2", fontSize=9, fillColor=GRAY, textAnchor="middle"))
    STORY.append(d)


def citation_graph():
    d = Drawing(FW, 171)
    bw = 132
    box(d, 0, 110, bw, 46, "Zhao 2016", "procedural yarn")
    box(d, 183, 110, bw, 46, "Montazeri 2020", "ply appearance")
    box(d, 366, 110, bw, 46, "Tang 2024", "reflection / transmission")
    box(d, 183, 10, bw, 46, "FabricGen 2026", "implicit microstructure")
    box(d, 366, 10, bw, 46, "Li 2026", "fiber capture")
    arrow(d, 132, 133, 183, 133)
    arrow(d, 315, 133, 366, 133)
    arrow(d, 249, 110, 249, 56)
    arrow(d, 393, 110, 289, 56)
    arrow(d, 432, 110, 432, 56)
    arrow(d, 66, 110, 389, 56)
    STORY.append(d)


def matrix_draft():
    d = Drawing(FW, 126)
    patterns = [
        ("Plain 2×2", [[1, 0], [0, 1]]),
        ("Twill 4×4", [[int((j - i) % 4 < 2) for j in range(4)] for i in range(4)]),
        ("Rectangular 4×6", [[int((i // 2 + j // 2) % 2 == 0) for j in range(6)] for i in range(4)]),
    ]
    for x, (label, matrix) in zip([38, 206, 356], patterns):
        nrows, ncols = len(matrix), len(matrix[0])
        sz = 17
        for i, row in enumerate(matrix):
            for j, value in enumerate(row):
                d.add(Rect(x + j * sz, 90 - (i + 1) * sz, sz, sz,
                           fillColor=BLUE if value else colors.HexColor("#ecd3b7"),
                           strokeColor=colors.white, strokeWidth=.8))
        d.add(String(x + ncols * sz / 2, 8, label, textAnchor="middle",
                     fontName="KRv2", fontSize=9, fillColor=INK))
    d.add(String(FW / 2, 113, "행 = weft / 열 = warp / 파랑 = warp over",
                 textAnchor="middle", fontName="KRv2", fontSize=9, fillColor=GRAY))
    STORY.append(d)


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#d2dfe6"))
    canvas.line(48, 38, W - 48, 38)
    canvas.setFont("KRv2", 7.3)
    canvas.setFillColor(GRAY)
    canvas.drawString(48, 25, f"FABRIC / OPTICS ENGINE   v{VERSION}   ·   {DATE}")
    canvas.drawRightString(W - 48, 25, f"{doc.page:02d}")
    canvas.restoreState()


# 01 — Outcome before implementation details.
PAGE_TITLES.append("원사에서 직물까지")
add(f"RESEARCH & ENGINEERING REPORT / v{VERSION} / {DATE}", "KickerV2")
STORY.append(Spacer(1, 16))
add("원사에서 직물까지<br/>계층 기하와 광학 엔진", "CoverV2")
add("Fiber → Ply → Yarn → Weave → Fabric → Optical response", "H2V2")
add("제품 사진과 실물 원단 사이의 외관 차이를 줄이기 위한, 검증 가능한 forward simulator의 두 번째 구현 보고서. 염색·퇴색은 후속 단계로 두고, 개별 섬유의 구조와 광학 특성을 연결했다.")
fig("figures/hierarchy_v2/hierarchy_levels.png",
    "실제 v2 생성 결과. 선은 명시적 섬유 중심선이며 표시 두께와 색은 물리적 반지름·재료 색을 뜻하지 않는다.", maxh=173)
table(["구현·실행", "저장된 결과"], [
    ["다섯 계층 기하 예제", "190 / 140 / 210 / 140 / 140 fibers; 각 예제의 연속 polyline 간격 검사 통과"],
    ["혼합 재료 광학 연결", "98 fibers, 2 materials × 2 radii = 4 export groups; 실제 Mitsuba 반사·투과 렌더"],
    ["국소 기준 광학", "7-fiber 직선 bundle; 3 wavelengths × 2 polarizations; Maxwell 및 ray 실행"],
    ["통합 회귀 검증", f"{TEST['tests_run']} tests; failures {TEST['failures']}, errors {TEST['errors']}, skipped {TEST['skipped']}"],
], [143, FW - 143])
callout("이번 버전에서 확보한 것", "같은 섬유의 위치·반지름·재료 ID·부모 관계를 여러 광학 계산에 넘기고, 각 변환의 유효성과 오차를 추적하는 실행 가능한 연구 기반이다. 실물 소재별 외관의 정확성은 앞으로 측정 시편과 비교해 확인해야 한다.")
add("자료 기준: data/hierarchy_v2, data/optical_bridge_v2, data/final_test_summary.json. 원본 v1 보고서와 코드는 유지하며 이 문서는 신규 v2 모듈에 집중한다.", "CaptionV2")

# 02 — Purpose and module architecture.
title(2, "연구 목적과 모듈의 역할", "사용자가 원하는 것은 해상도 증가 자체보다, 다른 조건에서도 실물의 재질감을 예상할 수 있는 표현이다.")
add("고해상도 사진은 한 촬영 조건의 작은 무늬를 더 많이 보존한다. 그러나 조명 방향이 바뀔 때의 광택 이동, 반사와 비침의 균형, 파장에 따른 흡수 차이는 그 정지 영상만으로 모두 정해지지 않는다. 연구의 목적은 이 변화 반응을 예측하는 재질 모델을 얻는 것이다.")
architecture()
table(["모듈", "현재 출력", "다음 모델과의 경계"], [
    ["D · draft", "교차 순서, 반복, float, lift plan", "유한 두께의 제조 가능성은 별도"],
    ["G · hierarchy", "명시적 원형 섬유, 계층·샘플링", "장력·접촉 평형은 후속"],
    ["V · validation", "연속 간격, refinement, 변환 상한", "실제 원단 측정과의 정확성은 별도"],
    ["O · optical scene", "스펙트럼·단위·IDs·source hash", "파동/광선/BSDF가 같은 물리를 갖는다고 가정하지 않음"],
    ["E · evaluation", "기준 계산과 렌더·구조 통계", "촬영 설계·역추정·지각 평가는 후속"],
], [80, 185, FW - 265])
add("핵심 질문: 구조·재료가 조금 다른 두 원단이 좋은 RGB 관측에서는 비슷하지만 다른 조명이나 투과 조건에서는 달라지는가? 그 차이를 가장 효율적으로 확인하는 관측은 무엇인가? v2는 이 질문에 필요한 통제 가능한 형상과 공통 광학 입력을 만든다.")

# 03 — Literature map with explicit reading status.
title(3, "문헌 지도와 실제 검토 범위", "논문을 참고한 수준, 코드를 읽은 수준, 실제 실행한 수준을 구분한다. 상세 기록은 notes/literature_engine_v2.md.")
citation_graph()
add("화살표는 검토한 1차 문헌에서 확인한 인용 관계다. Weavecraft·TexGen의 설계/역학 계열은 이 외관 모델 계열과 병행해서 참고했다. 전체 직물 연구를 망라한 인용 그래프는 아니다. [1–7]", "CaptionV2")
table(["자료", "실제 검토", "이번 코드의 사용 범위"], [
    ["FabricGen, CVPR 2026 [1]", "첨부 본문 10쪽 전체; 공식 supplementary의 구조/렌더링 절", "draft와 계층 분리 참고. LLM·diffusion 학습 및 저자 구현 미실행"],
    ["Tang R/T capture, 2024 [2]", "첨부 arXiv v3 13쪽 전체; 공식 주요 소스와 pinned commit", "반사·투과 분리 및 optical depth 해석. 역복원/ASGGX 미구현"],
    ["Montazeri 2020 / Trunz 2023 [3,4]", "대표 구조·절차 생성 절", "곡선 기울기, 재귀 frame, migration 참고. 전체 방법 재현 아님"],
    ["Weavecraft 2020 [5]", "공식 프로젝트·저자 설명", "3D block과 yarn mechanics의 확장 기준. PDF 전체/저자 코드 미실행"],
    ["TexGen [6]", "공식 README, Yarn.h 및 weave interface", "단면·반복·계층 인터페이스 참고. compile/vendor 없음"],
    ["Zhao 2016 / Li 2026 [7,8]", "공식 project 및 후속 논문 맥락; Li 주요 절", "CT fitting / inverse fiber capture의 비교 범위. 파이프라인 미실행"],
    ["Yu 2025 / Mitsuba 3.9.1 [10–12]", "Yu 관련 모델 검토; Mitsuba hair/curve 소스 감사", "기존 국소 파동 기준과 실제 curve render 연결. Yu 전체 shader 재현 아님"],
], [118, 181, FW - 299])
add("Weavecraft와 Zhao의 큰 PDF/자료 아카이브는 제공된 reader 범위에서 전체 내용을 열람하지 못했다. 이 문서의 구현 근거는 실제 읽은 절·공식 인터페이스·독립 유도·실행 테스트에 한정한다.", "SmallV2")

# 04 — Interpret the two uploaded papers correctly.
title(4, "두 첨부 논문을 엔진에 반영하는 방식")
sub("FabricGen: implicit appearance를 명시적 기준 기하와 연결")
equation(r"F(p)=\{\mathbf{n}(p),\mathbf{t}(p),h(p)\},\qquad p=(x,y)")
add("FabricGen의 procedural query는 UV 위치의 normal, tangent, height를 반환한다. Macro albedo 생성과 microstructure를 분리하고, multi-ply helix, UV sliding, 확률적 방향 층을 통해 섬유성 외관을 구성한다. 이것을 개별 섬유의 접촉 역학으로 해석하면 안 된다. [1]")
add("v2는 미세 구조를 기준 파동·광선·렌더러에 공통으로 전달하기 위해 각 fiber의 실제 곡선을 저장한다. 향후 implicit/집계 표현을 추가할 때에는 같은 명시적 기준 장면과 비교해 속도·오차를 측정한다. FabricGen의 학습 데이터나 저자 생성 코드는 이번 실행에 포함하지 않았다.")
sub("Tang: 반사·투과를 구분하고 물리 길이와 optical depth를 분리")
equation(r"f=f_s+f_m+f_d^{r,t}")
equation(r"T_{\mathrm{eff}}=T\,[S_{\min}+(1-\mu)(1-S_{\min})]")
add("Tang의 모델은 두 실제 yarn layer, SGGX single scattering, ASGGX 다중 산란 근사, diffuse 성분 및 gap의 직접 투과를 구분한다. 위 두 번째 식은 해당 모델의 경험적 optical-thickness modulation이다. mm 단위의 섬유 두께나 장력 평형의 결과와 같지 않다. 촬영계 Gaussian blur 역시 파동 회절의 대체식이 아니다. [2]")
table(["관찰한 논문 요소", "v2에서 보존·준비한 것", "후속 검증"], [
    ["위·아래 층의 차이", "warp/weft와 모든 parent ID, 실제 공극", "반사만 쓸 때와 반사+투과의 식별력"],
    ["미세 방향 분포", "길이·체적 가중 tangent moment", "SGGX 분포/광학 density의 별도 fitting"],
    ["정밀 미세 구조와 빠른 외관", "explicit fiber 기준 + adapter", "집계 모델의 각도별 오차와 계산 비용"],
], [123, 189, FW - 312])
add("공식 Tang 저장소 검토 revision: 67150eeca9f28b85f8fe21d40d888d34bd4d3b25. GPL-3.0 소스를 참고했으나 코드·weights를 복사하거나 의존성으로 포함하지 않았다. [2]", "SmallV2")

# 05 — Detailed hierarchy.
title(5, "계층 데이터 계약: fiber에서 patch까지")
fig("figures/hierarchy_v2/hierarchy_levels.png",
    "동일한 local sweep 연산을 반복해 fiber/ply/yarn 계층을 구성한다. 예시 그림은 데이터 구조 설명이며 실제 소재의 현미경 사진이 아니다.", maxh=166)
table(["계층", "입력·객체", "물리적 의미와 보존 정보"], [
    ["Fiber", "FiberSpec", "material_id, 원형 반지름, ply 단면 offset, migration/loop"],
    ["Ply", "PlySpec", "fiber tuple, yarn 단면 offset, fiber twist와 phase"],
    ["Yarn", "YarnSpec", "ply tuple, ply twist와 phase; 각 ply의 부모"],
    ["Weave", "WeaveDraft", "행=weft, 열=warp, 1=warp over; 임의 직사각 반복"],
    ["Fabric patch", "FabricSpec", "경·위사 수와 pitch, crimp 분배, gap, sampling, seed"],
    ["Geometry", "HierarchyGeometry", "fiber_records, yarn/ply 중심선, bounds, spec, metadata"],
], [86, 133, FW - 219])
code("FiberCurve\n  points_mm[N,3], radii_mm[N]\n  fiber_id, yarn_id, ply_id, material_id\n  family, yarn_index, ply_index, fiber_index\n  kind, cross_section='circle'")
add("좌표와 반지름은 mm, twist는 부모 중심선 1 mm당 부호 있는 회전 수다. 현재 fiber별 반지름은 일정하며 곡선 표현은 보간 polyline이다. 각 배열은 immutable bytes를 사용해 생성 후 좌표·반지름이 바뀌지 않도록 했다.")
add("저장 schema: textile-hierarchy/2.0. 가변 길이 곡선은 offsets를 둔 NPZ로 저장하며 allow_pickle=False로 읽는다. JSON에는 config·부모 관계·단위·NPZ hash를 보존한다. 상위 spec/dictionary 전체를 불변 객체라고 주장하지는 않는다.", "SmallV2")

# 06 — Topology and crimp.
title(6, "직조 위상과 처방된 C² crimp")
matrix_draft()
add("W의 각 원소는 두 yarn의 교차 순서다. 물질·굵기·장력은 이 binary 값에 들어 있지 않다. 각 축의 반복 길이를 따로 사용하므로 직사각 repeat와 음수 padding index도 처리한다. 두 family를 바꿀 때는 높이의 의미까지 바뀌어 W′ = 1 − Wᵀ가 된다.")
equation(r"z^{\mathrm{warp}}_j(i)=a_w(2W_{ij}-1),\quad z^{\mathrm{weft}}_i(j)=-a_f(2W_{ij}-1)")
equation(r"a_w+a_f=R_{w,\mathrm{env}}+R_{f,\mathrm{env}}+g")
equation(r"h(u)=10u^3-15u^4+6u^5,\quad 0\leq u\leq1")
add("warp_crimp_share는 같은 교차 중심선 거리 중 warp에 배분할 비율이다. 인접 교차 높이는 quintic h(u)로 연결한다. 이 함수는 단조이며 양 끝의 1·2차 도함수가 0이다. Lateral waviness도 교차점에서 0인 C² bump를 써서 교차 anchor를 유지한다.")
table(["검사·출력", "할 수 있는 판단", "해석의 경계"], [
    ["cyclic float / unbound yarn", "repeat 경계를 넘는 float와 결속 없음 검출", "loom 설정·마찰·변형 안정성은 별도"],
    ["lift plan round-trip", "동일 열을 묶어 정확한 threading/lift plan 생성", "최적 treadle tie-up을 찾는 문제와 구분"],
    ["over/under + envelope gap", "처방된 crossing과 국소 packing 유지", "전역 섬유 충돌은 capsule 검사 필요"],
], [118, 188, FW - 306])
callout("직조 패턴의 주기성과 전체 미시 구조의 주기성", "부모 한 주기의 호길이 L에 대해 TL이 정수가 아니면 twist phase가 닫히지 않는다. Migration phase와 frame holonomy도 별도다. 현재 출력은 유한 padded patch이고 geometry_tileable=False를 기록한다.")

# 07 — Parent arclength and RMF.
title(7, "호길이와 RMF에 기반한 재귀 sweep", "기하 엔진의 핵심: 두 twist를 각각의 부모 곡선에서 정의한다.")
equation(r"s_k=\sum_{j<k}\|\mathbf{c}_{j+1}-\mathbf{c}_j\|,\qquad\phi(s)=\phi_0+2\pi T s")
equation(r"\mathbf{x}(s)=\mathbf{c}(s)+(q_x\cos\phi-q_y\sin\phi)\mathbf{n}_1+(q_x\sin\phi+q_y\cos\phi)\mathbf{n}_2")
add("여기서 n₂ = t × n₁이고 (t, n₁, n₂)는 부모 곡선의 이동 frame이다. 양의 T는 부모의 진행 tangent를 축으로 하는 오른손 회전이다. S/Z 표기는 관찰 방향에 의존하므로 수치 부호와 자동으로 동일시하지 않는다.")
table(["단계", "계산", "이 단계가 필요한 이유"], [
    ["1", "부모 segment 길이와 누적 호길이", "세계 x/y/z 좌표로 twist를 매개화하는 오차 방지"],
    ["2", "double-reflection RMF transport", "곡률이 0인 구간에서도 Frenet normal flip을 피함"],
    ["3", "offset 회전 + bounded displacement", "local 단면 배치와 부호 규약을 하나의 식으로 유지"],
    ["4", "생성된 ply의 호길이를 다시 계산", "ply가 yarn보다 길어질 때 fiber의 회전 수를 보존"],
    ["5", "segment·turn·phase step과 전역 간격 검사", "처방 파라미터와 실제 discretization 사이의 오차 확인"],
], [43, 223, FW - 266])
sub("수치 frame의 정확도는 별도로 검증")
add("Wang 등의 double-reflection RMF를 독립 구현했다. 해석적 helix의 Bishop frame과 비교하고, chord length refinement 및 좌표 강체변환을 검사했다. 일반 polyline에서 계산하는 tangent와 해석적 tangent를 구분하므로 임의 기하 전체에 대해 보편적인 4차 수렴을 주장하지 않는다. [9]")
add("되돌아가는 cusp, 0 길이 segment, 정의되지 않는 초기 frame은 입력 오류로 거부한다. Stand-alone build_yarn의 sampling은 호출자가 공급한다. 입력 중심선에 비해 twist가 너무 빠르면 독립적으로 sampling을 늘리고 진단해야 한다.")
callout("독립 대칭성 테스트", "y → −y 반사와 함께 두 계층의 twist, phase, transverse offset 부호를 바꾸면 전체 nested fiber가 반사된 해와 일치했다. 단일 helix만 확인하는 테스트를 넘어 두 단계 frame·부호 연결을 검사한다.")

# 08 — Controlled irregularity.
title(8, "Migration과 loop: 통제된 구조 변수")
sub("방사 migration")
equation(r"r_i(s)=r_i^0+A_i\cos(2\pi s/P_i+\varphi_i),\qquad0\leq A_i<r_i^0")
add("명목 방사 offset에서 유한 진폭을 갖는 이동을 더한다. 중심 fiber는 방사 방향이 정의되지 않아 이 migration을 허용하지 않는다. Phase를 지정하지 않으면 seed와 전체 fiber ID의 SHA-256로 결정한다. Fiber 생성 순서를 바꿔도 같은 ID의 형상은 바뀌지 않는다.")
sub("기존 fiber의 국소 loop excursion")
equation(r"b(u)=64u^3(1-u)^3\quad(0\leq u\leq1),\qquad b=0\ \mathrm{outside}")
add("양 끝의 값과 1·2차 도함수가 0이며 가운데에서 1이 되는 compact bump다. 기존 fiber에 바깥 방향으로 더해 다시 연결되는 곡선을 만든다. 새로운 fiber 객체를 복제하지 않지만 반지름을 유지한 채 길이가 바뀌므로 재료량 proxy도 바뀐다.")
equation(r"g^{\mathrm{section}}_{ij}\geq d_{ij}-A_i^{\max}-A_j^{\max}-r_i-r_j")
add("같은 단면에서의 보수적 간격 하한을 먼저 검사한다. Loop 최대 변위도 A<super>max</super>에 포함한다. 이 식은 서로 다른 축 위치에서 접근하는 곡선의 충돌을 보장하지 못하므로, 생성 후 전역 capsule 검사가 필수다.")
table(["변수", "현재 할 수 있는 실험", "후속에 필요한 측정/모델"], [
    ["migration", "진폭·주기를 고정한 optical sensitivity", "CT 또는 현미경 기반 radial population 통계"],
    ["waviness", "교차 위치를 유지한 방향 분포 변화", "실제 yarn sliding과 장력·마찰 관계"],
    ["loop", "국소 돌출이 가림·산란에 미치는 변화", "staple 길이, breakage, 실제 hairiness 분포"],
], [90, 205, FW - 295])
callout("현재의 불규칙성은 제어 변수", "Zhao·Trunz 계열에서 다루는 CT fitting이나 실제 방적 통계를 재현한 상태는 아니다. 질량 보존·접촉 평형까지 주장하려면 별도의 기계적 경로와 실측 파라미터가 필요하다. [4,7]")
irregularity_figure()

# 09 — Actual five geometry examples.
title(9, "다섯 가지 실제 생성 예제")
fig("figures/hierarchy_v2/topology_to_fibers.png",
    "위: binary draft. 아래: 생성된 명시적 fiber 중심선. 파랑/주황은 warp/weft 구분이며 소재 색을 나타내지 않는다. 첫 세 예제는 ply 수·반지름·pitch도 달라 직조 효과만 분리한 비교는 아니다.", maxh=282)
rows = []
for key, label in CASES:
    g = GEOM[key]
    rows.append([label, f"{g['yarn_count']} / {g['ply_count']}", f"{g['fiber_count']:,}",
                 f"{g['vertex_count']:,}", f"{g['total_fiber_length_mm']:.3f}",
                 f"{g['clearance_audit']['minimum_clearance_lower_bound_mm'] * 1000:.3f}"])
table(["예제", "yarn / ply", "fibers", "정점", "총 길이 mm", "간격 LB μm"],
      rows, [164, 67, 48, 67, 75, FW - 421])
add("모든 예제는 서로 다른 fiber 사이 연속 polyline capsule 검사에서 겹침 0을 기록했다. LB는 검사 알고리즘이 보장하는 보수적 하한이다. 표의 정점은 실제 수락된 기본 sampling 결과이며 단순한 요청값만 센 것이 아니다.")
add("기본 twill, migration/waviness twill, loop twill은 crossing 중심선 거리를 0.064 mm로 유지했다. Envelope 변위만큼 nominal gap을 조정해 crimp 크기의 변화를 줄였다. 다만 migration과 waviness를 동시에 켰으므로 두 효과를 각각 식별하는 요인 실험은 아직 아니다.")
add("원본: examples/hierarchy/*.json 및 data/hierarchy_v2/&lt;case&gt;/{hierarchy_geometry.json, hierarchy_geometry.npz, hierarchy_metrics.json}.", "SmallV2")

# 10 — Continuous clearance proof.
title(10, "전역 capsule 검사와 보장 범위")
add("정점 사이 거리가 멀어도 선분 중간에서 두 fiber가 교차할 수 있다. 따라서 vertex-only 검사 대신, 각 segment에 반지름을 더한 연속 capsule 집합을 검사한다. 동일 단면 packing 통과 후 서로 다른 축 위치에서 접근하는 tight helix도 별도의 실패 예제로 확인했다.")
equation(r"\|\mathbf{m}_i-\mathbf{m}_j\|\leq h_i+h_j+r_i+r_j+p")
equation(r"R_{\mathrm{search}}=2\max_i(h_i+r_i)+p")
add("m은 segment midpoint, h는 half-length, r은 fiber 반지름, p는 probe margin이다. 표면 간격이 p 이하인 모든 쌍은 위 첫 식을 만족하므로 KD-tree의 전역 search radius가 이를 빠짐없이 포함한다. 남은 후보에는 segment-to-segment 최소거리를 계산한다.")
equation(r"g_{\mathrm{LB}}=\min\!\left(p,\min_{\mathrm{tested}}(d_{ij}-r_i-r_j)\right)")
add("후보에서 제외한 far pair는 간격이 p보다 크다는 것만 알 수 있어 최종 하한은 p를 넘지 않는다. 검사한 최소 간격이 더 크더라도 이를 전체의 정확한 최소값으로 보고하지 않는다.")
table(["예제", "검사한 서로 다른 fiber segment 쌍", "겹침"],
      [[label, f"{GEOM[key]['clearance_audit']['tested_segment_pairs']:,}",
        str(GEOM[key]['clearance_audit']['overlapping_capsule_pairs'])] for key, label in CASES],
      [196, 233, FW - 429])
sub("독립 리뷰에서 발견하고 수정한 실제 결함")
add("batch_size = −1을 주면 narrow phase를 건너뛰고 교차 장면에 대해 separated=True를 반환하던 오류가 있었다. 반지름 0.002 mm인 직교 선분의 실제 clearance는 −0.004 mm였다. 현재 batch_size와 max_candidate_pairs는 양의 정수만 허용하며 음수·0·bool·비정수를 거부한다. 이 실패 조건을 독립 회귀 테스트에 고정했다.")
callout("간격 인증의 정확한 대상", "서로 다른 constant-radius fiber의 polyline capsule union이다. 같은 fiber의 자기접촉, 실제 표면 압착·접촉력, B-spline 변환 후 형상은 각각 별도 검사 대상이다. Spline export는 14쪽에서 이 하한을 전달한다.")

# 11 — Complete hierarchy refinement.
title(11, "전체 계층의 sampling refinement")
fig("figures/hierarchy_v2/sampling_refinement.png",
    "기본·2배·4배의 전체 계층을 다시 생성한 결과. 거리, 총 길이, tangent tensor가 함께 변하는 정도를 기록했다. 원사 중심선만 조밀하게 만든 결과가 아니다.", maxh=207)
rows = []
for key, label in CASES:
    r = REFINE[key]
    c1, c2 = r["comparisons"]
    rows.append([label, "/".join(str(v) for v in r["samples_per_crossing"]),
                 f"{c1['max_parameter_matched_centerline_distance_mm'] * 1000:.5f}",
                 f"{c2['max_parameter_matched_centerline_distance_mm'] * 1000:.5f}",
                 f"{c2['relative_total_length_change']:.2e}"])
table(["예제", "samples/crossing", "1→2 거리 μm", "2→4 거리 μm", "2→4 상대 길이"],
      rows, [163, 103, 78, 78, FW - 422])
add("기준은 adaptive refinement 후 실제 수락된 baseline mesh다. 요청 sampling이 서로 달라도 같은 mesh로 자동 승격될 수 있으므로, 그런 두 요청을 서로 다른 해상도로 비교하지 않도록 했다. 각 curve의 대응 매개변수와 union knot를 사용해 위치를 비교한다.")
equation(r"\delta_L=\frac{|L_f-L_c|}{L_f},\qquad \delta_C=\|\mathbf{C}_f-\mathbf{C}_c\|_F")
add("2→4 단계의 최대 대응 중심선 차이는 약 0.00695–0.03887 μm였다. 같은 단계에서 상대 길이 변화는 약 1.10×10⁻⁶–3.09×10⁻⁵였다. 이 값은 계산된 두 polyline 사이의 관측된 차이이며, 계산하지 않은 continuum limit에 대한 엄밀한 오차 상한은 아니다.")
callout("Sampling과 광학 정확도의 관계", "곡선 위치의 변화가 작아도 파동 위상·좁은 간격의 광학 반응이 민감할 수 있다. 후속 단계에서는 기하 refinement와 광학 출력 refinement를 함께 비교해야 한다. 이 표를 즉시 외관 정확도의 보증으로 사용하지 않는다.")

# 12 — Optical scene contract.
title(12, "OpticalScene: 공통 입력과 provenance")
table(["타입", "필수 데이터", "검증하는 계약"], [
    ["MaterialSpectrum", "material ID, λ, n, κ, source, status", "진공 nm; passive scalar index; 범위 밖 외삽 거부"],
    ["OpticalFiber", "fiber/yarn/ply/material IDs, 좌표, r, basis", "mm; 원형·일정 반지름; 부모·material 참조 유효"],
    ["OpticalScene", "fibers, materials, host n, schema, provenance", "immutable arrays; canonical JSON hash"],
    ["BundleSection", "plane frame, circles/IDs, eligibility, diagnostics", "선택한 모든 fiber의 교차·기울기·곡률·간격"],
    ["Mitsuba manifest", "group별 curve file, λ, 실제 상수, bounds", "file/manifest/scene SHA와 fiber ID 추적"],
], [100, 196, FW - 296])
sub("혼방은 개별 fiber의 재료 배치")
add("같은 기하에서도 A/B 재료의 fiber별 할당을 바꿀 수 있다. 혼합비 하나에서 임의의 유효 굴절률을 만들어 넣지 않는다. 따라서 core와 표면에 어느 재료가 있는지, 같은 비율에서 공간 배열이 달라지는지 같은 질문을 독립적으로 설계할 수 있다.")
sub("엄격하게 거부하는 입력")
add("NaN/Inf, 비양수 반지름·굴절률, 음의 κ, 중복 ID, 없는 material 참조, 하나의 ply가 두 yarn을 부모로 갖는 상태, 0 길이 segment, 정렬되지 않은 파장, 알 수 없는 schema/curve basis를 거부한다. 조용한 단위 변경이나 spectral extrapolation도 허용하지 않는다.")
table(["단위·convention", "값", "이유"], [
    ["Geometry", "mm", "반지름·흡수 길이·renderer 좌표를 하나의 기준으로 연결"],
    ["Wavelength", "vacuum nm", "host-medium 파장과 구분"],
    ["Complex index", "n + iκ, exp(−iωt)", "κ ≥ 0에서 감쇠하는 passive convention"],
    ["Schema", "textile.optical_scene/2.0", "미지원 데이터의 암묵적 해석 방지"],
], [115, 172, FW - 287])
add("스펙트럼은 등방성 scalar 표현이다. 선형 보간은 주어진 구간 안에서만 수행한다. Kramers–Kronig 일관성, 복굴절, 실제 섬유 단면·거칠기 분포가 이 자료 구조만으로 검증되지는 않는다.")
add("기준 파일: textile_sim/optical_scene.py, data/optical_bridge_v2/fabric_scene.json. Hash는 데이터가 섞이거나 변형된 경우를 추적하며 물리 측정의 진실성을 외부 인증하는 수단은 아니다.", "SmallV2")

# 13 — Absorption units and material-radius groups.
title(13, "흡수·매질·반지름을 일관되게 변환")
equation(r"\mu_a[\mathrm{mm}^{-1}]=\frac{4\pi\kappa}{\lambda_{0,\mathrm{nm}}10^{-6}},\qquad I(L)=I_0e^{-\mu_aL}")
equation(r"\lambda_h[\mu\mathrm{m}]=\frac{10^{-3}\lambda_{0,\mathrm{nm}}}{n_h},\qquad m=\frac{n+i\kappa}{n_h}")
add("기존 2D Maxwell solver는 background index 1로 쓰인 식이다. 실제 host index n<sub>h</sub>를 사용하려면 매질 파장과 상대 굴절률을 위와 같이 전달한다. 좌표·반지름은 mm에서 μm로 변환한다. Ray engine에는 절대 n, n<sub>h</sub>, μm⁻¹로 바꾼 흡수계수를 따로 넘긴다.")
equation(r"\sigma_{a,\mathrm{shader}}=\mu_a\,r")
add("Mitsuba 3.9.1 hair.cpp의 내부 경로 길이는 반지름 1인 단면으로 정규화되어 있다. 따라서 물리 μ<sub>a</sub>를 그대로 넣으면 안 된다. Material과 radius가 모두 같아야 하나의 BSDF 그룹으로 묶을 수 있다. 이 변환은 pinned 공식 소스에서 확인했다. [11,12]")
export = OPT["mitsuba_exports"][0]
table(["450 nm 그룹", "반지름 μm", "fibers", "n", "μa mm⁻¹", "shader σa"],
      [[g["material_id"].replace("synthetic_", "합성 "), f"{g['radius_mm'] * 1000:.0f}",
        str(g["fiber_count"]), f"{g['n_real']:.2f}", f"{g['absorption_per_mm']:.1f}",
        f"{g['absorption_per_mm'] * g['radius_mm']:.3f}"] for g in export["groups"]],
      [128, 76, 57, 65, 83, FW - 409])
sub("Backend별 domain은 다르다")
add("Wave solver는 passive complex index를 직접 사용한다. Ray와 hair는 실수 Fresnel + Beer absorption 근사이며 기본 κ/n 제한은 0.01이다. 이 값은 사용 domain을 명시하는 임계값이지 모든 장면에서 일정 오차를 보장하는 물리 법칙이 아니다. 강한 흡수체는 이 adapter에서 거부한다.")
callout("실크·코튼·큐프라라는 이름을 붙이기 전", "이 실행의 A/B는 단위·재료 전달을 확인하려고 정의한 합성 유전체다. 실제 소재의 분광 복소 굴절률, 표면 상태, 비원형 단면과 구조 통계를 확보한 뒤 해당 소재라고 검증해야 한다.")

# 14 — Spline and quantization bound.
title(14, "Spline export의 형상 오차를 전달")
add("Polyline 정점을 cubic B-spline control point로 해석하면 원래 선분과 다른 곡선이 생긴다. Adapter는 양 끝에 선형 외삽 control point를 하나씩 추가해 끝점 위치를 유지하고, 변환 오차를 manifest에 기록한다. P₀…P₃로 정의되는 Q(t)와 원래 chord L(t)에 대해 다음 관계가 성립한다.")
equation(r"Q(t)-L(t)=B_0(t)\Delta^2P_0+B_3(t)\Delta^2P_1")
equation(r"B_0,B_3\geq0,\ B_0+B_3\leq\frac{1}{6}\quad\Rightarrow\quad\epsilon_s\leq\frac{1}{6}\max_j\|\Delta^2P_j\|")
add("Pinned bsplinecurve.cpp loader는 control을 float32로 저장한다. B-spline이 nonnegative partition of unity이므로 control의 최대 float32 변위가 spline 중심선의 추가 변위 상한이 된다. 반지름 반올림도 tube 두께 오차에 따로 더한다. [12]")
equation(r"g_{\mathrm{export}}\geq g_{\mathrm{source}}-2(\epsilon_s+\epsilon_{c32}+\epsilon_{r32})")
max_s = max(g["max_centerline_smoothing_bound_mm"] for g in export["groups"])
table(["98-fiber 장면의 실제 값", "수치"], [
    ["원본 polyline 표면 간격 하한", f"{OPT['fabric_polyline_clearance']['minimum_clearance_lower_bound_mm'] * 1000:.6f} μm"],
    ["가장 큰 smoothing 중심선 상한", f"{max_s * 1000:.8f} μm"],
    ["가장 큰 combined tube 변위 상한", f"{export['max_tube_displacement_bound_mm'] * 1000:.8f} μm"],
    ["Export 후 서로 다른 tube 간격 하한", f"{export['exported_tube_separation_lower_bound_mm'] * 1000:.8f} μm"],
], [321, FW - 321])
add("같은 자료를 독립 리뷰에서 다시 읽어 fiber별 변환 오차와 원본 간격을 재계산했다. Source capsule 검사의 212,657쌍과 manifest의 각 material/radius 그룹이 일치함을 확인했다.")
callout("이 상한이 설명하는 정확한 범위", "저장된 float32 control로 정의되는 이상적인 constant-radius spline tube의 기하적 분리다. 렌더러가 수행하는 모든 부동소수점 ray traversal/intersection 연산의 오차를 interval arithmetic으로 제한한 것은 아니다. 같은 fiber의 자기접촉도 이 bound의 대상이 아니다.")
add("변환 후 간격이 음수로 내려가면 기존 source 인증만으로 export가 안전하다고 판단하지 않는다. Sampling을 바꾸거나 더 작은 smoothing tolerance를 요구하고 다시 검사해야 한다.", "SmallV2")

# 15 — 3D to 2D validity.
title(15, "3D 단면을 2D 원통 문제로 줄일 조건")
equation(r"a=\frac{r}{|\mathbf{t}\cdot\mathbf{n}|},\qquad b=r,\qquad\frac{A_{\mathrm{ellipse}}}{A_{\mathrm{circle}}}=\frac{1}{|\cos\beta|}")
add("비스듬한 원형 원통을 자르면 타원이 된다. 위 식은 국소 tangent cylinder의 단면이다. 곡률이 있는 실제 tube의 전체 교차가 정확한 타원이라는 뜻은 아니다. 기존 2D solver가 가정하는 무한 평행 원형 원통은 유한 직물의 임의 단면에 자동으로 적용할 수 없다.")
fig("data/optical_bridge_v2/optical_bridge_diagnostics.png",
    "실제 sweep: 비스듬한 절단의 타원 면적비, twist 증가 시 local tilt, 98-fiber 장면의 방향 통계. 그림은 section 유효성·구조를 진단하며 전체 3D 파동 정확도를 보여주는 결과가 아니다.", maxh=180)
table(["모드", "허용 기준", "판단의 의미"], [
    ["strict", "수치 허용오차 안의 straight/parallel bundle", "국소 형상이 2D 가정에 적합"],
    ["local_parallel", "사용자가 허용한 tilt·곡률·중심선 편차", "명시적으로 요청한 근사; 3D wave error 보증 없음"],
], [93, 203, FW - 296])
add("선택한 모든 fiber에 대해 교차 1회, 축 방향 support window, tilt, window 내 tangent 변화·중심선 편차, 원형 단면과 circle 간격을 확인한다. 실패한 fiber를 조용히 빼고 남은 부분만 계산하지 않는다.")
table(["Tilt", "0°", "5°", "15°", "30°", "60°"],
      [["타원/원 면적비", "1.000000", "1.003820", "1.035276", "1.154701", "2.000000"],
       ["strict 허용", "예", "아니오", "아니오", "아니오", "아니오"]],
      [114, 77, 77, 77, 77, FW - 422])
add("생성 yarn의 fiber twist를 0.1/0.5/1/2 turns/mm로 바꿨을 때 최대 local tilt는 0.432/2.158/4.301/8.488°였다. 모두 strict에서 거부됐다. 작은 타원 면적 오차만으로 상대 fiber 방향·입사 위상·유한 길이 효과가 작다고 결론낼 수 없다.")

# 16 — Actual wave/ray integration.
title(16, "생성된 보정용 yarn에서 Maxwell / ray 실행")
add("한 ply의 직선 7-fiber bundle을 hierarchy API로 만들었다. Fiber 반지름 4 μm, 중심 간격 12 μm, 길이 0.3 mm이며 A 4개와 B 3개를 교대로 배치했다. Strict section을 통과한 같은 IDs/반지름/재료에서 450·550·650 nm와 Ez·Hz 두 편광을 계산했다.")
table(["λ nm", "편광", "Wave Csca μm", "Wave Cabs μm", "flux 상대 잔차", "ray 흡수비"],
      [[str(r["wavelength_nm_vacuum"]), r["polarization"], f"{r['wave_Csca_um']:.5f}",
        f"{r['wave_Cabs_um']:.5f}", f"{r['wave_relative_flux_residual']:.2e}",
        f"{r['ray_energy']['absorbed']:.6f}"] for r in OPT["calibration_solver_runs"]],
      [56, 48, 108, 104, 106, FW - 422])
equation(r"C_{\mathrm{ext}}=C_{\mathrm{sca}}+C_{\mathrm{abs}}\quad\mathrm{(2D\ length\ units)}")
equation(r"P_{\mathrm{back}}+P_{\mathrm{forward,collided}}+P_{\mathrm{gap}}+P_{\mathrm{abs}}=1")
add("조건당 50,000 rays, 총 300,000 rays를 실행했다. Wave의 최대 local/global flux 상대 잔차는 8.49×10⁻¹⁵였고 ray는 각 표본의 에너지 분배를 추적해 잔차 0을 기록했다. 이는 유한 표본 추정의 불확실성이 0이라는 뜻은 아니다.")
sub("이 실험이 검증한 연결")
add("HierarchyGeometry → OpticalScene → BundleSection → wave_inputs/ray_inputs → 실제 solver의 전체 경로에서 서로 다른 재료와 단위가 전달된다. Geometry·material 데이터가 광학 계산까지 도달했는지를 확인하는 통합 실험이다.")
sub("서로 다른 양을 같은 반사율로 비교하지 않는다")
add("평면파 원통 문제의 C<sub>sca</sub>, C<sub>abs</sub>는 2D 단면적이므로 길이 단위를 가진다. 유한 폭 ray ensemble의 energy fraction은 입사 sampling에 대한 무차원 비율이다. 같은 이름의 R/T로 놓고 단순 차이를 계산하면 normalization을 혼동한다. 동등한 입사장·수집각·단위를 정의한 비교가 후속 과제다.")
callout("해석의 한계", "기준 2D Maxwell 모델은 원형·평행·무한 길이 조건에 대한 계산이다. 이 결과를 3D 직물 전체의 BSDF에 결합하거나 Yu 2025의 전체 ray–wave shader를 재현한 것으로 해석하지 않는다. [10]")

# 17 — Actual 3D render preview.
title(17, "98-fiber 혼합 재료 장면의 실제 렌더")
fig("data/optical_bridge_v2/fabric_optical_bridge.png",
    "Mitsuba 3.9.1 llvm_ad_rgb, 128×128, 64 spp, 450/650 nm 반사·투과. 모든 패널은 동일 표시 exposure. 밝은 부분은 PNG 표시에서 clip될 수 있으며 원본 linear.npy는 보존한다. 입자성은 유한 Monte Carlo 표본의 영향이다.", maxh=330)
table(["조건", "seed", "평균 linear camera radiance", "최대 linear 값"],
      [[f"{r['wavelength_nm_vacuum']:.0f} nm / " + ("반사" if r["mode"] == "reflection" else "투과"),
        str(r["seed"]), f"{r['mean_linear']:.6f}", f"{r['max_linear']:.4f}"]
       for r in OPT["actual_render_runs"]], [161, 63, 174, FW - 398])
add("이 장면은 2/2 twill의 3 warp × 4 weft, yarn당 2 plies × 7 fibers다. Warp 3 μm, weft 4 μm 반지름과 두 synthetic material을 4개 그룹으로 전달했다. 실제 광학 constant는 manifest에서 읽으며, 렌더 설정의 단일 material 기본값으로 덮어쓰지 않는다.")
add("현재 renderer는 선택한 파장의 물리 상수를 RGB 세 채널에 동일하게 넣은 단일 파장 proxy다. 표의 평균은 카메라 복사휘도 통계이며 hemispherical 반사율·투과율이 아니다. R+T 보존 검증이나 spectral color 재현에 이 수치를 사용하지 않는다. 서로 다른 seed의 작은 파장별 차이도 유의한 효과라고 주장하지 않는다.", "SmallV2")

# 18 — Descriptive microstructure, not an automatic BSDF.
title(18, "구조 통계를 광학 집계 모델로 연결하기")
equation(r"\mathbf{C}_L=\frac{\sum_i\ell_i\mathbf{t}_i\mathbf{t}_i^T}{\sum_i\ell_i},\qquad\mathbf{C}_V=\frac{\sum_i\pi r_i^2\ell_i\mathbf{t}_i\mathbf{t}_i^T}{\sum_i\pi r_i^2\ell_i}")
add("길이 가중 C<sub>L</sub>와 체적 proxy 가중 C<sub>V</sub>를 all/material/family/yarn/ply마다 계산한다. 두 tensor는 PSD, trace 1이며 회전 R에 대해 C′ = RCRᵀ로 변환된다. Segment를 불균등하게 쪼개도 같은 직선 geometry라면 통계는 변하지 않아야 한다.")
equation(r"A_{\perp}(\omega)=\sum_i2r_i\ell_i\sqrt{1-(\omega\cdot\mathbf{t}_i)^2}")
add("각 원통 segment의 가리지 않은 lateral projected area를 더한다. 끝면, 가림, joint, 다중 산란, wave coherence를 포함하지 않으므로 합쳐진 투영 면적이나 opacity/extinction/BSDF와 같지 않다. ∑πr²ℓ도 segment cylinder volume 합이며 정확한 union solid volume은 아니다.")
a = STAT["groups"]["all"]
table(["98-fiber 장면 통계", "값"], [
    ["segment 수 / 총 중심선 길이", f"{a['segment_count']:,} / {a['length_mm']:.6f} mm"],
    ["길이 가중 tensor의 diagonal", ", ".join(f"{a['orientation_length'][i][i]:.6f}" for i in range(3))],
    ["체적 가중 tensor의 eigenvalues", ", ".join(f"{v:.6f}" for v in a["orientation_volume_eigenvalues"])],
    ["lateral projected sums, x / y / z", ", ".join(f"{v:.6f}" for v in a["unoccluded_lateral_projected_area_mm2"]) + " mm²"],
], [239, FW - 239])
sub("SGGX는 별도 모델 식별 단계")
add("같은 tangent second moment라도 공간 상관, 물질 흡수, 표면 상태가 다르면 산란이 달라질 수 있다. 따라서 C를 바로 SGGX 행렬이라고 선언하지 않는다. 향후 projected-area distribution, density/roughness, single/multiple scattering 항을 명시하고 기준 각도별 산란에 맞춰 fitting해야 한다. [2,3]")
table(["후속 집계 비교", "평가할 양"], [
    ["Explicit fibers ↔ ply/SGGX proxy", "같은 구조·재료·광원에서 lobe 위치, 폭, 강도, 투과 gap"],
    ["국소 wave ↔ ray reference", "같은 입사장과 수집각에서 각도 분포·흡수·phase 민감도"],
    ["대규모 LOD", "view distance별 오차, 메모리, 시간, 연속적 전환"],
], [223, FW - 223])

# 19 — Testing and independent review.
title(19, "수치 검증과 독립 리뷰 결과")
callout(f"통합 결과: {TEST['tests_run']} tests 통과", f"data/final_test_summary.json 기준 failures {TEST['failures']}, errors {TEST['errors']}, skipped {TEST['skipped']}. Python {TEST['python']}, 실행시간 {TEST['elapsed_seconds']:.3f} s. 이 시간은 해당 실행 환경의 기록이며 성능 보장값이 아니다.")
table(["새 모듈 검증군", "리뷰 당시 수", "독립적인 기대값/실패 조건"], [
    ["weave_draft", "8", "직사각 축, repeat, family exchange, lift-plan round-trip"],
    ["hierarchy", "17", "해석적 helix/RMF, 부모 호길이, 내부 선분 교차, refinement"],
    ["optical_scene", "27", "Beer 변환, spline/float32 bound, domain 거부, 실제 backend"],
    ["independent v2 review", "7", "실제 결함 회귀, nested mirror, 순서/분할 불변, 실제 solver similarity"],
], [143, 76, FW - 219])
add("위 네 검증군 59개는 독립 리뷰 시점에 함께 실행했다. 전체 개수는 legacy 및 추가 runner 검증을 포함한 최신 통합 JSON에서 읽는다. tests 수는 서로 더해서 별도의 물리 검증 횟수로 해석하지 않는다.", "SmallV2")
sub("1.7배 similarity를 실제 adapter+solver 경로에서 확인")
add("두 반지름과 복소 굴절률을 가진 fiber, n<sub>host</sub> = 1.23 장면에서 geometry와 진공 파장을 함께 1.7배로 바꾸었다. 대응 파장의 n+iκ는 유지했다. Wave의 길이 단위 단면적은 1.7배가 되고, Beer가 포함된 무차원 ray 분율은 같아야 한다.")
table(["독립 관측", "결과"], [
    ["Ez Csca / Cext / Cabs 비", "1.699999999999997 / 1.6999999999999995 / 1.700000000000231"],
    ["Hz Csca / Cext / Cabs 비", "1.6999999999999968 / 1.6999999999999993 / 1.7000000000002191"],
    ["ray fraction", "같은 1,500-ray seed에서 11 decimal places까지 불변"],
], [162, FW - 162])
sub("발견한 결함을 회귀로 고정")
add("음수 batch size가 충돌 검사 자체를 우회하던 오류를 수정했다. Frozen dataclass의 owning ndarray가 setflags(write=True)로 다시 수정 가능했던 문제는 immutable bytes backing으로 수정했다. 이는 실제 실패 fixture에서 확인한 수정이며, 모든 테스트를 구현의 반환값만 되풀이하는 방식으로 만들지 않았다.")
add("리뷰는 저장된 98-fiber geometry→scene의 모든 좌표·반지름·IDs를 다시 비교하고 spline separation bound도 재계산했다. Hash와 검사 기록은 notes/review_engine_v2.md 및 최종 summary에 있다.", "SmallV2")

# 20 — Research plan with useful gates.
title(20, "다음 연구를 어디에 집중할 것인가")
add("다음 우선순위는 자유도를 늘리는 것보다, 현재의 공통 기하에서 광학 근사와 추가 관측의 가치를 측정하는 것이다. Dyeing/fading은 계속 분리하고 첫 물리 검증은 소재·직조·공정 범위를 좁힌 패치로 진행한다.")
table(["단계", "실행할 연구", "통과 기준"], [
    ["A · 구조 기준", "같은 반지름·pitch·체적 범위에서 twist, packing, migration을 한 번에 하나씩 변경", "sampling·간격·방향 통계를 함께 보고; 실제 현미경 구조와 차이 명시"],
    ["B · 광학 기준", "동일 입사장/수집각에서 국소 wave와 ray 비교; 3D explicit reference 수렴", "에너지 normalization 일치, angular lobe와 흡수의 오차, 반복 seed 신뢰구간"],
    ["C · 집계 모델", "ply/SGGX 또는 검증된 proxy를 explicit reference에 fit", "미사용 geometry·조명·각도에서 외관 오차와 속도 이득"],
    ["D · 실제 소재", "한 섬유·몇 가지 원사/직조 시편의 반사·투과·구조 측정", "실측 optical constants와 모델 오차를 분리; 독립 원단 held-out"],
    ["E · 관측 설계", "좋은 다중조명 RGB에 각도/파장/편광 관측 추가", "같은 시간·광량·detector 예산에서 미관측 외관 예측 개선"],
], [73, 227, FW - 300])
sub("가능성이 높은 첫 질문")
callout("같은 재료 비율, 다른 fiber 배치", "A/B 혼방의 부피 비율이 같고 정면 RGB가 비슷한 두 yarn을 만들되, A가 표면에 많은 경우와 내부에 많은 경우를 구분한다. 반사·투과의 각도/파장 응답이 이를 얼마나 분리하는지 조사한다. 비율·구조·광원·잡음을 통제해야 하며, 이것은 아직 실행 전 가설이다.")
add("이 가설은 material ID를 fiber별로 보존하는 v2 구조와 직접 연결된다. 단순 평균 굴절률로 섞으면 없어지는 공간 정보가 실제로 관측 가능한지 확인할 수 있다. 단, 무작위 배열까지 일반화하거나 실크/코튼 혼방을 정확히 맞춘다는 결론은 실험 후에 내려야 한다.")
sub("Meta-optics로 이어지는 결정")
add("먼저 기존 광학계로 필요한 관측 채널을 찾는다. 그 다음 메타표면이 같은 예산에서 촬영 수·시간·부피를 줄이는지, 검출기 픽셀과 광량을 유용한 채널에 더 잘 배분하는지 비교한다. VIS 외관에는 VIS 관측이 직접 대응하며 IR은 독립 시편에서 추가 정보를 주는지 확인한 뒤 연결한다.")

# 21 — Reproducibility and version control.
title(21, "재현·버전 관리·실험 기록")
add(f"저장소: <link href='{REPO}' color='#31588a'>{REPO}</link><br/>저장소 식별자는 확인된 private repository 기준이다. 원격 파일의 동기화 이력과 커밋은 저장소의 작업 로그에서 확인한다. 보고서의 수치 입력은 아래 저장된 JSON이며 generator는 새 시뮬레이션을 실행하지 않는다.", "SmallV2")
table(["경로", "역할"], [
    ["textile_sim/weave_draft.py · hierarchy.py", "위상, 계층, sampling, 전역 검사"],
    ["textile_sim/optical_scene.py", "공통 scene·단면·material/radius export·통계"],
    ["examples/hierarchy/*.json", "다섯 예제의 입력 파라미터"],
    ["data/hierarchy_v2/", "NPZ/JSON 기하, metrics, refinement"],
    ["data/optical_bridge_v2/", "기준해, scene, manifests, linear render·PNG"],
    ["notes/*_v2.md · notes/optical_bridge.md", "문헌, 수학, 독립 리뷰, 구현 범위"],
    ["data/final_test_summary.json", "최종 suite 결과와 검사한 소스 SHA-256"],
    ["references/user_provided/", "첨부 원문과 hash provenance"],
], [271, FW - 271])
sub("기본 실행 명령")
code("python -m pip install -r requirements.txt\npython -m unittest discover -s tests -v\npython run_engine_v2.py --help\npython run_optical_bridge_experiments.py --output data/optical_bridge_v2\npython report/build_engine_v2_report.py")
add("Geometry runner의 선택 가능한 단계·기본 출력은 --help와 README를 따른다. Optical smoke에는 --skip-render를 사용할 수 있지만, 저장된 보고서의 네 장면은 실제 render를 포함한 결과다. 재현 환경의 Mitsuba version/variant, seed, 광원·카메라, exposure, spp, 해상도는 각 render JSON에 남는다.", "SmallV2")
sub("실험을 바꿀 때 남길 최소 기록")
add("입력 config와 seed → source revision/hash → 생성 geometry와 audit → scene/manifest hash → backend 설정 → raw 선형 결과 → 요약 metrics → 비교 그림 → 관측·한계·수정 사유를 순서대로 남긴다. 결과가 좋지 않은 실행도 실패 조건과 함께 log에 남겨야 다음 버전에서 모델이 바뀐 이유를 추적할 수 있다.")
add("이 보고서의 재생성에는 Noto Sans KR regular/bold 파일이 필요하다. TEXTILE_REPORT_FONT_DIR로 폴더를 지정할 수 있다. 완성된 PDF에는 사용 glyph가 포함되어 있어 열람 시 별도 폰트 설치가 필요 없다. 기존 report/build_report.py와 v1 PDF는 변경하지 않았다.", "SmallV2")

# 22 — Primary bibliography.
title(22, "주요 1차 자료와 코드 출처", "문헌별 열람/실행 수준은 3쪽 및 notes/literature_engine_v2.md에서 함께 확인한다.")
refs = [
    ("[1] Tang et al. FabricGen. CVPR 2026.",
     "https://lxtyin.ac.cn/projects/fabricgen/", "본문 + 공식 supplementary의 procedural 구조·렌더링 절. arXiv:2603.07240."),
    ("[2] Tang et al. Woven Fabric Capture with a Reflection-Transmission Photo Pair. SIGGRAPH 2024. DOI 10.1145/3641519.3657410.",
     "https://arxiv.org/abs/2406.19398v3", "공식 코드 github.com/lxtyin/FabricBTDF-Recovery; 검토 revision 67150eeca9f28b85f8fe21d40d888d34bd4d3b25, GPL-3.0."),
    ("[3] Montazeri et al. A Practical Ply-Based Appearance Model of Woven Fabrics. 2020. DOI 10.1145/3414685.3417777.",
     "https://shuangz.com/projects/practical_cloth-sa20/", "Primary PDF §§3.1–3.3: crossing과 slope, ply 표현."),
    ("[4] Trunz et al. Neural inverse procedural modeling of knitting yarns from images. 2023.",
     "https://arxiv.org/abs/2303.00154", "Procedural generation §§3.1–3.3; inverse network 미실행."),
    ("[5] Wu et al. Weavecraft: An Interactive Design and Simulation Tool for 3D Weaving. TOG 39(6), 2020. DOI 10.1145/3414685.3417865.",
     "https://www.cs.cornell.edu/projects/weavecraft/", "공식 프로젝트/저자 설명. 본문 전체와 원저자 simulation 실행은 미완료."),
    ("[6] TexGen — official source and engineering textile geometry interfaces.",
     "https://github.com/louisepb/TexGen", "README, Core/Yarn.h, weave interface 검토. Compile/import/vendor 없음."),
    ("[7] Zhao et al. Fitting Procedural Yarn Models for Realistic Cloth Rendering. TOG 35(4), 2016. DOI 10.1145/2897824.2925932.",
     "https://projects.shuangz.com/procyarn-sg16/", "공식 CT-cloth project 및 code/data route 검토. 원본 fitting 미실행."),
    ("[8] Li et al. Fiber-level Woven Fabric Capture. Author publication page, 2026. DOI 10.1145/3816036.",
     "https://www.rendering-zixuan.com/paper_pages/FiberFabric/", "이전 preprint arXiv:2409.06368; 주요 reconstruction 절과 현재 출판 정보 검토."),
    ("[9] Wang et al. Computation of Rotation Minimizing Frames. TOG, 2008. DOI 10.1145/1330511.1330513.",
     "https://www.microsoft.com/en-us/research/publication/computation-rotation-minimizing-frames/", "Double-reflection RMF의 독립 구현과 analytic helix 비교."),
    ("[10] Yu et al. Realistic Cloth Rendering with a Ray-Wave Hybrid Shading Model. 2025. DOI 10.1145/3763359.",
     "https://blaire9989.github.io/assets/3_RayWaveFabric/project.html", "사용자가 지정한 ray–wave 연구 기준. v2는 전체 shader 재현을 주장하지 않음."),
    ("[11] Chiang et al. A Practical and Controllable Hair and Fur Model for Production Path Tracing. 2016.",
     "https://www.disneyanimation.com/publications/a-practical-and-controllable-hair-and-fur-model-for-production-path-tracing/", "Mitsuba hair BSDF의 원 모델. 원단 소재별 실측 정확성은 별도 검증."),
    ("[12] Mitsuba 3.9.1 pinned source audit.",
     "https://github.com/mitsuba-renderer/mitsuba3/tree/v3.9.1/src", "bsdfs/hair.cpp: 반지름 정규화 흡수. shapes/bsplinecurve.cpp: curve와 float32 loader. 실제 v2 renderer로 실행."),
]
for head, url, note in refs:
    add(f"<b>{escape(head)}</b><br/><link href='{url}' color='#31588a'>{escape(url)}</link><br/>{escape(note)}", "RefV2")
add("외부 저자 코드·dataset을 재배포하지 않았다. 이 저장소의 계층/bridge는 독립 구현이며 논문의 개념 참고와 방법 재현을 구분한다. User-provided PDF는 별도 출처·hash 기록과 함께 보존한다.", "CaptionV2")


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(OUTPUT), pagesize=A4, leftMargin=48, rightMargin=48,
                            topMargin=40, bottomMargin=51,
                            title=f"원사에서 직물까지: 계층 기하와 광학 엔진 v{VERSION}",
                            author="Textile Optics Engine research workspace",
                            subject="실행된 계층 기하·광학 bridge·수치 검증 및 연구 설계",
                            pageCompression=1)
    doc.build(STORY, onFirstPage=footer, onLaterPages=footer)
    print(str(OUTPUT))
    print(json.dumps({"planned_pages": len(PAGE_TITLES), "version": VERSION,
                      "tests_run": TEST["tests_run"], "figures_from_saved_artifacts": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
