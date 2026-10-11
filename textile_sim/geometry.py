"""Procedural fiber -> ply -> yarn -> woven cloth geometry, in millimeters.

The construction is geometric, not a textile manufacturing/mechanics solver.
Warp follows +y, weft +x. A weave matrix entry 1 means warp is above weft.
Different-fiber separation can be certified on the continuous rendered cubic
B-splines using conservative Bezier control-hull capsule bounds.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import json
import numpy as np
from scipy.spatial import cKDTree


def normalize(x, axis=-1):
    x = np.asarray(x, dtype=float)
    return x / np.maximum(np.linalg.norm(x, axis=axis, keepdims=True), 1e-30)


def weave_pattern(name: str) -> np.ndarray:
    """Plain, balanced 2/2 twill, or 5-end 4/1 warp-faced satin (step 2)."""
    if name == "plain":
        i, j = np.indices((2, 2))
        return ((i+j) % 2 == 0).astype(np.int8)
    if name == "twill":
        i, j = np.indices((4, 4))
        return ((j-i) % 4 < 2).astype(np.int8)
    if name == "satin":
        i, j = np.indices((5, 5))
        return ((j-2*i) % 5 != 0).astype(np.int8)
    raise ValueError("pattern must be plain, twill, or satin")


def periodic_crimp(s, fixed_index, family, pattern, pitch_mm, height_mm):
    """C1 interpolation of prescribed over-under crossing heights.

    At a crossing, both first derivatives are zero. This avoids spline
    overshoot but does not attempt to solve contact forces or yarn flattening.
    """
    s = np.asarray(s, dtype=float)
    q = s / pitch_mm
    j0 = np.floor(q).astype(int)
    u = q-j0
    n = pattern.shape[0]
    if family == "warp":
        b0 = pattern[j0 % n, fixed_index % n]
        b1 = pattern[(j0+1) % n, fixed_index % n]
        sign = 1.
    elif family == "weft":
        b0 = pattern[fixed_index % n, j0 % n]
        b1 = pattern[fixed_index % n, (j0+1) % n]
        sign = -1.
    else:
        raise ValueError("family must be warp or weft")
    z0, z1 = sign*height_mm*(2*b0-1), sign*height_mm*(2*b1-1)
    h = u*u*(3-2*u)
    return z0+(z1-z0)*h


def parallel_frames(points):
    """Rotation-minimizing frames along a polyline, without Frenet singularity."""
    p = np.asarray(points, dtype=float)
    t = normalize(np.gradient(p, axis=0))
    u = np.empty_like(t)
    reference = np.eye(3)[np.argmin(np.abs(t[0]))]
    u[0] = normalize(reference-np.dot(reference, t[0])*t[0])
    for k in range(1, len(t)):
        axis = np.cross(t[k-1], t[k])
        sin_a = np.linalg.norm(axis)
        cos_a = np.clip(np.dot(t[k-1], t[k]), -1., 1.)
        if sin_a > 1e-12:
            a = axis/sin_a
            prev = u[k-1]
            u[k] = (cos_a*prev+sin_a*np.cross(a, prev)
                    +(1-cos_a)*np.dot(a, prev)*a)
        else:
            u[k] = u[k-1]
        u[k] = normalize(u[k]-np.dot(u[k], t[k])*t[k])
    v = normalize(np.cross(t, u))
    return t, u, v


def arclength(points):
    d = np.linalg.norm(np.diff(points, axis=0), axis=1)
    return np.r_[0., np.cumsum(d)]


def hex_pack(rings=3, spacing_mm=0.018):
    """Exact centered hexagonal lattice, 1+3r(r+1) fiber centers."""
    if rings < 0 or spacing_mm <= 0:
        raise ValueError("rings>=0 and spacing>0 required")
    out = []
    for a in range(-rings, rings+1):
        for b in range(-rings, rings+1):
            if max(abs(a), abs(b), abs(a+b)) <= rings:
                out.append([spacing_mm*(a+0.5*b), spacing_mm*np.sqrt(3)/2*b])
    return np.asarray(out, dtype=float)


@dataclass
class FabricConfig:
    pattern: str = "plain"
    yarns_per_direction: int = 10
    pitch_mm: float = 0.20
    fiber_radius_mm: float = 0.004
    fiber_spacing_mm: float = 0.016
    fiber_rings: int = 3
    plies: int = 1
    ply_orbit_mm: float = 0.0
    ply_scale_u: float = 1.35
    ply_scale_v: float = 0.60
    fiber_twist_per_mm: float = 0.7
    ply_twist_per_mm: float = 0.35
    crimp_height_mm: float = 0.038
    samples_per_pitch: int = 18
    jitter_fraction: float = 0.0
    seed: int = 20261010

    def validate(self):
        weave_pattern(self.pattern)
        if self.plies not in [1, 2, 3]:
            raise ValueError("plies must be 1, 2, or 3")
        if self.fiber_radius_mm <= 0 or self.fiber_spacing_mm <= 2*self.fiber_radius_mm:
            raise ValueError("positive radius and nonoverlapping packing required")
        if self.fiber_spacing_mm*min(self.ply_scale_u,self.ply_scale_v) <= 2*self.fiber_radius_mm:
            raise ValueError("flattened packing would overlap")
        if self.yarns_per_direction < 2 or self.samples_per_pitch < 6:
            raise ValueError("too few yarns or axial samples")
        ply_r = self.fiber_rings*self.fiber_spacing_mm*max(self.ply_scale_u,self.ply_scale_v)+self.fiber_radius_mm
        if self.plies > 1 and 2*self.ply_orbit_mm*np.sin(np.pi/self.plies) <= 2*ply_r:
            raise ValueError("ply orbits overlap at equal axial position")
        yarn_r = ply_r + (self.ply_orbit_mm if self.plies > 1 else 0.)
        if self.pitch_mm <= 2*yarn_r:
            raise ValueError("neighboring yarn envelopes overlap laterally")
        vertical_r = (self.fiber_rings*self.fiber_spacing_mm*self.ply_scale_v+self.fiber_radius_mm
                      if self.plies==1 else yarn_r)
        if self.crimp_height_mm <= vertical_r:
            raise ValueError("crossing height cannot separate yarn envelopes")
        if not 0 <= self.jitter_fraction < .12:
            raise ValueError("jitter_fraction must be in [0,.12)")
        return self


def build_fabric(config: FabricConfig):
    """Return explicit fibers and parent centerlines in mm.

    A fiber is stored as a sequence of control points [x,y,z,r]. The rendered
    cubic B-spline approximates this polyline. Adjacent sampling convergence
    is tested separately, rather than assuming interpolation is exact.
    """
    c = config.validate()
    rng = np.random.default_rng(c.seed)
    pattern = weave_pattern(c.pattern)
    n = c.yarns_per_direction
    offset = .5*(n-1)*c.pitch_mm
    # One extra pitch beyond each visible boundary avoids exposed fiber tips.
    s = np.linspace(-c.pitch_mm, n*c.pitch_mm,
                    (n+1)*c.samples_per_pitch+1)
    packed = hex_pack(c.fiber_rings, c.fiber_spacing_mm)
    fibers, yarns, plies, labels = [], [], [], []
    for family in ["warp", "weft"]:
        for j in range(n):
            z = periodic_crimp(s, j, family, pattern, c.pitch_mm, c.crimp_height_mm)
            if family == "warp":
                yc = np.column_stack([np.full_like(s, j*c.pitch_mm-offset), s-offset, z])
            else:
                yc = np.column_stack([s-offset, np.full_like(s, j*c.pitch_mm-offset), z])
            yarns.append(yc)
            _, yu, yv = parallel_frames(yc)
            ya = arclength(yc)
            for p in range(c.plies):
                phase_y = 2*np.pi*(c.ply_twist_per_mm*ya + p/c.plies)
                orbit = c.ply_orbit_mm if c.plies > 1 else 0.
                pc = yc + orbit*(np.cos(phase_y)[:,None]*yu+np.sin(phase_y)[:,None]*yv)
                plies.append(pc)
                _, pu, pv = parallel_frames(pc)
                pa = arclength(pc)
                phase_f = 2*np.pi*c.fiber_twist_per_mm*pa
                cf, sf = np.cos(phase_f), np.sin(phase_f)
                for f, pos in enumerate(packed):
                    jitter = rng.uniform(-1, 1, 2)*c.jitter_fraction*c.fiber_spacing_mm
                    q = pos+jitter
                    fu = (q[0]*cf-q[1]*sf)*c.ply_scale_u
                    fv = (q[0]*sf+q[1]*cf)*c.ply_scale_v
                    fc = pc+fu[:,None]*pu+fv[:,None]*pv
                    rad = np.full(len(fc), c.fiber_radius_mm)
                    fibers.append(np.column_stack([fc, rad]))
                    labels.append([0 if family == "warp" else 1, j, p, f])
    return {"fibers":np.asarray(fibers), "yarns":np.asarray(yarns),
            "plies":np.asarray(plies), "labels":np.asarray(labels),
            "config":asdict(c), "weave_matrix":pattern,
            "visible_width_mm":n*c.pitch_mm}


def write_curves(path, fibers):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for curve in fibers:
            np.savetxt(f, curve, fmt="%.9g")
            f.write("\n")
    return path


def save_geometry(folder, geo):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    curves = write_curves(folder/"fibers.txt", geo["fibers"])
    np.savez_compressed(folder/"geometry.npz", fibers=geo["fibers"],
                        yarns=geo["yarns"], plies=geo["plies"], labels=geo["labels"],
                        weave_matrix=geo["weave_matrix"])
    (folder/"config.json").write_text(json.dumps(geo["config"], indent=2))
    return curves


def sampled_clearance(geo, samples_stride=1, max_points=250000):
    """Diagnostic nearest centers on different fibers, not a continuous proof.

    A strictly positive sampled clearance does NOT prove continuous curves
    nonintersecting. Axial refinement and an independent segment check are
    required when changing packing/twist; report the sampling used.
    """
    curves = geo["fibers"][:, ::samples_stride, :]
    # Query a modest neighborhood then exclude points on the same fiber.
    pts = curves[:,:,:3].reshape(-1,3)
    ids = np.repeat(np.arange(len(curves)), curves.shape[1])
    radii = curves[:,:,3].ravel()
    if len(pts)>max_points:
        ix = np.linspace(0, len(pts)-1, max_points, dtype=int)
    else:
        ix = np.arange(len(pts))
    tree=cKDTree(pts)
    d, near=tree.query(pts[ix], k=24, workers=1)
    different=ids[near] != ids[ix,None]
    clear=np.where(different, d-radii[ix,None]-radii[near], np.inf)
    best=np.min(clear, axis=1)
    return {"minimum_sampled_clearance_mm":float(np.min(best)),
            "sampled_overlap_fraction":float(np.mean(best<0)),
            "query_points":len(ix), "axial_stride":samples_stride,
            "caveat":"Discrete centers only; does not certify continuous tube separation."}


def segment_distance(p0,p1,q0,q1):
    """Exact minimum distances for batches of line segment pairs."""
    u,v,w=p1-p0,q1-q0,p0-q0
    a=np.sum(u*u,axis=-1); b=np.sum(u*v,axis=-1); c=np.sum(v*v,axis=-1)
    d=np.sum(u*w,axis=-1); e=np.sum(v*w,axis=-1)
    det=a*c-b*b
    ss=np.divide(b*e-c*d,det,out=np.zeros_like(det),where=det>1e-28)
    tt=np.divide(a*e-b*d,det,out=np.zeros_like(det),where=det>1e-28)
    valid=(det>1e-28)&(ss>=0)&(ss<=1)&(tt>=0)&(tt<=1)
    interior=np.linalg.norm(w+ss[...,None]*u-tt[...,None]*v,axis=-1)
    candidates=[np.where(valid,interior,np.inf)]
    for p in [p0,p1]:
        t=np.clip(np.sum((p-q0)*v,axis=-1)/np.maximum(c,1e-30),0,1)
        candidates.append(np.linalg.norm(p-q0-t[...,None]*v,axis=-1))
    for q in [q0,q1]:
        s=np.clip(np.sum((q-p0)*u,axis=-1)/np.maximum(a,1e-30),0,1)
        candidates.append(np.linalg.norm(q-p0-s[...,None]*u,axis=-1))
    return np.min(candidates,axis=0)


def _spline_beziers(fibers):
    p=fibers[:,:,:3]
    p0,p1,p2,p3=p[:,:-3],p[:,1:-2],p[:,2:-1],p[:,3:]
    q=np.stack([(p0+4*p1+p2)/6,(2*p1+p2)/3,
                (p1+2*p2)/3,(p1+4*p2+p3)/6],axis=2)
    return q


def certify_spline_clearance(geo, subdivision=1, probe_margin_mm=.004, batch_size=100000):
    """Conservative separation certificate for DIFFERENT constant-radius fibers.

    Convert every uniform cubic B-spline segment to its Bezier control polygon.
    Its entire curve lies in the convex hull, hence inside the endpoint chord
    capsule enlarged by max distance of the two middle control points to that
    chord. Exact segment distances between inflated capsules prove separation.
    If a bound <=0, this is a failed certificate, not proof of an intersection.
    Subdivision reduces conservatism. Same-fiber local self overlap is excluded.
    """
    curves=np.asarray(geo["fibers"])
    if not np.allclose(curves[:,:,3],curves[:,0:1,3],rtol=0,atol=1e-14):
        raise ValueError("certificate currently assumes constant fiber radius")
    q=_spline_beziers(curves)
    for _ in range(subdivision):
        a=(q[:,:,0]+q[:,:,1])/2; b=(q[:,:,1]+q[:,:,2])/2; c=(q[:,:,2]+q[:,:,3])/2
        d=(a+b)/2; e=(b+c)/2; f=(d+e)/2
        left=np.stack([q[:,:,0],a,d,f],axis=2)
        right=np.stack([f,e,c,q[:,:,3]],axis=2)
        q=np.stack([left,right],axis=2).reshape(len(q),-1,4,3)
    count=q.shape[1]
    ids=np.repeat(np.arange(len(q)),count)
    radii=np.repeat(curves[:,0,3],count)
    q=q.reshape(-1,4,3)
    a,b=q[:,0],q[:,3]
    chord=b-a
    l2=np.sum(chord*chord,axis=-1)
    deviations=[]
    for j in [1,2]:
        t=np.clip(np.sum((q[:,j]-a)*chord,axis=-1)/np.maximum(l2,1e-30),0,1)
        deviations.append(np.linalg.norm(q[:,j]-a-t[:,None]*chord,axis=-1))
    err=np.maximum(*deviations)
    inflated=radii+err
    length=np.sqrt(l2)
    midpoint=(a+b)/2
    search=2*float(np.max(inflated))+float(np.max(length))+probe_margin_mm
    pairs=cKDTree(midpoint).query_pairs(search,output_type="ndarray")
    pairs=pairs[ids[pairs[:,0]]!=ids[pairs[:,1]]]
    minimum=np.inf; unresolved=0; checked=0
    for k in range(0,len(pairs),batch_size):
        p=pairs[k:k+batch_size]
        i,j=p[:,0],p[:,1]
        d=segment_distance(a[i],b[i],a[j],b[j])-inflated[i]-inflated[j]
        minimum=min(minimum,float(np.min(d,initial=np.inf)))
        unresolved+=int(np.sum(d<=0));checked+=len(p)
    # All omitted pairs have clearance greater than probe_margin_mm by the
    # triangle inequality and the conservative global search radius above.
    bound=min(minimum,probe_margin_mm)
    return {"certified_separated":bool(bound>0),
            "minimum_clearance_lower_bound_mm":float(bound),
            "max_curve_to_chord_bound_mm":float(err.max()),
            "unresolved_capsule_pairs":unresolved,"tested_pairs":checked,
            "segments":len(a),"bezier_subdivisions":subdivision,
            "scope":"All pairs of DIFFERENT constant-radius cubic B-spline fibers; excludes same-fiber self-intersections."}


def project_gap_mask(geo, resolution=512, width_mm=None):
    """Approximate projected open AREA FRACTION for geometry previews.

    This supersampled polyline rasterizer is not a conservative continuous-
    spline visibility certificate and does not return a coherent amplitude.
    Squaring its fractional pixels in a wave solver would incorrectly apply
    area fractions twice. The executed diffraction pipeline instead uses the
    binary ray-intersection mask from render.normal_visibility_mask.
    """
    from PIL import Image, ImageDraw
    width=width_mm or geo["visible_width_mm"]
    # Supersampling gives a deterministic area-fraction approximation.
    scale=2
    size=resolution*scale
    im=Image.new("L", (size,size), 0)
    draw=ImageDraw.Draw(im)
    for curve in geo["fibers"]:
        xy=(curve[:,:2]/width+.5)*size
        diameter=max(1, round(2*np.max(curve[:,3])/width*size))
        draw.line([tuple(q) for q in xy], fill=255, width=diameter, joint="curve")
    arr=np.asarray(im,dtype=float)/255.
    cover=arr.reshape(resolution,scale,resolution,scale).mean(axis=(1,3))
    return 1.-cover, width*1000/resolution
