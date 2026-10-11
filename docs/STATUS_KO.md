# 현재 연구 상태 — v0.5

**업데이트: 2026-10-12 KST / 2026-10-11 UTC**

## 지금 어디까지 됐는가

**Fiber → ply → yarn → weave → fabric의 계층 기하와 제한된 원사 평형을 만들고, 같은 섬유의 물질점·반지름 변화를 3D 광학 계산에 연결한 상태다.** v0.5의 전체 391개 테스트, 최종 216회 비교 실험과 독립 검산, 32회 물리 oracle, 72회 renderer 길이 척도 실험을 완료했다.

**전체 연구가 완료된 상태는 아니다.** 실제 실크·코튼·큐프라·린넨의 외관을 정확히 복원했다거나, 좋은 RGB보다 추가 계측이 유리하다거나, 메타표면의 이득을 입증한 결과는 아직 없다. 이번에 새로 확인한 가장 가까운 과제는 **광택의 수치 수렴**이다. 그것을 확보해야 구조·재료 차이를 계측 설계의 근거로 사용할 수 있다.

## 원래 연구 목적

연구 제목은 **직물 외관 재현을 위한 다중 규모 광학 모델링과 메타광학 계측**이다. 온라인 의류 사진에서 예상한 시각적 재질감과 실제 원단을 보는 경험 사이의 차이를 줄이는 것이 목적이다. 고해상도 RGB의 디테일을 보존하면서 다른 조명·시점·역광에서의 외관을 예측하고, 그 예측에 유용한 각도·분광·편광·IR 정보를 선별해 메타광학 계측과 연결한다.

현재 시뮬레이터는 이 연구의 순방향 기반 모듈이다. 염색·퇴색은 보류하며, 촉감은 속성별 기준 측정이 필요한 후속 연구로 둔다. 전체 대화의 요구와 결정은 [연구헌장](RESEARCH_CHARTER_KO.md)에 정리했다.

## 모듈별 상태

| 모듈 | 구현·검증한 부분 | 아직 해결할 부분 |
| --- | --- | --- |
| **Constituent / fiber** | 재료 ID·합성 복소 굴절률, 명시적 중심선·반지름, 국소 2D ray/Maxwell 계산 | 실제 재료 spectrum·단면·복굴절·표면 상태의 측정 |
| **Ply / yarn** | 꼬임·배치·migration·loop, 기준 물질좌표의 계층 운반 | 실제 material twist, 내부 응력·sliding·contact |
| **Weave / fabric** | draft·lift plan·평직·능직 등, 유효 원사 높이 평형, finite patch | 3D rod·마찰·압착·동적 변형·전체 의류 drape |
| **기하 → 광학** | v0.5 가변 radius·닫힌 mesh·Fresnel 경계·경로 길이 흡수 | 같은 fiber의 self-contact 인증, 단면 재구성의 국소 보존과 수렴 |
| **광학 해석** | 기존 분광 hair 경로, 새 closed-volume 경로, raw radiance·seed 통계 | 원주·축 sampling·ray offset의 수치 오차, 실측 BSDF·파동 결합 |
| **계층 광학 축약** | projected-area density·SGGX fitting 진단 | fabric BSDF·차폐·다중 산란·영상 오차에 대한 검증 |
| **카메라·추정·계측** | 관측·이상적 meta 모듈과 비교 설계 보존 | 교정된 실제 카메라, inverse fitting, RGB 대비 추가 채널 이득, 소자 제작 |
| **제품 표현·지각** | 재조명·확대·역광·시편 매칭 평가 구조 | 실제 원단을 이용한 표시·사용자 평가 |

## 이번에 실제로 추가한 것

| 항목 | 결과 | 근거 |
| --- | --- | --- |
| 전체 테스트 | **391개, 실패·오류·생략 0**; 기존 코드와 함께 실행 | [전체 summary](../data/final_test_summary.json), [log](../data/final_tests.log) |
| 가변 반지름 연결 | 42 fibers, 8,106 points, node radius 2.8083–3.2355 μm | [기하 결과](../data/variable_radius_v5/geometry_metrics.json) |
| 반지름·원주 분할 비교 | **216회**, 64×64·64 spp, 3파장·3조명·4 seeds | [실험 manifest](../data/variable_radius_v5/experiment_manifest.json) |
| 저장 결과 독립 검산 | 252 meshes, 54 scenes, 216개 영상·통계와 원본 material pair 재구성 | [독립 summary](../data/validation_v5/independent_review/verification_summary.json) |
| 물리 oracle | **32회**, Beer·furnace·taper·8배 길이 상사 | [물리 보고서](../notes/volume_optics_validation_v5.md) |
| 실제 fiber의 길이 척도 감도 | **72회**, 같은 물리 모델의 수치상 1/10/100배 scene | [감도 결과](../data/validation_v5/volume_scale_sensitivity/sensitivity_metrics.json) |
| 통합 실행 | 저장소 밖 cwd에서 새 기하 → 검산, render 0회; 원본·소스 변화 없음 | [통합 manifest](../data/validation_v5/no_render_integration/run_manifest.json) |

세 실험의 합은 **320번의 실제 render 호출**이다. 72회 감도 실험의 S=1 조건 24개는 주 실험의 N=64·550 nm와 겹치며 원시 영상도 동일하다. 독립 반복은 각 조건의 4 seeds이고, 중복 실행·RGB 채널·픽셀을 추가 독립 표본으로 계산하지 않는다. 개발 중 거부한 216회와 별도 pilot도 최종 표본 수에 합산하지 않는다.

## 결과가 알려준 것

**첫째, 가변 반지름의 광학 연결은 실행된다.** 다만 전체 frustum 적분을 맞추면서도 각 선분의 부피는 약 −3.96~+3.80% 재분배된다. 실제 국소 질량 보존이 해결됐다는 의미로 쓰면 안 된다.

**둘째, 부피가 수렴해도 광택이 수렴한 것은 아니다.** 16→32→64각형에서 mesh 부피 오차는 약 −2.55→−0.64→−0.16%로 줄었지만, 32→64의 R0 평균 radiance는 약 25.7~31.6% 바뀌었다. 최고 분할에서 반지름 변화의 9개 조건은 모두 신뢰구간에 0을 포함했다. 현 예산에서 반지름 효과를 분리하지 못했다는 결과다.

**셋째, scene 길이 단위도 수치 검증 항목이다.** Renderer의 surface-ray offset은 완전한 길이 상사를 따르지 않는다. 별도 fiber 감도 실험에서 S=10과 100 사이의 평균 차이는 약 −4.24~+3.30%이고 모든 구간이 0을 포함하지만, 이것은 두 설정이 충분히 가깝다는 동등성 검정이 아니다. 수렴을 주장하려면 허용 오차 안으로 구간 전체가 들어오는지 따로 평가해야 한다.

## 다음 연구 단계와 완료 기준

1. **순방향 모델의 수치 오차를 먼저 제한한다.** 원주·축 sampling, 좌표 원점·scene scale, 경계 offset, Monte Carlo 예산을 별도로 바꾸어 조명별 contrast의 오차 범위를 구한다. 목표 radius·material contrast보다 작은 오차인지 사전에 정한 허용값으로 판단한다. 단지 차이의 CI에 0이 있다는 기준은 사용하지 않는다.
2. **단면 법칙과 광학 축약을 검증한다.** 현재 global volume scale과 국소 보존을 고려한 대안을 비교하고, 고해상도 explicit fiber 결과를 기준으로 ply/yarn/fabric 축약의 실제 BSDF·영상 오차를 평가한다. 파동 모델은 별도의 정규화·coherence 계약을 통과한 범위에서 연결한다.
3. **작은 실제 원단 패치로 물성과 관측계를 보정한다.** 현미경 구조, 방향별 반사·투과, 광원·카메라를 측정하고 미관측 조명·독립 시편에서 검증한다. 여기서부터 실제 소재 이름별 재현 성능을 말할 수 있다.
4. **강한 RGB 비교군을 넘는 관측을 선택한다.** 같은 촬영 시간·광량·픽셀 조건에서 각도·분광·편광·IR의 추가 가치를 검증한다. 유용한 관측이 확인되면 기존 광학과 메타광학의 전체 시스템을 비교한다.

상세 수학·가정·원시 결과·실패 후 수정은 [v0.5 실험 보고서](../notes/variable_radius_v5_experiment.md), 전체 배포 근거는 [릴리스 설명](RELEASE_V0_5.md), 시간 순서의 의사결정과 버전 이력은 [작업 로그](WORK_LOG.md)에 있다.
