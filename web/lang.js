// The languages the page and the story can be in. One setting drives both: `project.output_language` is the language the model
// writes in and the language the page is shown in. No DOM here, so Node can test it.
//
//   LANGUAGES            the languages the page offers, with the name each is shown by (a language's own name is never translated)
//   DEFAULT_LANGUAGE     what a project is in when nothing else says
//   normalizeLanguage    any code a file or a browser may hold, as one of the codes above: zh, zh-Hans and zh-CN are `zh`,
//                        anything else, or nothing, is the default
//   bundleFiles          where a language's two files are: the page's words and the schema (card labels, help, messages)
//   loadBundles          reads both through `getJson(url)` and checks they are the language asked for
//   replaceContents      empties an object and fills it from another, keeping the object, so everything that holds it sees the swap
//   applyLanguageToProject  the project takes the page's language, and says what the page should do about it

export const LANGUAGES = [
  { code: "en", name: "English", short: "EN" },
  { code: "zh", name: "中文", short: "中文" },
];

export const DEFAULT_LANGUAGE = "en";

export function normalizeLanguage(code) {
  const base = String(code ?? "").trim().toLowerCase().split(/[-_]/)[0];
  return LANGUAGES.some((language) => language.code === base) ? base : DEFAULT_LANGUAGE;
}

export const bundleFiles = (code) => ({ text: `data/text.${code}.json`, schema: `data/schema.${code}.json` });

// Both files of a language, or an error saying which one could not be used. Nothing is changed on the page by this.
export async function loadBundles(code, getJson) {
  const language = normalizeLanguage(code);
  const files = bundleFiles(language);
  const [text, schema] = await Promise.all([getJson(files.text), getJson(files.schema)]);
  if (text?._meta?.language !== language) throw new Error(`${files.text} is not the ${language} text`);
  if (schema?.lang !== language) throw new Error(`${files.schema} is not the ${language} schema`);
  return { language, text, schema };
}

// The same object with new contents. The cards, their ids and their fields are the same in every language, and only the wording
// differs, so a panel that was given the schema once keeps working after the language changes.
export function replaceContents(target, next) {
  for (const key of Object.keys(target)) delete target[key];
  return Object.assign(target, next);
}

// The project follows the page's language. The answer says what the page should do: "same" (nothing), "rebase" (the project was blank,
// so the change is not work and the saved copy is brought up to date) or "changed" (an edit the writer can save).
export function applyLanguageToProject(project, code, wasBlank) {
  const language = normalizeLanguage(code);
  if (project.output_language === language) return "same";
  project.output_language = language;
  return wasBlank ? "rebase" : "changed";
}
