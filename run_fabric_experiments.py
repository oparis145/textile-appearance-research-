"""Reproduce the actual fabric renders, geometry gates, and camera experiment.

Run from this directory: python run_fabric_experiments.py [--quick]
Default output is deterministic-seeded; Monte Carlo images remain numerical
estimates. Results are synthetic, without measured cloth ground truth.
"""
from pathlib import Path
from dataclasses import replace
import argparse,json,time
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from textile_sim.geometry import *
from textile_sim.render import *
from textile_sim.camera import *
from textile_sim.aperture_wave import fraunhofer,blur_incoherent,incoherent_average,angular_mass_within

BASE=Path(__file__).resolve().parent
DATA=BASE/'data'; FIG=BASE/'figures'


def jsave(path,value):
    Path(path).write_text(json.dumps(value,indent=2))


def make_geometry_fig(geometries):
    fig=plt.figure(figsize=(12,7.4),layout='constrained')
    for j,(name,g) in enumerate(geometries.items()):
        a=fig.add_subplot(2,3,j+1,projection='3d')
        for i,p in enumerate(g['yarns']):
            a.plot(p[:,0]*1000,p[:,1]*1000,p[:,2]*1000,lw=1.6,
                   color='#087f8c' if i<len(g['yarns'])//2 else '#e09b2d')
        a.view_init(elev=30,azim=-58);a.set_box_aspect((1,1,.23))
        a.set_title(name.capitalize()+' | yarn centerlines')
        a.set_xlabel('x [um]');a.set_ylabel('y [um]');a.set_zlabel('z [um]')
        a=fig.add_subplot(2,3,j+4)
        f=g['fibers']; pick=(g['labels'][:,0]==0)&(g['labels'][:,1]==4)
        for curve in f[pick]:
            a.plot(curve[:,1]*1000,curve[:,0]*1000,lw=.55,alpha=.8,color='#087f8c')
        a.set_xlim(-250,250);a.set_ylim(-150,-50)
        a.set_title('One yarn: 37 explicit fibers')
        a.set_xlabel('along yarn [um]');a.set_ylabel('transverse [um]')
    fig.suptitle('Procedural geometry | same fiber packing, three over-under patterns',fontsize=15)
    fig.savefig(FIG/'fabric_geometry.png',dpi=180);plt.close(fig)


def run_camera_experiment(a, px):
    """Replay only optics and detector steps from a saved linear render."""
    camera_results={};fig,ax=plt.subplots(2,3,figsize=(11,7.7),layout='constrained')
    cases_camera=[(.02,1),(.04,1),(.08,1),(.04,2),(.04,4),(.04,8)]
    for idx,(na,binning) in enumerate(cases_camera):
        cfg=CameraConfig(na=na,binning=binning,seed=2030+idx)
        result=observe(a,px,cfg)
        key=f'NA{na:g}_bin{binning}'
        camera_results[key]={k:v for k,v in result.items() if k not in ['image','noiseless','expected_electrons','radiance_noise_variance']}
        camera_results[key]['rmse_noise']=float(np.sqrt(np.mean((result['image']-result['noiseless'])**2)))
        np.savez_compressed(DATA/('camera_'+key+'.npz'),image=result['image'],noiseless=result['noiseless'],pixel_um=result['pixel_um'])
        ax.flat[idx].imshow(encode_srgb(result['image'],.5),interpolation='nearest')
        ax.flat[idx].set_title(f'NA {na:g} | {result["pixel_um"]:.2f} um/pixel\n'
                               f'{result["image"].shape[1]} x {result["image"].shape[0]} object-space samples')
        ax.flat[idx].set_xticks([]);ax.flat[idx].set_yticks([])
    fig.suptitle('Camera simulation | matched detected photons per object-space area\n'
                 'Circular-pupil MTF, pixel-area integration, Poisson shot noise + read noise',fontsize=14)
    fig.savefig(FIG/'camera_comparison.png',dpi=180);plt.close(fig)
    return camera_results


def main(quick=False):
    DATA.mkdir(exist_ok=True);FIG.mkdir(exist_ok=True)
    metrics={'scope':'Synthetic circular fibers; no dyeing, measured-fabric fit, or fabricated metasurface.',
             'geometry':{},'renders':{},'visibility':{},'diffraction':{}}
    geos={};paths={};images={}
    n=10
    for name in ['plain','twill','satin']:
        cfg=FabricConfig(pattern=name,yarns_per_direction=n,samples_per_pitch=24)
        g=build_fabric(cfg)
        certificate=certify_spline_clearance(g,subdivision=0)
        if not certificate['certified_separated']:
            raise RuntimeError(f'{name}: physical geometry separation gate failed: {certificate}')
        p=save_geometry(DATA/('fabric_'+name),g)
        geos[name]=g;paths[name]=p
        metrics['geometry'][name]={'configuration':g['config'],'fiber_count':len(g['fibers']),
             'control_point_count':int(np.prod(g['fibers'].shape[:2])),'clearance_certificate':certificate}
        print('GEOMETRY',name,certificate,flush=True)
    make_geometry_fig(geos)
    resolution=128 if quick else 256
    spp=32 if quick else 192
    cases=[('front_x','reflection',0),('front_y','reflection',90),
           ('back_diffuse','hemisphere_transmission',0)]
    for name,g in geos.items():
        for label,mode,azi in cases:
            key=name+'_'+label
            c=RenderConfig(resolution=resolution,spp=spp,mode=mode,light_azimuth_deg=azi,
                           exposure=.5,seed=20261010)
            a,m=render_fabric(paths[name],g['visible_width_mm'],g['config']['fiber_radius_mm'],c,FIG/key)
            images[key]=a;metrics['renders'][key]=m
            jsave(DATA/'fabric_metrics.json',metrics)
            print('RENDER',key,m['render_seconds'],'mean',m['mean_linear'],flush=True)
        gap,px=normal_visibility_mask(paths[name],g['visible_width_mm'],resolution=1024)
        np.savez_compressed(DATA/('fabric_'+name+'_gap.npz'),gap=gap,pixel_um=px)
        metrics['visibility'][name]={'normal_open_fraction':float(gap.mean()),'mask_resolution':1024,'pixel_um':px}
        waves=[fraunhofer(gap,px,wavelength_um=w,pad_factor=2) for w in [.45,.55,.65]]
        avg=incoherent_average(waves)
        for sigma in [0.,.1,1.]:
            z=blur_incoherent(avg,source_sigma_deg=sigma)
            key=f'{name}_sigma{sigma:g}'
            metrics['diffraction'][key]={'input_transmission':z.input_transmission,
                  'total_angular_power':float(z.power.sum()),
                  'within_0p5_deg':float(angular_mass_within(z,.5)),
                  'within_2_deg':float(angular_mass_within(z,2.)),
                  'normal_open_fraction':float(gap.mean()),
                  'assumption':'Projected zero-thickness opaque gap mask; not total fabric BTDF.'}
        jsave(DATA/'fabric_metrics.json',metrics)
    fig,axes=plt.subplots(3,3,figsize=(10.5,10.9),layout='constrained')
    for i,name in enumerate(geos):
        for j,(label,_,_) in enumerate(cases):
            axes[i,j].imshow(encode_srgb(images[name+'_'+label],.5))
            axes[i,j].set_xticks([]);axes[i,j].set_yticks([])
            if i==0: axes[i,j].set_title(['Front light: azimuth 0 deg','Front light: azimuth 90 deg','Diffuse back illumination'][j])
            if j==0: axes[i,j].set_ylabel(name.capitalize(),fontsize=13)
    fig.suptitle('Actual path-traced fabric images | identical n, absorption, packing and display exposure\n'
                 'Synthetic fibers; direct spatial geometry and inter-fiber scattering',fontsize=14)
    fig.savefig(FIG/'fabric_contact_sheet.png',dpi=180);plt.close(fig)
    # A resolved close-up for the spatial camera test (same actual geometry).
    g=geos['plain']
    c=RenderConfig(resolution=256 if quick else 512,spp=64 if quick else 256,
                    width_fraction=.4,exposure=.5,seed=614)
    a,m=render_fabric(paths['plain'],g['visible_width_mm'],g['config']['fiber_radius_mm'],c,FIG/'fabric_macro')
    metrics['renders']['macro']=m
    px=g['visible_width_mm']*.4*1000/c.resolution
    camera_results=run_camera_experiment(a,px)
    metrics['camera']=camera_results
    jsave(DATA/'fabric_metrics.json',metrics)
    print('FABRIC EXPERIMENTS DONE',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--quick',action='store_true')
    main(p.parse_args().quick)
