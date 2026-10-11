# Change log

변경 기록은 구현한 기능과 검증 범위를 기준으로 작성한다. 최종 배포 commit/tag는 [작업 로그](docs/WORK_LOG.md)에서 확인한다. 현재 저장소에 별도의 오픈소스 라이선스를 부여하지 않았다.

## 0.5.1 — 2026-10-11 UTC / 2026-10-12 KST

### Geometry-derived figures

- `visualization/structure_maps.py`: 기존 hierarchy와 v0.5 tube sweep에서 실제 float32 triangle surface를 만들고 nearest-hit geometric normal·별도 smooth normal·barycentric centerline tangent·world-Z·distance·정수 계층/material ID를 공간 정합해 기록.
- Ply envelope proxy와 explicit fiber, 전체 패치와 같은 교차점 확대를 비교. Mixed-material ply의 단일 material을 꾸며내지 않고 child provenance를 보존.
- Center-hit 물리값과 실제 supersample 표시값을 분리. 180° 주기 orientation, 물리 높이 공통 범위, straight RGBA coverage, 정수 category, 스케일바·방향 glyph의 좌표 계약을 명시.
- Canonical 3×2 basket과 별도 compact 2×2 basket의 세 figure family를 PNG/PDF/SVG로 출력. 저장 NPZ·JSON·RGBA·최소 supersample 배열과 hash manifest에서 plot-only 재구성을 제공.
- 80 μm pitch·16 yarns/48 plies/336 fibers의 compact 설계와 실제 sampling·다른 curve capsule 간격 감사. 55 μm 후보의 sampling 실패와 70 μm 후보의 capsule 분리 인증 실패도 보존. Same-curve self-contact나 역학 평형 인증으로 해석하지 않음.
- Producer 표시 함수를 재사용하지 않는 독립 coordinate/identity/RGBA/file 검산과 해석적 평면·가림 oracle. Source·입력·단위·카메라·파일·배열의 해시를 연결.
- 사용자 Fig. 5의 출처, 원문·supplement의 normal/orientation/height 의미, 현재 구현과의 차이를 기록. 연구 README·현재 상태·CITATION·시각화 수학/API·figure 보고서를 갱신.

### Validation and observed failure

- **425 tests passed, failures/errors/skips 0**, 24.814377603초. 87개 source의 실행 전후 해시가 같음. 보강 전422-test 실행은 별도 보존. [최종 전체 summary](data/validation_v5_1/final_suite/test_summary.json).
- 기존 v0.5.0 core·가변 반지름 실험·216/32/72회 radiance 자료는 변경하지 않음. 새 primary geometry ray 수를 광학 표본 수와 합산하지 않음.
- 독립 reader가 canonical hierarchy PDF의 잘림을 검출: manifest566,866 bytes에 대해433,871 bytes, EOF 없음. 원인 미확정. 거부 증거를 보존하고 동결 source의 plot-only 경로로 복원해 파일 전체를 다시 검산. [거부 기록](data/validation_v5_1/rejected_figure_serialization/rejection_summary.json).
- 후속 SVG/PDF에서도 잘림을 관측해 별도 `finalize_structure_figures.py`를 추가. 모든 그림을 BytesIO에서 완성·container 검사 후 원자 저장하고18개 accepted 파일을 최종 바이트 대조. 원래 generation provenance·24개 NPZ는 보존. 잘림 거부·hash 불일치 시 기존 destination 보호·일시 exporter의 실패 후 복구 테스트3개 추가.
- 두 사례의 **8 maps/208 arrays/24 NPZ/18 figure files** 독립 검산 통과. 최종594-ray analytic oracle, PDF6개의 실제1-page parse·raster 확인. Compact 설명문 겹침을 데이터 변경 없이 조정. [최종 파일 검사](data/validation_v5_1/figure_finalization/publication_checks.json).
- 구조맵은 실제 원단의 역추정, 논문 Fig. 5의 같은 파라미터 재현, 실물 색·촉감, complete fabric BSDF 또는 광택 수렴의 증거가 아님. [완료 범위·재현·한계](docs/RELEASE_V0_5_1.md).

## 0.5.0 — 2026-10-11 UTC / 2026-10-12 KST

### Added

- `textile_sim/variable_radius.py`: v0.4의 선분 반지름을 길이 가중 정점 단면적과 fiber별 배율로 연속화. 원래 물질좌표·부모/material ID·source hash를 유지하고 immutable profile과 nonpickle NPZ/JSON 저장·복원 제공.
- RMF 고리와 두 endcap으로 닫힌 tapered triangle mesh 생성. 원통 부피 proxy, 선형 반지름의 직선 frustum 적분, 실제 mesh signed volume을 별도로 계산. 총 frustum 보존과 선분별 부피 재분배, 원주 다각형·축방향 오차를 분리.
- `textile_sim/volume_optics.py`: 검산한 float32 정점/uint32 면을 실제 Mitsuba mesh에 전달하고 기하 법선의 dielectric 경계와 inverse-mm 순수 흡수 매질을 `volpath`로 연결. 재료/scene/buffer identity와 내부 출사 경계 검사.
- 새 node 반지름의 상한 capsule과 float32 변위를 사용하는 장면별 다른-fiber 간격 gate. 같은 fiber의 자기 교차가 검사되지 않았다는 범위를 metadata에 유지.
- `run_variable_radius_experiments.py`: 같은 pose·물질점·재료·rig에서 두 반지름 상태를 원주 16/32/64 분할, 세 조명·세 파장·네 seed로 비교. 원시 scalar 영상, 개별 render 행, pointwise/Bonferroni paired 구간과 기하 진단 저장.
- `verify_variable_radius_artifacts_v5.py`: producer driver/renderer를 import하지 않고 저장 profile·실제 buffer·scene metadata·seed 통계 재검산. 원본 mechanics pair를 제공하면 네 파일의 hash와 v0.4 material map에서 좌표·반지름·ID를 재구성.
- `run_engine_v5.py`: `experiment → verify → tests`, 쓰기 없는 dry-run, 새 출력 경로·렌더 예산·source/input/output hash·실패 기록. `--source-input`으로 원본 재구성을 명시하며 기본 원본이 없는 archive는 `unavailable_default`로 구분. 원본과 저장 산출물의 검증 범위를 혼동하지 않음.
- `run_volume_optics_validation_v5.py`의 Beer·dielectric furnace·내부 출사·단위 상사 기준 문제와 `run_volume_scale_sensitivity_v5.py`의 실제 fiber 척도 비교. 설치 Mitsuba 3.9.1 header와 고정된 공식 source의 경계·흡수·ray-offset 규약을 대조.
- [가변 반지름 수학/API](notes/variable_radius_geometry_v5.md), [광학 소스 감사](notes/variable_radius_optics_source_audit_v5.md), [원단 실험](notes/variable_radius_v5_experiment.md), [광학 oracle](notes/volume_optics_validation_v5.md), [독립 검토](notes/review_variable_radius_v5.md)와 전체 연구 설계/architecture 갱신. 염색·퇴색 보류, 강한 RGB 비교군과 메타광학의 추가 정보 가치라는 연구 방향 유지.

### Fixed during independent review

- RMF 초기 normal을 투영한 값으로 바꿔 저장한 뒤 재투영할 때 생기던 round-trip 차이: 원래 입력 seed를 그대로 보존. 실제 42개 fiber의 명시 seed 저장·재로드를 다시 검사.
- 유효한 다른 scene metadata의 혼용, metadata 수정과 일부 잘못된 config를 거부하도록 scene handle/hash 결합과 입력 검증 보강. Taper 법선의 축방향 성분과 실제 geometric normal 사용을 확인.
- 첫 216회 후 한 mesh NPZ에서 잘린 ZIP과 nested checksum 불일치를 발견해 독립 검산이 거부. 발생 원인은 확정하지 않음. 메모리에서 완성한 NPZ의 flush/fsync·atomic replacement·readback, 모든 ZIP CRC·중첩 hash의 최종 gate를 추가하고 전체 실험을 새로 실행. 거부한 자료·당시 source와 [감사 기록](data/validation_v5/serialization_rejection_216/rejection_audit.json)을 보존.
- Runner가 선택한 원래 mechanics pair를 read-only hash 범위와 verifier 명령에 함께 넣고 실제 원본 재구성 여부를 기록. 누락된 명시 경로는 실패하며, 저장 영상 검증 횟수와 새 실행 횟수를 분리. 실패 후 실제 부분 render 수를 확정할 수 없으면 `null` 유지.

### Validation and actual outcomes

- 최종 전체 **391 tests, 0 failures, 0 errors, 0 skips**, 실행 중 source 변경 0. 렌더 호출·수동 재로드·과거 test run을 test 함수 수에 합산하지 않음. [최종 test summary](data/final_test_summary.json).
- 최종 원단 비교 **216회**, **202.188323초**. 아홉 NPZ의 CRC·중첩 hash와 source/input 불변 gate 통과. 독립 검산은 원본 네 파일의 물질좌표 재구성, **252개 fiber mesh·54개 scene metadata·216개 저장 영상 기록·77개 출력 파일**을 대조. [실험 manifest](data/variable_radius_v5/experiment_manifest.json), [독립 검산](data/validation_v5/independent_review/verification_summary.json).
- 별도 광학 oracle **32회**는 사전 선언한 물리 오차 guard 통과. 별도 척도 1/10/100 비교 **72회**는 source 불변·CRC 검사 통과. 세 완료 배치의 실제 호출은 **216+32+72=320회**이며 독립 측정 320개라는 뜻이 아님. 척도 배치의 1배 기준 **24개 조건은 원단 배치와 중복**되므로 새로운 독립 seed로 합산하지 않음. [물리 oracle](data/validation_v5/volume_physics/validation_metrics.json), [척도 비교](data/validation_v5/volume_scale_sensitivity/sensitivity_metrics.json).
- 거부한 첫 216회와 최종 216회의 raw radiance는 byte까지 동일. 이를 8 seeds나 독립 표본 증가로 합치지 않음. 최종 자료는 실제 저장 mesh까지 새 무결성 gate를 통과한 배치.
- Repo 밖 작업 디렉터리에서 `experiment verify --no-render` 통합 경로가 **실제 렌더 0회**와 원본 재구성으로 통과. 별도로 선택하는 `tests`의 작은 renderer 기준 문제는 이 생략 옵션의 적용 대상이 아님. [통합 manifest](data/validation_v5/no_render_integration/run_manifest.json).
- 가변 정점 반지름 2.808323–3.235533 μm; fiber별 총 frustum 적분 상대 오차 최대 4.44e−16. 개별 선분 재분배는 −3.96381%~+3.80001%로, 총합 보존과 국소 비압축성은 다름.

### Scientific boundaries and unresolved gates

- 원주 16/32/64에서 mesh/frustum 부피 차이는 약 −2.55389%/−0.64480%/−0.16407%로 감소했지만, 32→64의 R0 radiance 점추정은 두 상태·세 파장에서 약 25.70~31.56% 감소. 작은 부피 오차가 facet 법선·광량 수렴을 보장하지 않음.
- 최고 원주 분할의 반지름 비교 9조건 모두 pointwise 95%·Bonferroni 구간에 0 포함. 현재 예산에서 반지름 효과를 검출하지 못했으며 두 모델의 물리적 동등성을 입증하지도 않음.
- Pinned source와 실제 교차 질의에서 ray 시작점 이동의 절대 길이 항을 확인. 72회 척도 실험의 전체 18개 비교 family 구간에는 0이 포함되지만, 이는 척도 불변성·동등성·수렴의 인증이 아님. 원주·축방향 sampling, 좌표 원점·offset, Monte Carlo와 모델 오차를 구분하는 gate 유지.
- 두 반지름 상태 모두 같은 새 dielectric/흡수 모델로 비교. v0.4 hair와 v0.5 mesh 사이의 shader 변경을 반지름 효과로 해석하지 않음. 세 파장 scalar 진단은 CIE 색 재현 또는 full 3D wave/polarization 검증이 아님.
- Same-fiber self-intersection, full rod/contact/sliding/twist 평형, 비원형·복굴절·실측 표면 산란, 실물 원단 재현과 역추정은 미해결. 실제 실크·코튼 등의 정확도, 추가 채널의 RGB 대비 이득, 제작한 메타표면의 시스템 이득이나 촉감 개선을 이번 결과로 주장하지 않음.

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
- 최종 전체 테스트·실험·독립 검산 수치는 [v0.4 릴리스 설명](docs/RELEASE_V0_4.md)과 [v0.4.0 태그의 test summary](https://github.com/Phill-lms/textile-appearance-research/blob/v0.4.0/data/final_test_summary.json)에 기록.
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
