"""Energy-audited scalar Fraunhofer diffraction for a finite textile gap mask.

Lengths are micrometres. Angular coordinates are small-angle direction cosines
q_x=lambda*f_x, q_y=lambda*f_y, numerically radians near the optical axis.
This is a thin, scalar, paraxial aperture model, NOT a Maxwell cloth solver.
Output ``power[j,i]`` is a fraction of incident power per angular bin. It
replaces geometrical direct-gap transmission rather than adding energy to it.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
from typing import Sequence

import numpy as np
from scipy.ndimage import gaussian_filter


@dataclass
class DiffractionResult:
    theta_x_rad: np.ndarray
    theta_y_rad: np.ndarray
    power: np.ndarray
    input_transmission: float
    diagnostics: dict

    @property
    def angular_density(self) -> np.ndarray:
        """Paraxial fraction per d(qx)d(qy); approximately power per sr."""
        return self.power / (_spacing(self.theta_x_rad) * _spacing(self.theta_y_rad))

    @property
    def total_power(self) -> float:
        return float(self.power.sum())


def _spacing(x: np.ndarray) -> float:
    if x.size < 2:
        raise ValueError("Angular grid needs at least two bins per axis.")
    return float(x[1] - x[0])


def _pair(value) -> tuple[float, float]:
    if np.isscalar(value):
        return float(value), float(value)
    if len(value) != 2:
        raise ValueError("pixel_um must be a scalar or (dy, dx).")
    return float(value[0]), float(value[1])


def fraunhofer(amplitude_mask: np.ndarray, pixel_um: float | tuple[float, float],
               wavelength_um: float = 0.55, pad_factor: int = 2,
               paraxial_limit_deg: float = 5.0,
               incident_field: np.ndarray | None = None) -> DiffractionResult:
    """FFT an arbitrary finite amplitude/phase mask under normal plane-wave light.

    The incident-power reference is uniform unit irradiance on the ORIGINAL
    mask rectangle. Zero padding adds no incident light. For M original pixels
    and N padded pixels, P_k=|FFT(mask)_k|^2/(N*M). Discrete Parseval therefore
    gives sum(P)=mean(|mask|^2). Optional ``incident_field`` replaces unit plane
    illumination, and M is replaced by sum(|incident_field|^2). This permits a
    truncated Gaussian beam, always referenced to its incident beam power.
    No outgoing-direction renormalization is used.

    Values outside the propagating cone are flagged, not silently redistributed.
    A discrete FFT aliases frequencies beyond the pixel Nyquist limit; refining
    the physical mask grid, independently of padding, is needed for convergence.
    """
    a = np.asarray(amplitude_mask, dtype=np.complex128)
    if a.ndim != 2 or min(a.shape) < 2 or not np.isfinite(a).all():
        raise ValueError("amplitude_mask must be a finite 2-D array of size >=2.")
    dy, dx = _pair(pixel_um)
    if min(dy, dx, wavelength_um) <= 0:
        raise ValueError("Pixel spacing and wavelength must be positive.")
    if int(pad_factor) != pad_factor or pad_factor < 1:
        raise ValueError("pad_factor must be a positive integer.")
    incident_norm = float(a.size)
    illumination = "uniform plane wave on original rectangle"
    if incident_field is not None:
        incident = np.asarray(incident_field, dtype=complex)
        if incident.shape != a.shape or not np.isfinite(incident).all():
            raise ValueError("incident_field must be finite and match mask shape.")
        incident_norm = float(np.sum(abs(incident) ** 2))
        if incident_norm <= 0:
            raise ValueError("Incident field must carry positive power.")
        a = a * incident
        illumination = "user-specified coherent incident field"
    shape = (a.shape[0] * int(pad_factor), a.shape[1] * int(pad_factor))
    field = np.fft.fftshift(np.fft.fft2(a, s=shape))
    power = np.abs(field) ** 2 / (np.prod(shape) * incident_norm)
    qx = wavelength_um * np.fft.fftshift(np.fft.fftfreq(shape[1], d=dx))
    qy = wavelength_um * np.fft.fftshift(np.fft.fftfreq(shape[0], d=dy))
    q2 = qy[:, None] ** 2 + qx[None, :] ** 2
    tin = float(np.sum(np.abs(a) ** 2) / incident_norm)
    paraxial = np.sin(np.deg2rad(paraxial_limit_deg)) ** 2
    diag = {
        "model": "scalar thin-aperture Fraunhofer, paraxial angular coordinates",
        "illumination": illumination,
        "wavelength_um": float(wavelength_um),
        "pixel_um_dy_dx": [dy, dx],
        "original_shape": list(a.shape), "pad_factor": int(pad_factor),
        "input_transmission": tin, "fft_total_power": float(power.sum()),
        "parseval_abs_error": abs(float(power.sum()) - tin),
        "outside_propagating_cone_power": float(power[q2 > 1.0].sum()),
        "paraxial_limit_deg": float(paraxial_limit_deg),
        "outside_paraxial_cone_power": float(power[q2 > paraxial].sum()),
        "lost_power": 0.0,
    }
    return DiffractionResult(qx, qy, power, tin, diag)


def blur_incoherent(result: DiffractionResult, source_sigma_deg: float = 0.0,
                    detector_sigma_deg: float = 0.0,
                    na: float | None = None) -> DiffractionResult:
    """Average mutually incoherent Gaussian source angles and detector blur.

    Standard deviations (not FWHM) are degrees per Cartesian angular axis.
    Convolution is of nonnegative INTENSITY, with zero continuation beyond the
    angular field. Gaussian variances add. Any boundary escape is reported.
    Optional NA is an on-axis circular detector acceptance applied after blur.
    This small-angle shift approximation ignores oblique-angle mask foreshortening.
    """
    if min(source_sigma_deg, detector_sigma_deg) < 0:
        raise ValueError("Gaussian standard deviations must be nonnegative.")
    if na is not None and not 0 <= na <= 1:
        raise ValueError("NA must lie in [0,1] for an air-side acceptance.")
    sigma = np.deg2rad(np.hypot(source_sigma_deg, detector_sigma_deg))
    p = result.power.copy()
    before = float(p.sum())
    if sigma > 0:
        p = gaussian_filter(p, (sigma / _spacing(result.theta_y_rad),
                                sigma / _spacing(result.theta_x_rad)),
                            mode="constant", cval=0.0, truncate=6.0)
    escape = max(0.0, before - float(p.sum()))
    na_loss = 0.0
    if na is not None:
        accepted = result.theta_y_rad[:, None] ** 2 + result.theta_x_rad[None, :] ** 2 <= na ** 2
        na_loss = float(p[~accepted].sum())
        p = np.where(accepted, p, 0.0)
    diag = dict(result.diagnostics)
    diag.update({"source_sigma_deg": float(source_sigma_deg),
                 "detector_sigma_deg": float(detector_sigma_deg),
                 "angular_window_loss": escape, "na": na,
                 "na_rejected_power": na_loss,
                 "lost_power": float(diag.get("lost_power", 0.0)) + escape + na_loss,
                 "output_power": float(p.sum())})
    return replace(result, power=p, diagnostics=diag)


def _edges(centres: np.ndarray) -> np.ndarray:
    d = _spacing(centres)
    return np.concatenate((centres - 0.5 * d, [centres[-1] + 0.5 * d]))


def _rebin_axis(mass: np.ndarray, old: np.ndarray, new: np.ndarray, axis: int) -> np.ndarray:
    """Conservative bin-overlap remapping, piecewise constant within old bins."""
    work = np.moveaxis(mass, axis, -1)
    flat = work.reshape(-1, work.shape[-1])
    cdf = np.concatenate((np.zeros((flat.shape[0], 1)), np.cumsum(flat, axis=1)), axis=1)
    oe, ne = _edges(old), _edges(new)
    rebinned = np.empty((flat.shape[0], len(new)), dtype=float)
    for i, row in enumerate(cdf):
        rebinned[i] = np.diff(np.interp(ne, oe, row, left=0.0, right=row[-1]))
    shape = work.shape[:-1] + (len(new),)
    return np.moveaxis(rebinned.reshape(shape), -1, axis)


def incoherent_average(results: Sequence[DiffractionResult], weights=None,
                       theta_x_rad=None, theta_y_rad=None) -> DiffractionResult:
    """Spectral/instance average on a common grid by conservative INTENSITY bins.

    Weights are normalized incident spectral powers, not field amplitudes.
    Default grid uses the widest input angular field and largest input grid.
    Grid truncation losses remain explicit; each wavelength retains its own
    transmitted power. This does not turn three bands into calibrated RGB.
    """
    if not results:
        raise ValueError("At least one diffraction result is required.")
    w = np.ones(len(results)) if weights is None else np.asarray(weights, float)
    if w.shape != (len(results),) or not np.isfinite(w).all() or np.any(w < 0) or w.sum() <= 0:
        raise ValueError("Provide one finite nonnegative weight per result, with positive sum.")
    w = w / w.sum()
    if theta_x_rad is None or theta_y_rad is None:
        def grid(axis):
            ax = [getattr(r, axis) for r in results]
            lo = min(_edges(a)[0] for a in ax)
            hi = max(_edges(a)[-1] for a in ax)
            n = max(a.size for a in ax)
            return lo + (np.arange(n) + 0.5) * ((hi - lo) / n)
        if theta_x_rad is None:
            theta_x_rad = grid("theta_x_rad")
        if theta_y_rad is None:
            theta_y_rad = grid("theta_y_rad")
    x, y = np.asarray(theta_x_rad, float), np.asarray(theta_y_rad, float)
    for axis in (x, y):
        if axis.ndim != 1 or axis.size < 2 or not np.all(np.diff(axis) > 0):
            raise ValueError("Output angular axes must be finite, increasing 1-D grids.")
        if not np.allclose(np.diff(axis), np.diff(axis)[0]):
            raise ValueError("Output angular axes must be uniformly spaced.")
    output = np.zeros((len(y), len(x)))
    tin = input_power = 0.0
    for weight, result in zip(w, results):
        rebinned = _rebin_axis(result.power, result.theta_x_rad, x, axis=1)
        rebinned = _rebin_axis(rebinned, result.theta_y_rad, y, axis=0)
        output += weight * rebinned
        tin += weight * result.input_transmission
        input_power += weight * result.total_power
    diag = {"model": "incoherent weighted intensity average",
            "weights": w.tolist(), "input_transmission": float(tin),
            "input_angular_power": float(input_power),
            "spectral_rebin_loss": max(0.0, float(input_power - output.sum())),
            "lost_power": max(0.0, float(tin - output.sum())),
            "output_power": float(output.sum()),
            "wavelengths_um": [r.diagnostics.get("wavelength_um") for r in results]}
    return DiffractionResult(x, y, np.maximum(output, 0.0), float(tin), diag)


def woven_gap_mask(shape=(256, 256), pixel_um=2.0, pitch_um=128.0,
                    gap_um=30.0, jitter_fraction=0.0, seed=0) -> np.ndarray:
    """Finite binary projection of two opaque orthogonal yarn families.

    This models open pores only. Over/under order does not change the normal
    projected gap mask. Yarn-centre perturbations are fixed per yarn; no change
    of local index or scattering is implied. jitter_fraction is a fraction of
    pitch, with independently uniform +/- displacements of line centres.
    """
    dy, dx = _pair(pixel_um)
    if not 0 <= gap_um <= pitch_um or pitch_um <= 0 or jitter_fraction < 0:
        raise ValueError("Require 0<=gap<=pitch, positive pitch and nonnegative jitter.")
    rng = np.random.default_rng(seed)
    def gap_axis(n, d):
        pos = (np.arange(n) + 0.5) * d
        centres = np.arange(-1, int(np.ceil(n*d / pitch_um)) + 2, dtype=float) * pitch_um
        centres += rng.uniform(-jitter_fraction, jitter_fraction, centres.size) * pitch_um
        width = pitch_um - gap_um
        if width == 0:
            return np.ones(n, bool)
        return np.min(np.abs(pos[:, None] - centres[None, :]), axis=1) >= width * 0.5
    return np.outer(gap_axis(shape[0], dy), gap_axis(shape[1], dx)).astype(float)


def angular_mass_within(result: DiffractionResult, radius_deg: float,
                        boundary_subsamples: int = 12) -> float:
    """Integrate a disk using partial-bin area at its boundary, no renormalization.

    Integer centre-in-disk masks introduce substantial oscillations with FFT
    padding. Here only bins crossing the disk boundary need fine area quadrature.
    The angular density is treated as constant inside each original FFT bin.
    """
    if radius_deg < 0 or boundary_subsamples < 1 or int(boundary_subsamples) != boundary_subsamples:
        raise ValueError("Require nonnegative radius and positive integer boundary subsamples.")
    r2 = np.deg2rad(radius_deg) ** 2
    dx,dy=_spacing(result.theta_x_rad),_spacing(result.theta_y_rad)
    ax,ay=abs(result.theta_x_rad)[None,:],abs(result.theta_y_rad)[:,None]
    far=(ax+dx/2)**2+(ay+dy/2)**2
    near=np.maximum(ax-dx/2,0)**2+np.maximum(ay-dy/2,0)**2
    full=far<=r2
    edge=(near<r2)&~full
    iy,ix=np.where(edge)
    mass=float(result.power[full].sum())
    if ix.size:
        n=int(boundary_subsamples)
        offsets=(np.arange(n)+.5)/n-.5
        x=result.theta_x_rad[ix];y=result.theta_y_rad[iy]
        fraction=np.zeros(ix.size)
        for sy in offsets:
            for sx in offsets:
                fraction+=(x+sx*dx)**2+(y+sy*dy)**2<=r2
        mass+=float(np.sum(result.power[iy,ix]*fraction/(n*n)))
    return mass


def run_aperture_experiments(output_dir: str | Path) -> dict:
    """Run fixed reproducible sweeps and save real computed plots/data."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    compact = {}
    fig, axes = plt.subplots(3, 3, figsize=(12, 9), constrained_layout=True)
    for row, gap in enumerate((10.0, 30.0, 80.0)):
        # 1um raster resolves all requested integer widths without ambiguous
        # edge samples; physical window remains 512um (four 128um periods).
        mask = woven_gap_mask((512, 512), 1.0, gap_um=gap)
        raw = [fraunhofer(mask, 1.0, wl, 2) for wl in (0.45, 0.55, 0.65)]
        avg = incoherent_average(raw)
        for col, sigma in enumerate((0.0, 0.1, 1.0)):
            r = blur_incoherent(avg, sigma)
            xdeg = np.rad2deg(r.theta_x_rad)
            ydeg = np.rad2deg(r.theta_y_rad)
            choose_x, choose_y = abs(xdeg) <= 3, abs(ydeg) <= 3
            den = r.angular_density[np.ix_(choose_y, choose_x)]
            im = axes[row, col].imshow(np.log10(den + 1e-8), origin="lower",
                extent=(xdeg[choose_x][0], xdeg[choose_x][-1], ydeg[choose_y][0], ydeg[choose_y][-1]),
                cmap="magma", vmin=-3, vmax=3, aspect="equal")
            axes[row, col].set_title(f"gap {gap:g} um; source sigma {sigma:g} deg")
            axes[row, col].set_xlabel("small-angle x (deg)")
            axes[row, col].set_ylabel("small-angle y (deg)")
            rows.append({"gap_um": gap, "source_sigma_deg": sigma,
                         "geometric_open_fraction": float(mask.mean()),
                         "transmitted_total": r.total_power,
                         "within_0p5_deg": angular_mass_within(r, 0.5),
                         "within_2_deg": angular_mass_within(r, 2.0),
                         "angular_window_loss": r.diagnostics["angular_window_loss"],
                         "largest_parseval_error": max(t.diagnostics["parseval_abs_error"] for t in raw)})
            compact[f"gap{int(gap)}_sigma{sigma:g}_marginal"] = r.power.sum(axis=0)
        compact[f"gap{int(gap)}_mask"] = mask
        compact["theta_x_rad"] = avg.theta_x_rad
    fig.suptitle("Finite textile pores: incoherent 450/550/650 nm equal-power intensity\nlog10 power density, common scale; calculated scalar paraxial diffraction")
    fig.colorbar(im, ax=axes.ravel().tolist(), shrink=.8, label="log10 incident-power fraction / sr (paraxial)")
    fig.savefig(output_dir / "aperture_gap_source_sweep.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(2, 3, figsize=(12, 7), constrained_layout=True)
    disorder_rows = []
    for row, jitter in enumerate((0.0, 0.12)):
        mask = woven_gap_mask((512, 512), 1.0, gap_um=30.0, jitter_fraction=jitter, seed=711)
        r = fraunhofer(mask, 1.0, 0.55, 2)
        axes[row, 0].imshow(mask, cmap="gray", origin="lower", extent=(0,512,0,512))
        axes[row, 0].set_title(f"Finite mask, jitter {jitter:g} pitch")
        axes[row, 0].set_xlabel("x (um)"); axes[row, 0].set_ylabel("y (um)")
        for col, sigma in enumerate((0.0, 1.0), start=1):
            b = blur_incoherent(r, sigma)
            deg = np.rad2deg(b.theta_x_rad)
            take = abs(deg) <= 3
            im = axes[row,col].imshow(np.log10(b.angular_density[np.ix_(take,take)]+1e-8),origin="lower",
                extent=(deg[take][0],deg[take][-1],deg[take][0],deg[take][-1]),cmap="magma",vmin=-3,vmax=3)
            axes[row,col].set_title(f"550 nm; source sigma {sigma:g} deg")
            axes[row,col].set_xlabel("small-angle x (deg)")
            axes[row,col].set_ylabel("small-angle y (deg)")
            disorder_rows.append({"jitter_fraction":jitter,"source_sigma_deg":sigma,
                                 "open_fraction":float(mask.mean()),"total_power":b.total_power,
                                 "peak_density_per_sr":float(b.angular_density.max())})
        compact[f"jitter{jitter:g}_mask"] = mask
    fig.suptitle("Periodicity sensitivity: a finite four-pitch textile patch (no periodic boundary condition)")
    fig.colorbar(im, ax=axes[:,1:].ravel().tolist(), shrink=.8, label="log10 incident-power fraction / sr (paraxial)")
    fig.savefig(output_dir / "aperture_periodic_vs_jitter.png",dpi=160)
    plt.close(fig)
    # Single rectangular pore widths: wavelength scaling, no array-order confusion.
    fig, ax = plt.subplots(figsize=(9,5),constrained_layout=True)
    slit_results = []
    n, dx = 512, 0.5
    for width in (10.0,30.0,80.0):
        for wl,style in ((0.45,"--"),(0.55,"-"),(0.65,":")):
            a = np.zeros((16,n))
            w = int(round(width/dx))
            a[:,n//2-w//2:n//2-w//2+w] = 1.0
            r = fraunhofer(a, (2.0,dx), wl, 8)
            marginal = r.power.sum(axis=0)
            x = np.rad2deg(r.theta_x_rad)
            take = (x >= 0) & (x <= 5)
            ax.semilogy(x[take],np.maximum(marginal[take]/marginal.max(),1e-9),style,label=f"{width:g} um, {wl*1000:.0f} nm")
            expected = wl/width
            k = np.argmin(abs(r.theta_x_rad-expected))
            slit_results.append({"slit_width_um":width,"wavelength_um":wl,
                "analytic_first_zero_deg_paraxial":float(np.rad2deg(expected)),
                "nearest_fft_bin_deg":float(x[k]),
                "intensity_near_first_zero_relative":float(marginal[k]/marginal.max())})
    ax.set(ylim=(1e-7,1.2),xlabel="small-angle x (deg)",ylabel="normalized angular marginal",
           title="Rectangular pore: wider gaps have narrower diffraction; wavelength scaling")
    ax.grid(alpha=.2);ax.legend(ncol=3,fontsize=8)
    fig.savefig(output_dir / "aperture_slit_wavelength.png",dpi=160)
    plt.close(fig)
    # Gaussian-windowed apertures connect to the local-beam construction, while
    # remaining explicitly scalar/paraxial and separate from ply scattering.
    fig,axes=plt.subplots(2,3,figsize=(11,6.5),constrained_layout=True)
    n,dx,waist=256,.5,10.
    x=(np.arange(n)-n/2+.5)*dx
    rectangle=np.outer(abs(x)<15,abs(x)<15)
    gaussian_rows=[]
    for col,offset in enumerate((0.,12.,22.)):
        beam=np.exp(-((x[None,:]-offset)**2+x[:,None]**2)/waist**2)
        axes[0,col].imshow((abs(beam)**2)*rectangle,origin="lower",extent=(-64,64,-64,64),
                            cmap="viridis",vmin=0,vmax=1)
        axes[0,col].set(xlim=(-30,40),ylim=(-30,30),title=f"Beam offset {offset:g} um",
                        xlabel="x (um)",ylabel="y (um)")
        for wl,color in ((.45,"royalblue"),(.55,"forestgreen"),(.65,"firebrick")):
            r=fraunhofer(rectangle,dx,wl,4,incident_field=beam)
            marginal=r.power.sum(axis=0)/_spacing(r.theta_x_rad)
            axes[1,col].plot(np.rad2deg(r.theta_x_rad),marginal,color=color,label=f"{wl*1000:.0f} nm")
            gaussian_rows.append({"offset_um":offset,"beam_waist_um":waist,"wavelength_um":wl,
                "aperture_width_um":30.,"transmitted_beam_fraction":r.total_power,
                "within_2_deg_beam_fraction":angular_mass_within(r,2.),
                "parseval_error":r.diagnostics["parseval_abs_error"]})
        axes[1,col].set(xlim=(-5,5),xlabel="small-angle x (deg)",ylabel="beam-power fraction / rad")
        axes[1,col].legend(fontsize=8);axes[1,col].grid(alpha=.2)
    fig.suptitle("Gaussian beam truncated by one pore: correct incident-beam power reference\nWaist10 um;30 um square aperture; source components remain mutually incoherent")
    fig.savefig(output_dir/"aperture_gaussian_beam.png",dpi=160);plt.close(fig)
    convergence=[]
    for dx in (2.,1.,.5):
        n=int(128/dx)
        a=woven_gap_mask((n,n),dx,128,40)
        r=fraunhofer(a,dx,.55,4)
        convergence.append({"pixel_um":dx,"pad_factor":4,"case":"physical_grid",
                            "total_power":r.total_power,"within_0p5_deg":angular_mass_within(r,.5)})
    a=woven_gap_mask((128,128),1.,128,40)
    for pad in (2,4,8,16):
        r=fraunhofer(a,1.,.55,pad)
        convergence.append({"pixel_um":1.,"pad_factor":pad,"case":"angular_padding",
                            "total_power":r.total_power,"within_0p5_deg":angular_mass_within(r,.5)})
    data={"gap_source_sweep":rows,"periodicity_sweep":disorder_rows,
          "single_slit":slit_results,"gaussian_beam_sweep":gaussian_rows,
          "convergence":convergence,
          "scope":"Synthetic opaque-gap masks; fixed index absent here; scalar paraxial thin screen. No measured fabric validation."}
    (output_dir / "aperture_metrics.json").write_text(json.dumps(data,indent=2))
    np.savez_compressed(output_dir / "aperture_arrays.npz",**compact)
    return data


if __name__ == "__main__":
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",default="data")
    args=parser.parse_args()
    print(json.dumps(run_aperture_experiments(args.output),indent=2))
