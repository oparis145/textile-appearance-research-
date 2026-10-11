# 작업 로그와 버전 증거

기록 기준일: **2026-10-11 UTC**. 이 문서는 실제 수행한 작업을 기록한다. 장기 로드맵은 [연구 설계](RESEARCH_DESIGN_KO.md)에 따로 두며, 계획한 일을 완료된 이력에 섞지 않는다.

## 1. 버전 기준

| 기준 | 확인한 상태 |
| --- | --- |
| 이전 작업의 기록일 | 2026-10-10 baseline 실험 자료를 보존 |
| 로컬 baseline commit | `27462377e72c8134502e5978895b11a134614f0e` |
| 로컬 baseline tag | `v0.1.0-baseline` |
| Baseline 원본 설명 | [baseline_v0.1.md](baseline_v0.1.md): 교체 전 README를 그대로 복사 |
| 현재 개발 버전 | `0.3.0`: 축소 원사 평형·계층 광학 축약·실제 분광 관측·검증 |
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

### v0.2 종료 시 미완료였던 연구 항목

v0.2 시점에는 mechanical equilibrium, same-fiber self-contact, 비원형/복굴절 fiber, 실제 물질 상수 fitting, local→3D scattering aggregation, 실제 metasurface 성능, 실물·지각 검증은 각각의 모델·실험이 필요하다. 별도의 완료 근거 없이 현재 feature 목록에 포함하지 않는다.

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

## 6. v0.3 역학-광학 연결 작업 기록 (2026-10-11)

### 질문과 범위

원단의 모습을 충분히 설명하려면 직조 순서뿐 아니라 원사의 굴곡과 섬유 방향, 재료의 분광 응답을 유지해야 한다. 이번 버전은 **유효 원사 역학이 바꾼 기하를 개별 섬유 광학 관측까지 전달하고, 계층을 축약할 때 잃는 방향 정보를 측정하는 것**을 목표로 했다. 염색·퇴색과 촉감 예측은 계속 제외했다. 실크·코튼 같은 이름을 임의의 물성 상수로 치환하지 않았다.

| 작업 | 실제 구현·확인 결과 | 근거 |
| --- | --- | --- |
| 문헌 확장 | Weavecraft, Leaf periodic yarn, DER, SGGX, SpongeCake 저자 원문 기술 절 검토; Yang 2026의 SGGX 직접 중복을 확인; 확인된 인용 관계와 미확인 후속 논문을 구분 | [문헌 ledger](../notes/literature_engine_v3.md) |
| 역학 | 고정된 평면 원사 트랙의 높이 자유도에 대해 축 인장과 small-slope 굽힘을 최소화; 해석 gradient/Hessian과 독립 KKT 검사 | [역학 계약](../notes/weave_mechanics_v3.md) |
| 간격 제약 | 교차점 높이와 slope의 Lipschitz bound를 결합; 실제 3D 원사 envelope 간격을 보수적으로 제한 | 같은 문서 §4 및 테스트 |
| 계층 연결 | 42-fiber plain optical pair와 84-fiber 2-ply twill의 초기·평형 기하 생성; ID/material/radius와 source hash 보존 | [mechanics data](../data/mechanics_v3) |
| 수치 실험 | 굽힘 강성·prestrain 각각의 sweep, plain/twill/basket, 4/8/16 mesh, beam 2차 수렴 | [실험 manifest](../data/mechanics_v3/experiment_manifest.json) |
| 광학 축약 | 개별 선분 투영 면적을 공통 부피로 평균하고 SGGX 1개/2-family/6-yarn/6-ply fitting; 96 학습·1,200 별도 방향 평가 | [광학 계약](../notes/optical_scale_v3.md) |
| 분광 관측 | 536회 실제 explicit-fiber rendering, 64×64, 32 spp, 4 seeds; CIE 1931과 Planck 3000/6500 K 적분 | [원본 metrics](../data/optical_v3/optical_scale_metrics.json) |
| 결과 재검산 | 실제 raw radiance에서 paired XYZ 통계 재계산, finite-source Lambertian 검사, 입력·source hash 및 export 간격 확인 | [독립 review](../notes/review_engine_v3.md) |
| 독립 리뷰 수정 | 각도 fitting rank 미검사, stale equilibrium 진단/문제 재사용, slope premise를 위반한 간격 bound를 수정 | review §2-4 |
| 통합 테스트 보완 | default solve의 가족 교환 좌표 차이 4.77 pm를 진단; E/gradient/Hessian 순열 검사 추가, solver 수렴 조건 강화; 좌표 assertion 허용 오차는 유지 | [실패 기록](../data/validation_v3/initial_full_suite_failure.json), [후속 검사](../data/validation_v3/family_exchange_followup.json) |
| 과학 suite | 230 tests, failures/errors/skips 모두 0; 19.932 s. Runner 통합 테스트를 추가한 배포 최종 수치는 아래 최신 summary를 사용 | [최종 summary](../data/final_test_summary.json) |

### 결과를 해석하는 경계

유효 원사 평형 이후 섬유를 새 부모 곡선 위에 재생성했다. 전체 부피 proxy +0.04424%, 경사 섬유 길이 -0.57358%, 위사 +0.66206%가 나타났다. 이는 섬유 material coordinate를 보존한 변형이 아니며, 광학 변화 전체를 접선 분포 하나의 효과로 귀속시키지 않는다.

6500 K Planck 조명에서 영상 평균 Y는 반사 방위각 0°에서 +37.04%, 90°에서 -32.37%였다. 투과 45°의 +0.64%는 현재 4-seed Monte Carlo 구간이 0을 포함하여 구분되지 않았다. 이 구간은 렌더링 반복 불확실성만 나타낸다. SGGX 1개에서 경·위사 2개로 바꾸면 초기 기하 투영량 오차가 3.5727%에서 0.2198%로 감소했지만, 이 수치는 외관 영상 오차나 실제 fabric BSDF의 정확도가 아니다.

현재 구현의 역학은 마찰·단면 압축·ply 응력 전달·3D drape를 풀지 않는다. 광학은 본 v3에서 coherent 3D scattering, 편광, fluorescence 또는 보정된 실제 원단 물성을 포함하지 않는다. 메타표면의 추가 측정 이득과 강한 다중조명 RGB 대비 우위는 아직 측정 설계와 실제 원단 실험으로 검증해야 한다.

### 최종 runner와 배포 gate

`run_engine_v3.py`는 mechanics → optics → verify → tests의 실제 명령을 연결한다. 새 출력 디렉터리만 허용하며, 생략된 upstream은 지정한 기존 입력으로 연결한다. 실행 당시 source/입력/출력 해시와 종료 코드를 보존한다. `--no-render`는 광학 실험에만 적용되고 작은 renderer unit test의 생략을 뜻하지 않는다. 실패한 부분 렌더의 정확한 횟수를 모르면 `null`을 남기도록 수정했으며, 0회로 잘못 보고하지 않는 회귀 검사를 추가했다.

과학 모듈 230개와 runner 9개를 합친 **최종 239 tests가 모두 통과**했다. `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -u validate_all.py`의 실행 시간은 19.734876초, failures/errors/skips는 모두 0이다. [최종 test summary](../data/final_test_summary.json)에 체크한 각 source의 SHA-256이 있다.

[최종 artifact audit](../data/engine_v3_final_artifact_audit/run_manifest.json)은 저장된 536회의 radiance 배열, 역학 상태, 재구성 fiber, export, CIE 통계를 현재 소스로 다시 검산했다. 이 audit의 새 광학 실험 렌더 횟수는 0이다. [앞선 unified verify+tests 실행](../data/engine_v3_verification/run_manifest.json)은 당시 238개 전체 테스트가 성공한 역사적 snapshot이다. 이후 추가한 실패-렌더 회귀 검사까지 포함한 최신 수치는 239개다. [새 역학부터 no-render로 실행한 기록](../data/validation_v3/no_render_integration/README.md)은 원본 manifest/log/summary의 부분 보존이며 geometry 산출물 전체를 옮긴 것으로 주장하지 않는다.

### v0.3 원격 구성 기록

코드 및 실험의 Git tree를 GitHub에 만든 뒤 로컬 tree와 대조했다. 아래 객체는 기존 `main` 이후의 순서로 연결하며, 최종 문서·보고서까지 완료한 뒤 한 번에 `main`에 반영한다.

| 단계 | 로컬 commit | GitHub commit | 일치 확인한 tree |
| --- | --- | --- | --- |
| 역학·광학·runner·회귀 코드 | `386ca80e0991e0644e7c811068151f8bd83ea35d` | `ef48484ceb13e0e818e5d935b8ee796f71a7cca0` | `d7c62abd7b9c03b31dcedbe8c5d2f5f56b8ac7f9` |
| 실제 실험·원본 배열·239-test 증거 | `1067ff6d49d7547d63c31ae5952b1189572872ab` | `36ed3c3a59a15295737cc93a4a10d668959bab2e` | `29977d71c7d23c509d4f066df11cff61a9066202` |

공식 CIE CSV와 metadata의 원래 CRLF를 유지하기 위해 해당 경로를 `-text`로 지정했다. 일반 소스는 LF를 사용하고 curve 텍스트의 마지막 구분 빈 줄은 데이터 형식으로 보존한다. 원본 데이터나 렌더 입력을 whitespace 정리로 수정하지 않았다. PDF 생성기의 ReportLab 버전과 외부 글꼴 identity는 [report/README.md](../report/README.md)에 기록했다.

### v0.3.0 게시 확인

2026-10-11 11:48:13 UTC에 [v0.3.0 release](https://github.com/Phill-lms/textile-optics-engine/releases/tag/v0.3.0)를 게시했다. GitHub API와 릴리스 화면에서 tag가 `6e18d28c508420e47fb55589043b34a06bb27794`를 가리키는 것을 확인했다. 해당 tree `1801814a504e1e947ef016ebda4e05baa89a2d3e`는 로컬 archive commit `2de1efc0f17ab6db5a0125bdd2dfed1e154d62b6`의 tree와 동일하다. 태그의 연구 snapshot은 Git 파일 451개, 173,907,925 bytes이며 저장소는 private이다.

문서·22쪽 보고서 단계의 원격 commit은 `1daf366f7299636dc0efd4c29710bb019eefee89`이다. 그 뒤 한국어 README에서 숫자와 강조 기호가 붙어 표시되는 문제만 수정한 commit `6e18d28`을 릴리스 대상으로 삼았다. 과학 소스는 최종 239-test summary에 기록된 SHA-256과 모두 일치했다. PDF는 1,635,817 bytes, SHA-256 `0b16f74315204d0b5f845cf903399349146987c4d3a70a5dea582926f78cd609`이다.

[기계 판독 가능한 v0.3 배포 검증](../data/repository_release_v3_audit.json)과 [릴리스 확인 화면](github_v0_3_release_verified.jpg)을 이 로그와 함께 별도 provenance commit으로 보존한다. 따라서 이후 main에는 이 게시 기록이 추가되지만 v0.3.0 tag는 검증된 연구 snapshot에 유지된다. 이 게시 확인에서 실험이나 전체 테스트를 다시 실행한 것으로 기록하지 않으며 GitHub Actions 성공을 주장하지 않는다.

## 2026-10-11 — 연구 정체성과 문서 구조 수정

사용자가 저장소 제목과 앞선 연구 논의의 반영 여부를 지적했다. 기존 연구 설계에는 화면·실물의 외관 차이와 VIS/IR·메타광학 목표가 일부 보존되어 있었지만, README 제목은 구현체 이름이었고 긴 릴리스 기록이 전체 연구 목적을 가렸다. 대표 제목을 **「직물 외관 재현을 위한 다중 규모 광학 모델링과 메타광학 계측」 / Multiscale Textile Appearance Modeling and Meta-Optical Sensing**으로 정했다.

동일한 비공개 저장소(ID 1414149528)를 `Phill-lms/textile-appearance-research`로 이름 변경하고 GitHub About을 연구 목적에 맞춰 수정했다. README는 목적·현재 검증 상태·원래 논의의 결정·연구 모듈·구현 계층·재현 순서로 재구성했다. [연구헌장](RESEARCH_CHARTER_KO.md)은 사용자의 요구, 범위 결정, 모듈별 입력·출력·검증 기준을 연결한다. 연구 설계와 CITATION의 제목·현재 URL도 일치시켰다.

대화의 M1–M9와 v0.1 PDF의 M1–M9가 서로 다른 역할에 쓰였음을 확인했다. 현재 연구 모듈은 R-M, 구현 모듈은 H/K/O/V/C/Q로 구분하고, 역할이 보존되지 않은 M3은 임의 추정하지 않았다. IR 보조 경로는 R-IR 신규 확장으로 표시했다. 고해상도 RGB 비교군, VIS 외관 검증, IR·메타광학의 추가 가치 입증, 원단별 실측 물성, 촉감의 별도 기준 측정, 염색·퇴색 보류를 명시했다.

이 변경은 과거 tag·commit·첨부 논문·보고서·배포 hash를 수정하지 않는다. 과거 버전의 이름은 당시 기록으로 유지하고, v0.3 테스트 수치의 링크는 해당 tag에 고정했다. 로컬 작업 경로도 기존 산출물 링크를 위해 유지한다. [저장소 identity 확인](../data/repository_identity_2026_10_11.json)은 이름 변경 당시의 원격 head와 private 상태를 기록한다. 이 문서 변경만으로 추가 시뮬레이션이나 실제 원단 검증을 완료했다고 표시하지 않는다.

## 2026-10-11 — v0.4 물질좌표 운반·광학 연결·독립 검증

### 연구 질문과 구현

기존 v3는 평형 원사 곡선의 현재 호길이에서 fiber를 재생성했다. 같은 fiber ID가 있어도 같은 물질점의 이동은 아니었다. 이번 작업은 reference fiber·ply·yarn 좌표와 부모 대응을 고정하고, 명시적 director와 frame을 통해 동일한 지점을 운반한다. 이 과정에서 불필요한 재생성 차이를 구분하고 국소적인 길이·반지름·부피 변화와 광학 입력을 추적할 수 있게 했다.

`material_transport.py`는 yarn→ply→fiber의 full 3-component offset map, RMF/SO(3) 보간, immutable reference/state와 semantic hash를 구현한다. Reference는 저장한 초기 형상이며 stress-free 물질 상태가 아니다. `constant_reference`는 원래 radius를 유지해 현재 광학 adapter로 전달한다. `incompressible_segments`는 선분마다 `r_e=r_0/sqrt(lambda_e)`로 원기둥 부피 proxy를 보존하지만, 가변 radius adapter가 없는 현재 renderer로의 export는 거부한다.

수학·API는 [물질좌표 설계](../notes/material_transport_v4.md), 전체 실험은 [실험 설명](../notes/material_transport_v4_experiment.md), 발견한 실패와 수정 이유는 [독립 리뷰](../notes/review_material_transport_v4.md)에 있다. 이번 구현은 물질좌표의 대응을 선언한 운동학이며 full fiber stress·material twist·contact/sliding·3D 질량 보존을 풀지 않는다.

### 실제 발견하고 고친 결함

- 새 ply normal을 각 pose의 yarn normal에서 독립 투영하면 gauge 선택에 따라 회전이 섞였다. 해석 반례의 인위적 차이는 8.6993385°였다. Reference ply director를 parent 상대 회전으로 운반한 후 최소 tangent alignment를 적용했다.
- Material reference hash에서 부모 대응 일부가 빠져 있었고, public state에 다른 reference/radius mode 또는 길이가 같은 다른 pose를 섞을 수 있었다. Parent maps를 digest에 포함하고 constructor에서 실제 map·ID·모드의 일치를 검사했다.
- Driver 그래프의 seed 수 하드코딩, 고정 strain histogram 범위, 상대비율 CI로 읽힐 수 있는 표기를 수정했다. 현재 구간은 절대 radiance 차이의 paired t 구간이며, 관측 baseline으로 나눈 그림은 모집단 비율의 CI가 아니다.
- Runner의 verify-only에서도 producer의 source SHA를 현재 코드와 대조하도록 보완했다. 저장 원시 파일과 기록을 검산하며, 과거 외부 입력의 절대 경로를 재탐색하지는 않는다.

### 실행 결과

| 항목 | 실제 결과 | 해석 |
| --- | --- | --- |
| 물질점 추적 | 42 fibers, 8,106 vertices, 8,064 segments | 원래 labels·부모·ID 유지, reference에서 같은 점 평가 |
| 길이 변화 | 전체 +0.0442244%, 경사 −0.5733227%, 위사 +0.6617715% | 서로 반대인 변화가 전체 합계에서 상쇄 |
| 국소 strain | −14.032~+14.120%, reference-length 가중 RMS 1.7282% | 실제 원단의 탄성 strain이 아닌 prescribed map 진단 |
| 선분 부피 proxy | 일정 radius 전체 +0.0442244%; 보존 모드 최대 상대 잔차 6.66e−16 | 굽은 전체 섬유의 실제 체적·질량 보존과 구분 |
| 재생성 대비 위치 | RMS 0.077344 μm, 최대 0.208708 μm | 같은 parent parameter index에서의 기하 비교 |
| 새로운 간격 검산 | Tracked polyline 2.945386 μm, spline/float32 차감 후 2.597543 μm 하한 | 다른 fiber 사이만 인증; self-contact·접촉력 제외 |
| 최종 광학 실험 | 108회, 64×64·32 spp·4 seeds, 450/550/650 nm, R0/R90/T45 | 세 상태 공통 rig와 합성 스펙트럼의 단색 진단 |
| 재생성 대비 광학 차이 | 9조건 중 8개의 pointwise 95% 구간이 0 포함 | 실물 외관 정확도 개선의 근거로 해석하지 않음 |

최종 driver는 **2026-10-11 13:36:24.185987–13:36:43.867250 UTC**, 총 **19.681288638초**에 완료했다. [최종 manifest](../data/material_transport_v4/experiment_manifest.json)의 source/input은 시작·종료 시 동일하다. [최종 radiance](../data/material_transport_v4/optics/spectral_radiance.npz)는 SHA-256 `7ad3703951ca475ac733a33cbf3354f2437cc589b88bbb7b605dee5df63269ea`다.

이전 108회 pilot은 표시·일반 입력 범위 리뷰 후 최종 108회와 분리해 보존했다. 두 run의 raw radiance는 **byte까지 동일**하므로 서로 독립적인 8개 seed나 216개 고유 측정으로 합치지 않는다. [Pilot checkpoint](../data/validation_v4/pilot_checkpoint/checkpoint.json)는 최종과 동일한 29개 파일을 content hash로 공유하고, 달라진 3개 파일·원래 manifest·원래 driver source를 보존한다. 원래 source는 당시 기록된 SHA와 정확히 일치한다.

### 전체 테스트와 통합 경로

`OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -u validate_all.py`를 최종 source에서 실행했다. **297 tests, failures/errors/skips 모두 0**, 실행 시간 **19.256124534초**다. [v0.4.0 태그의 전체 summary](https://github.com/Phill-lms/textile-appearance-research/blob/v0.4.0/data/final_test_summary.json), [v0.4.0 태그의 전체 log](https://github.com/Phill-lms/textile-appearance-research/blob/v0.4.0/data/final_tests.log)에 검사 대상 source별 SHA가 있다. 새 58개 검사는 구현 17개, 독립 수학 18개, runner 16개, 산출물 검산 7개다. 기존 239개와 새 코드를 함께 실행한 결과이며 과거 v3 summary를 재사용하지 않았다.

산출물 검산의 손상 테스트 5개는 checksum과 producer ledger까지 다시 계산한 후 허위 strain, determinant −1 frame, NaN radiance, 허위 paired mean, 누락된 원래 label을 거부했다. 두 정상 검사는 rendered/skipped 모드를 다룬다. 이런 검사는 실제 물성·실물 재현의 검증과 별개다.

[최종 runner artifact audit](../data/validation_v4/final_artifact_audit/run_manifest.json)는 저장된 108회 결과의 raw arrays·6개 paired comparisons·두 radius modes·세 geometry/scene/curve·투영량·새 간격을 재검산해 통과했다. 새 실험 렌더는 0회, 검산한 저장 렌더는 108회이며 source/input 변화가 없다. [독립 reviewer의 결과 사본](../data/validation_v4/independent_review/verification_summary.json)도 원본 bytes 그대로 보존했다.

[별도 no-render 통합 실행](../data/validation_v4/no_render_integration/run_manifest.json)은 저장소 밖 cwd에서 새 experiment→verify를 실행했다. 10.877307962초에 통과했고 새/저장 렌더 모두 0회인 skipped 모드다. 34개 실제 출력 파일을 모두 보존했으며 source 62개와 입력 7개의 시작·종료 hash 변화가 없다. 이 결과를 108회 재렌더 또는 전체 tests를 다시 실행한 횟수로 세지 않는다.

### Git 이력 구성

| 단계 | 로컬 commit | GitHub commit | 일치 확인한 tree |
| --- | --- | --- | --- |
| 연구 제목·README·연구헌장 | `2ea17f91ec7228a887c98235013ece1f9f289a9e` | `6a2fdc08a5066eb65748df62c3507016843e77c0` | `b246a3ee355b5e76eb1bf1f07fc5196fbd16d899` |
| 물질좌표·runner·독립 검산 코드 | `2a2b7189044f401bbf39510c63b0f086ec5e8821` | `955bddc8fdb3d85cb85118d33408056cb29f32a1` | `939d8471a595644915d87b82ac9711effc83602a` |
| 최종 실험·297 tests·검산·pilot 기록 | `8d819a0a29c543e3237c3a94eeddafcd737a4cb1` | `ae62d9afe19eba52d085dafc8d20306061eb0964` | `b99d0b80f89a86031d701a21c7ba004f5f7512a6` |

문서·실험을 완성한 tree를 확인한 뒤 main에 반영한다. 실제 v0.4.0 tag·release의 commit과 private 상태는 게시 후 별도 확인 기록으로 추가한다. 저장소 [연구 제목 반영 화면](github_research_identity_v4.jpg)도 함께 보존한다. 과거 태그와 보고서는 해당 버전의 원래 상태로 유지한다.

## 2026-10-11 — v0.4.0 게시 완료와 최종 provenance 확인

**2026-10-11 13:53:43 UTC**, [v0.4.0 릴리스](https://github.com/Phill-lms/textile-appearance-research/releases/tag/v0.4.0)를 게시했다. GitHub API에서 repository ID `1414149528`, 현재 이름 `Phill-lms/textile-appearance-research`, **private=true**, release ID `409698473`, draft=false, prerelease=false를 확인했다. 브라우저에서는 연구 제목·연구 목적·297개 테스트·108회 렌더와 Latest 표지를 확인했다. 저장소 이름과 About, README는 전체 연구 방향에 맞춰 수정되어 있다.

| 확인 대상 | 실제 값 |
| --- | --- |
| Release tag | `v0.4.0` |
| Tag가 가리키는 GitHub commit | `5060feb4c0e3f7789e231b44d93c2ac5154e5208` |
| 내용이 같은 로컬 최종 commit | `7ab26bf96ae080dddb8d13100b9b4507886e1c68` |
| 원격·로컬의 동일한 Git tree | `73148efc61aaf60f2290ef5057e5af25f598e983` |
| 이 snapshot의 추적 파일 | 547 blobs, 총 192,406,367 bytes |
| 게시 시 재확인한 코드 | 전체 테스트 source 41개·실험 producer source 19개, hash 불일치 0개 |

이는 앞 표의 연구 정체성→코드→실험/검증 commit에 최종 README·연구 설계·수학·실험 보고·리뷰·작업 로그를 추가한 snapshot이다. Git 데이터 API로 만든 commit은 로컬 commit과 메타데이터가 달라 SHA가 다르지만, 각 단계의 tree hash를 대조해 경로와 파일 bytes의 일치를 확인했다. Main 갱신은 예상한 이전 head를 조건으로 수행했다.

[기계 판독 가능한 게시 확인](../data/repository_release_v4_audit.json)에는 API에서 받은 릴리스 설명과 tag/commit/tree, private 상태, 결과·source hash 검사를 보존했다. [게시된 릴리스 화면](github_v0_4_release_verified.jpg)도 함께 남긴다. 이 후속 provenance commit은 main에 추가하며 **v0.4.0 tag는 위 검증된 snapshot에 유지한다.**

게시 확인 단계에서는 광학 실험이나 전체 테스트를 다시 실행하지 않았다. 최종 실행의 297개 테스트·108회 렌더를 그대로 확인한 것이며, GitHub Actions 성공이나 실물 재현 성능을 인증한 것으로 기록하지 않는다. Pilot의 같은 네 seed를 추가 독립 표본으로 합치지 않는다. 현재 완료한 연구 증가분은 물질좌표에 따른 동일 fiber 상태 추적, 국소 변형 진단과 기존 광학 경로의 검증 가능한 연결이다.

## 2026-10-11 UTC / 2026-10-12 KST — v0.5 가변 반지름·닫힌 표면 광학·독립 검산

### 연구 질문과 사전 비교 설계

V0.4는 동일한 fiber 물질점을 운반하고 선분 신장에 따른 반지름을 계산했지만, 기존 광학 adapter는 일정 반지름만 허용했다. 이번 작업의 질문은 **같은 물질점·중심선·재료·관측계에서 반지름 상태를 바꾼 효과를 표면 분할과 renderer의 수치 오차에서 구분할 수 있는가**였다. 실제 원단의 시각적 재질감 재현이라는 전체 목표를 유지하고, 실측 inverse fitting·RGB 대비 추가 정보·메타표면 제작·지각 평가는 별도의 후속 gate로 남겼다. 염색·퇴색은 계속 보류했다.

원단 실험은 처음부터 두 반지름 상태, R0/R90/T45 조명, 16/32/64 원주 분할, 450/550/650 nm, 네 seed로 정했다. 기본 예산은 **2×3×3×3×4=216회**, 각 영상은 64×64·64 spp다. 최고 분할의 반지름 비교 9조건과 인접 분할 비교 36조건을 별도 family로 정해 pointwise 및 Bonferroni 구간을 계산했다. 픽셀·파장·gray RGB 세 채널을 독립 반복으로 세지 않았다. [실험 설계·seed·광원·통계 계약](../notes/variable_radius_v5_experiment.md#5-실험-구성과-통계).

### 구현과 수학·소스 검토의 결정

| 구현 | 실제로 추가한 기능과 계약 |
| --- | --- |
| `variable_radius.py` | 선분별 radius를 길이 가중 node area로 연속화하고 fiber별 배율을 적용. 원래 두 물질좌표·부모·fiber/material ID·source state를 보존한 immutable profile |
| 닫힌 tapered tube | RMF 고리·옆면 삼각형·두 endcap, 원래 normal seed, 실제 법선·표면적·signed volume. 저장한 source로부터 nonpickle NPZ/JSON 재구성 |
| `volume_optics.py` | float32/uint32 buffer의 실제 기하를 검사하고 `mi.Mesh`에 전달. Geometric face normal, real dielectric 경계, inverse-mm 순수 흡수, `volpath`, scene handle와 metadata hash 결합 |
| 원단 producer | 두 상태의 중심선·material labels 동일성, 공통 rig/bounds, 원주 분할별 mesh·실제 렌더·개별 record·raw scalar 저장 |
| 독립 verifier | producer driver/renderer 없이 profile·buffer·scene·seed 통계 재계산. 명시한 원본 mechanics 네 파일에서 핵심 v4 map을 재적용해 좌표·반지름·ID 대조 |
| 통합 runner | `experiment → verify → tests`, cold dry-run, 새 출력·렌더 예산·source/input 불변, 원본 `--source-input`, 독립 worker의 전체 test discovery |

반지름 연속화에서는 내부 node의 \(\widetilde r_i^2\)를 인접 선분 \(r_e^2\)의 길이 가중 평균으로 정하고, 각 fiber에서 전역 배율을 선택했다. **원통 proxy \(\sum_e\pi r_e^2\ell_e\), 직선 frustum 적분 \(\sum_e\pi\ell_e(r_i^2+r_ir_{i+1}+r_{i+1}^2)/3\), 실제 닫힌 mesh signed volume**은 구분했다. 전역 배율은 앞의 두 총합을 맞추지만 개별 물질 선분의 부피를 재분배한다. 실제 mesh를 다시 확대하여 polygon·굽힘·축방향 오차를 숨기지 않았다. [기하 수학/API](../notes/variable_radius_geometry_v5.md), [독립 기하 검토](../notes/review_variable_radius_v5.md).

광학 경로를 선택하기 전에 Mitsuba **3.9.1 / `llvm_ad_rgb`**, 공식 tag의 commit `478e193a183c21723f4a8251afc3ad29a8da4c5e`를 확인했다. `hair.cpp`, `bsplinecurve.cpp`, `dielectric.cpp`, `homogeneous.cpp`의 byte/blob과 실제 runtime 교차를 대조했다. Hair의 흡수는 반지름으로 정규화된 국소 경로이므로 \(\mu_a r\) mapping을 요구하고, curve는 내부 출사 교차를 제거한다. 이 때문에 가변 curve에 dielectric/medium만 붙이는 경로 대신 **닫힌 mesh와 실제 내부 광로**를 선택했다. 새 매질에는 \(\mu_a=4\pi\kappa/\lambda_0\,[\mathrm{mm}^{-1}]\), \(\sigma_t=\mu_a\), albedo 0을 전달한다. 실수 Fresnel 근사의 \(\kappa/n\le0.01\) gate를 명시했다. 두 반지름 상태 모두 같은 새 광학 모델을 사용하며 v4 hair와의 모델 차이를 반지름 효과로 해석하지 않았다. [소스 감사와 실제 교차 probe](../notes/variable_radius_optics_source_audit_v5.md), [보존한 probe/checkpoint](../data/validation_v5/backend_source_audit/checkpoint.json).

### 독립 리뷰에서 발견한 결함과 수정

| 발견한 문제 | 실제 수정과 확인 |
| --- | --- |
| 초기 RMF normal의 재투영 오차 | 이미 투영한 첫 normal을 seed로 바꿔 저장하면 재로드 시 ulp 차이가 발생. 명시 seed의 실제 42개 fiber 중 39개 실패를 재현한 뒤 원래 입력 seed를 보존하도록 수정; 수정 후 42개 모두 복원 |
| Scene와 metadata 혼용 | 다른 scene의 유효 metadata 또는 변경 metadata를 사용할 수 있던 경로를 handle/hash 결합과 render 전 재해시로 거부 |
| `max_depth` sentinel 입력 | 비정수 `-1.0`이 정수 sentinel을 우회하지 않도록 엄격한 정수 검증. 일반 유한 값·config·bounds·material 입력 거부 검사 유지 |
| 실제 geometric normal 확인 | Mitsuba가 disabled 상태에도 길이 0의 `vertex_normals` key를 노출함을 확인. Key 부재 가정 대신 길이 0·`has_vertex_normals()==False`·실제 교차 normal을 검사 |
| 완성되지 않은 ZIP과 중첩 hash | 실제 저장 mesh NPZ에서 central directory/EOF가 없는 파일을 관찰. Outer ledger만으로 통과할 수 있던 경로를 차단하고 원자 저장·readback·전체 CRC/nested hash gate 추가 |

직선 원기둥·원뿔대의 해석 부피, cap/옆면 winding, 독립 ray–triangle 입출사, taper 법선의 축방향 성분, 강체/단위 변환, 원호의 축방향 수렴을 별도 검사했다. Same-fiber self-intersection은 이 테스트의 통과 범위에 포함하지 않았다. 자세한 반례와 회귀 검사는 [기하 review](../notes/review_variable_radius_v5.md) 및 [광학 oracle review](../notes/volume_optics_validation_v5.md)에 있다.

### 첫 216회 거부와 전체 재실행

첫 no-render preflight와 첫 216회 후 저장 무결성을 검사하는 과정에서 잘린 NPZ를 관찰했다. 첫 216회의 `radial_032/incompressible_segments/renderer_buffers.npz`는 로컬 ZIP header를 갖지만 central directory 끝 표지가 없었다. Mesh manifest에 앞서 기록한 hash는 실제 바이트와 달랐고, 마지막 outer ledger는 불완전한 파일의 hash와 일치했다. 따라서 producer가 `passed`를 남겼어도 독립 verifier는 이를 거부했다.

**발생 원인은 확정하지 않았다.** 파일시스템·NumPy·특정 실행 단계나 의도적인 변경으로 귀속할 증거는 없다. 손상 테스트는 별도 임시 경로를 사용했다. 거부한 파일·실험 기록·당시 source의 일부와 hash를 [serialization rejection 기록](../data/validation_v5/serialization_rejection_216/rejection_audit.json)에 보존했다. 이 묶음에는 첫 실행이 참조하던 모든 scene 파일이 들어 있지 않으므로 **첫 216회의 완전한 재실행 snapshot이나 self-contained optical replay package가 아니다**. 보존 목적은 실제 거부 근거와 수정 전 상태의 추적이다.

NPZ를 메모리에서 완성한 뒤 임시 파일에 write·flush·fsync하고 원자적으로 교체하며, 저장 직후 readback과 마지막 전체 ZIP CRC·중첩 hash를 확인하도록 보완했다. 기존 실패 파일을 고쳐 통과로 표시하지 않고 수정한 source에서 216회 전체를 다시 실행했다.

최종 원단 driver는 **2026-10-11 15:53:29.178158–15:56:51.366451 UTC**, **202.188323358998초**에 완료했다. 아홉 NPZ의 CRC와 nested checksum, source/input 불변 gate를 통과했다. 실행 상태와 hash ledger는 [최종 manifest](../data/variable_radius_v5/experiment_manifest.json)에 있다. [최종 raw radiance](../data/variable_radius_v5/optics/spectral_radiance.npz)의 SHA-256은 `7e677abb8d777bab68044033de22d114a279be11b79cc239af8afe18cf4f1728`이다.

거부한 첫 배치와 최종 배치의 raw radiance는 **byte까지 동일**했다. 최종 배치는 실제 저장 mesh까지 검산을 통과한 결과이며, 두 배치를 독립 8 seeds나 추가 고유 측정으로 합산하지 않는다. 첫 216회의 release용 accepted count는 0으로 남겼다.

### 완료된 테스트·독립 검산·추가 실험

| 실행 | 실제 완료 범위 | 시간과 근거 |
| --- | --- | --- |
| 전체 suite | **391 tests, failures/errors/skips 0, 실행 중 source 변경 0** | **30.231309687995235초**; [전체 summary](../data/final_test_summary.json), [격리 worker summary](../data/validation_v5/final_artifact_and_tests/tests/test_summary.json) |
| 원본을 포함한 독립 검산 | 원본 네 파일에서 두 material state 재구성, 252개 fiber mesh·54개 scene metadata·216개 영상 기록·77개 출력 파일 | [독립 verifier summary](../data/validation_v5/independent_review/verification_summary.json), [runner의 검산·tests 기록](../data/validation_v5/final_artifact_and_tests/run_manifest.json) |
| 외부 cwd의 no-render 통합 | 새 experiment→verify, 원본 재구성, 새/저장 렌더 모두 **0회** | **39.99984886699531초**; [통합 manifest](../data/validation_v5/no_render_integration/run_manifest.json) |
| 물리 oracle | 8조건×4 seeds = **32회**, 16×16·2,048 spp·550 nm, 사전 오차 guard 모두 통과 | **9.465649273초**; [manifest](../data/validation_v5/volume_physics/experiment_manifest.json), [metrics](../data/validation_v5/volume_physics/validation_metrics.json) |
| 실제 fiber 척도 민감도 | 척도 1/10/100×두 상태×세 조명×네 seed = **72회**, 64각형·64×64·64 spp·550 nm | **196.183671359초**, source 불변·CRC 통과; [manifest](../data/validation_v5/volume_scale_sensitivity/experiment_manifest.json), [metrics](../data/validation_v5/volume_scale_sensitivity/sensitivity_metrics.json) |

전체 suite는 `validate_all.py`와 같은 unittest discovery를 격리 worker에서 실행했다. 391개는 테스트 함수 실행 수이며 수동 42-fiber 재로드, 광선 교차 질의, renderer 호출을 추가하지 않았다. `--no-render`는 experiment의 렌더를 생략하지만 따로 선택한 tests의 작은 광학 기준 문제까지 생략하는 옵션은 아니다.

독립 verifier는 원본 pair의 네 파일에서 핵심 v4 material map을 다시 적용한다. 따라서 producer driver와 분리된 검산이지만 완전히 독립적인 두 번째 material-transport solver는 아니다. 저장 scalar 영상에서 통계·seed/index·hash를 재계산한 것이며 기록된 실행 자체를 외부에서 인증한 것으로 표현하지 않는다. 현재 producer source와의 hash 비교는 runner가 별도로 수행했다. `--source-input`을 명시한 경로가 없으면 실패하고, 기본 원본이 없는 custom archive는 내부 산출물 검증만 수행했음을 표시한다.

세 완료 실험의 호출은 **216+32+72=320회**다. 이는 고유한 독립 측정 320개가 아니다. 특히 척도 1배의 **24개 기준 조건은 앞선 216회와 중복**되므로 독립 seed 증가로 합산하지 않는다. 실패한 첫 216회와 개발 pilot도 최종 통계에 추가하지 않았다.

### 정량 결과와 해석의 한계

| 결과 | 실제 값 | 판정 |
| --- | --- | --- |
| 동일 물질점의 반지름 비교 | 42 fibers·8,106 vertices·8,064 segments, 두 상태의 중심선·labels 동일 | 반지름 외의 source 대응을 통제 |
| 연속 node radius | 2.808323–3.235533 μm | 합성 reference와 선언한 반지름 법칙의 재구성 |
| Fiber별 총 frustum 오차 | 최대 상대 4.44e−16 | 원통 proxy와 총합 일치; 실제 질량 보존 증명 아님 |
| 선분별 재분배 | −3.96381%~+3.80001%, 절댓값 99백분위 1.74383% | 국소 비압축성은 보존하지 않음 |
| 다른 fiber의 buffer 간격 하한 | 64각형에서 일정/가변 각각 **2.945345/2.602843 μm** | 새 node 상한 capsule에서 float32 최대 변위 두 배를 차감한 해당 장면의 보수적 하한 |
| 실제 mesh/frustum 부피 차이 | 16/32/64에서 약 **−2.55389%/−0.64480%/−0.16407%** | 원주 다각형 이득과 남은 굽힘/축방향 오차를 구분 |
| 반지름의 radiance 차이 | 최고 분할의 9조건 모두 pointwise·Bonferroni 구간에 0 포함 | 현재 예산에서 효과 미검출; 물리적 동등성 판정 아님 |
| 원주 32→64의 R0 radiance | 두 상태·세 파장의 점추정 **약 25.70~31.56% 감소** | 부피 수렴만으로 facet 법선·광량 수렴을 주장할 수 없음 |

장면별 간격은 원래 chord를 각 fiber의 최대 새 node radius로 감싼 capsule이 옆면·cap triangle을 포함한다는 관계를 사용했다. 기하 buffer에 대해 계산한 이 하한은 같은 fiber의 비인접 부분 간 자기 관통, 실제 contact force·압착·미끄럼, 모든 새 원단의 비접촉을 인증하지 않는다. [기하 metrics](../data/variable_radius_v5/geometry_metrics.json), [광학 metrics](../data/variable_radius_v5/optics/optical_metrics.json).

32회 단순 oracle에서는 Beer의 다섯 optical depth, 흡수 없는 dielectric furnace, 8배 길이 상사, taper를 검사했다. 모든 사전 물리 guard는 통과했지만 8배−1배 paired radiance는 **−2.19400390e−5**, 95% 구간 **[−3.13756757e−5, −1.25044023e−5]**로 0을 제외했다. 설치 header와 실제 `spawn_ray`/exit 교차를 조사해 \(\epsilon_{\rm ray}(1+\|p\|_\infty)n\)의 절대 항과 내부 광로 단축을 확인했다. 기본 offset 척도는 mm 좌표에서 약 0.0894 μm다. 이 근거는 단순 cap geometry에 한정하며 원단 오차 전체의 원인을 확정하지 않는다. [물리 oracle·pinned source](../notes/volume_optics_validation_v5.md), [실제 교차 감사](../data/validation_v5/ray_offset_audit/ray_offset_audit.json).

이를 계기로 시행한 별도 72회 척도 비교는 모든 길이·광원·camera를 a배, 흡수를 1/a배 한 수치 proxy를 사용했다. 원래 물리적 mm 기하·재료는 별도 입력으로 남겼다. 10→100의 상대 radiance 점추정은 일정 반지름 R0/R90/T45에서 **+0.042%/+0.934%/−4.242%**, 가변 반지름에서 **−0.590%/+3.303%/+1.654%**였다. 이 여섯 pointwise 구간과 전체 척도 쌍 18조건의 Bonferroni 구간은 모두 0을 포함했다. **미검출은 동등성·불변성·수렴의 증명이 아니며**, 원점·offset·표본 예산의 오차 gate가 남는다. 기하광학의 상사 진단을 full-wave 규모 불변성으로 해석하지 않는다.

이번 단계의 완료는 가변 반지름에서 추적 가능한 닫힌 광학 경계까지의 연결과 그 오차 분석이다. 반지름 역추정, 실물 재질별 정확도, RGB 대비 추가 채널의 정보 이득, 메타표면의 시스템 성능, 촉감 개선은 입증하지 않았다. 작은 물리적 신호보다 원주/축방향·법선·ray-offset·Monte Carlo 오차가 충분히 작아지는지를 다음 판단 기준으로 정리했다. [연구 설계](RESEARCH_DESIGN_KO.md), [아키텍처](ARCHITECTURE.md).

### Git 이력과 현재 게시 확인 범위

| 단계 | 로컬 commit | 확인한 GitHub commit | Git tree |
| --- | --- | --- | --- |
| v0.5 기하·광학·runner·검산 코드 | `802403c568a9f2a63b3167b7c1963dd0b2ca801e` | `b51131d17fd3e9ae59d7ab2669c8b3dd20dd50ae` | `0680e39a8fa675a94031d154e7f6d0a4cb3b9db2` |
| 최종 원단·oracle·척도·391 tests·검산 자료 | `c2df0609a30d6e473971299b29ec3d4770fd1847` | `af2ce4d209b83b818186783719451b692408619e` | `abf6e1906589491d5f4319941784fd683d200791` |

코드와 자료 단계 모두 로컬·원격 commit의 metadata가 달라도 동일한 tree를 확인했다. 이 시점에는 두 원격 commit 객체의 내용을 확인했으며, main은 최종 문서와 함께 갱신하기 전의 v0.4 상태다. 이 표는 최종 문서 commit·v0.5 tag·release 게시를 완료했다고 기록하지 않는다. 자료·문서를 포함한 최종 tree와 게시 상태는 실제 확인 후 별도 게시 감사 절에 추가한다. 과거 v0.4.0 tag와 원래 실험 결과는 유지한다.

### v0.5 최종 게시 확인 — 2026-10-12 01:23 KST

최종 문서까지 포함한 로컬 commit `cc73ceefeb4b09d4bdb4b42b60ff977aab237655`와 원격 commit `7c72530b756be59326f85c1dc40254abe5767922`의 tree는 **`8fae16181504f1ebfd9e85dfb15bdaf174706849`로 동일**했다. 기존 main head를 조건으로 한 fast-forward 갱신 후 GitHub branch API에서 commit·tree를 확인했다. 저장소 ID **1414149528**, 이름 **Phill-lms/textile-appearance-research**, **private=true**와 연구 설명도 재확인했다.

**[v0.5.0 릴리스](https://github.com/Phill-lms/textile-appearance-research/releases/tag/v0.5.0)는 2026-10-11 16:23:03 UTC / 2026-10-12 01:23:03 KST에 게시됐다.** Release ID는 `409780890`이며 draft가 아니다. `v0.5.0` tag는 위 원격 commit을 가리킨다. 브라우저에서 연구 제목, tag·commit, 391개 테스트와 216/32/72회 표가 표시된 것을 확인하고 [게시 화면](github_v0_5_release_verified.jpg)을 보존했다. [게시 감사 JSON](../data/repository_release_v5_audit.json)에 확인 범위와 해시를 기록했다.

문서의 로컬 링크 362개와 코드 fence를 검사했고 누락이 없었다. 마지막 검증의 75개 source 파일은 최종 391-test summary와 해시가 같았다. 첫 게시 기록 이후에는 감사 증거와 사용자가 추가 요청한 구조맵·figure 작업을 별도 commit으로 이어간다. **v0.5.0의 과학 코드·수치 자료 tag는 고정**하며 새로운 그림을 이전 실험 결과에 소급해 포함하지 않는다.

## v0.5.1 — 실제 구조맵·논문용 figure 요청의 구현과 마무리

**일자: 2026-10-12 KST / 2026-10-11 UTC.** 사용자가 하던 작업을 완료하고 첨부한 논문 figure처럼 데이터를 가공·render해 달라고 요청했다. 첨부 경로에 대한 읽기 오류 메시지가 있었지만 실제 작업공간의 `upload/image.png`를 확인할 수 있었고, 이미지를 직접 열어 normal·orientation·height 3-panel을 확인했다. 이 자료는 FabricGen Fig. 5였다. 원본을 변경 없이 비공개 저장소의 reference로 보존하고 출처·SHA-256을 기록했다. 별도의 생성형 이미지로 수치 결과를 대신하지 않았다.

### 연구 범위와 구현 결정

원래 연구 목적은 **제품 사진에서 예상한 원단 외관과 실제 시편을 보는 경험 사이의 차이**를 줄이는 것이다. 이번 figure 단계는 그 연구의 순방향 기하와 광학을 검토하는 연결부로 두었다. Normal·orientation·height를 보기 좋게 출력하는 것을 실제 실크·코튼·큐프라·린넨의 외관 복원이나 메타표면의 우위로 확대하지 않았다. 염색·퇴색 보류, 촉감의 별도 기준 측정, 강한 RGB 비교군, 미관측 조명 검증이라는 연구 방향을 유지했다.

FabricGen 원문 §3·§5.1, Fig. 5 및 공식 supplementary를 참고했다. 해당 논문은 UV 기반의 해석적 curved-helix 모델을 제공한다. 현재 엔진의 결과는 **이미 구축한 명시적 fiber/ply 3D 표면**에서 실제 nearest-hit를 구하는 다른 표현이다. 특히 논문의 twist-rotated fiber orientation과 현재 ply centerline tangent를 같은 정의라고 표시하지 않았다. 공식 프로젝트의 dataset·supplement 링크와 웹사이트 템플릿 코드를 방법 구현 코드로 혼동하지 않았다.

| 구현 결정 | 이유와 실제 계약 |
| --- | --- |
| 두 표면을 같은 hierarchy에서 생성 | Ply proxy는 표현 외피, explicit fiber는 개별 섬유·공극. 두 표현이 생략하는 정보를 비교 |
| 같은 카메라·crop·nearest hit 사용 | Normal·height·ID가 서로 다른 표면 위치에서 오는 불일치를 방지 |
| 실제 geometric normal 보존 | Smooth display normal과 분리해 삼각형 표면의 분할 오차를 숨기지 않음 |
| Directed 3D centerline tangent 원본 | 화면에서는 XY 180° 주기 축으로 표시; surface BSDF tangent-plane projection은 별도 |
| World-Z와 ray distance 분리 | 높이 원점을 고정하고 카메라 깊이를 물리 높이로 혼동하지 않음 |
| Center 물리 필드와 supersample 표시 분리 | 경계의 coverage를 개선하면서 물리벡터·높이·정수 category를 가짜 평균값으로 바꾸지 않음 |
| 표시 변환과 원본을 함께 보존 | RGB=(n+1)/2, cyclic orientation, μm 높이·공통 범위, headless glyph·스케일바를 독립 검산 |
| Figure와 데이터 출처 연결 | PNG/PDF/SVG, NPZ/JSON, 최소 SS·RGBA·source·spec·camera·hash manifest |

API·단위·camera·ray 식·barycentric 보간·원자 저장은 [시각화 기술 문서](../visualization/README.md), 연구 연결은 [표현 설계](VISUALIZATION_DESIGN_KO.md)에 정리했다. 문서 리뷰에서 +Z를 개별 표면 바깥쪽 법선과 혼동할 수 있는 문장을 고정 세계좌표의 높이 축으로 바로잡았다.

### 별도 compact 설계와 거부한 조건

기존 3×2 basket은 10 yarns·30 plies·210 fibers, 1.08×0.80 mm의 상대적으로 성긴 시편이다. 원래 spec·자료는 유지하고 별도의 2×2 compact basket을 만들었다. 확정한 값은 경·위사 8개씩, 총 **16 yarns·48 plies·336 fibers**, pitch80 μm, ply offset14 μm, ply twist+6 turns/mm, fiber twist−2.3 turns/mm, fiber radius2 μm, nominal crossing-envelope gap12 μm이다. 가시 패치는0.64×0.64 mm다.

55 μm-pitch 후보는 기존 sampling/refinement 예산 gate에서 실패했다. 70 μm-pitch·6 μm-gap 후보는 different-fiber capsule 검사에서 음의 간격을 보여 분리 인증이 실패했다. Capsule overlap은 실제 삼각형 관통을 증명하는 별도 narrow-phase 결과가 아니므로 구분했다. Gate를 완화해 그림을 채우지 않고 채택 가능한 80 μm 시편을 사용했다.

최종 전체 hierarchy는48 samples/crossing에서 최대 선분3.5911 μm·최대 turn0.09621 rad였다. 실제 다른-fiber/다른-ply capsule의 전역 분리 하한은 모두1 μm였다. 남겨진 후보 최소값2.4449/4.1221 μm를 전역 최소 간격으로 바꾸어 부르지 않았다. Same-curve self-contact, 본격적인 역학 평형·마찰·압착은 인증하지 않았다. [실제 입력·실패·sampling·clearance 감사](../examples/visualization/compact_three_ply_basket_design_audit.json).

### 실제 지도 생성과 첫 통합 테스트

원래 시편과 compact 시편에서 각각 전체 패치/같은 교차 확대 × ply/fiber의4개 지도를 생성했다. 기본 가로 표본은640, 표시 SS는2×2, 표면 원주 분할은64다. 원래 사례 전체 표본은474×640, 확대는640×640이며 compact는 모두640×640이다. 원래 사례의 공통 높이 범위는−70~70 μm, compact는−60~60 μm다. 다른 사례 간 동일 gray 값이 같은 높이를 뜻한다고 해석하지 않도록 범위를 각 figure에 명시했다.

원래 최종 지도 생성은 **87.824516963초**, compact는 **157.705858047초**였다. 저장한 최종 map에 대응하는 primary ray 질의는 각각 **7,129,600 / 8,192,000회**다. 이는 pixel-center와 실제 표시 SS를 합친 기하 교차 수이며 radiance 호출이나 독립 물리 표본 수가 아니다. 이번 지도 producer의 조명 렌더 호출은0회다. 개발 preview나 레이아웃 조정 후 반복도 독립 표본 증가로 계산하지 않았다.

Ply proxy와 explicit fiber의 전체 시야 sample coverage는 원래 시편에서 **41.1982% / 39.2858%**, compact에서 **74.2178% / 71.6590%**였다. Coverage는 해당 camera의 기하 hit 비율이다. 재료의 체적 충진율이나 광학 투과율로 해석하지 않는다. 정상적인 빈 공간은 gray background와 miss mask로 보존했다.

새 기하16개·표현11개·독립 반례4개 테스트를 기존391개와 함께 실행했다. 첫 통합 결과는 **422 tests, failures/errors/skips0, 27.997428244초**, 당시85개 source hash가 전후 동일했다. 이후 출력 저장을 보강하기 때문에 이 snapshot은 [pre-publication suite](../data/validation_v5_1/pre_publication_suite/test_summary.json)에 별도 보존한다. 최종 상태의 suite와 수치를 혼용하지 않는다.

### 파일 검산에서 발견한 PDF/SVG 잘림

수치 원본·좌표·ID·coverage·색 변환이 통과한 후, figure 파일 단계에서 독립 reader가 불일치를 발견했다. 당시 기록과 손상 바이트를 각각 보존했다.

| 발견 | 기대 길이 | 실제 관측 길이 | 검산 결과 |
| --- | --- | --- | --- |
| Canonical hierarchy PDF |566,866 bytes|433,871 bytes|EOF 없음·유효 페이지 확인 불가 |
| 후속 canonical hierarchy SVG |778,425 bytes|581,192 bytes|닫히지 않은 XML token |
| Compact material detail PDF |635,100 bytes|124,685 bytes|EOF 없음 |

첫 PDF는 같은 source로 plot-only 재구성하면 원래 완전한566,866 bytes와 같은 SHA로 복원됐다. 그러나 후속 파일까지 잘린 관측이 있어 최종 저장 경로를 보강했다. **원인은 확정하지 않았다.** 이 기록만으로 특정 라이브러리, 파일시스템 또는 작업자가 원인이라고 결론내리지 않았다. 첫 실패 시 새 geometric oracle은 아직 호출되지 않았으므로 그 감사 시도의 새 query는0회였다. [거부 근거](../data/validation_v5_1/rejected_figure_serialization/rejection_summary.json)와 하위 후속 기록을 보존했다.

이미 Git에 고정한 원래 지도 producer를 바꾸어 수치 측정을 다시 수행하지 않고 **새 publication adapter**를 추가했다. 기존 RGBA·camera·map metadata를 읽어 원래 compositor에 메모리 exporter를 일시 연결하고, PNG/PDF/SVG 전체를 BytesIO로 완성한 뒤 container 검사, flush/fsync·atomic replacement·exact-byte readback을 수행한다. 모든18개 accepted figure 파일의 최종 바이트를 한 번 더 대조하고 generation provenance와 publication provenance를 나눈다. PDF 전체 page parsing/raster QA는 설치된 도구로 별도 확인하며 필수 의존성으로 몰래 추가하지 않는다.

Compact 3-panel의 설명문이 패널 제목과 겹친 시각 문제도 출력 단계에서 설명문을 패널 아래 여백으로 옮겨 수정한다. 데이터·카메라·색 변환은 바뀌지 않는다. 사용하지 않는 generic compact triptych와 임시 파일은 accepted figure 집합에 포함하지 않는다. 최종 출력·테스트·독립 감사의 실제 결과는 완료된 JSON과 아래 게시 기록을 기준으로 읽는다.

### 추적 가능한 코드 단계

| 단계 | 로컬 commit | GitHub commit | 동일한 Git tree |
| --- | --- | --- | --- |
| 구조맵·표현·검산·compact 입력과 테스트 |`71ca7692b4e65cfa5cc9f39790e2903e64882191`|`368bf1468f59519fc863b6a4793907375c473db6`|`1820418e654a89d270e7df2080bfd52942b1f7d3`|

위 코드 commit을 기존 private repository의 main에 expected-head 조건으로 추가했다. 원래 v0.5.0 tag와 과학 core·자료는 그대로 유지했다. Publication 보강·최종 데이터·문서와 v0.5.1 태그는 그 뒤 별도 commit으로 이어지며, 게시를 실제 확인하기 전 완료로 기록하지 않는다.


### 최종 검증 완료와 v0.5.1 게시 준비 — 2026-10-12 KST / 2026-10-11 UTC

Publication 보강 후 최종 전체 suite와 두 사례의 독립 저장자료 검산, 최종 figure의 실제 화면·파일 확인을 완료했다. 아래 결과는 위의 422-test 중간 실행을 대체해 해석하는 **현재 소스의 최종 검증 기록**이며, 과거 v0.5.0의 391-test 실행과 각 실행 당시 source hash는 그대로 보존한다.

| 최종 확인 항목 | 실제 완료 결과 | 근거 |
| --- | --- | --- |
| 현재 전체 unittest suite | **425 tests, failures/errors/skips 모두 0**, **24.814377603초**. 실행 전후 검사 대상 **87개 source SHA-256 동일**, 변경 파일 0 | [최종 summary](../data/validation_v5_1/final_suite/test_summary.json), [실행 로그](../data/validation_v5_1/final_suite/tests.log) |
| 두 사례의 독립 저장자료 검산 | 합계 **8 maps·208 arrays·24개 고유 NPZ·18개 accepted figure files** 통과. 사례별 4 maps·104 arrays·12 NPZ·9 figure files | [기존 사례 summary](../data/validation_v5_1/independent_review/verification_summary.json), [compact summary](../data/validation_v5_1/compact_review/verification_summary.json) |
| 최종 해석적 기하 oracle | **594 primary-ray queries**, 기울어진 평면·세계좌표·두 겹 표면의 가림 검산. 이 oracle 및 저장자료 검산의 **조명·radiance 렌더 호출 0회** | [최종 oracle 원본](../data/validation_v5_1/independent_review/analytic_oracles.json), [독립 검토 기록](../notes/review_structure_figures_v5_1.md) |
| 최종 publication adapter | **15.417649361초**, 18개 accepted 파일의 메모리 container 검사·atomic 저장·exact-byte readback·최종 hash 대조 통과. 원시 기하 재추적 없음 | [최종 publication checks](../data/validation_v5_1/figure_finalization/publication_checks.json) |
| 실제 그림과 PDF 확인 | 독립 검토자가 최종 PNG 6개를 직접 확인. PDF 6개 모두 실제 **1-page parse와 rasterization** 성공; PNG decode·SVG XML parse도 확인 | [독립 visual review](../data/validation_v5_1/independent_review/visual_review.json), [container/page QA](../data/validation_v5_1/figure_finalization/page_container_qa.json) |

최종 425개는 기존 391개와 새 기하·표현·검산·publication 테스트 34개를 함께 실행한 테스트 함수 수다. 지도 생성의 primary-ray 수, 최종 594-query oracle, figure 파일 수 또는 v0.5의 광학 호출을 테스트 수에 합산하지 않았다. 저장 배열의 독립 reader는 원시 지도를 다시 생성하지 않았고, finalizer는 이미 보존한 RGBA를 재배치했다. **18개 accepted figure는 두 manifest가 지정한 세 그림 계열 × 세 형식 × 두 사례**이며, 거부하거나 미참조 상태로 보존한 중간 파일을 포함하지 않는다.

최종 문서 `README.md`, `docs/STATUS_KO.md`, `docs/RELEASE_V0_5_1.md`, `docs/VISUALIZATION_DESIGN_KO.md`, `CHANGELOG.md`, `notes/structure_figures_v5_1.md`, `notes/review_structure_figures_v5_1.md`를 읽기 전용으로 점검했다. **로컬 링크·이미지 링크 153회에서 누락 대상 0개**였고, 현재형 425 tests·87 sources·8 maps·24 NPZ·18 accepted figures는 최종 JSON 기록과 일치했다. 391-test 및 보강 전 422-test 표현은 과거 실행으로 구분되어 있었다. 이 문서 점검을 위해 코드·그림·전체 테스트를 다시 실행하지 않았다.

Publication 보강 코드와 최종 데이터의 Git 단계는 다음과 같이 기록했다.

| 단계 | 로컬 commit | 확인한 GitHub commit | Git tree |
| --- | --- | --- | --- |
| Publication 저장 보강 코드·회귀 검사 | `f4d4ab0073e4c669946506a2076d9b6de704c0fb` | `60659c371eb4878f66393e9c0097551f7b9afed2` | `b02b8d8735ddf811ea1ebb01fa72c64861678503` |
| 최종 지도·figure·검산·테스트 데이터 | `68d054f8cb0aca929a0e4d0dc140407bff623842` | 이 기록 시점에 원격 전송 중; commit 미확정 | `7dda82d2d9931f20f76a171648caaabd3c5899e9` |

Publication 보강 코드의 로컬·원격 commit은 같은 Git tree로 반영되었음을 확인했다. 데이터 단계는 **81개 파일·266,012,978 bytes**를 로컬 commit으로 고정한 뒤 원격 전송 중이다. 따라서 이 절은 v0.5.1의 최종 데이터·문서·tag·release가 게시되었다고 기록하지 않는다. 원격 최종 commit·tree와 private 저장소의 실제 게시 확인은 완료 후 별도 게시 감사 절에 추가한다. 기존 v0.5.0 tag와 과학 코드·광학 데이터는 유지한다.


### v0.5.1 원자료의 GitHub 전송 완료와 파일 트리 대조

최종 데이터 81파일·266,012,978 bytes를 비공개 저장소의 `v0.5.1-publication` 작업 브랜치에 반영했다. 로컬 데이터 commit `68d054f8cb0aca929a0e4d0dc140407bff623842`와 원격 commit `38835c84694ede5f64801f86d81da5a39afceac3`의 Git tree는 **`7dda82d2d9931f20f76a171648caaabd3c5899e9`로 정확히 같았다.** 원자료 34파일, 두 figure manifest와 accepted 그림 18파일, 최종·중간·거부 검증 근거를 이 snapshot에 포함했다.

전송 중 GitHub 연결 도구가 큰 base64 요청을 `MCP request body is invalid or exceeds the 16 MiB limit`이라는 HTTP 400으로 거부했다. 도구 제한에 맞는 50개 blob은 연결 도구로 저장하고, 큰 원본 8파일은 GitHub의 파일 업로드 기능으로 처리했다. 여섯 파일 96,181,691 bytes 묶음의 웹 commit도 파일 크기 오류로 실패했으며, 이 메시지만으로 별도의 정확한 제한값이나 내부 원인을 단정하지 않았다. 남은 파일을 성공한 범위의 두 파일 묶음으로 나눠 처리했다.

서로 같은 basename을 가진 여섯 파일은 작업 브랜치의 전송 단계에서만 구별 가능한 임시 파일명을 사용했다. 원본 크기와 Git blob SHA를 모두 확인한 후 manifest의 원래 경로로 tree를 구성했다. **최종 데이터 tree에는 전송용 임시 경로가 없으며 수치 배열·정밀도·파일 바이트도 바뀌지 않았다.** 원격 metadata에서 repository ID 1414149528·private=true와 현재 연구 설명을 재확인했다. [전송 및 대조 감사](../data/repository_data_v51_upload_audit.json).

연구 보고서에 실제 PDF 페이지 QA, 독립 육안 검토, 게시 전 해시 대조의 직접 링크도 추가했다. 로컬 Git origin은 변경된 저장소 이름 `Phill-lms/textile-appearance-research`에 맞췄다. 이 시점의 main은 publication 보강 코드 commit까지이며, 최종 문서를 작업 브랜치에 반영한 후 main·tag·release를 확정한다.


### v0.5.1 최종 게시 확인 — 2026-10-12 02:32:56 KST

**[v0.5.1 릴리스](https://github.com/Phill-lms/textile-appearance-research/releases/tag/v0.5.1)를 2026-10-11 17:32:56 UTC / 2026-10-12 02:32:56 KST에 게시했다.** Release ID는 `409816754`이며 draft가 아니다. 연구 제목·구조맵·18개 그림·425개 테스트와 미검증 범위를 게시 화면에서 확인했다. 저장소는 ID `1414149528`, `Phill-lms/textile-appearance-research`, **private=true**다.

최종 문서까지 포함한 로컬 commit `b30c53df6e3967bd166ceef52ef154fa769888c4`와 원격 commit **`4bb51b2b89e7cb98fddf8152c3012ca48d3822ef`**의 tree는 **`c453be81bf3cce275af7957dcd98957fdf6be344`로 정확히 일치**했다. 작업 브랜치의 완성 snapshot을 기존 main head에 대한 expected-SHA 조건으로 반영했다. GitHub API에서 main의 commit·tree, `refs/tags/v0.5.1`의 commit target, 실제 release 게시 시간을 각각 확인했다.

확정 문서 9개의 로컬 링크·이미지 링크 **252회에서 누락 0개**, 짝이 맞지 않는 code fence 0개를 확인했다. 검사는 [문서 링크 감사](../data/validation_v5_1/documentation_links.json)에 기록했다. 게시 후에도 최종 suite의87개 source hash와 accepted18개 figure hash가 원본과 일치했다. 이를 위해 전체 테스트나 과학 실험을 추가 실행하지 않았다.

[게시 화면](github_v0_5_1_release_verified.jpg)에는 연구 이름, private 저장소 표시, v0.5.1·commit, 구조맵8개·그림18개·425개 테스트가 함께 보인다. [게시 감사 JSON](../data/repository_release_v51_audit.json)에 source/data commit·동일 tree, 실제 release body, 화면 해시와 확인 범위를 보존했다. 이 게시 확인과 증거는 후속 문서 commit으로 추가하며, **v0.5.1 태그는 위의 확정 코드·자료·문서 commit에 고정한다.**
