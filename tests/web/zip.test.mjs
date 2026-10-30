import "./text-setup.mjs";
import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync, readFileSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { crc32, dosDate, makeZip } from "../../web/zip.js";
import { cardFiles, cardsZipName } from "../../web/exporting.js";
import { schema, readyProject } from "./helpers.mjs";

const when = new Date(2026, 9, 24, 14, 30, 10);

test("crc32 matches the known check values", () => {
  assert.equal(crc32(new TextEncoder().encode("123456789")), 0xcbf43926);
  assert.equal(crc32(new Uint8Array(0)), 0);
});

test("the date is kept the way a zip keeps it", () => {
  const { time, day } = dosDate(when);
  assert.equal(day >> 9, 2026 - 1980);
  assert.equal((day >> 5) & 15, 10);
  assert.equal(day & 31, 24);
  assert.equal(time >> 11, 14);
  assert.equal((time >> 5) & 63, 30);
  assert.equal((time & 31) * 2, 10);
  assert.equal(dosDate(new Date(1970, 0, 1)).day >> 9, 0);   // before 1980 is held at 1980
});

test("the zip has the right layout and its names are marked as UTF-8", () => {
  const bytes = makeZip([{ name: "a.json", text: "{}" }, { name: "é-ü.json", text: "héllo" }], when);
  const view = new DataView(bytes.buffer);
  assert.equal(view.getUint32(0, true), 0x04034b50);
  assert.equal(view.getUint16(6, true) & 0x0800, 0x0800);
  const end = bytes.length - 22;
  assert.equal(view.getUint32(end, true), 0x06054b50);
  assert.equal(view.getUint16(end + 10, true), 2);
  assert.equal(view.getUint32(end + 16, true) + view.getUint32(end + 12, true), end);
});

test("two files with one name are refused, and an empty zip is still a zip", () => {
  assert.throws(() => makeZip([{ name: "a", text: "1" }, { name: "a", text: "2" }]), /Two files/);
  const empty = makeZip([]);
  assert.equal(empty.length, 22);
});

test("a real unzip tool opens it and gets every file back, byte for byte", (t) => {
  try { execFileSync("unzip", ["-v"], { stdio: "ignore" }); } catch { t.skip("no unzip tool here"); return; }
  const dir = mkdtempSync(join(tmpdir(), "zip-"));
  const files = [
    { name: "plain.json", text: '{"a": 1}\n' },
    { name: "empty.txt", text: "" },
    { name: "naïve-café.json", text: "Ünïcode — “quotes” 日本語\n" },
    { name: "big.txt", text: "chapter text ".repeat(20000) },
  ];
  writeFileSync(join(dir, "x.zip"), makeZip(files, when));
  execFileSync("unzip", ["-tq", join(dir, "x.zip")]);        // tests every checksum
  execFileSync("unzip", ["-qq", "-O", "UTF-8", join(dir, "x.zip"), "-d", join(dir, "out")], { stdio: "ignore" });
  for (const f of files) assert.equal(readFileSync(join(dir, "out", f.name), "utf8"), f.text);
  assert.equal(readdirSync(join(dir, "out")).length, files.length);
});

test("the card files of a project go into the zip under their own names", async () => {
  const project = await readyProject();
  project.title = "The Salt Coast!";
  const files = cardFiles(schema, project);
  assert.equal(cardsZipName(project), "the-salt-coast-cards.zip");
  const bytes = makeZip(files.map((f) => ({ name: f.name, text: f.text })));
  const view = new DataView(bytes.buffer);
  assert.equal(view.getUint16(bytes.length - 22 + 10, true), files.length);
});
