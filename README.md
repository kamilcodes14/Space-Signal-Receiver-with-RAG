# Space Signal Receiver

A signal-detection pipeline built the same way real SETI/radio-astronomy
software works: **capture → detect → visualize**. Right now it runs on
simulated data so you can build and test the whole pipeline before your
RTL-SDR dongle arrives. Once it does, one line changes.

## Run it now (webpage version)

```bash
pip install -r requirements.txt
cd src
python app_web.py
```

Then open your browser to **http://localhost:5000** — you'll get a page
with a button to run a capture and see the waterfall plot right there,
no terminal reading required.

## Run it now (terminal/CLI version)

```bash
pip install -r requirements.txt
cd src
python3 app.py --seed 42
```

This will:
1. Generate a synthetic spectrogram (noise + one injected signal that
   drifts in frequency, like a real transmitter would from Doppler shift)
2. Run a de-doppler drift search to find it — the same core technique
   `turbo_seti` uses on real Breakthrough Listen telescope data
3. Save `outputs/waterfall.png` — a spectrogram with the detected
   signal's drift line marked in red

Try `--seed` with different numbers, or edit `SimulatedSource` in
`src/source.py` to change signal strength, drift rate, or turn the
injected signal off entirely (to confirm the detector stays quiet on
pure noise).

## Project structure

```
space-signal-receiver/
├── src/
│   ├── source.py       # where data comes from (simulated now, real hardware/files later)
│   ├── detector.py      # threshold + de-doppler drift search
│   ├── visualizer.py    # waterfall (spectrogram) plotting
│   └── app.py            # ties it all together
├── data/                  # put real downloaded telescope files here later
├── outputs/               # generated plots land here
└── requirements.txt
```

## Research assistant (optional)

A RAG-powered chat widget lives at the bottom-right of the web pages -
it answers questions grounded in your own indexed papers and run logs
(and can compare the two). See [RAG_SETUP.md](RAG_SETUP.md) to set it up.

## When the RTL-SDR dongle arrives — full setup

### 1. Driver install
- **Windows:** Plug the dongle in, then use [Zadig](https://zadig.akeo.ie/) to
  install the **WinUSB** driver for it (RTL-SDR dongles show up as a DVB-T TV
  tuner by default — Zadig replaces that driver so SDR software can use it).
- **Linux:** `sudo apt-get install rtl-sdr librtlsdr-dev` then unplug/replug
  the dongle. Run `rtl_test` — it should detect the device and print tuner
  info (`Found 1 device`, `Detached kernel driver`, etc.).
- **Mac:** `brew install librtlsdr`

### 2. Sanity-check it with a GUI tool first
Before touching any code, confirm the hardware itself works:
- **GQRX** (Linux/Mac) or **SDR#** (Windows) — free SDR receiver apps.
- Tune to a local FM station (e.g. 100-105 MHz) and confirm you hear audio.
  If that works, the dongle, driver, and antenna chain are all good.

### 3. Get a pass-prediction tool
Satellites are only overhead for ~10-15 minutes per pass. Use
**[Gpredict](http://gpredict.oz9aec.net/)** (free, cross-platform) or
`n2yo.com` in a browser — enter your location (Lahore) and it tells you
exactly when NOAA-19, NOAA-15, NOAA-18, or the ISS next pass overhead,
and how high above the horizon (higher = stronger signal).

### 4. Antenna note
The small antenna these dongles ship with is fine for FM/local testing but
weak for satellites. A simple wire **V-dipole cut for ~137 MHz** (roughly
two ~52 cm wire legs) is a common cheap DIY upgrade and dramatically
improves NOAA satellite reception. Not required to get started, but worth
it once you've confirmed the basic chain works.

### 5. Capture a real pass with our pipeline
Once Gpredict shows a pass starting:

```bash
python3 app.py --source rtlsdr --freq-mhz 137.1
```
(swap 137.1 for whichever satellite is passing — see the frequency list
in `source.py`'s `RTLSDRSource` docstring)

This runs the exact same capture → de-doppler search → waterfall pipeline
you already tested on simulated data — except now `power` comes from real
IQ samples pulled live off the dongle via `pyrtlsdr`. A real satellite
pass has genuine Doppler drift as it moves overhead, so this is a
legitimate test of the same drift-search code, on a real signal.

`pip install pyrtlsdr` is needed for this (already in `requirements.txt`,
commented out — uncomment it once the dongle's here).

## Working with real telescope data (no hardware needed)

Berkeley's Breakthrough Listen project publishes real raw/reduced SETI
telescope data for free, including a tutorial on detecting the Voyager 1
spacecraft's actual signal in real Green Bank Telescope data:
`github.com/UCBerkeleySETI/breakthrough`

To use it: `pip install blimpy`, download a sample `.fil`/`.h5` file, and
implement `FileSource` in `src/source.py` using `blimpy.Waterfall` — same
`(freqs, times, power)` contract again.

## Extending it (ties into AstroML)

The natural next step, given the exoplanet-detection ML work already
done in AstroML: train a classifier to distinguish real candidate
signals from RFI (radio-frequency interference) in the spectrograms —
an active problem in real SETI pipelines.
