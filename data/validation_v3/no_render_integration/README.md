# v3 통합 실행의 기록 발췌

이 폴더는 새 역학 계산 → 새 광학 export·SGGX 계산 → 새 결과 검증을 실제로
실행한 기록이다. **원래 실행 폴더의 완전한 복사본은 아니다.**

- `run_manifest.json`, `logs/`, `verification/artifact_verification.json`은 원본을
  바이트 그대로 복사했다. 원래 경로와 SHA-256을 수정하지 않았다.
- `summary.json`만 이 기록의 범위와 결과를 정리한 새 문서다.
- 원래 생성된 기하·광학 scene·curve·SGGX 배열·그림은 이 폴더로 복사하지
  않았다. manifest의 경로는 원래 scratch 실행을 가리키며, 이 폴더 안에 모든
  파일이 존재한다는 뜻이 아니다.
- 검사 시 모델 source가 바뀌지 않았음은 원본 manifest에 기록되어 있다.
  원본 실행 당시 runner SHA는 `summary.json`에 보존했다. 그 실행 후 runner에
  출력 경로가 재사용 입력 폴더와 겹치는 경우를 거절하는 보호 검사를 추가했다.
  이후의 전체 source 상태 검증은 별도의 최종 verification 실행으로 기록한다.

## 실제 수행한 명령

실행한 working directory는 저장소 바깥인
`/workspace/scratch/2b957533e88d`였다.

```bash
python /workspace/scratch/2b957533e88d/textile_optics_engine/run_engine_v3.py \
  --stages mechanics optics verify \
  --no-render \
  --output /workspace/scratch/2b957533e88d/textile_optics_engine/tmp/runner_v3_full_no_render
```

| 단계 | 결과 | 경과 시간 |
|---|---|---:|
| mechanics | 새 역학 시편·sweep·refinement·benchmark 생성, 통과 | 25.31 s |
| optics | 생성된 역학 기하를 입력으로 새 export·투영면적 fitting, 통과 | 3.69 s |
| verify | 생성된 기하·KKT·간격·투영면적 재검사, 통과 | 2.60 s |

**이 실행이 수행한 explicit-fiber render는 0개**다. 광학 metrics의
`render_status`는 `not_requested`다. 536개 렌더 결과의 원래 기록이나
그 결과의 별도 verification과 합산하지 않는다.

## 다시 실행하려면

의존성이 설치된 저장소에서 아직 존재하지 않는 출력 경로를 선택한다.

```bash
python run_engine_v3.py --stages mechanics optics verify --no-render \
  --output data/engine_v3_runs/new_no_render_run
```

이 명령은 실제로 새 계산을 수행하고, 그 결과 전체를 지정한 새 폴더에 쓴다.
본 발췌 폴더를 `--input-data`로 사용하면 필요한 원래 배열이 없으므로 안 된다.
