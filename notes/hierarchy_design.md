# 원사에서 직물까지: 계층 기하 엔진 v2

작성 기준: 2026-10-11. 염색·퇴색은 이번 범위에서 제외한다.

## 1. 목적과 구현 상태

이 엔진의 목적은 텍스처처럼 보이는 무늬를 생성하는 데 그치지 않고,
광학 엔진이 추적할 수 있는 **섬유 위치·방향·반지름·물질 식별자와 부모 관계**를
일관된 단위로 생성하는 것이다. 기존 `textile_sim/geometry.py`의 동작은 변경하지 않았다.

새 모듈은 `textile_sim/hierarchy.py`, `textile_sim/weave_draft.py`이다.
생성 결과는 명시적인 원형 섬유의 **보간 polyline**이며, 렌더러의 cubic B-spline
제어점이라고 암묵적으로 해석하지 않는다. B-spline 변환은 광학 연결 모듈이 별도
오차 한계를 보고하면서 수행한다.

실제로 구현·실행한 기능:

- 임의의 직사각형 binary weave draft와 서로 다른 경·위사 반복 길이.
- 섬유 → ply → yarn → 직조의 부모 관계 및 물질 ID 보존.
- 부모 곡선의 실제 polyline 호길이를 사용하는 양·음의 독립 twist.
- double-reflection rotation-minimizing frame에 의한 곡선 위 계층 배치.
- 제한된 독립 방사 방향 migration, 기존 섬유의 C2 loop excursion.
- 교차점의 over/under 순서를 유지하는 C2 crimp와 교차점 사이 waviness.
- 전체 명시적 곡선에 대한 서로 다른 섬유 사이 capsule 간격 검사.
- 가변 길이 곡선을 pickle 없이 저장하는 NPZ와 버전·단위·부모 관계 JSON.
- 완전한 계층을 1/2/4배로 재생성해 위치·호길이·방향 분포의 수렴을 확인.

**아직 포함하지 않은 것:** 실제 방적·제직 역학, 장력 평형, 접촉력·마찰·압착,
staple 길이 통계와 실제 보풀 분포 추정, 비원형 섬유, 3D weave block, knitting,
임의 곡면 위 옷 전체의 등거리 배치, 실제 원단 파라미터 fitting.

## 2. 논문과 구현의 관계

### FabricGen, CVPR 2026

사용자가 올린 본문 10쪽 전체와 주요 그림을 읽었다. 논문의 microstructure 표현은
UV 위치에 대한 `n(p), t(p), h(p)`의 procedural query다. multi-ply는 curved helix,
yarn sliding은 UV remapping, flyaway는 SpongeCake의 확률적 방향 층으로 표현한다.
명시적인 개별 섬유 경로와 제직 역학을 모두 푸는 모델은 아니다.

이번 엔진은 계층 분리와 직조 draft를 참고하되, 파동·광선·렌더러의 공통 입력을
만들기 위해 명시적 곡선을 선택했다. FabricGen의 LLM·diffusion 학습, UV 해석식,
SpongeCake layer를 재현했다고 주장하지 않는다. color/albedo 합성도 실행하지 않았다.

### 관련 1차 자료

1. Trunz et al., *Neural inverse procedural modeling of knitting yarns from images*,
   [본문 §§3.1–3.2](https://arxiv.org/html/2303.00154v1).
   local recursive frame과 radial migration을 참고했다. 본 구현의 bounded excursion은
   CT 데이터에 맞춘 Zhao 모델이나 해당 논문의 전체 yarn generator 재현이 아니다.
2. Wang et al., *Computation of Rotation Minimizing Frames*, TOG 2008,
   [저자 연구기관 페이지](https://www.microsoft.com/en-us/research/publication/computation-rotation-minimizing-frames/),
   DOI [10.1145/1330511.1330513](https://doi.org/10.1145/1330511.1330513).
   두 반사에 의한 RMF를 독립 구현하고 analytic helix의 Bishop frame과 비교했다.
3. Montazeri et al., *A Practical Ply-Based Appearance Model of Woven Fabrics*, 2020,
   [저자 PDF](https://projects.shuangz.com/practical_cloth-sa20/practical_cloth-sa20-ld.pdf).
   §3.1은 over/under만 맞춘 중심선으로 실제 slope distribution이 보장되지 않는다고
   지적한다. 그래서 본 엔진은 평형을 주장하지 않으며 tangent second moment를 함께 기록한다.
4. Weavecraft, 2020, DOI [10.1145/3414685.3417865](https://doi.org/10.1145/3414685.3417865),
   [공식 저자 페이지](https://www.antequ.net/).
   3D block 계층 구성과 yarn-level simulation은 중요한 장기 확장 대상이다.
   현재 single-layer binary draft를 Weavecraft의 multilayer mechanics와 동일시하지 않는다.
5. Zhao et al., *Fitting Procedural Yarn Models for Realistic Cloth Rendering*, 2016,
   [저자 프로젝트](https://projects.shuangz.com/procyarn-sg16/).
   CT fitting과 관측된 flyaway 통계를 사용하는 계열이다. 이번 숫자는 합성 입력이며
   실크·코튼·울의 실측 상수로 이름 붙이지 않는다.

외부 소스를 확인한 것과 그 소프트웨어를 실행한 것은 다르다. 위 계층 모듈은 자체
구현이며 FabricGen/Weavecraft/Zhao generator 코드를 복사해 넣지 않았다.

## 3. 계층 데이터 계약

| 계층 | 객체 | 보존하는 정보 |
|---|---|---|
| 물질 참조 | `material_id` | 광학 모듈에서 정의할 물질 식별자; 기하 코드에 임의 상수를 숨겨 넣지 않음 |
| 섬유 | `FiberSpec` | local ID, 원형 반지름, ply 단면 offset, migration·loop 설정 |
| Ply | `PlySpec` | 섬유 tuple, yarn 단면 offset, fiber twist와 초기 phase |
| Yarn | `YarnSpec` | ply tuple, ply twist와 초기 phase |
| 직조 위상 | `WeaveDraft` | 행=weft, 열=warp, 1=warp over, 각각의 반복 길이 |
| 유한 직물 패치 | `FabricSpec` | 경·위사 수와 pitch, crimp 배분, envelope gap, sampling, seed |
| 계산 결과 | `HierarchyGeometry` | 모든 fiber record, yarn/ply 중심선, spec, metadata |

모든 길이는 **mm**, twist는 **부모 호길이 1 mm당 부호 있는 회전 수**다.
양의 twist는 부모 진행 tangent를 축으로 하는 오른손 회전이다. 관찰 방향에 의존하는
S/Z 표기를 수치 부호와 암묵적으로 동치로 두지 않았다.

각 `FiberCurve`는 다음을 가진다.

```text
points_mm[N,3], radii_mm[N]
fiber_id, yarn_id, ply_id, material_id
family, yarn_index, ply_index, fiber_index
kind, cross_section
```

현재 섬유별 반지름은 일정하며 `cross_section="circle"`이다. `kind="loop_excursion"`
이어도 같은 하나의 fiber record를 유지한다. 좌표·반지름 배열은 immutable bytes를
바탕으로 하므로 `setflags(write=True)`로 수정 가능 상태로 바꿀 수 없다.
부모 관계 dictionary와 spec 자체를 암호학적 불변 객체라고 주장하지는 않는다.

JSON schema 이름은 `textile-hierarchy/2.0`이다. 축·단위 규약이 다르거나 알 수 없는
설정 필드가 들어오면 조용히 보정하지 않고 예외를 낸다.

## 4. 수학적 구성

### 4.1 Twist는 세계 좌표가 아닌 부모 호길이에 적용

부모 중심선의 정점이 $\mathbf c_k$이면

$$s_k=\sum_{j<k}\|\mathbf c_{j+1}-\mathbf c_j\|.$$

부모 tangent와 두 normal을 $\mathbf t,\mathbf n_1,\mathbf n_2$라 하고
$\mathbf n_2=\mathbf t\times\mathbf n_1$로 둔다. local offset
$\mathbf q=(q_x,q_y)$와 twist $T$에 대해

$$\phi(s)=\phi_0+2\pi Ts,$$

$$\mathbf x(s)=\mathbf c(s)+
(q_x\cos\phi-q_y\sin\phi)\mathbf n_1(s)+
(q_x\sin\phi+q_y\cos\phi)\mathbf n_2(s).$$

이 연산을 yarn→ply와 ply→fiber에서 각각 적용한다. Ply 경로의 길이는 꼬임 때문에
yarn 중심선보다 길 수 있으므로, 두 단계에서 같은 전역 축 좌표를 사용하면 fiber
회전 수가 달라지는 오차가 생긴다. 테스트는 이를 수치적으로 구분한다.

RMF는 Frenet frame처럼 곡률이 0이 되는 구간에서 normal이 뒤집히지 않도록 한다.
곡선 자체가 되돌아가 tangent가 정의되지 않는 cusp는 입력 오류로 처리한다.
해석적 tangent를 제공하면 그 tangent를 사용하고, 일반 polyline에서는 호길이 기반
수치 tangent를 사용한다. 따라서 모든 생성 기하에 대해 해석적 tangent를 가정한
4차 정확도를 일반적으로 주장하지 않는다.

### 4.2 Migration과 loop

명목 방사 위치 $r_i^0$인 섬유에 대해

$$r_i(s)=r_i^0+A_i\cos(2\pi s/P_i+\varphi_i)$$

를 사용한다. $A_i<r_i^0$이며 중심 섬유의 방사 방향은 정의되지 않으므로 migration을
허용하지 않는다. 미지정 phase는 `seed + 전체 fiber ID`의 SHA-256에서 결정하므로
생성 순서나 Python hash randomization에 영향을 받지 않는다.

Local loop 구간에서는 $u\in[0,1]$에 대해

$$b(u)=64u^3(1-u)^3$$

를 추가한다. 구간 밖은 0이다. 양 끝에서 값·1차·2차 미분이 0이며 가운데 최대값은
1이다. 따라서 기존 섬유에 다시 연결되는 연속적인 outward excursion이 생긴다.

이는 보풀의 통계적·역학적 모델이 아니다. 섬유 객체를 복제하지는 않지만 반지름을
유지하면서 경로 길이가 바뀌므로 체적 proxy와 필요한 재료량은 바뀔 수 있다.
**질량 보존이나 실제 방적 경로를 보장하지 않는다.**

두 섬유의 명목 offset 사이 거리가 $d_{ij}$이고 최대 이동량이 $A_i^{\max}$,
$A_j^{\max}$이면 동일 단면의 간격 하한은

$$d_{ij}-A_i^{\max}-A_j^{\max}-r_i-r_j.$$

이 값이 양수인 경우만 사전 허용한다. 서로 다른 축 위치에서 접근하는 섬유는 이
검사로 알 수 없으므로, 생성 후 전체 segment 검사를 별도로 수행한다.

### 4.3 Rectangular draft와 C2 crimp

$P_{ij}$에서 $i$는 weft row, $j$는 warp column이다. 교차점에서

$$z^{\mathrm{warp}}_j(i)=a_w(2P_{ij}-1),$$
$$z^{\mathrm{weft}}_i(j)=-a_f(2P_{ij}-1).$$

두 yarn envelope 반지름의 합에 지정 gap을 더한 값을 $D$라 하면
$a_w+a_f=D$로 설정한다. `warp_crimp_share`가 각 family에 crimp를 얼마나
배분할지를 정한다. 인접 높이 사이에는

$$h(u)=10u^3-15u^4+6u^5$$

로 보간한다. 높이 overshoot가 없고 교차점의 1·2차 도함수가 0이다.
서로 다른 경·위사 pitch와 서로 다른 반복 길이를 각각 사용한다.

`yarn_waviness_mm`는 같은 C2 bump로 교차점 사이에서 lateral displacement를 만든다.
교차점 자체는 이동하지 않는다. 이는 FabricGen의 UV Perlin sliding을 재현한 것이
아니며, 교차 제약을 유지하는 독립적인 bounded 기하 변형이다.

단순 위상만으로 실제 원단의 slope나 장력을 예측할 수 없다. 장기적으로 Montazeri
계열의 strain/contact 에너지 또는 yarn mechanics를 추가할 수 있지만 이번 코드에는
그 최적화가 들어 있지 않다. 현재 생성된 tangent가 실측 tangent라고 간주하면 안 된다.

### 4.4 미시 구조의 seamless tiling은 별도 조건

Draft와 yarn 중심선의 주기성이 보장되더라도, 한 주기 동안의 parent 호길이 $L$에
대한 $TL$이 정수가 아니면 fiber twist phase는 닫히지 않는다. Migration phase와
frame holonomy도 별도 고려 대상이다. 따라서 metadata는
`geometry_tileable=False`를 기록한다. 반복 셀을 단순 복사해 seam이 없다고 주장하지 않는다.

## 5. 연속 기하 간격 검사

`audit_clearance()`는 각 polyline segment를 반지름이 일정한 capsule로 다룬다.
Segment midpoint와 half-length를 이용한 KD-tree broad phase 뒤에 정확한 segment
사이 최소거리를 계산한다.

Segment $i$의 half-length가 $h_i$, 반지름이 $r_i$일 때 search radius는

$$R_{\rm search}=2\max_i(h_i+r_i)+m$$

이다. 여기서 $m$은 probe margin이다. 이 반경 밖에서 제외된 midpoint pair는 삼각
부등식에 따라 최소 표면 간격이 $m$보다 크다. 따라서 최종 보고 하한은

$$\min(m,\;\min_{\rm tested}(d_{ij}-r_i-r_j)).$$

**보장 범위:** 서로 다른 fiber record의 연속 polyline tube 전체.
같은 fiber의 자기접촉, B-spline으로 바뀐 곡선, 실제 압착된 재료는 이 보장에 포함되지 않는다.

중요한 독립 회귀 예제는 다음 두 가지다.

- 모든 정점이 떨어져 있어도 segment 내부에서 교차하는 두 선분: 충돌 검출.
- 동일 단면에서는 떨어져 있는 두 촘촘한 helix가 서로 다른 축 위치에서 접근:
  사전 packing 검사는 통과하지만 전역 검사는 실패.

리뷰에서 음수 `batch_size`가 검사 반복을 생략할 수 있는 오류를 발견해 수정했다.
현재 `batch_size`, `max_candidate_pairs`는 양의 정수만 허용한다. False certificate를
만들던 조건은 독립 리뷰 테스트에 포함했다.

## 6. 실제 생성한 예제와 결과

| JSON 예제 | Yarn 계층 | 섬유 수 | 정점 수 | 전역 간격 검사 |
|---|---|---:|---:|---|
| `plain_single_ply` | 1 ply × 19 fibers | 190 | 26,638 | 통과 |
| `twill_two_ply` | 2 plies × 7 fibers | 140 | 39,116 | 통과 |
| `basket_rectangular_three_ply` | 3 plies × 7 fibers, 4×6 draft | 210 | 58,674 | 통과 |
| `twill_migration_waviness` | 2-ply + radial migration + waviness | 140 | 39,116 | 통과 |
| `twill_loop_excursions` | 위 조건 + local loop | 140 | 78,092 | 통과 |

처음 세 예제의 최소 간격 하한은 각각 약 1.927, 1.765, 2.465 μm였다.
Migration/waviness와 loop 예제의 하한은 각각 약 1.522, 1.527 μm였다.
이들은 서로 다른 계층 구성이 가능한지 확인하는 예제이며, 모든 변수를 고정한
직조 효과 비교는 아니다. 나머지 twill 예제는 yarn 교차 중심 거리를 모두 64 μm로
고정했다. Migration/loop 때문에 envelope가 커질 때 gap을 조정해 crimp가 함께
변하는 혼선을 줄였다. Waviness와 migration은 한 예제에서 함께 켜므로 각각의
효과를 분리하는 최종 실험을 대신하지 않는다.

각 실행의 정확한 간격·길이·방향 통계·시간·입력 해시는
`data/hierarchy_v2/<case>/hierarchy_metrics.json`에 있다.
실행된 설정은 `examples/hierarchy/<case>.json`이다.
`figures/hierarchy_v2`의 wire 그림은 기하 진단용 중심선이다. 구조를 읽을 수 있도록
축 aspect와 선 두께를 조정했으며, 그림에서 실제 반사색·섬유 직경을 추정하면 안 된다.
좌표의 mm 값과 저장된 radius 배열이 물리적 치수의 기준이다.

계층 전체의 샘플링 비교 결과는 `data/hierarchy_v2/sampling_refinement_metrics.json`에
저장했다. Plain의 1→2배와 2→4배 기하 차이는 최대 약 0.137 μm와 0.0389 μm였고,
3-ply rectangular basket은 약 0.0727 μm와 0.0235 μm였다. 이것은 두 생성 mesh의
차이며 계산하지 않은 연속 극한에 대한 오차 인증은 아니다.

Adaptive sampling이 서로 다른 요청을 같은 mesh로 올릴 수 있으므로, refinement
비교는 입력한 점 수가 아니라 **실제로 채택된 baseline 점 수**에서 시작한다.

## 7. 방향 통계와 광학 연결

섬유 tangent의 길이 가중 2차 모멘트를 기록한다.

$$\mathbf Q=\frac{\sum_k\ell_k\mathbf t_k\mathbf t_k^T}{\sum_k\ell_k}.$$

$\mathbf Q$는 대칭·양의 준정부호이고 trace가 1이다. 전체, family별, material별로
저장한다. 이 행렬만으로 masking, 섬유 단면, 재료, 산란 다중경로가 결정되는 것은
아니므로 BSDF나 SGGX 파라미터라고 부르지 않는다.

광학 연결의 원칙:

1. 구조 → optical scene 변환에서 fiber/material/ply/yarn ID를 보존한다.
2. mm→μm, 흡수 계수 단위, 파장 범위는 경계에서 명시적으로 변환한다.
3. 2D 무한 평행 원통 wave/ray solver에는 실제로 평행하고 직선인 구간만 정확한
   입력으로 보낼 수 있다. 기울어진 단면을 원형으로 조용히 근사하지 않는다.
4. Ply/frame 기준 절단면에 대한 곡률·각도 분산·유효 범위를 보고하고, 근사가 필요한
   경우에는 해당 전제와 오차 평가가 먼저다.
5. Mitsuba에 polyline 정점을 B-spline 제어점으로 넘기면 기하가 달라진다. 연결 모듈이
   smoothing 및 float32 quantization bound를 계산하고, 기존 clearance에서 이를
   차감해 새 기하의 분리 조건을 확인한다.

관련 구현과 실행 결과는 `textile_sim/optical_scene.py`와
`notes/optical_bridge.md`를 참조한다.

## 8. 재현 명령

```bash
python -m unittest discover -s tests -p 'test_weave_draft.py' -v
python -m unittest discover -s tests -p 'test_hierarchy.py' -v

python -m textile_sim.hierarchy \
  --config examples/hierarchy/basket_rectangular_three_ply.json \
  --out data/hierarchy_v2/basket_rectangular_three_ply

python examples/hierarchy/plot_geometry_diagnostics.py
```

CLI는 기본적으로 전역 간격 검사를 수행하며, 실패하면 결과를 검토할 수 있도록
저장한 다음 nonzero exit code를 반환한다. `--skip-clearance`를 명시적으로 사용하면
metadata에 미검증 상태가 기록된다.

`save_hierarchy()`는 가변 길이 좌표를 누적 offset 배열로 저장한다. `np.load(...,
allow_pickle=False)`를 사용하며 JSON에 NPZ의 SHA-256을 기록한다. JSON과 NPZ의
대응이 다르거나 수치 파일이 바뀌면 load가 실패한다. 이것은 원시 데이터와 부모 관계의
일관성 검사이지, 외부 provenance의 진위를 인증하는 전자 서명은 아니다.

## 9. 다음 확장에서 먼저 검증할 항목

- 실제 yarn 영상이나 CT로 offset·직경·twist·migration 분포를 추정한다.
- 교차점 높이 제약만 맞춘 기하와 단순 yarn equilibrium 모델의 tangent 분포를 비교한다.
- 같은 기하 입력으로 reflection/transmission 양쪽을 맞추는지 확인한다.
- Polyline→B-spline 변환 후 광학량까지 sampling convergence를 검사한다.
- 같은 fiber에서의 자기접촉, elliptical cross-section, 압착된 ply, strand 길이 보존은
  각각의 기준 문제를 만든 다음 추가한다.
- 3D weave blocks와 weaving mechanics는 새로운 위상·역학 계층으로 설계한다.
  현재 2D draft의 옵션 하나처럼 취급하지 않는다.
