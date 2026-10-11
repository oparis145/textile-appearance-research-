"""Explicit-fiber cloth path tracing with Mitsuba 3.9.1.

Uses the published Chiang et al. (2016) near-field dielectric-fiber BCSDF;
this is a ray-optical baseline, NOT Yu et al. (2025)'s fitted ray-wave BSDF.
No fabricated measured optical constants or neural/generated textures are used.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import os, sys, time, json
import numpy as np
from PIL import Image


def get_mitsuba(variant="llvm_ad_rgb"):
    try:
        import mitsuba as mi
    except ImportError:
        local=Path(__file__).resolve().parents[2]/".sim_deps"
        if local.is_dir():
            sys.path.insert(0,str(local))
            import mitsuba as mi
        else:
            raise ImportError("Install requirements: python -m pip install mitsuba==3.9.1")
    if mi.variant()!=variant:
        mi.set_variant(variant)
    if mi.__version__!="3.9.1":
        raise RuntimeError("This experiment audits Mitsuba 3.9.1. Install that version before using radius-normalized absorption.")
    return mi


@dataclass
class RenderConfig:
    resolution: int = 384
    spp: int = 128
    seed: int = 53
    mode: str = "reflection"
    light_elevation_deg: float = 45.
    light_azimuth_deg: float = 0.
    light_halfwidth_deg: float = 7.
    view_elevation_deg: float = 90.
    view_azimuth_deg: float = -90.
    ior: float = 1.55
    absorption_per_mm: float = 2.
    longitudinal_roughness: float = .18
    azimuthal_roughness: float = .20
    max_depth: int = -1
    rr_depth: int = 8
    exposure: float = 1.
    ambient: float = .0
    width_fraction: float = .82


def direction(elevation_deg, azimuth_deg):
    e,a=np.deg2rad([elevation_deg,azimuth_deg])
    return np.array([np.cos(e)*np.cos(a),np.cos(e)*np.sin(a),np.sin(e)])


def encode_srgb(linear, exposure=1.):
    a=np.maximum(np.asarray(linear)*exposure,0.)
    a=np.where(a<=.0031308,12.92*a,1.055*a**(1/2.4)-.055)
    return np.clip(a,0,1)


def hair_properties(config, radius_mm):
    """Map physical absorption to the radius-normalized Mitsuba 3.9.1 shader.

    Source audit: hair.cpp transmitted_length=2*cos(gamma_t)/cos(theta_t),
    with NO radius multiplier. Thus input sigma_a must be mu_a * radius.
    This wrapper deliberately follows pinned source rather than assuming the
    current docs' inverse-scene-unit description supplies that conversion.
    """
    c=config
    if c.absorption_per_mm<0 or not 0<c.longitudinal_roughness<1 or not 0<c.azimuthal_roughness<1:
        raise ValueError("passive absorption and roughness in (0,1) required")
    return {"type":"hair", "int_ior":c.ior, "ext_ior":1.,
            "sigma_a":{"type":"uniform", "value":c.absorption_per_mm*radius_mm},
            "longitudinal_roughness":c.longitudinal_roughness,
            "azimuthal_roughness":c.azimuthal_roughness,
            "scale_tilt":0.}


def scene_dictionary(curves_path, width_mm, radius_mm, config:RenderConfig):
    mi=get_mitsuba()
    c=config
    if c.mode not in ["reflection","transmission","furnace","hemisphere_reflection","hemisphere_transmission"]:
        raise ValueError("unknown render mode")
    half=.5*width_mm*c.width_fraction
    vo=direction(c.view_elevation_deg,c.view_azimuth_deg)
    # Project the chosen up axis to the view plane; stable at normal view.
    up=np.array([0.,1.,0.])
    if abs(np.dot(up,vo))>.95: up=np.array([0.,0.,1.])
    camera=mi.ScalarTransform4f().look_at(origin=vo*10*width_mm,
            target=[0,0,0],up=up).scale([half,half,1])
    scene={"type":"scene",
           "integrator":{"type":"path","max_depth":c.max_depth,"rr_depth":c.rr_depth},
           "sensor":{"type":"orthographic","to_world":camera,
                "sampler":{"type":"independent","sample_count":c.spp},
                "film":{"type":"hdrfilm","width":c.resolution,"height":c.resolution,
                        "pixel_format":"rgb","component_format":"float32",
                        "rfilter":{"type":"box"}}},
           "fibers":{"type":"bsplinecurve","filename":str(Path(curves_path).resolve()),
                     "bsdf":hair_properties(c,radius_mm)}}
    if c.mode=="furnace":
        scene["environment"]={"type":"constant","radiance":1.}
    elif c.mode.startswith("hemisphere_"):
        values=np.zeros((128,256,3),dtype=np.float32)
        if c.mode=="hemisphere_reflection": values[:64]=1.
        else: values[64:]=1.
        scene["environment"]={"type":"envmap","bitmap":mi.Bitmap(values),
                              "to_world":mi.ScalarTransform4f().rotate([1,0,0],90)}
    else:
        li=direction(c.light_elevation_deg,c.light_azimuth_deg)
        if c.mode=="transmission": li[2]*=-1
        # A finite area light; light_halfwidth_deg is an angular half-width
        # (rectangle geometry), not a Gaussian standard deviation.
        distance=20*width_mm
        source_half=distance*np.tan(np.deg2rad(c.light_halfwidth_deg))
        up_light=[0,1,0] if abs(li[1])<.95 else [1,0,0]
        tr=mi.ScalarTransform4f().look_at(origin=li*distance,target=[0,0,0],up=up_light)
        tr=tr.scale([source_half,source_half,1])
        # For a small distant square emitter, solid angle ~4a²/d². Set its
        # radiance so normal-incidence irradiance is approximately pi.
        # Exact comparable scenes reuse the same emitter geometry/radiance.
        omega=4*np.tan(np.deg2rad(c.light_halfwidth_deg))**2
        radiance=np.pi/max(omega,1e-10)
        scene["key"]={"type":"rectangle","to_world":tr,
                      "emitter":{"type":"area","radiance":float(radiance)}}
        if c.ambient>0:
            scene["environment"]={"type":"constant","radiance":c.ambient}
    return scene


def render_fabric(curves_path, width_mm, radius_mm, config:RenderConfig, output_prefix=None):
    mi=get_mitsuba()
    d=scene_dictionary(curves_path,width_mm,radius_mm,config)
    t=time.perf_counter()
    scene=mi.load_dict(d)
    build=time.perf_counter()-t
    t=time.perf_counter()
    image=np.array(mi.render(scene,seed=config.seed,spp=config.spp))
    elapsed=time.perf_counter()-t
    if not np.isfinite(image).all() or image.min()<-1e-6:
        raise RuntimeError("nonfinite or negative linear radiance")
    metadata={"render_config":asdict(config),"mitsuba_version":mi.__version__,
              "variant":mi.variant(),"scene_units":"mm", "width_mm":width_mm,
              "fiber_radius_mm":radius_mm,"sigma_a_shader":config.absorption_per_mm*radius_mm,
              "geometry_seconds":build,"render_seconds":elapsed,
              "mean_linear":float(image.mean()),"max_linear":float(image.max()),
              "display_clipped_fraction":float(np.mean(image*config.exposure>1)),
              "model":"Chiang2016 near-field BCSDF; explicit-fiber multiple ray scattering",
              "source_width_definition":"rectangle angular half-width; not Gaussian sigma"}
    if output_prefix:
        p=Path(output_prefix)
        p.parent.mkdir(parents=True,exist_ok=True)
        np.save(str(p)+"_linear.npy",image)
        Image.fromarray(np.round(encode_srgb(image,config.exposure)*255).astype(np.uint8)).save(str(p)+".png")
        Path(str(p)+".json").write_text(json.dumps(metadata,indent=2))
    return image,metadata


def normal_visibility_mask(curves_path,width_mm,resolution=512,width_fraction=.82):
    """Direct Embree ray visibility, including the actual rendered splines."""
    mi=get_mitsuba()
    c=RenderConfig(resolution=resolution,spp=1,width_fraction=width_fraction)
    scene=mi.load_dict({"type":"scene","fibers":{"type":"bsplinecurve", "filename":str(Path(curves_path).resolve())}})
    x=(np.arange(resolution)+.5)/resolution-.5
    xx,yy=np.meshgrid(x*width_mm*width_fraction,x*width_mm*width_fraction)
    rays=mi.Ray3f(mi.Point3f(xx.ravel(),yy.ravel(),np.full(xx.size,10*width_mm)),mi.Vector3f(0,0,-1))
    mask=np.asarray(~scene.ray_test(rays)).reshape(resolution,resolution)
    return mask.astype(float),width_mm*width_fraction*1000/resolution
