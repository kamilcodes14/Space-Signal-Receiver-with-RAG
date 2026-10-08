# Space Signal Receiver with RAG

A Python prototype for **capture -> linear-drift search -> waterfall -> run log**,
with an optional research assistant over your documents and saved results.
The pipeline supports synthetic spectrograms, an RTL-SDR adapter, and bounded
Breakthrough Listen `.fil`/`.h5` selections through `blimpy`.

**Validation status:** tested on 300 synthetic signal observations, 100 noise-only
observations, and Berkeley's known Voyager 1 Green Bank Telescope example.
This reproduces a known spacecraft signal; it is not a discovery, a blind SETI
survey, or proof that an arbitrary candidate is astronomical. Hardware capture
has been unit-tested using a fake device, not validated with a physical dongle.

## Run a local simulation

Use Python 3.12 for the exact validated environment:

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements-core.txt
python src/app.py --seed 42
python src/app.py --seed 42 --no-signal --out outputs/noise.png
```

The CLI saves a waterfall PNG and a timestamped JSON record in `src/data/logs/`.
It reports start frequency in MHz, drift in Hz/s, and an **excess-power score**.
The JSON field `snr` retains its original name for compatibility; it is not a
calibrated signal-to-noise measurement or false-alarm probability.

The defaults use 1 Hz frequency channels and 1 s time steps, with a 0.4 Hz/s
injection that visibly moves across channels. Set `--strength` and `--drift-hz-s`
to explore sensitivity. Simulations are independent exponential power noise plus
an additive nearest-bin track, without spectral leakage or an RF transfer model.

## Web interface

```bash
python src/app_web.py
```

Open http://localhost:5000. Use the seed and injection checkbox to run the
simulation. This view keeps plots in memory; CLI run logs are the persistent
input to the optional research assistant. Hosted deployments need their own
persistent log storage; the browser is not receiving signals from a local dongle.

## Reproduce the experiments

```bash
pip install -r requirements-validation-lock.txt
python -m pytest -q
python scripts/benchmark.py --seeds 25 --noise-seeds 100
python scripts/validate_voyager.py --download
```

The lock file records the environment used for the committed results (Python
3.12). `requirements-research.txt` offers broader version ranges, but exact
reproduction should use the lock file. The optional RAG stack is separate and
was not part of these experiments.

`--download` retrieves the approximately 48 MiB public Berkeley file and verifies
its SHA256. The tutorial's HTTP download worked in the validation environment;
HTTPS returned HTTP 502. Hash verification checks against the exact bytes used
here; it is not a substitute for publisher-provided authenticity metadata.
If the upstream server is unavailable, obtain the unchanged file separately and
pass `--file` to the validation script. Telescope data are not committed to Git.

Read **[the validation report](reports/VALIDATION.md)** for all results,
confidence intervals, provenance, limitations, and remaining work.

## Analyze a telescope sub-band

```bash
python src/app.py --source file \
  --file data/Voyager1.single_coarse.fine_res.h5 \
  --f-start 8419.296 --f-stop 8419.298 --max-time-steps 16 \
  --max-drift-bins 4 --out outputs/voyager.png
```

Frequency bounds are in MHz. Search range is in **bins per integration**;
conversion to Hz/s uses the actual channel spacing and integration interval.
The default grid spaces track endpoints at most one channel apart. Select a
small sub-band: this is a prototype brute-force algorithm, not a scalable survey
search. Only single-IF data are supported; the adapter does not silently average
polarizations. The current detector does not incorporate file masks, calibrated
bandpass removal, barycentric corrections, or RFI rejection.

## Hardware adapter (not field-validated)

Install your device's system drivers and `pyrtlsdr`, then choose a frequency your
hardware supports and a transmitter known to be active:

```bash
python src/app.py --source rtlsdr --freq-mhz 137.1
```

The frequency above is only an example, not a claim that a satellite is active
there. Each 2048-sample FFT at 2.048 MS/s represents **1 ms** of samples.
The 256-frame default capture is about 0.256 s and is generally too short/coarse
for slow astronomical drift measurements. Longer captures, channelization,
windowing, averaging, gain/bandpass calibration, and dropped-sample detection
need development and real hardware evaluation. A USB dongle attached to your
computer is accessed by a local process, not by a cloud-hosted web application.

## Optional research assistant

See [RAG_SETUP.md](RAG_SETUP.md). Add reference documents to `src/data/docs/`;
CLI captures create JSON logs in `src/data/logs/`. Rebuild the index after runs:

```bash
pip install -r requirements.txt
cd src
python -m rag.ingest
```

Image captioning and chat require an Anthropic API key. No live LLM/RAG calls were
made as part of the signal-validation report. Image captions are interpretations,
not substitutes for the numerical run records.

## Layout

- `src/source.py`: synthetic, sample-clock SDR, and telescope-file sources.
- `src/detector.py`: mean-centered drift search and conversion to physical units.
- `src/visualizer.py`: frequency-offset waterfall plots.
- `src/app.py`, `src/app_web.py`: CLI and simulation web interface.
- `scripts/`: reproducible experiments and data retrieval.
- `tests/`: algorithm, units, file-reader, CLI, and web checks.
- `reports/`: committed measurements, plots, provenance, and limitations.

## Attribution

The real-data example follows the [UC Berkeley SETI blimpy Voyager tutorial](https://github.com/UCBerkeleySETI/blimpy/blob/master/examples/voyager.ipynb).
The detector here is a small nearest-bin brute-force implementation, not an
implementation or performance equivalent of `turboSETI`. This validation update
was developed with AI assistance; reviewing the code and reproducing the results
is necessary before representing it as independently performed research.
