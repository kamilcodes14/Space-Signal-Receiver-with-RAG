"""Fixed synthetic experiment; writes every trial and a summarized report.
Run from repository root: python scripts/benchmark.py --seeds 25 --noise-seeds 100
"""
import argparse
import json
import platform
import sys
from pathlib import Path
from time import perf_counter
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from source import SimulatedSource
from detector import dedoppler_search


def wilson(k,n):
    z=1.96; p=k/n; d=1+z*z/n
    mid=(p+z*z/(2*n))/d
    radius=z*np.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [max(0.,mid-radius),min(1.,mid+radius)]


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--seeds',type=int,default=25)
    ap.add_argument('--noise-seeds',type=int,default=100)
    ap.add_argument('--out',type=Path,default=Path('reports/synthetic'))
    args=ap.parse_args(); args.out.mkdir(parents=True,exist_ok=True)
    records=[]; nt,nf=64,256
    def run(seed,strength,drift,inject=True):
        source=SimulatedSource(n_time_steps=nt,n_freq_bins=nf,freq_range_mhz=(1420,1420.000256),
                               seed=seed,signal_strength=strength,drift_rate_hz_per_s=drift,inject_signal=inject)
        _,_,p=source.capture()
        out={'seed':seed,'strength':strength,'drift_hz_s':drift,'injected':inject}
        truth=source.truth
        for name,grid in [('drift_search',None),('stationary_baseline',[0.])]:
            t0=perf_counter(); c=dedoppler_search(p,grid,n_sigma=6)
            elapsed=perf_counter()-t0
            matched=False; err=None
            if c and truth:
                start_error=abs(c[0]['start_freq_bin']-truth['start_freq_bin'])
                end_error=abs(c[0]['start_freq_bin']+c[0]['drift_rate_bins_per_step']*(nt-1)-
                              truth['start_freq_bin']-truth['drift_rate_bins_per_step']*(nt-1))
                matched=start_error<=2 and end_error<=2
                if matched:err=abs(c[0]['drift_rate_bins_per_step']-truth['drift_rate_bins_per_step'])
            out[name]={'candidates':len(c),'top':c[0] if c else None,'recovered':bool(matched),
                       'absolute_drift_error_hz_s':err,'elapsed_s':elapsed}
        return out
    for strength in [.5,1.,2.,3.]:
        for drift in [-.4,0.,.4]:
            for seed in range(1000,1000+args.seeds):
                records.append(run(seed,strength,drift))
        print(f'Completed strength {strength}',flush=True)
    for seed in range(5000,5000+args.noise_seeds):records.append(run(seed,0,0,False))
    groups=[]
    for strength in [.5,1.,2.,3.]:
        for drift in [-.4,0.,.4]:
            trials=[r for r in records if r['injected'] and r['strength']==strength and r['drift_hz_s']==drift]
            entry={'strength':strength,'drift_hz_s':drift,'n':len(trials)}
            for method in ['drift_search','stationary_baseline']:
                k=sum(r[method]['recovered'] for r in trials)
                errors=[r[method]['absolute_drift_error_hz_s'] for r in trials if r[method]['recovered']]
                entry[method]={'recovered':k,'recall':k/len(trials),'recall_wilson_95':wilson(k,len(trials)),
                                'median_abs_drift_error_hz_s':float(np.median(errors)) if errors else None}
            groups.append(entry)
    noise=[r for r in records if not r['injected']]
    summary={'python':platform.python_version(),'numpy':np.__version__,
             'configuration':{'n_time':nt,'n_freq':nf,'df_hz':1,'dt_s':1,'threshold':6,
                              'signal_seeds':[1000,999+args.seeds],'noise_seeds':[5000,4999+args.noise_seeds],
                              'matching':'Strongest candidate; both track endpoints within 2 bins of injection.',
                              'noise_model':'independent chi-square(df=2), mean 2, std 2; additive single-bin signal'},
             'groups':groups,'noise_only':{},'runtime':{}}
    for method in ['drift_search','stationary_baseline']:
        k=sum(r[method]['candidates']>0 for r in noise)
        summary['noise_only'][method]={'false_alarm_observations':k,'n':len(noise),
                                     'rate':k/len(noise),'wilson_95':wilson(k,len(noise))}
        summary['runtime'][method]={'median_seconds':float(np.median([r[method]['elapsed_s'] for r in records]))}
    (args.out/'trials.json').write_text(json.dumps(records,indent=2)+'\n')
    (args.out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    fig,ax=plt.subplots(figsize=(7,4))
    for method,label,marker in [('drift_search','Drift search','o'),('stationary_baseline','Zero-drift baseline','s')]:
        vals=[]
        for strength in [.5,1.,2.,3.]:
            trials=[r for r in records if r['injected'] and r['strength']==strength and r['drift_hz_s']!=0]
            vals.append(sum(r[method]['recovered'] for r in trials)/len(trials))
        ax.plot([.5,1,2,3],vals,marker=marker,label=label)
    ax.set(xlabel='Injected power per integration (noise mean = 2)',ylabel='Track recovery fraction',ylim=(-.03,1.03),
           title='Nonzero drift injections: +/-0.4 Hz/s')
    ax.legend();ax.grid(alpha=.2);fig.tight_layout();fig.savefig(args.out/'recovery.png',dpi=160);plt.close(fig)
    print(json.dumps({'noise_only':summary['noise_only'],'runtime':summary['runtime']},indent=2))

if __name__=='__main__':main()
