# Change log

변경 기록은 구현한 기능과 검증 범위를 기준으로 작성한다. 최종 배포 commit/tag는 [작업 로그](docs/WORK_LOG.md)에서 확인한다. 현재 저장소에 별도의 오픈소스 라이선스를 부여하지 않았다.

## 0.4.0 — 2026-10-11

### Research identity

- 같은 비공개 저장소를 `Phill-lms/textile-appearance-research`로 이름 변경. 연구 제목은 **직물 외관 재현을 위한 다중 규모 광학 모델링과 메타광학 계측 / Multiscale Textile Appearance Modeling and Meta-Optical Sensing**.
- README·About·CITATION을 연구 목적에 맞추고, 연구헌장에 대화의 요구사항·유지할 결정·모듈·검증 기준을 연결.
- 연구 모듈 R-M과 구현 모듈 H/K/O/V/C/Q를 구분. 원래 목표, 강한 RGB 비교군, VIS/IR 역할, 원단별 실측 물성, 메타표면의 이득 검증, 촉감의 별도 기준과 염색·퇴색 보류를 유지.

### Added

- `material_transport.py`: 명시적 reference/target director와 부모 correspondence, immutable reference labels, yarn→ply→fiber의 3-component framed offset map.
- `FramedCurve`의 RMF/SO(3) 보간과 지원 범위 검사, reference/state semantic hash, 부모·fiber·mode·pose의 정합 검사.
- 선분별 stretch·engineering/log strain·반지름·원기둥 부피 proxy 저장. 일정 반지름과 선분 proxy 보존 모드를 구분하고, 가변 반지름의 기존 광학 export를 차단.
- `run_material_transport_experiments.py`: initial/regenerated/transported 기하, 두 radius mode, 새 clearance·scene·spline audit, 공통 rig의 450/550/650 nm 비교.
- `verify_material_transport_artifacts_v4.py`: 저장 raw arrays에서 물질좌표·frame·기하·strain·부피·scene·curve·투영량·paired radiance를 재검산. Producer 완료와 전체 output hash ledger 확인.
- `run_engine_v4.py`: experiment→verify→tests, cold dry-run, 출력 분리, 명시적 렌더 예산, 부분 실패의 미확정 횟수, source/input/output hash와 기존 결과 검산의 구분.
- 실제 최종 108회 단색 렌더와 원시 배열·그림, 수학/API·실험 설명·독립 리뷰. 원래 v3 계층/평형/분광 자료는 그대로 보존.

### Fixed during independent review

- 새 ply tangent에 초기 normal을 독립 투영할 때 좌표계 선택에 따라 생길 수 있던 spurious spin: reference ply director를 parent rotation으로 운반한 뒤 최소 tangent 정렬.
- Reference hash에서 빠진 부모 대응을 포함하고, 다른 reference·radius mode·잘못된 부모/위치가 섞인 state를 거부.
- 그래프의 고정 strain 범위에 의한 clipping과 seed 수 하드코딩 제거. 절대 밝기 차이의 CI를 관측 baseline으로 나눈 표시를 모수의 상대비율 CI와 구분.
- Verify-only 경로에서도 저장 producer의 source hash와 현재 source를 대조. 과거 외부 입력의 절대 경로를 재탐색하는 대신, 저장 실험 폴더를 독립 재구성하고 run 중 변화를 검사.

### Actual outcomes and boundaries

- 42 fibers / 8,106 vertices / 8,064 segments의 material labels 보존. 총 길이 +0.0442244%와 국소 strain 약 −14~+14%의 상쇄를 확인.
- 선분 proxy 보존 모드의 최대 상대 부피 잔차 6.66e−16. 이 수치는 3D 전체 체적·질량·접촉 물리의 보존 증명이 아님.
- 재생성과 추적 사이의 위치 RMS 차이 0.07734 μm. 9개 조명·파장 조건 중 8개의 pointwise 95% 구간이 0 포함; 실물 외관 정확도 개선을 주장하지 않음.
- 최종 전체 테스트·실험·독립 검산 수치는 [v0.4 릴리스 설명](docs/RELEASE_V0_4.md)과 [현재 test summary](data/final_test_summary.json)에 기록.
- 원본 pilot 108회 후 표시·일반 입력 범위 리뷰를 반영해 최종 108회를 재실행. 두 run의 원시 radiance는 byte까지 동일하므로 독립 표본 수를 늘린 것으로 계산하지 않음. [Pilot checkpoint](data/validation_v4/pilot_checkpoint/checkpoint.json)에서 공통 원시 파일을 content hash로 연결하고 변경 파일·당시 source를 보존.
- 현재 모듈은 prescribed no-slip kinematics이며 stress-free reference·full rod/contact/sliding/twist equilibrium·가변 radius renderer·실측 원단·메타표면 효과는 후속 연구.

## 0.3.0 — 2026-10-11

### Added

- `YarnElasticity`, `ReducedWeaveSpec`, `ReducedWeaveProblem`, `WeaveEquilibrium`: fixed projected tracks의 yarn-height quasi-static 모델.
- Exact segment stretch와 작은 기울기 bending 에너지·analytic gradient/Hessian, tension-domain convexity, fixed endpoints, independent warp/weft constitutive inputs.
- Draft/slope/envelope gap의 conservative linear inequalities와 same-family pitch 조건; SLSQP·Hessian preconditioning 및 독립 KKT 검사.
- `build_relaxed_hierarchy()`의 v2 fiber/ply/yarn bridge; regenerated-fiber length/volume와 material-point 비보존 상태 기록.
- 42-fiber optical pair, 84-fiber two-ply twill, 8개 parameter sweep, 3개 topology, mechanical mesh refinement, analytic beam benchmark.
- `optical_lod.py`: 공통 부피의 그룹별 projected-area density, SPD SGGX fitting, visible-normal/phase normalization과 소광 가중 reciprocity.
- 공식 CIE 1931 2° 데이터의 출처·hash·CC BY-SA 4.0 기록; 실제 파장별 radiance의 Planck-source XYZ 적분과 paired-seed uncertainty.
- 536회 실제 64×64/32-spp explicit-fiber renders, 380–780 nm 기준 sweep, 한 반사 방향의 실제 12.5 nm refinement; 별도 Lambertian rig 기준.
- `run_engine_v3.py`: mechanics/optics/verify/tests 의존 순서, 새 output directory, 기존 evidence 검산과 새 계산·render skip 구분, command/log/hash manifest.
- 원문·후속 문헌 확인을 확대한 v3 literature ledger, 독립 수학·저장 결과 리뷰, 한국어 연구 설계·architecture·release 설명.

### Fixed during review

- Rank가 부족한 angular fitting이 작은 training residual만으로 통과하던 경로: 여섯 대칭 계수의 design rank 검사.
- 다른 mechanics problem 또는 변경 height에 과거 결과를 붙일 수 있던 경로: problem/height SHA 결합, export에서 실제 KKT·energy 재계산.
- Slope 전제가 깨진 입력에 configured geometric bound를 보고하던 경로: invalid premise와 별도 observed-slope bound 구분.
- 통합 실행에서 coordinate ordering에 민감한 family-exchange solver 정밀도: energy/gradient/Hessian invariance를 검증하고 solve tolerance를 강화, 기존 assertion tolerance 유지.

### Validation and actual outcomes

- Plain optical pair의 excess energy −70.05%, warp/weft crimp 배분 변화와 multi-ply geometry clearance 확인.
- 96 train/1,200 held-out 방향에서 1 SGGX → 2 family SGGX의 projected-area 상대 RMSE가 초기 3.5727→0.2198%, 평형 3.5788→0.2984%.
- 6500 K Planck의 두 반사 조명에서 평균 Y +37.04%/−32.37%, 투과 +0.64%는 paired 4-seed 95% 구간이 0을 포함.
- 실제 25/12.5 nm refinement의 한 반사 방향 XYZ 차이 0.170–0.363%; finite-source Lambertian 기준과 renderer 차이 0.178%.
- 최종 전체 suite의 test 수·failure/error/skip·source hash는 [통합 test summary](data/final_test_summary.json), 독립 검산·수정은 [v3 review](notes/review_engine_v3.md)에 기록한다.

### Scope and compatibility

- 기존 v0.1/v0.2 scientific modules·reference results·reports를 보존한다. 새 mechanics와 optics는 기존 hierarchy/scene을 소비한다.
- Mechanics는 height-only 축소 모델이며 full DER/Weavecraft, contact/friction/flattening/garment drape가 아니다.
- Fiber material point를 운반하지 않고 재생성한다. Optical pair volume proxy +0.04424%, family length redistribution을 명시한다.
- SGGX projected-area fitting/phase 수학과 실제 fabric BSDF는 다르다. Optical fixture는 1 ply/yarn이라 독립 ply 효과를 증명하지 않는다.
- 실제 렌더는 spectral ray model이며 full 3D wave/polarization이 아니다. Planck 6500 K와 D65, MC uncertainty와 실물 accuracy를 구분한다.
- Yang 등의 SGGX textile fitting, Tang R/T, FabricGen, Weavecraft·Leaf·DER와의 overlap을 명시한다. 새 구성만으로 독창성·실물 재현·메타표면 우위를 주장하지 않는다.

## 0.2.0 — 2026-10-11

### Added

- 직사각형 binary `WeaveDraft`, 음수 padding/주기 조회, 기본 weave families, cyclic float와 unbound yarn 진단, lift-plan round trip.
- 명시적 `FiberSpec → PlySpec → YarnSpec → FabricSpec`와 부모/material ID를 보존한 polyline 결과.
- Double-reflection RMF, 부모 호길이 기준 signed twist, bounded radial migration, crossing 사이 waviness, 기존 fiber의 compact C2 loop.
- C2 crossing crimp, independent warp/weft pitch와 crimp 배분, sampling phase/segment/turn gates.
- 다른 fiber의 continuous capsule clearance와 versioned JSON/NPZ 저장.
- `MaterialSpectrum`, `OpticalScene`, geometry/material/units/source/status·hash 계약.
- Strict/local slice 검사와 기존 2D Maxwell/ray adapter; per-material/radius Mitsuba export/render.
- Polyline→B-spline smoothing, float32 coordinate/radius bound, export manifest와 curve hash 검증.
- 계층별 tangent moment와 unoccluded lateral-area statistics.
- 5개 hierarchy 구성, 실제 1/2/4 refinement, 7-fiber calibration과 98-fiber mixed-material optical 실험.
- `run_engine_v2.py`: 새 output directory, stage command/log/hash/환경/실패 기록, geometry/refinement/optics/tests.
- Runner CLI 회귀 테스트, 별도 수학·물리 리뷰 테스트, 수동 실행 CI 설정.
- 한국어 연구/설계/architecture/work-log 문서, 문헌·라이선스 audit, 인용 메타데이터.

### Fixed during review

- 음수 `batch_size`가 clearance 검사를 건너뛰고 교차 geometry를 통과시키던 오류.
- Frozen fiber ndarray의 writable flag를 다시 켤 수 있던 문제.
- Adaptive refinement에서 nominal 배수와 실제 서로 다른 mesh를 혼동할 수 있던 비교 방식.
- Polyline control을 그대로 renderer geometry로 해석할 때 생기는 변위·float32 오차의 미기록 경로.

### Validation

- 5개 geometry case의 different-fiber clearance 통과와 complete-hierarchy refinement 실행.
- 실제 mixed-material 2D wave/ray 및 3D Mitsuba integration 실행.
- 별도 reviewer가 source geometry와 optical scene의 일치, 1.7배 geometry/wavelength similarity, material order invariance, spline separation bound 재검산.
- 새 runner와 배포 기준 `validate_all.py`에서 각각 전체 **181 tests, 0 failures, 0 errors, 0 skips** 확인. [v2 Runner summary](data/engine_v2_test_reproduction/tests/test_summary.json)는 당시 실행의 소스 hash와 함께 보존한다. `data/final_test_summary.json`은 현재 버전 통합 실행 때 갱신되므로 v2의 고정 기록으로 사용하지 않는다.

### Scope retained

- 합성 물질과 유한 planar patch; measured-fabric fidelity는 아직 평가하지 않았다.
- Geometry generation은 방적·제직 mechanics 또는 contact equilibrium을 풀지 않는다.
- Exact 2D solver는 허용된 local parallel circular bundle에 한정한다. Full 3D wave cloth, ASGGX inverse fitting, spectral display color는 새 기능으로 주장하지 않는다.
- 기존 `geometry.py`와 baseline optical/camera/meta 모듈의 동작은 보존했다.

## 0.1.0-baseline — 이전 2026-10-10 작업, 2026-10-11 archive

- 단일·다중 원통 electromagnetic reference, Gaussian beam angular spectrum, ray Fresnel/Beer transport.
- 비음수 angular surrogate, finite aperture diffraction, procedural fiber cloth geometry.
- 실제 Mitsuba fiber path tracing, camera MTF/pixel/noise, 이상적 meta pupil과 측정행렬, angular photon-count 진단.
- 수치·그림·선형 배열·물리 검산·문헌·보고서를 보존.
- 로컬 archive commit: `27462377e72c8134502e5978895b11a134614f0e`, tag: `v0.1.0-baseline`.
- 교체 전 README는 [docs/baseline_v0.1.md](docs/baseline_v0.1.md)에 원문 그대로 있다.
