# 사용자 제공 논문 원본

두 논문은 2026-10-11 사용자가 이 연구를 위해 제공했다. 원본 파일을 수정하지 않았으며, 정확한 바이트 수와 SHA-256은 [PROVENANCE.json](PROVENANCE.json)에 기록했다. 저작권은 원저자·출판사에 있다. 이 저장소와 첨부 자산은 사용자가 요청한 비공개 연구 공간이다.

| 파일 | 보존 위치 | 읽은 범위 |
| --- | --- | --- |
| [FabricGen CVPR 2026](Tang_FabricGen_Microstructure-Aware_Woven_Fabric_Generation_CVPR_2026_paper.pdf) | 이 디렉터리의 Git 파일 | 제공된 10쪽 본문 전체 |
| `2406.19398v3.pdf` | [비공개 v0.2.0 release의 PDF asset](https://github.com/Phill-lms/textile-optics-engine/releases/download/v0.2.0/2406.19398v3.pdf) | 제공된 13쪽 본문·보충 전체 |

두 번째 파일은 47,640,125 bytes로 웹 Git 파일 업로드 한도보다 커서 Release asset으로 보존한다. 저장소의 **Releases → v0.2.0 → Assets**에서 다운로드할 수 있다. Git clone에는 이 asset의 메타데이터가 들어 있고 PDF 자체는 포함되지 않는다. 엔진 실행에는 논문 PDF가 필요하지 않다.

논문·공식 코드·후속 연구별로 무엇을 읽고 구현했는지는 [문헌 검토](../../notes/literature_engine_v2.md)에 정리했다. 논문 제목이나 저장소를 확인한 것과 방법 전체를 재현한 것을 구분한다.

GitHub가 반환한 asset digest와 로컬 원본 SHA-256이 일치함을 확인했다. [배포 검증 기록](../../data/repository_release_audit.json).

## 추가 figure 참고 이미지 — 2026-10-12 KST

사용자가 다시 첨부한 [Figure 5 이미지](fabricgen_figure5_reference.png)는 FabricGen의 **3-ply basket weave normal·orientation·height map**이다. 원본 바이트는 수정하지 않고 [별도 provenance](figure5_reference_provenance.json)에 해시·출처·용도를 기록했다. 새 구조맵의 표현 형식과 정의를 참고하며, 이 그림의 픽셀을 우리 엔진의 기하·측정값·검증 자료로 사용하지 않는다. 새 그림은 생성한 3D 표면과 명시한 camera에서 별도로 계산한다.
