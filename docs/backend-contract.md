# Backend contract

*What the page sends the backend and what comes back. Phases 7 and 8. The backend is not written yet: the page runs against a mock (`web/mock.js`) that answers in exactly these shapes.*

The code that holds this contract:

| What | Where |
| --- | --- |
| Page: build requests, read replies, errors | `web/logic.js` (section "The backend contract") |
| Page: sending, timeouts, Stop, status | `web/client.js` |
| Backend: the same shapes as Pydantic models | `pulpermill/schema/contract.py` |
| Stand-in backend | `web/mock.js` |
| Examples checked on both sides | `web/tests/contract-vectors.json` |

If this document and the vectors disagree, the vectors are right, because tests run them.

## Ground rules

- **Stateless.** Every request carries everything the call needs. The backend keeps nothing between calls except whether it is busy.
- **All or nothing.** A call that fails, times out or is stopped changes nothing. The writer presses the button again. The page never keeps half an answer.
- **Model calls start only from a button press.** Typing and leaving a field never call the backend. The one call the page makes by itself is `status`, and it is not a model call.
- **Named calls are kept.** A model call may carry a `job_id` (8 to 64 letters, digits, `_` or `-`, made by the page). The backend then keeps the call going if the connection drops, and keeps its answer in memory (the newest 30 finished calls) so the page can ask for it with `{"call": "job", "job_id": ...}`. The reply is `{"ok": true, "state": "running", "stage"?}` while it runs, `{"ok": true, "state": "unknown"}` if the backend has never seen it or was restarted, and otherwise exactly what the call would have answered (its reply or its error). Fetching does not remove it. `{"call": "cancel", "job_id": ...}` stops a running named call (`cancelled`, or `unknown`). `{"call": "cancel"}` with no `job_id` stops whatever call is running, named or not (`cancelled`, or `unknown` when nothing runs); the backend reports `busy` until the call has really ended, so a stop that is slow shows as a status that stays `busy`. Sending a named call again does not start it twice: it answers where the call stands. A call without a `job_id` is stopped when its connection drops, as before. Nothing is written to disk, so restarting the backend loses every kept answer.
- **Rotating lists arrive trimmed.** The page sends at most five places, things, ties, holdings, Knowledge entries and pressures in a request: everything the beat names (by link, or in its words), then the least used. A value counts as used only when it appears in a written chapter's text. The lists are not marked as cut; the backend treats what it is sent as the whole.
- **One job at a time.** The backend runs one model call at a time. A second one gets `busy`.
- **The page decides.** The backend answers; it never edits the project. Anything that would replace what the writer wrote is confirmed on the page before it lands.
- **Language.** `language` is the language the model writes in. Instructions to the model stay in English. The backend checks the output language and retries once if it drifted.

## Transport

Every call is one `POST` of one JSON object to `<address>/api`, with `content-type: application/json`. The call is named inside the object (`"call": "fill"`). There is one address, so a proxy or a mock needs one route.

The page is served from another origin (GitHub Pages, or `localhost` while building), so the backend must answer the browser's cross-origin check: reply to the `OPTIONS` preflight, and send `access-control-allow-origin` (the page's origin, or `*`), `access-control-allow-methods: POST` and `access-control-allow-headers: content-type, ngrok-skip-browser-warning, x-pulpermill-token`. A backend without this looks like `unreachable` to the page.

**Headers the page sends.** Every request to a real backend carries `ngrok-skip-browser-warning: 1`, which skips ngrok's browser warning page, and, when the writer has typed an access token, `x-pulpermill-token` with that token. The token is a shared secret, because a tunnel address is public. When the backend has a token configured it checks it, in constant time, on **every `POST`, including `status`**, and answers `unauthorized` (401) when it is missing or wrong. It answers the `OPTIONS` preflight **without** the token, because the browser does not attach custom headers to a preflight. The token is never logged or put in a reply. A backend with no token configured ignores the header.

A page served over `https` may not call a plain `http` address, except one on the writer's own computer (`localhost`, `127.0.0.1`). The page refuses such an address when the writer types it.

## Replies and errors

Every reply is a JSON object. Success is `{"ok": true, ...the call's own fields}`. Failure is:

```json
{"ok": false, "error": {"kind": "bad_output", "detail": ""}}
```

The page reads the body first. When the body is not an answer it falls back on the HTTP status, so send the status that goes with the kind.

| `kind` | Sent by | HTTP | Meaning | What the writer sees |
| --- | --- | --- | --- | --- |
| `busy` | backend | 503 | Another model call is running. | The model is busy with another job, so nothing was changed. Try again in a moment. |
| `bad_request` | backend | 400 | The page sent something the backend cannot use: a schema version newer than it knows, or a shape that fails `parse_request`. A bug, not a writer mistake. `detail` is shown. | The page sent something the model's server didn't understand, so nothing was changed. |
| `bad_output` | backend | 502 | The model's answer did not fit the shape, even after the backend's retry. The pipeline allows two attempts in total, and the first failure's message goes into the second. | The model's answer didn't come out in the right shape, so nothing was changed. Press the button again. |
| `too_long` | backend | 413 | The prompt does not fit the model's context. Checked before the call, so it fails fast. | There is too much text to send to the model in one go, so nothing was changed. Shorten the notes or the example chapter. |
| `stopped` | backend | 409 | The writer pressed Stop and the call ended. The page has usually stopped listening, so this is rarely read. | Stopped. Nothing was changed. |
| `server` | backend | 500 | Anything else. `detail` is shown, in plain words. | The model's server had a problem, so nothing was changed. |
| `unauthorized` | backend | 401 | The access token is missing or wrong. | The model's server didn't accept the access token, so nothing was changed. Check the token beside the address. |
| `unreachable` | **page** | none | Nothing answered. Never sent by a backend. | Couldn't reach the model, so nothing was changed. Check the address and that it is running. |
| `timeout` | **page** | none | No answer in time (below). Never sent by a backend. | The model took too long to answer, so nothing was changed. |

The page gives up after 5 seconds for `status`, 180 seconds for `fill` and `judge`, 120 seconds for `style_fit` and `offstage`, 300 seconds for `plan`, 600 seconds for `end_story` and 1800 seconds for `generate`.

## Status and Stop

`status` is `{"call": "status"}` and the reply is `{"ok": true, "state": "idle"}` or `"busy"`. The page asks when it opens, when the writer presses Check, after the address changes, and after a Stop or a timeout.

**Progress.** Story calls are long and are not streamed. While one runs, the page asks `status` every second. A busy backend may say where it is: `{"ok": true, "state": "busy", "stage": "events"}`. `stage` is one of `offstage`, `think`, `beat`, `retry`, `write`, `events`, `shifts`, `update`, is only sent while busy, and is optional (a backend that does not know leaves it out; a stage the page does not know is ignored). The same checks tell the page the connection is lost: three failed checks in a row end the call as `unreachable`, nothing changed. So `status` must always answer, even while the model is working.

**Stop.** The Stop button is shown whenever the page has a call going or the backend says `busy`, including a job the page no longer tracks. Pressing it aborts the page's request and sends `cancel` (with the call's `job_id` when the page knows it, otherwise with none), and a cancel that fails is shown. When the connection closes the backend must stop inference (the doc's cancel flag, checked inside the generation loop) and report `idle` from then on. After a Stop or a timeout the page asks `status` every half second, up to 120 times (a minute), keeps the button disabled, shows "Stopping…" and keeps the page locked until it says `idle`. If the backend is still busy after that minute the page says so plainly, shows "Busy" and leaves Stop visible to press again; the Check button also asks again.

## The calls

Every call but `status` starts with the same two fields: `schema_version` (the project file format, from the page's schema; a backend that knows only older versions answers `bad_request`) and `language`.

### `fill`: fill one card

The writer's notes and an example chapter go in; the card's fields come out. Only the five fillable cards are accepted: `style`, `characters`, `world`, `entanglements`, `setup`.

```json
{
  "call": "fill", "schema_version": 1, "language": "en",
  "card": "setup", "instance": null,
  "note": "Suvi must find the ledger before the harbour board does.",
  "example_chapter": null,
  "values": {"protagonist": "", "normal": "", "disruption": "", "goal": "", "stakes": "", "chapter_count": null},
  "related": {"style": {"person": "first"}, "characters": [{"id": "c0000001", "name": "Suvi"}]}
}
```

- `note` is the writer's note for this card, exactly as typed. `example_chapter` is shared by every card. At least one must be non-blank; the page does not call otherwise, and the backend refuses it (`bad_request`).
- `instance` is the character's id when `card` is `characters`, and `null` for every other card.
- `values` is the card as it stands now, by field key, so the model can see what is already written. For Characters it is that one character, with its `id`.
- `related` is the cards this card reads (the schema's `reads`), by card id, copied from the project. Never the whole project. Characters is a list; the others are single cards.

Reply:

```json
{"ok": true, "values": {"protagonist": "Suvi", "goal": "Find the ledger.", "chapter_count": 8}}
```

- `values` holds fields of that card, by key. Keys the card does not have are ignored by the page; a value of the wrong kind (text where a list goes) is a `bad_output`.
- **Empty means no answer.** A field left out, `""`, `null` or `[]` leaves whatever the writer wrote there alone. The page never blanks a field because the model had nothing.
- **Links are words, not ids.** A field that points at another card's entry (`protagonist`, a tie's `tie_from`, a pressure's `bears_on`) holds that entry's name as the writer sees it: `"Suvi"`. The backend never invents or guesses ids. The page turns each name into an id; a name that matches nothing, or two entries, is left empty and the writer is told. For a field that takes several (`bears_on`), send a list of names.
- **Lists are lists of objects without ids.** The page gives every new item an id. A list that comes back the same as it was changes nothing.
- Choices (`select` fields) hold the option's `value` from the schema, not its label.
- **An either-or pair holds one value.** Where a card's list item is "one of two" (a knowledge entry's `rule` or `fact`, a pressure's `source_agent` or `source_circumstance`), the reply schema offers two shapes, each with one of the pair required and the other absent. If both still arrive, the page keeps the first of the pair and drops the other.
- Write in `language`. Fixed fields (name, age, sex, appearance) are written once here like any other; the story never changes them.

### `judge`: the model-judged rules of one card

Some rules are judgements code cannot make ("the era is a fact, not a mood"). The page asks only when the writer presses Validate, and only about the rules whose fields changed since they were last asked (it remembers answers by the content of the fields a rule reads and the cards it links to).

```json
{
  "call": "judge", "schema_version": 1, "language": "en",
  "card": "world", "instance": null,
  "rules": [{"id": "everyday_has_friction", "fields": ["everyday_life"]}],
  "values": {"name": "The Salt Coast", "everyday_life": "Ordinary."},
  "related": {}
}
```

`rules` holds only the rules to answer now, each with the card fields it is about. The rule's wording and judge prompt live in the schema's text files, which the backend reads; the page does not send them.

Reply:

```json
{"ok": true, "results": [
  {"rule": "everyday_has_friction", "hits": [{"field": "everyday_life"}]}
]}
```

- One result per rule asked, in any order. `hits` says where the rule is broken, and an empty list means it passed. **A rule with no result is not counted as passed**: the writer is told it got no answer.
- A hit names a `field` of the card. For a problem inside a list item it also gives the item's `id` as it was sent in `values`, and optionally the `key` of the box inside that item. A hit on an item that is gone falls back to the whole field.
- Results for rules that were not asked are ignored. A hit that names a field the card does not have is a `bad_output`.
- Judge results are warnings. They never stop the writer, and the page shows them as the model's opinion until the writer edits the thing they are about.

### `style_fit`: does the protagonist suit the voice?

The story-start gate. Does the protagonist's personality allow the person, tense and voice the Style card chose? (The page does not send this yet; the gate comes with the story phase.)

```json
{"call": "style_fit", "schema_version": 1, "language": "en",
 "style": {"person": "first", "tense": "past"},
 "protagonist": {"id": "c0000001", "name": "Suvi", "flaw": "Guarded."}}
```

Reply: `{"ok": true, "fits": false, "message": "Too guarded for first person."}`. `message` is optional and is shown when `fits` is false.

## The story calls

These carry a story, one chapter at a time. The same ground rules hold: stateless, all or nothing, the page decides, links in words. What is new is that **the page does the code work and sends the result**: the spotlight, the legal shifts, the open plants, the available reveals, the current goal, the use counts and which cards are in play (the cast, and what the beat touches) are worked out on the page. The backend renders prose from what it is sent, runs the model, and answers. Cards and records inside these requests are the project's own values, copied. Every item keeps its own `id`, so a reply can point back at an item by the id it was sent; but a field that links to another entry carries that entry's name ("Suvi"), not its id, so the backend can write prose without a lookup table. The character cards sent are the cast's only.

Replies use words for links (a place's name, a character's name, a rule's statement, the wording of an open plant that was sent). The step that lands each reply turns the words into ids, the way the fill does, and tells the writer about any that match nothing.

### `offstage`: what the background does

Only sent when the page decides an offstage change is due (every second chapter). About background groups and places, never the spotlight.

```json
{"call": "offstage", "schema_version": 1, "language": "en", "chapter": 2, "chapter_count": 8,
 "cast": [{"id": "c0000001", "name": "Suvi"}], "world": {}, "entanglements": {}, "latest_events": {"happened": "..."},
 "earlier_offstage": [{"chapter": 2, "did": "The board raids the docks."}]}
```

`earlier_offstage` lists the background moves already made, oldest first (empty when there are none), so the next one can be a different kind.

Reply: `{"ok": true, "did": "The board raids the docks.", "reach": "Suvi hears the bells."}`. Both are needed; the page refuses half a move.

### `plan`: think, then fill the beat

One call. The backend thinks in free text, then fills the beat in the schema's shape. The thinking comes back and **the writer is shown it**. `offstage` is the move from the call above, when there was one. `retry` is sent only when the page's block rules refused the first attempt: it holds that attempt and the rules' words, and the backend tries once more with them. The pipeline allows two attempts in total.

Request: `chapter`, `chapter_count`, `style`, `setup`, `goal` (the goal the story stands on now), `story_goal` (Setup's goal once the chapters have moved off it), `goal_plan` (`{due, age, since, earlier_goals}`), `cast`, `world`, `entanglements`, `spotlight`, `legal_shifts` (`harder` and/or `easier`), `open_plants` (`[{text, chapter}]`), `available_reveals`, `use_counts`, `earlier_beats`, `earlier_events`, `latest_shifts`, `offstage`, `retry`.

Reply: `{"ok": true, "thinking": "...", "beat": {"where": "The Salt Coast", "collision_goal": "..."}}`. `beat` holds the beat's planner fields by key (not the cast, the chapter number, the spotlight, the offstage move or the planned-from hash: those are the writer's or the page's). A `payoff` is a list of open plants' wording as it was sent. Keys the beat does not have are ignored.

*Added 2026-11-05 (later additions, so older requests stay valid).* A plan request may also carry `choose` (boolean, default `false`) and `pressure_options` (default `[]`): every rule and object of the world in words with an `id` (`{id, kind: "rule", statement, cost, when_broken}` or `{id, kind: "object", name, description, significance}`; ids unique). The page sends `choose: true` with the options on every plan call (the Plan button, Run all and a replan; `choose` still defaults to `false` in the contract, so older requests stay valid, and only the retry after the Outline's block rules sends `choose: false`); `spotlight` and `pressure` are then the page's stand-in pair, kept as a fallback when the select step fails twice. The mill runs the select step whenever the request asks to choose and has at least one tie between two people of the cast: it picks exactly three combinations holding at least `min(3, the number of distinct pairs)` different pairs, so with fewer than three pairs a pair may repeat, and the brainstorm then writes two different chapters for it. A reply may carry `picked`: `{"spotlight": "<a tie id from the request>", "pressure": "<an option id>" | null}`, and the page applies it to the beat only if both ids check out. A reply carries `picked` when the select step ran and the plan's idea held; after a select fallback there is none and the beat keeps the page's pair.

*Added 2026-11-07 (a later addition, so older requests stay valid).* A plan request may also carry `origin_history` (boolean, default `false`). When it is `true` and the chapter is 2 or later, the select, brainstorm and plan prompts of the mill add the Setup's `disruption` (never the `normal`) to their "Who the story follows" section as origin history that the story so far extends from. Chapter 1 and the `generate` call are unchanged, and with the flag `false` the prompts are byte-identical to before. The page does not send the flag yet.

### `generate`: write a chapter

One call, three passes: write the chapter, the Events pass (what the text shows happened) and the shifts pass (the new edge of the ties the chapter moved). People and the World do not change from chapter to chapter; people change once, at the end of the story (`finish`). Nothing is kept if any pass fails; the writer presses Generate again.

Request: `chapter`, `chapter_count`, `style`, `setup` (the normal and the disruption only in chapter 1), `goal` (the goal the chapter begins from), `story_goal`, `earlier_goals` (the goals before it, oldest first), `cast`, `world`, `entanglements`, `standing` (where the ties stand now: their latest edges, which override the cards), `earlier_events`, `previous_ending`, `beat` (in words), `open_plants`, `available_reveals`. A prompt that does not fit is `too_long`, checked before the model runs.

Reply:

```json
{"ok": true, "chapter_text": "...",
 "events": {"happened": "...", "changed": "...", "planted": null, "paid_off": [], "reveals_landed": [],
            "behaviors_seen": [], "things_seen": [], "goal_change": "redefined", "goal_now": "Find the ledger in the cellar."},
 "shifts": [{"card": "entanglements", "target": null, "patch": {"ties": [{"op": "replace", "id": "t1000001", "values": {"edge": "to keep her daughter from leaving"}}]}}],
 "changes": [{"section": "knowledge", "item": "k0000001", "field": "knows", "value": "Suvi"}],
 "new_knowledge": [{"person": "Suvi", "status": "suspects", "rule": null, "fact": "The ledger is forged."},
                   {"person": "Pekka", "status": "knows", "entry": "k0000001"}],
 "shown": ["p0000001", "k0000001"]}
```

- `events` is what the text shows. A planned plant, payoff or reveal counts only when it is here; the page compares. `goal_change` (`achieved`, `redefined` or `abandoned`) and `goal_now` are always given: how the chapter left the goal it began with, and what the protagonist wants from here on. The page makes `goal_now` the goal the next chapter is planned from. `paid_off` and `reveals_landed` use the wording that was sent.
- `shifts` holds at most one entry, for the Entanglements (`card` is `entanglements`, `target` is null), and its patch only `replace`s the `edge` of ties named by the id they were sent with. A shift for Characters or the World, a change to anything else on a tie, two entries for the Entanglements, or an entry with an empty patch is refused (`bad_output`).
- `shown` is optional (a reply without it means none): the ids, as the page sent them, of the knowledge entries, ties and holdings the chapter actually showed (never a pressure: its use is the spotlight) (something a person acts on, is held back by, learns, or that changes on the page, not merely one that is named). The model that reads the chapter decides; the backend asks for it as a list of handles in the same pass as the changes and turns them back into ids, dropping any it does not know. The page keeps them in the chapter's record (`entanglements_shown`) and counts use from that record, so what has been shown least is what later requests carry. A reply without it counts nothing for that chapter.
- `new_knowledge` is optional (a reply without it means none): Knowledge for someone who has come to know, suspect or be misled about something. A row about something that already has a line gives `entry`, that line's id as sent (the backend turns the handle back), with `rule` and `fact` empty, and the person is put into that line; only something with no line yet is written out as a `rule` or `fact`. `person` is a character's or group's name as sent; give exactly one of `rule` (a World rule's wording as sent) and `fact` (free text); `status` is `knows`, `suspects` or `misled`. The backend never makes an id. The page adds each entry as a change the writer can read in the chapter's review, and leaves one out, saying why, when the person or rule is not found, the person is a character who is not in the chapter, the entry gives both or neither of rule and fact (when it names no `entry`), the `entry` is not a line the page sent, or the person is already so. One entry is one thing with three lists of people and groups (`knows`, `suspects`, `misled`, a person in one of them): a proposal about a thing that already has an entry puts that person into the entry (moving them if they stood another way), and several proposals about a new thing make one entry between them. There is no limit on how many a chapter adds. It asks first when a lock covers the Knowledge list. A malformed entry (wrong type, unknown status) makes the whole reply `bad_output`. Undo takes the entries out with the rest of the chapter.
- A `changes` entry on a Knowledge item names `knows`, `suspects` or `misled` as the field and the one person or group who now stands that way as the value; the page moves them out of the item's other lists, and clears `belief` when no one is misled any more.
- `changes` are proposals to **live** Entanglements fields (`ties`, `holdings`, `knowledge`, `pressures`). `item` is an id the page sent; the backend never makes one. The page applies them, asks before touching anything locked, and warns if a reveal landed but no one's knowledge changed.

### `finish`: how the story changed each person

*Added 2026-11-07 (a new call, so older requests stay valid).* After the last chapter, one model call looks back over the whole story and writes the most notable change per person: at most one entry for each character, and none for a character the story did not truly change. It reads the chapters' Events records (what happened, what changed; one entry per chapter, in order) and the Characters cards as they were before the story began, so it knows the field names and the current values. It never reads a chapter's text. The Setup card gives it the protagonist and the opening.

```json
{"call": "finish", "schema_version": 4, "language": "en",
 "setup": {"protagonist": "c0000001", "normal": "Suvi kept the Archive.", "disruption": "A ledger went missing."},
 "protagonist": "c0000001",
 "characters": [{"id": "c0000001", "name": "Suvi", "fear": "Being found out", "wants": [{"id": "w0000001", "text": "To be left alone"}]},
                {"id": "c0000002", "name": "Marit"}],
 "events": [{"chapter": 1, "happened": "Suvi hid the ledger.", "changed": "Suvi now owes her mother an answer."},
            {"chapter": 2, "happened": "Suvi told Marit where it was.", "changed": "Suvi has let her mother in."}]}
```

Request: `setup`, `protagonist` (the id of one of `characters`), `characters` (at least one, all of them, with ids) and `events` (at least one, oldest first). A request with a field it does not know is `bad_request`.

Reply: `{"ok": true, "shifts": [{"card": "characters", "target": "c0000001", "patch": {"fear": "Being left with nobody to tell"}}]}`. `target` is the character's id as it was sent. `patch` is a sparse copy of the Characters card in the shape every shift has: a single-value field holds its new value, a list field holds `replace` operations naming items by the id they were sent with. Fixed fields (name, age, sex, appearance) never appear. The list is empty when nobody changed in a way that matters, and that is a valid reply. A reply for the Entanglements or the World, two entries for one character, or an entry with no target is `bad_output`.

The page stores each entry as a shift on the last beat. The last beat is exempt from two rules of the Shifts record, the cap of seven entries per beat and the cast rule (a story may have more than six characters, and a character who was not in the last chapter may still have changed over the whole story); the rule that allows one entry per character on a beat still holds. The backend checks every entry before it answers: only people it was sent, one entry each, a patch that fits the card. When no reply passes the check after two attempts, the call answers with no shifts, so the end of the story is never blocked by it.

## How it is tested

- `web/tests/logic.test.mjs` ("The contract vectors") checks that the page builds exactly the golden requests and reads every valid reply and refuses every invalid one.
- `tests/schema/test_contract.py` checks that the Pydantic models accept and refuse the same examples, and that the error kinds, fillable cards, card list and HTTP statuses match what the page uses.
- Examples where the two sides are deliberately not equally strict (extra keys, a value of the wrong kind for one particular card) are left out of the vectors.
- `web/mock.js` answers every call, including the story calls (a plain sample chapter, a beat made from the request's own places, and a stage in `status`), and can be made to fail on demand (`mock.queue("busy", "bad_output", …)`), and writing `FLAG ME` into a card makes its judge and style-fit answers complain, so every state above can be seen in the page without a model.
