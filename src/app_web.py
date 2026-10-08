"""
Web version of the receiver — same pipeline, just with a webpage instead
of a terminal.

Run it:
    python app_web.py

Then open your browser to:
    http://localhost:5000
"""

import base64
from flask import Flask, render_template_string, request

from source import SimulatedSource
from detector import threshold_hits, dedoppler_search, physical_candidates
from visualizer import plot_waterfall_bytes

app = Flask(__name__)

# Research assistant widget (RAG over data/docs + data/logs) — optional.
# Imported defensively so the core signal-detection pages still work even
# before `pip install -r requirements.txt` pulls in the new RAG deps.
try:
    from rag_api.chat import chat_bp
    app.register_blueprint(chat_bp)
    RAG_WIDGET_ENABLED = True
except ImportError as exc:
    print(f"[rag] research assistant widget disabled - missing dependency: {exc}")
    RAG_WIDGET_ENABLED = False

WIDGET_SCRIPT_TAG = '<script src="/static/chat_widget.js"></script>' if RAG_WIDGET_ENABLED else ""

HOME_PAGE = """
<!doctype html>
<html>
<head>
  <title>Hello Space</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: -apple-system, Segoe UI, Arial, sans-serif;
           background: #0d1117; color: #e6edf3; margin: 0;
           height: 100vh; display: flex; align-items: center; justify-content: center;
           text-align: center; }
    h1 { font-size: 3em; margin-bottom: 0; }
    p { color: #8b949e; font-size: 1.1em; }
    a.button { display: inline-block; margin-top: 24px; padding: 12px 28px;
               background: #2f81f7; color: white; text-decoration: none;
               border-radius: 8px; font-size: 1.05em; }
    a.button:hover { background: #1f6feb; }
  </style>
</head>
<body>
  <div>
    <h1>🛰️ Hello Space</h1>
    <p>A signal-detection pipeline for real and simulated space signals.</p>
    <a class="button" href="/signal">Go to Signal Receiver →</a>
  </div>
  {{ widget_script|safe }}
</body>
</html>
"""

SIGNAL_PAGE = """
<!doctype html>
<html>
<head>
  <title>Signal Receiver</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: -apple-system, Segoe UI, Arial, sans-serif; max-width: 800px;
           margin: 40px auto; padding: 0 16px; background: #0d1117; color: #e6edf3; }
    h1 { font-size: 1.6em; }
    a.back { color: #8b949e; text-decoration: none; font-size: 0.9em; }
    a.back:hover { color: #e6edf3; }
    form { background: #161b22; padding: 16px; border-radius: 8px; border: 1px solid #30363d;
           margin-top: 16px; }
    label { display: block; margin: 10px 0; }
    input[type=number] { padding: 6px; border-radius: 4px; border: 1px solid #30363d;
                          background: #0d1117; color: #e6edf3; width: 100px; }
    button { margin-top: 12px; padding: 10px 20px; border: none; border-radius: 6px;
             background: #2f81f7; color: white; font-size: 1em; cursor: pointer; }
    button:hover { background: #1f6feb; }
    .results { margin-top: 24px; padding: 16px; background: #161b22; border-radius: 8px;
               border: 1px solid #30363d; }
    .candidate { padding: 6px 0; border-bottom: 1px solid #21262d; }
    img { max-width: 100%; border-radius: 6px; margin-top: 12px; border: 1px solid #30363d; }
    .stat { color: #8b949e; }
  </style>
</head>
<body>
  <a class="back" href="/">← Back to Home</a>
  <h1>📡 Signal Receiver</h1>
  <form method="POST" action="/signal">
    <label>Seed (change this to get a different simulated capture):
      <input type="number" name="seed" value="{{ seed }}">
    </label>
    <label>
      <input type="checkbox" name="inject_signal" {% if inject_signal %}checked{% endif %}>
      Inject a signal (uncheck for a noise-only test; false positives are possible)
    </label>
    <button type="submit">Capture &amp; Detect</button>
  </form>

  {% if ran %}
  <div class="results">
    <p class="stat">Captured {{ n_time }} time steps × {{ n_freq }} freq bins
       ({{ freq_min }}–{{ freq_max }} MHz)</p>
    <h3>{{ n_candidates }} candidate signal(s) found</h3>
    {% for c in candidates %}
    <div class="candidate">~{{ c.freq_mhz }} MHz &nbsp;|&nbsp; drift {{ c.drift }} Hz/s &nbsp;|&nbsp; excess-power score {{ c.snr }}</div>
    {% endfor %}
    <img src="data:image/png;base64,{{ image_b64 }}" alt="waterfall plot">
  </div>
  {% endif %}
  {{ widget_script|safe }}
</body>
</html>
"""


def run_pipeline(seed, inject_signal):
    source = SimulatedSource(seed=seed, inject_signal=inject_signal)
    freqs, times, power = source.capture()
    threshold_hits(power)  # kept for parity with the CLI pipeline; not shown in the UI
    raw_candidates = dedoppler_search(power, n_sigma=6.0)

    candidates = []
    for c in physical_candidates(raw_candidates, freqs, times):
        freq_mhz = c["frequency_mhz"]
        candidates.append({
            "freq_mhz": round(float(freq_mhz), 9),
            "drift": round(c["drift_rate_hz_per_s"], 4),
            "snr": round(c["snr"], 2),
        })

    png_bytes = plot_waterfall_bytes(freqs, times, power, candidates=raw_candidates)
    image_b64 = base64.b64encode(png_bytes).decode("ascii")

    return freqs, power, candidates, image_b64


@app.route("/", methods=["GET"])
def index():
    return render_template_string(HOME_PAGE, widget_script=WIDGET_SCRIPT_TAG)


@app.route("/signal", methods=["GET", "POST"])
def signal():
    if request.method == "GET":
        return render_template_string(
            SIGNAL_PAGE, ran=False, seed=42, inject_signal=True,
            widget_script=WIDGET_SCRIPT_TAG,
        )

    try:
        seed = int(request.form.get("seed", 42))
        if not 0 <= seed <= 2**32 - 1:
            raise ValueError
    except (ValueError, TypeError):
        return "Seed must be an integer between 0 and 4294967295.", 400
    inject_signal = request.form.get("inject_signal") == "on"

    freqs, power, candidates, image_b64 = run_pipeline(seed, inject_signal)

    return render_template_string(
        SIGNAL_PAGE, ran=True, seed=seed, inject_signal=inject_signal,
        n_time=power.shape[0], n_freq=power.shape[1],
        freq_min=round(float(freqs.min()), 9), freq_max=round(float(freqs.max()), 9),
        n_candidates=len(candidates), candidates=candidates,
        image_b64=image_b64,
        widget_script=WIDGET_SCRIPT_TAG,
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
