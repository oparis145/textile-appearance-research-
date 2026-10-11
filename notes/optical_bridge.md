# Optical engine bridge v2 — 형상과 광학을 연결하는 검증 가능한 계약

## 목적과 현재 구현 범위

이번 버전의 목적은 원단 형상 생성기가 만든 **실제 개별 섬유의 기하·계층·재료 ID**를 광학 계산으로 전달하는 것이다. `fiber → ply → yarn → weave` 계층을 보존하고, 같은 입력에서 기준 파동 계산, 광선 수송, 원단 경로 추적과 구조 통계를 만들 수 있게 했다.

염색·퇴색·촉감·실측 재료 파라미터 추정은 포함하지 않는다. 이번 예제의 `synthetic_A`, `synthetic_B`는 코드 경로와 물리 단위를 검증하기 위한 합성 유전체이다. 실크, 코튼, 큐프라, 린넨으로 명명할 실험적 근거가 없다.

실행한 연결은 다음 두 가지이다.

1. **HierarchyGeometry → OpticalScene → Mitsuba**: 3D 개별 섬유와 재료를 보존한 원단 경로 추적.
2. **HierarchyGeometry → OpticalScene → 유효성 검사된 단면 → 기존 2D Maxwell / ray solver**: 곧고 평행한 보정용 yarn에서 실제 양쪽 solver 실행.

직조 전체의 3D 파동 해석, 2D 산란을 3D cloth BSDF로 올리는 보정, Tang2024의 SGGX/ASGGX 복원, Yu2025 전체 방법의 재현은 완료했다고 주장하지 않는다.

## 관련 논문·공개 코드에서 반영한 설계 원칙

### Tang et al. 2024

사용자가 첨부한 *Woven Fabric Capture with a Reflection-Transmission Photo Pair*, arXiv:2406.19398v3의 본문과 supplementary를 검토했다.

- 반사와 투과는 서로 다른 제약을 제공한다. 모델은 각 위치에서 위·아래 두 yarn layer를 별도로 다룬다.
- SGGX single scattering, azimuth-invariant ASGGX를 이용한 저차 다중 산란 근사, diffuse 고차 성분이 구분되어 있다.
- supplementary의 gap delta transmission은 섬유를 만나지 않는 직접 투과 성분이다.
- 논문의 tension-aware thickness는 위치와 직조에 따라 지정한 optical thickness 배율이다. 응력 평형을 푼 역학 결과나 실제 길이 단위의 섬유 두께와 동일하지 않다.
- 촬영계의 out-of-focus source를 위한 Gaussian 처리를 공극 회절의 물리 해석으로 가져오지 않는다.

공식 코드의 `Readme.md`, `sggx.py`, `render.py`와 저장소 메타데이터를 GitHub connector로 확인했다. 확인한 revision은 `67150eeca9f28b85f8fe21d40d888d34bd4d3b25`이다. 라이선스는 GPL-3.0이다. 이번 모듈에는 해당 저장소의 코드를 복사하거나 의존성으로 포함하지 않았다. 학습 네트워크와 pretrained weights도 실행하지 않았다.

- Paper: <https://arxiv.org/abs/2406.19398>
- Official project: <https://wangningbei.github.io/2024/FabricBTDF.html>
- Pinned repository: <https://github.com/lxtyin/FabricBTDF-Recovery/tree/67150eeca9f28b85f8fe21d40d888d34bd4d3b25>
- Inspected SGGX code: <https://github.com/lxtyin/FabricBTDF-Recovery/blob/67150eeca9f28b85f8fe21d40d888d34bd4d3b25/sggx.py>
- Inspected forward renderer: <https://github.com/lxtyin/FabricBTDF-Recovery/blob/67150eeca9f28b85f8fe21d40d888d34bd4d3b25/render.py>

### Mitsuba 3.9.1 / Chiang hair model

기존 버전에서 감사한 `hair.cpp`의 실제 내부 경로 길이는 반지름이 1인 단면으로 정규화되어 있다. 따라서 물리 흡수계수를 그대로 넣지 않고 반드시

\[
\sigma_{a,\mathrm{shader}}=\mu_a\,r
\]

로 변환한다. 또한 pinned source는 hair BSDF를 `bsplinecurve`와 함께 쓰도록 명시한다. `linearcurve`로 형상을 바꾸면 국소 프레임이 달라질 수 있으므로 이를 동등한 대체재로 사용하지 않았다.

- Audited hair source: <https://github.com/mitsuba-renderer/mitsuba3/blob/v3.9.1/src/bsdfs/hair.cpp>
- Audited B-spline shape source: <https://github.com/mitsuba-renderer/mitsuba3/blob/v3.9.1/src/shapes/bsplinecurve.cpp>
- Inspected linear shape source: <https://github.com/mitsuba-renderer/mitsuba3/blob/v3.9.1/src/shapes/linearcurve.cpp>
- Original model: <https://www.disneyanimation.com/publications/a-practical-and-controllable-hair-and-fur-model-for-production-path-tracing/>

## 1. Versioned scene contract

구현: `textile_sim/optical_scene.py`.

### 데이터 타입

| 타입 | 필수 정보 | 의미 |
|---|---|---|
| `MaterialSpectrum` | material ID, wavelength, n, κ, source, data status | 파장별 등방성 scalar 복소 굴절률. 실측 여부를 명시 |
| `OpticalFiber` | fiber/yarn/ply/material ID, 좌표, radius, curve basis, cross-section, provenance | 개별 섬유의 실제 위치와 계층 소속 |
| `OpticalScene` | materials, fibers, background index, schema, units, provenance | 광학 모듈들이 공유하는 불변 입력 |
| `BundleSection` | scene hash, 단면 좌표·반지름·IDs, plane frame, eligibility, diagnostics | 2D solver로 넘겨도 되는지 판단한 단면 |

좌표 단위는 **mm**, 파장 단위는 **진공 nm**, 위상 convention은 \(e^{-i\omega t}\), passive index는 \(n+i\kappa\), \(\kappa\ge0\)이다. 이 단위를 바꾸려면 명시적 변환이 필요하다.

배열은 원본을 복사한 뒤 immutable bytes를 backing store로 사용한다. 원본 배열 변경이나 `setflags(write=True)`로 frozen scene을 수정할 수 없다. JSON round-trip은 canonical content SHA-256를 확인한다. scene schema는 `textile.optical_scene/2.0`이다.

다음 오류를 거부한다.

- 중복 ID, 존재하지 않는 material 참조, 하나의 ply가 서로 다른 yarn을 부모로 갖는 경우.
- NaN/Inf, 비양수 반지름·굴절률, 음의 κ, 0 길이 segment.
- 정렬되지 않은 파장, 데이터 범위 밖의 spectral extrapolation.
- 자동 단위 변경, 알 수 없는 schema/curve basis.

`from_hierarchy()`는 `HierarchyGeometry.fiber_records`를 읽고 각 fiber의 material ID, parent IDs, family와 생성 provenance를 그대로 보존한다. 혼방은 서로 다른 fiber labels로 표현한다. 혼합비를 넣어 임의의 유효 굴절률 하나를 계산하지 않는다.

### 흡수와 단위 변환

진공 파장 \(\lambda_0\)에서

\[
\mu_a=\frac{4\pi\kappa}{\lambda_0},\qquad
I(L)=I(0)e^{-\mu_a L}.
\]

`MaterialSpectrum.at()`의 `absorption_per_mm`는 \(\lambda_0[\mathrm{nm}]\times10^{-6}\)을 사용한다. 2D ray engine에 전달할 때에는 다시 \(\mathrm{mm}^{-1}\to\mu\mathrm m^{-1}\)로 변환한다.

매질 굴절률이 \(n_h\)인 경우 기존 원통 wave solver에는

\[
\lambda_h[\mu\mathrm m]=\frac{\lambda_0[\mathrm{nm}]\times10^{-3}}{n_h},
\quad m=\frac{n+i\kappa}{n_h}
\]

를 전달한다. 기존 wave solver의 background가 1인 수식과 일치시키기 위한 변환이다. Ray engine에는 절대 \(n\), \(n_h\), 물리 흡수를 별도로 전달한다.

Ray와 hair 모델은 실수 굴절률 Fresnel + Beer absorption 근사이다. `max_kappa_ratio`는 그 근사를 사용하겠다는 명시적 domain 제한이며 기본값은 0.01이다. 이 임계값이 모든 조건에서 특정 오차를 보장한다는 뜻은 아니다. 정확한 복소 굴절률 interface가 필요한 강한 흡수체는 이 adapter가 거부한다. Wave solver는 passive complex index를 직접 사용한다.

## 2. Polyline에서 Mitsuba cubic B-spline으로의 전환

기하 엔진의 원본은 polyline이다. 이를 B-spline control polygon으로 아무 설명 없이 넘기면 렌더된 기하가 달라진다. 이번 adapter는 다음을 구현했다.

1. 양 끝에 직선 외삽 control point를 하나씩 추가한다. 원래 양 끝 위치는 유지된다.
2. 각 segment의 B-spline 중심선과 원래 선분 사이의 displacement를 해석적으로 제한한다.
3. 사용자가 지정한 `max_smoothing_error_mm`를 넘으면 export를 거부한다.
4. 변화량과 원래 curve basis를 manifest에 기록한다.

네 control point \(P_0,P_1,P_2,P_3\)로 정의한 cubic B-spline segment \(Q(t)\)와 원래 chord \(L(t)=(1-t)P_1+tP_2\)에 대해

\[
Q(t)-L(t)=B_0(t)(P_0-2P_1+P_2)+B_3(t)(P_1-2P_2+P_3).
\]

\(B_0,B_3\ge0\), \(B_0+B_3\le1/6\)이므로

\[
\max_t\|Q(t)-L(t)\|
\le \frac16\max_j\|P_j-2P_{j+1}+P_{j+2}\|.
\]

추가로 pinned shape loader는 `InputFloat=float`를 사용한다. 각 control point의 float32 반올림 오차 최대값은 B-spline의 nonnegative partition-of-unity 성질에 의해 중심선 반올림 오차의 상한이 된다. 반지름의 float32 오차도 별도로 기록한다.

이 수치만으로 다른 섬유 사이 contact가 없다고 할 수는 없다. 예제 driver는 먼저 원본 polyline tube의 연속 간격을 감사하고, 삼각부등식에 따라

\[
g_{\mathrm{export}}\ge
g_{\mathrm{polyline}}-2(\epsilon_{\mathrm{smoothing}}+
\epsilon_{\mathrm{float32,center}}+\epsilon_{\mathrm{float32,radius}})
\]

를 확인한다. 이것은 **서로 다른 섬유 사이의 기하적 분리**에 대한 보수적 전달이다. 범위는 저장된 float32 control point로 정의되는 이상적 spline tube의 기하이다. 렌더러의 모든 floating-point ray traversal/intersection 연산 오차까지 제한하는 것은 아니다. 같은 섬유의 self-contact, 표면 거칠기, 실제 접촉 역학을 검사한 것도 아니다.

### Material뿐 아니라 radius로도 그룹을 나누는 이유

같은 재료라도 반지름이 다르면 shader에 넣어야 하는 \(\sigma_a=\mu_a r\)가 달라진다. 따라서 export group key는 `(material_id, radius_mm)`이다. 그룹마다 curve file과 BSDF를 하나씩 만든다. `manifest.json`은 파일 SHA-256, scene SHA-256, 파장, 실제 optical constants, 변환한 흡수, 모든 fiber IDs를 포함하며 manifest 자체의 hash도 검증한다.

현재 Mitsuba variant는 `llvm_ad_rgb`이다. 파장별 \(n,\kappa\)를 선택하고 세 RGB 채널에 같은 scalar 물리를 적용하는 **단일 파장 proxy**이다. 결과를 spectral integration 또는 색 재현 결과라고 부르지 않는다. 편광과 wave interference도 이 경로에 없다.

## 3. 3D 섬유에서 원형 2D 단면을 추출할 때의 유효성

기존 2D wave/ray engine은 **무한히 길고 평행한 원형 원통**을 다룬다. 직조에서 임의의 평면을 자르면 이 조건이 일반적으로 성립하지 않는다.

반지름 \(r\), 국소 tangent \(\mathbf t\), slice normal \(\mathbf n\)인 원통을 비스듬히 자르면 타원의 반축은

\[
a=\frac{r}{|\mathbf t\cdot\mathbf n|},\qquad b=r.
\]

이 식은 국소 tangent cylinder의 평면 교차에 대한 식이다. 곡률을 가진 tube 전체의 정확한 타원 해는 아니다.

`extract_bundle_section()`는 선택된 **모든** fiber에 대해 다음을 확인한다.

- slice와 centerline의 교차가 정확히 하나인가?
- 필요한 축 방향 window가 fiber 길이 안에 존재하는가?
- local tangent가 plane normal과 평행한가?
- window 안의 tangent 변화와 중심선 편차가 허용치 안에 있는가?
- intrinsic cross-section이 원형인가?
- 변환할 circular sections 사이에 양의 간격이 있는가?

교차하지 않거나 조건을 만족하지 못하는 fiber를 조용히 제거해서 작은 유효 bundle로 만들지 않는다. 선택한 fiber 중 하나라도 실패하면 backend adapter는 계산을 거부하고 diagnostics를 요구한다.

두 모드는 다음과 같다.

| 모드 | 의미 |
|---|---|
| `strict` | 수치 허용오차 안에서 straight/parallel인 local geometry만 허용 |
| `local_parallel` | 사용자가 명시적으로 허용한 작은 tilt·curvature 범위를 parallel circles로 근사 |

`local_parallel`이 성공해도 3D 파동 정확도가 검증된 것은 아니다. 보고되는 ellipse area ratio, tangent 변화, centerline 편차와 window 길이는 이후 근사 오차를 조사하기 위한 정보다. 특히 작은 각도의 타원 면적 오차가 작더라도, 무한 원통의 상대 방향·입사 위상 차이가 광학적으로 작다는 보장은 없다.

## 4. 광학 모델로 넘기기 전 보존하는 구조 통계

각 fiber polyline segment의 길이를 \(\ell_i\), tangent를 \(\mathbf t_i\), 반지름을 \(r_i\)라 하면 두 가지 second moment를 계산한다.

\[
\mathbf C_L=\frac{\sum_i\ell_i\mathbf t_i\mathbf t_i^T}{\sum_i\ell_i},\qquad
\mathbf C_V=\frac{\sum_i\pi r_i^2\ell_i\mathbf t_i\mathbf t_i^T}
{\sum_i\pi r_i^2\ell_i}.
\]

두 텐서는 PSD이고 trace가 1이며 좌표 회전 \(R\)에 대해 \(C'=RCR^T\)로 변환된다. All/material/family/yarn/ply 단위로 보존한다.

추가로 관찰 방향 \(\omega\)에 대한 lateral cylinder projected area 합을 계산한다.

\[
A_{\perp}(\omega)=\sum_i2r_i\ell_i\sqrt{1-(\omega\cdot\mathbf t_i)^2}.
\]

이 값에는 끝면, 가림, 다중 산란, wave coherence가 없다. 불투명도나 extinction coefficient 또는 BSDF라고 사용하면 안 된다. 또한 \(\sum\pi r_i^2\ell_i\)는 segment cylinder volume의 합으로, joint 및 overlap 보정을 포함한 정확한 solid volume이 아니다.

이 통계들은 향후 SGGX fit의 입력이나 진단으로 사용할 수 있지만, **형상 second moment를 SGGX 행렬이라고 자동 선언하지 않는다.** SGGX의 projected-area distribution과 광학 density/roughness를 맞추려면 별도의 모델·기준 산란 fitting이 필요하다.

## 5. 실제 실행한 v2 실험

재현 driver: `run_optical_bridge_experiments.py`.

### 생성된 yarn에서 wave/ray bridge

- 한 ply, 7개 fiber, 반지름 4 μm, 중심 간격 12 μm.
- 두 합성 재료를 fiber label로 교대로 배정.
- 길이 0.3 mm의 straight calibration geometry.
- 450/550/650 nm × Ez/Hz에서 Maxwell과 ray를 모두 실행.
- 조건당 50,000 rays, 총 300,000 rays.
- Maxwell local/global flux 최대 상대 잔차: **8.49 × 10⁻¹⁵**.
- 모든 계산에서 양의 흡수와 passive energy partition을 확인.

이는 서로 다른 optical constants가 실제 개별 섬유에 전달되고, 단위 변환 후 solver가 작동하는 통합 검증이다. Maxwell과 ray의 angular discrepancy 자체는 별도 근사 오차 문제이며 두 방법의 동일성을 주장하지 않는다.

### Oblique slice / twisted yarn 진단

| Slice tilt | 타원/원 면적비 | strict 허용 |
|---:|---:|---|
| 0° | 1.000000 | 예 |
| 5° | 1.003820 | 아니오 |
| 15° | 1.035276 | 아니오 |
| 30° | 1.154701 | 아니오 |
| 60° | 2.000000 | 아니오 |

별도로 `build_yarn`으로 fiber twist를 바꾸면 0.1/0.5/1/2 turns/mm에서 가장 큰 local tilt는 약 **0.432/2.158/4.301/8.488°**였다. 모두 strict 2D reduction에서 거부됐다. 따라서 “단면 이미지가 생성됐다”와 “원형 2D 광학 문제로 환원된다”를 구분할 수 있다.

### 생성된 원단에서 실제 경로 추적

- 3 warp × 4 weft, 직사각형 2/2 twill patch.
- yarn마다 2 plies, ply마다 7 fibers: **98 fibers**, **24,304 segments**.
- warp radius 3 μm, weft radius 4 μm.
- 두 합성 material × 두 radius = **4 optical groups**.
- 450 nm와 650 nm의 reflection/transmission: **4회 실제 Mitsuba render**.
- 128 × 128 pixels, 64 spp, unbounded path depth with Russian roulette.

원본 polyline clearance audit는 212,657개의 후보 segment pair를 검사했고, 모든 다른 fiber 사이 간격에 대한 보수적 하한 **2 μm**를 확보했다. 최대 spline 중심선 smoothing bound는 **0.04114 μm**였다. Float32 반올림까지 포함해도 이 실험의 exported tubes는 양의 분리 하한을 유지한다. 정확한 최신 값은 `optical_bridge_metrics.json`의 `mitsuba_exports`를 참조한다.

이 초기 렌더의 평균 camera linear radiance는 다음과 같다.

| 단일 파장 proxy | Reflection | Transmission |
|---:|---:|---:|
| 450 nm | 0.04450 | 0.14998 |
| 650 nm | 0.04610 | 0.15193 |

이 값은 같은 원단을 각 지정 조명·카메라에서 본 영상 평균이다. 반구 반사율/투과율이 아니며 R+T로 합산할 수 없다. 파장별 seed가 다르고 64 spp의 Monte Carlo 잡음이 있으므로, 작은 파장 차이를 유의한 물리 효과로 주장하지 않는다. 저장한 그림은 구조·재료 전달과 실제 렌더 실행을 확인하는 preview이며 최종 사진급 재현 성능 평가가 아니다.

## 6. 검증

`tests/test_optical_scene.py`에는 다음 독립 검산과 integration test가 있다.

- κ에서 구한 intensity absorption과 complex field amplitude 감쇠의 일치.
- SHA-256 scene round-trip과 수정 검출; immutable bytes-backed arrays.
- 직접 구현한 cardinal B-spline basis를 401개 parameter로 평가한 smoothing bound 검사.
- 재료·반지름 그룹별 Beer attenuation의 물리 단위 일치.
- 비스듬한 원통의 타원 반축, 회전·이동에 대한 단면 거리 불변성.
- window 내부 curvature, 여러 교차, 짧은 길이, coplanar segment, circular overlap의 명시적 거부.
- 길이/부피 가중 orientation tensor의 해석해와 회전 공변성.
- unoccluded projected area의 독립 구면 적분: 평균 \(\pi rL/2\).
- 실제 v2 hierarchy → scene → wave/ray 실행.
- 실제 두 재료 Mitsuba 렌더 및 export 파일/manifest hash 검사.

독립 리뷰에서는 geometry·radius·vacuum wavelength를 1.7배, absorption coefficient를 1/1.7배로 바꾼 similarity test를 추가했다. `hierarchy → section → wave_inputs/ray_inputs → 기존 solver`를 통과한 Ez/Hz 파동 단면적은 약 10⁻¹² 상대 수준에서 1.7배 스케일되었고, 광선의 energy fractions는 불변이었다. 이 검사는 `tests/test_engine_v2_review.py`에 다른 계약·통계 검산과 함께 보존되어 있다.

전체 테스트의 최신 실행 수와 통과 여부는 저장소의 통합 validation report를 기준으로 한다. 단위 테스트 통과가 실물 원단의 optical constants, 촉감, 새 조명에서의 외관 예측 정확도를 검증했다는 뜻은 아니다.

## 7. 재현과 사용

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
python -m unittest discover -s tests -p test_optical_scene.py -v

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
python run_optical_bridge_experiments.py
```

주요 결과는 `data/optical_bridge_v2/`에 저장된다.

- `calibration_scene.json`, `fabric_scene.json`: hash가 있는 실제 optical inputs.
- `calibration_section.json`: 2D reduction eligibility/단면 검증.
- `calibration_optical_arrays.npz`: 파동과 광선의 실제 각도 배열.
- `fabric_geometry/`: 원본 v2 hierarchy.
- `mitsuba_450nm/`, `mitsuba_650nm/`: 그룹별 곡선과 optical manifest.
- `fabric_microstructure.json`: 계층별 tangent·volume·projected area 통계.
- `fabric_polyline_clearance.json`: 다른 fiber 사이 연속 간격 감사.
- `fabric_optical_bridge.png`, `optical_bridge_diagnostics.png`: 실행 결과 그림.
- `optical_bridge_metrics.json`: 재현 설정, scope, 수치 결과.

## 다음에 광학 연구로 연결할 부분

이 버전은 형상과 solver 사이에서 정보를 잃거나 잘못 해석하지 않도록 연결을 정리했다. 다음 연구 질문은 **생성된 3D ply의 tilt/curvature/packing에서 어떤 조건까지 local scattering kernel을 사용할 수 있으며, 이를 재료·조명·각도별로 어떻게 검증할 것인가**이다.

진행 순서는 다음이 타당하다.

1. 빔 크기·축방향 window·twist를 함께 바꿔 local approximation의 실패 조건을 찾는다.
2. 2D cross-section kernels와 3D ray reference 사이의 projection·polarization convention을 맞춘다.
3. 위치·방향·재료가 다른 ply들의 반응을 통계적으로 압축하고 독립 geometry에서 검증한다.
4. 실제 카메라/메타광학의 수집 각도와 광자 예산을 통과한 뒤에도 남는 외관 차이를 평가한다.

이 단계에서 SGGX/ASGGX와 ray-wave hybrid는 비교·근사 후보가 된다. 근사 모델의 파라미터를 기하량과 동일하다고 가정하지 않고, 이번 explicit-fiber 계산과 실제 시편을 기준으로 검증해야 한다.
