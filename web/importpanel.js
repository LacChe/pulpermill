// The import panel: shown under the notices when the writer picks a card file with "Import card…". It says what is in the
// file and what bringing it in would do to the project, lets the writer choose how a character comes in (as a new character,
// or in place of one they already have), and changes nothing until they press the button. Afterwards a notice offers Undo.
// Nothing here calls the model. The rules are in exporting.js.
import { fileKind, readCardFile, planImport, applyImport } from "./exporting.js";
import { instanceName } from "./logic.js";
import { section, fill, joinList } from "./text.js";

export const STRINGS = section("import");

function node(tag, props = {}, ...children) {
  const made = Object.assign(document.createElement(tag), props);
  made.append(...children);
  return made;
}

// hooks: {schema, client, getProject, goTo(cardId, instanceId), forget(cardId, instanceId, keys), changed(), redraw(), notice(text, kind, action)}
export function createImportPanel(root, hooks) {
  let session = null;         // {project, read, file, choice}
  let bring = null;

  const refuse = (reason, card) => hooks.notice(joinList([fill(STRINGS.reasons[reason], { card: card ? hooks.schema.cards[card].label : "" }), STRINGS.unchanged], "sentence"), "notice-bad");

  function close() {
    session = null;
    bring = null;
    root.hidden = true;
    root.replaceChildren();
  }

  function refresh() {
    if (bring) bring.disabled = hooks.client.state.working;
  }

  // The writer picked a file. Open the panel, or say why not.
  function start(text, file) {
    close();
    const project = hooks.getProject();
    if (!project) return;
    const kind = fileKind(text);
    if (kind === "project") { refuse("project"); return; }
    const read = readCardFile(text, hooks.schema);
    if (!read.ok) { refuse(read.reason); return; }
    const plan = planImport(hooks.schema, project, read);
    if (!plan.ok) { refuse(plan.reason, plan.card); return; }
    session = { project, read, file, choice: { mode: "add" } };
    draw();
    bring?.focus();
  }

  function accept() {
    const project = hooks.getProject();
    if (!session || session.project !== project || hooks.client.state.working) return;
    const { schema } = hooks;
    const plan = planImport(schema, project, session.read, session.choice);
    if (!plan.ok) { const card = plan.card; const reason = plan.reason; close(); refuse(reason, card); return; }
    const done = applyImport(schema, project, plan);
    const card = schema.cards[plan.card];
    close();
    hooks.forget(plan.card, done.instanceId, done.keys);
    hooks.goTo(plan.card, done.instanceId);
    hooks.changed();
    const name = plan.name || STRINGS.unnamed.toLowerCase();
    const text = !card.many_per_project ? fill(STRINGS.filledCard, { card: card.label })
      : plan.mode === "add" ? (plan.name ? fill(STRINGS.addedCharacter, { name: plan.name }) : STRINGS.addedUnnamed)
      : fill(STRINGS.replacedCharacter, { name: instanceName(project[plan.card].find((i) => i.id === plan.targetId)) || name });
    hooks.notice(text, "", {
      label: STRINGS.undo,
      run: () => {
        if (hooks.getProject() !== project) return;
        done.undo();
        hooks.changed();
        hooks.redraw();
        hooks.notice(STRINGS.undone);
      },
    });
  }

  function chooser(project, plan) {
    const mine = project.characters ?? [];
    const add = node("input", { type: "radio", name: "import-mode", checked: session.choice.mode === "add" });
    add.addEventListener("change", () => { session.choice = { mode: "add" }; session.focus = "radio"; draw(); });
    const rows = [node("label", {}, add, node("span", { textContent: STRINGS.addNew }))];
    if (mine.length) {
      const replace = node("input", { type: "radio", name: "import-mode", checked: session.choice.mode === "replace" });
      const select = node("select", { className: "text-control", disabled: session.choice.mode !== "replace" });
      for (const person of mine) {
        select.append(node("option", { value: person.id, textContent: instanceName(person) || STRINGS.unnamed, selected: person.id === session.choice.id }));
      }
      select.setAttribute("aria-label", STRINGS.replaceOne);
      replace.addEventListener("change", () => { session.choice = { mode: "replace", id: select.value }; session.focus = "radio"; draw(); });
      select.addEventListener("change", () => { session.choice = { mode: "replace", id: select.value }; session.focus = "select"; draw(); });
      rows.push(node("label", {}, replace, node("span", { textContent: STRINGS.replaceOne }), select));
    }
    return node("fieldset", { className: "import-choice" }, node("legend", { textContent: STRINGS.how }), ...rows);
  }

  function draw() {
    if (!session) { close(); return; }
    const { schema } = hooks;
    const project = hooks.getProject();
    if (session.project !== project) { close(); return; }
    let plan = planImport(schema, project, session.read, session.choice);
    if (!plan.ok && plan.reason === "no_target") { session.choice = { mode: "add" }; plan = planImport(schema, project, session.read, session.choice); }
    if (!plan.ok) { const { reason, card } = plan; close(); refuse(reason, card); return; }
    const card = schema.cards[plan.card];
    const parts = [node("h3", { textContent: STRINGS.title })];
    parts.push(node("p", {
      textContent: card.many_per_project
        ? (plan.name ? fill(STRINGS.whatCharacter, { name: plan.name, file: session.file }) : fill(STRINGS.whatCharacterUnnamed, { file: session.file }))
        : fill(STRINGS.whatCard, { card: card.label, file: session.file }),
    }));
    if (card.many_per_project) {
      if ((project.characters ?? []).length) parts.push(chooser(project, plan));   // with nobody to replace there is nothing to choose
      const target = plan.mode === "replace" ? project.characters.find((i) => i.id === plan.targetId) : null;
      parts.push(node("p", { className: "help", textContent: target ? fill(STRINGS.replaceWords, { name: instanceName(target) || STRINGS.unnamed.toLowerCase() }) : STRINGS.addWords }));
    } else {
      parts.push(node("p", { className: "help", textContent: fill(plan.replaced.length ? STRINGS.replacesCard : plan.filled.length ? STRINGS.fillsEmpty : STRINGS.sameCard, { card: card.label }) }));
    }
    if (plan.replaced.length) parts.push(node("p", { textContent: fill(STRINGS.replacesFields, { fields: joinList(plan.replaced) }) }));
    if (plan.lost) parts.push(node("p", { className: "import-warn", textContent: fill(STRINGS.lost, { cards: joinList(plan.lost.cards), n: plan.lost.count }) }));
    if (plan.ignored.length) parts.push(node("p", { className: "help", textContent: fill(STRINGS.ignored, { fields: joinList(plan.ignored) }) }));
    parts.push(node("p", { className: "note", textContent: STRINGS.safe }));
    bring = node("button", { type: "button", className: "validate", textContent: STRINGS.bring });
    bring.addEventListener("click", accept);
    const cancel = node("button", { type: "button", textContent: STRINGS.cancel });
    cancel.addEventListener("click", close);
    parts.push(node("div", { className: "plan-actions" }, bring, cancel));
    root.replaceChildren(...parts);
    root.hidden = false;
    refresh();
    // The panel is drawn again after each choice, so keep the keyboard where the writer was.
    if (session.focus === "radio") root.querySelector('input[name="import-mode"]:checked')?.focus();
    if (session.focus === "select") root.querySelector("select")?.focus();
    session.focus = null;
  }

  return { start, close, refresh, reset: close };
}
