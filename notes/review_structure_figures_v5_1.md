# v0.5.1 구조 맵 시각화의 독립 검토

## 1. 검토 목적과 reference의 의미

사용자가 올린 Figure 5는 3-ply basket weave의 normal, orientation,
height를 나란히 보여준다. 제공 이미지의 SHA-256은
`19e8ff5a7565eaec91bd02f39342df3b5d7e57a57b87ed07135ea49ff9322822`다.
캡션은 해당 파라미터가 supplementary material에 있음을 설명하지만,
제공 이미지 자체에는 좌표계·채널 encoding·높이 범위가 없다.

새 그림은 저장소의 실제 계층 기하를 같은 종류의 진단 맵으로 보여주는
작업이다. 원 Figure 5와 동일한 파라미터나 색 encoding을 복원했다는
의미로 사용하지 않는다. Source audit에서 확인한 FabricGen의 방향은
ply orientation을 표면법선 주변으로 twist angle만큼 회전한 fiber
orientation이다. 새 맵의 ply 중심선 tangent와 이 값은 같은 정의가
아니다. 본 구현은 선택한 계층의 실제 중심선 tangent를 보존하고,
표시에서 그 XY 투영을 무방향 축으로 읽는다.

참고 자료는 사용자가 제공한
[Figure 5 이미지](../references/user_provided/fabricgen_figure5_reference.png),
[provenance](../references/user_provided/figure5_reference_provenance.json),
[FabricGen PDF](../references/user_provided/Tang_FabricGen_Microstructure-Aware_Woven_Fabric_Generation_CVPR_2026_paper.pdf)의
§3 식 (1), §5.1 식 (3)–(6), Figure 5다. 원 논문의 파라미터 재현과
새 엔진의 진단 맵 생성은 별도 검증 과제다. 구현 범위와 광학 연결은
[시각화 설계 문서](../docs/VISUALIZATION_DESIGN_KO.md)에도 명시했다.

이 검토는 **형상·좌표·배열·시각적 encoding의 일관성**을 다룬다.
색·광택을 렌더링하거나 실제 섬유의 광학 상수를 추정하는 작업이 아니다.
v0.5의 동결된 기하·광학 source와 기존 실험 자료는 변경하지 않는다.

## 2. 사용한 기존 기하와 ply proxy의 범위

생성기의 입력은 기존
[`basket_rectangular_three_ply.json`](../examples/hierarchy/basket_rectangular_three_ply.json)이다.
동결된 `build_hierarchy`로 계층을 다시 만들고,
`data/structure_maps_v5_1/input_spec.json`에 설정을 복사 보존한다.
독립 초기 점검에서는 기존
`data/hierarchy_v2/basket_rectangular_three_ply/hierarchy_geometry.{json,npz}`도
읽어 아래 구조와 수치를 확인했다. 두 경로를 같은 파일 입력으로
표현하지 않는다. 새 자료는 각 맵 metadata에 실제 생성 기하의 hash,
부모 관계, 재료 lookup을 남긴다.

| 항목 | 기존 입력 값 |
|---|---:|
| 직조 | 3×2 rectangular basket, binary warp-over draft |
| 원사 | warp 6개 + weft 4개 |
| Ply | 원사마다 3개, 합계 30개 |
| Fiber | ply마다 7개, 합계 210개 |
| Fiber 정점 | 58,674개 |
| Fiber 반지름 | 2 μm |
| Ply 외피 반지름 | 8.5 μm |
| Warp / weft pitch | 0.18 / 0.20 mm |
| Nominal visible 영역 | 1.08 × 0.80 mm |
| 전체 fiber 좌표의 Z bounds | 약 −64.916∼+65.000 μm |

원본은 3-ply 원사라는 계층과 3×2 basket이라는 직조 grouping을 별도로
정의한다. 두 숫자의 의미를 혼용하지 않는다. 원사 끝에는 padding이
있으므로 전체 좌표 bounds와 nominal visible 영역도 구분한다.

`ply_envelope`는 부모 ply 중심선을 주위 섬유를 감싸는 반지름으로
둘러싼 **채워진 외피 proxy**다. 이 입력에서 7개 fiber 단면의 면적 합은
외피 원 단면의

\[
7\left(\frac{2}{8.5}\right)^2\simeq0.38754
\]

배다. 따라서 외피를 그리는 것은 실제 fiber 사이 공극을 채우는 다른
기하 표현이며, 실제 fiber surface의 확대 그림으로 표시하면 안 된다.
이 면적 비는 reference 단면의 비교값이며 변형 후 실제 packing fraction,
공극률 또는 광학 투과율을 측정한 값이 아니다.

`explicit_fiber`는 저장된 개별 fiber의 중심선과 반지름을 사용한다.
두 표현을 비교할 때 같은 world 좌표·camera crop·높이 범례를 유지하되,
외피 proxy의 차폐와 silhouette을 실제 섬유의 차폐와 동일하다고
해석하지 않는다. 여러 재료가 들어 있는 ply에는 단일 물질 ID를
임의로 붙이지 않고 자식 재료 목록과 혼합 상태를 보존한다.

### 별도 compact 예시

[Compact 입력](../examples/visualization/compact_three_ply_basket.json)은 기존
입력을 대체하지 않는다. 2×2 basket grouping, warp/weft 각각 8개,
pitch 80 μm, ply 중심 offset 14 μm, ply twist +6 turns/mm를 사용한다.
세 ply와 ply당 일곱 fiber라는 계층은 같지만 전체 객체는 원사 16개,
ply 48개, fiber 336개다. Nominal 영역은 0.64×0.64 mm다.

[설계 감사](../examples/visualization/compact_three_ply_basket_design_audit.json)는
서로 다른 fiber와 서로 다른 ply proxy에 대한 capsule separation의
보수적 하한을 각각 1 μm로 기록한다. 후보 집합에서 관측한 최소값
2.445/4.122 μm를 전체 pair의 정확한 최소값이라고 바꾸어 읽지 않는다.
이 검토는 그 탐색을 다시 실행하지 않는다. 원시 그림의 원사·ply·fiber
index와 재료 할당을 원본 설정과 대조하고, 설계 감사와 그림의 source
spec을 연결한다. Same-curve self-contact와 역학적 평형은 이 예시에서도
해결됐다고 주장하지 않는다.

## 3. 맵별 수학과 표시 계약

| 맵 | 원시 물리량 | 표시와 독립 검사 |
|---|---|---|
| Surface normal | world-space triangle geometric unit normal | \((\mathbf n+1)/2\)의 직접 RGB; 조명·gamma·sRGB 변환 없음 |
| Smooth normal | 별도 보간 normal, 제공되는 경우에만 | geometric normal과 다른 변수로 표시; 물리적 경계 법선으로 대체하지 않음 |
| Orientation | 선택한 계층의 directed world tangent | \(\theta=\operatorname{atan2}(t_y,t_x)\bmod\pi\)를 표시; \(\mathbf t\)와 \(-\mathbf t\)가 같은 축 |
| Height | 첫 가시 hit의 world Z, mm | μm로 단위 변환 후 같은 입력의 full/zoom·두 표현에 공통 범례 |
| Ray distance | 정규화된 ray의 origin부터 hit까지 거리, mm | height와 다른 배열; camera 위치 변경으로 값이 변함 |
| Object / parent / material ID | 정수 categorical ID와 lookup | 평균 ID 금지; proxy의 missing/mixed ID와 background를 valid mask로 구분 |
| Coverage | pixel 안의 supersample hit 비율 | silhouette antialiasing용 값; pixel-center의 valid mask와 다름 |

Normal은 world 축 기준이어야 한다. Camera 축을 RGB 축으로 쓰거나
그림을 위아래로 뒤집으면서 normal 성분을 그대로 두는 오류를 피한다.
Top-down 시점의 camera right는 +X, up은 +Y, view direction은 −Z이며
row 0은 가장 높은 Y 위치다. `imshow`의 origin과 extent, 방향 범례,
scale bar도 이 정의와 맞아야 한다.

Orientation의 projected length가 지정 threshold보다 작으면 XY 방향은
정의되지 않는다. 이때 임의 hue를 부여하지 않고 별도 undefined mask와
색을 사용한다. 원시 tangent의 단위 길이는 검사하지만
\(\mathbf n\cdot\mathbf t=0\)을 무조건 요구하지 않는다. 중심선 방향은
실제 표면 접평면 방향과 다른 계약이고, taper·곡선·ring 삼각화에 따른
차이도 있기 때문이다.

Pixel-center의 hit를 저장한 physical map과 supersampled 색 평균을
구분한다. Supersample을 먼저 각각 colorize한 뒤 색을 평균하는 것은
시각화의 antialiasing이다. 그 혼합 색을 하나의 실제 normal·tangent·ID로
역해석해서는 안 된다. Miss는 float map에서 NaN, ID에서 −1로 남기고,
zero normal이나 height 0으로 바꾸지 않는다. Valid한 mixed-material
ply의 material ID도 −1일 수 있으므로 **valid mask가 우선**이다.

경계의 저장 형식은 **straight RGBA**다. 부분적으로 덮인 pixel에서
hit mask를 \(m_j\), 각 supersample의 표시색을 \(c_j\)라 두면

\[
\alpha=\langle m_j\rangle,\qquad
c=\frac{\langle m_jc_j\rangle}{\alpha}\quad(\alpha>0).
\]

배경색 \(B\) 위에서 \(\alpha c+(1-\alpha)B\)를 한 번 적용한다.
검산기는 저장된 supersample을 별도로 읽어
\(\langle m_jc_j+(1-m_j)B\rangle\)를 직접 합산해 비교한다.
이 방식은 premultiplied RGB를 straight RGB로 잘못 저장해 경계가
두 번 어두워지는 오류를 검출한다. \(\alpha=0\)인 저장 RGB는 0이다.

방향색은 `twilight_shifted`를 phase 0.25만큼 순환 이동한 2,048-entry
LUT다. 범례와 맵이 같은 LUT를 사용한다. 이 색은 방향의 수치 encoding이며
원단색이나 물리적 radiance를 뜻하지 않는다. 높이의 공통 범위는 첫
ply surface의 Z bounds를 10 μm 간격으로 바깥쪽 확장해 정한다.
다음 기하 표현이 그 범위를 넘으면 생성기를 중단하며, 각 맵마다
새 최솟값·최댓값으로 정규화하지 않는다. Main과 compact는 서로 다른
설계이므로 각각 별도의 공통 범위인 ±70 μm와 ±60 μm를 사용한다.

## 4. 독립 검증 설계

일반 원시 검사에서는 데이터 파일과 source의 해시, 전체 배열 shape,
유한성·NaN mask, 정수 ID, normal/tangent 단위 길이, position의 Z와
height 일치, camera basis와 ray distance 일치, supersample coverage를
확인한다. Figure manifest에서는 공통 height 범위, 단위, normal transfer,
무방향 orientation, input/output file hash와 background 정의를 확인한다.

별도 해석적 oracle은 다음 두 조건을 사용한다.

1. **기울어진 평면:** \(z=ax+by+c\)인 두 삼각형을 top-down camera로
   관찰하면 pixel center의 height와
   \((-a,-b,1)/\sqrt{a^2+b^2+1}\) normal을 직접 계산할 수 있다.
   깊이와 world height의 혼동, image Y 뒤집기, geometric normal의
   방향 오류를 실제 ray 결과와 대조한다.
2. **앞뒤 평면의 차폐:** 같은 XY 범위를 덮는 두 평면 중 더 높은
   world-Z의 면이 선택되어야 한다. 면의 입력 순서만으로 object ID가
   결정되거나 뒷면 높이가 저장되지 않는지 확인한다.

이 oracle은 직물 producer의 기하 재생성 방법을 다시 구현하지 않는다.
알려진 기하의 정확한 답과 실제 ray intersection 결과를 비교한다.
이미 저장한 직물 그림의 조건 수와 oracle query 수, unit test 함수 수는
별도로 기록한다. 새 영상 렌더나 wave/volume 광학 검증으로 계산하지
않는다.

## 5. 물리적 해석의 한계

Normal/orientation/height map은 지정한 삼각형 surface의 기하 정보를
보여준다. 이 그림이 보기 좋다는 사실로 fiber packing·실물 구조·광택·
분광 반사·회절·촉감의 정확성을 입증할 수는 없다. 유한 원주·축 sampling,
parent envelope approximation, 오목한 내부와 보이지 않는 표면, crop
밖 구조의 영향은 별도로 남는다. 각도·파장 반응을 다루는 광학 엔진과
연결할 때에는 해당 엔진의 경계·단위·수렴 계약을 다시 확인해야 한다.

## 6. 감사 도중 발견한 저장 실패의 보존

첫 최종 자료 감사는 raw/SS/display의 12개 NPZ와 네 맵의 좌표·재료
할당·색 변환 검사를 지난 뒤 **hierarchy PDF의 byte hash 불일치로
중단**됐다. Manifest는 566,866 bytes를 기록했지만 실제 파일은
433,871 bytes였고, PDF 끝 표시인 `%%EOF`가 없었다. 나머지 여덟 개
그림 파일의 hash는 manifest와 일치했다.

이 실패는 검산기가 성공으로 덮어쓰지 않았다. 당시 manifest와 잘린
PDF, 관측한 모든 그림 파일의 hash·길이를
[거부 기록](../data/validation_v5_1/rejected_figure_serialization/rejection_summary.json)에
보존했다. 복사한 증거는 전체 생성 실험의 독립 재실행 bundle이 아니며,
원시 맵은 당시 manifest의 hash로 연결된다. 파일이 잘린 원인은 이
관측만으로 특정하지 않았다. 본 검토의 네 corruption 테스트는 메모리
배열만 바꾸며 canonical 파일에 쓰지 않는다.

실패한 실행은 저장자료를 읽기만 했다. 해석적 oracle은 전체 저장자료
검사를 통과한 뒤 실행하도록 배치했으므로, 이 시도의 추가 기하 query와
조명 렌더는 모두 0회다. 그림 복구에는 보존된 display 배열을 다시
배치하는 `--replot-from` 경로를 사용하며, geometry를 다시 관찰한
자료나 추가 광학 실험으로 계산하지 않는다.

후속 확인에서도 다른 그림 export 두 건의 truncation을 관측했다.
각 시점의 manifest를 함께 보존해 어느 기대 hash와 비교했는지
구분했다.

| 거부된 export | Manifest 길이 | 실제 길이 | 별도 구조 확인 |
|---|---:|---:|---|
| Main hierarchy PDF | 566,866 bytes | 433,871 bytes | PDF EOF 없음 |
| Main hierarchy SVG, 후속 replot | 778,425 bytes | 581,192 bytes | XML의 line 670에서 닫히지 않은 token |
| Compact material-detail PDF | 635,100 bytes | 124,685 bytes | PDF EOF 없음 |

후속 원본은
[main SVG 거부 기록](../data/validation_v5_1/rejected_figure_serialization/followup_main_svg/rejection_summary.json)과
[compact PDF 거부 기록](../data/validation_v5_1/rejected_figure_serialization/followup_compact_pdf/rejection_summary.json)에
연결된다. 검산 코드를 완화해 통과시키지 않고, 별도 publication finalizer가
완성된 figure bytes를 먼저 검증한 후 원자적으로 저장하는 단계에서
해결하도록 했다. 원래 원시 맵과 생성 소스의 provenance는 유지한다.

## 7. 최종 저장자료 검사 결과 — 2026-10-11

최종 [main 감사](../data/validation_v5_1/independent_review/verification_summary.json)와
[compact 감사](../data/validation_v5_1/compact_review/verification_summary.json)는
모두 **PASS**다. 독립 검산 source의 SHA-256은 두 실행 모두
`0721e047dab8791c39b5e5464c253c900ccab25af09331ad4a7713c73584176e`이며,
검사 중 source와 입력 파일의 변경은 없었다.

| 항목 | Main | 별도 compact |
|---|---:|---:|
| 저장 맵 | 4 | 4 |
| 검사한 저장 배열 | 104 | 104 |
| 중복 제외 NPZ archive / CRC | 12 | 12 |
| 그림 구성 / 최종 파일 | 3 / 9 | 3 / 9 |
| 검산한 metric scale bar | 6 | 6 |
| 검산한 무방향 line glyph | 39 | 130 |
| 같은 입력 내 공통 높이 범례 | −70∼+70 μm | −60∼+60 μm |
| 기록된 원시 맵 생성 primary query | 7,129,600 | 8,192,000 |
| 이번 배열 검산의 새 primary query | 0 | 0 |
| 이번 별도 해석적 oracle의 새 primary query | 594 | 0 |
| 조명·radiance 렌더 호출 | 0 | 0 |
| 독립 감사 소요 시간 | 6.718 s | 8.766 s |

8개 맵의 208개 배열과 24개 고유 archive를 검사했다. 원시 맵 생성의
15,321,600회 query는 표면의 첫 교차점을 찾는 기하 query이며,
광학 시뮬레이션의 독립 반복수나 15,321,600장의 이미지가 아니다.
수정된 publication finalizer는 원시 맵을 다시 추적하지 않고 저장된
display 배열에서 그림을 다시 배치했다. 독립 검산은 finalizer source,
보존된 생성 manifest, 입력 배열, 최종 파일 사이의 hash를 확인하고
원래 생성 필드가 유지됐는지 비교했다.

### 원시 수치와 해석

아래 coverage는 SS2 lattice에서 얻은 **투영 hit 면적 비율**이다.
높이는 같은 lattice의 첫 가시 표면 world Z 범위다. Pixel-center의
높이 극값과 SS의 극값은 다른 sampling 결과이므로 섞지 않는다.

| 입력 / 맵 | 중심 격자 H×W | 중심 hit 수 | SS coverage | SS 높이 범위 (μm) |
|---|---:|---:|---:|---:|
| Main overview / ply | 474×640 | 124,972 | 41.198% | −56.525∼64.996 |
| Main zoom / ply | 640×640 | 139,150 | 33.938% | −56.421∼64.761 |
| Main overview / fiber | 474×640 | 119,202 | 39.286% | −62.576∼64.887 |
| Main zoom / fiber | 640×640 | 131,780 | 32.161% | −62.543∼64.614 |
| Compact overview / ply | 640×640 | 303,464 | 74.218% | −41.099∼50.996 |
| Compact zoom / ply | 640×640 | 300,095 | 73.255% | −41.601∼50.992 |
| Compact overview / fiber | 640×640 | 293,848 | 71.659% | −46.759∼50.977 |
| Compact zoom / fiber | 640×640 | 287,815 | 70.285% | −46.786∼50.980 |

Ply proxy는 fiber 사이를 채우므로 이 예시의 overview coverage가
explicit fiber보다 크다. 이 차이를 부피 공극률 또는 광학 투과율로
치환하지 않는다. Compact의 높은 coverage는 별도 pitch·twist·기하
설정의 결과이며 원본 맵에 한 시각적 보정이 아니다.

모든 맵에서 `height_mm == position_mm[..., 2]`는 저장값 기준 정확히
일치했고, normal·tangent 단위 길이의 최대 오차는 약 \(5.1\times10^{-8}\)
이하였다. 실제 hit 좌표와 독립 camera ray 좌표의 최대 차이는
\(3.522\times10^{-7}\) mm였다. Float32 교차점 저장의 오차 범위를
검사했으며, 이를 실물 위치 정확도로 해석하지 않는다. 앞면 first hit의
법선 부호 오류와 정의되지 않은 XY 방향은 이 여덟 맵에서 0건이었다.

각 SS 색에 배경을 적용해 독립 합산한 RGB와 저장 straight RGBA를
한 번 합성한 결과의 최대 차이는 \(2.981\times10^{-8}\) 이하였다.
높이 범위를 넘어서 clipping된 SS는 0개다. 중심 categorical ID는
정수·lookup·부모 관계를 검사했으며 평균 ID로 바꾸지 않았다.

\(\max|\mathbf n\cdot\mathbf t|\)는 main 약 0.02524, compact 약
0.04714였다. 따라서 이 파일의 tangent를 임의로 BSDF의 표면 접선이라고
간주하면 안 된다. 현재 계약은 선택 계층의 중심선 방향이며, 표면
접평면으로의 투영·재정규화가 필요한 광학 모델은 그 변환을 따로
정의해야 한다.

### 해석적 oracle과 고의 오류 검출

최종 [oracle 원시 기록](../data/validation_v5_1/independent_review/analytic_oracles.json)은
동결된 기하 source를 실제 실행한 해시를 포함한다.

| Oracle | 실제 primary query | 정확한 답과의 차이 |
|---|---:|---|
| \(z=0.2x-0.3y+0.4\), 중심 9×11 및 SS2 | 495 | 높이 최대 \(5.325\times10^{-8}\) mm, normal 벡터 최대 \(2.385\times10^{-8}\); hit mask·coverage 일치 |
| 앞면 \(z=0.6\), 뒷면 \(z=0.05\), 중심 9×11 | 99 | 앞면 15 / 뒷면 84 hit; 높이 최대 \(3.577\times10^{-8}\) mm, object 선택 일치 |

초기 개발 때의 594-query 결과도
[별도 원본 복사](../data/validation_v5_1/independent_review/initial_development_oracles.json)로
남겼다. 초기 실행에는 실행 시점 source hash가 없었으므로 현재 hash를
소급 부여하지 않았다. 복사 작업은 새 query를 만들지 않았다. 최종
594회는 별도의 실제 재검증이며 둘을 같은 실행으로 보고하지 않는다.

[독립 corruption 테스트](../tests/test_structure_review_v5_1.py) 네 개는
world height를 ray depth로 바꾼 경우, image Y가 뒤집힌 경우, ID를
float로 저장한 경우, coverage를 두 번 곱한 RGBA를 거부한다. 네 focused
test가 통과했으며 수정 대상은 메모리 배열뿐이다. 저장소 전체 suite의
최종 횟수와 결과는 별도
[release gate](../data/validation_v5_1/final_suite/)를 따른다.

## 8. 최종 그림 확인과 재현

독립 검토 에이전트는 2026-10-11에 최종 PNG 6개를 화면에 열어 확인했다.
[검토 기록](../data/validation_v5_1/independent_review/visual_review.json)은
해당 PNG의 현재 hash와 확인 내용을 남긴다. Main은 개방된 원본 직조,
compact는 별도 촘촘한 직조임이 제목과 subtitle에 드러난다. 두 hierarchy
그림은 같은 crop의 외피와 개별 fiber를 다른 행으로 구분하고,
material-detail 그림은 A/B synthetic ID와 실제 염색을 혼동하지 않게
범례를 붙였다. 최종 normal 범례·footer와 compact subtitle의 겹침은
관찰되지 않았다. 일부 삼각형 경계나 categorical map의 계단 모양은
지정한 기하 sampling 및 pixel-center 표시의 일부다.

이 화면 확인은 수치 검산을 대신하지 않는다. 또한 별도 제작 담당자의
[container/page QA](../data/validation_v5_1/figure_finalization/page_container_qa.json)는
최종 18개 파일의 hash, PNG 6개 전체 decode, SVG 6개 XML parse,
PDF 6개 각각의 1-page parse·rasterization을 기록한다. 검산기의 PDF
header/EOF 확인보다 넓은 검사이며 실행 주체와 범위를 구분한다.
미참조 중간 그림은 accepted manifest의 과학 결과에 포함하지 않는다.
최종 inventory의 미참조 파일 여부도 위 별도 QA 기록을 따른다.

아래 명령은 저장된 자료를 읽어 재검산한다. 출력은 아직 존재하지 않는
새 경로를 사용하며 보존된 최종 감사 기록을 덮어쓰지 않는다. Main에서만
작은 해석적 oracle을 실행하고 compact의 배열 검산에서는 중복하지 않는다.

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m visualization.review_structure_figures \
  --manifest figures/structure_v5_1/figure_manifest.json \
  --output scratch_runs/recheck_structure_v5_1_main

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m visualization.review_structure_figures \
  --manifest figures/structure_v5_1/compact/figure_manifest.json \
  --output scratch_runs/recheck_structure_v5_1_compact \
  --skip-oracles
```

검산은 저장자료의 좌표·부모 ID·색 변환·hash 일관성과 해석적 기하
조건을 확인한다. 직물 기하 전체를 다시 생성해 source geometry hash를
독립 계산한 것은 아니며, 해당 hash는 생성·설계 기록 사이의 동일성을
대조했다. 실물 원단과의 정합, 역학 평형, wave/volume 광학의 수렴,
원단의 광택·촉감 예측은 이 release의 새 증명 범위에 포함되지 않는다.
