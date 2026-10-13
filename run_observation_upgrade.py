#!/usr/bin/env python3
"""Bounded NumPy/SciPy experiments; never overwrite an existing nonempty run.

The defaults execute new first-surface/refinement, local-volume and angular-LOD
experiments, not a Mitsuba re-render of the v5 fabric. --v5-input optionally
reads an existing archive and runs absolute-tolerance paired equivalence gates.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import time

import numpy as np
import scipy
from textile_sim.surface_reference import surface_power, observe, angular_lod, observation_error
from textile_sim.local_volume_profile import reconstruct_local_volume, global_volume_baseline, frustum_volumes
from textile_sim.observation_gate import choose_observation_lod, paired_equivalence, audit_v5_radial_pair

BASE_COMMIT = 'd5ee2b7d4677f8b98f99bac821fec340ffe98c9c'


def _json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n',encoding='utf-8')


def _hashes():
    root = Path(__file__).resolve().parent
    paths = [Path(__file__).resolve(), root/'textile_sim'/'surface_reference.py',
             root/'textile_sim'/'local_volume_profile.py', root/'textile_sim'/'observation_gate.py',
             root/'tests'/'test_observation_upgrade.py']
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def experiments():
    sides_set = [16,32,64,128,256,512,1024]
    sensors = [.5,2.,8.]
    sources = [0.,2.]
    detector_counts = [256,512]
    optical, observed, candidates = [], [], {n:[] for n in sides_set}
    for source in sources:
        ref,_ = surface_power(grid_size=8192,source_sigma_deg=source,source_order=161)
        ref_low,_ = surface_power(grid_size=4096,source_sigma_deg=source,source_order=161)
        for sides in sides_set:
            for phase_fraction in [0.,.25,.5]:
                phase = phase_fraction*2*np.pi/sides
                kw = dict(sides=sides,phase_rad=phase,source_sigma_deg=source)
                p,budget = surface_power(grid_size=8192,source_order=161,**kw)
                low,_ = surface_power(grid_size=4096,source_order=161,**kw)
                source_low,_ = surface_power(grid_size=8192,source_order=81,**kw)
                for detectors in detector_counts:
                    for sensor in sensors:
                        r,c = (observe(x,sigma_deg=sensor,detector_bins=detectors) for x in (ref,p))
                        l,q,rl = (observe(x,sigma_deg=sensor,detector_bins=detectors) for x in (low,source_low,ref_low))
                        error=observation_error(r,c)
                        grid=max(observation_error(c,l)['relative_l2'],observation_error(r,rl)['relative_l2'])
                        src=observation_error(c,q)['relative_l2']
                        name=f'source{source}/sensor{sensor}/phase{phase_fraction}/bins{detectors}'
                        row={'sides':sides,'source_sigma_deg':source,'sensor_sigma_deg':sensor,
                             'phase_fraction':phase_fraction,'detector_bins':detectors,'volume_relative_error':budget['area_ratio']-1,
                             'budget':budget,**error,'grid_refinement_l2':grid,'source_refinement_l2':src}
                        optical.append(row)
                        candidates[sides].append({'condition':name,**error,'refinement_l2':grid+src})
                        if source == 0. and phase_fraction == 0. and detectors == 512 and sides in [32,128,512]:
                            observed.append({'sides':sides,'sensor_sigma_deg':sensor,
                                             'reference':r.tolist(),'candidate':c.tolist()})
    selection=choose_observation_lod([{'name':f'polygon_{n}','cost':n,'conditions':v}
                      for n,v in candidates.items()],max_relative_l2=.02,
                      max_relative_power=.01,max_refinement_l2=.005)
    heldout=[]
    if selection['selected'] is not None:
        chosen=int(selection['selected'].split('_')[-1])
        rr,_=surface_power(grid_size=8192,source_sigma_deg=1.,source_order=161)
        pp,_=surface_power(sides=chosen,phase_rad=.137*2*np.pi/chosen,
                          grid_size=8192,source_sigma_deg=1.,source_order=161)
        for sensor in [.75,3.]:
            r,c=(observe(x,sigma_deg=sensor,detector_bins=1024) for x in (rr,pp))
            heldout.append({'source_sigma_deg':1.,'sensor_sigma_deg':sensor,'detector_bins':1024,
                            'phase_fraction':.137,**observation_error(r,c)})
    lod=[]
    ref,_=surface_power(grid_size=8192)
    for groups in [4,8,16,32,64,128,256]:
        p=angular_lod(ref,groups)
        for sensor in sensors:
            r,c=(observe(x,sigma_deg=sensor,detector_bins=512) for x in (ref,p))
            lod.append({'groups':groups,'sensor_sigma_deg':sensor,**observation_error(r,c)})
    volumes=[]
    for count in [16,64,128,256]:
        for amplitude in [0.,.03,.1,.25]:
            coordinate=(np.arange(count)+.5)/count
            stretch=1+amplitude*np.sin(2*np.pi*coordinate)
            length=.8/count*stretch
            radius=.003/np.sqrt(stretch)
            target=np.pi*length*radius**2
            new=reconstruct_local_volume(length,radius)
            old=global_volume_baseline(length,radius)
            old_error=frustum_volumes(length,old)/target-1
            volumes.append({'segments':count,'stretch_amplitude':amplitude,
                'old_max_local_relative_error':float(np.max(np.abs(old_error))),
                'old_total_relative_error':float(frustum_volumes(length,old).sum()/target.sum()-1),
                'new_max_local_relative_error':new['max_relative_volume_error'],
                'new_total_relative_error':float(new['segment_volumes'].sum()/target.sum()-1),
                'reference_segment_radii_mm':radius.tolist(),
                'old_node_radii_mm':old.tolist(),'new_node_radii_mm':new['node_radii'].tolist()})
    a=np.ones((4,1)); b=a+np.array([[-.1],[.1],[-.1],[.1]])
    guard=paired_equivalence(a,b,absolute_tolerance=.01,repeat_ids=[101,102,103,104],condition_ids=['synthetic_control'])
    return {'schema':'textile.observation_upgrade/0.6-research', 'base_commit':BASE_COMMIT,
        'parameters':{'grid_sizes':[4096,8192],'source_orders':[81,161],
                      'detector_bins':detector_counts,'n_inside':1.55,'polarization':'unpolarized',
                      'source_sigmas_deg':sources,'sensor_sigmas_deg':sensors,
                      'polygon_sides':sides_set,'circle_quadrature_order':4},
        'optical_cases':optical,'selected_polygon':selection,'heldout_selected_polygon':heldout,'observed_distributions':observed,
        'angular_lod_cases':lod,'local_volume_cases':volumes,'zero_ci_control':guard,
        'scope':{'new_mitsuba_renders':0,'measured_samples':0,'new_full_3d_wave_solver':False,
                 'existing_425_tests_rerun_locally':False,
                 'reflection':'first exterior surface only, common 2R incident aperture',
                 'lod':'1D angular histogram compression, not fabric BSDF aggregation',
                 'volume':'per-chord frustum conservation, not bent-solid conservation',
                 'refinement':'observed diagnostic, not a proven global numerical bound'}}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--v5-input',type=Path)
    parser.add_argument('--coarse',type=int,default=32)
    parser.add_argument('--fine',type=int,default=64)
    parser.add_argument('--absolute-tolerance',type=float)
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args(argv)
    if args.v5_input and (args.absolute_tolerance is None or not np.isfinite(args.absolute_tolerance) or args.absolute_tolerance <= 0):
        parser.error('--v5-input requires a predeclared positive --absolute-tolerance')
    output=args.output.resolve()
    if args.v5_input:
        source=args.v5_input.resolve()
        if source==output or source in output.parents or output in source.parents:
            parser.error('v5 input and output must not overlap')
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        parser.error('output must be a new or empty directory')
    if args.dry_run:
        print(json.dumps({'output':str(output),'first_surface_cases':252,'angular_lod_cases':21,
                          'local_volume_cases':16,'new_mitsuba_renders':0,'v5_read':bool(args.v5_input)}))
        return 0
    output.mkdir(parents=True,exist_ok=True)
    start=time.perf_counter(); before=_hashes()
    manifest={'status':'running','started_utc':datetime.now(timezone.utc).isoformat(),
              'source_sha256':before,'python':platform.python_version(),
              'numpy':np.__version__,'scipy':scipy.__version__,'base_commit':BASE_COMMIT}
    _json(output/'run_manifest.json',manifest)
    try:
        result=experiments()
        if args.v5_input:
            result['v5_radial_equivalence']=audit_v5_radial_pair(args.v5_input,
                coarse=args.coarse,fine=args.fine,absolute_tolerance=args.absolute_tolerance)
        _json(output/'results.json',result)
        manifest.update(status='completed',elapsed_seconds=time.perf_counter()-start,
            source_unchanged=before==_hashes(),
            output_sha256={'results.json':hashlib.sha256((output/'results.json').read_bytes()).hexdigest()})
        if not manifest['source_unchanged']:
            raise RuntimeError('source changed during experiment')
        _json(output/'run_manifest.json',manifest)
        print(json.dumps({'status':'completed','output':str(output),
                          'selected_polygon':result['selected_polygon']['selected'],
                          'elapsed_seconds':manifest['elapsed_seconds']}))
        return 0
    except Exception as exc:
        manifest.update(status='failed',error_type=type(exc).__name__,error=str(exc),elapsed_seconds=time.perf_counter()-start)
        _json(output/'run_manifest.json',manifest)
        raise


if __name__ == '__main__':
    raise SystemExit(main())
