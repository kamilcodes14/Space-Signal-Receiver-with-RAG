"""
Root-level entrypoint for Vercel. Vercel's Flask framework detection looks
for a file named app.py (among a few other names) at the project root
with a Flask instance called `app`. The real app lives in src/app_web.py
so local dev (python src/app_web.py) keeps working unchanged -- this file
just re-exports it for deployment.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from app_web import app  # noqa: E402  (re-exported for Vercel to find)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
