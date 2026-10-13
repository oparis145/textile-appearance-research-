# 직물 외관 재현을 위한 다중 규모 광학 모델링과 메타광학 계측

**Multiscale Textile Appearance Modeling and Meta-Optical Sensing**

의류 사진에서 예상한 시각적 재질감과 실물의 차이를 줄이는 연구입니다. 실제 공간 디테일을 보존하며 다른 조명·시점·역광의 외관을 예측하고, 그 예측에 필요한 추가 관측을 검증한 뒤 외부 메타광학을 설계합니다. 4K·매크로·다중조명 RGB는 강한 비교군이고, VIS가 기준 대역입니다. IR은 추가 정보의 가치로 평가합니다. **염색·퇴색은 계속 보류합니다.**

## 최신 추가: 관측 오차와 국소 부피 보존

2026-10-13의 **observation-gate 연구 증분**을 추가했습니다. 정식 v0.6 릴리스나 전체 엔진 검증을 뜻하지 않습니다. 기존 v0.5.1 코드·실험·논문용 구조맵은 보존했고, 아래 새 모듈은 그 결과를 덮어쓰지 않습니다.

| 추가 모듈 | 이번에 실제로 한 일 | 아직 주장하지 않는 것 |
| --- | --- | --- |
| `local_volume_profile.py` | 양의 연속 반지름에서 각 선분의 직선 원뿔대 부피를 보존; 16개 합성 변형 검사 | 실제 섬유 구성식·굽은 mesh의 국소 고체 부피 보존 |
| `surface_reference.py` | 원형/정다각형의 첫 표면 Fresnel 반사를 유한 각도 관측에서 비교; 252조건 | 완전한 fiber/fabric BSDF, 내부 굴절·다중 산란·파동 통합 |
| `observation_gate.py` | CI 포함 0과 동등성을 구분; 관측 오차·refinement별 축약 선택; v5 데이터 adapter | 실측 정확도, 수렴한 reference의 자동 인증 |
| `run_observation_upgrade.py` | 새 폴더에 결과와 소스·출력 hash 저장; 결정론적 재실행 | 기존 425개 테스트나 Mitsuba 원단 실험의 재실행 |

**새 모듈 55개 테스트가 실패·오류·생략 없이 통과했습니다.** 기존 v0.5.1의 425-test 기록과 합산하지 않습니다. 이번 새 Mitsuba/3D 원단 렌더는 0회입니다. 현재 환경은 Python 3.13.5, NumPy 2.3.5, SciPy 1.17.0이며 이전 전체 검증 환경과 구분합니다.

실제 결과: 비교용 전체 부피 rescale의 최대 선분 오차 2.493%가 새 직선 원뿔대 규칙에서는 약 6.7e-16이었습니다. 광학 쪽에서는 detector bin과 facet 방향의 우연한 정렬이 가짜 수렴을 만들 수 있어, bin 수·단면 위상 대조와 회귀 테스트를 추가했습니다. 이것은 **기준 문제의 개선**이며 기존 3D 원단 광택 오차를 전부 해결한 결과가 아닙니다.

## 읽는 순서

- [현재 상태](docs/STATUS_KO.md) · [이번 수학·결과·한계](docs/OBSERVATION_UPGRADE_KO.md)
- [문헌별 읽기 깊이·구현 결정](notes/literature_observation_upgrade.md)
- [새 수치 요약](data/observation_gate_v6/summary.json) · [새 테스트 기록](data/observation_gate_v6/test_summary.json) · [실행 manifest](data/observation_gate_v6/run_manifest.json)
- [원래 연구헌장](docs/RESEARCH_CHARTER_KO.md) · [기존 전체 연구 설계](docs/RESEARCH_DESIGN_KO.md) · [구현 아키텍처](docs/ARCHITECTURE.md)
- [변경 전 v0.5.1 README 전체](README_v0_5_1.md): 과거 그림·수치·모든 실행 명령·문헌·라이선스 안내를 보존합니다.

## 새 모듈 실행

저장소 루트와 기존 NumPy/SciPy 환경에서:

```bash
python -m unittest discover -s tests -p 'test_observation_upgrade.py' -v
python run_observation_upgrade.py --output scratch_runs/observation_v6 --dry-run
python run_observation_upgrade.py --output scratch_runs/observation_v6
```

출력 폴더는 새 폴더 또는 빈 폴더여야 합니다. `results.json`은 전체 각도 분포와 조건별 수치를, `run_manifest.json`은 소스/입출력 hash와 실행 범위를 담습니다. 저장소에는 compact summary와 재생성 코드를 두고 전체 raw 결과는 실행으로 만듭니다.

기존 v5 archive의 평균 radiance를 새 동등성 판정으로 읽는 선택 기능도 있습니다. `--v5-input data/variable_radius_v5 --coarse 32 --fine 64 --absolute-tolerance ...`를 추가하되, 허용량은 실험 전에 정한 **절대 radiance 단위**여야 합니다. fixture 기반 adapter 테스트와 실제 archive 전체 검증은 다릅니다.

## 연구 우선순위

현재 구현은 실제 원단의 정확한 재현이나 RGB 대비 추가 계측·메타표면 우위를 입증한 상태가 아닙니다. 다음 단계는 원형 기준에서 곡선 fiber·교차·작은 patch로 광학 수렴을 검증하고, 물질좌표와 새 반지름의 연결에서 실제 고체 부피·접촉을 확인하는 것입니다. 그다음 실측 thread R/T와 strong RGB 기준을 교정하고, fiber/ply/yarn 축약 및 추가 관측의 이득을 비교합니다.

기존 provenance와 제3자 권리는 [이전 README](README_v0_5_1.md), [참조 NOTICE](references/NOTICE.md), 각 논문의 라이선스를 따릅니다. 이번 구현은 참고한 논문 전체의 재현이나 새로운 오픈소스 라이선스 부여를 뜻하지 않습니다.
