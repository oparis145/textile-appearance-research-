"""Scalar incoherent optical transfer, pixel integration, and detector noise.

This module simulates a conventional diffraction-limited circular pupil; it
does not claim a fabricated metasurface PSF, measured QE, or camera calibration.
All processing is in linear radiance before display encoding.
Pixel sizes are object-referred in the fabric experiment. The photon-density
parameter is AFTER collection: holding it fixed across NA isolates the MTF
change at matched detected photons. It does not model fixed-exposure NA**2
collection, magnification, or detector quantum efficiency automatically.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import numpy as np


def circular_incoherent_mtf(frequency_per_um, wavelength_um=.55, na=.04):
    if wavelength_um<=0 or not 0<na<=1:
        raise ValueError("positive wavelength and 0<NA<=1 required")
    nu=np.asarray(frequency_per_um,dtype=float)/(2*na/wavelength_um)
    u=np.clip(np.abs(nu),0,1)
    h=2/np.pi*(np.arccos(u)-u*np.sqrt(np.maximum(1-u*u,0)))
    return np.where(np.abs(nu)<1,h,0.)


def optical_filter(image,pixel_um,wavelength_um=.55,na=.04,pad=32):
    """Apply incoherent circular pupil OTF. Edge padding avoids circular wrap.

    The input must already resolve the relevant optical frequencies. If its
    sampling is too coarse, this operation cannot undo pre-existing aliasing.
    """
    a=np.asarray(image,dtype=float)
    if a.ndim not in [2,3] or pixel_um<=0:
        raise ValueError("2D/3D image and positive pixel size required")
    margins=((pad,pad),(pad,pad))+(((0,0),) if a.ndim==3 else ())
    b=np.pad(a,margins,mode='edge') if pad else a
    fy=np.fft.fftfreq(b.shape[0],d=pixel_um)
    fx=np.fft.fftfreq(b.shape[1],d=pixel_um)
    f=np.hypot(fy[:,None],fx[None,:])
    h=circular_incoherent_mtf(f,wavelength_um,na)
    if a.ndim==3: h=h[:,:,None]
    out=np.fft.ifft2(np.fft.fft2(b,axes=(0,1))*h,axes=(0,1)).real
    if pad: out=out[pad:-pad,pad:-pad]
    return out


def integrate_pixels(image,binning):
    a=np.asarray(image)
    if binning<1 or int(binning)!=binning:
        raise ValueError("integer binning>=1 required")
    b=int(binning)
    if a.shape[0]%b or a.shape[1]%b:
        raise ValueError("image dimensions must be divisible by binning")
    shape=(a.shape[0]//b,b,a.shape[1]//b,b)+a.shape[2:]
    return a.reshape(shape).mean(axis=(1,3))


@dataclass
class CameraConfig:
    wavelength_um: float = .55
    na: float = .04
    binning: int = 1
    electrons_per_um2_unit_radiance: float = 30.
    read_noise_e: float = 2.5
    full_well_e: float = 30000.
    seed: int = 809


def observe(image,input_pixel_um,config:CameraConfig,add_noise=True):
    """Add detector noise to an already sampled, linear-radiance input.

    ``radiance_noise_variance`` is the analytical PRE-saturation variance.
    It is not the variance of clipped full-well observations. The input may
    contain renderer Monte Carlo noise; ``noiseless`` means no added detector
    noise, not a noise-free or optically exact scene reference. A Nyquist flag
    is a sampling diagnostic, not proof that the input has no prior aliasing.
    """
    c=config
    if c.electrons_per_um2_unit_radiance<=0 or c.read_noise_e<0 or c.full_well_e<=0:
        raise ValueError("invalid detector noise parameters")
    blurred=optical_filter(image,input_pixel_um,c.wavelength_um,c.na)
    ideal=integrate_pixels(blurred,c.binning)
    pixel_um=input_pixel_um*c.binning
    gain=c.electrons_per_um2_unit_radiance*pixel_um**2
    expected=np.maximum(ideal,0)*gain
    rng=np.random.default_rng(c.seed)
    measured=(rng.poisson(expected)+rng.normal(0,c.read_noise_e,expected.shape)
              if add_noise else expected.copy())
    saturated=measured>c.full_well_e
    measured=np.minimum(measured,c.full_well_e)
    # Bias-subtracted read noise may legitimately give negative estimates;
    # only display code clips. This prevents a positive black-level bias.
    estimate=measured/gain
    return {"image":estimate,"noiseless":ideal,"expected_electrons":expected,
            "pixel_um":pixel_um,"config":asdict(c),
            "saturation_fraction":float(np.mean(saturated)),
            "radiance_noise_variance":(expected+c.read_noise_e**2)/gain**2,
            "variance_definition":"Poisson plus read-noise variance before full-well clipping",
            "pixel_coordinates":"object-referred in the fabric experiment",
            "photon_budget_definition":"detected electrons per object-referred area; NA collection not automatic",
            "input_nyquist_per_um":.5/input_pixel_um,
            "output_nyquist_per_um":.5/pixel_um,
            "optical_cutoff_per_um":2*c.na/c.wavelength_um,
            "output_sampling_resolves_optical_cutoff":bool(.5/pixel_um>=2*c.na/c.wavelength_um),
            "input_resolves_optical_cutoff":bool(.5/input_pixel_um>=2*c.na/c.wavelength_um)}
