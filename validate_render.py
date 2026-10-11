"""Independent physics checks for the explicit-fiber renderer and camera.

Run from textile_lab:
  OPENBLAS_NUM_THREADS=1 python validate_render.py --phase all

Runs use saved, hash-identified production geometry; they do not rebuild it.
Dr.Jit uses two threads to avoid contention with the production renders. The
saved per-case arrays allow interrupted runs to resume without losing evidence.
Image means are outgoing radiance for one camera, NOT hemispherical material
reflectance/transmittance. The Chiang near-field BCSDF is NonSymmetric; no
pointwise BRDF reciprocity assertion is imposed.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import re
import time

import numpy as np
from scipy.integrate import quad

from textile_sim.camera import CameraConfig, circular_incoherent_mtf, optical_filter, integrate_pixels, observe
from textile_sim.render import RenderConfig, get_mitsuba, scene_dictionary, hair_properties


BASE=Path(__file__).resolve().parent
DATA=BASE/"data"
MANIFEST=DATA/"render_validation_metrics.json"


def save_json(path, value):
    path=Path(path)
    temporary=path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(value,indent=2,allow_nan=False))
    temporary.replace(path)


def numerical_pupil_overlap(normalized_frequency):
    """Independent disk-overlap quadrature for the incoherent circular OTF.

    Two unit-radius pupil disks are separated by 2*nu. Integrate their vertical
    overlap directly; do not reuse the analytic acos/sqrt MTF expression.
    """
    nu=abs(float(normalized_frequency))
    if not np.isfinite(nu):raise ValueError("frequency must be finite")
    if nu>=1:return 0.0
    separation=2*nu
    lower=max(-1.,separation-1.)
    upper=min(1.,separation+1.)
    def height(x):
        return 2*np.sqrt(max(0.,min(1-x*x,1-(x-separation)**2)))
    value=quad(height,lower,upper,points=[separation/2],epsabs=2e-11,epsrel=2e-11)[0]
    return float(value/np.pi)


def camera_physics_checks(n_seeds=64):
    nu=np.array([0.,.1,.25,.5,.8,.95,1.,1.2])
    reference=np.array([numerical_pupil_overlap(x) for x in nu])
    analytic=circular_incoherent_mtf(nu*(2*.04/.55),.55,.04)
    result={"pupil_overlap":{
        "normalized_frequency":nu.tolist(),"direct_area_quadrature":reference.tolist(),
        "analytic_mtf":analytic.tolist(),"maximum_absolute_error":float(np.max(abs(reference-analytic)))}}
    n,pixel,amplitude=256,.5,.4
    y,x=np.indices((n,n))
    grating=[]
    for kx,ky,binning in [(5,7,1),(12,9,1),(15,0,1),(7,11,4),(21,5,4)]:
        phase=2*np.pi*(kx*x+ky*y)/n
        scene=1+amplitude*np.cos(phase)
        filtered=integrate_pixels(optical_filter(scene,pixel,.55,.04,pad=0),binning)
        yy,xx=np.indices(filtered.shape)
        phase_out=2*np.pi*(kx*(binning*xx+(binning-1)/2)+ky*(binning*yy+(binning-1)/2))/n
        observed=2*np.mean((filtered-1)*np.cos(phase_out))/amplitude
        f=np.hypot(kx,ky)/(n*pixel)
        opt=numerical_pupil_overlap(f/(2*.04/.55))
        box=1.
        for frequency_index in (kx,ky):
            if frequency_index:
                box*=np.sin(np.pi*frequency_index*binning/n)/(binning*np.sin(np.pi*frequency_index/n))
        predicted=opt*box
        grating.append({"kx":kx,"ky":ky,"binning":binning,
                        "frequency_per_um":float(f),"measured_contrast_transfer":float(observed),
                        "pupil_area_times_discrete_pixel_transfer":float(predicted),
                        "absolute_error":float(abs(observed-predicted))})
    result["two_dimensional_gratings"]=grating
    # Fixed physical field of view and detected photon density after optical
    # collection. Larger pixels collect more photoelectrons and incur fewer
    # read-noise samples. This is not a fixed-exposure comparison across NA.
    input_n=256; input_pixel=.8; intensity=.35; electron_density=50.; read_noise=3.
    flat=np.full((input_n,input_n),intensity)
    budget=intensity*electron_density*(input_n*input_pixel)**2
    noise=[]
    for binning in (1,2,4):
        gain=electron_density*(input_pixel*binning)**2
        npix=(input_n//binning)**2
        predicted_pixel_var=(intensity*gain+read_noise**2)/gain**2
        totals=[]; sum_error=0.;sum_squared_error=0.;count=0; expected=[]
        for seed in range(n_seeds):
            c=CameraConfig(binning=binning,electrons_per_um2_unit_radiance=electron_density,
                           read_noise_e=read_noise,full_well_e=1e9,seed=11000+seed)
            value=observe(flat,input_pixel,c)
            error=value["image"]-intensity
            sum_error+=float(error.sum());sum_squared_error+=float(np.square(error).sum());count+=error.size
            totals.append(float(value["image"].sum()*gain))
            expected.append(float(value["expected_electrons"].sum()))
        mean_error=sum_error/count
        measured_pixel_var=(sum_squared_error-count*mean_error**2)/(count-1)
        noise.append({"binning":binning,"pixel_um":input_pixel*binning,"n_seeds":n_seeds,
            "gain_electrons_per_unit_radiance":gain,"pixels_per_frame":npix,
            "predicted_total_photoelectrons":budget,"expected_total_photoelectrons":float(np.mean(expected)),
            "mean_measured_total_electrons":float(np.mean(totals)),
            "measured_total_electron_variance":float(np.var(totals,ddof=1)),
            "predicted_total_electron_variance":float(budget+npix*read_noise**2),
            "measured_radiance_noise_variance":float(measured_pixel_var),
            "predicted_radiance_noise_variance":float(predicted_pixel_var),
            "radiance_variance_ratio":float(measured_pixel_var/predicted_pixel_var),
            "mean_radiance_error":float(mean_error),
            "mean_radiance_standard_error":float(np.sqrt(predicted_pixel_var/count)),
            "total_electrons_by_seed":totals})
    result["fixed_area_photon_and_noise_checks"]=noise
    dark=observe(np.zeros((512,512)),1.,CameraConfig(read_noise_e=3.,seed=231))
    result["bias_subtracted_dark"]={"mean":float(dark["image"].mean()),
        "negative_fraction":float(np.mean(dark["image"]<0)),"variance":float(dark["image"].var()),
        "predicted_variance":.01}
    saturated=observe(np.full((128,128),100.),.8,CameraConfig(
        electrons_per_um2_unit_radiance=50,read_noise_e=3,full_well_e=500,seed=322))
    result["saturation_limit"]={"saturation_fraction":saturated["saturation_fraction"],
        "linear_scene_value":100.,"mean_clipped_estimate":float(saturated["image"].mean()),
        "measured_clipped_variance":float(saturated["image"].var()),
        "returned_preclip_variance":float(saturated["radiance_noise_variance"].mean()),
        "interpretation":"The reported analytic variance is for unsaturated Poisson+read measurements; clipping introduces bias and changes variance. The implementation applies a post-read signal ceiling."}
    return result


def absorption_source_audit():
    source=BASE/"references"/"Mitsuba_hair.cpp"
    text=source.read_text()
    chords=re.findall(r"Float transmitted_length\s*=\s*([^;]+);",text)
    if not chords or any("radius" in value for value in chords):
        raise RuntimeError("pinned source no longer matches audited radius-normalized chord")
    samples=[]
    for radius in (.002,.004,.01):
        for theta,gamma in [(0.,0.),(.37,.2),(.8,.55)]:
            mu=2.
            sigma=hair_properties(RenderConfig(absorption_per_mm=mu),radius)["sigma_a"]["value"]
            normalized_chord=2*np.cos(gamma)/np.cos(theta)
            shader=float(np.exp(-sigma*normalized_chord))
            physical=float(np.exp(-mu*(radius*normalized_chord)))
            samples.append({"radius_mm":radius,"theta_t_rad":theta,"gamma_t_rad":gamma,
                            "shader_transmittance":shader,"physical_Beer_transmittance":physical,
                            "absolute_error":abs(shader-physical)})
    return {"tag":"Mitsuba v3.9.1","source_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),
            "source_url":"https://raw.githubusercontent.com/mitsuba-renderer/mitsuba3/v3.9.1/src/bsdfs/hair.cpp",
            "normalized_chord_expressions":chords,
            "has_nonsymmetric_flag":"BSDFFlags::NonSymmetric" in text,
            "physical_conversion":"sigma_a_shader = absorption_per_mm * fiber_radius_mm",
            "checks":samples}


def first_event_bsdf_probe(scene,n_rays=131072,seed=28719):
    """Check lossless sample weights at actual first surface interactions.

    This is a restricted diagnostic of the sample() estimator in radiance
    transport mode. It does not independently integrate eval(), check every
    direction, establish pointwise reciprocity, or certify a white furnace.
    """
    mi=get_mitsuba()
    rng=np.random.default_rng(seed)
    positions=rng.random((2,n_rays))
    ray,_=scene.sensors()[0].sample_ray(0.,.5,mi.Point2f(*positions),mi.Point2f(.5,.5))
    si=scene.ray_intersect(ray)
    active=si.is_valid()
    mask=np.asarray(active)
    _,weights=si.bsdf().sample(mi.BSDFContext(),si,mi.Float(rng.random(n_rays)),
                              mi.Point2f(*rng.random((2,n_rays))),active)
    values=np.asarray(weights).mean(axis=0)[mask].astype(float)
    return {"incident_sensor_rays":n_rays,"valid_surface_rays":int(mask.sum()),"seed":seed,
            "mean_zero_absorption_one_event_sample_weight":float(values.mean()),
            "std_weight":float(values.std()),"weight_min":float(values.min()),
            "weight_max":float(values.max()),"finite_fraction":float(np.isfinite(values).mean()),
            "note":"First-hit radiance-mode BSDF samples, not pointwise reciprocity. This checks local sample weights; it does not establish eval/PDF normalization or full-scene furnace conservation."}


def sensor_coverage(scene,resolution,subdivisions=4):
    """Sample actual camera rays; avoid assuming a screen/world-axis mapping."""
    mi=get_mitsuba()
    sensor=scene.sensors()[0]
    yy,xx=np.indices((resolution,resolution))
    center=mi.Point2f(((xx+.5)/resolution).ravel(),((yy+.5)/resolution).ravel())
    ray,_=sensor.sample_ray(0.,.5,center,mi.Point2f(.5,.5))
    center_hit=np.asarray(scene.ray_test(ray)).reshape(resolution,resolution)
    fraction=np.zeros((resolution,resolution))
    for iy in range(subdivisions):
        for ix in range(subdivisions):
            sample=mi.Point2f(((xx+(ix+.5)/subdivisions)/resolution).ravel(),
                              ((yy+(iy+.5)/subdivisions)/resolution).ravel())
            ray,_=sensor.sample_ray(0.,.5,sample,mi.Point2f(.5,.5))
            fraction+=np.asarray(scene.ray_test(ray)).reshape(resolution,resolution)/(subdivisions**2)
    return {"coverage":fraction,"center_hit":center_hit,
            "fully_sampled_covered":fraction==1.,"fully_sampled_open":fraction==0.}


def image_statistics(image,masks):
    gray=np.mean(image.astype(float),axis=2) if image.ndim==3 else image.astype(float)
    records={"full_mean":float(gray.mean()),"full_min":float(gray.min()),"full_max":float(gray.max()),
             "rmse_to_unit_radiance":float(np.sqrt(np.mean((gray-1)**2)))}
    for label,key in [("center_covered","center_hit"),("fully_covered","fully_sampled_covered"),
                       ("fully_open","fully_sampled_open")]:
        mask=masks[key]
        records[label+"_pixels"]=int(mask.sum())
        records[label+"_mean"]=float(np.mean(gray[mask])) if np.any(mask) else None
    return records


class RenderValidator:
    def __init__(self,resolution=96,spp=256,force=False):
        self.mi=get_mitsuba()
        import drjit as dr
        dr.set_thread_count(2)
        DATA.mkdir(exist_ok=True)
        self.geometry=DATA/"fabric_plain"/"fibers.txt"
        if not self.geometry.is_file():raise FileNotFoundError("Run/save the plain production geometry first")
        self.geometry_hash=hashlib.sha256(self.geometry.read_bytes()).hexdigest()
        cfg=json.loads((self.geometry.parent/"config.json").read_text())
        self.width=cfg["yarns_per_direction"]*cfg["pitch_mm"]
        self.radius=cfg["fiber_radius_mm"]
        self.resolution=resolution;self.spp=spp;self.force=force
        self.scenes={};self.integrators={};self.images={}
        self.config=RenderConfig(resolution=resolution,spp=spp,mode="furnace",absorption_per_mm=0.,max_depth=-1,rr_depth=8)
        self.manifest=json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
        previous=self.manifest.get("geometry_sha256")
        if previous and previous!=self.geometry_hash:
            raise RuntimeError("Saved validation belongs to a different geometry; use a clean evidence directory")
        self.manifest.update({"geometry_path":"data/fabric_plain/fibers.txt","geometry_sha256":self.geometry_hash,
                              "geometry_configuration":cfg,"resolution":resolution,"mitsuba_version":self.mi.__version__,
                              "drjit_version":dr.__version__,"drjit_threads":dr.thread_count(),"image_quantity":"outgoing radiance for one orthographic camera; not hemispherical material reflectance"})
        self.manifest.setdefault("cases",{})
        self.masks=sensor_coverage(self.scene("furnace",0),resolution,4)
        np.savez_compressed(DATA/"render_validation_coverage.npz",**self.masks)
        self.manifest["coverage"]={"subpixel_grid":"4x4 deterministic sensor-ray locations",
            "mean_coverage":float(self.masks["coverage"].mean()),
            "center_covered_pixels":int(self.masks["center_hit"].sum()),
            "fully_sampled_covered_pixels":int(self.masks["fully_sampled_covered"].sum()),
            "fully_sampled_open_pixels":int(self.masks["fully_sampled_open"].sum()),
            "caveat":"All 16 subsamples hitting is a numerical covered-pixel mask, not a continuous-area certificate."}
        save_json(MANIFEST,self.manifest)

    def scene(self,mode,absorption):
        key=(mode,float(absorption))
        if key not in self.scenes:
            cfg=replace(self.config,mode=mode,absorption_per_mm=absorption)
            self.scenes[key]=self.mi.load_dict(scene_dictionary(self.geometry,self.width,self.radius,cfg))
        return self.scenes[key]

    def run_case(self,label,mode="furnace",absorption=0.,depth=-1,spp=None,seed=9101):
        spp=self.spp if spp is None else spp
        signature={"mode":mode,"absorption_per_mm":absorption,"depth":depth,"spp":spp,"seed":seed,
                   "resolution":self.resolution,"rr_depth":8,"geometry_sha256":self.geometry_hash}
        path=DATA/("render_validation_"+label+".npy")
        old=self.manifest["cases"].get(label)
        if old and old.get("configuration")==signature and path.exists() and not self.force:
            a=np.load(path)
            self.images[label]=a
            return a
        scene=self.scene(mode,absorption)
        if depth not in self.integrators:
            self.integrators[depth]=self.mi.load_dict({"type":"path","max_depth":depth,"rr_depth":8})
        start=time.perf_counter()
        a=np.asarray(self.mi.render(scene,integrator=self.integrators[depth],seed=seed,spp=spp))
        elapsed=time.perf_counter()-start
        if np.any(~np.isfinite(a)) or np.min(a)<-1e-6:raise RuntimeError("invalid rendered linear radiance")
        np.save(path,a)
        record={"configuration":signature,"render_seconds":elapsed,**image_statistics(a,self.masks)}
        self.manifest["cases"][label]=record;self.images[label]=a
        save_json(MANIFEST,self.manifest)
        print(label,"seconds",round(elapsed,3),"full",round(record["full_mean"],7),
              "covered",record["fully_covered_mean"],flush=True)
        return a

    def empty_source_orientation(self):
        result={}
        for mode in ("furnace","hemisphere_reflection","hemisphere_transmission"):
            cfg=replace(self.config,resolution=8,spp=4,mode=mode)
            d=scene_dictionary(self.geometry,self.width,self.radius,cfg);del d["fibers"]
            a=np.asarray(self.mi.render(self.mi.load_dict(d),spp=4,seed=163))
            result[mode]={"mean":float(a.mean()),"minimum":float(a.min()),"maximum":float(a.max())}
        self.manifest["empty_scene_source_orientation"]=result
        save_json(MANIFEST,self.manifest)

    @staticmethod
    def mean_and_seed_uncertainty(images,masks):
        values=[image_statistics(a,masks) for a in images]
        result={"n_seeds":len(images)}
        for key in ("full_mean","center_covered_mean","fully_covered_mean","fully_open_mean"):
            if any(v[key] is None for v in values):
                result[key]=None;result[key+"_seed_sd"]=None;result[key+"_seed_se"]=None
                continue
            a=np.array([v[key] for v in values],float)
            result[key]=float(a.mean())
            result[key+"_seed_sd"]=float(a.std(ddof=1))
            result[key+"_seed_se"]=float(a.std(ddof=1)/np.sqrt(len(a)))
        return result

    def furnace_checks(self):
        self.empty_source_orientation()
        self.bsdf_probe()
        groups={}
        for depth in (-1,2,4,8,16,32):
            arrays=[self.run_case(f"furnace_depth{depth}_seed{seed}",depth=depth,seed=seed) for seed in (9101,9102,9103)]
            groups[str(depth)]=self.mean_and_seed_uncertainty(arrays,self.masks)
            self.manifest["furnace_depth_groups"]=groups
            save_json(MANIFEST,self.manifest)
            print("FURNACE_GROUP",depth,json.dumps(groups[str(depth)]),flush=True)
        infinite=np.mean([self.images[f"furnace_depth-1_seed{s}"] for s in (9101,9102,9103)],axis=0)
        for depth in (2,4,8,16,32):
            image=np.mean([self.images[f"furnace_depth{depth}_seed{s}"] for s in (9101,9102,9103)],axis=0)
            groups[str(depth)]["full_mean_bias_vs_unlimited"]=float(np.mean(image-infinite))
            groups[str(depth)]["covered_mean_bias_vs_unlimited"]=float(np.mean((image-infinite)[self.masks["fully_sampled_covered"]]))
            groups[str(depth)]["pixel_rmse_vs_unlimited_seed_mean"]=float(np.sqrt(np.mean((image-infinite)**2)))
        hemispheres={}
        for mode,base_seed in (("hemisphere_reflection",10101),("hemisphere_transmission",11101)):
            arrays=[self.run_case(f"{mode}_seed{base_seed+j}",mode=mode,seed=base_seed+j) for j in range(3)]
            hemispheres[mode]=arrays
        sums=[hemispheres["hemisphere_reflection"][j]+hemispheres["hemisphere_transmission"][j] for j in range(3)]
        summary=self.mean_and_seed_uncertainty(sums,self.masks)
        sum_mean=np.mean(sums,axis=0)
        summary["mean_sum_minus_unit"]=float(sum_mean.mean()-1)
        summary["pixel_rmse_sum_vs_unlimited_mean"]=float(np.sqrt(np.mean((sum_mean-infinite)**2)))
        summary["upper_mean"]=float(np.mean(hemispheres["hemisphere_reflection"]))
        summary["lower_mean"]=float(np.mean(hemispheres["hemisphere_transmission"]))
        self.manifest["hemisphere_source_linearity"]=summary
        self.run_case("furnace_abs2_seed12101",absorption=2.,seed=12101)
        self.manifest["furnace_depth_groups"]=groups
        save_json(MANIFEST,self.manifest)
        plot_render_checks(self.manifest)

    def bsdf_probe(self):
        result=first_event_bsdf_probe(self.scene("furnace",0.))
        result["geometry_sha256"]=self.geometry_hash
        result["mitsuba_version"]=self.mi.__version__
        save_json(DATA/"render_validation_bsdf_probe.json",result)
        return result

    def sampling_checks(self):
        # One independent high-sample image is a noisy reference, not ground
        # truth. Its noise floor is explicitly included in the interpretation.
        reference=self.run_case("sampling_reference_spp2048_seed16001",mode="reflection",absorption=2.,spp=2048,seed=16001)
        records={}
        for spp in (64,256,1024):
            images=[self.run_case(f"sampling_spp{spp}_seed{seed}",mode="reflection",absorption=2.,spp=spp,seed=seed) for seed in (15001,15002,15003)]
            rmses=np.array([np.sqrt(np.mean((a-reference)**2)) for a in images])
            stack=np.asarray(images,dtype=float)
            between=float(np.mean(np.var(stack,axis=0,ddof=1)))
            summary=self.mean_and_seed_uncertainty(images,self.masks)
            summary.update({"spp":spp,"rmse_to_independent_2048spp_by_seed":rmses.tolist(),
                            "mean_rmse_to_reference":float(rmses.mean()),
                            "rmse_standard_deviation_across_seeds":float(rmses.std(ddof=1)),
                            "mean_pixel_between_seed_variance":between,
                            "variance_times_spp":between*spp,
                            "reference_is_noisy":True})
            records[str(spp)]=summary
            self.manifest["sampling_convergence"]=records
            save_json(MANIFEST,self.manifest)
            print("SAMPLING_GROUP",spp,json.dumps(summary),flush=True)
        v1024=records["1024"]["mean_pixel_between_seed_variance"]
        for spp in (64,256,1024):
            records[str(spp)]["predicted_rmse_with_reference_noise_from_1024"]=float(np.sqrt(v1024*(1024/spp+1024/2048)))
        self.manifest["sampling_convergence"]=records
        save_json(MANIFEST,self.manifest)
        plot_render_checks(self.manifest)


def plot_camera_checks(camera):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,3,figsize=(13,4.2),layout="constrained")
    p=camera["pupil_overlap"]
    axes[0].plot(p["normalized_frequency"],p["analytic_mtf"],"-",label="Implemented circular OTF")
    axes[0].plot(p["normalized_frequency"],p["direct_area_quadrature"],"o",mfc="none",label="Independent pupil overlap")
    axes[0].set(xlabel="Spatial frequency / cutoff",ylabel="Contrast transfer",title="Pupil physics, independently integrated")
    axes[0].legend(fontsize=8)
    noise=camera["fixed_area_photon_and_noise_checks"]
    b=[x["binning"] for x in noise]
    axes[1].plot(b,[x["expected_total_photoelectrons"] for x in noise],"o-",label="Expected total photoelectrons")
    axes[1].set(xlabel="Detector binning per axis",ylabel="Photoelectrons over fixed scene area",title="Fixed detected-photon / area budget",xticks=b)
    axes[2].loglog(b,[x["predicted_radiance_noise_variance"] for x in noise],"-",label="Poisson + read prediction")
    axes[2].loglog(b,[x["measured_radiance_noise_variance"] for x in noise],"o",mfc="none",label="64 independent seeds")
    axes[2].set(xlabel="Detector binning per axis",ylabel="Radiance-estimate noise variance",title="Noise changes with physical pixel area")
    axes[2].legend(fontsize=8)
    for ax in axes:ax.grid(alpha=.2)
    fig.suptitle("Independent camera checks | unsaturated sensor regime",fontsize=13)
    fig.savefig(DATA/"render_validation_camera.png",dpi=180);plt.close(fig)


def plot_render_checks(manifest):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    with np.load(DATA/"render_validation_coverage.npz") as f:coverage=f["coverage"]
    fig,axes=plt.subplots(2,3,figsize=(13,8),layout="constrained")
    im=axes[0,0].imshow(coverage,vmin=0,vmax=1,cmap="gray")
    axes[0,0].set_title("Actual sensor-ray sampled fiber coverage")
    fig.colorbar(im,ax=axes[0,0],fraction=.05)
    furnace_paths=[DATA/f"render_validation_furnace_depth-1_seed{s}.npy" for s in (9101,9102,9103)]
    constant=None
    if all(p.exists() for p in furnace_paths):
        constant=np.mean([np.load(p) for p in furnace_paths],axis=0)
        im=axes[0,1].imshow(constant.mean(axis=2)-1,vmin=-.08,vmax=.08,cmap="coolwarm")
        axes[0,1].set_title("Lossless furnace: mean radiance minus 1")
        fig.colorbar(im,ax=axes[0,1],fraction=.05)
    else:axes[0,1].axis("off")
    group=manifest.get("furnace_depth_groups",{})
    depths=[d for d in (2,4,8,16,32) if str(d) in group]
    axes[0,2].errorbar(depths,[group[str(d)]["fully_covered_mean"] for d in depths],
                       yerr=[group[str(d)]["fully_covered_mean_seed_se"] for d in depths],fmt="o-",label="Sampled fully covered pixels")
    if "-1" in group:
        axes[0,2].axhline(group["-1"]["fully_covered_mean"],color="black",linestyle="--",label="Unlimited depth + roulette")
    axes[0,2].set(xlabel="Maximum path depth",ylabel="Outgoing radiance",title="Finite-depth truncation bias",xticks=depths)
    axes[0,2].legend(fontsize=8)
    if "hemisphere_source_linearity" in manifest and constant is not None:
        upper=np.mean([np.load(DATA/f"render_validation_hemisphere_reflection_seed{s}.npy") for s in (10101,10102,10103)],axis=0)
        lower=np.mean([np.load(DATA/f"render_validation_hemisphere_transmission_seed{s}.npy") for s in (11101,11102,11103)],axis=0)
        im=axes[1,0].imshow((upper+lower-constant).mean(axis=2),vmin=-.08,vmax=.08,cmap="coolwarm")
        fig.colorbar(im,ax=axes[1,0],fraction=.05)
        axes[1,0].set_title("Upper + lower source minus full furnace")
    else:axes[1,0].axis("off")
    data=manifest.get("sampling_convergence",{})
    sampling_complete=all(str(s) in data and "predicted_rmse_with_reference_noise_from_1024" in data[str(s)]
                          for s in (64,256,1024))
    if sampling_complete:
        spp=np.array([64,256,1024])
        axes[1,1].loglog(spp,[data[str(s)]["mean_rmse_to_reference"] for s in spp],"o-",label="RMSE to independent 2048 spp")
        axes[1,1].loglog(spp,[data[str(s)]["predicted_rmse_with_reference_noise_from_1024"] for s in spp],"--",label="1/spp variance + reference floor")
        axes[1,1].set(xlabel="Samples per pixel",ylabel="Linear-radiance RMSE",title="Actual illuminated-cloth convergence")
        axes[1,1].legend(fontsize=8)
        ref=np.load(DATA/"render_validation_sampling_reference_spp2048_seed16001.npy")
        axes[1,2].imshow(np.clip(ref**(1/2.2),0,1))
        axes[1,2].set_title("Independent noisy reference, 2048 spp")
    else:
        axes[1,1].axis("off");axes[1,2].axis("off")
    for ax in [axes[0,0],axes[0,1],axes[1,0],axes[1,2]]:ax.set_xticks([]);ax.set_yticks([])
    for ax in [axes[0,2],axes[1,1]]:ax.grid(alpha=.2)
    fig.suptitle("Explicit-fiber renderer: independent physical and numerical checks\nImage means describe one camera, not hemispherical material reflectance",fontsize=13)
    fig.savefig(DATA/"render_validation_overview.png",dpi=180);plt.close(fig)


def main(phase="all",resolution=96,spp=256,force=False):
    DATA.mkdir(exist_ok=True)
    if phase in ("all","camera"):
        result=json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
        result["camera"]=camera_physics_checks()
        result["absorption_source_audit"]=absorption_source_audit()
        save_json(MANIFEST,result)
        plot_camera_checks(result["camera"])
        print("CAMERA PHYSICS COMPLETE",flush=True)
    if phase in ("all","furnace","sampling","probe"):
        validator=RenderValidator(resolution,spp,force)
        if phase in ("all","furnace"):validator.furnace_checks()
        if phase in ("all","sampling"):validator.sampling_checks()
        if phase=="probe":validator.bsdf_probe()
    print("RENDER VALIDATION COMPLETE",phase,flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--phase",choices=["all","camera","furnace","sampling","probe"],default="all")
    p.add_argument("--resolution",type=int,default=96)
    p.add_argument("--spp",type=int,default=256)
    p.add_argument("--force",action="store_true")
    a=p.parse_args();main(a.phase,a.resolution,a.spp,a.force)
