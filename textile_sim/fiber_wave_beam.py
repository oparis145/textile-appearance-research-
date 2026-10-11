"""Coherent Gaussian angular-spectrum illumination of exact 2-D fibers.

Independent extension of fiber_wave's checked cylinder coefficients.  This
is an exact propagating Helmholtz angular spectrum evaluated by quadrature,
not a scalar diffraction correction added to geometric rays.  A Gaussian
amplitude exp[-(y-y0)^2/w0^2] at x=0 has paraxial irradiance sigma=w0/2.

The incident continuum has finite power. A finite quadrature sum of plane
waves is only a local approximation to that continuum; its global plane-wave
norm must NOT be used to define beam power. The continuum power integral is
computed separately and checked against numerical line Poynting flux.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
import numpy as np
from scipy.special import roots_hermite, roots_legendre, hankel1
from scipy.linalg import lu_factor, lu_solve

from .fiber_wave import cylinder_coefficients, _cluster_far_field


def gaussian_spectrum(wavelength_um=.55, waist_um=10., offset_um=0., waist_x_um=0., n_quad=64):
    """Return coherent quadrature nodes and exact-continuum incident power.

    u(x,y) = integral A(q) exp[i(kx*(x-x0)+q*(y-y0))] dq/(2*pi),
    A(q)=sqrt(pi)*w0*exp(-w0^2*q^2/4), kx=sqrt(k^2-q^2)>0.
    The negligible evanescent Gaussian tail is excluded. This implementation
    requires w0>=5*lambda; it does not claim a tightly focused vector beam.
    """
    lam,w0,y0,x0 = map(float,(wavelength_um,waist_um,offset_um,waist_x_um))
    if not np.all(np.isfinite([lam,w0,y0,x0])) or lam<=0 or w0<5*lam:
        raise ValueError("Require finite wavelength>0 and waist>=5*wavelength")
    if int(n_quad)!=n_quad or n_quad<8:
        raise ValueError("n_quad must be an integer >=8")
    k=2*np.pi/lam
    nodes,gh=roots_hermite(int(n_quad))
    q=2*nodes/w0
    keep=np.abs(q)<k
    omitted_weight=float(np.sum(gh[~keep])/np.sqrt(np.pi))
    if omitted_weight>1e-14:
        raise ValueError("Propagating-spectrum truncation is unresolved at this waist/order")
    q=q[keep]; weights=gh[keep]/np.sqrt(np.pi)
    kx=np.sqrt(k*k-q*q)
    # Parseval of the continuous field with flux factor kx/k, using a distinct
    # Hermite quadrature for exp(-w0^2*q^2/2), not squared amplitude weights.
    pn,pw=roots_hermite(128)
    pq=np.sqrt(2)*pn/w0
    pkeep=np.abs(pq)<k
    power=float(w0/np.sqrt(2)*np.sum(pw[pkeep]*np.sqrt(1-(pq[pkeep]/k)**2)))
    return {"q":q,"kx":kx,"weights":weights,"alpha":np.arctan2(q,kx),
            "k":k,"wavelength_um":lam,"waist_um":w0,"offset_um":y0,"waist_x_um":x0,
            "n_quad":int(n_quad),"incident_power_um":power,
            "paraxial_incident_power_um":float(w0*np.sqrt(np.pi/2)),
            "omitted_propagating_tail_amplitude_weight":omitted_weight}


def incident_field(spectrum,x_um,y_um):
    """Return scalar field and its x/y derivatives; all coordinates in um."""
    x,y=np.broadcast_arrays(np.asarray(x_um,float),np.asarray(y_um,float))
    phase=np.exp(1j*(spectrum["kx"][:,None]*(x.ravel()[None,:]-spectrum["waist_x_um"])
                      +spectrum["q"][:,None]*(y.ravel()[None,:]-spectrum["offset_um"])))
    w=spectrum["weights"]
    u=w@phase; dx=(1j*spectrum["kx"]*w)@phase; dy=(1j*spectrum["q"]*w)@phase
    return u.reshape(x.shape),dx.reshape(x.shape),dy.reshape(x.shape)


def incident_line_flux(spectrum,x_um,half_width_in_waists=6.,n_y=6001):
    """Numerical incident flux integral, independent of the spectral norm.

    The scalar host flux normalized to a unit-amplitude axial plane wave is
    jx=Im(conj(u)*du/dx)/k. Returned finite-window integration is a validation
    observable; source and spatial quadrature must both be converged.
    """
    y=spectrum["offset_um"]+np.linspace(-half_width_in_waists*spectrum["waist_um"],
                                        half_width_in_waists*spectrum["waist_um"],int(n_y))
    u,dx,_=incident_field(spectrum,np.full_like(y,float(x_um)),y)
    flux=np.imag(np.conj(u)*dx)/spectrum["k"]
    power=float(np.trapezoid(flux,y))
    return {"y_um":y,"field":u,"flux_density":flux,"power_um":power,
            "relative_power_error":float((power-spectrum["incident_power_um"])/spectrum["incident_power_um"])}


class ClusterOperator:
    """Reusable exact cylinder T-matrix with arbitrary coherent illumination.

    Reuses fiber_wave's Maxwell boundary coefficients.  The finite linear
    system is factored once per geometry, wavelength, polarization and N.
    """
    def __init__(self,positions_um,radius_um,wavelength_um,n_complex,polarization="Ez",n_terms=None):
        self.positions=np.asarray(positions_um,float)
        if self.positions.ndim!=2 or self.positions.shape[1]!=2 or len(self.positions)<1 or not np.all(np.isfinite(self.positions)):
            raise ValueError("positions_um must have finite nonempty shape (M,2)")
        self.count=len(self.positions)
        self.radii=np.broadcast_to(np.asarray(radius_um,float),(self.count,)).copy()
        self.indices=np.broadcast_to(np.asarray(n_complex,complex),(self.count,)).copy()
        distance=np.linalg.norm(self.positions[:,None]-self.positions[None,:],axis=2)
        np.fill_diagonal(distance,np.inf)
        if np.any(distance<=self.radii[:,None]+self.radii[None,:]):
            raise ValueError("Cylinders must have strictly positive gaps")
        initial=[cylinder_coefficients(a,wavelength_um,n,polarization,n_terms) for a,n in zip(self.radii,self.indices)]
        order=max(c["n_terms"] for c in initial)
        coeffs=[cylinder_coefficients(a,wavelength_um,n,polarization,order) for a,n in zip(self.radii,self.indices)]
        self.n_terms=order; self.modes=coeffs[0]["modes"]; self.width=len(self.modes)
        self.k=2*np.pi/float(wavelength_um); self.wavelength_um=float(wavelength_um);self.polarization=polarization
        self.t=np.stack([c["t"] for c in coeffs]); self.h=np.stack([c["surface_h"] for c in coeffs])
        self.internal_q=np.stack([c["internal_q"] for c in coeffs])
        self.translations={}
        orders=np.arange(-2*order,2*order+1)
        lookup=self.modes[None,:]-self.modes[:,None]+2*order
        matrix=np.eye(self.count*self.width,dtype=complex)
        for j in range(self.count):
            for ell in range(self.count):
                if j==ell:continue
                delta=self.positions[j]-self.positions[ell]
                beta=np.arctan2(delta[1],delta[0])
                unique=hankel1(orders,self.k*np.linalg.norm(delta))*np.exp(1j*orders*beta)
                g=unique[lookup]
                self.translations[j,ell]=g
                matrix[j*self.width:(j+1)*self.width,ell*self.width:(ell+1)*self.width]=-(self.t[j]*self.h[j])[:,None]*g/self.h[ell][None,:]
        self.matrix=matrix
        self.lu=lu_factor(matrix,check_finite=True)

    def plane_coefficients(self,alpha=0.):
        direction=np.array([np.cos(alpha),np.sin(alpha)])
        return np.exp(1j*self.k*(self.positions@direction))[:,None]*(1j**self.modes*np.exp(-1j*self.modes*alpha))[None,:]

    def beam_coefficients(self,spectrum):
        if not np.isclose(spectrum["k"],self.k,rtol=1e-13,atol=0):
            raise ValueError("Beam wavelength and scatterer wavelength must agree")
        phase=np.exp(1j*((self.positions[:,0,None]-spectrum["waist_x_um"])*spectrum["kx"][None,:]
                          +(self.positions[:,1,None]-spectrum["offset_um"])*spectrum["q"][None,:]))
        mode_phase=1j**self.modes[None,:]*np.exp(-1j*np.outer(spectrum["alpha"],self.modes))
        return (phase*spectrum["weights"][None,:])@mode_phase

    def solve(self,incident_coefficients):
        c=np.asarray(incident_coefficients,complex)
        if c.shape!=(self.count,self.width) or not np.all(np.isfinite(c)):
            raise ValueError("incident_coefficients have the wrong shape or nonfinite entries")
        rhs=(self.t*self.h*c).ravel()
        surface=lu_solve(self.lu,rhs,check_finite=True)
        residual=float(np.linalg.norm(self.matrix@surface-rhs)/max(np.linalg.norm(rhs),1e-300))
        b=surface.reshape(self.count,self.width)/self.h
        local=c.copy()
        for (j,ell),g in self.translations.items():local[j]+=g@b[ell]
        local_abs=-4/self.k*np.sum(np.real(np.conj(local)*b)+np.abs(b)**2,axis=1)
        extinction=-4/self.k*np.real(np.vdot(c,b))
        return {"b":b,"local_c":local,"incident_c":c,"local_absorption_um":local_abs,
                "extinction_interference_um":float(extinction),"linear_system_residual":residual}

    def far_field(self,solution,theta):
        return _cluster_far_field(theta,self.modes,solution["b"],self.positions,self.k)


def beam_scattering(operator,spectrum,theta=None,angular_quad=512):
    """Return finite-beam R/A/T with independently checked optical flux.

    R integrates the scattered field only over the backward outgoing
    hemisphere. Since the incident spectrum has kx>0 only, it contributes no
    outgoing wave there. A is independent local inward boundary flux. T is
    1-R-A: it includes incident/scattered interference in the forward beam.
    The forward scattered-field integral alone is NOT transmitted power.
    """
    result=operator.solve(operator.beam_coefficients(spectrum))
    theta=np.linspace(-np.pi,np.pi,4096,endpoint=False) if theta is None else np.atleast_1d(np.asarray(theta,float))
    far=operator.far_field(result,theta)
    g,w=roots_legendre(int(angular_quad))
    back_theta=np.pi+.5*np.pi*g
    fback=operator.far_field(result,back_theta)
    backward_power=float(np.sum(w*np.abs(fback)**2)/operator.k)
    nq=max(2048,16*(operator.n_terms+1))
    fulltheta=2*np.pi*(np.arange(nq)+.5)/nq
    ffull=operator.far_field(result,fulltheta)
    psca=float(4/operator.k*np.mean(np.abs(ffull)**2))
    pabs=float(result["local_absorption_um"].sum())
    pext=result["extinction_interference_um"]
    incident=spectrum["incident_power_um"]
    refl=backward_power/incident;absorbed=pabs/incident
    result.update({"theta":theta,"far_field":far,"scattered_power_density_um_per_rad":2/(np.pi*operator.k)*np.abs(far)**2,
                   "incident_power_um":incident,"backward_power_um":backward_power,"absorbed_power_um":pabs,
                   "scattered_power_um":psca,"R":float(refl),"A":float(absorbed),"T":float(1-refl-absorbed),
                   "global_local_flux_error_um":float(pext-psca-pabs),
                   "relative_global_local_flux_error":float(abs(pext-psca-pabs)/max(incident,abs(pext),psca,1e-300)),
                   "angular_quad":int(angular_quad),"n_terms":operator.n_terms,
                   "offset_um":spectrum["offset_um"],"waist_um":spectrum["waist_um"],"source_n_quad":spectrum["n_quad"]})
    return result


def run_beam_benchmark(output_dir=None,n_rays=250000):
    """Controlled change of illumination only, with source/order checks."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from .ply_ray import hex_bundle,trace_bundle
    output=Path(output_dir) if output_dir else Path(__file__).resolve().parents[1]/"data"
    output.mkdir(parents=True,exist_ok=True)
    started=time.perf_counter()
    positions,radii=hex_bundle(1,5,.4)
    wavelengths=.55;waist=10.;index=1.55
    offsets=[0.,5.,10.]
    theta=-np.pi+(np.arange(8640)+.5)*2*np.pi/8640
    arrays={"theta_rad":theta,"positions_um":positions,"radii_um":radii,"offsets_um":offsets}
    metrics={"model":"coherent forward-propagating Gaussian angular spectrum; exact 2D parallel circular cylinders",
             "wavelength_um":wavelengths,"waist_amplitude_1_over_e_radius_um":waist,"ray_gaussian_irradiance_sigma_um":waist/2,
             "fixed_synthetic_index":index,"geometry":"hex_bundle(1,5,.4)","offsets_um":offsets,
             "source_nodes":64,"ray_count_per_case":n_rays,"normalization_checks":[],"cases":[],
             "T_definition":"T=1-R-A includes incident/scattered forward interference; forward scattered power is not T",
             "ray_limit":"Gaussian power profile with parallel rays; finite wave angular divergence is retained only in the wave model",
             "paraxial_angular_rms_deg":float(np.rad2deg(1/(2*np.pi/wavelengths*waist)))}
    for nodes in (24,32,48,64,96):
        s=gaussian_spectrum(wavelengths,waist,n_quad=nodes)
        for x in (-40.,40.):
            line=incident_line_flux(s,x)
            metrics["normalization_checks"].append({"source_nodes":nodes,"line_x_um":x,"spectral_power_um":s["incident_power_um"],
                "line_power_um":line["power_um"],"relative_error":line["relative_power_error"]})
            if nodes==64 and x==-40:
                arrays["normalization_line_y_um"]=line["y_um"]
                arrays["normalization_line_flux_density"]=line["flux_density"]
        if nodes>=64 and abs(line["relative_power_error"])>1e-10:
            raise RuntimeError("Numerical incident line-flux normalization failed")
    for pol in ("Ez","Hz"):
        operators={}
        for order in (83,91,99):
            t0=time.perf_counter();operators[order]=ClusterOperator(positions,radii,wavelengths,index,pol,order)
            metrics.setdefault("factorization_timings",[]).append({"polarization":pol,"N":order,"seconds":time.perf_counter()-t0})
        for offset in offsets:
            t0=time.perf_counter()
            spectrum=gaussian_spectrum(wavelengths,waist,offset,n_quad=64)
            low=beam_scattering(operators[91],spectrum,theta=theta)
            high=beam_scattering(operators[99],spectrum,theta=theta)
            order_change=float(np.linalg.norm(high["scattered_power_density_um_per_rad"]-low["scattered_power_density_um_per_rad"])/np.linalg.norm(high["scattered_power_density_um_per_rad"]))
            src32=beam_scattering(operators[99],gaussian_spectrum(wavelengths,waist,offset,n_quad=32),theta=theta)
            src96=beam_scattering(operators[99],gaussian_spectrum(wavelengths,waist,offset,n_quad=96),theta=theta)
            source_change=float(np.linalg.norm(src96["scattered_power_density_um_per_rad"]-high["scattered_power_density_um_per_rad"])/np.linalg.norm(high["scattered_power_density_um_per_rad"]))
            source32_change=float(np.linalg.norm(src32["scattered_power_density_um_per_rad"]-high["scattered_power_density_um_per_rad"])/np.linalg.norm(high["scattered_power_density_um_per_rad"]))
            angular256=beam_scattering(operators[99],spectrum,theta=[0.],angular_quad=256)
            angular1024=beam_scattering(operators[99],spectrum,theta=[0.],angular_quad=1024)
            angular_low_change=float(abs(angular256["R"]-high["R"])/max(high["R"],1e-300))
            angular_change=float(abs(angular1024["R"]-high["R"])/max(high["R"],1e-300))
            if order_change>1e-7 or source_change>1e-8 or angular_change>1e-7 or high["relative_global_local_flux_error"]>1e-9:
                raise RuntimeError(f"Beam convergence gate failed {pol}, offset {offset}: N={order_change}, source={source_change}, angular={angular_change}")
            wave_seconds=time.perf_counter()-t0
            ray=trace_bundle(positions,radii,n_fiber=index,n_rays=n_rays,seed=91703+int(offset),polarization=pol,
                             beam="gaussian",gaussian_sigma_um=waist/2,beam_center_um=offset,theta_bins=180,max_events=200)
            row={"polarization":pol,"offset_um":offset,"R_wave":high["R"],"A_wave":high["A"],"T_wave":high["T"],
                 "R_ray":ray["energy"]["backward"],"R_ray_SE":ray["energy_standard_error"]["backward"],
                 "A_ray":ray["energy"]["absorbed"],"T_ray":ray["energy"]["collided_forward"]+ray["energy"]["uncollided_forward"],
                 "ray_residual":ray["energy"]["residual"],"ray_numerical_failures":ray["summary"]["numerical_failure_count"],
                 "incident_power_um":spectrum["incident_power_um"],"wave_backward_power_um":high["backward_power_um"],
                 "wave_scattered_power_um":high["scattered_power_um"],"wave_extinction_interference_um":high["extinction_interference_um"],
                 "relative_global_local_flux_error":high["relative_global_local_flux_error"],
                 "multipole_N91_vs_N99_relative_L2":order_change,"source32_vs64_relative_L2":source32_change,
                 "source64_vs96_relative_L2":source_change,"backward_quadrature256_vs512_relative_change":angular_low_change,
                 "backward_quadrature512_vs1024_relative_change":angular_change,
                 "wave_with_checks_seconds":wave_seconds,"R_ray_relative_discrepancy":float((ray["energy"]["backward"]-high["R"])/high["R"])}
            binned_wave=(high["scattered_power_density_um_per_rad"]/spectrum["incident_power_um"]).reshape(180,48).mean(axis=1)
            binned_ray=ray["angular_power_per_rad"]["all_escaped"]
            backmask=np.cos(ray["theta_rad"])<0
            row["backward_2deg_binned_relative_L2"]=float(np.linalg.norm((binned_ray-binned_wave)[backmask])/np.linalg.norm(binned_wave[backmask]))
            row["backward_2deg_binned_relative_L1"]=float(np.sum(np.abs(binned_ray-binned_wave)[backmask])/np.sum(binned_wave[backmask]))
            metrics["cases"].append(row)
            label=f"{pol}_offset{int(offset)}"
            arrays[label+"_wave_scattered_power_fraction_per_rad"]=high["scattered_power_density_um_per_rad"]/spectrum["incident_power_um"]
            arrays[label+"_ray_escaped_power_fraction_per_rad"]=ray["angular_power_per_rad"]["all_escaped"]
    metrics["total_wall_seconds"]=time.perf_counter()-started
    np.savez_compressed(output/"fiber_wave_gaussian_beam.npz",**arrays)
    (output/"fiber_wave_gaussian_beam_metrics.json").write_text(json.dumps(metrics,indent=2),encoding="utf-8")
    fig,axes=plt.subplots(1,3,figsize=(13,4),constrained_layout=True)
    ax=axes[0]
    ys=np.linspace(-25,25,500)
    for offset in offsets:ax.plot(ys,np.exp(-2*(ys-offset)**2/waist**2),label=f"offset {offset:g} um")
    ax.set(xlabel="Transverse coordinate y (um)",ylabel="Paraxial waist irradiance / peak",title="Same geometry; only beam offset changes")
    ax.legend(fontsize=8);ax.grid(alpha=.2)
    for ax,pol in zip(axes[1:],("Ez","Hz")):
        rows=[r for r in metrics["cases"] if r["polarization"]==pol]
        ax.plot(offsets,[r["R_wave"] for r in rows],"o-",label="Coherent Gaussian Maxwell")
        ax.errorbar(offsets,[r["R_ray"] for r in rows],yerr=[2*r["R_ray_SE"] for r in rows],fmt="s--",capsize=3,label="Parallel Gaussian rays; +/-2 SE")
        ax.set(xlabel="Beam center offset y0 (um)",ylabel="Backward power / total incident beam power",title=f"{pol}: radius 5 um; gap 0.4 um")
        ax.legend(fontsize=7);ax.grid(alpha=.2)
    fig.suptitle("Controlled Gaussian illumination: amplitude waist w0=10 um; 550 nm",fontsize=13)
    fig.savefig(output/"fiber_wave_gaussian_beam.png",dpi=180);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11,4.2),constrained_layout=True)
    bins=-np.pi+(np.arange(180)+.5)*2*np.pi/180
    degrees=np.mod(np.rad2deg(bins),360)
    backmask=(degrees>90)&(degrees<270)
    selected=np.where(backmask)[0][np.argsort(degrees[backmask])]
    for ax,pol in zip(axes,("Ez","Hz")):
        wave=arrays[pol+"_offset0_wave_scattered_power_fraction_per_rad"].reshape(180,48).mean(axis=1)
        ray=arrays[pol+"_offset0_ray_escaped_power_fraction_per_rad"]
        row=next(r for r in metrics["cases"] if r["polarization"]==pol and r["offset_um"]==0)
        ax.plot(degrees[selected],wave[selected],label="Coherent Gaussian Maxwell",lw=1.3)
        ax.plot(degrees[selected],ray[selected],label="Parallel Gaussian power rays",lw=1.3)
        ax.set(xlabel="Backward outgoing angle (deg); 180 = back toward source",
               ylabel="Power / total incident beam power / rad",
               title=f"{pol}: integrated R close; angular relative L2={row['backward_2deg_binned_relative_L2']:.3f}",xlim=(90,270))
        ax.legend(fontsize=8);ax.grid(alpha=.2)
    fig.suptitle("Centered 550 nm beam, identical 2-degree bins: integrated power does not fix angular response",fontsize=12)
    fig.savefig(output/"fiber_wave_gaussian_backward_profiles.png",dpi=180);plt.close(fig)
    return metrics


if __name__=="__main__":
    result=run_beam_benchmark()
    print(json.dumps(result,indent=2))
