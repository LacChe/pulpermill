"""The real engine's own logic, run against a stand-in for llama-cpp-python's Llama. What only the real library can show
(speed, memory, whether Stop lands during prefill) is measured on Kaggle by tools/measure_engine.py."""
import json
import threading
import time
from dataclasses import replace

import pytest

from pulpermill.backend.config import ModelSettings, Sampling
from pulpermill.backend.engine import download
from pulpermill.backend.engine.base import CancelFlag
from pulpermill.backend.engine.gpu import check_memory
from pulpermill.backend.engine.llama import LlamaEngine, load
from pulpermill.backend.errors import Cancelled
from pulpermill.prompts import tokens as gemma


class FakeLlama:
    """Tokenizes one word to one id (plus <bos> if asked), records every call, streams canned pieces."""

    def __init__(self, **options):
        self.options = options
        self.tokenize_calls, self.evals, self.completions, self.resets = [], [], [], 0
        self.pieces = ["Hello", " there", ".", ""]
        self.finish = "stop"
        self.piece_delay = 0.0
        self.eval_delay = 0.0
        self.closed = False

    def tokenize(self, data, add_bos=True, special=False):
        self.tokenize_calls.append((data.decode(), add_bos, special))
        words = data.decode().split()
        return ([1] if add_bos else []) + list(range(100, 100 + len(words)))

    def reset(self):
        self.resets += 1

    def eval(self, ids):
        time.sleep(self.eval_delay)
        self.evals.append(list(ids))

    def create_completion(self, **kwargs):
        self.completions.append(kwargs)
        llama = self

        def stream():
            try:
                for i, piece in enumerate(llama.pieces):
                    time.sleep(llama.piece_delay)
                    last = i == len(llama.pieces) - 1
                    yield {"choices": [{"text": piece, "finish_reason": llama.finish if last else None}]}
            finally:
                llama.closed = True
        return stream()


SETTINGS = ModelSettings(n_ctx=2000, n_batch=4)


def engine(**kw):
    llm = FakeLlama()
    for k, v in kw.items():
        setattr(llm, k, v)
    return LlamaEngine(llm, SETTINGS, grammar_factory=lambda schema: ("GRAMMAR", schema)), llm


def test_the_prompt_is_wrapped_in_the_chat_template_and_tokenized_once_with_one_bos():
    e, llm = engine()
    e.generate("  Write a line.  ", 20)
    assert len(llm.tokenize_calls) == 1
    text, add_bos, special = llm.tokenize_calls[0]
    assert text == gemma.chat_text("Write a line.") and "<bos>" not in text      # the template carries no <bos> of its own
    assert add_bos is True and special is True                                      # the library adds the one <bos>
    assert llm.completions[0]["prompt"][0] == 1 and llm.completions[0]["prompt"].count(1) == 1


def test_count_tokens_is_what_generate_sends():
    e, llm = engine()
    assert e.count_tokens("one two three") == len(e._ids("one two three"))


def test_prefill_is_in_steps_of_n_batch_and_leaves_the_last_token_for_generation():
    e, llm = engine()
    prompt = " ".join(["w"] * 30)
    e.generate(prompt, 10)
    ids = llm.completions[0]["prompt"]
    flat = [t for step in llm.evals for t in step]
    assert flat == ids[:-1]
    assert all(len(step) <= SETTINGS.n_batch for step in llm.evals) and len(llm.evals) > 3
    assert llm.resets == 1


def test_it_streams_text_calls_on_token_and_records_the_run():
    e, llm = engine()
    seen = []
    text = e.generate("Hi.", 50, on_token=seen.append, params=Sampling(temperature=0.5, top_k=10, seed=7))
    assert text == "Hello there." and seen == ["Hello", " there", "."]
    run = e.last_run
    assert run["output_tokens"] == 3 and run["stop"] == "stop" and run["truncated"] is False
    assert run["prefill_s"] >= 0 and run["generation_s"] >= 0 and run["prompt_tokens"] > 0
    sent = llm.completions[0]
    assert sent["temperature"] == 0.5 and sent["top_k"] == 10 and sent["seed"] == 7 and sent["max_tokens"] == 50
    assert sent["stop"] == ["<end_of_turn>"] and sent["stream"] is True and sent["grammar"] is None
    assert run["sampling"]["temperature"] == 0.5


def test_a_reply_cut_at_max_tokens_is_marked_truncated():
    e, _ = engine(finish="length")
    e.generate("Hi.", 3)
    assert e.last_run["truncated"] is True


def test_a_constraint_becomes_a_grammar_built_from_the_schema():
    e, llm = engine()
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    e.generate("Hi.", 20, constraint=schema)
    kind, text = llm.completions[0]["grammar"]
    assert kind == "GRAMMAR" and json.loads(text) == schema and e.last_run["constrained"] is True


def test_a_prompt_and_reply_that_do_not_fit_the_context_are_refused_before_any_work():
    e, llm = engine()
    with pytest.raises(ValueError):
        e.generate(" ".join(["w"] * 2000), 100)
    assert llm.evals == [] and llm.completions == []


def test_stop_before_the_call_does_nothing():
    e, llm = engine()
    flag = CancelFlag()
    flag.set()
    with pytest.raises(Cancelled):
        e.generate("Hi.", 10, cancel=flag)
    assert llm.evals == [] and llm.completions == []


def test_stop_between_prefill_steps_ends_before_generation_starts():
    e, llm = engine(eval_delay=0.05)
    flag = CancelFlag()
    threading.Timer(0.12, flag.set).start()
    started = time.monotonic()
    with pytest.raises(Cancelled):
        e.generate(" ".join(["w"] * 200), 10, cancel=flag)
    assert time.monotonic() - started < 0.5          # one step, not the whole 50
    assert llm.completions == []


def test_stop_during_generation_closes_the_stream_and_raises_cancelled():
    e, llm = engine(piece_delay=0.05)
    llm.pieces = ["x"] * 100
    flag = CancelFlag()
    threading.Timer(0.12, flag.set).start()
    with pytest.raises(Cancelled):
        e.generate("Hi.", 100, cancel=flag)
    assert llm.closed is True and e.last_run["stop"] == "cancelled" and e.last_run["output_tokens"] < 10


def test_loading_retries_once_without_flash_attention():
    built = []

    class Picky(FakeLlama):
        def __init__(self, **options):
            built.append(options["flash_attn"])
            if options["flash_attn"]:
                raise RuntimeError("flash attention not supported")
            super().__init__(**options)

    loaded = load(replace(SETTINGS, min_free_vram_mb=0), "/m.gguf", llama_class=Picky)
    assert built == [True, False] and isinstance(loaded, LlamaEngine)


def test_loading_passes_the_settings_through():
    seen = {}

    class Spy(FakeLlama):
        def __init__(self, **options):
            seen.update(options)
            super().__init__(**options)

    load(replace(SETTINGS, tensor_split=(0.5, 0.5), min_free_vram_mb=0), "/m.gguf", llama_class=Spy)
    assert seen["model_path"] == "/m.gguf" and seen["n_ctx"] == 2000 and seen["tensor_split"] == [0.5, 0.5]
    assert seen["n_gpu_layers"] == -1 and seen["verbose"] is False


def test_memory_that_is_too_tight_gets_a_plain_sentence():
    assert check_memory([900, 5000], 400) is None
    assert check_memory(None, 400) is None
    sentence = check_memory([900, 120], 400)
    assert "GPU 1" in sentence and "120" in sentence and "GPU 0" not in sentence


# ---- the downloader ----

def test_a_model_already_on_disk_is_not_downloaded_again(tmp_path=None):
    import tempfile
    folder = tempfile.mkdtemp()
    settings = replace(SETTINGS, directory=folder, file="m.gguf")
    (__import__("pathlib").Path(folder) / "m.gguf").write_bytes(b"x" * 10)
    called = []
    path = download.ensure_model(settings, downloader=lambda *a: called.append(a), size=10)
    assert path.endswith("m.gguf") and not called


def test_a_failed_download_is_retried_with_a_doubling_wait_then_gives_up():
    import tempfile
    settings = replace(SETTINGS, directory=tempfile.mkdtemp(), download_tries=3, download_backoff_seconds=10)
    waits, tries = [], []

    def flaky(repo, file, directory):
        tries.append(1)
        if len(tries) < 3:
            raise ConnectionError("reset")
        return "/ok.gguf"

    assert download.ensure_model(settings, downloader=flaky, sleep=waits.append, size=1, free_bytes=lambda p: 10**12) == "/ok.gguf"
    assert waits == [10, 20]
    tries.clear()
    with pytest.raises(RuntimeError) as error:
        download.ensure_model(settings, downloader=lambda *a: (_ for _ in ()).throw(ConnectionError("x")), sleep=lambda s: None, size=1, free_bytes=lambda p: 10**12)
    assert "downloaded" in str(error.value)


def test_not_enough_disk_stops_before_downloading_when_the_size_is_known():
    import tempfile
    settings = replace(SETTINGS, directory=tempfile.mkdtemp())
    called = []
    with pytest.raises(RuntimeError) as error:
        download.ensure_model(settings, downloader=lambda *a: called.append(1), size=22 * 10**9, free_bytes=lambda p: 5 * 10**9)
    assert "disk" in str(error.value) and not called
