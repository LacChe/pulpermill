# The writer's brief (phase 2)

*2026-10-25. Part A, phase 2. Craft guidance for every call, in plain English, written for you to read and edit. Nothing here is code. Phase 3 turns the agreed wording into text files and renderers; phase 4 builds the prompts from it.*

How to read it. Text in a `DRAFT` block is wording that would go to the model, so it is phrased positively (what to do) and addressed to the model. Everything else is explanation for you and may use plain "don't". Edit freely; whatever you change here is what phase 3 builds.

Contents: 1 the shared idea; 2 the chapter writer (the big one); 3 the planner; 4 offstage; 5 the Events extractor; 6 the Shifts extractor; 7 the card calls and end of story; 8 what I need from you.

## 1. The shared idea

A small model writes what it is shown. Show it a form and it fills in a form. So every prompt does three things:

1. **It says what good looks like**, in positive words, once and briefly.
2. **It hands over material as prose**, not as rows of labels (inventory, section 3).
3. **It ends on the task**, with a short reminder, because a 27B model weights the last lines most.

One more habit runs through the whole brief: **say less, say it concretely.** "Write vividly" does nothing. "Name one thing the protagonist can smell, touch or hear in the first paragraph" does.

## 2. The chapter writer (W)

### 2.1 What a chapter that reads well does

This is the core of the craft text (block 1 of the writer's prompt). It is short on purpose.

```
DRAFT: what a good chapter does
You are writing one chapter of a novel. A chapter is a scene, not a summary:
someone wants something, something stands in the way, they have to choose,
and by the end something is different.

Start inside the moment, at the place and time given, with the scene already
moving. Stay in the scene: show what people do, say and notice, in the order
it happens, and let the reader work out what it means.

People act from who they are. Let a want, a fear or a flaw show up as a
choice the person makes, a thing they say, or a thing they cannot bring
themselves to do. Each person on stage speaks in their own way.

Give the reader concrete things: a sound, an object in someone's hands, the
weight of a door, the exact words of a line. One precise detail does more than
three general ones.

Let the scene take the time it needs. When the moment matters, slow down and
play it out beat by beat; when it does not, move on in a sentence.

End where the scene ends, on a moment that leaves a question open.
```

Why each paragraph is there:

| Paragraph | The failure it prevents |
| --- | --- |
| Scene, not summary | The model narrates "she spent the afternoon searching" instead of playing the search. |
| Start inside the moment | Throat-clearing openings and recaps of the last chapter. |
| People act from who they are | Characters described by labels ("she was guarded") rather than shown choosing. |
| Concrete things | Flat, generic prose. |
| Take the time it needs | Rushing, and the "wrap up early" habit that makes chapters 600 to 900 words. |
| End where the scene ends | Resolving the scene early, or a tidy moral at the end. |

### 2.2 The hard rules

Person, tense, distance and language are fixed. They go first, as rules, and again in the reminder at the very end (block 12).

```
DRAFT: the rules block
Write in {language}.
{person rule: first or third, from Style}
{tense rule: past or present, from Style}
{distance rule: external, close or deep, from Style}
Keep person, tense and distance the same from the first line to the last,
including inside dialogue tags and in the middle of an action scene.
```

The person, tense and distance sentences already exist in `style.yaml` and are reused word for word. The last sentence is new and names the two places a model most often slips.

### 2.3 Each Style field as one concrete instruction

The existing expansions describe a quality ("sentences are short and clipped"). A model follows a *checkable behaviour* better. The plan: keep each existing expansion and add one concrete line after it. These additions are what phase 3 puts into `style.yaml`; the table is for you to edit.

| Field | Option | Concrete line added after the existing expansion |
| --- | --- | --- |
| distance | external | Report what can be seen and heard. Give no sentence a thought or feeling as if the reader were inside the head; let gesture and speech carry it. |
| distance | close | Give the protagonist's perceptions and plain thoughts, in the narrator's own words. |
| distance | deep | Let the protagonist's mind colour every sentence: what they notice, misread and remember is the description. |
| humor | none | Keep jokes out; let any lightness come from the characters' warmth, never from the narrator. |
| humor | dry | Put the humor in understatement and exact observation, never in a punchline. |
| humor | absurd | Let the absurd be met with a straight face, so the narration never winks. |
| humor | dark | Find the joke inside the grim thing, and let it die quickly. |
| pacing | lingering | Spend a full paragraph on at least two moments that matter, with sensory detail. |
| pacing | balanced | Slow down for the choice and the turn; cover everything else briskly. |
| pacing | brisk | Open on action, cut transitions, and end each paragraph on forward motion. |
| rhythm | terse | Keep most sentences under twelve words; fragments are welcome. |
| rhythm | varied | Match sentence length to the moment: short for action and shock, longer for thought. |
| rhythm | flowing | Link clauses into long sentences, and use a short one only for emphasis. |
| diction | plain | Prefer the ordinary word. Use strong verbs and exact nouns, and few adjectives. |
| diction | ornate | Choose rare, layered words and let a sentence carry two images. |
| formality | formal | Keep the narration grammatical and composed, and let characters speak in full sentences. |
| formality | casual | Use contractions, idiom and an easy voice, in the narration as well as in speech. |
| imagery | literal | Name things as they are, and use no comparisons. |
| imagery | occasional | Use at most one comparison a page, and put it at the moment that matters most. |
| imagery | lush | Use a comparison or a sensory detail in nearly every paragraph. |
| edge | clean | Keep the vocabulary gentle even when events are rough. |
| edge | coarse | Let characters swear and the narration be blunt and earthy where it fits them. |
| explicitness | implied | Cut away at the peak of an intense moment and let the aftermath tell it. |
| explicitness | shown | Stay in the room for intense moments and describe them plainly. |
| attitude | earnest, warm, wry, sardonic, clinical, melancholic, wondering | Express it in what the narrator chooses to notice and how it is phrased, not in statements about the narrator's feeling. |
| amount | sparse | Give lines of dialogue only where someone must speak; let narration carry the rest. |
| amount | abundant | Carry the scene mainly through conversation. |
| directness | direct | Let people say what they mean. |
| directness | subtext | Let people say something near the point and leave the point unsaid. |
| polish | naturalistic | Let people interrupt, trail off and talk over each other. |
| polish | stylised | Give dialogue shape: rhythm, wit, lines worth quoting. |
| voice_difference | distinct | Give each speaker a different sentence length, vocabulary and habit, so a line can be told apart without its tag. |
| voice_difference | uniform | Give the cast one shared way of speaking. |
| genre (lead-in) | any | Add: "Use the conventions and texture of this genre, and keep its pleasures." |
| lens (lead-in) | any | Add: "Let this decide what the narrator notices, in every scene." |
| the four notes | any | Passed through exactly as you wrote them, labelled with the group they belong to. |

Two points for your review:

- **Attitude has seven options, so one shared concrete line.** It tells the model to show attitude through selection and phrasing. If you would rather have one line per option, say so.
- **Numbers like "under twelve words" and "one comparison a page"** are my first guesses. They make the instruction checkable, which phase 6's reading rubric needs. We tune them against real output.

Test early (brief section 4.1, item 8): change one Style option, keep everything else, and check the prose visibly changes. This is the first thing to run in phase 7.

### 2.4 The scene engine as a scene

The beat has seven working parts: the goal, the block, two choices, the turn, harder or easier, and where it ends. Rendered as seven lines, they produce seven paragraphs in that order, which is the checklist story you do not want. So the scene is described as one situation, in the model's own terms.

Here is the same beat as the existing template would send it, and as the brief proposes.

```
AS THE TEMPLATE SENDS IT (avoid)
Chapter 4. We open at The Salt Coast docks, Tuesday just after the shop opens,
three days later. Present: Suvi, Aino. The protagonist is after the ledger, but
the only witness is the landlord, who will talk only if Suvi stays quiet about
the rent. They must choose between keeping the landlord's goodwill and learning
the truth about the ledger. By the end, Suvi learns the customer's name, but the
guild now knows she is asking. This chapter is harder. It ends on Suvi finding
her own initials in the ledger's last entry.
```

```
DRAFT: the same beat as a scene
The chapter opens at the Salt Coast docks, on Tuesday just after the shop
opens, three days after the last chapter. Suvi and Aino are there.

Suvi wants the ledger. The only person who saw it is the landlord, and he will
talk only if she stays quiet about the rent. So she has to decide what matters
more: keeping his goodwill, or learning the truth about the ledger. Either
choice costs her the other.

By the end of the chapter something has changed: Suvi has the customer's name,
and the guild now knows she is asking. This is a harder chapter than the one
before it, so let the pressure rise.

The chapter stops on this moment: Suvi finds her own initials in the ledger's
last entry. Stop there, with the question hanging.

This is the shape of the scene, not a script. Find your own way through it:
the people, the dialogue, the small events that carry Suvi from the opening to
that last moment are yours to invent.
```

What changed, and why:

| Change | Reason |
| --- | --- |
| The goal and block are one sentence with "but", then the choice follows from them | The model sees cause and effect, not four fields. |
| "Either choice costs her the other" is said once, plainly | The cost is what makes it a scene. |
| The turn is phrased as what is different, not as an event to stage | The model finds the event. |
| The ending is a *stopping moment* | It stops on the image, not on a summary. |
| A closing line says it is a shape, not a script | It protects against ticking each part off in order. |

The optional parts are added as plain sentences only when present, each in its own short paragraph:

```
DRAFT: optional parts of the scene
{if a reveal} In this chapter the reader learns that {rule statement}. The truth
is: {truth}. {Who learns it} comes to know it. Let it arrive through something
that happens in the scene, in one clear moment; no narrator explains it.
{if a plant} Set this up for later, in passing and without emphasis: {plant}.
{if a payoff} Pay off what was set up earlier: {plant}, set up in chapter {n}.
Let it land as a consequence of what the characters do here.
{if an offstage move} While the cast were elsewhere, {did}. It reaches {name} like
this: {reach}. Work it into the scene as something they run into, not as news.
{if a goal change} By the end of the chapter, {the goal has been achieved /
the goal has changed to X / the goal has been abandoned}.
{if a spotlight} The pressure in focus is: {pressure}. Keep it present in the
scene, felt in what people do.
{if the last chapter} This is the last chapter. Bring the story to its close
and settle what the story set in motion, then stop.
{if chapter 1} Before the story, ordinary life was: {normal}. What just broke
it: {disruption}. Open the story there.
```

### 2.5 People acting from who they are

Each person on stage is a paragraph portrait, then a few pointers on how to use it (the pointers are given once, not once per person):

```
DRAFT: how to use the portraits
These are the people on stage. Use their wants, fears, flaws and values to decide
what they choose, and show the choice. Let a flaw cost someone something. Let
competence show in how a person handles a task, not in being told. Let each
person's way of speaking, set out in the portrait, show in what they say.
Dispositions ("when X, they Y") are tendencies. Draw on the one the moment
calls for, and let the others rest.
```

The "where they stand now" block carries one extra line, because it must override the cards:

```
DRAFT: where they stand now
This is where each person stands at the start of the chapter. It is newer than
their portrait; where the two differ, follow this.
```

### 2.6 Secrets, knowledge and the page

The writer sees all of World, hidden truths included. The prompt keeps a hidden truth off the page by saying what each person knows:

```
DRAFT: knowledge
Some of what is true here is hidden from the people in it. What each person
knows, suspects or wrongly believes is listed below. Write each person from
their own knowledge. The narration says only what the point-of-view character
could know. A hidden truth enters the story only in the moment the scene
gives it.
```

Limits of this: a 27B model will sometimes still let a truth slip. That is exactly what X1 catches (it is offered every available reveal, not only the planned one), and the page records it.

### 2.7 Sections

The chapter is written in sections (decision D5). Each pass gets the same long start and a different end: what has been written so far, this section's job, and the reminder.

**Four sections of about 750 words** (the default):

| Section | Job |
| --- | --- |
| 1 | Open inside the scene. Show what the protagonist wants and meet the first sign of what stands in the way. |
| 2 | Press on the block. The protagonist tries, it costs, and it gets harder. Place the plant and the reveal here if the beat has them and they fit. |
| 3 | Force the choice. Play it out, with its cost. Pay off an open plant here if the beat has one. |
| 4 | Show what is different now, and stop on the ending moment. |

**Three sections of about 1,000 words** (if four feels too thin to tune): join 1 and 2, then 3, then 4.

```
DRAFT: a section's job (block 11)
This is section {k} of {n} of the chapter, about {words} words.
Its job: {the job from the table above, with the beat's own details filled in}.
The scene is not over after this section{ unless this is the last one}. Do not
sum up, conclude or look back; end the section mid-scene, on a line or an action,
so the next section can pick up from it.
```

For the last section the final sentence changes to: "This is the last section: bring the scene to its ending moment and stop there."

**The extra pass for a short chapter.** A continuation after the ending would damage the ending. So the check is made *before* the last section: if the words so far are well under the pace (below about 80% of the target at that point), one extra section is inserted before the closing one.

```
DRAFT: the extra section
The scene is not over. Stay in it and take it further: let the protagonist try
something else, let someone say what they have been holding back, or let the
obstacle show a new side. Write about {words} more words, then stop mid-scene.
```

If the chapter is still short after the closing section, it is returned as written and its length is logged. Shortness is a thing to tune, not a reason to throw a chapter away (decision D10).

**What each later section sees of the earlier text.** Only the last ~300 words, as plain text under "The chapter so far", plus the earlier-chapter material in the stable part. This keeps the prompt small. The risk is that the model repeats itself across sections (the same gesture or image appears twice). So the reminder carries one line: "Use fresh images and gestures; the ones in the passage above are already used."

### 2.8 Failure modes and what the prompt says instead

From brief section 2. Each failure gets a positive instruction in a place where a small model will read it.

| Failure | What the prompt says instead | Where |
| --- | --- | --- |
| Reads as a checklist | The scene is a situation; "a shape, not a script" | Block 9 |
| Summarises where a scene belongs | "Show what people do and say, in the order it happens"; "play it out beat by beat when the moment matters" | Blocks 1, 11 |
| Resolves the scene early | "The scene is not over after this section"; sections that end mid-scene | Blocks 11, 12 |
| Drifts in person, tense or distance | The three hard rules, repeated at the very end | Blocks 1, 12 |
| Repeats phrasing from the last chapter or the last section | "Use fresh images and gestures"; the opening is told to start somewhere new | Blocks 9, 12 |
| Characters described, not acting | "Show the choice"; portraits with a usage note | Block 4 |
| Secrets leak | "Write each person from their own knowledge"; the reveal is "one clear moment" | Blocks 5, 9 |
| Plant missing, payoff missing | The plant and payoff are named in the scene as their own short paragraphs | Block 9 |
| Flat voice | Each Style field is one checkable line | Block 2 |
| Meta text ("Here is the next section") | "Reply with the story text only" | Block 12 |

### 2.9 Draft reminder (block 12)

```
DRAFT: the reminder
Write in {language}, {person} person, {tense} tense, {distance} distance, the
whole way through. Stay in the scene and use fresh images and gestures.
{mid sections: Do not end the scene.} {last section: Stop on the ending moment.}
Reply with the story text only: no headings, notes or commentary.
```

## 3. The planner (P)

The planner's output (the beat) becomes the writer's brief, so a planner that writes a checklist beat causes a checklist chapter. Its craft guidance is mostly "make this a real scene."

### 3.1 The thinking pass

Kept short and in a fixed order, so it stays useful at 8 to 10 tokens a second. About 250 to 400 words in all.

```
DRAFT: the thinking steps
Think in these steps, briefly, in plain sentences.
1. Where the story stands: what the protagonist wants, what has changed, and
   what the chapter after this one needs to be possible.
2. Three directions for this chapter, one line each. Each should put the
   protagonist's want against something specific in this world.
3. Pick one and say why: what makes it fresh, and why it follows from the last
   chapter's turn rather than repeating it.
4. The choice: the two things the protagonist wants or values that cannot both
   be had, and what each one costs.
5. What is different at the end, and the last moment of the chapter.
6. Whether to plant something for later, pay off an open plant, or bring a
   hidden truth to light, and why now.
7. In one line, how the chapter should be told: where to slow down.
```

### 3.2 The beat pass

```
DRAFT: what each part of the beat should be
Fill the beat from your plan.
- The opening place and time put the scene already in motion.
- What the protagonist is after is a goal they can act on in scenes, such as
  getting, finding or stopping something. It should narrow one of their wants.
- What blocks it grows out of the last chapter's turn, or out of the pressure in
  focus.
- Each choice is something the protagonist wants or values. Picking one costs
  the other.
- The turn says what is different by the end, and it differs from the earlier
  turns.
- The ending is a moment that leaves a question open.
- Use only a shift from the allowed list, only a reveal from the available ones,
  and only open plants for a payoff.
```

These are the model-judged rules (`turn_is_a_change`, `choice_is_costly`, `ends_on_open_question`, `goal_now_*`) turned into instructions up front, so the model writes to them instead of being flagged afterwards. The planner is also told which words to avoid in the beat's fields in positive form: "Write each field as a plain sentence a writer could act on, with names of people and places."

### 3.3 Using the code's numbers

| What the code sends | How the planner is told to use it |
| --- | --- |
| Use counts for places and objects | "Lean towards places and things that have been used least, when they fit the scene." |
| The allowed shifts | "Pick from these." The pacing limit is a rule, not advice. |
| Open plants (at most two) | "A payoff resolves one of these. Choose it when the chapter gives it a natural home." |
| Available reveals | "Bring one to light only when the story is ready for it." |
| The current goal, or none | If none: "The goal has ended. Plan a chapter that winds the story down." |
| Chapter n of N | "Shape the chapter for where it falls: early chapters open doors, middle chapters tighten, late chapters pay off." |
| The tone fields (D1) | "The story is {genre}, seen through {lens}, with {humor} humor, a {attitude} narrator and {pacing} pacing. Plan scenes that suit it." |

### 3.4 On a retry

```
DRAFT: retry
Your first plan was refused for these reasons: {the rules' own words}.
Here is your first plan: {thinking} {beat}.
Keep what worked, and change only what the reasons say.
```

## 4. Offstage (O)

```
DRAFT: the offstage job
Between chapters the world moves without the protagonist. Choose one thing a
group or a place does that the main cast has not seen, and say how it reaches
the protagonist this chapter (a rumour, a notice, a changed price, a closed
road).
It is about a group or a place, never about the main cast. Pick something that
raises or reshapes the pressure, and let it come from what that group wants.
Write each part in one or two plain sentences.
```

Two things I need from the code for this to work: the spotlight (finding F2, confirmed), and that the move never repeats an earlier one (the last chapter's Events are included for that).

## 5. The Events extractor (X1)

This is the call whose output the next chapter reads. Its `happened` text is the story so far.

```
DRAFT: the Events job
Read the chapter and say what it shows happened. Count only what is on the page.
Write "happened" as short plain narration: one sentence per event, in the order
it happened, usually 4 to 8 sentences. An event is a moment that changes who
knows what, who holds what, or where people stand. Name people; say what they
did.
Write "changed" as one short sentence: what is different for the protagonist now.
For each of the following, answer only from the lists given, copying the wording
exactly, and only when it is clearly there in the text: the plant, the payoff,
the hidden truths that came to light, the dispositions that showed, the objects
that appeared. If something the beat planned is not in the text, leave it out.
Say yes to "goal changed" only if the text shows it.
```

Conservative by design: a plant or a reveal that did not land is simply left out, and the page keeps it available for next time. Left-out is cheap; a false "landed" costs a lost reveal.

## 6. The Shifts extractor (X2)

```
DRAFT: the Shifts job
Read the chapter and say who moved. Only people whose belief, fear, want, refusal
or decision changed in this chapter count, and only what changed, not who they
already were. Compare with where each person stood at the start.
For each person who moved, fill in only the boxes that changed:
  believes: a conviction they now hold, which the story could prove wrong
  fears: a fear that is new or different
  wants: an abstract desire that changed
  refuses: something they now will not do
  decided: what they decided; for the protagonist, say which of the two choices
           the chapter posed they took, or what they did instead
Then say what changed in the live entanglements: a tie's bond or edge, who holds
something, what someone now knows, suspects or wrongly believes, a pressure's
state or next move. Use the handle given for each item. Add a new knowledge line
only when someone has learned, suspected or been misled about something that has
no line yet. Say who actually learned the hidden truth, if one came out.
When nothing changed, give an empty list.
```

Guard in the prompt: `wants` is abstract and a concrete aim toward a person belongs on a tie's edge; `believes` about a fact already on a knowledge line belongs there instead. Both are one line each in the job text.

## 7. The card calls and the end of the story

Short, because they are medium and low priority and phase 4 will tune them.

- **Fill (F).** "Fill each field from the note and the chapter. Stay inside this card: invent freely within it, and link only to things that already exist. Name people, places and things by their names. Write a field only when the text gives you something for it; leave the rest empty." The scope table from `tests/cardfill/00-test-plan.md` goes in as the card's own "may invent / must not invent" line. A first working prompt only; the tests tune it.
- **Judge (J).** One rule at a time. "Answer for each item below whether it breaks the rule. Name only the items that do." The text files' own judge prompts supply the question; the backend removes the request for rewrites.
- **Style fit (S).** "Could this person carry a story told in this person, tense and distance? A very guarded protagonist in first person is hard; a very talkative one in a clinical, external voice is hard. Say yes or no; if no, say in one sentence which part to look at."
- **End of story (E).** "The story is over. Update each person and the world to how they are now, using the records of what happened and how people changed. Change only what the story changed. Keep fixed facts as they are. Return the changed fields only." One person at a time if the model is not coping with all of them.

## 8. What I need from you

1. **The attitude lines.** One shared concrete line for the seven attitudes, or seven separate ones?
2. **The numbers in 2.3** ("under twelve words", "one comparison a page"). Fine as first guesses?
3. **Four sections or three.** Four of about 750 words, as proposed?
4. **The scene paragraph in 2.4.** This is the most important wording in the document. Does the rewritten beat read like the brief you want the model to get?
5. **Anything missing from the failure list** in 2.8 that you have seen in the model's earlier output.

When these are settled, phase 3 turns the agreed wording into the text files and the renderers, with a length cap per field and a fixed order.
