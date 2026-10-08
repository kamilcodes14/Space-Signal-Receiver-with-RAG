"""Waterfall with channel-center coordinates and labeled relative power."""
import io
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def _draw_waterfall(freqs, times, power, candidates=None):
    fig, ax = plt.subplots(figsize=(10, 6))
    reference = max(float(np.median(power)), np.finfo(float).tiny)
    power_db = 10 * np.log10(np.maximum(power / reference, np.finfo(float).tiny))
    # Relative Hz avoids losing narrowband structure in a large MHz offset.
    offset_hz = (np.asarray(freqs) - freqs[0]) * 1e6
    im = ax.pcolormesh(offset_hz, times, power_db, shading='nearest', cmap='viridis')
    ax.invert_yaxis()
    ax.set_xlabel(f'Frequency offset from {freqs[0]:.9f} MHz (Hz)')
    ax.set_ylabel('Time (s)')
    ax.set_title('Waterfall - captured power and candidate tracks')
    fig.colorbar(im, ax=ax, label='Power / median power (dB)')
    df = float(np.median(np.diff(offset_hz)))
    for c in (candidates or [])[:5]:
        bins = c['start_freq_bin'] + c['drift_rate_bins_per_step'] * np.arange(len(times))
        valid = (bins >= 0) & (bins <= len(freqs) - 1)
        ax.plot(bins[valid] * df, np.asarray(times)[valid], 'r--', lw=1.3, alpha=.8)
    fig.tight_layout()
    return fig


def plot_waterfall(freqs, times, power, candidates=None, out_path='outputs/waterfall.png'):
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig = _draw_waterfall(freqs, times, power, candidates)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return str(path)


def plot_waterfall_bytes(freqs, times, power, candidates=None):
    fig = _draw_waterfall(freqs, times, power, candidates)
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150)
    plt.close(fig)
    return buf.getvalue()
