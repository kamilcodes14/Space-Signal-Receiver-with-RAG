"""
Detection logic -- finds candidate signals in a power spectrogram.

Two layers, same as real SETI pipelines (just simplified):
1. threshold_hits: flag any bin that's way above the noise floor.
2. dedoppler_search: real signals drift in frequency over time (Doppler
   shift). Random noise spikes don't follow a consistent drift line, so
   summing power along candidate drift lines separates real signals from
   noise far more reliably than a single-frame threshold does. This is a
   simplified version of what turbo_seti does on real telescope data.
"""

import numpy as np


def threshold_hits(power, n_sigma=5.0):
    """Return (time_idx, freq_idx) pairs for bins above noise_mean + n_sigma*std."""
    noise_mean = np.median(power)
    noise_std = np.std(power)
    threshold = noise_mean + n_sigma * noise_std
    hit_times, hit_freqs = np.where(power > threshold)
    return list(zip(hit_times, hit_freqs)), threshold


def dedoppler_search(power, drift_rates_bins_per_step=None, n_sigma=6.0):
    """Brute-force de-doppler search: for each candidate drift rate, sum
    power along that diagonal line through the spectrogram. A real drifting
    signal lights up one line consistently; noise doesn't.

    Returns a list of dicts: {drift_rate, start_freq_bin, snr}
    """
    n_time, n_freq = power.shape
    if drift_rates_bins_per_step is None:
        drift_rates_bins_per_step = np.linspace(-2.0, 2.0, 41)  # bins/step

    noise_mean = np.median(power)
    noise_std = np.std(power)

    candidates = []
    for drift in drift_rates_bins_per_step:
        for start_bin in range(n_freq):
            bin_indices = np.round(start_bin + drift * np.arange(n_time)).astype(int)
            valid = (bin_indices >= 0) & (bin_indices < n_freq)
            if valid.sum() < n_time * 0.8:  # signal must stay in-band most of the time
                continue
            path_power = power[np.arange(n_time)[valid], bin_indices[valid]]
            total = path_power.sum()
            expected = noise_mean * valid.sum()
            snr = (total - expected) / (noise_std * np.sqrt(valid.sum()))
            if snr > n_sigma:
                candidates.append({
                    "drift_rate_bins_per_step": round(float(drift), 3),
                    "start_freq_bin": int(start_bin),
                    "snr": round(float(snr), 2),
                })

    # de-duplicate: keep the strongest candidate per rough frequency neighborhood
    candidates.sort(key=lambda c: -c["snr"])
    kept = []
    used_bins = set()
    for c in candidates:
        neighborhood = c["start_freq_bin"] // 10
        if neighborhood not in used_bins:
            kept.append(c)
            used_bins.add(neighborhood)
    return kept
