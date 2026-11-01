# Fixed upstream sets

Hand-written Characters, World and (for set A) Entanglements cards, saved as JSON from the schema's own models, so they are valid and keep the same ids on every load. They give the Entanglements and Setup probes a stable foundation, so a failure on a later card is not blamed on an earlier fill. Every set was checked for: valid shape under schema version 3, no character named in World, no person, place or object named on a character card, every reference resolving, and allowed holder types. `tests/evals/test_fixtures_valid.py` checks the shape and the links on every run.

| Set | Files | Used by |
| --- | --- | --- |
| A (Tern Station) | set-A-characters.json, set-A-world.json | W1 (Characters only), E1 (Characters and World; the Lattice is unowned and Entanglements is the thing being filled) |
| A plus Entanglements | the same two files plus set-A-entanglements.json | U2, U3, U5, U6, U7 (Setup reads all three) |
| B (Quay Street) | set-B-characters.json, set-B-world.json | E2, E4, E8, E9 |
| C (Thimble Hollow) | set-C-characters.json, set-C-world.json | E3 |

Things the probes rely on:
- **A:** the Lattice has no holder (the only holding is Dock 9 held by the Salvage Authority). Imre has two ties (to Teodora, from Teodora; to Kasimir), so he is a protagonist with ties in every Setup probe. Maren Holt does not exist, so U5's tempting input names a non-character. Setup restating the character card (U6) is checked against Imre's own card: stubborn, afraid of being found out as afraid, wants to be taken seriously.
- **B:** there is no Dockhands' Brotherhood, so E2's tempting input names a group that does not exist; the Harbor Mutual does exist, for the control. Walt and Ines are the two characters, with no tie between them, so E4 and E8 start from nothing. The Lantern Bar is a place nobody holds, for E9.
- **C:** Pim, Orla and Corbin are all characters, and the Parish Council is a group, so E3 can tie any two of them. No tie is held yet.

These cards were written by hand to follow the schema's guidance and checked structurally. They have not been run through the model-judged warnings (for example `wants_conflict` or `object_unowned`), so treat them as hand-checked, not guaranteed warning-free, until they are.
