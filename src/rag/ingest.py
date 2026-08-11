"""
Builds the vector index for the RAG assistant.

Two source types are indexed, tagged separately so the agent can tell
the model (and the user) where an answer came from:

  data/docs/   research papers, tutorials, README-style docs
               (.pdf, .docx, .md, .txt)
  data/logs/   this project's own outputs: waterfall run summaries,
               detection results, telemetry notes
               (.txt, .json, .md, .png/.jpg - waterfall plots etc.)

Images (waterfall plots, spectrograms) are captioned with Claude's
vision before embedding, so questions like "what did the plot for
run 042 look like" retrieve normally, same as any text chunk. This
means an ANTHROPIC_API_KEY is needed at ingest time if any image
files are present (not just at chat time).

Run:
    python -m rag.ingest

Produces rag_index/index.faiss + rag_index/metadata.json
"""

import base64
import json
import mimetypes
import os
import re
from pathlib import Path

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "data" / "docs"
LOGS_DIR = ROOT / "data" / "logs"
INDEX_DIR = ROOT / "rag_index"
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"  # small, free, runs locally

CHUNK_SIZE = 800       # characters per chunk
CHUNK_OVERLAP = 150    # characters shared between consecutive chunks
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

CAPTION_PROMPT = (
    "Describe this image in detail for a technical knowledge base entry. "
    "If it's a waterfall plot or spectrogram, describe the axes, any "
    "visible signal features (approximate frequency, drift direction/rate, "
    "intensity or SNR appearance, width), and anything notable a radio "
    "astronomer reviewing detections would care about. Be specific and "
    "factual - don't speculate about anything not visibly present."
)

_vision_client = None


def _get_vision_client():
    """Lazy import + init so ingest.py works without ANTHROPIC_API_KEY
    when there are no image files to caption."""
    global _vision_client
    if _vision_client is None:
        import anthropic

        _vision_client = anthropic.Anthropic()
    return _vision_client


def read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def read_pdf_file(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def read_docx_file(path: Path) -> str:
    from docx import Document

    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs)


def caption_image(path: Path) -> str:
    """Uses Claude vision to turn an image into an indexable text description."""
    media_type = mimetypes.guess_type(str(path))[0] or "image/png"
    data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")

    client = _get_vision_client()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}},
                    {"type": "text", "text": CAPTION_PROMPT},
                ],
            }
        ],
    )
    caption = "".join(b.text for b in response.content if b.type == "text")
    return f"[Image: {path.name}] {caption}"


def load_source(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return read_pdf_file(path)
    if suffix == ".docx":
        return read_docx_file(path)
    if suffix in IMAGE_EXTENSIONS:
        return caption_image(path)
    return read_text_file(path)


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
    """Simple sliding-window chunker on whitespace-normalized text."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start += size - overlap
    return chunks


def collect_chunks():
    """Walk data/docs and data/logs, return list of (text, metadata)."""
    records = []

    allowed_ext = {".pdf", ".docx", ".md", ".txt", ".json"} | IMAGE_EXTENSIONS

    for source_dir, source_type in [(DOCS_DIR, "doc"), (LOGS_DIR, "log")]:
        if not source_dir.exists():
            continue
        for path in sorted(source_dir.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in allowed_ext:
                continue
            is_image = path.suffix.lower() in IMAGE_EXTENSIONS
            try:
                raw = load_source(path)
            except Exception as exc:  # noqa: BLE001 - report and skip bad files
                print(f"  skip {path.name}: {exc}")
                continue

            # Image captions are already a single short chunk - don't
            # re-split them with the same sliding window as long text.
            chunks = [raw] if is_image else chunk_text(raw)

            for i, chunk in enumerate(chunks):
                records.append(
                    {
                        "text": chunk,
                        "source": path.name,
                        "source_type": source_type,  # "doc" or "log"
                        "modality": "image" if is_image else "text",
                        "chunk_index": i,
                    }
                )
    return records


def build_index():
    print("Scanning data/docs and data/logs ...")
    records = collect_chunks()
    if not records:
        print("No files found. Add papers/docs to data/docs/ and logs to data/logs/, then rerun.")
        return

    print(f"Found {len(records)} chunks. Loading embedding model ({EMBED_MODEL_NAME}) ...")
    model = SentenceTransformer(EMBED_MODEL_NAME)

    texts = [r["text"] for r in records]
    embeddings = model.encode(texts, show_progress_bar=True, normalize_embeddings=True)
    embeddings = np.asarray(embeddings, dtype="float32")

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)  # inner product on normalized vectors = cosine similarity
    index.add(embeddings)

    INDEX_DIR.mkdir(exist_ok=True)
    faiss.write_index(index, str(INDEX_DIR / "index.faiss"))
    with open(INDEX_DIR / "metadata.json", "w", encoding="utf-8") as f:
        json.dump({"model": EMBED_MODEL_NAME, "records": records}, f, indent=2)

    print(f"Saved index with {len(records)} chunks to {INDEX_DIR}/")


if __name__ == "__main__":
    build_index()
