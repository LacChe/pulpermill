// The import panel: shown under the notices when the writer picks a card file with "Import card…". It says what is in the
// file and what bringing it in would do to the project, lets the writer choose how a character comes in (as a new character,
// or in place of one they already have), and changes nothing until they press the button. Afterwards a notice offers Undo.
// Nothing here calls the model. The rules are in exporting.js.
import { planBatchImport, applyImport } from "./exporting.js";
import { section, fill, joinList } from "./text.js";

export const STRINGS = section("import");

function node(tag, props = {}, ...children) {
  const made = Object.assign(document.createElement(tag), props);
  made.append(...children);
  return made;
}

// hooks: {schema, client, getProject, goTo(cardId, instanceId), forget(cardId, instanceId, keys), changed(), redraw(), notice(text, kind, action)}
export function createImportPanel(root, hooks) {
  let session = null;         // {project, entries, failed}
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

  function failureText(failure) {
    if (failure.readError) return STRINGS.reasons.unreadable;
    return fill(STRINGS.reasons[failure.reason], { card: failure.card ? hooks.schema.cards[failure.card].label : "" });
  }

  // The writer picked files. Open the panel for valid files, or report every failure.
  function start(entries) {
    close();
    const project = hooks.getProject();
    if (!project) return;
    const result = planBatchImport(hooks.schema, project, entries.filter((entry) => !entry.readError));
    const failed = [...result.failed, ...entries.filter((entry) => entry.readError).map((entry) => ({ ...entry, reason: "unreadable" }))];
    if (failed.length) hooks.notice(failed.map((failure) => fill(STRINGS.failedFile, { file: failure.file, reason: failureText(failure) })).join("\n"), "notice-bad");
    if (!result.accepted.length) return;
    session = { project, entries: result.accepted, failed };
    draw();
    bring?.focus();
  }

  function accept() {
    const project = hooks.getProject();
    if (!session || session.project !== project || hooks.client.state.working) return;
    const { schema } = hooks;
    const result = planBatchImport(schema, project, session.entries);
    if (!result.accepted.length) { close(); hooks.notice(STRINGS.unchanged, "notice-bad"); return; }
    const dones = result.accepted.map(({ plan }) => applyImport(schema, project, plan));
    const last = result.accepted[result.accepted.length - 1].plan;
    const failures = result.failed.length ? ` ${result.failed.map((failure) => fill(STRINGS.failedFile, { file: failure.file, reason: failureText(failure) })).join(" ")}` : "";
    close();
    for (const { plan } of result.accepted) {
      const done = dones[result.accepted.findIndex((entry) => entry.plan === plan)];
      hooks.forget(plan.card, done.instanceId, done.keys);
    }
    hooks.goTo(last.card, dones[dones.length - 1].instanceId);
    hooks.changed();
    hooks.notice(`${fill(STRINGS.importedBatch, { n: result.accepted.length })}${failures}`, "", {
      label: STRINGS.undo,
      run: () => {
        if (hooks.getProject() !== project) return;
        const backs = [...dones].reverse().map((done) => done.undo());
        const blocked = backs.some((back) => !back.done);
        if (blocked) { hooks.notice(STRINGS.undoBlocked, "notice-bad"); return; }
        hooks.changed();
        hooks.redraw();
        hooks.notice(STRINGS.undone);
      },
    });
  }

  function draw() {
    if (!session) { close(); return; }
    const project = hooks.getProject();
    if (session.project !== project) { close(); return; }
    const parts = [node("h3", { textContent: STRINGS.title }), node("p", { textContent: fill(STRINGS.batchReady, { n: session.entries.length }) })];
    parts.push(node("ul", { className: "import-files" }, ...session.entries.map((entry) => node("li", { textContent: entry.file }))));
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
