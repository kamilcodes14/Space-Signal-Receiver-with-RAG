"""
Main pipeline: capture -> detect -> visualize.

Run now, with simulated data:
    python src/app.py

Once the RTL-SDR dongle arrives, change ONE line in main() -- swap
SimulatedSource() for RTLSDRSource(...) -- everything downstream
(detector, visualizer) stays exactly the same.
"""

import argparse
import os
from source import SimulatedSource, RTLSDRSource
from detector import threshold_hits, dedoppler_search
from visualizer import plot_waterfall

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    parser = argparse.ArgumentParser(description="Space signal receiver pipeline")
    parser.add_argument("--source", choices=["simulated", "rtlsdr"], default="simulated",
                         help="Data source.")
    parser.add_argument("--freq-mhz", type=float, default=137.1,
                         help="Center frequency in MHz (rtlsdr source only). "
                              "137.1=NOAA-19, 137.62=NOAA-15, 137.9125=NOAA-18")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    parser.add_argument("--out", default=os.path.join(PROJECT_ROOT, "outputs", "waterfall.png"))
    args = parser.parse_args()

    # ---- 1. CAPTURE ----
    if args.source == "simulated":
        source = SimulatedSource(seed=args.seed)
    elif args.source == "rtlsdr":
        source = RTLSDRSource(center_freq_hz=args.freq_mhz * 1e6)
    else:
        raise NotImplementedError(f"Source '{args.source}' not wired up yet.")

    print(f"[receiver] capturing from source: {args.source}")
    freqs, times, power = source.capture()
    print(f"[receiver] captured {power.shape[0]} time steps x {power.shape[1]} freq bins "
          f"({freqs.min():.2f}-{freqs.max():.2f} MHz)")

    # ---- 2. DETECT ----
    hits, threshold = threshold_hits(power, n_sigma=5.0)
    print(f"[detector] {len(hits)} raw threshold hits (threshold={threshold:.1f})")

    candidates = dedoppler_search(power, n_sigma=20.0)
    print(f"[detector] {len(candidates)} drift-consistent candidate signal(s):")
    for c in candidates:
        freq_mhz = freqs.min() + c["start_freq_bin"] * (freqs.max() - freqs.min()) / len(freqs)
        print(f"    - ~{freq_mhz:.4f} MHz, drift {c['drift_rate_bins_per_step']} bins/step, "
              f"SNR {c['snr']}")

    # ---- 3. VISUALIZE ----
    out_path = plot_waterfall(freqs, times, power, candidates=candidates, out_path=args.out)
    print(f"[visualizer] saved waterfall plot -> {out_path}")


if __name__ == "__main__":
    main()
