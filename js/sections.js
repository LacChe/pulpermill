/* Pulpermill page: How the fields of a card are grouped into sections, each with a plain-language description.
   The key is where the fields sit: a card's name ('style', 'characters', 'world', 'outline') or a list inside one
   ('outline.chapter_beats'), the same dotted path the editor uses. Each section lists the field names it holds, in the
   order they are drawn. A field no section names goes in a last "Other" section, so nothing is ever hidden. Titles and
   descriptions are English here and go through t(); the Chinese is in i18n_zh.js. */
const SECTIONS = {
  style: [
    {
      t: "Who is telling the story",
      keys: ["label", "pov", "tense"],
      d: 'Choose who is speaking and when. Point of view is whose eyes we see the story through: "I" (first person), or "she" or "he" staying close to one character (third person). Tense is whether events are told as already over (past) or as they happen (present).',
    },
    {
      t: "Perspective",
      keys: ["lens", "stance", "interiority"],
      d: "How the narrator takes in the world. The lens is what it notices and what it never registers. Stance is its attitude toward events. Interiority is how far it goes inside the main character's mind. Write a few words in each box, or pick a suggestion below it.",
    },
    {
      t: "Language",
      keys: ["economy", "diction", "figurative"],
      d: "The words themselves: how much language each moment gets, how plain or ornate the words are, and how much metaphor there is.",
    },
    {
      t: "Rhythm and manner",
      keys: ["cadence", "humor", "dialogue_manner", "time_handling"],
      d: "How the narration moves: the feel of its sentences, whether and how it is funny, how speech is written down, and how it treats time inside a chapter.",
    },
    {
      t: "Narrator",
      keys: ["narrator"],
      d: "One paragraph that blends every choice above into a single way of perceiving the world. This is the description the chapter writer reads, so edit it directly if the narrator does not sound right to you.",
    },
    {
      t: "Signature moves and off-limits",
      keys: ["signature_moves", "off_limits"],
      d: "Signature moves are devices this narrator uses again and again that a reader would recognise. Off-limits lists what the narration must never do. Leave it empty if there is nothing to rule out.",
    },
    {
      t: "Sample passages",
      keys: ["exemplars"],
      d: "Short passages that show the narrator at work. Write them about ordinary situations, not about your plot.",
    },
  ],
  characters: [
    {
      t: "Who they are",
      keys: ["name", "role", "presence"],
      d: "What to call them, how they would be introduced to a stranger, and how they carry themselves. Write them so they would hold in any story: nothing here should depend on this plot.",
    },
    {
      t: "What drives them",
      keys: ["want", "wound", "blind_spot"],
      d: "Want is what they chase and the fear underneath it. Wound is what happened to them long ago and the rule about the world it taught them. Blind spot is how they see themselves, set against the thing they do that contradicts it.",
    },
    {
      t: "Under pressure",
      keys: ["armor", "tell", "limits"],
      d: "Armor is how they meet conflict and keep people away. The tell is what pressure does to their body, a repeated motion any setting could supply an object for. Limits are what they will never do, and what it would take to make them.",
    },
    {
      t: "With people and in speech",
      keys: ["with_people", "soft_spot", "voice"],
      d: "How they handle others and what they hold back, what gets past their armor, and how they talk. Give each character a different way of speaking.",
    },
  ],
  world: [
    {
      t: "The place and what it costs",
      keys: ["setting", "pressure"],
      d: "Setting is where and when, and what an ordinary day is like; it may carry one past event that people still live under. Pressure is what living here costs: what is scarce, forbidden or owed, and who feels it.",
    },
    {
      t: "How things work here",
      keys: ["rules"],
      d: "Short statements, each a mechanic or custom plus what it makes people do or give up. A rule with no price attached is not worth keeping.",
    },
    {
      t: "Places",
      keys: ["locations"],
      d: "The settings where scenes happen. For each, say what the place does to people: who belongs there and who does not, what is done or hidden there.",
    },
    {
      t: "Objects and groups",
      keys: ["objects", "groups"],
      d: "Objects are things people want, fear or have paid for, with who holds them and where they are now. Groups are factions or organizations: how they are felt in daily life, and what they want.",
    },
    {
      t: "Secrets",
      keys: ["hidden_truths"],
      d: "Facts that are true in your world but have not appeared on the page yet. For each, say who is guarding it and what exposure would cost, and choose which characters already know it. Readers learn a secret when a chapter reveals it.",
    },
  ],
  outline: [
    {
      t: "The story's core",
      keys: ["premise", "protagonist", "opposition", "theme", "ending"],
      d: "Premise is the story in one or two sentences: who wants what, what stands in the way, and what winning or losing would cost. Protagonist is the one character the story follows. Opposition is what stands against them and what it wants; a person with a want of their own works better than a vague force. Theme is the choice the story forces, two good things set against each other; no character ever says it aloud. Ending is the answer to the story's central question and what it cost, as a concrete situation.",
    },
    {
      t: "People and arcs",
      keys: ["relationships", "arcs", "leave_open"],
      d: 'A relationship pairs two characters and says what lies between them: a debt, a lie, a grievance, a hunger. An arc is how a person ends up, paired with something they do or say that shows it, what forces the change and what it costs them. "Leave open" lists questions you want the story to deliberately never answer.',
    },
    {
      t: "Length and chapter plan",
      keys: ["total_chapters", "shape", "chapter_beats"],
      d: "How many chapters the whole story has, fixed from the start. Shape says where hope, a false win, the low point, the peak and the coda fall, with chapter numbers, rising and falling rather than climbing steadily. Only the chapter you are working on has a plan; the next is planned after it is written.",
    },
  ],
  "outline.chapter_beats": [
    {
      t: "Scene",
      keys: ["chapter_num", "when", "location", "present", "opening"],
      d: "When and where the chapter starts, who is there, and the first thing that happens on the page: someone already doing or saying something.",
    },
    {
      t: "Conflict and action",
      keys: ["goal", "obstacle", "agendas", "events", "ends_on"],
      d: "What the main character wants in this chapter, and what runs up against it, best of all another person's competing want. Agendas say what each other person present is after or hiding. Events are the few things that happen in order, each a shift in who has the upper hand. Ends on is the situation the chapter stops on.",
    },
    {
      t: "What changes",
      keys: ["turn", "direction"],
      d: "One sentence on what is true at the end that was not true at the start, and whether the chapter leaves the main character better off, worse off, or both.",
    },
    {
      t: "Planting and payoff",
      keys: ["plants", "pays_off", "reveals"],
      d: "A plant is something shown now that a later chapter uses again; a payoff is that later use. Reveals are the secrets from the World card that come out in this chapter.",
    },
  ],
};
