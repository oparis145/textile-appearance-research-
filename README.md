# Textile Optical Simulation Lab — 실행 결과 v1

**섬유의 전자기 산란 → 섬유 묶음의 광선 수송 → 실·직조 기하 → 원단 영상 → 카메라 측정**을 실제로 계산한 연구 프로토타입입니다. 염색·퇴색은 이번 범위에서 제외했습니다. 수치 데이터, 실행 코드, 단위·가정, 독립 검산, 실패 및 수정 기록을 함께 제공합니다.

먼저 `report/textile_optical_simulation_report_ko.pdf`를 읽고, 모듈별 수식과 세부 검증은 `notes/`를 참고하세요. 그림은 생성형 이미지가 아니라 저장된 수치 결과에서 만든 플롯 또는 실제 path-tracing 출력입니다.

## 구현하고 실행한 범위

| 모듈 | 계산한 내용 | 연결 및 한계 |
|---|---|---|
| `fiber_wave.py` | 원형 무한 원통의 Maxwell 해, 다중 원통 T-matrix, 편광·흡수·근접장·원거리장 | 2D 평행 섬유 기준해; 원단 전체 3D Maxwell은 아님 |
| `fiber_wave_beam.py` | 위상과 전력을 보존하는 Gaussian beam의 coherent angular spectrum, 빔 위치 변화 | 유한 입사 전력으로 후방 R·흡수 A 계산; 전방 T에는 간섭이 포함됨 |
| `ply_ray.py` | 정확한 원 교차, Fresnel 반사·굴절, 내부 및 섬유 사이 다중 경로, Beer 감쇠 | 1/7/19개 섬유 묶음; 독립 Debye 경로 적분과 비교 |
| `angular_surrogate.py` | 비음수 von Mises 혼합으로 각도 분포 압축, 독립 seed 검증 | 2D 진단용 압축; 논문의 3D ASG BSDF를 재현한 것은 아님 |
| `geometry.py` | 섬유 → ply → yarn → 평직/2:2 능직/5-end 수자직 | 기하 생성; 섬유 역학·접촉력 해석은 아님 |
| `render.py` | 실제 3D 섬유 곡선 + Chiang2016 BCSDF + Mitsuba3 다중 산란 | 파동 기준해와 별도의 광선 기반 3D baseline |
| `aperture_wave.py` | 유한 틈새 마스크 Fraunhofer 회절, Gaussian beam, 광원·파장 평균 | 직접 공극 투과 성분만; 전체 원단 BTDF와 중복 합산하지 않음 |
| `camera.py` | 원형 pupil MTF, 픽셀 면적 적분, Poisson/read noise, 포화 | object-referred sampling, 지정한 검출 광자 예산 |
| `meta_optics.py` | 이상적 위상 pupil, Fresnel 전파, PSF·ROI·측정행렬 rank | 소자 Maxwell/Jones 모델이나 제작 효율 검증은 아님 |
| `angular_measurement.py` | 실제 Gaussian 파동/ray 분포의 1/6/18/90 각도 채널, Poisson KL·gain profiling·독립 계수 실험 | 두 고정 합성 모형을 구분하는 이상적 검출 실험; 재질 분류나 사람 지각이 아님 |

공통된 물리 파라미터를 사용하되, **2D 파동 결과를 3D 원단 BSDF로 변환하는 검증되지 않은 단계를 숨겨 연결하지 않았습니다.** 실제 연결은 `geometry → render → camera`와 `geometry → binary gap visibility → aperture diffraction`이며, 파동/광선 비교·분포 압축·메타광학 측정행렬은 별도로 검증됩니다. 메타광학 측정행렬과 직물 역문제는 아직 통합되지 않았습니다.

모든 굴절률·고정 흡수 계수는 통제된 합성 입력입니다. 실크·코튼·큐프라·린넨 등 특정 원단의 실측 파라미터로 주장하지 않습니다. 원단 영상의 입자는 유한 path-tracing 표본의 Monte Carlo 잡음을 포함하며, 파동 speckle을 추가한 결과가 아닙니다.

## 환경과 실행

실행 환경: Python 3.12.14, NumPy 2.3.5, SciPy 1.17.0, Mitsuba 3.9.1 / Dr.Jit 1.5.0, LLVM CPU. GPU는 필요하지 않았습니다. 운영체제·BLAS·컴파일러 차이 때문에 부동소수점 결과가 비트 단위로 같다는 보장은 없습니다. `data/environment.json`에 실제 버전을 기록했습니다.

```bash
cd textile_lab
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

# 모든 모듈의 단위·물리 검증
python run_all.py --stages tests

# 실행 명령만 확인
python run_all.py --dry-run

# 전체 실험을 순서대로 다시 실행
python run_all.py
```

`run_all.py`는 각 단계의 stdout/stderr, 시간, 종료 코드를 `data/reproduction_logs/`에 저장합니다. 기존 모듈 결과 파일은 다시 계산한 값으로 갱신됩니다. 원본 결과를 보존하려면 별도 폴더에 압축을 풀어 실행하세요. 렌더러의 원본 코드 단위 검토에 맞춰 Mitsuba 버전을 고정했습니다.

### 필요한 단계만 실행

```bash
# Maxwell 단일 섬유/작은 묶음 + 광선 기준 + 같은 기하 파동/광선 비교
python run_all.py --stages wave ray match beam

# 저장된 beam 분포에 각도 검출·광자 통계를 적용
python run_all.py --stages measurement

# 광선 각도 분포를 1/4/8/16개 비음수 lobe로 압축
python run_all.py --stages surrogate

# 틈새 회절 및 이상적인 외부 위상 pupil
python run_all.py --stages aperture meta

# 3개 직조의 섬유 기하, 9개 반사/역광 영상, 확대 영상, 카메라 비교
python run_all.py --stages fabric

# white furnace, 경로 깊이, 광원 선형성, spp 수렴, 카메라 독립 검산
python run_all.py --stages render-checks

# 빠른 실행 점검용; 배포된 기준 렌더의 품질과 다름
python run_all.py --stages fabric --quick-fabric
```

수치 행렬·ray 기준 실험은 CPU에서 실행됩니다. 기본 원단 영상은 256×256, 192 samples/pixel, macro는 512×512, 256 samples/pixel입니다. 경로 깊이는 무제한(`max_depth=-1`)이고 Russian roulette를 사용합니다. 시간을 줄이기 위해 경로 깊이를 낮추면 다중 산란 에너지가 크게 손실되므로 품질 설정으로 취급하지 마세요. 계산 시간은 장비에 따라 달라집니다.

## 주요 결과를 확인할 파일

| 파일 | 내용 |
|---|---|
| `data/fiber_wave_metrics.json` | 단일/다중 원통 정확도, 수렴, 에너지·흡수 검산 |
| `data/fiber_wave_textile_matched_metrics.json` | 반지름 5 μm × 7개 섬유의 같은 기하 파동/광선 비교 |
| `data/fiber_wave_gaussian_beam_metrics.json` | Gaussian beam 위치별 실제 파동/광선 R, 각도 오차 |
| `data/ply_ray_summary.json` | 1/7/19개 묶음 전력 분해와 ray Monte Carlo 수렴 |
| `data/ply_ray_surrogate_metrics.json` | 독립 검증 분포에 대한 압축 오차와 최적화 종료 상태 |
| `data/fabric_metrics.json` | 기하 분리 인증, 9개 렌더, 가시 공극, 회절, 카메라 조건 |
| `figures/fabric_contact_sheet.png` | 동일 파라미터로 계산한 평직·능직·수자직 비교 |
| `figures/camera_comparison.png` | 같은 입력 원단에 대한 NA·픽셀·잡음 비교 |
| `data/render_validation_metrics.json` | furnace, 경로 깊이, 광원·sampling 검산 |
| `data/meta_metrics.json` | 실제 위상 전파로 얻은 H, rank, 포집 광량, 수렴 |
| `data/meta_symmetry_ablation.png` | 네 초점의 대칭 여부가 독립 채널 수에 주는 영향 |
| `data/final_test_summary.json` | 최종 통합 테스트 결과 |
| `data/angular_measurement_metrics.json` | 유한 각도 채널·Poisson count에서 남는 두 모델의 차이 |
| `notes/` | 수식, 인터페이스, 문헌 검토, 독립 리뷰, 한계 |

`*.npz`, `*_linear.npy`에는 표시용 sRGB 변환 이전 배열이 들어 있습니다. 정량 비교는 PNG 밝기가 아니라 선형 배열과 JSON을 사용해야 합니다. JSON의 `mean_linear`는 정해진 광원 하의 카메라 평균 radiance이며 반구 반사율/투과율이 아닙니다.

## 측정 및 물리량 계약

1. 2D 파동·ray 길이는 μm, 원단 기하는 mm입니다. 파동 계산의 산란 단면적은 축 길이당 단면적으로 단위가 μm이며 반사 확률이 아닙니다.
2. 파동은 `exp(-iωt)`, outgoing Hankel1, 수동 매질 `n+iκ`를 사용합니다. `Ez`/`Hz`로 편광을 명시합니다.
3. 서로 비간섭인 광원·파장은 강도를 더합니다. Gaussian beam 내부 angular spectrum은 복소 진폭을 합쳐 coherent field를 만듭니다.
4. 직접 투과, 산란, 회절을 각각 독립 에너지로 더하지 않습니다. 현재 회절 결과는 렌더 영상에 합성하지 않은 진단입니다.
5. 카메라의 μm/pixel은 물체면 환산값입니다. NA sweep은 검출 전자 수/물체면 면적을 같게 둡니다. 실제 고정 노출에서 NA에 따른 수집 광량 변화·배율·QE는 자동 적용하지 않습니다.
6. 카메라 `radiance_noise_variance`는 포화 전 Poisson+read 분산입니다. `noiseless`는 추가 검출기 잡음이 없다는 뜻이고, 입력 path-tracing 잡음은 남습니다. 입출력 Nyquist를 별도로 보고합니다.
7. 메타광학의 η=0.8은 가정값입니다. 4×9 행렬의 rank=4여도 임의의 9개 성분을 유일하게 복원할 수 없습니다. 광학 power를 전자 수로 변환하려면 파장별 QE와 λ/(hc)를 포함해야 합니다.

## 문헌과 공개 코드

- Yu, Walter, Marschner, Weidlich (2025), *Realistic Cloth Rendering with a Ray-Wave Hybrid Shading Model*, DOI [10.1145/3763359](https://doi.org/10.1145/3763359). 논문 핵심 방법을 검토했습니다. 공식 프로젝트에서 논문/보충자료를 확인했으며 공개된 전체 구현은 확인하지 못했습니다. 본 프로젝트는 전체 논문 재현이 아닙니다.
- Xia et al. (2020), [A Wave Optics Based Fiber Scattering Model](https://mandyxia.com/research/wavefiber.html), [WaveOpticsFiber](https://github.com/mandyxmq/WaveOpticsFiber). BEM 방법·저장소를 검토했고, 여기서는 독립적으로 검산 가능한 원형 다중 원통 해를 구현했습니다. 원 저장소는 빌드·실행하지 않았습니다.
- Chiang et al. (2016), [A Practical and Controllable Hair and Fur Model for Production Path Tracing](https://www.disneyanimation.com/publications/a-practical-and-controllable-hair-and-fur-model-for-production-path-tracing/). Mitsuba 3.9.1의 이 모델을 실제 3D fiber path tracing에 사용했습니다.
- Tang et al. (2024), [Woven Fabric Capture with a Reflection-Transmission Photo Pair](https://wangningbei.github.io/2024/FabricBTDF.html), [공개 코드](https://github.com/lxtyin/FabricBTDF-Recovery). coarse reflection/transmission·역추정 비교군으로 검토했습니다. 학습/복원은 실행하지 않았습니다.
- [MetaSpectra+](https://meta-imaging.qiguo.org/), [공개 코드](https://github.com/guo-research-group/MetaSpectra-plus). 실제 다층 메타광학과 단순 다초점 pupil의 차이를 검토했습니다. 논문의 소자/학습을 재현하지 않았습니다.

상세 문헌·접근 범위는 `notes/ray_wave_literature.md`, `notes/meta_optics.md`에 있습니다. 타인의 논문 PDF, 체크포인트와 설치된 외부 패키지는 이 배포 묶음에 포함하지 않습니다. 단위 감사를 재현하는 데 필요한 Mitsuba v3.9.1의 hair.cpp 원문 한 파일은 references/에 원래 라이선스와 함께 제공합니다. 이 파일은 원 저자의 코드이며 자체 구현으로 주장하지 않습니다. 나머지 Python 시뮬레이션 구현은 이 작업에서 작성했고 외부 라이브러리는 각자의 라이선스에 따라 별도로 설치합니다.
