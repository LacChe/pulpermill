# Fill input limits

A fill call (the "Fill with the model" button) takes the writer's note for the card and the example chapter. Both are limited, in tokens:

| | Tokens | English words | Chinese or Japanese characters |
| --- | --- | --- | --- |
| Example chapter (shared by every card) | 8,000 | about 6,200 | about 11,100 |
| Note (one per card) | 2,000 | about 1,500 | about 2,800 |

The numbers are `fill_note` and `fill_chapter` in `pulpermill/prompts/budgets.yaml`, and `FILL_LIMITS` in `web/logic.js`. A test keeps the two equal.

## Where the numbers come from

Before this there was no limit. The fill prompt got whatever room was left, and when it did not fit, the example chapter was cut from the middle
without telling the writer, which could drop facts they wanted used.

- **Input room.** `n_ctx` 24,576, minus the fill reply (`MAX_OUTPUT` 2,000), minus the margin (300), leaves 22,276 tokens for the whole prompt.
- **The fixed part.** The instructions, the field guidance and the related cards take 1.8k to 3.4k tokens on ordinary cards. With the related cards as full
  as the schema allows (8 people with every list at its maximum, a full world, 12 ties) the heaviest cards (Setup, Entanglements, World) reach about 10.7k.
  That leaves about 11.6k tokens for the writer's text.
- **The split.** 8,000 + 2,000 = 10,000 tokens, which leaves about 1.6k spare. The example chapter is more than twice the longest chapter in
  `evals/cardfill` (2,277 words) and about five chapters of what the writer produces (1,200 words each).

`tests/prompter/test_fill_limits.py` builds the heaviest prompt of every card with a note and a chapter exactly at their limits and checks that it fits
with no squeeze and that none of the writer's text was cut. If `n_ctx`, the margin, the reply size or the wording changes so that it no longer fits, that test fails.

## Why tokens, and how the page counts

What a character costs depends on the language (Gemma 3 tokenizer, measured):

| Language | Tokens per character |
| --- | --- |
| English | 0.21 |
| French, German, Spanish | 0.23 to 0.24 |
| Korean | 0.58 |
| Chinese, Japanese | 0.72 |

So 33,000 English characters and 11,000 Chinese characters cost about the same. The page has no tokenizer (33 MB), so it estimates a little high:
0.25 tokens for a Latin letter, 0.75 for a Chinese, Japanese or Korean character, 0.5 for any other script. It shows how much of the limit each text uses,
turns red when it is over, and disables the button while either text is over. Nothing is cut off while the writer types. The backend counts exactly
and answers `too_long` (413) for a note or chapter over its limit, before any inference; the writer's text is never cut to fit.

## Not measured

- **Speed.** How long an 8k-token prompt takes to read on the real GPU (`tools/measure_engine.py`). If it is too slow, lower `fill_chapter`.
- **Quality.** Whether Gemma 3 27B still extracts the facts reliably from a 6,000-word chapter. Try two or three before settling on 8,000.
- **Other scripts.** Cyrillic, Arabic, Thai and others are guessed at 0.5. A miss there only means the backend refuses what the page let through.
