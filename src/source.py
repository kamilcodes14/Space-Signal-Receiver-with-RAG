"""Spectrogram sources; frequency centers in MHz, sample centers in seconds.

All sources return (freqs_mhz, times_s, power[time, frequency]). Hardware
and telescope adapters do not imply that an observation is astronomical.
"""
from pathlib import Path
import numpy as np


class SimulatedSource:
    """Independent exponential power noise plus a nearest-bin linear track.

    Default resolution is 1 Hz/bin with 1 s integrations, so the default
    0.4 Hz/s signal traverses about 51 bins. No sub-bin leakage is modeled.
    """
    def __init__(self, n_freq_bins=512, n_time_steps=128,
                 freq_range_mhz=(1420.0, 1420.000512), seed=None,
                 inject_signal=True, drift_rate_hz_per_s=0.4,
                 signal_strength=3.0, time_step_s=1.0, start_bin=None):
        if n_freq_bins < 2 or n_time_steps < 2:
            raise ValueError('At least two frequency bins and time steps are required.')
        if not np.isfinite(time_step_s) or time_step_s <= 0:
            raise ValueError('time_step_s must be positive and finite.')
        if not np.all(np.isfinite(freq_range_mhz)) or freq_range_mhz[1] <= freq_range_mhz[0]:
            raise ValueError('Frequency bounds must be finite and increasing.')
        if not np.isfinite(signal_strength) or signal_strength < 0 or not np.isfinite(drift_rate_hz_per_s):
            raise ValueError('Signal strength must be nonnegative and drift finite.')
        if start_bin is not None and not 0 <= start_bin < n_freq_bins:
            raise ValueError('start_bin must be in band.')
        self.n_freq_bins, self.n_time_steps = n_freq_bins, n_time_steps
        self.freq_min, self.freq_max = freq_range_mhz
        self.rng = np.random.default_rng(seed)
        self.inject_signal, self.drift_rate_hz_per_s = inject_signal, drift_rate_hz_per_s
        self.signal_strength, self.time_step_s = signal_strength, time_step_s
        self.start_bin = start_bin
        self.truth = None

    def capture(self):
        freqs = np.linspace(self.freq_min, self.freq_max, self.n_freq_bins, endpoint=False)
        times = np.arange(self.n_time_steps) * self.time_step_s
        power = self.rng.chisquare(df=2, size=(self.n_time_steps, self.n_freq_bins))
        self.truth = None
        if self.inject_signal:
            df_hz = (freqs[1] - freqs[0]) * 1e6
            start = self.start_bin if self.start_bin is not None else self.n_freq_bins // 2
            drift = self.drift_rate_hz_per_s * self.time_step_s / df_hz
            bins = np.rint(start + drift * np.arange(self.n_time_steps)).astype(int)
            valid = (bins >= 0) & (bins < self.n_freq_bins)
            power[np.arange(self.n_time_steps)[valid], bins[valid]] += self.signal_strength
            self.truth = {'start_freq_bin': int(start), 'drift_rate_bins_per_step': float(drift),
                          'drift_rate_hz_per_s': self.drift_rate_hz_per_s,
                          'signal_strength': self.signal_strength, 'in_band_steps': int(valid.sum())}
        return freqs, times, power


class RTLSDRSource:
    """Unaveraged FFT frames from consecutive SDR samples (not 1 s frames).

    Time coordinates use sample count / sample rate and assume no dropped
    samples; USB timing/dropouts and RF calibration require hardware validation.
    """
    def __init__(self, center_freq_hz=137.1e6, sample_rate_hz=2.048e6,
                 n_time_steps=256, fft_size=2048, gain='auto'):
        from rtlsdr import RtlSdr
        if fft_size < 2 or n_time_steps < 2 or sample_rate_hz <= 0:
            raise ValueError('Invalid SDR capture dimensions or sample rate.')
        self.sdr = RtlSdr()
        try:
            self.sdr.sample_rate = sample_rate_hz
            self.sdr.center_freq = center_freq_hz
            self.sdr.gain = gain
        except Exception:
            self.sdr.close()
            raise
        self.n_time_steps, self.fft_size = n_time_steps, fft_size

    def capture(self):
        power = []
        for _ in range(self.n_time_steps):
            samples = self.sdr.read_samples(self.fft_size)
            if len(samples) != self.fft_size:
                raise ValueError('Short SDR frame; cannot assign a reliable sample time axis.')
            spectrum = np.fft.fftshift(np.fft.fft(samples))
            power.append(np.abs(spectrum) ** 2)
        offsets = np.fft.fftshift(np.fft.fftfreq(self.fft_size, d=1 / self.sdr.sample_rate))
        freqs = (self.sdr.center_freq + offsets) / 1e6
        times = (np.arange(self.n_time_steps) + 0.5) * self.fft_size / self.sdr.sample_rate
        return freqs, times, np.asarray(power)

    def close(self):
        self.sdr.close()


class FileSource:
    """Load a bounded .fil/.h5 sub-band with blimpy (optional dependency).

    Time spacing and channel centers come from the file header. Descending
    frequency axes are reversed together with the data. Only single-IF data
    are supported; polarization averaging is never silently assumed.
    """
    def __init__(self, filepath, f_start=None, f_stop=None, max_time_steps=256):
        self.filepath = Path(filepath)
        if not self.filepath.is_file():
            raise FileNotFoundError(self.filepath)
        if max_time_steps < 2:
            raise ValueError('max_time_steps must be at least two.')
        self.f_start, self.f_stop = f_start, f_stop
        self.max_time_steps = max_time_steps

    def capture(self):
        from blimpy import Waterfall
        obs = Waterfall(str(self.filepath), f_start=self.f_start, f_stop=self.f_stop,
                        t_start=0, t_stop=self.max_time_steps, max_load=0.25)
        power = np.asarray(obs.data, dtype=float)
        if power.ndim != 3 or power.shape[1] != 1:
            raise ValueError('Expected a loaded time x 1 IF x frequency sub-band. Select a smaller band if not loaded.')
        power = power[:, 0, :]
        freqs = np.asarray(obs.container.populate_freqs(), dtype=float)
        dt = float(obs.header['tsamp'])
        if not np.isfinite(dt) or dt <= 0:
            raise ValueError('Invalid integration time in telescope header.')
        times = np.arange(power.shape[0]) * dt
        if freqs[0] > freqs[-1]:
            freqs, power = freqs[::-1], power[:, ::-1]
        if power.shape != (len(times), len(freqs)) or min(power.shape) < 2:
            raise ValueError('File data and axes do not agree, or selection is too small.')
        return freqs, times, power
