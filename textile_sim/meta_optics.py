"""Ideal prescribed-phase pupil and scalar Fresnel measurement emulator.

This is NOT a nanostructure Maxwell solver or a fabricated metalens prediction.
The same prescribed phase is used at every wavelength, like an idealized
geometric-phase target; actual polarization conversion/dispersion is unspecified.
All lengths are micrometres. Integrated scalar field power is the bookkeeping
quantity, valid as an optical-power approximation in the paraxial regime.
"""
from dataclasses import dataclass
from pathlib import Path
import json
import numpy as np
from scipy.special import j1


@dataclass
class PupilConfig:
    grid_size: int = 512
    pixel_um: float = .5
    radius_um: float = 25.
    focal_um: float = 250.
    design_wavelength_um: float = .55
    conversion_efficiency: float = .8


def coordinates(config):
    c=config
    if (c.grid_size<16 or c.pixel_um<=0 or c.radius_um<=0 or c.focal_um<=0 or
        c.design_wavelength_um<=0 or not 0<=c.conversion_efficiency<=1 or
        c.grid_size*c.pixel_um<=2*c.radius_um):
        raise ValueError("Positive physical dimensions, fitting pupil and efficiency in[0,1] required.")
    return (np.arange(c.grid_size)-c.grid_size//2)*c.pixel_um


def phase_pupil(config=PupilConfig(), targets_um=((0.,0.),), weights=None, levels=None):
    """Phase of a sum of desired focal fields, followed by phase-only projection.

    Targets are positions in the nominal focal plane at design wavelength.
    Equal four-corner targets form a simple phase grating on a focusing phase.
    Projection discards amplitude information and creates ghost diffraction
    orders; target weights are therefore NOT guaranteed achieved efficiencies.
    """
    c=config;x=coordinates(c);xx,yy=np.meshgrid(x,x)
    targets=np.asarray(targets_um,float)
    if targets.ndim!=2 or targets.shape[1]!=2 or len(targets)<1 or not np.isfinite(targets).all():
        raise ValueError("targets_um must contain finite(x,y) positions.")
    w=np.ones(len(targets)) if weights is None else np.asarray(weights,float)
    if w.shape!=(len(targets),) or not np.isfinite(w).all() or np.any(w<0) or w.sum()<=0:
        raise ValueError("Target weights must be nonnegative with positive sum.")
    w=w/w.sum();k0=2*np.pi/c.design_wavelength_um
    lens=-k0*(xx*xx+yy*yy)/(2*c.focal_um)
    desired=np.zeros(xx.shape,complex)
    for weight,(tx,ty) in zip(w,targets):
        desired+=np.sqrt(weight)*np.exp(1j*(lens+k0*(xx*tx+yy*ty)/c.focal_um))
    phase=np.angle(desired)
    phase=np.where(abs(desired)<1e-12,0.,phase)
    if levels is not None:
        if levels<2 or int(levels)!=levels:
            raise ValueError("Phase quantization needs an integer number of levels>=2.")
        phase=np.round(phase*levels/(2*np.pi))*(2*np.pi/levels)
    mask=xx*xx+yy*yy<=c.radius_um**2
    # Unit incident scalar power on the clear pupil; transmission is eta.
    field=mask*np.exp(1j*phase)*np.sqrt(c.conversion_efficiency/(mask.sum()*c.pixel_um**2))
    return {"x_um":x,"phase_rad":phase,"mask":mask,"field":field,
            "targets_um":targets,"weights":w,"config":c,"phase_levels":levels}


def fresnel_propagate(field,pixel_um,wavelength_um,distance_um,pad_factor=2,
                      incident_angle_deg=(0.,0.),method="fresnel"):
    """Unitary periodic-window scalar propagation with explicit spatial padding.

    Fresnel transfer function exp[-i*pi*lambda*z*(fx²+fy²)] has unit magnitude.
    Padding convergence is necessary to check periodic wraparound. An optional
    angular-spectrum calculation provides a scalar nonparaxial phase comparison;
    evanescent modes are suppressed and their L2 power loss is reported.
    """
    u=np.asarray(field,complex)
    if u.ndim!=2 or min(u.shape)<2 or not np.isfinite(u).all():
        raise ValueError("Provide a finite2D field.")
    if pixel_um<=0 or wavelength_um<=0 or distance_um<0 or pad_factor<1 or int(pad_factor)!=pad_factor:
        raise ValueError("Positive sampling,wavelength,padding and nonnegative distance required.")
    theta=np.asarray(incident_angle_deg,float)
    if theta.shape!=(2,) or not np.isfinite(theta).all():
        raise ValueError("incident_angle_deg is(theta_x,theta_y).")
    y=(np.arange(u.shape[0])-u.shape[0]//2)*pixel_um
    x=(np.arange(u.shape[1])-u.shape[1]//2)*pixel_um
    k=2*np.pi/wavelength_um
    u=u*np.exp(1j*k*(np.sin(np.deg2rad(theta[0]))*x[None,:]+
                      np.sin(np.deg2rad(theta[1]))*y[:,None]))
    original_power=float(np.sum(abs(u)**2)*pixel_um**2)
    shape=tuple(n*int(pad_factor) for n in u.shape)
    # Align the discrete physical origin, including odd-to-even grid changes.
    # floor((new-old)/2) would shift an odd input by one pixel on an even output.
    before=[shape[i]//2-u.shape[i]//2 for i in range(2)]
    pads=[(before[i],shape[i]-u.shape[i]-before[i]) for i in range(2)]
    u=np.pad(u,pads)
    fx=np.fft.fftfreq(shape[1],pixel_um);fy=np.fft.fftfreq(shape[0],pixel_um)
    q2=wavelength_um**2*(fy[:,None]**2+fx[None,:]**2)
    spectrum=np.fft.fft2(np.fft.ifftshift(u))
    spec_mass=abs(spectrum)**2*pixel_um**2/np.prod(shape)
    if method=="fresnel":
        transfer=np.exp(-1j*np.pi*distance_um/wavelength_um*q2)
    elif method=="angular_spectrum":
        transfer=np.exp(1j*k*distance_um*(np.sqrt(np.maximum(1-q2,0))-1))
        transfer=np.where(q2<=1,transfer,0)
    else:
        raise ValueError("method is fresnel or angular_spectrum")
    out=np.fft.fftshift(np.fft.ifft2(spectrum*transfer))
    power=abs(out)**2*pixel_um**2
    metadata={"method":method,"wavelength_um":float(wavelength_um),"distance_um":float(distance_um),
        "incident_angle_deg":theta.tolist(),"pixel_um":float(pixel_um),"pad_factor":int(pad_factor),
        "input_scalar_power":original_power,"output_scalar_power":float(power.sum()),
        "relative_energy_residual":float(abs(power.sum()-original_power)/max(original_power,1e-30)),
        "pupil_spectral_power_outside_10deg":float(spec_mass[q2>np.sin(np.deg2rad(10))**2].sum()),
        "evanescent_spectral_power":float(spec_mass[q2>1].sum()),
        "lost_scalar_power":max(0.,original_power-float(power.sum())),
        "scope":"Prescribed phase,scalar field; no unitcell/polarization/fabrication model"}
    return {"x_um":(np.arange(shape[1])-shape[1]//2)*pixel_um,
            "y_um":(np.arange(shape[0])-shape[0]//2)*pixel_um,
            "field":out,"power":power,"metadata":metadata}


def roi_measurements(result,centres_um,radius_um=4.):
    """Disjoint circular sensor ROIs; output is incident-power fraction per ROI.

    Ghost power means outside the declared ROIs in the modeled sensor window;
    it includes ordinary Airy tails and defocus, not exclusively unwanted orders.
    """
    if radius_um<=0:raise ValueError("Positive ROI radius required.")
    x,y=result["x_um"],result["y_um"]
    assignment=np.zeros(result["power"].shape,bool);values=[]
    for cx,cy in centres_um:
        mask=(x[None,:]-cx)**2+(y[:,None]-cy)**2<=radius_um**2
        if np.any(assignment&mask):raise ValueError("Measurement ROIs must not overlap.")
        assignment|=mask;values.append(float(result["power"][mask].sum()))
    total=float(result["power"].sum())
    return {"roi_power":np.asarray(values),"captured_power":float(sum(values)),
            "outside_roi_power":max(0.,total-sum(values)),"total_power":total,
            "roi_radius_um":radius_um}


def airy_intensity(x_um,wavelength_um,focal_um,radius_um):
    """Analytic normalized Airy intensity for a circular paraxial focusing pupil."""
    v=2*np.pi*radius_um*np.asarray(x_um)/(wavelength_um*focal_um)
    out=np.ones_like(v,float);nonzero=abs(v)>1e-12
    out[nonzero]=(2*j1(v[nonzero])/v[nonzero])**2
    return out


def run_meta_experiments(output_dir="data"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    output_dir=Path(output_dir);output_dir.mkdir(parents=True,exist_ok=True)
    c=PupilConfig();targets=[(-10,-10),(10,-10),(-10,10),(10,10)]
    lenses={"single":phase_pupil(c),"four":phase_pupil(c,targets)}
    wavelengths=(.45,.55,.65);angles=(-1.,0.,1.)
    rows=[];H=[];images={};energy=[];single_rows=[]
    fig,axes=plt.subplots(3,3,figsize=(10,9),constrained_layout=True)
    fig_single,axes_single=plt.subplots(3,3,figsize=(10,9),constrained_layout=True)
    for i,wl in enumerate(wavelengths):
        for j,angle in enumerate(angles):
            r=fresnel_propagate(lenses["four"]["field"],c.pixel_um,wl,c.focal_um,2,(angle,0))
            m=roi_measurements(r,targets,4.)
            H.append(m["roi_power"]);energy.append(r["metadata"])
            take_x=abs(r["x_um"])<=25;take_y=abs(r["y_um"])<=25
            density=r["power"][np.ix_(take_y,take_x)]/c.pixel_um**2
            images[f"psf_lambda{wl:.2f}_theta{angle:+.0f}"]=density
            images["sensor_x_um"]=r["x_um"][take_x]
            image=axes[i,j].imshow(np.log10(density+1e-10),origin="lower",extent=(-25.25,25.25,-25.25,25.25),
                                  cmap="magma",vmin=-6,vmax=-1.5)
            from matplotlib.patches import Circle
            for tx,ty in targets:axes[i,j].add_patch(Circle((tx,ty),4,fill=False,color="cyan",lw=.7))
            axes[i,j].set(title=f"{wl*1000:.0f} nm; incident x {angle:+.0f} deg",xlabel="sensor x(um)",ylabel="sensor y(um)")
            rows.append({"lambda_um":wl,"angle_x_deg":angle,"roi_powers":m["roi_power"].tolist(),
                "captured_power":m["captured_power"],"outside_roi_power":m["outside_roi_power"],
                "total_power":m["total_power"],"pupil_highangle_power":r["metadata"]["pupil_spectral_power_outside_10deg"]})
            single=fresnel_propagate(lenses["single"]["field"],c.pixel_um,wl,c.focal_um,2,(angle,0))
            sm=roi_measurements(single,[(0,0)],4.)
            single_rows.append({"lambda_um":wl,"angle_x_deg":angle,"captured_power":sm["captured_power"],
                                "outside_roi_power":sm["outside_roi_power"],"total_power":sm["total_power"]})
            sim=axes_single[i,j].imshow(np.log10(single["power"][np.ix_(take_y,take_x)]/c.pixel_um**2+1e-10),
                origin="lower",extent=(-25.25,25.25,-25.25,25.25),cmap="magma",vmin=-6,vmax=-1.5)
            axes_single[i,j].add_patch(Circle((0,0),4,fill=False,color="cyan",lw=.7))
            axes_single[i,j].set(title=f"{wl*1000:.0f}nm; incident x {angle:+.0f}deg",xlabel="sensor x(um)",ylabel="sensor y(um)")
    fig.colorbar(image,ax=axes.ravel().tolist(),shrink=.8,label="log10 incident-power fraction / um²")
    fig.suptitle("Prescribed phase-only four-focus pupil: fixed sensor plane\nCyan=detector ROIs; wavelength and incidence both move/spread spots; assumed efficiency0.8")
    fig.savefig(output_dir/"meta_psf_wavelength_angle.png",dpi=160);plt.close(fig)
    fig_single.colorbar(sim,ax=axes_single.ravel().tolist(),shrink=.8,label="log10 incident-power fraction / um²")
    fig_single.suptitle("Single-focus quadratic phase baseline: same fixed phase law across wavelength\nIdeal phase plate, not an achromatic refractive lens; same assumed efficiency0.8")
    fig_single.savefig(output_dir/"meta_single_lens_baseline.png",dpi=160);plt.close(fig_single)
    H=np.asarray(H).T
    singular=np.linalg.svd(H,compute_uv=False)
    normalized=H/np.maximum(np.linalg.norm(H,axis=0),1e-30)
    correlation=normalized.T@normalized
    labels=[f"{wl*1000:.0f}nm/{angle:+.0f}°" for wl in wavelengths for angle in angles]
    fig,axes=plt.subplots(1,2,figsize=(12,5),constrained_layout=True)
    im=axes[0].imshow(H,cmap="viridis",vmin=0,vmax=H.max(),aspect="auto")
    axes[0].set_xticks(range(9),labels,rotation=50,ha="right")
    axes[0].set_yticks(range(4),["lower left","lower right","upper left","upper right"])
    axes[0].set_title("Positive measurement H: 4 ROIs × 9 hypotheses")
    fig.colorbar(im,ax=axes[0],label="incident-power fraction")
    im=axes[1].imshow(correlation,vmin=0,vmax=1,cmap="magma")
    axes[1].set_xticks(range(9),labels,rotation=50,ha="right");axes[1].set_yticks(range(9),labels)
    axes[1].set_title("Normalized column similarity (1 = indistinguishable shape)")
    fig.colorbar(im,ax=axes[1])
    fig.suptitle("A four-spot optic does not automatically separate four colors or all angle/wavelength states")
    fig.savefig(output_dir/"meta_measurement_matrix.png",dpi=160);plt.close(fig)
    # One prescribed asymmetry ablation, not a search over designs.
    asymmetric_targets=[(-12.,-9.),(9.,-12.),(-7.,11.),(13.,8.)]
    asymmetric=phase_pupil(c,asymmetric_targets)
    H_asymmetric=[];asymmetric_conditions=[]
    for wl in wavelengths:
        for angle in angles:
            r=fresnel_propagate(asymmetric["field"],c.pixel_um,wl,c.focal_um,2,(angle,0))
            m=roi_measurements(r,asymmetric_targets,4.)
            H_asymmetric.append(m["roi_power"])
            asymmetric_conditions.append({"lambda_um":wl,"angle_x_deg":angle,
                "captured_power":m["captured_power"],"total_power":m["total_power"],
                "outside_roi_power":m["outside_roi_power"]})
    H_asymmetric=np.asarray(H_asymmetric).T
    singular_asymmetric=np.linalg.svd(H_asymmetric,compute_uv=False)
    fig,axes=plt.subplots(2,2,figsize=(12,8),constrained_layout=True)
    for ax,matrix,label in ((axes[0,0],H,"Symmetric four spots"),(axes[0,1],H_asymmetric,"One asymmetric four-spot design")):
        im=ax.imshow(matrix,cmap="viridis",vmin=0,vmax=max(H.max(),H_asymmetric.max()),aspect="auto")
        ax.set_xticks(range(9),labels,rotation=40,ha="right");ax.set_yticks(range(4),["ROI1","ROI2","ROI3","ROI4"])
        ax.set_title(label)
    fig.colorbar(im,ax=axes[0,:].tolist(),label="incident-power fraction")
    axes[1,0].semilogy(range(1,5),np.maximum(singular,1e-18),"o-",label="symmetric")
    axes[1,0].semilogy(range(1,5),np.maximum(singular_asymmetric,1e-18),"s-",label="asymmetric")
    axes[1,0].set(xlabel="singular-value index",ylabel="singular value",xticks=range(1,5),
                  title="Independent measured combinations, not complete recovery")
    axes[1,0].legend();axes[1,0].grid(alpha=.2)
    axes[1,1].plot(range(9),H.sum(axis=0),"o-",label="symmetric")
    axes[1,1].plot(range(9),H_asymmetric.sum(axis=0),"s-",label="asymmetric")
    axes[1,1].set_xticks(range(9),labels,rotation=40,ha="right")
    axes[1,1].set(ylabel="power captured by four ROIs",title="Same pupil,eta0.8,4 × radius4um ROIs")
    axes[1,1].legend();axes[1,1].grid(alpha=.2)
    fig.suptitle("Measurement design ablation: symmetry changes information without adding detector channels")
    fig.savefig(output_dir/"meta_symmetry_ablation.png",dpi=160);plt.close(fig)
    # Single-lens baseline and quantized phase variants, at the design wavelength.
    baseline=[];quant=[]
    fig,axes=plt.subplots(2,3,figsize=(11,7),constrained_layout=True)
    variants=[("single focus",lenses["single"],[(0.,0.)]),("four focus",lenses["four"],targets)]
    for count in (2,4,8,16):variants.append((f"four focus,{count}phase levels",phase_pupil(c,targets,levels=count),targets))
    for ax,(label,pupil,rois) in zip(axes.ravel(),variants):
        r=fresnel_propagate(pupil["field"],c.pixel_um,.55,c.focal_um,2)
        m=roi_measurements(r,rois,4)
        take=abs(r["x_um"])<=35
        im=ax.imshow(np.log10(r["power"][np.ix_(take,take)]/c.pixel_um**2+1e-10),origin="lower",
            extent=(-35.25,35.25,-35.25,35.25),cmap="magma",vmin=-6,vmax=-1.5)
        ax.set(title=f"{label}\nROI power={m['captured_power']:.3f}",xlabel="x(um)",ylabel="y(um)")
        q={"case":label,"roi_count":len(rois),"captured_power":m["captured_power"],
           "outside_roi_power":m["outside_roi_power"],"phase_levels":pupil["phase_levels"],
           "total_power":m["total_power"]}
        quant.append(q)
    fig.colorbar(im,ax=axes.ravel().tolist(),shrink=.8,label="log10 incident-power fraction / um²")
    fig.suptitle("Scalar phase-mask baselines and quantization; different ROI counts, not equal detector-area comparison")
    fig.savefig(output_dir/"meta_lens_quantization.png",dpi=160);plt.close(fig)
    # Numerical convergence focuses on the intended detector quantity, not only global Parseval.
    convergence=[]
    for pad in (1,2,4):
        cc=PupilConfig(grid_size=256,pixel_um=.5);p=phase_pupil(cc,targets)
        r=fresnel_propagate(p["field"],cc.pixel_um,.55,cc.focal_um,pad)
        m=roi_measurements(r,targets,4)
        convergence.append({"case":"padding","grid":cc.grid_size,"pixel_um":cc.pixel_um,"padding":pad,"roi_power":m["captured_power"]})
    for n,dx in ((256,.5),(512,.25)):
        cc=PupilConfig(grid_size=n,pixel_um=dx);p=phase_pupil(cc,targets)
        r=fresnel_propagate(p["field"],dx,.55,cc.focal_um,4)
        m=roi_measurements(r,targets,4)
        convergence.append({"case":"pupil_sampling","grid":n,"pixel_um":dx,"padding":4,"roi_power":m["captured_power"]})
    # Scalar angular-spectrum comparison flags the paraxial approximation in ghosts.
    r=fresnel_propagate(lenses["four"]["field"],c.pixel_um,.55,c.focal_um,2,method="angular_spectrum")
    as_roi=roi_measurements(r,targets,4)
    arrays={"H":H,"H_asymmetric":H_asymmetric,"column_similarity":correlation,"singular_values":singular,
            "singular_values_asymmetric":singular_asymmetric,"pupil_phase_rad":lenses["four"]["phase_rad"],
            "asymmetric_pupil_phase_rad":asymmetric["phase_rad"],"pupil_mask":lenses["four"]["mask"],**images}
    np.savez_compressed(output_dir/"meta_arrays.npz",**arrays)
    from dataclasses import asdict
    results={"pupil_config":asdict(c),"target_centres_um":targets,"roi_radius_um":4.,
        "hypotheses":labels,"measurement_matrix":H.tolist(),"column_sums":H.sum(axis=0).tolist(),
        "singular_values":singular.tolist(),"rank_at_1e_8_relative":int(np.sum(singular>singular[0]*1e-8)),
        "asymmetric_targets_um":asymmetric_targets,"asymmetric_H":H_asymmetric.tolist(),
        "asymmetric_singular_values":singular_asymmetric.tolist(),
        "asymmetric_rank_at_1e_8_relative":int(np.sum(singular_asymmetric>singular_asymmetric[0]*1e-8)),
        "asymmetric_nullspace_dimension_at_1e_8_relative":9-int(np.sum(singular_asymmetric>singular_asymmetric[0]*1e-8)),
        "asymmetric_conditions":asymmetric_conditions,
        "column_similarity":correlation.tolist(),"conditions":rows,"single_lens_conditions":single_rows,"phase_variants":quant,
        "convergence":convergence,"angular_spectrum_design_roi_power":as_roi["captured_power"],
        "maximum_energy_residual":max(e["relative_energy_residual"] for e in energy),
        "scope":"Ideal phase prescription; scalar Fresnel; no fabricated-device or material validation. Four ROI measurements cannot uniquely recover nine arbitrary component weights."}
    (output_dir/"meta_metrics.json").write_text(json.dumps(results,indent=2))
    return results


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--output",default="data")
    args=p.parse_args();print(json.dumps(run_meta_experiments(args.output),indent=2))
