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
