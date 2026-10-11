# v0.5 가변 반지름의 연속 외형과 닫힌 튜브 기하

## 목적과 현재 범위

v0.4의 `incompressible_segments`는 기준 섬유의 물질 좌표를 유지하며 **직선 원통 선분 부피 근삿값**을 보존한다. 광학 엔진에서 그 상태를 렌더링하려면 선분마다 정의된 반지름을 실제 표면으로 바꾸는 계약이 필요하다. v0.5의 `textile_sim/variable_radius.py`는 이 중간 단계를 명시적으로 구현한다.

이 모듈은 다음을 구분한다.

1. **원래 선분 상태:** 각 물질 선분의 길이와 반지름, 원통 부피 근삿값.
2. **연속 반지름 표현:** 원래 정점에 정의한 양의 반지름과 선형 보간, 직선 원뿔대의 정확한 적분.
3. **렌더링 표면:** RMF 고리와 삼각형으로 만든 닫힌 표면, 그 삼각망의 실제 signed volume과 표면적.

세 부피를 서로 같은 것으로 취급하지 않는다. 첫 번째에서 두 번째로 가는 과정은 한 섬유의 총 적분만 보존하며, **개별 물질 선분 부피는 재분배**한다. 두 번째에서 세 번째로 가는 과정에는 단면 다각형화, 중심선 굽힘, 고리 방향 및 축방향 표본화가 관여한다. 삼각망을 다시 확대해 부피 오차를 숨기지 않는다.

현재 계층은 원형 단면만 지원한다. 타원·비원형 단면, 재료 단면의 물리적 twist, Poisson ratio, 응력·접촉·마찰·수축 등의 구성식은 이 모듈의 해가 아니다.

## 1. 데이터 계약

`VariableRadiusFiber`의 입력은 다음과 같다.

| 입력 | 의미 |
|---|---|
| `points_mm[N,3]` | 현재 섬유 중심선의 물질 정점 위치 |
| `material_coordinates_mm[N]` | 원래 섬유에 붙인 물질 좌표; 현재 arclength로 다시 쓰지 않음 |
| `parent_material_coordinates_mm[N]` | 부모 ply에 붙은 원래 좌표 |
| `segment_radius_mm[N-1]` | 현재 각 선분에 정의한 원통 반지름 |
| fiber/yarn/ply/material ID | 동일한 섬유, 부모 및 구성 재료의 이름 |
| family와 계층 index, kind | 경사·위사와 원래 계층 기록 |
| `provenance_json` | 원래 상태·기준 상태의 hash, radius mode와 대응 가정 |
| `length_unit`, `cross_section` | 명시적인 `mm`, `circle` |

필수 수치 배열은 finite이며, 선분 길이와 반지름은 양수여야 한다. 두 물질 좌표는 0에서 시작해 엄격하게 증가한다. 현재 위치와 물질 좌표가 동일한 arclength를 갖도록 강제하지 않는다. 그 차이가 변형을 나타내기 때문이다.

배열은 immutable bytes backing을 사용한다. 원래 caller 배열을 바꾸거나 NumPy의 WRITEABLE flag를 다시 켜서 저장 상태를 변경할 수 없다. 메타데이터는 유한한 JSON object로 직렬화한다. 프로필의 semantic hash는 기하, 반지름, 두 물질 좌표, 부모·재료·계층 정보와 provenance를 포함한다.

`profiles_from_transport(state)`는 유효한 v0.4 `MaterialTransportState`를 받아 tuple을 생성한다. 다음을 그대로 보존한다.

- 물질 정점 순서·위치와 두 좌표 배열.
- 모든 fiber/yarn/ply/material ID, family, 계층 index, kind.
- 기준 상태 및 현재 상태의 SHA-256.
- 원래 `constant_reference` 또는 `incompressible_segments` 모드.

이 adapter는 원래 반지름 상태를 구별해서 기록한다. 이름이 다른 재료를 혼합해 단일 유효 굴절률로 만드는 작업은 하지 않는다.

## 2. 선분 원통에서 연속 반지름으로

현재 선분의 길이와 반지름을 각각 \(\ell_e>0\), \(r_e>0\)라고 한다. 원래 근삿값은

\[
V_e^{\mathrm{cyl}}=\pi r_e^2\ell_e,
\qquad V^{\mathrm{cyl}}=\sum_eV_e^{\mathrm{cyl}}.
\]

v0.4의 선분 부피 보존 모드에서는 \(r_e=r_0/\sqrt{\lambda_e}\)를 사용하므로 이 근삿값이 기준 상태와 일치한다. 이 식 자체가 굽은 섬유의 실제 3차원 부피, 밀도 또는 물리적 질량 보존을 입증하지는 않는다.

### 2.1 길이로 가중한 정점 단면적

\(a_e=r_e^2\)라고 두고, 내부 정점의 첫 반지름을 다음과 같이 만든다.

\[
\widetilde r_i^2=
\frac{\ell_{i-1}a_{i-1}+\ell_i a_i}{\ell_{i-1}+\ell_i}.
\]

끝점은 인접한 선분의 반지름을 사용한다.

\[
\widetilde r_0=r_0,\qquad
\widetilde r_{N-1}=r_{N-2}.
\]

이 규칙은 **단면적을 연속 정점 표현으로 옮기는 선택된 근사**다. 미분방정식을 풀어 찾은 단면이나 유일한 최적 해로 주장하지 않는다. 반지름의 산술 평균과도 다른 규칙이다. 임의 smoothing strength를 숨기지 않고 고정된 식을 schema에 기록한다.

### 2.2 선형 반지름의 정확한 직선 적분

한 직선 선분에서 반지름이 \(r_i\)에서 \(r_{i+1}\)로 선형으로 변하면

\[
V_e^{\mathrm{frustum}}
=\int_0^{\ell_e}\pi r(s)^2\,ds
=\frac{\pi\ell_e}{3}
\left(r_i^2+r_ir_{i+1}+r_{i+1}^2\right).
\]

정점 반지름을 모두 같은 양의 수 \(q\)로 곱하면 이 적분은 \(q^2\)배가 된다. 따라서

\[
q=\sqrt{\frac{V^{\mathrm{cyl}}}
{\sum_eV_e^{\mathrm{frustum}}(\widetilde r)}},
\qquad r_i^{\mathrm{node}}=q\widetilde r_i
\]

를 적용한다. 부동소수점 오차 범위에서

\[
\sum_eV_e^{\mathrm{frustum}}(r^{\mathrm{node}})=V^{\mathrm{cyl}}
\]

가 된다. **섬유별**로 q를 구하므로 다른 섬유나 다른 재료 사이로 부피를 이동하지 않는다.

각 선분의 상대 오차는

\[
\epsilon_e=
\frac{V_e^{\mathrm{frustum}}-V_e^{\mathrm{cyl}}}{V_e^{\mathrm{cyl}}}
\]

로 저장한다. 총합이 보존되더라도 \(\epsilon_e\)는 0이 아닐 수 있다. 최대 절대 선분 오차와, 원래 부피로 가중한 평균 절대 오차를 별도로 보고한다. 이 때문에 새 표면을 `locally incompressible`이라고 표시하지 않는다.

### 2.3 단위와 특수 경우

- 단일 선분 또는 일정한 반지름에서는 같은 일정한 반지름이 부동소수점 허용 오차 내에서 유지된다.
- 모든 길이·반지름·물질 좌표를 \(c\)배 하면 반지름은 \(c\)배, 면적은 \(c^2\)배, 부피는 \(c^3\)배가 된다.
- 형상 좌표의 단위를 `m`로 바꾸어 넣고 `mm`로 해석하는 암묵 변환은 허용하지 않는다.
- 0 또는 음수 반지름, 중복 정점, 비유한 배열, 증가하지 않는 물질 좌표, 지원하지 않는 단위·단면은 거부한다.

## 3. RMF 단면에서 닫힌 삼각망으로

현재 중심선에서 double-reflection rotation-minimizing frame을 계산한다. 이 방법의 원전은 Wang, Jüttler, Zheng, Liu의 *Computation of Rotation Minimizing Frames*, ACM TOG 27(1), 2008이다. [저자 기관 논문 페이지](https://www.microsoft.com/en-us/research/publication/computation-rotation-minimizing-frames/).

여기서 사용한 표본 tangent, 선형 반지름, 단면 고리와 삼각화 전체 파이프라인의 차수를 원 논문의 RMF 알고리즘 차수와 동일하다고 주장하지 않는다. 곡률이 큰 영역에서는 별도의 축방향 수렴 검사가 필요하다.

정점 i의 tangent, 첫 normal, 두 번째 normal을 \((\mathbf t_i,\mathbf n_{1i},\mathbf n_{2i})\)라고 하면, M각형 단면의 j번째 정점은

\[
\mathbf v_{ij}=\mathbf p_i+r_i
\left[
\mathbf n_{1i}\cos(2\pi j/M)
+\mathbf n_{2i}\sin(2\pi j/M)
\right].
\]

고리 사이의 사각 면을 두 삼각형으로 나눈다. 시작과 끝에는 중심점과 M개의 삼각형 cap을 추가한다. 시작 cap은 \(-\mathbf t_0\), 끝 cap은 \(+\mathbf t_{N-1}\) 방향으로 감긴다. 직선 원통에서 옆면이 외부를 향하도록 정점 순서를 정했고, 기하 법선과 국소 방사 방향의 내적을 계산해 뚜렷하게 접힌 옆면을 거부한다.

수치 파일에는 실제 삼각형의 face normal을 저장한다. **반지름이 변하면 옆면 법선에 축방향 성분이 생긴다.** 단면의 방사 방향을 실제 표면 법선으로 대체하면 원뿔대의 반사·굴절 방향이 틀릴 수 있다. 면적 가중 vertex normal은 선택적 shading 자료로도 제공하지만, cap과 옆면의 sharp edge를 자동으로 분리하는 모델은 아니다. 현재 광학 연결에서는 기하 면 법선을 사용하는 것이 해석하기 쉽다.

### 초기 normal 보존

RMF는 초기 normal 선택에 의존한다. 원형 연속 단면은 그 좌표계 선택에 무관하지만, 유한 M각형 표면의 위상은 영향을 받을 수 있다. 따라서 실험 간에 같은 seed를 사용하거나 실제로 함께 회전시켜야 한다.

초기 구현 검토에서는 projected normal을 저장한 뒤 다시 정규화하면 ulp 수준 차이 때문에 정확한 저장/복원 비교가 실패하는 문제가 발견됐다. 현재는 **최초 입력 seed**를 immutable 배열로 저장한다. 입력이 None이면 기존 RMF가 선택하는 Cartesian axis를 명시적으로 저장한다. 계산된 실제 projected normal은 `frames[0,:,1]`로 별도 확인할 수 있다.

## 4. 실제 삼각망 부피와 단면 오차

닫힌 oriented triangle mesh의 signed volume은 수치 기준점 \(\mathbf o\)에 대해

\[
V_{\mathrm{mesh}}=\frac16\sum_f
(\mathbf v_{f0}-\mathbf o)\cdot
\left[(\mathbf v_{f1}-\mathbf o)\times(\mathbf v_{f2}-\mathbf o)\right]
\]

로 계산한다. 큰 world translation에서 상쇄 오차를 줄이기 위해 정점 평균을 수치 기준점으로 사용한다. 그 평균이 실제 고체 내부에 있다고 가정할 필요는 없다.

직선의 정렬된 원통·원뿔대에서는 정M각형 단면의 부피가 원형 적분의 다음 배수다.

\[
f_M=\frac{M\sin(2\pi/M)}{2\pi}.
\]

| 단면 각 수 M | 원형 대비 다각형 부피 감소 |
|---:|---:|
| 16 | 약 2.5505% |
| 32 | 약 0.6413% |
| 64 | 약 0.1606% |

이 식은 직선 oracle이며 굽은 tube의 부피에 그대로 적용하는 보존 법칙이 아니다. 다음 값을 함께 보고한다.

- 원래 원통 선분 총 부피 근삿값.
- 연속 반지름의 직선 원뿔대 총 적분.
- 실제 삼각망 signed volume 및 surface area.
- 삼각망/원뿔대 적분의 상대 차이.
- 직선 다각형 factor를 나눈 뒤 남는 상대 차이. 이는 진단 값이며 실제 geometry를 재정규화하지 않는다.
- 고리 반지름의 다각형 sagitta 상한 \(r_{\max}[1-\cos(\pi/M)]\).
- 인접 frame tangent 각, 이산 \(r\kappa\) 지표 및 반지름 기울기.

Sagitta 값은 **단면 고리**의 원과 다각형 사이 오차다. 굽은 tube의 내부 삼각 면, 새로운 교차 여부, 전체 표면의 Hausdorff 오차까지 증명하는 bound는 아니다.

## 5. topology, clearance, 물리적 한계

현재 생성 결과는 다음 검사를 통과해야 한다.

- 모든 삼각형 면적과 법선이 유한하고 면적이 양수다.
- 각 undirected edge가 정확히 두 면에 속하고 두 방향이 반대다.
- 모든 정점을 사용하며 구면 topology의 Euler characteristic가 2다.
- 닫힌 표면의 signed volume이 양수다.
- 옆면의 국소 법선 및 cap 방향이 정한 방향과 일치한다.

**이 검사는 서로 멀리 떨어진 면의 교차를 증명하지 않는다.** 자기 관통이 있어도 edge incidence와 Euler characteristic는 정상일 수 있고 signed volume도 양수일 수 있다. 따라서 `self_intersection_tested=False`, `inter_fiber_clearance_tested=False`, `physical_mass_conservation_certified=False`를 출력한다.

다른 섬유와의 간격은 원래 constant radius audit를 물려받으면 안 된다. 새 node radius의 최댓값과 실제 중심선·삼각망 표현에 맞는 보수적 경계를 사용해 다시 검사해야 한다. 실험 driver의 새로운 간격 검증과, 이 모듈의 단일 tube topology 검증은 서로 다른 검사다.

## 6. 저장·복원과 실행 예

```python
from textile_sim.variable_radius import (
    profiles_from_transport, build_tapered_tube,
    save_variable_radius_profiles, save_tapered_tube,
    load_variable_radius_profiles, load_tapered_tube,
)

profiles = profiles_from_transport(transport_state)
save_variable_radius_profiles(output / "profiles", profiles)

mesh = build_tapered_tube(profiles[0], radial_segments=32,
                          initial_normal=(1.0, 0.0, 0.0))
save_tapered_tube(output / "fiber_00000", mesh)

restored_profiles = load_variable_radius_profiles(output / "profiles")
restored_mesh = load_tapered_tube(output / "fiber_00000")
assert restored_mesh.sha256 == mesh.sha256
```

실제 섬유 tangent와 평행한 initial normal은 사용할 수 없다. 실험에서는 유효한 공통 seed나 명시적으로 운반한 seed를 선택해야 한다.

프로필은 `variable_radius_profiles.json` + `.npz`, 개별 mesh는 `tapered_tube.json` + `.npz`로 저장한다. object/pickle 자료를 사용하지 않는다. 복원은 다음을 수행한다.

1. 파일 이름이 정한 local 파일인지 확인하고 NPZ byte hash를 대조한다.
2. 원래 source array와 metadata에서 프로필을 다시 계산한다.
3. 저장한 node radius, 선분 부피 및 요약과 재계산 값을 대조한다.
4. 저장한 원래 RMF seed에서 mesh를 다시 계산한다.
5. 모든 정점·face·frame·normal과 semantic digest를 대조한다.

기존 산출물 경로의 파일은 덮어쓰지 않는다. 변조 시험에서는 NPZ의 byte checksum까지 다시 계산한 허위 node radius 또는 뒤집힌 triangle이 재계산 검증에서 거부되는지 확인한다. 이 일관성 검증만으로 외부 실물 데이터의 진위나 실험의 역사적 실행을 증명하는 것은 아니다.

## 7. 테스트와 리뷰

저자 테스트 `tests/test_variable_radius.py`는 24개다. 실제 실행에서 24/24 통과했다. 항목은 다음과 같다.

- 손으로 계산한 길이 가중 단면적·전역 보정 계수·선분별 재분배.
- 단일 선분·불균일 표본 간격의 일정 반지름 특수 경우.
- 물질 좌표·계층·material ID·source hash 보존과 두 원래 radius mode.
- 단위 스케일의 길이/면적/부피 차원 및 강체 회전 공변성.
- 정다각형 원통·원뿔대의 정확한 부피, taper 옆면 법선과 cap 방향.
- 단면 분할 증가에 따른 원형 부피·표면적 수렴.
- 굽은 tube의 실제 volume 차이 및 contact 미검증 상태.
- 모든 저장 배열의 비가변성, NaN·단위·좌표·반지름 잘못된 입력 거부.
- nonpickle 저장/복원, triangle·radius 변조 검출, 경로 변경 및 덮어쓰기 거부.

독립 검토 파일 `tests/test_variable_radius_review.py`는 별도 담당자가 구현한다. 최종 통합 실행 수와 광학 검증 결과는 v0.5 실험·리뷰 기록에서 확인해야 한다. 이 문서의 24개는 본 모듈 저자 테스트 수이며 전체 프로젝트의 총 테스트 수가 아니다.

## 8. 다음 연결

광학 adapter는 `TaperedTubeMesh.vertices_mm`와 `faces`를 읽고 `profile.material_id`에 해당하는 원래 재료 spectrum을 적용할 수 있다. 새로운 반지름을 기존 constant-radius hair 파라미터에 조용히 평균해서 넣지 않는다. 구체적인 경계 BSDF·매질 흡수·검출기 단위와 수렴 검증은 광학 adapter의 계약으로 이어진다.

이 모듈이 제공하는 것은 **같은 물질 상태 → 공개된 반지름 근사 → 검사 가능한 표면**의 연결이다. 실물 원단의 기계적 변형·광학 외관 정확도와 전체 옷 재현은 실측 및 별도 모델 검증이 필요하다.
