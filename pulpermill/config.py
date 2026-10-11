"""Pulpermill settings: constants only.

HOW SETTINGS ARE READ (one rule, used everywhere): other modules never copy a setting with `from .config import X`. They read it
as `config.X` at the moment they use it, so a value changed after import still takes effect. The launcher changes settings with
`config.override(N_CTX=8192, ...)` before it loads the model and starts the server. The request models in server.py are built
from MAX_REQUEST_* when server.py is imported, so overrides of those must come before that import (the launcher does it in that order).
"""

# ---------------------------------------------------------------- model (shared by cards and chapters)
MODEL_REPO = "bartowski/mlabonne_gemma-3-27b-it-abliterated-GGUF"
MODEL_FILE = "mlabonne_gemma-3-27b-it-abliterated-Q4_K_M.gguf"
MODEL_DIR = "/kaggle/working/models"      # created when the model is loaded
N_CTX, N_BATCH, TENSOR_SPLIT = 16384, 256, [0.58, 0.42]
FLASH_ATTN = True         # faster attention and a smaller memory footprint; the loader retries without it if this build rejects it
N_THREADS = None          # CPU threads (only matters if some layers end up on the CPU); None = the library's default

# ---------------------------------------------------------------- CARD generation settings
TEMPS = {"style": 0.7, "characters": 0.4, "world": 0.4, "outline": 0.4, "beat": 0.5}   # lower = sticks closer to your notes
GEN_TEMP = 0.7            # fallback
MAX_TOKENS = {"style": 2000, "characters": 5500, "world": 4000, "outline": 3500, "beat": 2500}   # answer budget per stage
CHARS_PER_TOKEN = 3.5     # conservative, for the length counters in the page
INSTRUCTION_TOKENS = 1200 # rough size of each stage's instructions, for the page's limits
RETRY_RESERVE = 400       # room kept for a retry's error message
MIN_TOKENS = {"style": 1200, "characters": 4200, "world": 2500, "outline": 2500, "beat": 1500}   # smallest answer a card may get; sets the input limits
# MAX_CHARACTERS and MAX_CHAPTERS come from schema.py
GRAMMAR_MODE = "fallback"  # "fallback": write the card freely and use the JSON grammar only to retry a broken first attempt;
                          # "always": grammar on every attempt; "never": never. The grammar was measured at 4.5 tokens/s against about
                          # 10 without it (Gemma's huge vocabulary makes it slow), so it is kept for repairs.
MAX_RETRIES = 1           # regenerations after a first attempt that is not usable JSON for the card. Names that do not match are
                          # repaired in code (and reported), so this only fires on genuinely broken output; each retry costs a full generation

RETRY_ERROR_CHARS = 800      # how much of the error text a retry shows the model (a pydantic error can run to pages)
BAD_REPLY_LOG_CHARS = 1500   # when a reply cannot be used, this many characters of it go to the log (the start and the end, if it is longer)

# ---------------------------------------------------------------- CHAPTER generation settings (separate from the cards')
DEFAULT_TARGET_WORDS = 3000
CHAPTER_GEN = dict(
    temperature=1.0,        # mlabonne's recommended setting for this abliterated model (was 0.7 under stock Gemma 3)
    repeat_penalty=1.05,    # kept gentle: this tokenizer's space-in-token vocabulary makes prose prone to
                            # word-fusion under a stronger penalty
    frequency_penalty=0.05, # light touch for the same reason
    top_p=0.95,
    top_k=64,
)
CHAPTER_TOKENS_PER_WORD = 2.0   # generous ceiling above the target word count (token/word ratio varies with style)
CHAPTER_MIN_ROOM_PER_WORD = 1.4 # refuse to start if the prompt leaves less room than this many tokens per target word
SUMMARY_GEN = dict(max_tokens=260, temperature=0.3, repeat_penalty=1.3, frequency_penalty=0.2)
EXTRACT_GEN = dict(max_tokens=1800, temperature=0.2)
EXTRACT_RETRIES = 2

# ---------------------------------------------------------------- output language (data only: no code branches on it)
# `name` goes into the prompts; `unit` is what the target length is counted in. To add a language, add a line here and a
# translation table for the page.
# `gen` overrides CHAPTER_GEN for that language. Chinese writes a name or a term as one or two single-character tokens, so a
# repeat penalty works against the words a story has to repeat, and a hot sampler picks look-alike characters (a test
# produced 张期 and 缄慢 for 张强 and 缄默). Treat these values as a starting point and tune them by looking at a chapter.
LANGUAGES = {
    "en": {"name": "English", "unit": "words", "gen": {}, "cjk": False},   # cjk: written in Han characters (used to check card text)
    "zh": {"name": "Simplified Chinese (简体中文)", "unit": "Chinese characters (字)", "cjk": True,
           "gen": dict(temperature=0.8, top_p=0.9, top_k=40, repeat_penalty=1.0, frequency_penalty=0.0)},
}

# ---------------------------------------------------------------- server
PORT = 8000
NGROK_SECRET = "NGROK_AUTHTOKEN"   # label of the Kaggle secret that holds your ngrok token

# ---- what a request may contain. Generous on purpose: the real limit on text is the prompt-size check at generation time (it
# answers with a readable message). These only stop absurd or malformed input at the door, with a clear 422 and no job started.
MAX_REQUEST_TEXT = 200_000      # characters in any one text field
MAX_REQUEST_JSON = 1_000_000    # characters of JSON in one request's cards, or in one imported file (compact, Chinese counted as one each)
MAX_IMPORT_FILES = 100          # files in one import request


def override(**values):
    """Change settings from the launcher. An unknown name raises, so a typo cannot silently change nothing."""
    for name, value in values.items():
        if name.startswith("_") or not name.isupper() or name not in globals():
            raise KeyError(f"unknown setting: {name}")
        globals()[name] = value
