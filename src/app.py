"""Reproducible capture -> detect -> visualize -> JSON run-log pipeline."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from source import SimulatedSource, RTLSDRSource, FileSource
from detector import dedoppler_search, physical_candidates
from visualizer import plot_waterfall

ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', choices=['simulated', 'rtlsdr', 'file'], default='simulated')
    parser.add_argument('--freq-mhz', type=float, default=137.1)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--no-signal', action='store_true')
    parser.add_argument('--strength', type=float, default=3.0)
    parser.add_argument('--drift-hz-s', type=float, default=0.4)
    parser.add_argument('--file', type=Path)
    parser.add_argument('--f-start', type=float, help='MHz; file sub-band lower bound')
    parser.add_argument('--f-stop', type=float, help='MHz; file sub-band upper bound')
    parser.add_argument('--max-time-steps', type=int, default=256)
    parser.add_argument('--threshold', type=float, default=6.0)
    parser.add_argument('--max-drift-bins', type=float, default=1.0)
    parser.add_argument('--out', type=Path, default=ROOT / 'outputs' / 'waterfall.png')
    parser.add_argument('--log', type=Path, help='Run JSON path; default is a timestamped data/logs entry')
    args = parser.parse_args()
    if args.source == 'file':
        if args.file is None:
            parser.error('--source file requires --file')
        source = FileSource(args.file, args.f_start, args.f_stop, args.max_time_steps)
    elif args.source == 'rtlsdr':
        source = RTLSDRSource(center_freq_hz=args.freq_mhz * 1e6)
    else:
        source = SimulatedSource(seed=args.seed, inject_signal=not args.no_signal,
                                 signal_strength=args.strength, drift_rate_hz_per_s=args.drift_hz_s)
    try:
        freqs, times, power = source.capture()
    finally:
        if hasattr(source, 'close'):
            source.close()
    candidates = physical_candidates(dedoppler_search(power, n_sigma=args.threshold,
                                      max_drift_bins_per_step=args.max_drift_bins), freqs, times)
    plot_waterfall(freqs, times, power, candidates=candidates, out_path=args.out)
    now = datetime.now(timezone.utc)
    run = {
        'schema_version': 1, 'created_utc': now.isoformat(), 'source': args.source,
        'parameters': {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        'shape': list(power.shape), 'frequency_start_mhz': float(freqs[0]),
        'frequency_end_mhz': float(freqs[-1]), 'channel_width_hz': float((freqs[1]-freqs[0])*1e6),
        'integration_spacing_s': float(times[1]-times[0]),
        'truth': getattr(source, 'truth', None), 'candidates': candidates,
        'score_definition': 'sum of per-row mean-subtracted power / sqrt(sum of per-row variances)',
        'limitations': 'Candidate score is not a calibrated false-alarm probability. A track is not proof of celestial origin.'
    }
    if args.source == 'file':
        with args.file.open('rb') as handle:
            run['input_sha256'] = hashlib.file_digest(handle, 'sha256').hexdigest()
    log = args.log or ROOT/'src'/'data'/'logs'/f"run_{now.strftime('%Y%m%dT%H%M%S%fZ')}.json"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(json.dumps(run, indent=2)+'\n')
    print(json.dumps({'candidates': len(candidates), 'top_candidate': candidates[0] if candidates else None,
                      'plot': str(args.out), 'log': str(log)}, indent=2))


if __name__ == '__main__':
    main()
