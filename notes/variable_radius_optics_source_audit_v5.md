# v0.5 가변 반지름 광학 연결: 소스 감사와 모델 선택

검토일: 2026-10-12 KST / 2026-10-11 UTC. 대상 runtime: **Mitsuba 3.9.1, `llvm_ad_rgb`**.

## 1. 결정과 적용 범위

**닫힌 tapered-tube triangle mesh + dielectric 경계 + homogeneous 순수 흡수 medium + `volpath`를 별도 ray-optical 기준 모델로 추가한다.**

v0.4의 `hair` BSDF 경로는 유지한다. 새 모델에서는 광선이 실제 입사점에서 굴절하고, 닫힌 경계 내부를 이동한 길이에 따라 흡수된 다음 실제 출사점에서 다시 경계를 만난다. 이는 `hair`의 국소 산란함수와 다른 광학 모델이다. 두 경로의 영상 차이를 반지름 효과나 새 구현의 정확도 개선이라고 해석하지 않는다.

첫 비교의 조건은 **같은 target centerline, 같은 원주 분할과 ring 배치, 같은 경계 모델, 같은 광학 상수·카메라·광원에서 constant radius와 transported radius만 변경하는 것**이다. 원주 분할 16/32/64의 차이는 별도 기하 수렴 항목으로 보고한다. 실물 정확도, 편광, 회절, 섬유 내부 미세 산란, 실제 원단의 표면 거칠기를 검증했다는 뜻은 아니다.

이 결정은 아래의 pinned source 감사, 실제 runtime 질의, 이후에 필요한 검증을 구분해 내렸다. 본 문서의 직접 실행은 **곡선 API 계약 검사**이며, 새 mesh renderer의 Beer/Fresnel 검증과 전체 fabric 실험 결과는 별도 실행 보고서의 책임이다.

## 2. 확인한 소스와 버전

공식 repository의 `v3.9.1` annotated tag를 GitHub API로 조회했다.

- Tag object: `a8c3ffd763c8e097a57e4fdb69befb78d5da2f2d`.
- Commit: `478e193a183c21723f4a8251afc3ad29a8da4c5e`.
- Tree: `a01a2a9033e5a2125d11c451e61d4fdd19c57c9d`.
- 아래 각 파일의 실제 UTF-8 byte 수와 Git blob hash를 이 tree에 있는 값과 대조했다.
- 설치된 wheel의 `mi.__version__`은 3.9.1이다. 소스 tag의 내용 확인과 runtime 동작 검사는 수행했지만, wheel binary 전체를 이 commit에서 재현 빌드했다는 보증은 아니다.

| 파일 | Byte 수 | Git blob SHA-1 | 검토 대상 |
|---|---:|---|---|
| `src/bsdfs/hair.cpp` | 32,994 | `90bd5b5180366607658f1b1cef9a173648531e38` | 흡수 texture 평가, 반지름으로 정규화된 광로 |
| `src/shapes/bsplinecurve.cpp` | 53,880 | `f14832c09bf38d4f827536ae29fca8295cfff581` | 가변 반지름, global UV, 내부 교차 거부 |
| `src/bsdfs/dielectric.cpp` | 15,725 | `a9b08d2743e2cddca52737523510ef8f60726190` | 굴절률 경계와 medium 연결 |
| `src/media/homogeneous.cpp` | 7,226 | `cbb9a8d61c938981f7a45e3383b75471167b14c6` | 실제 scene-unit 소광계수와 산란 albedo |

기존 저장소의 `references/Mitsuba_hair.cpp`와 새로 조회한 pinned `hair.cpp`의 SHA-256은 모두 `0ce061635989dfbb12b85b3c9f14851e858ca297ed71e8df86599b0c97a4791e`로 일치했다.

## 3. 후보 A: 가변 radius B-spline + hair BSDF

### 3.1 Geometry에 radius를 넣는 것만으로 흡수는 맞아지지 않는다

`hair.cpp`의 `eval`, `pdf` 관련 계산 및 sampling용 attenuation에서 흡수 texture를 surface interaction으로 평가한다. 사용되는 내부 chord 표현은 다음과 같다.

\[
T=\exp\left[-\sigma_{a,\mathrm{shader}}\,
\frac{2\cos\gamma_t}{\cos\theta_t}\right].
\]

곱해지는 기하학적 길이가 단위 반지름 기준이므로, 물리 흡수계수 \(\mu_a\,[\mathrm{mm}^{-1}]\)를 사용하는 현재 모델의 mapping은

\[
\sigma_{a,\mathrm{shader}}(s,\lambda)
=\mu_a(\lambda)\,r(s).
\]

PBRT의 공식 hair 설명도 단위 단면을 이용해 내부 경로와 Beer 흡수를 유도한다. 반지름이 변하는데 constant shader 입력을 그대로 유지하면, 현재 물리적 \(\mu_a\) 의미를 유지할 수 없다. [`hair.cpp`][S1], [PBRT Hair][P1].

### 3.2 정확한 좌표와 radius 재구성의 조건

Pinned `bsplinecurve.cpp`의 `compute_surface_interaction`은 다음 관계를 사용한다.

\[
v_{\rm global}=(v_{\rm local}+j)/N_{\rm segments}.
\]

여기서 \(j\)는 shape 전체의 primitive index이고, \(N_{\rm segments}\)는 그 shape에 들어 있는 **모든 곡선의 segment 수**이다. 개별 섬유마다 0부터 1로 반복하는 좌표가 아니다. `cubic_interpolation`은 중심선과 반지름에 같은 uniform cubic B-spline basis를 적용한다. 따라서 미래의 texture 구현은 shape/primitive 소속, control-index buffer, 실제 float32 control radii, 같은 basis를 사용해야 한다. coarse bitmap이나 fiber index만으로 대체하는 방법은 동등한 구현이 아니다. [`bsplinecurve.cpp`][S2].

이 연결을 정확하게 만들어도 hair BSDF는 국소 원통 산란 근사이다. 급격한 taper나 곡률에서 실제 출사 위치, 그 위치의 반지름·법선, 여러 경계 교차가 같은 국소 원통으로 대표될 수 있는지 따로 검증해야 한다. 정확한 `sigma_a` texture는 이 근사 한계 전체를 해결하지 않는다.

### 3.3 Curve + dielectric + medium을 직접 쓰지 않는 이유

공식 shape 문서와 pinned source는 curve의 backface가 제거되어 **곡선 내부에서 시작한 광선이 내부에서 나가는 경계를 교차하지 못한다**고 명시한다. 외형을 닫는 것과 내부 광로를 추적할 수 있는 것은 별개의 조건이다. 내부 흡수를 처리하려고 `bsplinecurve`에 단순히 dielectric과 interior medium을 붙이는 구성은 이 연구의 체적 경계 모델로 채택하지 않는다. [Shapes 문서][D1], [`bsplinecurve.cpp`][S2].

## 4. 실제 runtime 계약 검사

두 개의 곧은 taper를 하나의 `bsplinecurve` shape로 묶었다. 각 곡선의 control z는 \([-1,0,1,2]\), control radius는 \(r_0+0.1z\)이다. 첫 곡선은 x=0, \(r_0=0.2\), 두 번째는 x=3, \(r_0=0.4\)로 설정했다. 렌더러가 표현하는 중심선 구간은 z=0..1이며 각 곡선은 하나의 segment를 갖는다.

각 곡선의 z=0.05, 0.25, 0.50, 0.75, 0.95에 대해 외부에서 -x 방향으로 ray를 보내 총 10회 실제 교차를 질의했다. 본 probe의 길이는 임의 scene unit이고, 물리 원단 반지름 측정값이 아니다.

| 직접 확인한 항목 | 결과 |
|---|---:|
| Runtime / variant | 3.9.1 / `llvm_ad_rgb` |
| 외부 ray 10개의 교차 | 모두 유효 |
| \(r_0+0.1z\)와 교차점에서 읽은 radius의 최대 절대 차 | \(2.0980834958\times10^{-7}\) scene unit |
| \((j+z)/2\)와 `si.uv.y`의 최대 절대 차 | \(2.3841857932\times10^{-8}\) |
| 첫/두 번째 곡선 `prim_index` | 0 / 1 |
| 첫 곡선 내부에서 +y로 보낸 ray의 경계 교차 | **False** |
| 닫힌 cube 내부에서 +y로 보낸 ray의 경계 교차 | **True** |

외부 +x 표면의 법선은 약 \((0.9950372,0,-0.0995037)\)로 나타났고, 선형 taper의 해석적 법선 \((1,0,-0.1)/\sqrt{1.01}\)과 일치했다. 표면 법선을 원형 단면의 방사 방향만으로 지정하면 이러한 taper 성분을 놓친다는 것을 확인했다.

실행 파일의 SHA-256: `ecbb5de83f474c8856052436d90fdd3a95567e91df05cf486e75cc42d5ccb960`. 곡선 입력 SHA-256: `a45bb07529b7948c1367c6065c797d32c90caccebabcd3afa155a68ad23a9dbe`. 개발 중 실행 파일·입력·출력은 `scratch_runs/v5_source_audit/`에 보관했으며 이 경로는 배포 자료의 필수 의존성이 아니다. 아래 appendix는 임시 파일만으로 같은 계약을 다시 검사하는 완전한 코드다.

최초 probe에서 numpy scalar가 섞인 list를 `Ray3f`에 직접 전달한 호출은 Python binding의 implicit conversion 오류로 실패했다. 이후 명시적인 `Point3f`/`Vector3f`와 Python float를 사용했고 위 결과를 얻었다. 이 초기 호출 오류를 광학 실패나 통과한 probe로 계산하지 않았다.

## 5. 후보 B의 물리·수치 계약

경계의 `dielectric`은 실제 polygon face normal과 실수 굴절률을 사용한다. 경계 밖은 기존 배경 매질, 안은 해당 fiber의 homogeneous medium으로 둔다. 단색 계산에서는

\[
\sigma_t=\mu_a,\qquad \mathrm{albedo}=0,
\qquad \sigma_s=0,\qquad T(d)=e^{-\mu_a d}.
\]

Mitsuba의 homogeneous medium은 inverse scene unit의 \(\sigma_t\)를 받는다. scene 좌표가 mm이면 입력도 \(\mathrm{mm}^{-1}\)로 전달한다. Hair에서 사용한 \(\mu_a r\) 값을 여기 재사용하면 단위 오류가 된다. Dielectric 경계와 흡수 medium의 결합에는 medium을 처리하는 integrator가 필요하다. [Homogeneous 문서][D2], [Dielectric 문서][D3], [Integrators 문서][D4].

본 연구에 필요한 추가 계약과 검증은 다음과 같다.

1. **닫힘·방향:** 각 연결 성분은 닫힌 orientable 2-manifold이고, 퇴화 face가 없으며, 실제 outward winding과 내부→외부 교차가 맞아야 한다. Signed volume 하나만 양수라고 모든 face가 올바르다는 증명은 되지 않는다.
2. **매질 배치:** 서로 겹친 닫힌 섬유에서 interior/exterior 전이가 의미를 잃지 않도록 교차·겹침을 검사한다. Positive pairwise surface clearance는 서로 다른 섬유에 대한 검사이며 한 섬유의 self-intersection 보증을 자동으로 주지 않는다.
3. **기하 근사:** 수송된 segment radius를 vertex ring radius로 옮기는 방식은 별도 모델이다. 그 재구성 규칙을 기록하고, v0.4의 \(\sum_e\pi r_e^2\ell_e\) 보존과 실제 mesh volume 보존을 혼동하지 않는다.
4. **법선:** 최초 검증 경로는 geometric face normals를 사용한다. Vertex normal 보간을 켜려면 smooth shading과 실제 굴절 경계의 불일치·에너지 오차를 별도로 검토한다.
5. **해상도:** 같은 ring 배치에서 원주 분할만 바꾼 수렴, 같은 원주 분할에서 축 방향 표본·반지름 profile을 바꾼 수렴을 분리한다. 영상차에는 Monte Carlo 변동 구간도 함께 보고한다.
6. **단위:** 모든 길이를 a배, \(\mu_a\)를 1/a배 하고 다른 무차원 조건을 같게 두었을 때 transport가 일치하는지 검증한다. 모든 emitter 크기·위치와 camera·ray 오차 조건도 함께 다뤄야 한다.
7. **분광:** \(\mu_a=4\pi\kappa/\lambda_0\) 변환에서는 진공 파장을 mm로 맞춘다. 실수 굴절률 interface와 Beer absorption의 결합은 complex-index Fresnel이나 파동 전자기 해와 동일하지 않다. 파장 범위·물성 출처·약한 흡수 근사의 범위를 기록한다.
8. **통계·광원:** 매끄러운 dielectric은 좁은 specular 경로를 가지므로 낮은 spp나 작은 광원에서 영상이 매우 희소할 수 있다. 같은 seed를 사용했다는 사실만으로 mesh 분할 간 경로가 완전히 대응하거나 분산이 반드시 감소한다고 가정하지 않는다.

내접 정 N각형의 원 단면 대비 면적 비는 \(N\sin(2\pi/N)/(2\pi)\)이다. 이는 직선·평행 ring에 대한 기하학적 비교 기준이며, 곡선 섬유 mesh 전체의 volume 오차를 대신하지 않는다. 16/32/64 분할의 이상적인 원 단면 면적 부족은 각각 약 2.5505%, 0.6413%, 0.1606%다. 따라서 원주 16분할의 image 변화가 작다는 관측만으로 부피·표면·굴절이 수렴했다고 결론내리지 않는다.

## 6. B가 검증하는 것과 남기는 것

이 경로는 지정된 경계·굴절률·흡수계수에 대해 **형상이 실제 내부 광로를 어떻게 바꾸는지** 검사하기 위한 기준 모델이다. Hair 모델의 거칠기·scale tilt를 동일한 방법으로 복제하지 않는다. 실제 섬유에는 단면 비원형성, 복굴절, 표면층, 잔털, 내부 공극 등 별도 관측이 필요한 항목이 있다. 이 중 무엇이 목표 외관 오차를 지배하는지는 실측 자료와 광학 모델 비교로 판단해야 한다.

따라서 v0.5의 채택은 “원단 외관 문제를 해결했다”는 결과가 아니다. **변형에서 유도한 반지름 상태를 추적 가능한 물리 단위와 닫힌 광학 경계에 연결하는 구현 선택**이다.

## Appendix: Runtime probe 재현 코드

저장소 루트에서 Mitsuba 3.9.1이 준비된 Python으로 실행한다. 아래 코드는 ray intersection 10회와 내부 경계 2회를 질의한다. 영상 렌더링 횟수에는 포함하지 않는다.

```python
import tempfile
from pathlib import Path
import numpy as np
from textile_sim.render import get_mitsuba

mi = get_mitsuba()
with tempfile.TemporaryDirectory() as folder:
    filename = Path(folder) / "two_tapered.curves"
    with filename.open("w") as stream:
        for x, radius0 in [(0., .2), (3., .4)]:
            controls = [[x, 0., z, radius0 + .1*z]
                        for z in [-1., 0., 1., 2.]]
            np.savetxt(stream, controls, fmt="%.17g")
            stream.write("\n")
    scene = mi.load_dict({"type": "scene", "curves": {
        "type": "bsplinecurve", "filename": str(filename)}})
    radius_errors, uv_errors = [], []
    for index, (x, radius0) in enumerate([(0., .2), (3., .4)]):
        for z in [.05, .25, .5, .75, .95]:
            ray = mi.Ray3f(mi.Point3f(x+1., 0., z),
                          mi.Vector3f(-1., 0., 0.))
            si = scene.ray_intersect(ray)
            assert bool(np.asarray(si.is_valid())[0])
            position = np.asarray(si.p).ravel()
            uv = np.asarray(si.uv).ravel()
            radius_errors.append(abs(float(position[0])-x-(radius0+.1*z)))
            uv_errors.append(abs(float(uv[1])-(index+z)/2.))
            assert int(np.asarray(si.prim_index)[0]) == index
    inside = mi.Ray3f(mi.Point3f(0., 0., .5), mi.Vector3f(0., 1., 0.))
    assert not bool(np.asarray(scene.ray_test(inside))[0])
    cube = mi.load_dict({"type": "scene", "boundary": {"type": "cube"}})
    cube_ray = mi.Ray3f(mi.Point3f(0., 0., 0.), mi.Vector3f(0., 1., 0.))
    assert bool(np.asarray(cube.ray_test(cube_ray))[0])
    assert max(radius_errors) < 1e-6
    assert max(uv_errors) < 1e-6
    print(mi.__version__, mi.variant(), max(radius_errors), max(uv_errors))
```

## Primary sources

[S1]: https://github.com/mitsuba-renderer/mitsuba3/blob/478e193a183c21723f4a8251afc3ad29a8da4c5e/src/bsdfs/hair.cpp
[S2]: https://github.com/mitsuba-renderer/mitsuba3/blob/478e193a183c21723f4a8251afc3ad29a8da4c5e/src/shapes/bsplinecurve.cpp
[S3]: https://github.com/mitsuba-renderer/mitsuba3/blob/478e193a183c21723f4a8251afc3ad29a8da4c5e/src/media/homogeneous.cpp
[S4]: https://github.com/mitsuba-renderer/mitsuba3/blob/478e193a183c21723f4a8251afc3ad29a8da4c5e/src/bsdfs/dielectric.cpp
[D1]: https://mitsuba.readthedocs.io/en/v3.9.1/src/generated/plugins_shapes.html#b-spline-curve-bsplinecurve
[D2]: https://mitsuba.readthedocs.io/en/v3.9.1/src/generated/plugins_media.html#homogeneous-medium-homogeneous
[D3]: https://mitsuba.readthedocs.io/en/v3.9.1/src/generated/plugins_bsdfs.html#smooth-dielectric-material-dielectric
[D4]: https://mitsuba.readthedocs.io/en/v3.9.1/src/generated/plugins_integrators.html#volumetric-path-tracer-volpath
[P1]: https://www.pbr-book.org/4ed/Reflection_Models/Scattering_from_Hair

- [Mitsuba pinned `hair.cpp`][S1].
- [Mitsuba pinned `bsplinecurve.cpp`][S2].
- [Mitsuba pinned `homogeneous.cpp`][S3].
- [Mitsuba pinned `dielectric.cpp`][S4].
- [Mitsuba 3.9.1 shapes][D1], [media][D2], [BSDF][D3], [integrator][D4] documentation.
- Pharr, Jakob, Humphreys, *Physically Based Rendering*, 4th ed., [Scattering from Hair][P1].
