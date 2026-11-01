# What changed in the kit for schema version 3 (P6b)

One row per probe and per case of the earlier kit, and one per new probe. Status is kept, revised, retired or new. Every default from the P6b spec was checked against the schema (`pulpermill/schema/*.py` and `text/en/*.yaml`) and held. This is the one file where retired ideas are named.

What the schema no longer has: rule status (Common, Hidden, Myth) and rule truth, knowledge, pressures, Setup's goal and stakes. Ties now have a `bond` (what the tie is) and an `edge` (the "from" person's driver). A tie may start or end at a character or a group (`world.powers`). Holdings link a thing or place to a character, group or place.

## Probes

| ID | Status | Reason |
| --- | --- | --- |
| S1 | kept | Lens as a habit of attention: `lens_is_habit` still exists, input unchanged |
| S2 | kept | Genre as a tradition: `genre_not_plot` still exists, input unchanged |
| S3 | kept | Style text must hold no story names; nothing flags it at fill time, still Tier 1 |
| S4 | kept | Person and tense from the excerpt; no rule covers it, still Tier 1 |
| C1 | kept | Abstract wants; no rule covers an unnamed concrete aim (variant b), still Tier 1 |
| C2 | kept | A relationship inside a sketch; `char_no_relationships` still exists |
| C3 | kept | A role-only sketch; `sketch_describes_person` still exists |
| C4 | kept | Fear, flaw, vulnerability and values stay four separate fields; no rule covers repetition |
| C5 | kept | Values phrased positively; `values_positive` still exists |
| C6 | kept | Behaviors; the three behavior rules still exist |
| C7 | kept | A single want; `wants_count` and `wants_conflict` still exist |
| C8 | kept | Stated name, age, sex and appearance must come through exactly; no rule covers it |
| W1 | revised | Owner inside an object: the input stands; the owner now lives only in a holding, and the catalog says what "right" is under the current World and Entanglements |
| W2 | kept | A group's present plan stays out of World; `power_no_current_goals` still exists |
| W3 | retired | Rules have no status any more (a rule is a statement, a cost and a when-broken) |
| W4 | retired | Rules have no truth any more |
| W5 | kept | History without people, era as fact; both rules still exist |
| E1 | revised | A holding of an unowned object; the holding stays, the wording now speaks only of holdings. Still Tier 1: a missing holding is not flagged |
| E2 | revised | Was an invented agent in a pressure; now a tie to a group World does not hold. A tie can only end at an existing person or group, so the error is an invented group in free text or a dropped tie, which nothing flags. Still Tier 1 |
| E3 | revised | Edge is the "from" person's driver; "admires" is a feeling. `tie_edge_is_live` can flag it, so Tier 2 |
| E4 | revised | `bond` is what the tie is, `edge` is the driver; a bond that repeats or swallows the edge passes every rule. Stays important, Tier 1 |
| E5 | retired | Pressures are gone |
| E6 | retired | Knowledge is gone |
| E7 | retired | Knowledge is gone (and so is the Myth rule it used) |
| U1 | retired | Setup has no goal any more |
| U2 | revised | Normal and disruption: the input stands; "right" now also says what the normal gave the protagonist (`normal_is_concrete`) |
| U3 | revised | The ending now stays out of `disruption`, not the goal; a disruption with an ending in it is still an event, so nothing flags it. Tier 1 |
| U4 | retired | Setup has no stakes any more |
| U5 | revised | Protagonist: the tempting and control inputs lose their goal sentences; the check is unchanged (`protagonist_link_broken`) |
| E8 | new | A tie that points the wrong way: the edge ends up describing the "to" person. Valid tie, plausible edge, no rule |
| E9 | new | Ownership written as a tie instead of a holding. Valid either way, no rule flags a missing holding |
| U6 | new | A Setup that restates the character card (fear, flaw, wants) instead of a day and an event. A restatement that names a place or routine passes `normal_is_concrete` |
| U7 | new | A stated chapter count must be kept. `chapter_count` is any whole number, so nothing flags a changed one |

Six probes were thought of and not kept, because a wrong result would be flagged:

| Idea | Why not |
| --- | --- |
| An edge written as a plain feeling | `tie_edge_is_live` is the rule for it; E3 already covers it |
| A protagonist with no tie | `protagonist_has_tie` fires; the schema says a protagonist with no tie is allowed, so a fill that picks one is right with a warning, not silent |
| A tie to a group World does not hold | Is E2 |
| Holding of a thing by a holder of the wrong type | `holding_pair_allowed` blocks it |
| A tie from a character to itself | `tie_not_self` blocks it |
| Setup naming a protagonist who is not a character | Is U5 |

## Cases

All twelve cases stay (no case is retired). A case keeps its genre, characters, input mode and difficulty.

| ID | Status | Reason |
| --- | --- | --- |
| case-1 | kept | Chapter only; nothing in it is a removed field. The plan's built-in list no longer names a secret or a goal |
| case-2 | kept | Chapter only; nothing removed |
| case-3 | revised | The Setup note lost its goal and stakes; the Entanglements note lost Pim's suspicion; the oven rule is now a plain rule with a cost, with no hidden truth about pearwood |
| case-4 | revised | Setup lost goal and stakes (the disruption stays a condition on purpose); the World rule lost its hidden reason; Entanglements lost who-knows-what; the character notes keep their blur (relationships, owner, concrete aims) |
| case-5 | revised | The Setup note lost its goal and stakes; the chapter is untouched |
| case-6 | revised | The Knowledge and Pressures lines are gone; the six "secrets" are now six rules (still over the cap of 5); Setup lost goal and stakes; still seven characters and many ties |
| case-7 | kept | Chapter only; Style focus |
| case-8 | kept | One-liners; nothing removed |
| case-9 | revised | The World rule lost "everyone knows"; the Chinese text is otherwise untouched (still needs a native reader) |
| case-10 | revised | The two rules no longer say who knows; Setup lost goal and stakes; Entanglements lost the well-keepers' fear of being found out; still fragmentary and typo-ridden, "6 chaps" stays |
| case-11 | kept | Chapter only |
| case-12 | kept | Chapter only; its three rules are now simply rules |

## Other changes

- `make_fixtures.py`: the `UPSTREAM` table has the new probes and no retired ones.
- Upstream sets A, B and C needed no new card: A has the ties and the holding the Setup probes use, B has the Lantern Bar for E9 and no Brotherhood for E2, C has the three characters and the Council for E3. Only the README changed.
- The scoring sheets have 159 probe rows (53 fixtures) and 36 case rows.
