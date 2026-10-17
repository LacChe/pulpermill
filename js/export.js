/* Pulpermill page: Downloads: story and individual cards as files. */
const storyFile = () => slugify($("#slug").value || t("story"));
function downloadBlob(name, blob) {
  const a = el("a", { href: URL.createObjectURL(blob), download: name });
  document.body.append(a);
  a.click();
  a.remove();
}
function downloadText(name, text, type) {
  downloadBlob(name, new Blob([text], { type: type || "text/plain" }));
}

/* Single-file export for one card (style, world or outline/setup), or one character, so each can be kept or shared on its own. */
function exportSingleCard(j, key) {
  const pg = pages()[j],
    end = isEnding(j),
    names = { style: "style.json", outline: "setup.json", world: "world.json" };
  const val = pg.cards[key],
    name = names[key];
  if (!val || !name) return;
  const meta = { format: "pulpermill-cards", version: 1 };
  if (end) meta.note = "cards after chapter " + j;
  else meta.chapter = j + 1;
  const text = JSON.stringify(
    Object.assign({}, meta, { [key]: clean(val, key) }),
    null,
    2,
  );
  downloadText(storyFile() + "_" + name, text, "application/json");
}
function exportCharacter(j, i) {
  const c = (pages()[j].cards.characters || [])[i];
  if (!c) return;
  const base =
    slugify(c.id || c.name || "character_" + (i + 1)) || "character_" + (i + 1);
  downloadText(
    storyFile() + "_" + base + ".json",
    JSON.stringify(clean([c], "characters")[0], null, 2),
    "application/json",
  );
}
function exportStory() {
  const md = pages()
    .map((p, i) =>
      p.result
        ? "## " +
          t("Chapter {k}", { k: i + 1 }) +
          "\n\n" +
          p.result.text.trim() +
          "\n"
        : null,
    )
    .filter(Boolean)
    .join("\n");
  if (md) downloadText(storyFile() + "_story.md", md, "text/markdown");
}
