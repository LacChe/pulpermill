# Probe catalog

A probe is a very small input aimed at one field or boundary on one card. The fill may invent anything else the card needs; only the target is scored. Most probes come as a **tempting** input and a clean **control**. The control catches a prompt change that "fixes" the problem by deleting valid content.

Scoring uses the three buckets from the plan: right, wrong but flagged, wrong and silent. The cards are Style, Characters, World, Entanglements and Setup, as the schema has them now (schema version 3).

## How to read the table

- **Tier 1:** no rule or warning would flag a wrong fill, so a wrong result can only be silent. These are the probes where the tests are the safety net. A probe is Tier 1 when every wrong result it invites passes every rule; if a rule would catch some wrong results but not the likely one, it is still Tier 1 and the row says so.
- **Tier 2:** a rule or warning is expected to flag a wrong fill. Score whether the fill got it right, and whether the flag fired when it didn't.
- **★** marks the failure you named: an owner written into an object (W1, E1).
- **Needs:** probes marked "upstream" run from the fixed hand-written upstream cards, so a failure on this card is not blamed on an earlier one. Entanglements and Setup probes always need them.
- Probe ids are never reused. Retired and new probes are listed in `CHANGES.md`.

## Style

| ID | Target | Tempting input | Control | Right looks like | Expected flag | Tier |
| --- | --- | --- | --- | --- | --- | --- |
| S1 | lens | "a story about grief and betrayal" | "notices what people do with their hands" | A habit of attention, not a subject. A topic is turned into a way of looking, keeping the note's intent. | `lens_is_habit` (judge) | 2 |
| S2 | genre | "a heist where the crew gets double-crossed" | "heist caper, playful and tense" | A tradition or mood, no specific events. | `genre_not_plot` (judge) | 2 |
| S3 | all Style text | A note that names a character and a place ("Imre narrates, set on Tern Station") | The same voice described with no names | No story-specific name or event anywhere in Style. | None at fill time. Style is filled first, so no names exist yet for `style_agnostic` to match. | 1 |
| S4 | person, tense | Chapter excerpt (~150 words), first person past | Chapter excerpt, third person present (each is the other's control) | Person and tense match the excerpt. | None | 1 |

## Characters

| ID | Target | Tempting input | Control | Right looks like | Expected flag | Tier |
| --- | --- | --- | --- | --- | --- | --- |
| C1 | wants | Two variants. (a) "wants to pass Mr. Hale's exam and win back his sister's trust". (b) "wants to get promoted to lead diver". | "wants to succeed and to be trusted" | Wants are abstract. No named person and no concrete aim on the card. | Partial. `char_no_relationships` may catch the sister. Nothing catches an unnamed concrete aim (variant b). | 1 |
| C2 | sketch, history | "Dov's sister-in-law, a private eye who lost her husband to the docks" | "a private eye, dry and watchful, who distrusts anyone polite" | A trait of this person. No relationship and no other name. | `char_no_relationships` (judge), `char_other_names` (code, only if the name exists on a card) | 2 |
| C3 | sketch and the rest | One-liner: "grumpy lighthouse keeper" | A fuller note | Sketch says what the person is like, not just the role. Other fields are filled with substance faithful to the one-liner. | `sketch_describes_person` (judge) | 2 |
| C4 | fear, flaw, vulnerability, values | One idea repeated four ways: "afraid of failing; terrified of failure; vulnerable to criticism about failing; values success" | Four distinct ideas | Each of the four fields says something different. | None | 1 |
| C5 | values | "never lies, never abandons friends, would never steal" | "honesty, loyalty, earning what she has" | Each value is something protected, not a prohibition. | `values_positive` (judge) | 2 |
| C6 | behaviors | "when he's in a bar fight he punches the wall; when she gets the letter she burns it" | "when he feels cornered he gets sarcastic; when he's relaxed he whistles" | Inner or broad states, tendencies not single acts, one calm state. | `behavior_state_is_inner`, `behavior_is_tendency`, `behaviors_include_calm` (judge) | 2 |
| C7 | wants | A single want: "wants to be rich" | A note that already has two conflicting wants | At least two wants that cannot both be fully satisfied. The stated want is kept. | `wants_count` (code), `wants_conflict` (judge) | 2 |
| C8 | name, age, sex, appearance | A note that states all four, including specific details (a scar, a bell in one ear) | None (exact match) | Exactly as stated. | None | 1 |

## World

| ID | Target | Tempting input | Control | Right looks like | Expected flag | Tier |
| --- | --- | --- | --- | --- | --- | --- |
| W1 ★ | objects | "the Lattice, a drone owned by Teodora, kept in Dock 9" | "the Lattice, a salvage drone" | Description and significance name no owner and no location. The owner is left for Entanglements. | `object_unowned` (judge), `world_names_people` (code, if Teodora exists) | 2 |
| W2 | groups | "the Authority is planning to close Dock 9 next month" | "the Authority meters the air and taxes it" | What the group is and how daily life feels it. No present plan. | `power_no_current_goals` (judge) | 2 |
| W5 | history, era | "King Aldric's betrayal split the realm; a dark, oppressive age of decay" | "a civil war split the realm; steam engines at the docks, no electricity" | History is events and forces, no named individuals. Era is facts, not mood. | `history_no_people`, `era_is_fact_not_mood` (judge) | 2 |

## Entanglements (all run from the fixed upstream cards)

| ID | Target | Tempting input | Control | Right looks like | Expected flag | Tier |
| --- | --- | --- | --- | --- | --- | --- |
| E1 ★ | holdings (the second half of W1) | Note: "Teodora owns the Lattice", with the Lattice present and unowned in World | A note with no ownership | A holding links the Lattice to Teodora. No owner text is added to the World object. | None for a missing holding. `holding_pair_allowed` blocks only invalid pairs. | 1 |
| E2 | tie to a group World does not hold | "the Dockhands' Brotherhood is squeezing Walt" when World has no such group | The same note naming a group that does exist in World | Tempting: no tie ends at a group that is not in World, and no new group, place or object appears anywhere, including free text. Control: a tie from the Harbor Mutual to Walt. | None. `link_broken` only fires on a link that dangles, and the fill can only link to what the request listed. | 1 |
| E3 | ties: edge | "Pim admires Orla; they're mentor and student" | "Pim wants Orla to teach her the loafcast; Orla keeps finding reasons to say not yet" | The edge is what the "from" person wants the tie to give or do right now, not how they feel. The bond is the standing label. | `tie_edge_is_live` (judge) | 2 |
| E4 | ties: bond and edge apart | A note giving only a live aim ("Walt wants Ines to find where the dues go") | A note giving both | A bond (what the tie is) and an edge (Walt's driver in it), both present and saying different things. The bond is not the edge reworded, and the edge is not a second bond. | None. A bond that repeats or swallows the edge passes every rule. | 1 |
| E8 | tie direction | "Ines was hired by Walt to find out where the dues go, and he is desperate for an answer" | "Walt hired Ines to find out where the dues go, and he is desperate for an answer" | One tie from Walt to Ines: the bond says what it is (employer, hired investigator), the edge is Walt's driver. The edge belongs to the person at the "from" end. | None. A tie written the wrong way round is a valid tie with a plausible edge. | 1 |
| E9 | holding written as a tie | "Walt owns the Lantern Bar" | "Walt and Ines are old friends" | A holding of the Lantern Bar by Walt. No tie carries ownership as its bond (a bar is not an end of a tie). | None. A tie from Walt to a place cannot be stored, but a tie from Walt to a person or group with an "owner" bond passes every rule, and a missing holding is not flagged. | 1 |

## Setup (all run from the fixed upstream cards)

| ID | Target | Tempting input | Control | Right looks like | Expected flag | Tier |
| --- | --- | --- | --- | --- | --- | --- |
| U2 | normal, disruption | "life was dull and lonely; things are getting tense" | "he dives each dawn and drinks at the Spindle; the Authority posts a closing notice" | Normal is a concrete ordinary day (routines, people, places) and says what it gave Imre. Disruption is an event. | `normal_is_concrete`, `disruption_is_event` (judge) | 2 |
| U3 | ending kept out of the disruption | A note whose disruption carries the ending ("... and in the end Teodora is arrested and Imre is freed") | The same note without the ending | Setup holds no ending and no plan. The disruption is the event that has already happened. | None. A disruption that includes the ending is still an event, so `disruption_is_event` passes. | 1 |
| U5 | protagonist | A note naming someone who is not a character as the lead | A note naming an existing character | The protagonist is an existing character. No new character is invented. | `protagonist_link_broken` (block) | 2 |
| U6 | Setup restating the character card | "Open on who he is: stubborn, secretly afraid, wanting to be taken seriously" | "Open on his usual day, then the disruption: the Authority posts a closing notice" | Normal is a day in Imre's life drawn from World and his ties, not his fear, flaw and wants again. Disruption is an event. | None for a restatement that names a place or a routine. `normal_is_concrete` may catch only the vaguest versions. | 1 |
| U7 | stated chapter count | "Make it nine chapters" | "Make it six chapters" | `chapter_count` equals the number stated. | None. Any whole number is valid. | 1 |

## What the catalog shows

- Thirteen probes are Tier 1: S3, S4, C1, C4, C8, E1, E2, E4, E8, E9, U3, U6 and U7. For these a wrong fill reaches the user with no warning, so the tests are the only safety net. Start tuning there.
- An owner written into a World object (W1) is caught by `object_unowned`, but a missing holding is not (E1), so the two halves of the same mistake sit in different tiers.
- The four ties probes (E3, E4, E8, E9) each aim at a different way a tie can look fine and be wrong: an edge that is a feeling (flagged), a bond that swallows the edge, a tie that points the wrong way, and ownership written as a tie.
- A wrong concrete want (C1b) is the clearest rule gap: no warning covers a concrete aim that names no one. If the tests show the fill gets it wrong, a new warning rule is a possible fix, and that decision is yours.
- Rules in the schema never require a fill to keep a stated chapter count (U7), a protagonist's tie to appear (`protagonist_has_tie` is advice only), or a Setup to differ from the character card (U6).
