"""
Signal sources for the receiver pipeline.

Right now (no hardware yet): SimulatedSource stands in for a real dish.
It generates a spectrogram (time x frequency power array) with realistic
noise plus an injected narrowband signal that drifts in frequency over
time -- the same basic shape as real telescope data and the same shape
you'll get from an RTL-SDR once it arrives.

In ~9-10 days, once the RTL-SDR dongle shows up: implement RTLSDRSource
below (stubbed out) and swap it in app.py. No other code changes needed --
detector.py and visualizer.py don't care where the data came from.

Later, to work with real Breakthrough Listen telescope data: implement
FileSource using the `blimpy` library (pip install blimpy) to load .fil
or .h5 files downloaded from https://breakthroughinitiatives.org/opendatasearch
"""

import numpy as np


class SimulatedSource:
    """Generates synthetic telescope-like data: noise + an injected
    narrowband signal that drifts in frequency (like a real transmitter
    would, due to Doppler shift from relative motion)."""

    def __init__(self, n_freq_bins=2048, n_time_steps=256,
                 freq_range_mhz=(1400.0, 1420.0), seed=None,
                 inject_signal=True, drift_rate_hz_per_s=0.4,
                 signal_strength=12.0):
        self.n_freq_bins = n_freq_bins
        self.n_time_steps = n_time_steps
        self.freq_min, self.freq_max = freq_range_mhz
        self.rng = np.random.default_rng(seed)
        self.inject_signal = inject_signal
        self.drift_rate_hz_per_s = drift_rate_hz_per_s
        self.signal_strength = signal_strength

    def capture(self):
        """Returns (freqs_mhz, times_s, power) -- power has shape
        (n_time_steps, n_freq_bins), same layout real filterbank data uses."""
        freqs = np.linspace(self.freq_min, self.freq_max, self.n_freq_bins)
        times = np.arange(self.n_time_steps)  # seconds, 1s integrations

        # background noise floor (chi-squared-like, as real radio noise is)
        power = self.rng.chisquare(df=2, size=(self.n_time_steps, self.n_freq_bins))

        if self.inject_signal:
            bandwidth_mhz = self.freq_max - self.freq_min
            hz_per_bin = (bandwidth_mhz * 1e6) / self.n_freq_bins
            start_bin = self.rng.integers(int(self.n_freq_bins * 0.2),
                                           int(self.n_freq_bins * 0.8))
            for t in times:
                drift_bins = (self.drift_rate_hz_per_s * t) / hz_per_bin
                bin_idx = int(round(start_bin + drift_bins))
                if 0 <= bin_idx < self.n_freq_bins:
                    power[t, bin_idx] += self.signal_strength

        return freqs, times, power


class RTLSDRSource:
    """Captures live signal from an RTL-SDR dongle.

    Needs: pip install pyrtlsdr, plus the librtlsdr system driver
    (installed via your OS -- see README setup steps) and the dongle
    plugged in.

    center_freq_hz: which frequency to listen on. Common space targets:
        137.1e6   NOAA-19 weather satellite (APT)
        137.62e6  NOAA-15
        137.9125e6 NOAA-18
        145.8e6   ISS voice/SSTV downlink (varies by activity)
    Note: this dongle's FC0013 tuner covers 22-1100 MHz, so the 1420 MHz
    hydrogen line is out of range -- these satellite targets are the
    right fit for it.
    """

    def __init__(self, center_freq_hz=137.1e6, sample_rate_hz=2.048e6,
                 n_time_steps=256, fft_size=2048, gain="auto"):
        from rtlsdr import RtlSdr
        self.sdr = RtlSdr()
        self.sdr.sample_rate = sample_rate_hz
        self.sdr.center_freq = center_freq_hz
        self.sdr.gain = gain
        self.n_time_steps = n_time_steps
        self.fft_size = fft_size

    def capture(self):
        power_rows = []
        for _ in range(self.n_time_steps):
            samples = self.sdr.read_samples(self.fft_size)
            spectrum = np.fft.fftshift(np.fft.fft(samples))
            power_rows.append(np.abs(spectrum) ** 2)
        power = np.array(power_rows)

        freq_offsets = np.fft.fftshift(np.fft.fftfreq(self.fft_size, d=1 / self.sdr.sample_rate))
        freqs_mhz = (self.sdr.center_freq + freq_offsets) / 1e6
        times = np.arange(self.n_time_steps)
        return freqs_mhz, times, power

    def close(self):
        self.sdr.close()


class FileSource:
    """TODO for real archived telescope data (e.g. Breakthrough Listen).

    pip install blimpy
    from blimpy import Waterfall
    obs = Waterfall(path_to_fil_or_h5_file)
    freqs = obs.get_freqs()
    power = obs.data  # shape roughly matches what we use here
    """

    def __init__(self, filepath):
        raise NotImplementedError(
            "Implement with blimpy.Waterfall once you have a real data file -- "
            "see class docstring."
        )
