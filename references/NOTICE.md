# Source audit reference

`Mitsuba_hair.cpp` is the unmodified third-party file
`src/bsdfs/hair.cpp` from Mitsuba tag `v3.9.1`:

https://raw.githubusercontent.com/mitsuba-renderer/mitsuba3/v3.9.1/src/bsdfs/hair.cpp

It is included solely to reproduce the source-level absorption-unit check in
`validate_render.py`. The file is not an original implementation by this project.
Its original BSD-style copyright notice, conditions, and disclaimer are provided
in `Mitsuba_LICENSE.txt`, obtained from the same tagged repository.

Recorded source SHA-256:
`0ce061635989dfbb12b85b3c9f14851e858ca297ed71e8df86599b0c97a4791e`.

No other downloaded paper, third-party implementation, or learned checkpoint is
distributed in the research bundle. The simulation code imports separately
installed numerical and rendering libraries under their own licenses.
