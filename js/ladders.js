/* Pulpermill page: The wording of the five levels of each style dial (economy, diction, figurative, interiority, humor).
   This is a fallback copy so the sliders look right even before the backend has answered (or when it is an older version).
   The backend's /schema sends the same text as `ladders`, and when it does, that copy is the one used. If a level's wording is
   changed in pulpermill/schema/style.py (LADDERS), change it here too. Each entry is [name, description]; level 1 is first. */
const DIAL_LADDERS = {
  "economy": [
    [
      "Clipped",
      "Each moment gets the least language that carries it: one beat, one detail at most, then the next. Anything that doesn't move the scene or reveal the character is left out."
    ],
    [
      "Spare",
      "A few chosen details per moment, stated briefly, and then on. The prose moves faster than the events feel."
    ],
    [
      "Measured",
      "Each moment gets enough language to ground it: what is seen, what is done, what it costs. Neither rushed nor lingered over."
    ],
    [
      "Full",
      "Moments are given room. Detail is allowed to build up, and a scene can stay on a gesture, a room or a pause before moving on."
    ],
    [
      "Expansive",
      "Scenes are built out slowly and abundantly. The narration takes its time over setting, bodies, objects and small shifts, and is happy to give a single moment a whole paragraph."
    ]
  ],
  "diction": [
    [
      "Plain",
      "Everyday words a child could follow, and short ones where there is a choice. Nothing obscure, no showy vocabulary, and no word that makes the reader stop."
    ],
    [
      "Simple",
      "Mostly everyday words, with the occasional precise or less common one when it is the right word. Easy to read without effort."
    ],
    [
      "Balanced",
      "Ordinary and exact words side by side. The vocabulary is neither plain nor showy, and it stays natural to the narrator."
    ],
    [
      "Literary",
      "A wider, more deliberate vocabulary. Words are chosen for connotation and sound as well as sense, and less common words are welcome when they fit."
    ],
    [
      "Ornate",
      "Rich, elaborate, elevated language. Rare, archaic or learned words and formal phrasing are used freely, and the prose is meant to be savored as well as followed."
    ]
  ],
  "figurative": [
    [
      "Literal",
      "No metaphor or simile. Things are described as they are, and the narration states what happens directly."
    ],
    [
      "Sparing",
      "An image appears only when plain description would not carry it, and then briefly. Most pages have none."
    ],
    [
      "Occasional",
      "A figure of speech now and then, usually short and drawn from the story's own world. Plain description does most of the work."
    ],
    [
      "Frequent",
      "Images are a normal part of how things are described. Several appear in a scene, and they are expected to do work, not decorate."
    ],
    [
      "Rich",
      "Figurative language runs through the narration. Metaphor and simile are how the narrator sees, so scenes are described through comparison more often than through direct statement."
    ]
  ],
  "interiority": [
    [
      "Behaviorist",
      "The narration records only what can be seen and heard: actions, objects, speech. What the character thinks or feels is never stated, only shown through what they do."
    ],
    [
      "Restrained",
      "Thoughts and feelings are given only rarely and briefly, mostly through a physical sign or a short, flat remark. The reader infers most of what the character feels."
    ],
    [
      "Filtered",
      "The narration passes through the character's mind. It reports what they notice, think and feel in the narrator's own words, enough to follow them but not at length."
    ],
    [
      "Open",
      "Feelings and thoughts are stated openly and are a regular part of the page. The reader is told what the character wants, fears and makes of what happens."
    ],
    [
      "Stream of thought",
      "The narration is the character's own mind: associations, interruptions, half-formed thoughts and memories surface as they come, and the line between what happens and what they think is thin."
    ]
  ],
  "humor": [
    [
      "None",
      "The narration is in earnest throughout, with no jokes and no irony played for laughs."
    ],
    [
      "Rare",
      "Wit appears only occasionally, as a dry aside or a small ironic turn, and the story stays serious around it."
    ],
    [
      "Present",
      "A light vein of humor runs through the narration: wry observations and small ironies. It does not take over serious moments."
    ],
    [
      "Frequent",
      "Humor is a regular part of how the narrator speaks. Many paragraphs have a joke, an absurd comparison or a deflating aside, and it can sit beside serious events."
    ],
    [
      "Pervasive",
      "The narration is comic as a default. Almost everything is seen through a joke, an exaggeration or an absurdity, even in dark moments."
    ]
  ]
};
