"""Code checks on a written chapter (phase 6). They find what a machine can find; the reading rubric
(docs/prompts/06-reading-rubric.md) is what judges the chapter. A reader grades first and looks at the flags second, so the flags
never shape the reading. A flag is a pointer ("look here"), never a verdict. Plain text in, a list of `Flag` out. No model.

The checks are heuristics for English. Each is small and says what it saw, so a false alarm is easy to recognise."""
import re
from collections import Counter
from dataclasses import dataclass

STOP = set("a an the and or but of to in on at by for with from as is are was were be been it its that this these those he she they "
           "them his her their i me my we our you your not no so if then than there here had has have do did does will would "
           "could should can may might must into out up down over under again once only just very more most some any all each "
           "who whom what which when where why how about after before while until because through during".split())

PAST = set("was were had did said went came saw took made knew got thought felt told asked looked turned found stood put kept "
           "began left held heard let ran sat gave".split())
PRESENT = set("is are am has does says goes comes sees takes makes knows gets thinks feels tells asks looks turns finds stands "
              "puts keeps begins leaves holds hears lets runs sits gives".split())
FORMAT_LEAKS = [r"^\s*#{1,6}\s", r"^\s*[-*•]\s", r"^\s*\d+[.)]\s", r"\*\*", r"<\s*/?\s*(start|end)_of_turn", r"^\s*(chapter|section)\s+\d+\b",
                r"\b(here is|here's) (the|a|your) (next |first |final )?(section|chapter|part|continuation)", r"\bas an ai\b",
                r"^\s*(goal|choice|turn|block|ends on|beat)\s*:", r"\[(end|continue|section)[^\]]*\]"]


@dataclass(frozen=True)
class Flag:
    id: str
    detail: str

    def __str__(self):
        return f"{self.id}: {self.detail}"


def words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9À-ÿ']+", text)


def outside_quotes(text: str) -> str:
    """The narration: the text with whatever is inside double quotes (straight or curly) taken out."""
    return re.sub(r"\"[^\"]*\"|“[^”]*”", " ", text)


def content_words(text: str) -> set[str]:
    return {w.lower() for w in words(text) if w.lower() not in STOP and len(w) > 2}


def sentences(text: str) -> list[str]:
    return [x.strip() for x in re.split(r"(?<=[.!?])[\"”')]*\s+", text) if x.strip()]


def paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def overlap(needle: str, hay: set[str]) -> float:
    want = content_words(needle)
    return len(want & hay) / len(want) if want else 0.0


def whole_sentences(text: str) -> str:
    """A section that stopped at the token limit ends mid-word. Cuts it back to its last whole sentence; a text that already ends on
    a full stop, a closing quote or the like is returned as it is, and so is one with no sentence end in its second half."""
    body = text.rstrip()
    if not body or re.search(r"[.!?…—][\"”'’)\]]*$", body):
        return body
    ends = [m.end() for m in re.finditer(r"[.!?…][\"”'’)\]]*(?=\s)", body)]
    return body[:ends[-1]].rstrip() if ends and ends[-1] >= len(body) * 0.5 else body


# ---- The checks -----------------------------------------------------------------------------------------------------

def check_length(text, target=3000):
    n = len(words(text))
    if n < 0.8 * target:
        return [Flag("length-short", f"{n} words, under 80% of {target}")]
    if n > 1.3 * target:
        return [Flag("length-long", f"{n} words, over 130% of {target}")]
    return []


def check_person_and_tense(text, style, protagonist=""):
    flags = []
    narration = outside_quotes(text)
    toks = [w.lower() for w in words(narration)]
    per1000 = 1000 / max(len(toks), 1)
    first = sum(t in ("i", "my", "me", "myself", "i'd", "i'm", "i'll", "i've") for t in toks) * per1000
    second = sum(t in ("you", "your", "you'd", "you're") for t in toks) * per1000
    person = style.get("person", "third")
    if person == "first" and first < 8:
        flags.append(Flag("person-first", f"first person asked, \"I/my/me\" only {first:.0f} per 1,000 narration words"))
    if person == "third" and first > 4:
        flags.append(Flag("person-third", f"third person asked, \"I/my/me\" {first:.0f} per 1,000 narration words"))
    if person == "third" and second > 6:
        flags.append(Flag("person-third", f"third person asked, \"you\" {second:.0f} per 1,000 narration words"))
    if person == "second" and second < 8:
        flags.append(Flag("person-second", f"second person asked, \"you\" only {second:.0f} per 1,000 narration words"))
    past, present = sum(t in PAST for t in toks), sum(t in PRESENT for t in toks)
    tense = style.get("tense", "past")
    if tense == "past" and present * 2 > past and present > 15:
        flags.append(Flag("tense", f"past tense asked, but present-tense words {present} against past {past}"))
    if tense == "present" and past > present and past > 15:
        flags.append(Flag("tense", f"present tense asked, but past-tense words {past} against present {present}"))
    return flags


def check_repetition(text):
    flags = []
    toks = [w.lower() for w in words(outside_quotes(text))]
    grams = Counter(tuple(toks[i:i + 5]) for i in range(len(toks) - 4))
    again = [(" ".join(g), n) for g, n in grams.items() if n >= 3 and len({w for w in g if w not in STOP}) >= 2]
    if again:
        flags.append(Flag("repeat-phrase", "; ".join(f"\"{g}\" x{n}" for g, n in sorted(again, key=lambda x: -x[1])[:3])))
    paras = paragraphs(text)
    opener = Counter(p.split()[0].lower() for p in paras if p.split())
    if len(paras) >= 8 and opener and opener.most_common(1)[0][1] / len(paras) > 0.35:
        w, n = opener.most_common(1)[0]
        flags.append(Flag("repeat-opener", f"{n} of {len(paras)} paragraphs open with \"{w}\""))
    sents = sentences(outside_quotes(text))
    run = best = 1
    for a, b in zip(sents, sents[1:]):
        run = run + 1 if a.split()[:1] == b.split()[:1] else 1
        best = max(best, run)
    if best >= 5:
        flags.append(Flag("repeat-sentence-start", f"{best} sentences in a row start with the same word"))
    paras_seen, same = set(), 0
    for para in paragraphs(text):
        key = " ".join(para.lower().split())
        if len(key) >= 60 and key in paras_seen:
            same += 1
        paras_seen.add(key)
    if same:
        flags.append(Flag("repeat-paragraph", f"{same} whole paragraph(s) written twice"))
    seen, dupes = set(), 0
    for sent in sentences(text):
        key = sent.lower()
        if len(key.split()) >= 6 and key in seen:
            dupes += 1
        seen.add(key)
    if dupes:
        flags.append(Flag("repeat-sentence", f"{dupes} whole sentence(s) written twice"))
    return flags


def check_format(text):
    hits = []
    for pat in FORMAT_LEAKS:
        for line in text.splitlines():
            if re.search(pat, line, re.I):
                hits.append(line.strip()[:60])
                break
    flags = [Flag("format-leak", "; ".join(f"\"{h}\"" for h in hits))] if hits else []
    if len(paragraphs(text)) < 8 and len(words(text)) > 1500:
        flags.append(Flag("format-paragraphs", f"only {len(paragraphs(text))} paragraphs in {len(words(text))} words"))
    return flags


def check_echo(text, beat):
    """The beat's own sentences copied into the story: the checklist showing through."""
    flags = []
    low = " ".join(words(text)).lower()
    for key in ("collision_goal", "ends_on"):
        value = " ".join(words(str(beat.get(key) or ""))).lower()
        if len(value.split()) >= 6 and value in low:
            flags.append(Flag("beat-echo", f"{key} appears word for word"))
    return flags


def check_secrets(text, request):
    """A hidden truth the beat does not name, showing up in a sentence. Heuristic: most of the truth's content words in one sentence."""
    beat = request.get("beat") or {}
    named = (beat.get("reveal_rule") or "").strip().lower()
    truths = [(r.get("statement", ""), r.get("truth", "")) for r in request.get("available_reveals") or [] if r.get("truth")]
    truths += [(r.get("statement", ""), r.get("truth", "")) for r in (request.get("world") or {}).get("rules", []) if r.get("truth")]
    flags, done = [], set()
    for statement, truth in truths:
        if truth in done or statement.strip().lower() == named:
            continue
        done.add(truth)
        for sent in sentences(text):
            if overlap(truth, content_words(sent)) >= 0.7:
                flags.append(Flag("secret-early", f"a sentence says what \"{statement[:50]}\" hides: \"{sent[:80]}\""))
                break
    return flags


def check_cast(text, request):
    beat = request.get("beat") or {}
    on = set(beat.get("cast") or [])
    flags = []
    low = text
    for name in sorted(on):
        if not re.search(rf"\b{re.escape(name)}\b", low):
            flags.append(Flag("cast-missing", f"{name} is on stage but never named"))
    for person in request.get("cast") or []:
        name = person.get("name", "")
        if not name or name in on or name == (request.get("setup") or {}).get("protagonist"):
            continue
        n = len(re.findall(r"\b" + re.escape(name) + r"\b", low))
        if n > 3:
            flags.append(Flag("cast-offstage", f"{name} is offstage but named {n} times"))
    return flags


def check_ending(text, beat):
    flags = []
    body = text.rstrip()
    if body and body[-1] not in ".!?\"”')…—":
        flags.append(Flag("ending-cut", f"the text stops without closing punctuation: \"...{body[-40:]}\""))
    ends_on = beat.get("ends_on") or ""
    if ends_on:
        tail = content_words(" ".join(body.split()[-150:]))
        if overlap(ends_on, tail) < 0.4:
            flags.append(Flag("ending-target", f"the last 150 words hold {overlap(ends_on, tail):.0%} of the words of \"{ends_on[:60]}\""))
    return flags


def check_dialogue(text):
    total = len(words(text))
    spoken = len(words(" ".join(re.findall(r"\"[^\"]*\"|“[^”]*”", text))))
    share = spoken / max(total, 1)
    straight, curly = text.count('"'), text.count("“") + text.count("”")
    flags = []
    if share < 0.05:
        flags.append(Flag("dialogue-none", f"{share:.0%} of the words are spoken"))
    if share > 0.7:
        flags.append(Flag("dialogue-only", f"{share:.0%} of the words are spoken"))
    if straight > 4 and curly > 4:
        flags.append(Flag("quotes-mixed", f"{straight} straight and {curly} curly quote marks"))
    return flags


def check_language(text, language="en"):
    if language == "en" and re.search(r"[぀-ヿ㐀-鿿가-힯Ѐ-ӿ]", text):
        return [Flag("language-drift", "characters from another script in an English chapter")]
    return []


def run_checks(text: str, request: dict, target_words: int = 3000) -> list[Flag]:
    beat = request.get("beat") or {}
    style = request.get("style") or {}
    protagonist = (request.get("setup") or {}).get("protagonist", "")
    flags = [*check_length(text, target_words), *check_person_and_tense(text, style, protagonist), *check_repetition(text),
             *check_format(text), *check_echo(text, beat), *check_secrets(text, request), *check_cast(text, request),
             *check_ending(text, beat), *check_dialogue(text), *check_language(text, request.get("language", "en"))]
    return flags
