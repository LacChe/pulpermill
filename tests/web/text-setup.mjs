// Loads the English text bundle the way the page does at start, so code that words things with msg() or a section works in Node.
// Every test file imports this first.
import { readFileSync } from "node:fs";
import { setText } from "../../web/text.js";

export const bundle = JSON.parse(readFileSync(new URL("../../web/data/text.en.json", import.meta.url), "utf8"));
setText(bundle);
