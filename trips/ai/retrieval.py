"""
Semantic search over TakeOff's destination guides (the retrieval half of "Ask about this trip").

The guides live in `knowledge/destination_guides.md`, one document per city. They are split the way that worked
best in our A8 experiments: section-aware ("hybrid") chunks of at most AI_ASK_CHUNK_WORDS words (60), cut only at
sentence ends and never across paragraphs, each prefixed with its city and topic ("Kyoto, Japan / Getting there and
around: ..."), so a chunk that never names its city still carries it. Whole-paragraph chunks hid facts that sit at
the end of a mixed-topic paragraph (A8, Venice flooding), which is why the size is capped.

The embedding model loads once, the first time someone asks a question, and the chunk vectors are computed at the
same time and kept in memory (60 chunks take well under a second to search). Weights come from the Hugging Face Hub
and are cached on disk by `sentence-transformers`; nothing is written to the project folder.
"""

import re
import threading
from collections import defaultdict
from pathlib import Path

import numpy as np
from django.conf import settings

GUIDES_PATH = Path(__file__).resolve().parent / "knowledge" / "destination_guides.md"

# BGE models expect this instruction in front of short search queries (from the model card); others need none.
QUERY_PREFIXES = {"bge": "Represent this sentence for searching relevant passages: "}

_ABBREV = re.compile(r"\b(St|Mt|Dr|Mr|Mrs|Ms|vs|approx|e\.g|i\.e)\.", re.I)

_lock = threading.Lock()
_index = {}


class SearchUnavailable(Exception):
    """The embedding model is switched off or could not be loaded."""


def sentences(text):
    """Split text into sentences on . ! ? followed by a capital, keeping abbreviations such as 'St.' intact."""
    protected = _ABBREV.sub(lambda m: m.group(0).replace(".", "<DOT>"), text)
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9"])', protected)
    return [p.replace("<DOT>", ".").strip() for p in parts if p.strip()]


def split_paragraph(text, max_words):
    """Whole sentences grouped into pieces of at most max_words words (0 keeps the paragraph whole)."""
    if not max_words:
        return [text]
    pieces, current = [], []
    for sentence in sentences(text):
        if current and len(" ".join(current + [sentence]).split()) > max_words:
            pieces.append(" ".join(current))
            current = []
        current.append(sentence)
    if current:
        pieces.append(" ".join(current))
    return pieces


def load_chunks(path=GUIDES_PATH, max_words=None):
    """
    Parse the guides into hybrid chunks.

    `## City, Country` starts a document, `### Topic` a section, and each blank-line separated paragraph is cut into
    chunks of whole sentences: {"id", "city", "topic", "text", "body"}. `text` (what gets embedded) carries the
    "City, Country / Topic:" header; `body` is the chunk's own sentences, for display. Ids look like "kyoto-1.2"
    (second chunk of the first Kyoto paragraph).
    """
    max_words = settings.AI_ASK_CHUNK_WORDS if max_words is None else max_words
    chunks, city, topic, counter = [], None, None, defaultdict(int)
    for block in re.split(r"\n\s*\n", Path(path).read_text(encoding="utf-8")):
        block = " ".join(block.split())
        if block.startswith("## "):
            city = block[3:]
            continue
        if block.startswith("### "):
            topic = block[4:]
            continue
        if not block or block.startswith("# ") or city is None:
            continue
        key = re.sub(r"[^a-z]+", "-", city.split(",")[0].lower()).strip("-")
        counter[key] += 1
        for part, piece in enumerate(split_paragraph(block, max_words), 1):
            chunks.append({
                "id": f"{key}-{counter[key]}.{part}", "city": city, "topic": topic,
                "text": f"{city} / {topic}: {piece}", "body": piece,
            })
    return chunks


def guide_cities():
    """The 'City, Country' names that have a guide."""
    return sorted({c["city"] for c in load_chunks(max_words=0)})


def _pick_device():
    import torch
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _load_embedder(name):
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(name, device=_pick_device())


def _encode(embedder, texts):
    vectors = embedder.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(vectors, dtype=np.float32)


def _get_index():
    """Load the embedding model and embed every chunk, once per process (and again only if the settings change)."""
    if not settings.AI_LOCAL_ENABLED:
        raise SearchUnavailable("The travel guide search is switched off on this server.")
    key = (settings.AI_EMBEDDING_MODEL, settings.AI_ASK_CHUNK_WORDS)
    with _lock:
        if _index.get("key") != key:
            try:
                embedder = _index["embedder"] if _index.get("model") == key[0] else _load_embedder(key[0])
                chunks = load_chunks()
                matrix = _encode(embedder, [c["text"] for c in chunks])
            except Exception as exc:  # missing package, no network on first run, out of memory...
                raise SearchUnavailable(f"The travel guide search could not be loaded: {exc}") from exc
            prefix = next((p for name, p in QUERY_PREFIXES.items() if name in key[0].lower()), "")
            _index.clear()
            _index.update(key=key, model=key[0], embedder=embedder, chunks=chunks, matrix=matrix, prefix=prefix)
    return _index


def search(query, cities=None, k=None, min_score=None):
    """
    The top-k guide chunks for `query`, best first, each with a cosine `score`.

    `cities` limits the search to those 'City, Country' documents (a trip's own stops). Chunks scoring below
    `min_score` are dropped, so an off-topic question returns an empty list instead of the least-bad paragraphs.
    """
    k = k or settings.AI_ASK_TOP_K
    min_score = settings.AI_ASK_MIN_SCORE if min_score is None else min_score
    index = _get_index()
    allowed = [i for i, c in enumerate(index["chunks"]) if cities is None or c["city"] in cities]
    if not allowed:
        return []
    query_vector = _encode(index["embedder"], [index["prefix"] + query])[0]
    scores = index["matrix"][allowed] @ query_vector
    order = np.argsort(-scores)[:k]
    return [
        dict(index["chunks"][allowed[i]], score=round(float(scores[i]), 3))
        for i in order if scores[i] >= min_score
    ]
