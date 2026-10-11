# 작업 로그와 버전 증거

기록 기준일: **2026-10-11 UTC**. 이 문서는 실제 수행한 작업을 기록한다. 장기 로드맵은 [연구 설계](RESEARCH_DESIGN_KO.md)에 따로 두며, 계획한 일을 완료된 이력에 섞지 않는다.

## 1. 버전 기준

| 기준 | 확인한 상태 |
| --- | --- |
| 이전 작업의 기록일 | 2026-10-10 baseline 실험 자료를 보존 |
| 로컬 baseline commit | `27462377e72c8134502e5978895b11a134614f0e` |
| 로컬 baseline tag | `v0.1.0-baseline` |
| Baseline 원본 설명 | [baseline_v0.1.md](baseline_v0.1.md): 교체 전 README를 그대로 복사 |
| 현재 개발 버전 | `0.2.0`: 계층 기하·광학 연결·재현 runner·문서 |
| 확인된 GitHub 저장소 | [Phill-lms/textile-optics-engine](https://github.com/Phill-lms/textile-optics-engine), private |
| 초기 원격 README commit | `cad54984c6aca4f5751b08e834417e40b55c052f` |

로컬의 기존 archive commit과 원격 API 업로드로 만들어진 commit은 부모 이력이 달라 SHA가 달라질 수 있다. 해당 시점의 동일 파일 집합은 tree와 artifact hash로 확인한다. 확인된 원격 source/result commit과 tag는 아래 배포 기록에 별도로 남긴다.

## 2. 날짜별 실제 작업

| 날짜 | 작업 | 증거 / 결과 |
| --- | --- | --- |
| 2026-10-10 | 기존 optical simulation 단계 | 단일/다중 cylinder wave, ray transport, Gaussian beam, aperture, fiber render, camera, 이상적 meta pupil, angular detection 자료 보존. [원본 설명](baseline_v0.1.md), [기존 report](../report/textile_optical_simulation_report_ko.pdf) |
| 2026-10-11 | 기존 결과를 baseline으로 archive | 위 로컬 commit/tag 생성. 이전 source·data·notes·report 유지 |
| 2026-10-11 | 첨부 논문 검토 | FabricGen 본문 10쪽, Tang2024 arXiv v3 본문·보충 13쪽 전체 읽기. 주요 수식 페이지 시각 확인 |
| 2026-10-11 | 관련 문헌과 공식 source 확인 | TexGen, Weavecraft, procedural yarn, ply/multi-scale appearance, fiber capture, ray–wave의 범위가 명시된 검토. [문헌 audit](../notes/literature_engine_v2.md) |
| 2026-10-11 | 첨부 자료 보존 | 제공된 PDF를 변경 없이 `references/user_provided/`에 복사; [PROVENANCE.json](../references/user_provided/PROVENANCE.json) 유지 |
| 2026-10-11 | 계층 기하 구현 | `WeaveDraft`, fiber/ply/yarn/fabric schema, local RMF, signed arclength twist, bounded migration/waviness/loop, rectangular draft, 저장·clearance |
| 2026-10-11 | 계층 예제 5개 실행 | 190/140/210/140/140 fibers. 모든 다른 fiber의 polyline clearance gate 통과. [기하 결과](../data/hierarchy_v2) |
| 2026-10-11 | 실제 refinement 실행 | 채택된 adaptive baseline에서 1/2/4배로 전체 계층 재생성. 위치·길이·tangent 통계의 감소 확인. [수치](../data/hierarchy_v2/sampling_refinement_metrics.json) |
| 2026-10-11 | OpticalScene과 adapter 구현 | per-fiber material/radius·부모 ID·단위·provenance 보존, scene/export hash, strict/local slice, spline/float32 bound |
| 2026-10-11 | 실제 광학 연결 실험 | 7-fiber 보정 yarn의 6 wave/ray 조건, 98-fiber 원단의 4 Mitsuba 영상. [metrics](../data/optical_bridge_v2/optical_bridge_metrics.json) |
| 2026-10-11 | 독립 수학·코드 리뷰 | negative-batch false clearance와 배열 재수정 문제를 발견·수정. 7개 독립 회귀 테스트 추가. [review](../notes/review_engine_v2.md) |
| 2026-10-11 | 저장된 export 독립 재검산 | 98 fibers의 ID/material/좌표 동일성 확인, 212,657 segment pair 재검사, 2 μm source gap → 1.91769 μm spline bound 재계산 |
| 2026-10-11 | Unified v2 runner 구현 | 새 output 폴더, stage 순서, 실제 명령·종료 코드·시간·hash·pending 상태, geometry/refinement/optics/tests 연결 |
| 2026-10-11 | Runner 재현 확인 | 11개 geometry/refinement/optics 명령, experiment render 생략 모드에서 33.931초; 52개 artifact hash 검증. [manifest](../data/engine_v2_reproduction/run_manifest.json) |
| 2026-10-11 | 전체 suite를 새 runner로 실행 | **181 tests, failures/errors/skips 모두 0**, 테스트 11.279초. [run별 summary](../data/engine_v2_test_reproduction/tests/test_summary.json) |
| 2026-10-11 | 배포 기준 전체 suite 재실행 | `validate_all.py`: **181 tests, failures/errors/skips 모두 0**, 9.901초. [최종 summary](../data/final_test_summary.json)에 소스 hash 포함 |
| 2026-10-11 | 수동 CI workflow 준비 | workflow YAML을 로컬에서 확인. GitHub Actions 실행은 이 기록에서 완료로 주장하지 않음 |
| 2026-10-11 | 저장소 문서·버전 메타데이터 정리 | 한국어 README, 연구 설계, architecture, work log, changelog, CITATION, ignore 규칙 |
| 2026-10-11 | 비공개 GitHub 저장소 생성·확인 | `Phill-lms/textile-optics-engine`의 private 상태와 관리/업로드 권한 확인. 소스·자료 업로드 후 최종 commit은 별도 확인 |

테스트 수와 시간은 해당 실행 시점의 기록이다. 배포 기준 전체 suite는 [data/final_test_summary.json](../data/final_test_summary.json)과 [final_tests.log](../data/final_tests.log)를 우선 확인한다. 큰 legacy 광학 실험은 일부 저장된 기준 자료를 검증하며 전체를 매번 재생성하지 않는다.

## 3. 수정과 의사결정의 이유

### Topology와 rendering geometry 분리

FabricGen의 implicit UV normal/tangent/height representation을 explicit microfiber solver와 같은 것으로 표현하지 않기로 했다. 이번 엔진은 파동·광선의 공통 geometry를 만들기 위해 개별 fiber 좌표와 부모 ID를 유지한다. LLM/diffusion 학습과 SpongeCake shader를 구현했다는 주장은 하지 않는다.

### Negative batch의 false certificate 수정

서로 교차하는 두 segment에서 `batch_size=-1`이 실제 검사를 건너뛰고 양의 간격을 반환하는 문제가 재현됐다. 실행 budget 인자를 양의 정수로 검사하고 회귀 fixture를 추가했다. 통과한 검사의 개수와 scope가 certificate의 필수 조건이 되도록 했다.

### Immutable fiber storage

NumPy owning array의 writable flag만 내리면 다시 켤 수 있었다. Frozen fiber record의 points/radii를 immutable backing storage로 변경했다. Parent dictionary와 전체 spec까지 불변이라는 확대 주장은 하지 않는다.

### 실제로 다른 mesh의 refinement

Adaptive sampler가 서로 다른 nominal 요청을 같은 최종 mesh로 올릴 수 있었다. Refinement factor를 실제 채택된 baseline sampling에 적용하도록 정리했다. 최종 5개 case의 1/2/4배 mesh는 모두 실제로 달라지고, tangent 통계도 함께 비교한다.

### Optics 전송에서 기하 오차 예산 추가

Polyline을 B-spline으로 넘기면 곡선이 변하므로 smoothing을 계산했다. Pinned renderer의 float32 입력 때문에 control과 radius 반올림도 더했다. Source polyline 간격에서 이 변위 예산을 차감해 예제의 exported geometry가 분리되는지 확인했다.

### 현재 미완료로 유지하는 연구 항목

Mechanical equilibrium, same-fiber self-contact, 비원형/복굴절 fiber, 실제 물질 상수 fitting, local→3D scattering aggregation, 실제 metasurface 성능, 실물·지각 검증은 각각의 모델·실험이 필요하다. 별도의 완료 근거 없이 현재 feature 목록에 포함하지 않는다.

## 4. 원격 배포 기록

GitHub 앱으로 업로드한 각 단계의 tree가 로컬 commit의 tree와 정확히 일치하는지 검사한 뒤 `main`을 갱신했다. 원격 변경은 기존 HEAD를 확인하는 expected-SHA 조건을 사용했다.

| 단계 | 로컬 archive commit | 확인된 원격 commit | 동일한 tree |
| --- | --- | --- | --- |
| 기존 205개 파일 보존 | `27462377e72c8134502e5978895b11a134614f0e` | `e5ec6113c21627feaec746fb5e72e78202ea0bfe` | `5ee52af67b01804d8825b468e8ed1853fa17939b` |
| 계층·광학 adapter·63개 신규 검사 | `ecc476162f43f9f8295e0a2aebcee25922db7531` | `e3424e5785eab47ca6ce909dbb23b3ed60cfbb1b` | `a3f4e399459ffe235d27d258b3fc7626129706b6` |
| 실제 실험·그림·181개 전체 검증 | `e8ce40364f0a150ed739bcd8017cb99647de4671` | `3d23fce5d3b01d487a5b0562565fdb977a318418` | `c1782e31d53073c0d05651dbea4aac697dd4e9a9` |

기준 release `v0.1.0-baseline`이 원격 `e5ec611`을 가리키는 것을 확인했다. 기존 12.8 MB 보고서는 웹 업로드 후 Git blob SHA를 검증해 원래 `report/` 위치로 보존했다. 사용자 첨부 논문 가운데 47.6 MB 파일은 GitHub 웹 파일 제한보다 커서 비공개 v0.2.0 release의 asset으로 보존하며, 정확한 파일명·바이트 수·SHA-256은 [첨부 provenance](../references/user_provided/PROVENANCE.json)에 기록한다. 기존 `PACKAGE_MANIFEST.json`은 v0.1 archive에 대한 과거 기록이며 v0.2 전체 파일 목록으로 해석하지 않는다.

문서·22쪽 PDF의 원격 commit은 `9a6c3cee7d1fbcac8bff857c418b36c79b0a0568`이며, `v0.2.0` tag가 이 commit을 가리킨다. 해당 release tree `2065a75362cafa9c88a41b8ee11f33f4d744c28c`는 로컬 배포 tree와 정확히 일치한다: Git 파일 348개, 총 162,333,705 bytes. 비공개 상태와 두 release를 확인했고, Tang 원본 PDF의 GitHub asset ID `630405946`, 47,640,125 bytes, SHA-256 digest가 로컬 원본과 일치함을 확인했다. [기계 판독 가능한 배포 검증](../data/repository_release_audit.json)을 배포 뒤 별도 provenance commit으로 기록한다. 이 기록 추가는 수치 소스·결과를 바꾸지 않는다. GitHub Actions는 수동 workflow를 제공했으며 원격 실행 성공으로 주장하지 않는다.

## 5. 이후 로그 작성 형식

새 작업은 날짜, 질문/변경 이유, source commit, 입력 config/hash, 실제 명령, 검증 결과, 수치/그림 경로, 알려진 한계를 한 묶음으로 기록한다. 실패한 실험도 삭제 대신 실패 이유와 후속 수정에 연결한다. 큰 재현 결과는 `run_manifest.json`을 링크하고, 모든 stdout을 이 문서에 복사하지 않는다.
