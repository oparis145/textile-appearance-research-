# Fabric–광학 업그레이드: 국소 부피 보존과 관측 오차 판정

**2026-10-13 / observation-gate 연구 증분. 정식 v0.6 release 또는 전체 엔진 검증을 뜻하지 않는다.**
기준은 `d5ee2b7d4677f8b98f99bac821fec340ffe98c9c`의 v0.5.1이다. 기존 engine, 원시 결과, 425-test 기록은 그대로 보존한다.

## 1. 연구 목적과 이번에 선택한 범위

최종 목적은 **실제 원단의 공간 디테일을 보존하면서, 새로운 조명·시점·역광에서의 외관을 예측해 실물 판단의 차이를 줄이는 것**이다. 4K·매크로·다중조명 RGB는 강한 비교군으로 유지한다. VIS를 기준으로 하고 IR·편광·분광·메타광학은 실제 추가 정보가 있을 때 연결한다. 염색·퇴색과 모든 촉감의 예측은 이번 범위 밖이다.

문헌을 검토한 결과, 계층 기하/변형/ply 외관/최적 관측이라는 조합 자체에는 직접적인 선행연구가 있다. 따라서 원단 엔진을 계속 크게 만드는 대신 **물리적 작은 차이와 수치·표현 오차를 구분할 기반**부터 보강했다. 문헌별 읽기 깊이와 실행하지 않은 방법은 [문헌 ledger](../notes/literature_observation_upgrade.md)에 기록했다.

현재 v5의 알려진 병목은 단면 부피가 수렴해도 광택이 크게 변하고, 전체 부피를 맞추어도 개별 선분의 부피가 재분배된다는 점이다. 이번 코드는 그 두 문제의 제한된 기준 문제를 해결하고, 관측 기반 판정 모듈을 추가한다. **기존 3D 원단의 25.7–31.6% radiance 변화 원인을 전부 규명하거나 수정한 것은 아니다.**

## 2. 모듈과 실제 연결

| 신규 모듈 | 입력 -> 출력 | 실제 실행 범위 |
| --- | --- | --- |
| `local_volume_profile.py` | 선분 길이·목표 반지름 -> 양의 연속 정점 반지름 | 선분별 직선 원뿔대 부피 보존, 16개 합성 변형 사례 |
| `surface_reference.py` | 원형/정다각형 단면·입사 분포 -> 첫 계면 반사각별 전력 | 2D 기하광학, 252개 조건; 내부 굴절 이후 경로는 추적하지 않음 |
| 같은 모듈의 `observe`/`angular_lod` | 각도 전력 -> 유한 각도 응답·bin 또는 축약 | 21개 각도 분포 압축 사례; ply/fabric BSDF가 아님 |
| `observation_gate.py` | 정렬된 반복·관측값·사전 허용량 -> 동등/상이/미결정 | 다중 조건 paired-t 판정과 최소 비용 선택 |
| `audit_v5_radial_pair` | 기존 v5 scalar NPZ와 metadata -> paired 관측 판정 | 실제 schema에 맞춘 fixture 검증. 기존 비공개 원시 NPZ는 이 환경에서 새로 실행하지 않음 |
| `run_observation_upgrade.py` | 명시적 출력 폴더 -> 수치 JSON·hash manifest | 기존 결과 덮어쓰기 거부, 소스 불변 검사, 결정론적 재실행 확인 |

실제 계산 경로는 `단면 -> 첫 표면 반사 -> 각도 응답 -> 검출기 적분 -> 오차/비용 선택`이다. Fabric 경로는 `기존 물질선분 목표 부피 -> 새 연속 반지름 -> 독립 적분 검산`까지다. **새 반지름이 기존 closed-mesh renderer에 자동 적용되지는 않는다.** 그 연결은 곡선 tube의 자기 교차·실제 mesh 부피·광학 수렴을 따로 검사한 뒤 수행한다.

## 3. Fabric: 각 선분의 부피를 보존하는 반지름

현재 길이가 l_i, 목표 원통 proxy의 반지름이 R_i일 때 V_i*=pi*l_i*R_i^2로 둔다. 이 값이 실제 재료의 부피라는 것은 상위 모델이 입증해야 할 가정이다. 정점 반지름 r_i를 선분에서 선형 보간하면:

\[
V_i(r)=\frac{\pi l_i}{3}(r_i^2+r_i r_{i+1}+r_{i+1}^2).
\]

따라서 각 선분의 제약은:

\[
r_i^2+r_i r_{i+1}+r_{i+1}^2=3R_i^2,
\quad r_{i+1}=f_i(r_i)=\frac{-r_i+\sqrt{12R_i^2-3r_i^2}}{2}.
\]

f_i는 허용 구간에서 감소하고 자기 역함수다. 끝에서부터 양의 반지름 허용 구간을 역전파하고, 가능한 첫 반지름 중 기존의 부드러운 profile에 가까운 값을 1D 최적화로 고른다. 작은 반지름 근처의 상쇄를 줄이기 위해 구현에서는 유리화한 식을 사용한다. 최적화 성공 플래그에만 의존하지 않고 모든 선분을 다시 적분해 잔차를 검사한다.

중요한 한계:

- 어떤 입력은 양의 연속 선형 반지름으로 표현할 수 없다. 작은–큰–작은 단면의 불가능 사례를 거부하며 부피를 몰래 바꾸지 않는다.
- 끝점 반지름을 고정하지 않는다. 이를 고정하면 별도의 양립성 문제가 생긴다.
- 보존 대상은 **직선 chord의 원뿔대 적분**이다. 굽은 삼각망 고체의 부피, local incompressible constitutive law, material twist, 접촉력까지 해결했다는 뜻이 아니다.
- 허용구간은 부동소수점 계산과 사후 잔차 검사이며 엄밀한 interval-arithmetic 증명은 아니다. 1D 목적함수의 전역 최적성도 주장하지 않는다.

### 실제 결과

16/64/128/256 선분, 사인형 신장 진폭 0/3/10/25%의 16개 합성 조건을 계산했다. 비교군은 문서화된 v5의 길이 가중 단면 보간+전체 부피 rescale 규칙을 독립 재구현한 것이다.

- 비교 규칙의 최대 선분 부피 상대 오차: **2.4930479438%**.
- 새 규칙의 최대 선분 부피 상대 오차: **6.6613381478e-16**.
- 두 규칙 모두 전체 적분은 맞출 수 있다. 따라서 차이는 전체량이 아니라 **어디에 부피가 배분되는가**에 있다.
- 선형 반지름의 제곱을 Simpson 적분한 별도 검사와 길이 단위 상사 검사를 통과했다.

이 결과는 부피 계약의 개선이며 광택이나 실물 외관의 개선 수치는 아니다.

## 4. 광학: 첫 표면 반사 기준해

무한 원통 축은 z, 입사/출사 방향은 xy 평면이다. 외부 굴절률 1, 내부 실수 n>=1의 s/p Fresnel 전력 반사를 사용한다. 파동 효과·섬유 간 차폐·내부 반사·흡수는 계산하지 않는다.

### 원형 단면

입사 진행 방향을 0으로 두고 출사각 psi를 [0,2pi)로 표현하면 단위 입사 폭 2R당 전력 밀도는:

\[
p(\psi)=\frac14\sin(\psi/2)F(\sin(\psi/2)).
\]

F는 Fresnel 반사율이다. 각도 bin 내부 Gauss–Legendre 적분을 하고 전방의 주기적 cusp를 지나는 bin은 분할한다. 별도의 impact-parameter 적분으로 총 반사량을 검산한다.

### N각형 단면

외향 법선각 gamma_j와 입사 방향 phi에 대해 c_j=max[-cos(gamma_j-phi),0]이고:

\[
w_j=\sin(\pi/N)c_jF(c_j),\qquad
\psi_j=2\gamma_j-\phi+\pi.
\]

원형과 **같은 입사 폭 2R**로 정규화한다. 다각형의 작은 silhouette를 보정해서 결과를 같게 만들지 않는다. 반사 전력, 물질로 들어갔으나 더 추적하지 않은 전력, 놓친 입사 전력을 각각 기록한다. 면적비 N*sin(2pi/N)/(2pi)는 광학 오차와 별도로 계산한다.

### 관측 연산자

출사 전력에 normalized wrapped Gaussian **각도 응답**을 적용한 뒤 detector bin에서 적분한다. 이는 공간 camera blur가 아니다. 입사 광원 역시 횡단면의 Gaussian 진행각 분포이며 실제 3D 면광원과 동일하지 않다.

\[
\epsilon_q=\frac{\|H_qp_N-H_qp_{circle}\|_2}{\|H_qp_{circle}\|_2}.
\]

총 반사량의 오차와 각도 분포 오차를 둘 다 검사한다. 격자 4096/8192, 광원 적분 81/161을 비교한 차이는 수렴 진단이지 엄밀한 전역 오차 상한은 아니다.

## 5. 실제 광학 결과와 리뷰에서 찾은 정렬 오류

7개 단면 분할(16–1024) x 2개 입사각 폭(0,2도) x 3개 단면 위상(0,1/4,1/2 step) x 2개 detector bin 수(256,512) x 3개 각도 응답 폭(0.5,2,8도) = **252조건**을 계산했다.

사전 설정한 관측 L2 2%, 총전력 1%, 수치 refinement 진단 0.5%를 모두 만족하는 최저 비용 후보를 골랐다. 여기서 비용은 단면 수 proxy이며 실제 GPU 실행시간이 아니다.

| 단면 수 | 모든 선택 조건의 최대 상대 L2 | 최대 총 반사량 오차 | 판정 |
| ---: | ---: | ---: | --- |
| 64 | 220.06% | 1.0920% | 거부 |
| 256 | 68.05% | 0.06940% | 거부 |
| 512 | 10.47% | 0.01737% | 거부 |
| 1024 | 0.05809% | 0.004342% | 선택 |

최초 탐색은 detector 256개와 제한된 위상만 사용해 512각형을 선택했다. 재검토 중 **detector bin과 specular facet 방향의 우연한 정렬**이 낮은 오차를 만들 수 있음을 확인했다. bin 수와 quarter-phase를 추가하자 위 선택으로 바뀌었다. 이 실패를 회귀 테스트에 넣었다.

선택에 쓰지 않은 source sigma=1도, phase=0.137 step, detector=1024, sensor sigma=0.75/3도 두 조건의 상대 L2는 각각 **4.04135e-6 / 1.75394e-6**였다. 두 조건만의 추가 확인이며 일반적인 모든 관측의 보장은 아니다. **‘모든 fiber는 1024각형이 필요하다’는 결론도 아니다.** 굴절·다중 산란·광원·거칠기가 달라지면 필요한 수가 달라진다.

에너지 보존 angular histogram 축약 21조건도 별도로 계산했다. 2% 상대 L2를 만족하는 최소 그룹 수는 이 원형 기준에서 sensor sigma 0.5/2/8도일 때 128/64/32였다. 이는 관측 대역폭에 따른 정보 보존의 작은 예시이며 fiber->ply->fabric BSDF 축약 결과가 아니다.

## 6. ‘차이를 못 찾음’과 ‘충분히 같음’을 구분하는 gate

입력은 [독립 paired repeat, condition]이다. seed를 반복 단위로 쓰며 픽셀·RGB 채널·파장을 반복 수로 늘리지 않는다. 차이 d의 simultaneous paired Student-t 구간을 계산하고 사전에 정한 절대 허용량 +/-tau 안에 **구간 전체가 들어갈 때만** equivalent로 판정한다. 조건 수에 따른 Bonferroni 보정을 적용한다. 추가 오차 margin은 외부에서 근거를 가진 값으로 주어야 한다.

- equivalent: 확장된 구간 전체가 허용량 내부.
- different: 구간 전체가 허용량 바깥 한쪽에 위치.
- inconclusive: 둘 중 어느 쪽도 확정하지 못함.

평균 차이 0이지만 반복 차이가 +/-0.1인 대조군은 tau=0.01에서 **inconclusive**로 나왔다. CI가 0을 포함한다는 이유로 수렴을 선언하지 않는다. Student-t는 독립 반복 차이의 분포 가정을 사용하며 실물/모델/교정 오차를 자동 포함하지 않는다.

기존 v5 archive reader는 메타데이터 schema, SHA, 축 순서, scalar dtype, seed ID와 shape를 검사한다. 실제 파일의 모양은 저장소 verifier에서 대조했고, 이번 실행에서는 같은 schema의 fixture로 확인했다. 원래 v5 NPZ 전체의 새 재검산이나 425개 기존 suite 재실행은 하지 않았다.

## 7. 재현과 근거

```bash
# 저장소 루트. 기존 numpy/scipy 의존성으로 새 모듈만 검사한다.
python -m unittest discover -s tests -p 'test_observation_upgrade.py' -v
python run_observation_upgrade.py --output scratch_runs/observation_v6 --dry-run
python run_observation_upgrade.py --output scratch_runs/observation_v6

# 기존 v5 파일을 읽을 때에는 독립적으로 정한 절대 radiance 허용값을 명시한다.
# 아래 0.001은 사용법 예시일 뿐, 실제 원단의 보편적인 오차 기준이 아니다.
python run_observation_upgrade.py --output scratch_runs/observation_v5_audit \
  --v5-input data/variable_radius_v5 --coarse 32 --fine 64 \
  --absolute-tolerance 0.001
```

새 모듈 suite **55 tests, failures/errors/skips 0**. Python 3.13.5, NumPy 2.3.5, SciPy 1.17.0 환경이다. 기존 v0.5.1의 425-test 기록과 합산해 전체 통과 수로 주장하지 않는다. 새 full 3D/Mitsuba render는 **0회**다.

[요약 수치](../data/observation_gate_v6/summary.json), [테스트 기록](../data/observation_gate_v6/test_summary.json), [실행 manifest](../data/observation_gate_v6/run_manifest.json)에 이번 결과를 구분해 보존한다. 전체 raw JSON은 runner가 생성하는 `results.json`이다. 원본 raw와 초기/재검토 실행은 별도 배포 ZIP에도 포함하며, 저장소에는 compact summary와 생성 코드를 올린다. manifest의 raw hash는 그 전체 파일의 해시다. 같은 소스로 두 번 실행한 raw JSON이 byte-identical임을 확인했다.

## 8. 다음 연구의 명확한 경계

1. 원형 analytic hit -> 곡선 fiber -> 두 fiber 교차 -> 작은 fabric patch 순으로 새 reference를 확장한다. 현재 2D 첫 반사 결과를 기존 모든 3D 경로의 정답으로 사용하지 않는다.
2. 새 국소 반지름을 기존 물질좌표에 연결한 뒤, 굽은 고체의 부피·self-contact·실제 경계 법선을 검증한다. 전역 rescale로 mesh 오차를 숨기지 않는다.
3. 수렴한 explicit-fiber 영상과 ply/yarn/SGGX 기준선을 같은 R/T 관측에서 비교한다. `g(omega)` 오차와 BSDF/영상 오차를 분리한다.
4. 실제 thread/작은 원단의 R/T를 교정하고 strong RGB baseline을 만든다. 관측 선택은 model mismatch와 새로운 시편에서도 이득이 남는지 평가한다.
5. 유효 채널만 기존 광학과 메타광학으로 구현한다. throughput/crosstalk, 시간·광량·픽셀·전체 부피를 동일 기준으로 비교한다. 현재 구현은 그 이득의 실증이 아니다.
