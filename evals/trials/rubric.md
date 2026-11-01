# Reading rubric for a chapter

Read the chapter first, as a reader. Then read the beat and the spotlight tie above it, then the flags. Score each line 0, 1 or 2. The sheet has one row per chapter.

**Scale:** 0 = no, 1 = partly, 2 = clearly yes. When unsure between two, give the lower one and write a note.

| Column | Question | 2 looks like | 0 looks like |
| --- | --- | --- | --- |
| `interesting` | Would you keep reading? | You want to know what happens next; at least one moment surprised you or felt specific to this story | Reads as a summary or a list of events; nothing you could not have guessed |
| `act1_start` | Is the starting point clear: who, where, when? | The first page puts you with the right people, in the beat's place, at its time | You cannot tell where or when you are, or who the scene is about |
| `act2_conflict` | Does the central conflict emerge? | Something in the protagonist's way appears and presses on them | Things happen but nothing resists the protagonist |
| `act3_turn` | Is there a climax or turning point? | A moment after which the situation is different and cannot go back | The chapter ends at the same pressure it began with |
| `act4_end` | Is there an end point? | The chapter lands somewhere you could name, so the next chapter can start from it | It stops mid-motion, or trails off |
| `spotlight_moved` | Did the spotlight tie move to a distinctly new state? | Compare the bond and edge above with the chapter's end: something between these two people is now different, and you could say what | The two people end exactly as they began |
| `aim_moved` | Did the protagonist's aim move to a distinctly new state? | The aim was met, lost, changed or reframed, and the chapter shows how | The aim is still untouched, or the chapter drops it |
| `minor_roles` | Do minor characters stay in roles, with no names? | Anyone outside the cast is "the clerk" or "a neighbour", in the background, and carries nothing the plot needs | A named newcomer appears, or a role carries a turn of the plot |
| `style_fit` | Does it read as the chosen style? | Person, tense, distance, humour and attitude all match the Style, and the lens shows | You would not guess the style from the text |
| `different` | Is it a different chapter from the last? | New setting, new problem, new ending; the opening is not an echo | Same opening, same beats, same last line. Leave blank for chapter 1 |

`total` is the sum of the ten scores (0 to 20; chapter 1 is out of 18 and its `different` is left blank).

## How to read
- Read two or three chapters of one run in order before you score the first: the question "different from the last" needs it.
- Score the chapter against the beat and the Style card in the file above it, not against what you would have written.
- The flags are leads, not scores. A flag that proves wrong is a note (`flags_right`), not a penalty. Never raise or lower a score because a machine check fired; score what you read.
- Do not read the machine columns before scoring a chapter. Open the sheet's flag columns last.
- `calls_failed` counts plan or generate calls that failed or needed a retry in the chapter (see `warnings` and `plan_retried` in `summary.csv`).
- Chinese chapter (`t4-hollow-court-zh`): have a native reader score `style_fit` and `minor_roles`. Mark `graded_by` with who read it.

## What the machine columns mean (`summary.csv`)
| Column | Meaning |
| --- | --- |
| `length`, `length_flag` | Words (characters of Han script for Chinese). Flagged under 250 or over 2500 words (400 / 5000 characters) |
| `person_found`, `person_flag` | The person the narration is mostly in (first or third), from pronouns outside dialogue; `drift` when it is not the Style's person. `unclear` below 10 pronouns |
| `tense_found`, `tense_flag` | The tense the narration is mostly in, from common verb forms; `drift` when it is not the Style's tense. English only. `unclear` below 20 verb forms |
| `opening_repeat` | The opening of this chapter matches the opening of an earlier one |
| `repeated_sentences` | Sentences (6 or more words) that also appear in an earlier chapter |
| `edge_in_shifts` | The spotlight tie's edge was changed or the tie removed by this chapter's shifts. `false` means the shifts did not record a move; the text may still show one |
| `changed_empty` | The events' "changed" line is empty |
| `shifts_proposed`, `shift_count`, `shift_flag` | Shifts the model sent and shifts kept; `over_cap` above the schema's cap |
| `unknown_count`, `unknown_names` | Capitalised words mid-sentence that are not on a card (a new name, or a word the heuristic misread). English only |
| `offstage_names` | Names of characters who exist but are not in this chapter's cast |
