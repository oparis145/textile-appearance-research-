#!/usr/bin/env python3
"""Execute v3 hierarchy-aware optical reduction and spectral observation.

Requires the actual before/after geometry from run_weave_mechanics_experiments.py. All
optical constituent constants are synthetic; CIE observer samples are official.
The SGGX fit is assessed independently of the explicit-fiber renderer.
"""
from __future__ import annotations
from pathlib import Path
from dataclasses import asdict
import argparse
import copy
import hashlib
import json
import time
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

from textile_sim.hierarchy import load_hierarchy
from textile_sim.optical_scene import (MaterialSpectrum,OpticalScene,from_hierarchy,
    export_mitsuba,mitsuba_scene_dictionary,microstructure_statistics)
from textile_sim.optical_lod import (projected_area_density,fit_sggx_projected_area,
    fibonacci_directions,load_cie1931,planck_relative,spectral_xyz_weights,
    integrate_xyz,xyz_to_linear_srgb,paired_mean_interval)
from textile_sim.render import RenderConfig,get_mitsuba,encode_srgb,direction


def write_json(path, value):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")


def synthetic_materials():
    wavelength=np.arange(360.,831.,5.)
    a=8+70*np.exp(-((wavelength-460)/55)**2)
    b=8+65*np.exp(-((wavelength-620)/65)**2)
    return (MaterialSpectrum.from_absorption("synthetic_A",wavelength,1.52+3000/wavelength**2,a,
                "Synthetic A: smooth illustrative dielectric/absorption spectrum, not a measured textile"),
            MaterialSpectrum.from_absorption("synthetic_B",wavelength,1.61+4500/wavelength**2,b,
                "Synthetic B: smooth illustrative dielectric/absorption spectrum, not a measured textile"))


def fit_hierarchy(scene, volume, out, state):
    train=fibonacci_directions(96,.5)
    hold=fibonacci_directions(1200,.371)
    truth=projected_area_density(scene,hold,volume)["all"]
    rms=np.sqrt(np.mean(truth**2))
    rows=[];arrays={"train_directions":train,"heldout_directions":hold,"heldout_truth_per_mm":truth}
    for level in ("all","family","yarn","ply"):
        target=projected_area_density(scene,train,volume,group_by=level)
        prediction=np.zeros(len(hold));groups={}
        for key,y in target.items():
            fitted,diag=fit_sggx_projected_area(train,y)
            prediction+=fitted.projected_area(hold)
            groups[key]={"matrix_per_mm2":fitted.matrix.tolist(),"fit":diag}
        error=prediction-truth
        row={"level":level,"group_count":len(groups),"parameters":6*len(groups),
             "heldout_relative_rmse":float(np.sqrt(np.mean(error**2))/rms),
             "heldout_max_error_over_rms_target":float(np.max(np.abs(error))/rms),
             "fit_groups":groups}
        rows.append(row);arrays[level+"_heldout_prediction_per_mm"]=prediction
    np.savez_compressed(out/f"{state}_projected_area_fits.npz",**arrays)
    return {"scene_sha256":scene.sha256,"averaging_volume_mm3":volume,
            "training_direction_count":len(train),"heldout_direction_count":len(hold),
            "heldout_target_rms_per_mm":float(rms),"levels":rows,
            "status":"projected-area aggregation diagnostic only; no aggregate fabric BSDF rendered"}


def common_rig(dictionary, union_bounds, config):
    """Use identical physical camera/source coordinates for both geometries."""
    mi=get_mitsuba()
    width=float(np.max(union_bounds[1,:2]-union_bounds[0,:2]))
    center=union_bounds.mean(axis=0)
    half=.5*width*config.width_fraction
    vo=direction(config.view_elevation_deg,config.view_azimuth_deg)
    up=np.array([0.,1.,0.])
    if abs(vo@up)>.95: up=np.array([0.,0.,1.])
    dictionary["sensor"]["to_world"]=mi.ScalarTransform4f().look_at(
        origin=center+vo*10*width,target=center,up=up).scale([half,half,1])
    li=direction(config.light_elevation_deg,config.light_azimuth_deg)
    if config.mode=="transmission": li[2]*=-1
    distance=20*width
    source_half=distance*np.tan(np.deg2rad(config.light_halfwidth_deg))
    up_light=[0,1,0] if abs(li[1])<.95 else [1,0,0]
    dictionary["key"]["to_world"]=mi.ScalarTransform4f().look_at(
        origin=center+li*distance,target=center,up=up_light).scale([source_half,source_half,1])
    return {"width_mm":width,"center_mm":center.tolist(),"film_width_mm":2*half,
            "pixel_width_um":2*half/config.resolution*1000,
            "light_center_mm":(center+li*distance).tolist(),
            "light_halfwidth_mm":source_half,"camera_direction":vo.tolist()}


def _set_wavelength(params,mi,manifest,material_map,wavelength,background_n):
    rows=[]
    for j,group in enumerate(manifest["groups"]):
        optical=material_map[group["material_id"]].at(wavelength)
        if optical["kappa"]/optical["n_real"]>.01:
            raise ValueError("synthetic spectrum exceeded declared real-Fresnel approximation")
        eta=optical["n_real"]/background_n
        sigma=optical["absorption_per_mm"]*group["radius_mm"]
        params[f"fibers_{j:04d}.bsdf.eta"]=mi.Float(eta)
        params[f"fibers_{j:04d}.bsdf.sigma_a.value"]=mi.Float(sigma)
        rows.append({"material_id":group["material_id"],"radius_mm":group["radius_mm"],
             "relative_eta":eta,"absorption_per_mm":optical["absorption_per_mm"],
             "sigma_a_shader":sigma,"kappa":optical["kappa"]})
    params.update()
    return rows


def render_stack(scene,export_directory,manifest,union_bounds,config,wavelengths,seeds):
    mi=get_mitsuba()
    d=mitsuba_scene_dictionary(export_directory,config)
    rig=common_rig(d,union_bounds,config)
    compiled=mi.load_dict(d);params=mi.traverse(compiled)
    stack=np.zeros((len(seeds),config.resolution,config.resolution,len(wavelengths)),dtype=np.float32)
    rows=[];start=time.perf_counter();channel_mismatch=0.
    for k,wavelength in enumerate(wavelengths):
        optics=_set_wavelength(params,mi,manifest,scene.material_map,wavelength,scene.background_n)
        for s,seed in enumerate(seeds):
            # Reusing the seed across wavelength/state supports paired differences;
            # different seeds, not pixels/wavelengths, are statistical replicates.
            rgb=np.asarray(mi.render(compiled,seed=int(seed),spp=config.spp))
            if not np.isfinite(rgb).all() or rgb.min() < -1e-7:
                raise RuntimeError("invalid path traced spectral radiance")
            channel_mismatch=max(channel_mismatch,float(np.max(np.ptp(rgb,axis=-1))))
            if channel_mismatch>1e-5:
                raise RuntimeError("scalar wavelength computation unexpectedly has unequal RGB channels")
            stack[s,:,:,k]=rgb[:,:,0]
        rows.append({"wavelength_nm":float(wavelength),"groups":optics})
    return stack,{"render_config":asdict(config),"rig":rig,"seeds":list(map(int,seeds)),
        "wavelengths_nm":wavelengths.tolist(),"optical_parameters_by_wavelength":rows,
        "seconds":time.perf_counter()-start,"actual_render_count":len(wavelengths)*len(seeds),
        "maximum_scalar_rgb_channel_disagreement":channel_mismatch,
        "spectral_transport":"deterministic monochromatic real-Fresnel/Beer parameter sweep in llvm_ad_rgb",
        "not_modeled":["wave interference","polarization","fluorescence","measured camera spectral response"]}


def gray_reference(export_directory,union_bounds,config):
    """Lambertian finite-source numerical radiometric check at the common rig."""
    mi=get_mitsuba();d=mitsuba_scene_dictionary(export_directory,config)
    rig=common_rig(d,union_bounds,config)
    for key in list(d):
        if key.startswith("fibers_"): del d[key]
    width=rig["width_mm"];center=np.asarray(rig["center_mm"])
    d["reference"]={"type":"rectangle","to_world":mi.ScalarTransform4f().translate(center).scale([width*2,width*2,1]),
                    "bsdf":{"type":"diffuse","reflectance":.4}}
    img=np.asarray(mi.render(mi.load_dict(d),seed=803991,spp=256))[:,:,0]
    # Independent area quadrature of irradiance at the center. Camera image
    # covers a finite FOV, so only its central pixel block is compared.
    light=d["key"]["to_world"]
    mu,w=np.polynomial.legendre.leggauss(100)
    u,v=np.meshgrid(mu,mu,indexing="ij");weights=(w[:,None]*w[None,:]).ravel()
    p=np.array(light.matrix)[:3,:3]@np.vstack((u.ravel(),v.ravel(),np.zeros(u.size)))+np.array(light.matrix)[:3,3,None]
    r=p-center[:,None];r2=np.sum(r*r,axis=0);unit=r/np.sqrt(r2)
    normal=np.array(light.matrix)[:3,2];normal/=np.linalg.norm(normal)
    cos_light=np.maximum(0,(-unit).T@normal)
    cos_surface=np.maximum(0,unit[2])
    jac=np.linalg.norm(np.cross(np.array(light.matrix)[:3,0],np.array(light.matrix)[:3,1]))
    le=float(d["key"]["emitter"]["radiance"])
    expected=.4/np.pi*np.sum(weights*le*cos_light*cos_surface/r2)*jac
    n=config.resolution//2
    observed=float(img[n-1:n+1,n-1:n+1].mean())
    return {"expected_center_radiance":float(expected),"rendered_center_block_mean":observed,
            "relative_error":float(abs(observed-expected)/max(expected,1e-15)),
            "quadrature":"100x100 Gauss-Legendre over exact emitter rectangle",
            "render_spp":256,"comparison":"2x2 central pixels versus geometric center, plus Monte Carlo noise"}


def make_figures(out,figdir,states,fits,all_data,wavelengths,cie,observers,metrics):
    figdir.mkdir(parents=True,exist_ok=True)
    # Direct nonuniqueness example for the moment closure.
    angle=np.linspace(0,180,721);a=np.deg2rad(angle)
    curve_a=.5*(np.abs(np.sin(a))+np.abs(np.cos(a)))
    curve_b=.5*(np.abs(np.sin(a-np.pi/4))+np.abs(np.cos(a-np.pi/4)))
    fig,axs=plt.subplots(1,3,figsize=(14,4))
    axs[0].plot(angle,curve_a,label="axes x/y");axs[0].plot(angle,curve_b,label="axes rotated 45 degrees")
    axs[0].set(xlabel="Observation azimuth (degrees)",ylabel="A / sum(2 r L)",title="Same tangent second moment; different area")
    axs[0].legend(fontsize=8)
    x=np.arange(4)
    for state in states:
        axs[1].semilogy(x,[r["heldout_relative_rmse"] for r in fits[state]["levels"]],"o-",label=state)
    axs[1].set(xticks=x,xticklabels=["all","family","yarn","ply"],ylabel="Held-out relative RMSE",title="Projected-area fit error at each hierarchy")
    axs[1].legend()
    for state in states:
        ar=np.load(out/f"{state}_projected_area_fits.npz")
        truth=ar["heldout_truth_per_mm"]
        axs[2].scatter(truth[::8],ar["all_heldout_prediction_per_mm"][::8],s=8,alpha=.55,label=state)
    limits=axs[2].get_xlim();axs[2].plot(limits,limits,"k--",lw=.8)
    axs[2].set(xlabel="Explicit line-element density (1/mm)",ylabel="One SGGX fit (1/mm)",title="A fitted geometric prior, not a fabric BSDF")
    axs[2].legend()
    for ax in axs: ax.grid(alpha=.2)
    fig.tight_layout();fig.savefig(figdir/"projected_area_lod.png",dpi=180);plt.close(fig)
    np.savez_compressed(out/"equal_covariance_counterexample.npz",azimuth_deg=angle,
        xy_projected_area_normalized=curve_a,diagonal_projected_area_normalized=curve_b,
        common_tangent_covariance=np.diag([.5,.5,0.]))

    # Quantitative spectral synthesis: same fixed display exposure everywhere.
    configs=metrics["lighting_configs"]
    fig,axs=plt.subplots(4,len(configs),figsize=(12,13))
    labels=[]
    for row,(temperature,state) in enumerate([(3000,"initial"),(3000,"relaxed"),(6500,"initial"),(6500,"relaxed")]):
        weights,_=observers[temperature]
        for j,key in enumerate(configs):
            xyz=integrate_xyz(all_data[state][key].mean(axis=0),weights)
            rgb=xyz_to_linear_srgb(xyz)
            shown=encode_srgb(rgb,exposure=.7)
            Image.fromarray(np.round(shown*255).astype(np.uint8)).save(out/f"{state}_{key}_{temperature}K.png")
            axs[row,j].imshow(shown);axs[row,j].axis("off")
            if row==0: axs[row,j].set_title(key.replace("_"," "),fontsize=12)
            if j==0: axs[row,j].text(-.06,.5,f"{state}\nPlanck {temperature} K",va="center",ha="right",rotation=90,transform=axs[row,j].transAxes)
            labels.append({"state":state,"light":key,"temperature_kelvin":temperature,
                "negative_linear_srgb_fraction":float(np.mean(rgb<0)),
                "over_one_after_exposure_fraction":float(np.mean(.7*rgb>1))})
    fig.suptitle("Actual explicit fibers: wavelength response integrated with CIE 1931\nSynthetic constituent spectra; fixed exposure 0.7; no chromatic adaptation",fontsize=15)
    fig.tight_layout(rect=[.05,0,1,.94]);fig.savefig(figdir/"spectral_geometry_comparison.png",dpi=180);plt.close(fig)
    metrics["display_diagnostics"]=labels

    fig,axs=plt.subplots(1,2,figsize=(12,4))
    for state in states:
        for key,stack in all_data[state].items():
            mean=stack.mean(axis=(0,1,2))
            axs[0].plot(wavelengths,mean,label=f"{state}: {key}",ls="--" if state=="initial" else "-")
    axs[0].set(xlabel="Vacuum wavelength (nm)",ylabel="Mean scalar camera radiance",title="Actual rendered spectral responses")
    axs[0].legend(fontsize=7)
    rows=metrics["paired_observation_comparisons"]
    xx=np.arange(len(rows));mean=np.array([r["xyz_interval"]["mean_delta"][1] for r in rows]);low=np.array([r["xyz_interval"]["interval_low"][1] for r in rows]);high=np.array([r["xyz_interval"]["interval_high"][1] for r in rows])
    axs[1].errorbar(xx,mean,yerr=np.vstack((mean-low,high-mean)),fmt="o",capsize=3)
    axs[1].axhline(0,color="k",lw=.7)
    axs[1].set(xticks=xx,xticklabels=[r["light"]+"\n"+str(r["temperature_kelvin"])+" K" for r in rows],
        ylabel="Delta mean normalized Y",title="Relaxed minus initial: paired-seed 95% intervals")
    axs[1].tick_params(axis="x",labelsize=7)
    for ax in axs: ax.grid(alpha=.2)
    fig.tight_layout();fig.savefig(figdir/"spectral_response_uncertainty.png",dpi=180);plt.close(fig)


def run_experiments(pair_directory="data/mechanics_v3/optical_pair",output="data/optical_v3",
                    figures="figures/optical_v3",resolution=64,spp=32,replicates=4,render=True):
    if resolution<8 or spp<1 or replicates<2:
        raise ValueError("resolution>=8, spp>=1, and paired replicates>=2 required")
    source_files=("textile_sim/optical_lod.py","run_multiscale_optics_v3.py","textile_sim/optical_scene.py","textile_sim/render.py")
    source_hashes={name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in source_files}
    out=Path(output);out.mkdir(parents=True,exist_ok=True);figdir=Path(figures)
    start=time.perf_counter();states=("initial","relaxed")
    mats=synthetic_materials()
    scenes={s:from_hierarchy(load_hierarchy(Path(pair_directory)/s),mats) for s in states}
    if [f.fiber_id for f in scenes["initial"].fibers] != [f.fiber_id for f in scenes["relaxed"].fibers]:
        raise ValueError("paired geometry must preserve fiber identities")
    for a,b in zip(scenes["initial"].fibers,scenes["relaxed"].fibers):
        if (a.material_id,a.radius_mm,a.yarn_id,a.ply_id)!=(b.material_id,b.radius_mm,b.yarn_id,b.ply_id):
            raise ValueError("paired geometry changed assigned materials, radii, or parents")
    union_bounds=np.array([np.minimum.reduce([s.bounds_mm[0] for s in scenes.values()]),
                           np.maximum.reduce([s.bounds_mm[1] for s in scenes.values()])])
    volume=float(np.prod(union_bounds[1]-union_bounds[0]))
    metrics={"version":"textile.optical_scale/3.0","date_utc":"2026-10-11",
        "input_pair_directory":str(Path(pair_directory)),"material_status":"synthetic; no named textile calibration",
        "common_union_bounds_mm":union_bounds.tolist(),"common_averaging_volume_mm3":volume,
        "microstructure":{},"projection_fits":{},"render_runs":{},"paired_observation_comparisons":[],
        "scope":["spectral ray-optical explicit-fiber responses, no coherent transport",
          "SGGX geometric projected-area fits are diagnostics, not a fabric BSDF replacement",
          "before/after reassembled fibers may change material length; not a mass-conserving fiber mechanics claim",
          "CIE observer plus normalized Planck sources; synthetic constituents and common fixed camera/light rig",
          "no metasurface advantage or inverse-identifiability claim from these synthetic images"]}
    pair_meta=json.loads((Path(pair_directory)/"pair_metrics.json").read_text())
    metrics["input_pair_metrics_sha256"]=hashlib.sha256((Path(pair_directory)/"pair_metrics.json").read_bytes()).hexdigest()
    fits={};exports={}
    for state,scene in scenes.items():
        scene.save(out/f"{state}_optical_scene.json")
        metrics["microstructure"][state]=microstructure_statistics(scene)
        fits[state]=fit_hierarchy(scene,volume,out,state)
        metrics["projection_fits"][state]=fits[state]
        exports[state]=export_mitsuba(scene,out/f"{state}_curves",380.,max_smoothing_error_mm=.0004)
        metrics[state+"_spline_error_budget"]=[{k:g[k] for k in ("material_id","radius_mm","max_centerline_smoothing_bound_mm","float32_centerline_quantization_bound_mm","float32_radius_quantization_bound_mm")} for g in exports[state]["groups"]]
        audit=pair_meta[state]["clearance_audit"]
        displacement=max(g["max_centerline_smoothing_bound_mm"]+g["float32_centerline_quantization_bound_mm"]+
                         g["float32_radius_quantization_bound_mm"] for g in exports[state]["groups"])
        remaining=audit["minimum_clearance_lower_bound_mm"]-2*displacement
        if not audit["certified_separated"] or remaining<=0:
            raise RuntimeError("spline conversion exhausted the mechanics fixture clearance certificate")
        metrics[state+"_exported_clearance_budget"]={"source_clearance_lower_bound_mm":audit["minimum_clearance_lower_bound_mm"],
            "maximum_tube_displacement_bound_mm":displacement,"exported_clearance_lower_bound_mm":remaining,
            "scope":"different fibers only; source capsule gap minus twice smoothing and float32 storage bounds"}
    initial_volume=metrics["microstructure"]["initial"]["groups"]["all"]["sum_cylinder_volume_mm3"]
    relaxed_volume=metrics["microstructure"]["relaxed"]["groups"]["all"]["sum_cylinder_volume_mm3"]
    metrics["fiber_material_volume_relative_change"]=(relaxed_volume-initial_volume)/initial_volume
    wavelengths=np.linspace(380.,780.,17)
    cie_nm,cie_xyz=load_cie1931()
    observers={temperature:spectral_xyz_weights(wavelengths,cie_nm,cie_xyz,planck_relative(cie_nm,temperature)) for temperature in (3000,6500)}
    metrics["observer_integration"]={str(t):info for t,(w,info) in observers.items()}
    write_json(out/"synthetic_material_spectra.json",[m.to_dict() for m in mats])
    seeds=np.arange(replicates)*13579+9203
    configs={"reflection_warp":RenderConfig(resolution=resolution,spp=spp,light_elevation_deg=40,light_azimuth_deg=0,width_fraction=.68),
             "reflection_weft":RenderConfig(resolution=resolution,spp=spp,light_elevation_deg=40,light_azimuth_deg=90,width_fraction=.68),
             "transmission_diag":RenderConfig(resolution=resolution,spp=spp,mode="transmission",light_elevation_deg=55,light_azimuth_deg=45,width_fraction=.68)}
    metrics["lighting_configs"]={k:asdict(v) for k,v in configs.items()}
    all_data={state:{} for state in states}
    if render:
        for state in states:
            metrics["render_runs"][state]={}
            for key,config in configs.items():
                stack,info=render_stack(scenes[state],out/f"{state}_curves",exports[state],union_bounds,config,wavelengths,seeds)
                all_data[state][key]=stack
                metrics["render_runs"][state][key]=info
                np.savez_compressed(out/f"{state}_{key}_radiance.npz",radiance=stack,wavelengths_nm=wavelengths,seeds=seeds)
                print(json.dumps({"state":state,"light":key,"renders":info["actual_render_count"],"seconds":info["seconds"]}),flush=True)
        for key in configs:
            for temperature,(weights,info) in observers.items():
                before=integrate_xyz(all_data["initial"][key].mean(axis=(1,2)),weights)
                after=integrate_xyz(all_data["relaxed"][key].mean(axis=(1,2)),weights)
                interval=paired_mean_interval(before,after)
                metrics["paired_observation_comparisons"].append({"light":key,"temperature_kelvin":temperature,
                    "initial_mean_xyz":before.mean(axis=0).tolist(),"relaxed_mean_xyz":after.mean(axis=0).tolist(),
                    "relative_mean_Y_change":float((after[:,1].mean()-before[:,1].mean())/before[:,1].mean()),
                    "xyz_interval":interval})
        # Nested 50/25-nm reuse of the same rendered samples separates spectral
        # discretization from independent random-seed variation, while still
        # acknowledging that the 25-nm solution is not an exact reference.
        convergence=[]
        for key in configs:
            for temperature,(fine_w,_) in observers.items():
                coarse_w,_=spectral_xyz_weights(wavelengths[::2],cie_nm,cie_xyz,planck_relative(cie_nm,temperature))
                a=all_data["relaxed"][key].mean(axis=(1,2))
                fine=integrate_xyz(a,fine_w);coarse=integrate_xyz(a[:,::2],coarse_w)
                convergence.append({"light":key,"temperature_kelvin":temperature,
                    "coarse_50nm_vs_fine_25nm_relative_XYZ_mean_error":float(np.linalg.norm(coarse.mean(axis=0)-fine.mean(axis=0))/np.linalg.norm(fine.mean(axis=0))),
                    "paired_interval_coarse_minus_fine":paired_mean_interval(fine,coarse)})
        metrics["spectral_nested_grid_comparison"]=convergence
        # One actual 12.5-nm refinement under the first reflection light. The
        # existing 25-nm samples are reused verbatim and only midpoints computed.
        fine_wavelengths=np.linspace(380.,780.,33)
        midpoint_wavelengths=fine_wavelengths[1::2]
        metrics["spectral_fine_grid_render_runs"]={}
        refinement=[]
        for state in states:
            mid,info=render_stack(scenes[state],out/f"{state}_curves",exports[state],union_bounds,
                configs["reflection_warp"],midpoint_wavelengths,seeds)
            fine=np.zeros(mid.shape[:-1]+(33,),dtype=np.float32)
            fine[:,:,:,::2]=all_data[state]["reflection_warp"];fine[:,:,:,1::2]=mid
            np.savez_compressed(out/f"{state}_reflection_warp_fine_radiance.npz",radiance=fine,wavelengths_nm=fine_wavelengths,seeds=seeds)
            metrics["spectral_fine_grid_render_runs"][state]=info
            for temperature,(old_weights,_) in observers.items():
                fine_weights,_=spectral_xyz_weights(fine_wavelengths,cie_nm,cie_xyz,planck_relative(cie_nm,temperature))
                old_xyz=integrate_xyz(all_data[state]["reflection_warp"].mean(axis=(1,2)),old_weights)
                fine_xyz=integrate_xyz(fine.mean(axis=(1,2)),fine_weights)
                refinement.append({"state":state,"light":"reflection_warp","temperature_kelvin":temperature,
                    "coarse_25nm_vs_fine_12p5nm_relative_XYZ_mean_error":float(np.linalg.norm(old_xyz.mean(axis=0)-fine_xyz.mean(axis=0))/np.linalg.norm(fine_xyz.mean(axis=0))),
                    "paired_interval_coarse_minus_fine":paired_mean_interval(fine_xyz,old_xyz)})
        metrics["spectral_12p5nm_refinement"]=refinement
        metrics["lambertian_radiometric_benchmark"]=gray_reference(out/"initial_curves",union_bounds,configs["reflection_warp"])
        make_figures(out,figdir,states,fits,all_data,wavelengths,(cie_nm,cie_xyz),observers,metrics)
    metrics["actual_explicit_fiber_render_count"]=sum(info["actual_render_count"] for runs in metrics["render_runs"].values() for info in runs.values())+sum(info["actual_render_count"] for info in metrics.get("spectral_fine_grid_render_runs",{}).values())
    metrics["render_status"]="executed" if render else "not_requested"
    metrics["elapsed_seconds"]=time.perf_counter()-start
    if source_hashes!={name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in source_files}:
        raise RuntimeError("optical source changed during experiment; rerun after code is stable")
    metrics["source_sha256"]=source_hashes
    write_json(out/"optical_scale_metrics.json",metrics)
    print(json.dumps({"output":str(out),"seconds":metrics["elapsed_seconds"],"actual_renders":metrics["actual_explicit_fiber_render_count"]}),flush=True)
    return metrics


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pair-directory",default="data/mechanics_v3/optical_pair")
    p.add_argument("--output",default="data/optical_v3")
    p.add_argument("--figures",default="figures/optical_v3")
    p.add_argument("--resolution",type=int,default=64)
    p.add_argument("--spp",type=int,default=32)
    p.add_argument("--replicates",type=int,default=4)
    p.add_argument("--skip-render",action="store_true")
    a=p.parse_args()
    run_experiments(a.pair_directory,a.output,a.figures,a.resolution,a.spp,a.replicates,not a.skip_render)
