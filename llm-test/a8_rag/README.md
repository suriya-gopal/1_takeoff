# A8: Semantic relationships and retrieval

A retrieval-augmented generation (RAG) system over TakeOff's destination guides, tested with three embedding models
(small, medium, large) and three chunking strategies (fixed length, overlapping paragraphs, hybrid).

## Files

| File | What it is |
|---|---|
| `rag_system.ipynb` | Full pipeline and all experiments: knowledge base, chunking, embeddings, retrieval, generation, 9-configuration evaluation, data scaling, failure analysis, improvements, cost inputs |
| `rag_analysis.md` | Written analysis: evaluation tables, comparisons, failure analysis, improvement, system design |
| `data/destination_guides.md` | Knowledge base: 12 city guides, 40 paragraphs, 3,732 words |
| `data/extra_guides.md` | 19 extra paragraphs, used only for the larger-dataset scaling test |
| `results/` | Every result table as CSV (written by the notebook), plus `manual_review.csv` and `manual_review_round2.csv`: our verdict and reason for each generated answer, read back by the notebook |
| `requirements.txt` | Python packages |

## Setup

Python 3.10 or newer. About 6 GB of free memory and 5 GB of disk for model downloads.

```bash
# from this folder
conda activate venv-django          # or: python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
jupyter notebook rag_system.ipynb
```

Then choose **Kernel → Restart & Run All**. All paths are relative to this folder.

**Recommended on macOS:** download the generation model in a terminal before opening the notebook. Downloading
3.4 GB inside Jupyter can hit macOS's open-file limit and fail with `ZMQError: Too many open files`. Keep the
`allow_patterns` filter: without it the download also pulls every ONNX export in the repository (about 23 GB).

```bash
ulimit -n 4096
python -c "from huggingface_hub import snapshot_download; snapshot_download('HuggingFaceTB/SmolLM2-1.7B-Instruct', allow_patterns=['*.json', '*.txt', 'model.safetensors'])"
```

## Models

Downloaded automatically from Hugging Face on the first run and cached in `~/.cache/huggingface` (nothing is
stored in this folder; no token is needed).

| Role | Model | Size |
|---|---|---|
| Embedding, small | `sentence-transformers/all-MiniLM-L6-v2` | 384 dimensions, about 23M parameters |
| Embedding, medium | `sentence-transformers/all-mpnet-base-v2` | 768 dimensions, about 110M parameters |
| Embedding, large | `BAAI/bge-large-en-v1.5` | 1024 dimensions, about 335M parameters |
| Generation (all experiments) | `HuggingFaceTB/SmolLM2-1.7B-Instruct` | 1.7B parameters, from our A6/A7 benchmark |

The notebook uses an NVIDIA GPU or Apple GPU (MPS) when present, otherwise the CPU. On an Apple Silicon Mac the full
run takes roughly 15 to 30 minutes, almost all of it text generation (about 170 answers).

## Testing without downloads

`RAG_DRY_RUN=1 jupyter notebook rag_system.ipynb` swaps in tiny stand-in models so the code can be checked end to end
in seconds. Its numbers are meaningless; the submitted notebook is a normal run.
