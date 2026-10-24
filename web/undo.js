// What makes an Undo safe. An Undo puts back what its action changed, and nothing else: if the writer has changed that same
// part of the project since, putting the old copy back would throw their work away, so the Undo declines and says so.
// No DOM, so Node can test it.
//
//   watch(project, keys)    take a copy of those parts of the project now, before the action runs
//     .settle()             call once the action is done: remembers what the action left there
//     .undo()               puts the copies back and answers true, or, when those parts are no longer as the action left them,
//                           changes nothing and answers false
//   sameValue(a, b)         two stored values are equal
//   untouched(now, wrote, keys)   of those fields, the ones still holding what the action wrote (the rest were edited since)

const copy = (value) => (value === undefined ? undefined : JSON.parse(JSON.stringify(value)));
const print = (project, keys) => JSON.stringify(keys.map((key) => [key, project[key] ?? null]));

export const sameValue = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);

export function watch(project, keys) {
  const before = Object.fromEntries(keys.map((key) => [key, copy(project[key])]));
  let after = null;
  return {
    settle() { after = print(project, keys); },
    undo() {
      if (after !== null && print(project, keys) !== after) return false;
      for (const key of keys) {
        if (before[key] === undefined) delete project[key]; else project[key] = copy(before[key]);
      }
      return true;
    },
  };
}

export function untouched(now, wrote, keys) {
  return keys.filter((key) => sameValue(now[key], wrote[key]));
}
