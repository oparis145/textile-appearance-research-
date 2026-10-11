# v0.5 Scene-scale sensitivity: independent audit source

This saved audit checks the 72-run experiment from raw arrays and saved buffers. Statistics and file identities are computed without importing the producer's statistical or hashing helpers. Three fresh two-fiber backend scenes then check actual Mitsuba buffers and medium parameters; this adds **zero renders**.

Run from the repository root with the Python block below. It refuses to overwrite an earlier audit summary. The saved output is `data/validation_v5/independent_scale_audit/verification_summary.json`.

An exploratory API probe initially tried `MaterialSpectrum.from_dict`, which does not exist. It created no scene and no output. The corrected constructor is `MaterialSpectrum(**payload)`, verified from installed project code. This audit uses the corrected constructor.

<!-- BEGIN AUDIT CODE -->
```python
import hashlib, json, math, zipfile
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
from scipy.stats import t

root = Path.cwd()
base = root/"data/validation_v5/volume_scale_sensitivity"
main = root/"data/variable_radius_v5"
out = root/"data/validation_v5/independent_scale_audit"
out.mkdir(parents=True, exist_ok=True)
target = out/"verification_summary.json"
if target.exists():
    raise FileExistsError("The independent audit never overwrites an earlier result")
checks = []
def require(condition, label):
    if not bool(condition):
        raise AssertionError(label)
    checks.append(label)
def read(p):
    return json.loads(Path(p).read_text())
def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def canonical(x):
    return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False)
def array_hash(a):
    a = np.ascontiguousarray(a)
    h = hashlib.sha256(canonical([a.shape,a.dtype.str]).encode("ascii"))
    h.update(a.tobytes())
    return h.hexdigest()
def ci(x, family=1):
    x = np.asarray(x, dtype=np.float64)
    mean = math.fsum(map(float,x))/len(x)
    variance = math.fsum((float(z)-mean)**2 for z in x)/(len(x)-1)
    se = math.sqrt(variance/len(x))
    critical = float(t.ppf(1-.05/(2*family),len(x)-1))
    return {"mean_delta":mean,"interval_low":mean-critical*se,
            "interval_high":mean+critical*se,"standard_error":se,
            "family_size":family,"seed_count":len(x),
            "interval_excludes_zero":abs(mean)>critical*se}
def volume(v,f):
    v = np.asarray(v,dtype=np.float64)
    q = v-v.mean(axis=0)
    return float(np.einsum("ij,ij->i",q[f[:,0]],
        np.cross(q[f[:,1]],q[f[:,2]])).sum()/6)

manifest = read(base/"experiment_manifest.json")
metrics = read(base/"sensitivity_metrics.json")
main_metrics = read(main/"optics/optical_metrics.json")
scales,states,lights = metrics["scales"],metrics["states"],metrics["lights"]
seeds = metrics["seeds"]
require(scales==[1.,10.,100.] and len(states)==2 and len(lights)==3 and
        len(set(seeds))==4, "fixed 3 x 2 x 3 x 4 experiment design")
require(manifest["status"]=="passed" and manifest["actual_render_calls"]==72,
        "completed 72 calls")
for path,expected in manifest["producer_source_sha256"].items():
    require(sha(root/path)==expected==manifest["producer_source_sha256_after"][path],
            "immutable source: "+path)
for path,entry in manifest["output_files"].items():
    require(sha(base/path)==entry["sha256"] and (base/path).stat().st_size==entry["bytes"],
            "output file hash and length: "+path)
for path,expected in manifest["input_snapshot_sha256"].items():
    require(sha(base/"inputs"/path)==expected,"input snapshot: "+path)
    if path!="optics/optical_metrics.json":
        require(sha(main/path)==expected,"final canonical input: "+path)
snapshot_metrics = read(base/"inputs/optics/optical_metrics.json")
for name in ("union_bounds_mm","lighting_configs","seeds"):
    require(snapshot_metrics[name]==main_metrics[name],"canonical configuration: "+name)
npz_files = []
for path in sorted(base.rglob("*.npz")):
    with zipfile.ZipFile(path) as archive:
        require(archive.testzip() is None,"NPZ CRC: "+str(path.relative_to(base)))
    npz_files.append(str(path.relative_to(base)))
with np.load(base/"scalar_radiance.npz",allow_pickle=False) as archive:
    raw = archive["radiance"]
    require(archive["scales"].tolist()==scales and archive["seeds"].tolist()==seeds,
            "raw coordinate arrays")
require(raw.shape==(3,2,3,4,64,64) and raw.dtype==np.float32 and
        np.isfinite(raw).all() and (raw>=0).all(),"raw shape dtype finite nonnegative")
means = np.empty((3,2,3,4),dtype=np.float64)
for idx in np.ndindex(3,2,3,4):
    means[idx] = math.fsum(map(float,raw[idx].ravel()))/(64*64)
require(np.allclose(means,metrics["mean_radiance_per_seed"],rtol=0,atol=2e-17),
        "all 72 seed means independently recomputed")
scenes = {}
for scale in scales:
    for state in states:
        for light in lights:
            key=(scale,state,light)
            scene=read(base/"scenes"/f"scale_{scale:g}__{state}__{light}.json")
            identity={k:v for k,v in scene.items() if k not in ("scene_sha256","scene_build_seconds")}
            require(hashlib.sha256(canonical(identity).encode()).hexdigest()==scene["scene_sha256"],
                    "scene semantic identity: "+str(key))
            scenes[key]=scene
indices=set()
for record in metrics["records"]:
    idx=tuple(record["array_index"])
    require(idx not in indices, "unique render record: "+str(idx))
    indices.add(idx)
    si,st,li,ri=idx
    rgb=np.repeat(raw[idx][...,None],3,axis=-1)
    require(array_hash(rgb)==record["raw_float32_sha256"],"raw RGB reconstruction hash: "+str(idx))
    require(record["scene_sha256"]==scenes[(scales[si],states[st],lights[li])]["scene_sha256"]
            and record["seed"]==seeds[ri] and record["spp"]==64,
            "render record scene/seed binding: "+str(idx))
require(len(indices)==72,"72 distinct condition indices")

# Recompute each statistical contrast from raw images, not producer statistics.
comparisons=[]
max_interval_difference=0.
for row in metrics["comparisons"]:
    li=lights.index(row["light"])
    if row["kind"]=="radius_effect":
        si=scales.index(row["scale"])
        delta=means[si,1,li]-means[si,0,li]
        denominator=float(means[si,0,li].mean())
        family=3 if si==2 else None
    else:
        a,b=scales.index(row["before_scale"]),scales.index(row["after_scale"])
        if row["kind"]=="numerical_scale":
            st=states.index(row["state"])
            delta=means[b,st,li]-means[a,st,li]
            denominator=float(means[a,st,li].mean())
            family=18
        else:
            delta=(means[b,1,li]-means[b,0,li])-(means[a,1,li]-means[a,0,li])
            denominator=None
            family=9
    require(np.allclose(delta,row["paired_seed_differences"],rtol=0,atol=5e-17),
            "raw paired differences: "+str(len(comparisons)))
    check={"kind":row["kind"],"light":row["light"],
           "paired_seed_differences":delta.tolist(),"pointwise_95":ci(delta)}
    for key in ("scale","before_scale","after_scale","state"):
        if key in row: check[key]=row[key]
    if denominator is not None:
        relative=100*float(delta.mean())/denominator
        check["relative_mean_change_percent"]=relative
        require(abs(relative-row["relative_mean_change_percent"])<1e-11,"relative point estimate")
    if family is not None:
        check["family_adjusted"]=ci(delta,family)
    for kind in ("pointwise_95","family_adjusted"):
        if kind not in check: continue
        expected=row[kind]
        for key in ("mean_delta","interval_low","interval_high","standard_error"):
            difference=abs(check[kind][key]-expected[key])
            max_interval_difference=max(max_interval_difference,difference)
            require(difference<1e-14,"independent "+kind+" "+key)
        require(check[kind]["interval_excludes_zero"]==expected["interval_excludes_zero"],
                "interval decision agrees")
    comparisons.append(check)

# Independently validate actual float32 geometry against physical profiles.
geometry_rows=[]
canonical_geometry=[]
for st,state in enumerate(states):
    with np.load(base/"inputs/profiles"/state/"variable_radius_profiles.npz") as archive:
        profiles={k:archive[k] for k in archive.files}
    with np.load(base/"geometry/scale_1"/state/"renderer_buffers.npz") as archive:
        baseline={k:archive[k] for k in archive.files}
    with np.load(main/"meshes/radial_064"/state/"renderer_buffers.npz") as archive:
        canonical_buffers={k:archive[k] for k in archive.files}
    maximum_main_difference=0.
    for fi in range(42):
        key=f"fiber_{fi:04d}"
        require(np.array_equal(baseline[key+"/faces"],canonical_buffers[key+"/faces"]),
                "S1/canonical triangle identity")
        difference=float(np.max(np.abs(baseline[key+"/vertices_numerical"]-
                                       canonical_buffers[key+"/vertices_mm"])))
        maximum_main_difference=max(maximum_main_difference,difference)
    require(maximum_main_difference==0,"S1/canonical all float32 vertices identical")
    canonical_geometry.append({"state":state,"all_42_meshes_bitwise_identical":True})
    for scale in scales:
        folder=base/"geometry"/f"scale_{scale:g}"/state
        mapping=read(folder/"geometry_mapping.json")
        require(sha(folder/"renderer_buffers.npz")==mapping["array_file_sha256"],
                "geometry inner file identity")
        center_error=radius_error=physical_vertex_error=volume_relative_error=0.
        with np.load(folder/"renderer_buffers.npz") as archive:
            for fi,row in enumerate(mapping["fibers"]):
                key=f"fiber_{fi:04d}"
                pkey=f"fiber_{fi:05d}"
                v,f=archive[key+"/vertices_numerical"],archive[key+"/faces"]
                require(v.dtype==np.float32 and f.dtype==np.uint32 and np.isfinite(v).all(),
                        "saved renderer dtype: "+str((scale,state,fi)))
                require(array_hash(v)==row["buffer_audit_numerical_units"]["vertices_float32_sha256"]
                        and array_hash(f)==row["buffer_audit_numerical_units"]["faces_uint32_sha256"],
                        "saved buffer semantic digest")
                require(np.array_equal(f,baseline[key+"/faces"]),"scale-independent faces")
                points=profiles[pkey+"/points_mm"]
                radius=profiles[pkey+"/node_radius_mm"]
                physical=np.asarray(v,dtype=np.float64)/scale
                rings=physical[:-2].reshape(len(points),64,3)
                center_error=max(center_error,float(np.max(np.linalg.norm(rings.mean(1)-points,axis=1))))
                radii=np.linalg.norm(rings-points[:,None,:],axis=2)
                radius_error=max(radius_error,float(np.max(np.abs(radii-radius[:,None]))))
                physical_vertex_error=max(physical_vertex_error,float(np.max(np.abs(
                    physical-np.asarray(baseline[key+"/vertices_numerical"],dtype=np.float64)))))
                current=volume(v,f)/scale**3
                original=volume(baseline[key+"/vertices_numerical"],f)
                require(current>0 and original>0,"positive oriented volume")
                volume_relative_error=max(volume_relative_error,abs(current/original-1))
                for light in lights:
                    sr=scenes[(scale,state,light)]["meshes"][fi]
                    require(sr["fiber_id"]==row["fiber_id"] and
                        sr["buffer_audit"]["vertices_float32_sha256"]==array_hash(v) and
                        sr["buffer_audit"]["faces_uint32_sha256"]==array_hash(f),
                        "saved scene/geometry buffer binding")
        require(center_error<1e-7 and radius_error<1e-7 and physical_vertex_error<1e-7,
                "physical float32 coordinate/radius agreement within 1e-7 mm")
        require(volume_relative_error<1e-5,"normalized float32 volume relative error below 1e-5")
        geometry_rows.append({"scale":scale,"state":state,"mesh_count":42,
            "max_ring_center_error_physical_mm":center_error,
            "max_ring_radius_error_physical_mm":radius_error,
            "max_vertex_difference_from_scale1_physical_mm":physical_vertex_error,
            "max_volume_difference_from_scale1_fraction":volume_relative_error})

physical_materials={x["material_id"]:x for x in read(base/"inputs/optics/synthetic_material_spectra.json")}
material_rows=[]
for scale in scales:
    derived={x["material_id"]:x for x in read(base/"materials"/f"scale_{scale:g}.json")}
    for key,physical in physical_materials.items():
        numerical=derived[key]
        require(numerical["wavelength_nm"]==physical["wavelength_nm"] and
                numerical["n_real"]==physical["n_real"],"unchanged wavelength and real index")
        k=np.asarray(numerical["kappa"])
        require(np.allclose(k*scale,physical["kappa"],rtol=2e-16,atol=1e-18),
                "inverse-scale complete kappa table")
        wavelengths=np.asarray(physical["wavelength_nm"])
        mu=4*np.pi*np.interp(550.,wavelengths,physical["kappa"])/(550.e-6)
        numerical_mu=4*np.pi*np.interp(550.,wavelengths,k)/(550.e-6)
        material_rows.append({"scale":scale,"material_id":key,"physical_mu_per_mm":float(mu),
                              "numerical_sigma_t":float(numerical_mu),
                              "relative_mu_length_mapping_error":float(numerical_mu*scale/mu-1)})
        for state in states:
            for light in lights:
                sm=scenes[(scale,state,light)]["materials"][key]
                require(sm["material"]==numerical and abs(sm["sigma_t_per_scene_unit"]-mu/scale)<1e-12
                        and sm["albedo"]==0 and sm["n_real"]==float(np.interp(550.,wavelengths,physical["n_real"])),
                        "scene boundary and absorption mapping")
    for state in states:
        for light in lights:
            before=scenes[(1.,state,light)]
            after=scenes[(scale,state,light)]
            for key in ("bounds_mm","center_mm","span_mm","film_width_mm","camera_distance_mm"):
                require(np.allclose(np.asarray(after["rig"][key])/scale,before["rig"][key],
                                    rtol=0,atol=2e-14),"scaled camera/bounds: "+key)
            require(after["rig"]["view_direction"]==before["rig"]["view_direction"] and
                    after["render_config"]==before["render_config"],"identical directions/config")
            sa,sb=after["rig"]["source"],before["rig"]["source"]
            for key in ("distance_mm","half_width_mm"):
                require(abs(sa[key]/scale-sb[key])<2e-14,"scaled light geometry")
            for key in ("radiance","mode","direction_from_center"):
                require(sa[key]==sb[key],"unchanged light radiance/direction")

# Actual API reconstruction checks. This uses the frozen geometry/scene API,
# but independent raw/hash/statistics above use no producer helper.
# Three small scenes, two original fibers per scene; zero new renders.
from dataclasses import replace
from textile_sim.variable_radius import load_variable_radius_profiles,build_tapered_tube
from textile_sim.optical_scene import MaterialSpectrum
from textile_sim.render import RenderConfig,get_mitsuba
from textile_sim.volume_optics import build_volume_scene
original=load_variable_radius_profiles(base/"inputs/profiles/constant_reference")
selected={}
for i,p in enumerate(original):
    selected.setdefault(p.material_id,(i,p))
runtime_rows=[]
mi=get_mitsuba()
for scale in scales:
    profiles=[replace(p,points_mm=p.points_mm*scale,
        material_coordinates_mm=p.material_coordinates_mm*scale,
        parent_material_coordinates_mm=p.parent_material_coordinates_mm*scale,
        segment_radius_mm=p.segment_radius_mm*scale) for _,p in selected.values()]
    meshes=[build_tapered_tube(p,radial_segments=64,initial_normal=(0,0,1)) for p in profiles]
    materials=[MaterialSpectrum(**x) for x in read(base/"materials"/f"scale_{scale:g}.json")]
    meta=scenes[(scale,"constant_reference","R0")]
    handle,_=build_volume_scene(meshes,materials,550.,
        RenderConfig(**meta["render_config"]),bounds_mm=meta["rig"]["bounds_mm"])
    params=mi.traverse(handle.backend_scene)
    with np.load(base/"geometry"/f"scale_{scale:g}"/"constant_reference/renderer_buffers.npz") as archive:
        for i,((key,(original_index,_)),p) in enumerate(zip(selected.items(),profiles)):
            prefix=f"fiber_{i:04d}"
            source_prefix=f"fiber_{original_index:04d}"
            actual_v=np.asarray(params[prefix+".vertex_positions"]).reshape(-1,3)
            actual_f=np.asarray(params[prefix+".faces"]).reshape(-1,3)
            require(np.array_equal(actual_v,archive[source_prefix+"/vertices_numerical"]) and
                    np.array_equal(actual_f,archive[source_prefix+"/faces"]),
                    "actual backend buffers match saved buffers")
            eta=float(np.asarray(params[prefix+".bsdf.eta"]))
            sigma=float(np.asarray(params[prefix+".interior_medium.sigma_t.value.value"])[0])
            albedo=float(np.asarray(params[prefix+".interior_medium.albedo.value.value"])[0])
            expected=meta["materials"][key]
            require(abs(eta/expected["n_real"]-1)<1e-6 and
                    abs(sigma/expected["sigma_t_per_scene_unit"]-1)<1e-6 and albedo==0.,
                    "actual backend eta/sigma/albedo")
            runtime_rows.append({"scale":scale,"material_id":key,"actual_eta_float32":eta,
                "actual_sigma_t_float32":sigma,"albedo":albedo,
                "sigma_relative_rounding_error":sigma/expected["sigma_t_per_scene_unit"]-1,
                "all_vertices_and_faces_match_saved":True})
    del params,handle,meshes

with np.load(main/"optics/spectral_radiance.npz") as archive:
    canonical_raw=archive["radiance"]
ri=main_metrics["radial_segments"].index(64)
wi=main_metrics["wavelengths_nm"].index(550.)
slice_main=canonical_raw[ri,:,:,wi]
require(np.array_equal(raw[0],slice_main),"all 24 S1/canonical raw images bitwise identical")
for path,expected in manifest["producer_source_sha256"].items():
    require(sha(root/path)==expected,"source unchanged after audit: "+path)
source_note=root/"notes/volume_scale_sensitivity_v5_audit.md"
source_code=source_note.read_text().split("<!-- BEGIN AUDIT CODE -->\n"+chr(96)*3+"python\n",1)[1].split(chr(96)*3,1)[0]
result={"schema":"textile.independent_scene_scale_audit/5.0","status":"passed",
    "audit_utc":datetime.now(timezone.utc).isoformat(),
    "scope":"independent saved-data/statistical audit plus three small backend reconstructions; not a physical convergence certificate",
    "audit_source_code_sha256":hashlib.sha256(source_code.encode()).hexdigest(),
    "producer_manifest_sha256":sha(base/"experiment_manifest.json"),
    "raw_file_sha256":sha(base/"scalar_radiance.npz"),
    "canonical_main_raw_file_sha256":sha(main/"optics/spectral_radiance.npz"),
    "producer_source_sha256":manifest["producer_source_sha256"],
    "checks_passed":len(checks),"npz_crc_checked":npz_files,
    "output_file_count_checked":len(manifest["output_files"]),
    "source_file_count_checked":len(manifest["producer_source_sha256"]),
    "raw_images_audited":72,"scene_metadata_audited":18,
    "geometry_mesh_instances_audited":252,
    "additional_actual_render_calls":0,"actual_backend_reconstructed_scenes":3,
    "runtime_material_and_buffer_audit":runtime_rows,
    "geometry_audit":geometry_rows,"materials_audit":material_rows,
    "canonical_geometry":canonical_geometry,
    "canonical_overlap":{"conditions":24,"all_raw_bitwise_equal":True,"maximum_absolute_raw_difference":0.,
        "independent_seed_count_increased":False},
    "mean_radiance_per_seed":means.tolist(),
    "independently_recomputed_comparisons":comparisons,
    "maximum_interval_discrepancy":max_interval_difference,
    "trial_count_statement":"Three accepted experiments contain 216 + 32 + 72 = 320 actual render calls. Twenty-four S1 conditions repeat canonical N64/550-nm conditions with the same seeds and identical raw arrays. These repeats add no independent replicates; no unique-image count is claimed.",
    "limits":["Four seed-level replicates per condition, not independent pixel replicates.",
              "Zero in a difference interval is not an equivalence or convergence result.",
              "Geometry unit similarity is exact only within float32 representation and renderer numerical constants.",
              "The proxy kappa scale preserves this real-Fresnel/pure-absorption ray model, not complex-Fresnel or Maxwell scattering.",
              "Saved scene records prove producer bindings under source ledger; reconstruction is a fresh API check, not a retained historical scene object."]}
target.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
print(json.dumps({"status":result["status"],"checks":len(checks),"npz_count":len(npz_files),
    "additional_renders":0,"output":str(target),"max_interval_discrepancy":max_interval_difference,
    "geometry_audit":geometry_rows,"actual_backend_checks":runtime_rows},indent=2))
```
