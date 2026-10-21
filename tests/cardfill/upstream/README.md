# Fixed upstream sets

Hand-written Characters, World and (for set A) Entanglements cards, saved as JSON from the schema's own models, so they are valid and keep the same ids on every load. They give the Entanglements and Setup probes a stable foundation, so a failure on a later card is not blamed on an earlier fill. Every set was checked for: valid shape, no character named in World, no person, place or object named on a character card, every reference resolving, allowed holder types, and a truth on exactly the Myth rules.

| Set | Files | Used by |
| --- | --- | --- |
| A (Tern Station) | set-A-characters.json, set-A-world.json | E1 (Characters and World only; the Lattice is unowned and Entanglements is the thing being filled) |
| A plus Entanglements | the same two files plus set-A-entanglements.json | U1 to U5 (Setup reads all three) |
| B (Quay Street) | set-B-characters.json, set-B-world.json | E2, E4, E5, E6 |
| C (Thimble Hollow) | set-C-characters.json, set-C-world.json | E3, E7 |

Things the probes rely on:
- **A:** the Lattice has no holder (the only holding is Dock 9 held by the Salvage Authority). Imre is the protagonist for the U probes. Maren Holt does not exist, so U5's tempting input names a non-character.
- **B:** there is no Dockhands' Brotherhood, so E2's tempting input names a group that does not exist; the Harbor Mutual does exist, for the control. The Hidden rule (dues pass to the Customs House) and the Myth rule (the fund pays for burials, truth: it is empty) are the two rules E6 uses.
- **C:** the Myth rule is "only applewood works", with the truth that pearwood works too. Pim, Orla and Corbin are all characters.

These cards were written by hand to follow the schema's guidance, and checked with a small script covering the structural rules above. They have not been run through the model-judged warnings (for example `wants_conflict` or `object_unowned`), so treat them as hand-checked, not guaranteed warning-free, until they are.
