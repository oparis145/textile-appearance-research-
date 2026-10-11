# v0.3.0 — 원사 평형에서 분광 원단 관측까지

작성일: 2026-10-11. 저장소: [Phill-lms/textile-optics-engine](https://github.com/Phill-lms/textile-optics-engine). 최종 commit·tag·업로드 기록은 [작업 로그](WORK_LOG.md)에서 확인한다. 기존 v0.1/v0.2 자료를 보존하고 새 모듈·실험·리뷰를 추가한 버전이다.

## 이번 버전의 결과

**원사 높이의 축소 평형을 계산하고, 그 위에 fiber/ply를 재구성하여 실제 분광 광학 계산까지 연결했다.** 동시에 개별 섬유의 방향 정보를 하나의 fabric 표현으로 축약할 때 생기는 오차를 계층별로 비교했다.

이는 통제된 합성 입력의 forward engine이다. 실물 원단 외관을 완전히 재현했거나 기존 RGB보다 좋은 계측 장치를 검증한 결과는 아니다. Dyeing/fading은 미뤄 두었다.

| 계층·모듈 | 이번 추가 | 실제 evidence |
| --- | --- | --- |
| Yarn network | 인장·작은 기울기 굽힘에너지, 선형 draft/slope/간격 제약, 수치 평형 | [weave_mechanics.py](../textile_sim/weave_mechanics.py), [역학 note](../notes/weave_mechanics_v3.md) |
| Fiber/ply geometry | 초기·평형 원사에 기존 계층 생성기 연결 | [42-fiber pair](../data/mechanics_v3/optical_pair/), [84-fiber multi-ply](../data/mechanics_v3/two_ply/) |
| Hierarchical optics | 공통 부피의 비차폐 투영 면적, SGGX fitting/정규화·rank 검사 | [optical_lod.py](../textile_sim/optical_lod.py), [광학 note](../notes/optical_scale_v3.md) |
| Spectral observation | 실제 파장별 fiber path tracing, 공식 CIE·Planck 적분, seed pairing | [raw data·metrics](../data/optical_v3/) |
| Reproduction | mechanics/optics/verify/tests unified runner | [run_engine_v3.py](../run_engine_v3.py), 각 새 run의 manifest |
| Research and review | 원문·인용 연결 확인, 독립 수학/데이터 검산, 실패·수정 기록 | [문헌](../notes/literature_engine_v3.md), [리뷰](../notes/review_engine_v3.md), [연구 설계](RESEARCH_DESIGN_KO.md) |

## 실제 실험 수치

### 원사 평형과 계층 재구성

Optical pair는 3×3 plain draft, 6 yarns, yarn당 1 ply×7 fibers로 **42 fibers / 8,064 segments**다. 선언한 합성 물성과 고정된 끝 경계에서 초기→평형의 excess energy는 **70.0505% 감소**했다. Warp crimp는 **0.700048%→0.122466%**, weft는 **0.700048%→1.366730%**였다. [Pair metrics](../data/mechanics_v3/optical_pair/pair_metrics.json).

Two-ply twill에는 **84 fibers / 10,752 segments**를 실제 배치했다. 강성 ratio·prestrain을 나눈 8개 sweep, 3개 draft, mechanical mesh 4/8/16, analytic simply-supported beam 검사를 수행했다. Optical pair의 8→16 mesh RMS 높이 차이는 **0.17681 μm**였다. 이 차이는 관찰된 discretization 변화이고 실물 오차 상한은 아니다. [Mechanics manifest](../data/mechanics_v3/experiment_manifest.json).

### 계층별 projected-area fitting

| 표현 | 초기 held-out 상대 RMSE | 평형 held-out 상대 RMSE |
| --- | ---: | ---: |
| 전체 1 SGGX | 3.5727% | 3.5788% |
| 경·위사 2 SGGX | 0.2198% | 0.2984% |
| 6 yarn SGGX | 0.2198% | 0.2990% |
| 6 ply SGGX | 0.2198% | 0.2990% |

96개 방향으로 맞추고 다른 1,200개 방향에서 평가했다. 원사당 1 ply인 fixture라 yarn/ply 분할은 같다. 이 결과는 **차폐를 생략한 원통 선분 투영 통계의 축약 오차**다. BSDF·실제 사진·새 원단 일반화 오차로 해석하지 않는다. [Optical metrics](../data/optical_v3/optical_scale_metrics.json).

### 실제 분광 관측

**536회**의 실제 explicit-fiber 렌더를 저장했다. 2 states×3 directions×17 wavelengths×4 seeds의 408회와, 반사 한 방향의 12.5 nm 중간파장 128회다. 64×64, 32 spp, 380–780 nm; 별도 Lambertian rig benchmark 1회가 있다.

| 조명 | 6500 K Planck 평균 Y 변화 | ΔY의 4-seed paired 95% 구간 |
| --- | ---: | ---: |
| 반사 azimuth 0° | +37.04% | +0.00383 ~ +0.00805 |
| 반사 azimuth 90° | −32.37% | −0.00645 ~ −0.00403 |
| 투과 azimuth 45° | +0.64% | −0.00042 ~ +0.00053 |

반사에서는 방향별로 반대 부호의 변화가 나타났고, 투과의 변화는 현재 MC 예산에서 분리되지 않았다. 3000 K에서도 반사는 +36.69%/−33.42%이고 투과는 +1.00%로 구간이 0을 포함했다. [분광 관측 note](../notes/optical_scale_v3.md).

한 반사 방향에서 실제 25/12.5 nm 결과의 XYZ 차이는 **0.170–0.363%**였다. 다른 두 방향은 50/25 nm 비교만 있다. Finite area source의 독립 적분과 Lambertian renderer 차이는 **0.178%**였다. 두 검사는 제한된 수치 검산이며 hair scattering이나 실물 color accuracy의 검증이 아니다.

## 이번 버전의 핵심 경계

- **역학:** 고정된 평면 track 위의 height-only quasi-static 모델이다. Full DER, 마찰·접촉압, 단면 압착, 옷 전체 drape가 없다. 경위사 `EA/B/rest length`는 합성 유효 입력이다.
- **Fiber 재구성:** ID·반지름·재료는 유지하지만 material point/질량/strain/twist 보존 변형이 아니다. 전체 volume proxy +0.04424%, warp/weft 길이 −0.57358%/+0.66206%를 기록했다.
- **광학 축약:** SGGX projection과 phase 수학을 준비했지만 aggregate fabric BSDF를 구현·렌더 비교한 것은 아니다. 기준 이미지는 실제 개별 fiber hair 모델이다.
- **분광:** Scalar ray tracing을 파장별로 실제 실행했다. 회절·간섭·편광이 포함된 3D ray–wave 모델은 아니다. 6500 K Planck 광원은 D65가 아니다.
- **통계:** 4 seed 구간은 Monte Carlo 불확실성만 나타낸다. 모델/실물/교정 변동을 포함하지 않으며 pixel·파장을 독립 표본으로 부풀리지 않는다.
- **실물·소자:** Named textile calibration, inverse reconstruction, RGB 대비 추가 정보, 실제 metasurface efficiency, 사용자 시편 매칭은 다음 과제다.

## 독립 리뷰와 실패에서 배운 것

리뷰 중 낮은 fitting residual만으로 식별 부족 angular set을 통과시키는 경로, 다른 문제/height에 과거 equilibrium certificate를 붙일 수 있는 경로, slope 전제가 깨졌는데 configured gap을 보고하는 경로를 찾아 수정했다. 현재는 angular design rank, problem/height hash와 export 재계산, invalid premise의 명시적 진단이 적용된다. [수학·회귀 리뷰](../notes/review_engine_v3.md).

기계 좌표의 family-exchange 검사는 통합 환경에서 picometer 수준 solver 순서 차이로 한번 실패했다. Energy/gradient/Hessian의 교환 불변성을 추가 확인하고 더 엄격하게 solve하여 원래 coordinate assertion tolerance를 유지했다. 실패 로그와 재검산은 리뷰에 보존했다. 테스트 통과는 구현 계약의 evidence이며 실제 원단 모델의 정확성을 대신하지 않는다.

최종 **239 tests, 0 failures/errors/skips**, 19.735초의 결과를 확인했다. 과학 모듈 230개와 runner 9개를 포함한다. 통합 test 수·종료 상태·source hash는 [data/final_test_summary.json](../data/final_test_summary.json)이 기준이다. v0.2의 **181 tests, 0 failures/errors/skips** 기록은 [v2 reproduction summary](../data/engine_v2_test_reproduction/tests/test_summary.json)에 그대로 보존한다.

## 재현

```bash
# 실행할 명령·경로만 확인: 쓰기 없음
python run_engine_v3.py --dry-run

# 저장된 기준 결과 검산: 새 536회 렌더를 실행하는 명령은 아님
python run_engine_v3.py --stages verify --output scratch_runs/v3_audit

# 기존 pair에서 투영 축약·scene export를 실제 재계산, 렌더는 생략
python run_engine_v3.py --stages optics verify --no-render \
  --output scratch_runs/v3_projection

# 새 mechanics부터 모든 계산 실행
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python run_engine_v3.py --output scratch_runs/v3_full
```

Output은 새 폴더 또는 빈 폴더여야 한다. Omitted upstream 입력의 기본 위치는 `data/`이며 `--input-data`로 바꾼다. `--no-render`에서도 tests를 선택하면 작은 실제 renderer tests는 실행될 수 있다. 저장된 결과의 검산, 새로 실행한 계산, 생략한 rendering을 run manifest에서 분리한다.

별도 integration run은 저장소 밖 작업 디렉터리에서 새 mechanics → optics → verify를 `--no-render`로 실행해 성공했다. [보존한 로그·manifest·검산](../data/validation_v3/no_render_integration/)은 전체 출력이 아닌 부분 evidence archive다. 이 경로는 실제 의존 연결을 검사했으며 536개의 새 영상 재계산 성공 기록으로 사용하지 않는다.

## 다음 연구의 한 문장

**현재 엔진으로 기하·재료가 서로 모방하는 관측을 찾고, 그 모호성을 줄이는 채널이 강한 다중조명 RGB와 model mismatch를 모두 견디는지 검증한다.** 성공하면 그 채널을 기존 렌즈/격자/편광자 및 실제 메타광학으로 구현해 시스템 수준에서 비교한다. [상세 연구 목적·모듈·가설·gate](RESEARCH_DESIGN_KO.md).
