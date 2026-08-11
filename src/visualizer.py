"""Waterfall (spectrogram) plotting -- the standard view radio astronomers
use: frequency on x, time on y, signal power as color."""

import io
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def _draw_waterfall(freqs, times, power, candidates=None):
    fig, ax = plt.subplots(figsize=(10, 6))
    power_db = 10 * np.log10(power - power.min() + 1e-6)

    extent = [freqs.min(), freqs.max(), times.max(), times.min()]
    im = ax.imshow(power_db, aspect="auto", extent=extent, cmap="viridis")
    ax.set_xlabel("Frequency (MHz)")
    ax.set_ylabel("Time (s)")
    ax.set_title("Waterfall — captured signal")
    fig.colorbar(im, ax=ax, label="Power (dB, relative)")

    if candidates:
        n_freq = power.shape[1]
        freq_per_bin = (freqs.max() - freqs.min()) / n_freq
        for c in candidates:
            f0 = freqs.min() + c["start_freq_bin"] * freq_per_bin
            f1 = f0 + c["drift_rate_bins_per_step"] * freq_per_bin * (len(times) - 1)
            ax.plot([f0, f1], [times.min(), times.max()], "r--", linewidth=1.5, alpha=0.8)
            ax.annotate(f"SNR {c['snr']}", (f0, times.min()), color="red", fontsize=8)

    fig.tight_layout()
    return fig


def plot_waterfall(freqs, times, power, candidates=None, out_path="outputs/waterfall.png"):
    """Saves to disk. Used by the CLI (app.py) for local runs."""
    fig = _draw_waterfall(freqs, times, power, candidates)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path


def plot_waterfall_bytes(freqs, times, power, candidates=None):
    """Returns raw PNG bytes, no disk write. Used by app_web.py so it works
    on serverless platforms (Vercel) where the filesystem isn't writable/
    persistent between requests."""
    fig = _draw_waterfall(freqs, times, power, candidates)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf.read()
