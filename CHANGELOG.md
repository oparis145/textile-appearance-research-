# Change log

변경 기록은 구현한 기능과 검증 범위를 기준으로 작성한다. 최종 배포 commit/tag는 [작업 로그](docs/WORK_LOG.md)에서 확인한다. 현재 저장소에 별도의 오픈소스 라이선스를 부여하지 않았다.

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
- 새 runner와 배포 기준 `validate_all.py`에서 각각 전체 **181 tests, 0 failures, 0 errors, 0 skips** 확인. [Runner summary](data/engine_v2_test_reproduction/tests/test_summary.json), [최종 test summary](data/final_test_summary.json)는 실행별 소스 hash와 함께 보존한다.

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
