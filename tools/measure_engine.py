"""Run on the real hardware (Kaggle) to collect what only the real model can tell: the numbers behind docs/backend-notes.md
(handoff section 8). Prints Markdown to paste into that file, and writes it to a file too.

    from tools.measure_engine import measure_all
    measure_all(engine)              # tokenizer parity, speed, cancellation, free VRAM at the current n_ctx
    from tools.measure_engine import memory_by_ctx
    memory_by_ctx(config.model, path, [8192, 12288, 16384])   # loads and unloads the model for each; slow, run once

Nothing here changes the server or the settings."""
import gc
import statistics
import threading
import time
from pathlib import Path

from pulpermill.backend.engine.base import CancelFlag
from pulpermill.backend.engine.gpu import free_vram_mb
from pulpermill.backend.errors import Cancelled
from pulpermill.prompts import tokens as gemma

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "docs/prompts/samples/prompts"
ODD_TEXTS = {
    "curly quotes": "She said, “I won’t go,” and he answered, ‘then stay.’",
    "em dash": "The door was open — and the room was empty — or so it seemed.",
    "a tab": "Name:\tSuvi\nPlace:\tThe Salt Coast",
    "a long run of newlines": "First.\n\n\n\n\n\n\n\n\n\nSecond.",
    "an emoji": "The gull \U0001F426 took the bread \U0001F35E and left.",
}
SCHEMA = {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"], "additionalProperties": False}


def _padded(words_target_tokens: int = 4000) -> str:
    base = (SAMPLES / "writer-1-open.txt").read_text()
    text = base
    while gemma.chat_tokens(text) < words_target_tokens:
        text += "\n\n" + base
    return text


def parity(engine) -> list[str]:
    rows = ["| text | tokens.py | engine | equal |", "| --- | --- | --- | --- |"]
    texts = {p.name: p.read_text() for p in sorted(SAMPLES.glob("*.txt"))[:3]} | ODD_TEXTS
    for name, text in texts.items():
        ours, theirs = gemma.chat_tokens(text), engine.count_tokens(text)
        rows.append(f"| {name} | {ours} | {theirs} | {'yes' if ours == theirs else '**NO**'} |")
    return rows


def _timed(engine, prompt, max_tokens, constraint=None, params=None):
    started = time.monotonic()
    text = engine.generate(prompt, max_tokens, constraint=constraint, params=params)
    run = dict(engine.last_run)
    run["total_s"] = time.monotonic() - started
    run["chars"] = len(text)
    return run


def speed(engine) -> list[str]:
    prompt = _padded(4000)
    rows = ["| run | prompt tokens | prefill s | prefill tok/s | output tokens | generation s | gen tok/s |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for label, constraint, prompt_text, n in [
        ("free text, 4,000-token prompt", None, prompt, 200),
        ("constrained JSON, 4,000-token prompt", SCHEMA, prompt + "\n\nAnswer as JSON with one key, summary.", 120),
    ]:
        r = _timed(engine, prompt_text, n, constraint)
        rows.append(f"| {label} | {r['prompt_tokens']} | {r['prefill_s']:.1f} | {r['prompt_tokens'] / max(r['prefill_s'], 1e-6):.0f} | "
                    f"{r['output_tokens']} | {r['generation_s']:.1f} | {r['output_tokens'] / max(r['generation_s'], 1e-6):.1f} |")
    section = _timed(engine, prompt, 900)
    rows.append(f"| one section-sized write (900 tokens) | {section['prompt_tokens']} | {section['prefill_s']:.1f} | | {section['output_tokens']} | "
                f"{section['generation_s']:.1f} | total {section['total_s']:.0f} s |")
    return rows


def cancellation(engine) -> list[str]:
    rows = ["| cancelled during | seconds until the engine was idle |", "| --- | --- |"]
    for label, prompt, delay in [("generation", "Write a long story about a lighthouse keeper.", 4.0), ("prefill", _padded(4000), 1.0)]:
        flag, result = CancelFlag(), {}

        def work():
            try:
                engine.generate(prompt, 600, cancel=flag)
                result["end"] = time.monotonic(); result["how"] = "finished"
            except Cancelled:
                result["end"] = time.monotonic(); result["how"] = "cancelled"

        thread = threading.Thread(target=work)
        thread.start()
        time.sleep(delay)
        asked = time.monotonic()
        flag.set()
        thread.join(timeout=120)
        rows.append(f"| {label} | {result['end'] - asked:.2f} ({result['how']}) |" if "end" in result else f"| {label} | did not stop in 120 s |")
    return rows


def vram(engine) -> list[str]:
    return [f"Free VRAM now, per GPU (MB): {free_vram_mb()}; n_ctx {engine.settings.n_ctx}; cache {engine.settings.kv_cache_type or 'f16'}."]


def measure_all(engine, out: str = "backend-notes-draft.md") -> str:
    parts = ["## Tokenizer parity", *parity(engine), "", "## Speed", *speed(engine), "", "## Cancellation", *cancellation(engine), "", "## Memory", *vram(engine)]
    text = "\n".join(parts)
    print(text)
    Path(out).write_text(text)
    return text


def memory_by_ctx(settings, model_path: str, sizes=(8192, 12288, 16384)) -> str:
    from dataclasses import replace
    from pulpermill.backend.engine.llama import load
    rows = ["| n_ctx | free VRAM per GPU after loading (MB) | loaded |", "| --- | --- | --- |"]
    for n in sizes:
        engine = None
        try:
            engine = load(replace(settings, n_ctx=n, min_free_vram_mb=0), model_path)
            probe = engine.generate("Say hello.", 8)
            rows.append(f"| {n} | {free_vram_mb()} | yes, and it answered ({len(probe)} chars) |")
        except Exception as error:
            rows.append(f"| {n} | {free_vram_mb()} | no: {str(error)[:80]} |")
        finally:
            del engine
            gc.collect()
    text = "\n".join(rows)
    print(text)
    return text
