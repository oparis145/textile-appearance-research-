# Material-coordinate transport: 원사 변형과 동일 섬유 표본 연결

## 1. 이 모듈이 해결하는 문제

v3의 `build_relaxed_hierarchy`는 초기·평형 원사 경로 각각에서 `build_yarn`을
실행했다. 두 결과의 fiber ID가 같더라도, fiber twist의 위상은 각 상태의 **현재
parent arclength**로 다시 생성됐다. 따라서 같은 ID와 같은 표본 수는 물질점
대응을 보장하지 않았다. v3 코드·데이터는 그 사실을 명시한 채 보존한다.

v4 `textile_sim/material_transport.py`는 하나의 초기 기하를 참조 상태로 고정하고,
그 상태의 ply/fiber 표본을 원사 → ply → fiber 순서로 운반한다. 현재 기하에서
새 섬유를 생성하거나 새 꼬임 회전수를 적용하지 않는다. 모든 원래 fiber vertex의
ID, 순서, material ID와 참조 좌표가 보존된다.

**참조 상태는 선택한 초기 형상이다. 응력이 없는 자연 길이 상태라고 가정하지
않는다.** 아래 stretch·strain은 이 참조 형상에 대한 이산적인 기하 변화다.

이것은 prescribed framed no-slip **운동학적 가정**이다. 광학 사진이나 원사
중심선만으로 실측 물질점 대응을 추론한 결과가 아니며, 섬유 응력·미끄러짐·접촉·
마찰·재료 프레임 비틀림을 푼 것도 아니다.

## 2. 원래 물질 좌표를 고정한다

참조 원사 중심선 표본을 \(p^r_i\)라고 하면, 원사 물질 좌표는 처음 한 번

\[
u_i=\sum_{k<i}\|p^r_{k+1}-p^r_k\|
\]

로 선언한다. 변형 후 원사 표본 \(p^d_i\)에도 **같은 \(u_i\)** 를 부여한다.
변형 원사의 실제 호길이는 별도로 계산하며 물질 좌표로 덮어쓰지 않는다.

참조 fiber에는 그 자체의 표본 호길이 \(a_j\)와 parent ply의 물질 좌표 \(u_j\)를
함께 저장한다. 두 좌표는 다른 값이다. 전자는 fiber segment의 기준 길이를,
후자는 parent에서 어느 위치에 부착됐는지를 나타낸다.

현재 binding API는 기존 계층 생성기가 공유하는 vertex index를 이용하며,
`correspondence='shared_vertex_indices'`라는 **명시적인 호출자 선언**을 요구한다.
원사·ply·fiber의 표본 수가 다르거나, 부모 ID·family·index가 모호하면 거부한다.
서로 독립적으로 resampling된 스캔 데이터에는 이 선언을 적용하면 안 된다.

v3 optical-pair에서 initial/relaxed 원사는 각각 193개 표본을 가지며 같은 index의
평면 좌표가 동일하다. reduced height 모델은 고정된 평면 좌표의 높이만 바꾸므로,
그 index 대응을 사용할 수 있다. 이 사실이 fiber의 실제 no-slip 부착이나
물리적인 인장 응답까지 증명하지는 않는다.

변형 parent를 다른 mesh로 입력할 때는 각 새 꼭짓점의 **참조 물질 좌표**를
`deformed_parent_coordinates_mm`에 넣는다. 양 끝의 참조 좌표를 정확히 유지해야
하며, extrapolation이나 변경된 endpoint는 허용하지 않는다. 내부 좌표 대응의
물리적 타당성은 여전히 호출자가 확보해야 한다.

## 3. 고정된 frame offset을 운반한다

참조와 변형 parent의 frame을

\[
B^r(u)=[t^r,n^r,b^r],\qquad B^d(u)=[t^d,n^d,b^d]\in SO(3)
\]

로 두면, parent에 부착된 원래 표본 \(x^r(a)\)의 국소 좌표는

\[
q(a)=[B^r(u(a))]^T[x^r(a)-p^r(u(a))]
\]

이고 변형 위치는

\[
x^d(a)=p^d(u(a))+B^d(u(a))q(a).
\]

**세 좌표 성분을 모두 보존한다.** 새 normal plane에 투영하면서 axial offset을
삭제하지 않는다. 그래서 지정된 같은 parent material label에서 이 affine map은
역변환과 합성 법칙을 만족한다. 전체 3D 공간에서의 일대일 대응이나 다른 섬유와의
비관통을 보장하는 것은 아니다.

부모 위치는 물질 좌표에 대한 piecewise-linear interpolation을 사용한다.
정점 frame은 기존 double-reflection RMF 구현을 사용하고, 정점 사이 orientation은
SO(3)의 짧은 geodesic으로 보간한다. 중복점·퇴화 tangent·닫힌 parent·모호한
half-turn frame interval은 거부한다.

### 3.1 초기 director와 관측되지 않는 비틀림

중심선만으로는 첫 tangent 주위의 회전을 결정할 수 없다. 따라서 **참조와 변형
원사의 초기 director를 모두 명시적으로 입력**한다. rigid motion 시험에서는
점뿐 아니라 director도 같은 rotation으로 회전시켜야 한다. 중심선이 같은데
director가 달라지는 상태는 다른 prescribed material orientation이다.

이 모델의 Bishop/RMF 운반은 독립적인 material twist 자유도를 푸는 것이 아니다.
원사 중심선에서 읽을 수 없는 추가 spin을 자동으로 알아내지 않는다.

### 3.2 Ply의 시작 frame을 부모와 일관되게 연결하기

참조 ply의 초기 normal은 참조 yarn director를 ply tangent plane에 투영해 정한다.
변형 ply에서도 변형 yarn director를 독립적으로 다시 투영하면, ply tangent가
달라질 때 gauge에 따라 다른 추가 spin이 생길 수 있다.

대신 yarn의 상대 회전

\[
Q_y=B_y^d(0)[B_y^r(0)]^T
\]

으로 참조 ply tangent·normal을 함께 운반한다. 다음으로 \(Q_y t_p^r\)를 실제
변형 ply tangent \(t_p^d\)에 맞추는 최소 proper rotation \(A\)를 구해

\[
n_p^d(0)=A Q_y n_p^r(0)
\]

로 정한다. 반대 방향 tangent끼리의 정렬은 해가 유일하지 않으므로 거부한다.
이는 임의의 두 normal projection보다 일관된 운동학적 규칙이며, 실제 ply
torque/twist의 평형을 계산한 결과는 아니다.

## 4. 길이 변화, 변형률, 반지름의 의미

참조 및 변형 fiber segment의 chord 길이를 각각 \(\ell^r_j,\ell^d_j\)라고 하면

\[
\lambda_j=\frac{\ell^d_j}{\ell^r_j},\qquad
\epsilon_j=\lambda_j-1,\qquad e_j=\log\lambda_j.
\]

이 값은 원래 표본 사이의 기하학적 stretch·engineering strain·log strain이다.
섬유 constitutive law, 응력이 없는 rest length, bending strain을 이용해 계산한
물성값이 아니다. 샘플링, 꺾인 parent 곡선, RMF 변화에 따른 국소 집중도 포함될
수 있다. 따라서 전체 길이 변화가 작다는 이유로 local inextensibility를 주장하면
안 된다.

### 4.1 `constant_reference`

각 fiber의 기존 반지름 \(r_0\)를 유지한다. 기존 `FiberCurve`/`OpticalScene` 경로로
전달할 수 있지만, 이산 원통 segment의 부피는

\[
V^d_j=\pi r_0^2\ell^d_j=\lambda_j V^r_j
\]

이므로 길이 변화에 따라 달라진다. 모듈은 이 drift를 보고하며 질량 보존을
주장하지 않는다.

### 4.2 `incompressible_segments`

각 segment에

\[
r_j=\frac{r_0}{\sqrt{\lambda_j}}
\]

를 저장하면 \(\pi r_j^2\ell^d_j=\pi r_0^2\ell^r_j\)가 성립한다. 일정 밀도의
분리된 원통 요소라는 모델에서는 부피/질량 proxy가 보존되지만, 연속적인 원형
튜브의 접합부·곡률·중첩·재료 압축률을 푼 것은 아니다. 밀도도 이 모듈의 입력이
아니므로 `physical_mass_conservation_certified=False`로 남긴다.

현재 광학 adapter는 fiber 하나에 constant radius 하나만 지원한다. 따라서
이 모드에서 `to_hierarchy()`를 호출하면 **명시적으로 실패**한다. 반지름을
평균내거나 일부 segment 값만 선택해 광학 계산으로 넘기지 않는다. 우연히 모든
segment stretch가 같은 특수 예제에서도 이 별도의 모델 승인을 생략하지 않는다.

## 5. API와 보존 데이터

```python
from textile_sim.material_transport import (
    bind_material_reference, transport_material_reference,
    save_material_transport,
)

# v3 fixed-track height-graph fixture: first director is global +z.
normals = {yid: (0., 0., 1.) for yid in initial.yarns}
reference = bind_material_reference(
    initial,
    yarn_initial_normals=normals,
    correspondence="shared_vertex_indices",
)
labels = {
    yid: curve.material_coordinates_mm
    for yid, curve in reference.yarns.items()
}
state = transport_material_reference(
    reference,
    relaxed.yarns,
    yarn_initial_normals=normals,
    deformed_parent_coordinates_mm=labels,
    radius_mode="constant_reference",
)
tracked_geometry = state.to_hierarchy()
save_material_transport("new_output/constant_reference", state)
```

NPZ에는 원래/변형 fiber points, 두 parent 좌표, 현재 호길이, stretch·strain,
segment 반지름·부피, 원래/변형 parent points·frames·director를 저장한다. JSON에는
각 배열 prefix와 부모 관계·fiber provenance·좌표 단위·모델 범위·hash가 있다.
Pickle 없이 읽을 수 있다. 기존 동일 이름 결과를 덮어쓰지 않는다.

원래 reference는 immutable byte-backed 배열과 read-only mapping으로 보존한다.
모든 pose는 원래 reference에서 다시 평가하며, 이전 pose에 반복적으로 새로운
좌표를 누적하지 않는다. 사용자 입력의 mutable 배열·metadata를 후속 수정해도
reference와 state의 데이터가 바뀌지 않는다.

reference hash는 점·frame·ID뿐 아니라 **ply-yarn 연결과 parent 물질 좌표 map**도
포함한다. 공개 dataclass도 부모·family/index·물질 좌표의 일관성을 검사한다.
state는 parent 및 fiber 위치를 지정된 map으로 다시 계산해 비교한다. 다른
geometry를 끼워 넣은 state가 운반 결과라고 표시되는 것을 거부한다.

export는 참조 geometry의 과거 clearance/equilibrium certificate를 상속하지
않는다. 새로운 `audit_clearance()`가 필요하다. parent 높이를 평형으로 계산했어도
그 아래 fiber/ply의 물리 평형까지 계산했다고 표시하지 않는다.

## 6. 실제 v3 optical-pair에 적용한 결과

입력은 보존된 `data/mechanics_v3/optical_pair/{initial,relaxed}`이다. 섬유 수·표본 수·
순서가 그대로 유지됐다. 전체 optical experiment 결과는 v4 driver의 별도 보고서에
기록한다. 아래는 transport geometry 자체를 실제 계산해 얻은 수치다.

| 항목 | 실제 결과 |
|---|---:|
| Fiber / material vertex / segment | 42 / 8,106 / 8,064 |
| 참조 fiber 길이 합 | 40.6111653145 mm |
| 운반된 fiber 길이 합 | 40.6291253596 mm |
| 전체 길이·constant-radius 부피 proxy 변화 | +0.0442244% |
| 경사 fiber 길이 합 변화 | −0.5733227% |
| 위사 fiber 길이 합 변화 | +0.6617715% |
| Segment stretch 최소 / 최대 | 0.859680 / 1.141201 |
| 기준 길이로 가중한 engineering strain RMS | 1.72821% |
| 서로 다른 fiber capsule 간격 하한 | 2.945386 µm |
| 재생성 v3와 v4 운반 vertex의 RMS 차이 | 0.077344 µm |
| Incompressible-segment 부피 proxy 최대 상대 오차 | \(6.66\times10^{-16}\) |

**전체 길이 변화는 작지만 일부 segment의 stretch 변화는 약 ±14%다.** 이 수치는
local material inextensibility나 실제 섬유에 허용되는 변형이 입증되지 않았음을
보여준다. 작은 전체 부피 오차만 보고 물리적 변형의 정확성을 주장하지 않는다.
국소 strain의 mesh 의존성과 실제 물성은 별도로 검증해야 한다.

v3 재생성 결과와 이번 운반 결과의 기하 차이는 이 particular fixture에서 작다.
광학 차이가 Monte Carlo 잡음보다 작을 수 있으며, 큰 시각적 개선을 전제로 하지
않는다. 이번 구현의 주된 성과는 누락됐던 물질 좌표·변형 진단·부피 모델의 구분을
확보한 것이다.

## 7. 검증과 리뷰에서 바뀐 점

`tests/test_material_transport.py`는 17개 검사를 포함한다. 독립 리뷰 검사는
`tests/test_material_transport_review.py`에서 별도로 실행한다.

- Identity와 arbitrary rigid motion에서 모든 fiber point·ID·material label 유지.
- Straight helix의 회전 위상 보존 및 독립적인 helical chord 길이 식과 stretch 비교.
- Parent 물질 좌표가 비균일하거나 target mesh가 달라도 지정된 attachment 유지.
- Axial offset을 포함한 framed point map의 합성·역변환.
- 비균일 segment stretch의 부피 proxy 보존과 부적절한 optical export 거부.
- 원래 입력·출력의 mutable 배열, 잘못된 parent/family, 퇴화 curve, domain 밖 query 거부.
- NPZ raw arrays와 source/state/file hash의 연결, overwrite 거부.
- 참조 표본을 고정한 채 target curve를 세분화해 얻은 수렴 확인.

Smooth target curve의 2,049점 결과와 비교한 최대 fiber vertex 오차는 target 표본
17/33/65/129/257/513/1025개에서 각각
`6.24738e-4 / 1.57641e-4 / 5.36314e-5 / 9.70817e-6 / 2.41105e-6 /
8.03295e-7 / 1.33338e-7 mm`였다. 이 값은 계산한 두 이산 결과 사이의 차이이며
미계산 continuum 오차의 보장값은 아니다.

최초 자체 검사에는 오차 비율이 각 단계에서 3 이상이라는 과도한 조건이 있었다.
33→65점에서 실제 비율이 약 2.94라 실패했다. 최대 오차 위치가 고정된 child query
grid와의 상대 위상에 따라 이동하며, 전체 nested interpolation pipeline에 대해
일률적인 수렴 차수를 증명하지 않았으므로 검사를 **실측 오차 감소와 절대 오차
조건**으로 수정했다. 이를 모델 오류 수정이나 4차 수렴 확인이라고 기록하지 않는다.

독립 리뷰에서 reference hash에 correspondence map이 빠진 점과, public state
생성자가 바꿔 끼운 데이터를 충분히 검사하지 않은 점을 발견했다. 두 사항을 수정하고
회귀 검사를 추가했다. 자세한 내용은 [독립 리뷰](review_material_transport_v4.md)에 있다.

## 8. 다음에 필요한 물리

1. 원래 fiber material coordinate와 자연 길이·rest curvature·material director를
   분리해 정의한다. 관측 reference가 stress-free라고 가정하지 않는다.
2. Fiber/ply의 slip·torsion·strain energy를 포함한 변형 모델과 접촉/압착을 연결한다.
3. Segment strain 집중의 parent/fiber sampling 의존성을 조사하고, 실제 원단에
   허용되는 stretch 범위를 측정한다.
4. Variable-radius optical support를 추가하려면 연속 반지름/표면 모델, renderer
   근사, ray–wave adapter, clearance 검사를 함께 확장한다.

### 관련 기본 문헌

- Wang et al., *Computation of Rotation Minimizing Frames*, ACM TOG (2008):
  [저자 기관 PDF](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/12/Computation-of-rotation-minimizing-frames.pdf).
  Double reflection의 높은 차수 정확도는 tangent 입력 정확도 조건을 포함한다.
  현재 sampled-tangent 전체 계층에 같은 차수를 자동 적용하지 않는다.
- Bergou et al., *Discrete Elastic Rods* (2008):
  [저자 프로젝트](https://www.cs.columbia.edu/cg/rods/).
  Bishop frame과 독립적인 material-frame twist는 구별해야 한다. 현재 모듈은
  해당 rod 에너지·twist 자유도·dynamic solver를 구현한 것이 아니다.
