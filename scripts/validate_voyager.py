"""Reproduce the known Voyager 1 carrier in Berkeley's public GBT example.

This is a tutorial-dataset reproduction, not a new astrophysical discovery.
A ridge fit is a consistency check on the same data, not independent truth.
"""
import argparse
import hashlib
import json
import shutil
import sys
import urllib.request
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from source import FileSource
from detector import dedoppler_search, physical_candidates
from visualizer import plot_waterfall

URL='http://blpd0.ssl.berkeley.edu/Voyager_data/Voyager1.single_coarse.fine_res.h5'
SHA256='c9a9a54f4140e3754ffb2455fae4eeb2eb70c8207123116ee953e4fce15c36ac'
TUTORIAL='https://github.com/UCBerkeleySETI/blimpy/blob/master/examples/voyager.ipynb'


def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--file',type=Path,default=Path('data/Voyager1.single_coarse.fine_res.h5'))
    ap.add_argument('--download',action='store_true');ap.add_argument('--out',type=Path,default=Path('reports/voyager'))
    args=ap.parse_args()
    if not args.file.exists():
        if not args.download:ap.error('Dataset missing; use --download or pass --file.')
        args.file.parent.mkdir(parents=True,exist_ok=True)
        temp=args.file.with_suffix('.part')
        try:
            with urllib.request.urlopen(URL,timeout=60) as response,temp.open('wb') as f:
                shutil.copyfileobj(response,f)
            if digest(temp)!=SHA256:raise ValueError('Dataset SHA256 does not match the validated example.')
            temp.replace(args.file)
        finally:
            temp.unlink(missing_ok=True)
    if digest(args.file)!=SHA256:raise ValueError('Expected the unchanged Voyager tutorial dataset.')
    f,t,p=FileSource(args.file,8419.296,8419.298,max_time_steps=16).capture()
    candidates=physical_candidates(dedoppler_search(p,n_sigma=6,max_drift_bins_per_step=4),f,t)
    baseline=physical_candidates(dedoppler_search(p,[0.],n_sigma=6),f,t)
    ridge=(f[np.argmax(p,axis=1)]-f[0])*1e6
    slope,intercept=np.polyfit(t,ridge,1)
    residual=np.sqrt(np.mean((ridge-(intercept+slope*t))**2))
    top=candidates[0] if candidates else None
    df=float((f[1]-f[0])*1e6)
    # Sample spacing of the searched drift grid is one channel over duration.
    tolerance=2*df/(t[-1]-t[0])
    passed=bool(top and 8419.2968<top['frequency_mhz']<8419.2972 and
                top['drift_rate_hz_per_s']<0 and abs(top['drift_rate_hz_per_s']-slope)<=tolerance)
    result={
        'dataset_url':URL,'input_sha256':SHA256,'tutorial':TUTORIAL,
        'shape':list(p.shape),'frequency_selection_mhz':[8419.296,8419.298],
        'channel_width_hz':df,'integration_spacing_s':float(t[1]-t[0]),
        'first_to_last_integration_s':float(t[-1]-t[0]),'threshold':6,
        'max_drift_bins_per_step':4,'candidate_track_count':len(candidates),
        'top_candidate':top,'stationary_baseline_top':baseline[0] if baseline else None,
        'ridge_fit_drift_hz_s':float(slope),'ridge_residual_rms_hz':float(residual),
        'drift_agreement_tolerance_hz_s':float(tolerance),'consistency_check_passed':passed,
        'limitations':[
            'Known, preselected bright spacecraft signal; not a blind survey or discovery.',
            'Ridge fit uses the same data and is not independent ground truth.',
            'Candidate count includes overlapping tracks through one carrier, not distinct sources.',
            'False-positive rate on real telescope backgrounds is not measured by this example.',
            'No barycentric correction, calibrated flux, uncertainty model, or RFI rejection.'
        ]
    }
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/'validation.json').write_text(json.dumps(result,indent=2)+'\n')
    plot_waterfall(f,t,p,candidates[:1],args.out/'waterfall.png')
    print(json.dumps(result,indent=2))
    if not passed:raise SystemExit('Voyager consistency check failed.')

if __name__=='__main__':main()
