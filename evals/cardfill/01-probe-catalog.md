# Probe catalog

A probe is a very small input aimed at one field or boundary on one card. The fill may invent anything else the card needs; only the target is scored. Most probes come as a **tempting** input and a clean **control**. The control catches a prompt change that "fixes" the problem by deleting valid content.

Scoring uses the three buckets from the plan: right, wrong but flagged, wrong and silent.

## How to read the table

- **Tier 1:** no rule or warning would flag a wrong fill, so a wrong result can only be silent. These are the probes where the tests are the safety net.
- **Tier 2:** a rule or warning is expected to flag a wrong fill. Score whether the fill got it right, and whether the flag fired when it didn't.
- **★** marks the failures you named: an owner inside an object, a theme written as a goal, a wrong Hidden/Myth choice.
- **Needs:** probes marked "upstream" run from the fixed hand-written upstream cards (step 4), so a failure on this card is not blamed on an earlier one. Entanglements and Setup probes always need them.
- The World status labels in the UI are Common, Hidden and Myth. They are stored as `common`, `uncommon` and `false_belief`.

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
| W3 ★ | rule status | Four single-rule notes, each a control for the others: (a) "the gates close at dusk, everyone knows"; (b) "only the harbor clerks know the tide gate can't be opened from outside"; (c) "people say the river is cursed, but the mill is really poisoning it"; (d) a widely repeated claim that is secretly false (the dawn bell is really a clockwork) | Each of the others | (a) Common. (b) Hidden. (c) and (d) Myth, each with its truth. | None for a wrong status. Only a Myth with no truth is blocked (`rule_false_needs_truth`). | 1 |
| W4 | truth | (a) A Hidden rule. (b) A Myth whose note gives a vague truth ("it isn't actually true") | A Myth with a clear truth | Truth appears only on Myth rules, and says what is actually true, in terms that differ from the statement. | Partial. Only a missing truth on a Myth is blocked. | 1 |
| W5 | history, era | "King Aldric's betrayal split the realm; a dark, oppressive age of decay" | "a civil war split the realm; steam engines at the docks, no electricity" | History is events and forces, no named individuals. Era is facts, not mood. | `history_no_people`, `era_is_fact_not_mood` (judge) | 2 |

## Entanglements (all run from the fixed upstream cards)

| ID | Target | Tempting input | Control | Right looks like | Expected flag | Tier |
| --- | --- | --- | --- | --- | --- | --- |
| E1 ★ | holdings (the second half of W1) | Note: "Teodora owns the Lattice", with the Lattice present and unowned in World | A note with no ownership | A holding links the Lattice to Teodora. No owner text is added to the World object. | None for a missing holding. `holding_pair_allowed` blocks only invalid pairs. | 1 |
| E2 | invented entity | "the harbor guild is squeezing Walt" when World has no guild | The same note naming a group that does exist in World | Tempting: no new group, place or object appears anywhere, including free text. Control: the group becomes a pressure's agent. | None. `link_broken` only fires on a dangling link. | 1 |
| E3 | ties: edge | "Pim admires Orla; they're mentor and student" | "Pim wants Orla to teach her the loafcast; Orla keeps finding reasons to say not yet" | Edge is what one side wants from or hides from the other right now. | `tie_edge_is_live` (judge) | 2 |
| E4 | ties: bond vs edge | A note giving only a live aim ("Walt wants Ines to find where the dues go") | A note giving both | A bond (standing relationship) and an edge (live aim), both present and different. | None for the bond | 1 |
| E5 | pressures | "the Mutual is a threat" | "the Mutual takes the bar on Friday if Walt can't pay" | What the pressure is, what happens if it is ignored, a situational next move for an agent, at most 3 active. | `pressure_has_consequence`, `pressure_next_move_in_situation` (judge), `pressures_active_count` (code) | 2 |
| E6 | knowledge status | "Ines knows the dues go upstairs; the dockhands believe the fund buries widows" (World has a Hidden and a Myth rule for these) | "nobody knows" | Ines knows (Hidden rule). Dockhands misled (Myth rule). Unaware people are left out. | None for a wrong status | 1 |
| E7 | knowledge: rule vs fact | "Pim suspects pearwood works", where World has the Myth "only applewood works" | "Pim knows Corbin is leaving" (not a world rule) | Rule-based: links to the existing rule with status suspects. Non-rule: a free fact. Nothing new is invented through the fact text. | `knowledge_one_fact` blocks both-or-neither only | 1 |

## Setup (all run from the fixed upstream cards)

| ID | Target | Tempting input | Control | Right looks like | Expected flag | Tier |
| --- | --- | --- | --- | --- | --- | --- |
| U1 ★ | goal | "find peace about his brother" | "reach the dock before it closes" | An action checkable in scenes, narrowing one of the protagonist's wants. No theme or feeling. | `goal_is_action`, `goal_checkable`, `goal_touches_cards` (judge) | 2 |
| U2 | normal, disruption | "life was dull and lonely; things are getting tense" | "he dives each dawn and drinks at the Spindle; the Authority posts a closing notice" | Normal is concrete routines, people and places. Disruption is an event. | `normal_is_concrete`, `disruption_is_event` (judge) | 2 |
| U3 | outcome kept out | A note whose goal includes the ending ("in the end Teodora is arrested and Imre is freed") | The same note without the ending | Setup holds no ending and no plan. | None | 1 |
| U4 | stakes | "it's very important" | "if he fails, he loses his brother's claim and his last tie to him" | A cost or gain tied to an existing want, value or pressure. | `stakes_has_cost`, `stakes_tie_to_cards` (judge) | 2 |
| U5 | protagonist | A note naming someone who is not a character as the lead | A note naming an existing character | The protagonist is an existing character. No new character is invented. | `protagonist_link_broken` (block) | 2 |

## What the catalog shows

- Thirteen probes are Tier 1: S3, S4, C1, C4, C8, W3, W4, E1, E2, E4, E6, E7 and U3. For these a wrong fill reaches the user with no warning, so the tests are the only safety net. Start tuning there.
- Wrong Hidden/Myth/Common status (W3), a wrong knowledge status (E6) and an invented entity in Entanglements (E2) are all Tier 1, and each is a plausible-looking error.
- A wrong concrete want (C1b) is the clearest rule gap: no warning covers a concrete aim that names no one. If the tests show the fill gets it wrong, a new warning rule is a possible fix, and that decision is yours.
- The schema only requires a truth on Myth rules. A truth on a Hidden or Common rule, and a vague truth, are not flagged, so W4 is a code and human check.
