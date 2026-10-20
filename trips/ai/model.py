"""
The on-device language model.

The model and tokenizer load once, the first time a draft is requested, and stay in memory. Weights
come from the Hugging Face Hub and are cached on disk by `transformers`. Requests share one model, so
generation runs one at a time behind a lock.
"""

import threading

from django.conf import settings

GENERATION_SETTINGS = dict(do_sample=False, repetition_penalty=1.1)  # steady, repeatable output
RETRY_SAMPLING = dict(do_sample=True, temperature=0.7, top_p=0.9)    # used when a retry needs variety

_lock = threading.Lock()
_loaded = {}


class ModelUnavailable(Exception):
    """The on-device model is switched off or could not be loaded."""


def _pick_device(torch):
    """NVIDIA GPU if present, then Apple GPU, then CPU."""
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _load():
    """Load tokenizer and model once and keep them for later requests."""
    if not _loaded:
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            name = settings.AI_LOCAL_MODEL
            device = _pick_device(torch)
            dtype = torch.float16 if device != "cpu" else torch.bfloat16  # half size in memory
            tokenizer = AutoTokenizer.from_pretrained(name)
            model = AutoModelForCausalLM.from_pretrained(name, dtype=dtype).to(device)
            model.eval()
        except Exception as exc:  # missing package, no network on first run, out of memory...
            raise ModelUnavailable(f"The drafting model could not be loaded: {exc}") from exc
        _loaded.update(tokenizer=tokenizer, model=model, device=device)
    return _loaded["tokenizer"], _loaded["model"], _loaded["device"]


def _encode(tokenizer, messages):
    """Apply the model's chat template; fold the system rules into the first user turn if unsupported."""
    try:
        return tokenizer.apply_chat_template(
            messages, add_generation_prompt=True, return_tensors="pt", return_dict=True
        )
    except Exception:
        merged = [dict(m) for m in messages if m["role"] != "system"]
        rules = "\n".join(m["content"] for m in messages if m["role"] == "system")
        merged[0]["content"] = rules + "\n\n" + merged[0]["content"]
        return tokenizer.apply_chat_template(
            merged, add_generation_prompt=True, return_tensors="pt", return_dict=True
        )


def generate_text(messages, max_new_tokens=400, sample=False):
    """Run the model on a list of chat messages and return the reply text."""
    if not settings.AI_LOCAL_ENABLED:
        raise ModelUnavailable("The drafting model is switched off on this server.")

    import torch

    with _lock:
        tokenizer, model, device = _load()
        inputs = _encode(tokenizer, messages).to(device)
        options = RETRY_SAMPLING if sample else GENERATION_SETTINGS
        with torch.no_grad():
            output = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                max_time=settings.AI_LOCAL_TIMEOUT_SECONDS,  # stop cleanly instead of hanging a request
                pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
                **options,
            )
    new_tokens = output[0][inputs["input_ids"].shape[1]:]
    return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
