"""Linear-track integration with empirical, per-row noise centering.

Scores use an estimated mean (not a median) and variance. They are
standardized excess-power scores, NOT Gaussian false-alarm probabilities.
The exponential-noise simulations and real telescope data have different
noise statistics; thresholds need separate validation for each use case.
"""
import numpy as np


def validate_power(power):
    power = np.asarray(power, dtype=float)
    if power.ndim != 2 or min(power.shape) < 2:
        raise ValueError('Expected a time x frequency array with both dimensions >= 2.')
    if not np.all(np.isfinite(power)) or np.any(power < 0):
        raise ValueError('Power must be finite and nonnegative.')
    return power


def threshold_hits(power, n_sigma=6.0):
    power = validate_power(power)
    threshold = float(power.mean() + n_sigma * power.std())
    t, f = np.where(power > threshold)
    return list(zip(t, f)), threshold


def dedoppler_search(power, drift_rates_bins_per_step=None, n_sigma=6.0,
                     max_drift_bins_per_step=1.0, min_coverage=0.8,
                     max_candidates=100, dedup_bins=3):
    """Search nearest-bin tracks; vectorize all starting bins for each drift.

    The default grid has <= 1-bin endpoint spacing over the observation.
    Candidate suppression compares both endpoints, rather than arbitrary
    frequency buckets. Noise mean/variance are estimated across each row;
    broad signals, bandpass structure and RFI can bias those estimates.
    """
    power = validate_power(power)
    if not np.isfinite(n_sigma) or n_sigma <= 0 or not 0 < min_coverage <= 1:
        raise ValueError('Threshold must be positive; coverage must be in (0, 1].')
    if max_candidates < 1 or not np.isfinite(max_drift_bins_per_step) or max_drift_bins_per_step < 0:
        raise ValueError('Invalid candidate limit or drift range.')
    nt, nf = power.shape
    if drift_rates_bins_per_step is None:
        steps = int(np.ceil(max_drift_bins_per_step * (nt - 1)))
        drifts = np.linspace(-max_drift_bins_per_step, max_drift_bins_per_step, 2 * steps + 1)
    else:
        drifts = np.asarray(drift_rates_bins_per_step, dtype=float)
    if drifts.ndim != 1 or not drifts.size or not np.all(np.isfinite(drifts)):
        raise ValueError('Provide a finite, nonempty drift grid.')
    means = power.mean(axis=1)
    variances = power.var(axis=1)
    if not np.any(variances > 0):
        return []
    rows = np.arange(nt)[:, None]
    starts = np.arange(nf)[None, :]
    candidates = []
    for drift in drifts:
        indices = np.rint(starts + drift * rows).astype(int)
        valid = (indices >= 0) & (indices < nf)
        counts = valid.sum(axis=0)
        values = power[rows, np.clip(indices, 0, nf - 1)] - means[:, None]
        excess = np.where(valid, values, 0).sum(axis=0)
        variance = np.where(valid, variances[:, None], 0).sum(axis=0)
        score = np.divide(excess, np.sqrt(variance), out=np.zeros(nf), where=variance > 0)
        detected = np.flatnonzero((counts >= min_coverage * nt) & (score > n_sigma))
        for start in detected:
            candidates.append({'drift_rate_bins_per_step': float(drift),
                               'start_freq_bin': int(start), 'snr': float(score[start]),
                               'n_integrations': int(counts[start])})
    candidates.sort(key=lambda c: -c['snr'])
    kept = []
    for c in candidates:
        begin = c['start_freq_bin']
        end = begin + c['drift_rate_bins_per_step'] * (nt - 1)
        if any(abs(begin - k['start_freq_bin']) <= dedup_bins and
               abs(end - k['start_freq_bin'] - k['drift_rate_bins_per_step'] * (nt - 1)) <= dedup_bins
               for k in kept):
            continue
        kept.append(c)
        if len(kept) >= max_candidates:
            break
    return kept


def physical_candidates(candidates, freqs_mhz, times_s):
    """Attach MHz and Hz/s from uniformly spaced physical axes."""
    f, t = np.asarray(freqs_mhz), np.asarray(times_s)
    if len(f) < 2 or len(t) < 2 or not np.all(np.isfinite(f)) or not np.all(np.isfinite(t)):
        raise ValueError('Finite axes with at least two samples are required.')
    df, dt = float(np.median(np.diff(f))), float(np.median(np.diff(t)))
    if df <= 0 or dt <= 0 or not np.allclose(np.diff(f), df, rtol=1e-5, atol=1e-12) or not np.allclose(np.diff(t), dt):
        raise ValueError('Uniform, increasing frequency and time axes are required.')
    return [dict(c, frequency_mhz=float(f[c['start_freq_bin']]),
                 drift_rate_hz_per_s=float(c['drift_rate_bins_per_step'] * df * 1e6 / dt)) for c in candidates]
