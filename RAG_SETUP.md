# Research assistant (RAG) - setup

Already wired into `src/app_web.py` (registered as a blueprint, loaded
defensively so the core signal-detection pages keep working even before
you've installed these extra deps).

## 1. Install dependencies
```
pip install -r requirements.txt
```

## 2. Add content to index
- Put research papers / tutorials in `src/data/docs/` - PDF, Word
  (`.docx`), Markdown, or plain text. e.g. Breakthrough Listen docs,
  turbo_seti / blimpy references, any SETI papers you're citing.
- Put this project's own outputs in `src/data/logs/` - `.txt`/`.json`/`.md`
  notes, **or drop a `waterfall.png` / spectrogram image in directly**.
  Images are captioned by Claude vision at ingest time (see step 3 first -
  it needs the API key), so a plot becomes a normal searchable chunk
  without you writing a text summary by hand.

## 3. Set your API key
```
export ANTHROPIC_API_KEY=sk-ant-...
```
Needed for both ingest (only if you have image files to caption) and chat.

## 4. Build the index
```
cd src
python -m rag.ingest
```
This creates `src/rag_index/index.faiss` and `src/rag_index/metadata.json`
(gitignored - rebuild locally / on deploy, don't commit it).
Rerun this any time you add new docs, logs, or images.

## 5. Run it
```
cd src
python app_web.py
```
Open http://localhost:5000, click the pulsing dot bottom-right, ask
something like:
- "what's a de-doppler drift search" -> should answer from src/data/docs
- "did my last run detect anything" -> should answer from src/data/logs
- "is the drift rate in my last run consistent with what the papers expect"
  -> should search both and compare

If you see `[rag] research assistant widget disabled - missing dependency: ...`
printed on startup, the page still works fine - just install the deps from
step 1 and restart.

## Optional: general web search
By default the agent only knows `src/data/docs/` + `src/data/logs/` (plus
Claude's own general knowledge). To let it *also* search the live web for
anything outside your index - current events, a paper you haven't added,
fact verification - turn it on:
```
export RAG_ENABLE_WEB_SEARCH=true
```
This adds Anthropic's built-in `web_search` tool (`web_search_20250305`) to
the agent, capped at 3 searches per question (`WEB_SEARCH_MAX_USES` in
`src/rag/agent.py`). Two things to know:
- It must be enabled for your account in the Anthropic Console first
  (Settings -> tool usage), separate from this env var.
- It's billed per search ($10 / 1,000 searches as of this writing - check
  the Anthropic pricing page for current rates) on top of normal token
  costs, so it's off unless you explicitly ask for it.

With it off (the default), the agent stays scoped to your project's own
docs/logs - which is the stronger, more citable demo for a portfolio piece.
Web sources it uses show up in the returned `sources` list prefixed `web:`.

## Notes
- The agent (`src/rag/agent.py`) uses Claude's native tool-calling loop: it
  decides itself whether to search, how to phrase the query, whether to
  search docs/logs/both, and whether to reformulate and try again
  (capped at 4 rounds) before answering or admitting it couldn't find
  enough information.
- Swap `EMBED_MODEL_NAME` in `src/rag/ingest.py` for a different
  sentence-transformers model if you want higher quality at the cost of
  a larger download.
- The blueprint lives in `src/rag_api/` rather than a top-level `api/`
  folder on purpose - this repo's `vercel.json` already pins `app.py` as
  the one Vercel function, and a top-level `api/` directory is Vercel's
  default convention for auto-detecting *separate* serverless functions.
  Naming it `rag_api` keeps `chat.py` a plain module imported into the one
  existing Flask app instead of risking a second, unwanted function.
- Deploying to Vercel: you'll need to set `ANTHROPIC_API_KEY` as a Vercel
  environment variable, and either commit a prebuilt `rag_index/` or run
  the ingest step as part of your build - Vercel's serverless filesystem
  is read-only at request time, so `python -m rag.ingest` can't run
  on-demand there the way it can locally.
