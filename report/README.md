# Korean technical reports

The PDFs are complete, standalone deliverables. The v0.3 generator reads the
committed experiment JSON, plots and final test summary; it does not rerun the
scientific simulations or change their results.

## Rebuild v0.3

Use the pinned scientific requirements in `../requirements.txt`, plus
`reportlab==4.4.9` (the version used for this report). Provide Korean TrueType
fonts named `NotoSansKR-400.ttf` and `NotoSansKR-700.ttf` through the
`TEXTILE_REPORT_FONT_DIR` environment variable. These external fonts are not
part of the simulation engine and are not bundled in this repository.

```bash
python -m pip install reportlab==4.4.9
TEXTILE_REPORT_FONT_DIR=/absolute/path/to/fonts python report/build_engine_v3_report.py
```

The command is run from the repository root and writes
`report/fabric_engine_v3_report_ko.pdf`. All scientific values are loaded from
the checked-in evidence. The supplied final PDF uses 22 pages and records the
239-test passing snapshot.

## Font identity used in the supplied report

The Noto Sans KR font metadata identifies version
`2.004-H2;hotconv 1.0.118;makeotfexe 2.5.65603`, with SIL Open Font License 1.1
notice. Font copyright and license are retained in its embedded metadata;
see https://scripts.sil.org/OFL for that license. A different font version or
build of the font may change layout or binary PDF identity.

| Font file | Bytes | SHA-256 |
| --- | ---: | --- |
| NotoSansKR-400.ttf | 6,224,884 | `a255867e14555fa214fa082f42383805aad8311e15b47fc5481ddd35836a2c27` |
| NotoSansKR-700.ttf | 6,222,760 | `edf7200a9f1d9df2fa8f7ead07be7eac586959e6a612a5f647491e413c47a6d3` |

All 22 pages of the supplied PDF were rendered and visually reviewed. Text
bounds and glyph checks reported no issues. Historical v0.1 and v0.2 PDFs and
their generators are retained; the v0.3 report does not overwrite them.
