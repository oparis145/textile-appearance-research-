#!/usr/bin/env python3
"""Execute v2 geometry-to-optics experiments; all constants are synthetic.

No training data or external repository code is downloaded.  This driver builds
actual v2 yarn/fabric geometry, exports versioned optical scenes, runs the
existing wave/ray solvers and performs real Mitsuba renders when requested.
"""
from __future__ import annotations
from dataclasses import replace
from pathlib import Path
import argparse
import json
import time
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from textile_sim.hierarchy import (YarnSpec, hex_ply, build_yarn, build_hierarchy,
                                  FabricSpec, save_hierarchy, audit_clearance)
from textile_sim.weave_draft import WeaveDraft
from textile_sim.optical_scene import (MaterialSpectrum, OpticalScene, OpticalFiber,
    from_hierarchy, export_mitsuba, extract_bundle_section, BundleTolerance,
    wave_inputs, ray_inputs, microstructure_statistics, render_optical_scene)
from textile_sim.fiber_wave import cluster_scattering
from textile_sim.ply_ray import trace_bundle
from textile_sim.render import RenderConfig, encode_srgb


def _write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def synthetic_materials():
    return (MaterialSpectrum.from_absorption("synthetic_A", (450,550,650),
                (1.50,1.51,1.52), (2.,4.,6.),
                "Controlled synthetic dielectric A; not a named textile measurement"),
            MaterialSpectrum.from_absorption("synthetic_B", (450,550,650),
                (1.63,1.62,1.61), (12.,8.,4.),
                "Controlled synthetic dielectric B; not a named textile measurement"))


def run_experiments(output="data/optical_bridge_v2", *, run_render=True, resolution=128, spp=64):
    out=Path(output)
    out.mkdir(parents=True,exist_ok=True)
    started=time.perf_counter()
    mats=synthetic_materials()
    mats_id=tuple(m.material_id for m in mats)
    metrics={"experiment":"versioned hierarchy-to-optics bridge",
        "date_utc":"2026-10-11", "material_status":"synthetic; not silk/cotton/linen measurements",
        "source_paper":"Tang et al. 2024, arXiv:2406.19398v3 (scope/reference, not reproduction)",
        "assumptions":["dyeing/fading absent", "circular fibers and explicit assigned materials",
            "ray/Fresnel and Mitsuba hair use real index with Beer absorption",
            "2D Maxwell is only evaluated for explicitly accepted local parallel bundles"]}

    # 1. Actual generated straight mixed-material yarn -> both existing solvers.
    yarn=YarnSpec("calibration",(hex_ply(id="p0",rings=1,spacing_mm=.012,
        radius_mm=.004,material_ids=mats_id,fiber_twist_per_mm=0),))
    z=np.linspace(-.15,.15,61)
    centerline=np.column_stack((0*z,0*z,z))
    calibration_geometry=build_yarn(yarn,centerline,seed=801)
    calibration=from_hierarchy(calibration_geometry,mats)
    calibration.save(out/"calibration_scene.json")
    section=extract_bundle_section(calibration,[0,0,0],[0,0,1])
    if not section.eligible:
        raise RuntimeError("straight generated calibration failed the exact slice contract")
    _write(out/"calibration_section.json",section.diagnostics)
    metrics["calibration_geometry"]=calibration_geometry.summary()
    theta=-np.pi+2*np.pi*(np.arange(1440)+.5)/1440
    backward=np.cos(theta)<0
    arrays={"theta_rad":theta,"centers_mm":section.centers_mm,"radii_mm":section.radii_mm}
    optical_rows=[]
    for lam in (450,550,650):
        for pol in ("Ez","Hz"):
            wave=cluster_scattering(**wave_inputs(section,calibration,lam),polarization=pol,theta=theta)
            ray=trace_bundle(**ray_inputs(section,calibration,lam),n_rays=50000,seed=lam+(0 if pol=="Ez" else 1),
                             polarization=pol,theta_bins=180)
            key=f"{lam}_{pol}"
            arrays[key+"_wave_dcs_um_per_rad"]=wave["dCsca_dtheta"]
            arrays[key+"_ray_theta_rad"]=ray["theta_rad"]
            arrays[key+"_ray_encountered_escaped_density_per_rad"]=ray["angular_power_per_rad"]["encountered_escaped"]
            row={"wavelength_nm_vacuum":lam,"polarization":pol,
                "wave_Csca_um":wave["Csca"],"wave_Cabs_um":wave["Cabs"],
                "wave_Cback_um":float(np.sum(wave["dCsca_dtheta"][backward])*(2*np.pi/len(theta))),
                "wave_relative_flux_residual":wave["relative_energy_flux_residual"],
                "wave_linear_system_residual":wave["linear_system_residual"],
                "ray_energy":ray["energy"],"ray_n_rays":50000,
                "fiber_material_counts":{mid:section.material_ids.count(mid) for mid in mats_id}}
            optical_rows.append(row)
    metrics["calibration_solver_runs"]=optical_rows

    # 2. Known local cylinder slice: analytic ellipse validity, without pretending
    # an oblique slice can be passed to a circular T-matrix.
    oblique=[]
    for tilt in (0.,.04,.2,1.,5.,15.,30.,60.):
        a=np.deg2rad(tilt)
        q=np.array([[np.cos(a),0,np.sin(a)],[0,1,0],[-np.sin(a),0,np.cos(a)]])
        rotated=OpticalScene(calibration.materials,
            tuple(replace(f,points_mm=f.points_mm@q.T) for f in calibration.fibers))
        strict=extract_bundle_section(rotated,[0,0,0],[0,0,1])
        local=extract_bundle_section(rotated,[0,0,0],[0,0,1],
            tolerance=BundleTolerance(mode="local_parallel",max_tilt_deg=.1))
        rows=strict.diagnostics["rows"]
        oblique.append({"tilt_deg":tilt,"strict_eligible":strict.eligible,
                        "local_eligible":local.eligible,
                        "measured_ellipse_area_ratio":rows[0]["ellipse_area_ratio_vs_circle"],
                        "analytic_ellipse_area_ratio":1/np.cos(a)})
    metrics["oblique_slice_sweep"]=oblique

    # 3. A twisted generated yarn cannot be silently treated as an exact 2D bundle.
    twisted=[]
    for rate in (0.,.1,.5,1.,2.):
        ply=replace(yarn.plies[0],fiber_twist_per_mm=rate)
        g=build_yarn(replace(yarn,plies=(ply,)),centerline,seed=801)
        s=from_hierarchy(g,mats)
        sec=extract_bundle_section(s,[0,0,0],[0,0,1])
        rows=sec.diagnostics["rows"]
        twisted.append({"fiber_twist_per_mm":rate,"strict_eligible":sec.eligible,
            "max_tilt_deg":max(r.get("tilt_deg",0) for r in rows),
            "max_tangent_change_deg":max(r.get("max_tangent_change_deg",0) for r in rows),
            "max_centerline_deviation_mm":max(r.get("max_centerline_deviation_mm",0) for r in rows)})
    metrics["twisted_yarn_slice_sweep"]=twisted

    # 4. Actual nested mixed-material two-ply yarns -> rectangular fabric ->
    # wavelength-dependent per-radius hair groups -> reflected/transmitted image.
    def make_yarn(name,radius):
        return YarnSpec(name,tuple(hex_ply(id=f"p{j}",rings=1,spacing_mm=.012,
            radius_mm=radius,material_ids=mats_id,offset_mm=(sign*.022,0),
            fiber_twist_per_mm=1.1*sign) for j,sign in enumerate((-1,1))),
            ply_twist_per_mm=.45)
    spec=FabricSpec(WeaveDraft.twill(2,2),make_yarn("warp",.003),make_yarn("weft",.004),
        warp_count=3,weft_count=4,warp_pitch_mm=.2,weft_pitch_mm=.18,
        samples_per_crossing=28,max_segment_mm=.006,max_turn_radians=.1,seed=803)
    geometry=build_hierarchy(spec)
    save_hierarchy(out/"fabric_geometry",geometry)
    scene=from_hierarchy(geometry,mats)
    scene.save(out/"fabric_scene.json")
    stats=microstructure_statistics(scene)
    _write(out/"fabric_microstructure.json",stats)
    audit=audit_clearance(geometry,probe_margin_mm=.002,max_candidate_pairs=8_000_000)
    if not audit["certified_separated"]:
        raise RuntimeError("generated fabric failed its different-fiber polyline clearance audit")
    _write(out/"fabric_polyline_clearance.json",audit)
    metrics["fabric_geometry"]=geometry.summary()
    metrics["fabric_polyline_clearance"]=audit
    rendered=[]
    exports=[]
    figure,axs=plt.subplots(2,2,figsize=(8,8)) if run_render else (None,None)
    for li,lam in enumerate((450,650)):
        directory=out/f"mitsuba_{lam}nm"
        manifest=export_mitsuba(scene,directory,lam,max_smoothing_error_mm=.00015)
        max_tube_displacement=max(g["max_centerline_smoothing_bound_mm"]
            +g["float32_centerline_quantization_bound_mm"]+g["float32_radius_quantization_bound_mm"]
            for g in manifest["groups"])
        propagated_clearance=audit["minimum_clearance_lower_bound_mm"]-2*max_tube_displacement
        if propagated_clearance <= 0:
            raise RuntimeError("smoothing/float32 error exhausted the source geometry clearance bound")
        exports.append({"wavelength_nm":lam,"group_count":len(manifest["groups"]),
            "groups":[{k:g[k] for k in ("material_id","radius_mm","fiber_count","n_real","kappa",
                "absorption_per_mm","max_centerline_smoothing_bound_mm",
                "float32_centerline_quantization_bound_mm","float32_radius_quantization_bound_mm")} for g in manifest["groups"]],
            "max_tube_displacement_bound_mm":max_tube_displacement,
            "exported_tube_separation_lower_bound_mm":propagated_clearance,
            "separation_argument":"source capsule clearance minus 2*(smoothing + float32 center + radius error); different fibers only",
            "scene_sha256":scene.sha256})
        if run_render:
            for mi,mode in enumerate(("reflection","transmission")):
                config=RenderConfig(resolution=resolution,spp=spp,seed=805+li*2+mi,mode=mode,
                    width_fraction=.68,max_depth=-1,rr_depth=8,light_azimuth_deg=25,light_elevation_deg=50)
                img,info=render_optical_scene(directory,config,out/f"fabric_{lam}nm_{mode}")
                rendered.append(info)
                axs[li,mi].imshow(encode_srgb(img))
                axs[li,mi].set_title(f"{lam} nm scalar proxy | {mode}",fontsize=11)
                axs[li,mi].axis("off")
    if run_render:
        figure.suptitle("V2 fiber -> ply -> yarn -> weave -> actual path tracing\n98 fibers; 2 materials x 2 radii; fixed exposure",fontsize=13)
        figure.tight_layout()
        figure.savefig(out/"fabric_optical_bridge.png",dpi=180)
        plt.close(figure)
    metrics["mitsuba_exports"]=exports
    metrics["actual_render_runs"]=rendered
    metrics["render_status"]="executed" if run_render else "not_requested"

    figure,axs=plt.subplots(1,3,figsize=(12,3.5))
    axs[0].plot([r["tilt_deg"] for r in oblique],[r["measured_ellipse_area_ratio"] for r in oblique],"o-",label="extracted local cylinder")
    axs[0].set(xlabel="Slice tilt (deg)",ylabel="Ellipse / circle area",title="Oblique slices preserve the mismatch")
    axs[0].grid(alpha=.25)
    axs[1].plot([r["fiber_twist_per_mm"] for r in twisted],[r["max_tilt_deg"] for r in twisted],"o-")
    axs[1].set(xlabel="Fiber twist (turns/mm)",ylabel="Largest local tilt (deg)",title="Twisted bundle fails exact 2D reduction")
    axs[1].grid(alpha=.25)
    tensors=np.array([stats["groups"][f"family:{f}"]["orientation_volume"] for f in ("warp","weft")])
    x=np.arange(3)
    axs[2].bar(x-.18,np.diag(tensors[0]),width=.36,label="warp")
    axs[2].bar(x+.18,np.diag(tensors[1]),width=.36,label="weft")
    axs[2].set(xticks=x,xticklabels=["x","y","z"],ylabel="Volume-weighted <t_i^2>",title="Geometry statistics retained separately")
    axs[2].legend()
    figure.tight_layout();figure.savefig(out/"optical_bridge_diagnostics.png",dpi=180);plt.close(figure)
    np.savez_compressed(out/"calibration_optical_arrays.npz",**arrays)
    metrics["elapsed_seconds"]=time.perf_counter()-started
    metrics["scope"]= ["actual generated 3D fiber geometry is shared by optical export and statistics",
        "exact 2D wave/ray inputs only for the accepted straight calibration yarn",
        "no Tang2024/ASGGX fitting, no full Yu2025 wave-to-3D BSDF coupling",
        "monochromatic proxy render values are camera radiance, not spectral color or hemispheric RT"]
    _write(out/"optical_bridge_metrics.json",metrics)
    print(json.dumps({"output":str(out.resolve()),"seconds":metrics["elapsed_seconds"],
        "fiber_count":len(scene.fibers),"actual_renders":len(rendered),
        "wave_ray_conditions":len(optical_rows),"max_wave_flux_residual":max(r["wave_relative_flux_residual"] for r in optical_rows)},indent=2))
    return metrics


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",default="data/optical_bridge_v2")
    parser.add_argument("--skip-render",action="store_true")
    parser.add_argument("--resolution",type=int,default=128)
    parser.add_argument("--spp",type=int,default=64)
    args=parser.parse_args()
    run_experiments(args.output,run_render=not args.skip_render,resolution=args.resolution,spp=args.spp)
