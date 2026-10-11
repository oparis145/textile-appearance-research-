"""Plot saved v2 geometry. These are geometry diagnostics, not optical renders.

Run from the repository root after the hierarchy CLI examples:
    python examples/hierarchy/plot_geometry_diagnostics.py
"""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import numpy as np

from textile_sim.hierarchy import (
    FabricSpec, YarnSpec, build_yarn, load_hierarchy, hex_ply,
)


OUTPUT = ROOT/"figures"/"hierarchy_v2"
OUTPUT.mkdir(parents=True, exist_ok=True)
COLORS = {"warp": "#236caa", "weft": "#d47b30"}


def wire_plot(ax, geometry, *, along_z=False, crop=False, by_ply=False):
    for fiber in geometry.fiber_records:
        p = fiber.points_mm.copy()
        if crop:
            width, height = geometry.metadata["visible_size_mm"]
            outside = (np.abs(p[:, 0]) > width/2) | (np.abs(p[:, 1]) > height/2)
            p[outside] = np.nan
        color = (plt.cm.Set2(fiber.ply_index % 8) if by_ply
                 else COLORS.get(fiber.family, "#236caa"))
        if along_z:
            ax.plot(p[:, 2], p[:, 0], p[:, 1], color=color, linewidth=.65, alpha=.82)
        else:
            ax.plot(p[:, 0], p[:, 1], p[:, 2], color=color, linewidth=.55, alpha=.82)
    bounds = geometry.bounds_mm
    if along_z:
        ax.set_xlabel("parent axial z [mm]", labelpad=1)
        ax.set_ylabel("x [mm]", labelpad=1)
        ax.set_zlabel("y [mm]", labelpad=1)
        ax.set_box_aspect((3.2, 1, 1), zoom=.80)
        ax.view_init(18, -60)
    else:
        if crop:
            width, height = geometry.metadata["visible_size_mm"]
            ax.set_xlim(-width/2, width/2)
            ax.set_ylim(-height/2, height/2)
        ax.set_zlim(bounds[0, 2]*1.1, bounds[1, 2]*1.1)
        ax.set_xlabel("x [mm]", labelpad=1)
        ax.set_ylabel("y [mm]", labelpad=1)
        ax.set_zlabel("z [mm]", labelpad=1)
        ax.set_box_aspect((1.2, 1, .35), zoom=.82)
        ax.view_init(37, -52)
    ax.xaxis.set_major_locator(MaxNLocator(3))
    ax.yaxis.set_major_locator(MaxNLocator(3))
    ax.zaxis.set_major_locator(MaxNLocator(3))
    ax.tick_params(labelsize=7, pad=0)
    ax.grid(alpha=.18)


def main():
    plt.rcParams.update({"font.size": 9, "axes.titlesize": 11,
                         "figure.facecolor": "white", "savefig.facecolor": "white"})
    cases = ("plain_single_ply", "twill_two_ply", "basket_rectangular_three_ply")
    titles = ("Plain | 1 ply, 19 fibers/yarn", "2/2 twill | 2 plies, 14 fibers/yarn",
              "4 x 6 basket draft | 3 plies, 21 fibers/yarn")
    fig = plt.figure(figsize=(14.8, 8.2))
    grid = fig.add_gridspec(2, 3, height_ratios=(.75, 1.35), left=.06, right=.93,
                           bottom=.08, top=.85, hspace=.28, wspace=.30)
    for i, (name, title) in enumerate(zip(cases, titles)):
        spec = FabricSpec.from_dict(json.loads((ROOT/"examples"/"hierarchy"/(name+".json")).read_text()))
        geometry = load_hierarchy(ROOT/"data"/"hierarchy_v2"/name)
        ax = fig.add_subplot(grid[0, i])
        ax.imshow(spec.draft.as_array(), cmap="Blues", interpolation="nearest", vmin=0, vmax=1)
        ax.set_xticks(range(spec.draft.warp_repeat)); ax.set_yticks(range(spec.draft.weft_repeat))
        ax.set_xlabel("warp column"); ax.set_ylabel("weft row")
        ax.set_title(title, pad=12)
        for r in range(spec.draft.weft_repeat):
            for c in range(spec.draft.warp_repeat):
                val = spec.draft.matrix[r][c]
                ax.text(c, r, str(val), ha="center", va="center", color="white" if val else "#17354d")
        ax = fig.add_subplot(grid[1, i], projection="3d")
        wire_plot(ax, geometry, crop=True)
        ax.set_title(f"{len(geometry.fiber_records)} explicit circular fibers", pad=1)
    fig.suptitle("Topology to explicit geometry | 1 means warp over weft\n"
                 "Diagnostic centerlines; aspect adjusted; blue warp / orange weft; no measured material colors", fontsize=14, y=.98)
    fig.savefig(OUTPUT/"topology_to_fibers.png", dpi=190)
    plt.close(fig)

    spec = FabricSpec.from_dict(json.loads((ROOT/"examples"/"hierarchy"/"basket_rectangular_three_ply.json").read_text()))
    z = np.linspace(0, .7, 501)
    center = np.column_stack((np.zeros_like(z), np.zeros_like(z), z))
    solo = YarnSpec("fiber", (hex_ply(rings=0, radius_mm=.002, fiber_twist_per_mm=0),))
    ply = YarnSpec("ply", (hex_ply(rings=1, spacing_mm=.0065, radius_mm=.002, fiber_twist_per_mm=-2.3),))
    levels = [build_yarn(solo, center, initial_normal=(1, 0, 0)),
              build_yarn(ply, center, initial_normal=(1, 0, 0)),
              build_yarn(spec.warp_yarn, center, initial_normal=(1, 0, 0)),
              load_hierarchy(ROOT/"data"/"hierarchy_v2"/"basket_rectangular_three_ply")]
    fig = plt.figure(figsize=(15, 4.2))
    fig.subplots_adjust(left=.02, right=.93, bottom=.07, top=.77, wspace=.20)
    titles = ("Fiber\nconstant circular radius", "Ply\n7 fibers, -2.3 turns/mm",
              "Yarn\n3 plies, +1.1 turns/mm", "Weave\nrectangular crossing draft")
    for i, (geometry, title) in enumerate(zip(levels, titles)):
        ax = fig.add_subplot(1, 4, i+1, projection="3d")
        wire_plot(ax, geometry, along_z=i < 3, crop=i == 3, by_ply=i < 3)
        ax.set_title(title)
    fig.suptitle("Nested parent frames and parent-arclength twists | centerlines, axes aspect adjusted", fontsize=13, y=.98)
    fig.savefig(OUTPUT/"hierarchy_levels.png", dpi=190)
    plt.close(fig)

    path = ROOT/"data"/"hierarchy_v2"/"sampling_refinement_metrics.json"
    if path.exists():
        results = json.loads(path.read_text())
        fig, axes = plt.subplots(1, 3, figsize=(13, 4))
        fig.subplots_adjust(left=.07, right=.985, bottom=.20, top=.78, wspace=.32)
        for i, (name, result) in enumerate(results.items()):
            comparisons = result["comparisons"]
            x = [c["coarse_factor"] for c in comparisons]
            values = [[c["max_parameter_matched_centerline_distance_mm"]*1000 for c in comparisons],
                      [abs(c["relative_total_length_change"]) for c in comparisons],
                      [c["tangent_tensor_frobenius_change"] for c in comparisons]]
            label = name.replace("_", " ")
            for ax, y in zip(axes, values):
                ax.semilogy(x, y, "o-", label=label, color=plt.cm.tab10(i))
                ax.set_xticks([1, 2], ["1 to 2", "2 to 4"])
                ax.set_xlabel("sampling factor comparison")
                ax.grid(alpha=.25, which="both")
        for ax, title, unit in zip(axes, ("Matched centerline distance", "Total fiber length change", "Tangent tensor change"),
                                    ("maximum [micrometers]", "relative magnitude", "Frobenius norm")):
            ax.set_title(title); ax.set_ylabel(unit)
        axes[0].legend(fontsize=7, loc="lower left")
        fig.suptitle("Complete hierarchy refinement | observed differences, not error bounds to an uncomputed continuum", fontsize=12, y=.98)
        fig.savefig(OUTPUT/"sampling_refinement.png", dpi=190)
        plt.close(fig)
    print(f"Saved geometry diagnostics in {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
