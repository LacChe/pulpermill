/* Pulpermill page: the Simplified Chinese table (English text -> Chinese), plain data. ZH is the page text, PYD the backend validation messages. */
const ZH = {
  Pulpermill: "Pulpermill",
  "Backend URL (ngrok)": "后端地址(ngrok)",
  "Test connection": "测试连接",
  "Story name": "故事名称",
  my_story: "我的故事",
  Language: "语言",
  Stop: "停止",
  "Stopping…": "正在停止…",
  "Export story (.md)": "导出故事(.md)",
  Story: "故事",
  story: "故事",
  "Checking…": "检查中…",
  Connected: "已连接",
  "Connected ({model})": "已连接({model})",
  "Failed: {why}": "失败:{why}",
  words: "字",
  "This may take a few minutes.": "这可能需要几分钟。",
  Progress: "进度",
  "Writing the card": "正在生成卡片",
  "Trying again (attempt {n})": "正在重试(第{n}次)",
  "Example chapter (optional)": "示例章节(可选)",
  "Paste a chapter from any story to give the model something to work from. Each card below has its own switch for using it. The limit shown is the tightest of the cards that use it, and the chapter counts against each of their limits.":
    "粘贴任意故事中的一章,给模型一个参考。下面每张卡片都有各自的开关,决定是否使用它。显示的上限取使用示例章节的卡片中最紧的一张,章节会计入这些卡片各自的上限。",
  "another story in the same world, running alongside this one":
    "发生在同一世界、与此并行的另一个故事",
  "carries on after this chapter": "接着本章继续往下写",
  "Use the example chapter for this card": "这张卡片使用示例章节",
  "(paste an example chapter above first)": "(请先在上方粘贴示例章节)",
  "Add notes for this card first, or switch the example chapter on for it.":
    "请先为这张卡片添加笔记,或为它打开示例章节。",
  "Add notes for this card, or paste an example chapter above.":
    "请为这张卡片添加笔记,或在上方粘贴一章示例。",
  "Rewrite with note": "按备注重写",
  "What should change in this chapter? (optional)": "这一章要改什么?(可选)",
  "Note for rewriting the chapter": "重写本章的备注",
  "Rewrite chapter {k} with your note? The new version replaces this one.":
    "按你的备注重写第{k}章?新版本会替换当前版本。",
  "Your note: {note}": "你的备注:{note}",
  Setup: "开篇",
  Spark: "触发",
  Friction: "阻力",
  Shift: "转折",
  Peak: "高潮",
  Aftermath: "尾声",
  "(none)": "(无)",
  "(choose one)": "(请选择)",
  "{v} (not on the cards)": "{v}(卡片中没有)",
  "hidden truth": "隐藏真相",
  "broken link": "链接失效",
  "broken links: {n}": "失效链接:{n}",
  "This needs a {kind}. Available: {known}":
    "这里需要填写一个{kind}。可用:{known}",
  "Not a {kind} on the cards: {v}. Available: {known}":
    "卡片中没有这个{kind}:{v}。可用:{known}",
  "{where}: needs a {kind}": "{where}:需要填写{kind}",
  '{where}: "{v}" is not a {kind} on the cards':
    "{where}:“{v}”不是卡片中的{kind}",
  "These fields point at something that no longer exists:":
    "以下字段指向已不存在的内容:",
  "Broken links between cards ({n}). Fix the highlighted fields before writing.":
    "卡片之间有 {n} 处链接失效。请先修复标出的字段再撰写。",
  "The cards this one is built from have broken links ({n}). Fix the highlighted fields first.":
    "此卡片所依据的卡片有 {n} 处链接失效。请先修复标出的字段。",
  "The cards have broken links ({n}). Fix the highlighted fields before writing chapter {k}.":
    "卡片有 {n} 处链接失效。请先修复标出的字段,再撰写第{k}章。",
  "Updated after each chapter": "每章结束后更新",
  "One shape is handed to each chapter in turn, the least-used first. Empty is fine: the model then decides how each chapter opens and closes.":
    "每章按顺序分到一种结构,优先使用次数最少的。留空也可以:此时由模型自己决定每章如何开头和收尾。",
  "Planning the next chapter": "正在规划下一章",
  "What is the example for?": "示例章节用来做什么?",
  "Same story": "同一个故事",
  "the cards describe the example's own story":
    "各卡片描述的就是示例章节本身的故事",
  "Continue after it": "接着它写",
  "New story in the same world": "同一世界里的新故事",
  "Characters in this chapter": "本章的角色",
  "Choose up to {n}. The model only writes about these people, and the main character is always one of them.":
    "最多选 {n} 位。模型只会写这些人,主角一定在其中。",
  "main character": "主角",
  "in the chapter beat": "在本章要点中",
  "{n} of {max} chosen": "已选 {n} / {max}",
  "The beat for this chapter includes {names}, who are not chosen. Writing will plan the beat again for the people you chose.":
    "本章要点里包含 {names},但他们没有被选中。写作时会按你选的人重新规划本章要点。",
  "A generation writes up to {n} characters. Add as many as you like and choose up to {m} for each chapter.":
    "一次生成最多写 {n} 位角色。你可以添加任意多的角色,每章最多选 {m} 位。",
  "Planning this chapter": "正在规划本章",
  "Starts empty; filled in as the story goes": "起初为空,随故事推进自动填写",
  Chapters: "章节",
  "Chapter {k}": "第{k}章",
  Ending: "结局",
  "After chapter {k}": "第{k}章之后",
  "Writing…": "撰写中…",
  " · out of date": " · 已过期",
  " · cards changed": " · 卡片已改动",
  "Ready to write": "可以撰写",
  "Setting up the cards": "正在准备卡片",
  Ready: "就绪",
  "Save project": "保存项目",
  "Load project": "载入项目",
  "Reset everything…": "全部重置…",
  "Confirm reset": "确认重置",
  "This erases every card, note and chapter in this browser. Save the project first if you want to keep it.":
    "这会清除此浏览器中的所有卡片、笔记和章节。如果想保留,请先保存项目。",
  Cancel: "取消",
  "Erase everything": "全部清除",
  "Chapter {k} cards": "第{k}章卡片",
  "Ending cards": "结局卡片",
  "Import cards": "导入卡片",
  "Export cards": "导出卡片",
  "Generate the four cards in order and check each one, or import them. Then write the chapter.":
    "按顺序生成四张卡片并逐一检查,或直接导入。然后撰写章节。",
  "The cards as chapter {j} left them. The story has no chapter {k}, so there is nothing more to write. Edit or export them, or raise Total chapters on the Setup card to keep going.":
    "这是第{j}章结束时的卡片。故事没有第{k}章,所以没有更多内容可写。你可以编辑或导出这些卡片,也可以在“开篇”卡片中调高“章节总数”以继续。",
  "These are the cards as chapter {j} left them. Edit anything you like before writing chapter {k}; changed fields are marked.":
    "这是第{j}章结束时的卡片。撰写第{k}章之前可以随意修改;改动过的字段会被标出。",
  "Chapter {j} is out of date (an earlier chapter was rewritten), so these cards may not match what came before.":
    "第{j}章已过期(之前的某一章被重写过),因此这些卡片可能与前文不符。",
  "These cards changed after chapter {k} was written. Rewrite the chapter to apply the changes.":
    "第{k}章写完之后这些卡片又改动过。重写该章即可应用这些改动。",
  "Write chapter {k}": "撰写第{k}章",
  "Rewrite chapter {k}": "重写第{k}章",
  Starting: "正在开始",
  "Generate all four cards first.": "请先生成全部四张卡片。",
  "Write chapter {j} first.": "请先撰写第{j}章。",
  "What chapter {k} has to cover": "第{k}章要写的内容",
  "Opens at {loc}, {when}. Events:": "开场于{loc},{when}。事件:",
  "Rewrite chapter {k}? The new version replaces this one.":
    "重写第{k}章?新版本会取代当前版本。",
  "Confirm rewrite": "确认重写",
  "When it finishes, the cards it ends with can replace the ending cards. Only one version of those cards is kept, so if you want to keep the current ones, export them before you generate.":
    "完成后,本章结束时的卡片可以替换结局卡片。这些卡片只保留一个版本,所以如果想保留当前这一份,请在生成之前先导出。",
  "When it finishes, the cards it ends with can replace chapter {n}'s starting cards. Only one version of those cards is kept, so if you want to keep the current ones, export them before you generate.":
    "完成后,本章结束时的卡片可以替换第{n}章的起始卡片。这些卡片只保留一个版本,所以如果想保留当前这一份,请在生成之前先导出。",
  "Export the ending cards": "导出结局卡片",
  "Export chapter {n}'s starting cards": "导出第{n}章的起始卡片",
  "Rewrite and replace them": "重写并替换它们",
  "Rewrite and keep them": "重写并保留它们",
  "Imported: {items}.": "已导入:{items}。",
  "Nothing was imported.": "没有导入任何内容。",
  "Not imported or changed:": "未导入或未改动的内容:",
  "Consistency notes on the cards now on this page:": "此页面卡片的一致性提示:",
  "Undo this import": "撤销此次导入",
  Dismiss: "关闭",
  "Example chapter": "示例章节",
  "Paste one chapter here.": "在这里粘贴一章。",
  "Built from an earlier version of a previous card":
    "基于前一张卡片的旧版本生成",
  "Ready to check": "待检查",
  "Changed since the last chapter": "较上一章有改动",
  "Up to {n} chapters.": "最多 {n} 章。",
  "{card} notes": "{card}笔记",
  "Your notes for this card": "这张卡片的笔记",
  "Optional extra direction for this card. Leave blank to infer it all from the chapter.":
    "这张卡片的可选额外指示。留空则完全根据章节推断。",
  "Generating…": "生成中…",
  "Generate {what}": "生成{what}",
  "Generate {what} first.": "请先生成{what}。",
  "Check these:": "请留意:",
  "What should change? (optional)": "需要改什么?(可选)",
  "Note for regeneration": "重新生成的备注",
  "Regenerate with note": "按备注重新生成",
  Style: "文风",
  Characters: "角色",
  World: "世界观",
  "How the narration sounds. Built from your input with no names or plot.":
    "叙述的语气和腔调。根据你的输入生成,不含人名和情节。",
  "The whole cast in one pass, written to be different from each other.":
    "一次生成全部角色,彼此各不相同。",
  "Setting, rules, hidden truths, places, objects and groups.":
    "背景设定、规则、隐藏真相、地点、物品和团体。",
  "Premise, ending, arcs and the opening beat. The story continues from here, one chapter at a time.":
    "故事前提、结局、角色弧线和开篇要点。故事从这里开始,逐章继续写下去。",
  "How should the narration sound? What kind of narrator is telling this, and what attitude does it take toward events (humor, if any)? Do they comment or stay quiet? How do they handle feelings? What rhythm, how much dialogue? What would ruin it?":
    "叙述听起来应该是什么样?讲述者是怎样的人,对事件抱什么态度(如果有幽默,是哪种)?他会评论还是保持沉默?怎样处理感情?节奏如何,对话占多少?什么会毁掉它?",
  "For each person: what they want, how they see themselves versus what they actually do, how they talk, their habits, and how they feel about each other person. Say exactly who did what to whom.":
    "对每个人物:他们想要什么,自我认知与实际行为有何差距,说话方式,习惯,以及对其他每个人的感受。请明确写出谁对谁做了什么。",
  "The place and occasion, how it works as plain fact (one line per mechanic), the places, the objects that matter, and the secrets: what is true, who knows it, who does not.":
    "地点与场合,它如何运作的客观事实(每条规则一行),各个地点,重要的物品,以及秘密:真相是什么,谁知道,谁不知道。",
  "Chapter by chapter: where, whose point of view, what each person wants and is hiding, what goes wrong, how it ends. What must be planted early and pay off later. What the ending looks like concretely, and what stays unresolved.":
    "逐章写明:在哪里,谁的视角,每个人想要什么、隐瞒什么,哪里出了问题,如何收尾。哪些要早早埋下、之后回收。结局具体是什么样,哪些事保持悬而未决。",
  "Chapter {k} story": "第{k}章故事",
  "Out of date: an earlier chapter was rewritten":
    "已过期:之前的某一章被重写过",
  "Cards changed since": "此后卡片有改动",
  "Cards not updated": "卡片未更新",
  "The version below is replaced when this finishes.":
    "完成后将替换下面的版本。",
  "Chapter {k} has not been written yet. Once you write it, the story appears here.":
    "第{k}章尚未撰写。写完之后,故事会显示在这里。",
  "Characters who appear without a card:": "出现但没有角色卡的人物:",
  "This chapter changed nothing in the cards": "本章没有改动任何卡片",
  "What this chapter changed in the cards": "本章对卡片做出的改动",
  " (dropped from the card: {items})": "(已从卡片中移除:{items})",
  "Download chapter (.md)": "下载本章(.md)",
  "Chapter {j} was the last chapter of the story, so there is no more story to write. The cards on the left are how it ended.":
    "第{j}章是故事的最后一章,没有更多故事可写。左侧的卡片就是故事结束时的状态。",
  "Writing the chapter: about {n} words · {clock}":
    "正在撰写本章:约 {n} 字 · {clock}",
  "The model keeps writing until the chapter reaches a natural ending.":
    "模型会一直写到本章自然收尾为止。",
  "last run: {d}": "上次用时 {d}",
  "{s}s": "{s}秒",
  "{m}m {s}s": "{m}分{s}秒",
  "Writing the chapter": "正在撰写本章",
  "Reading the chapter for changes to the cards":
    "正在阅读本章,提取对卡片的改动",
  "Summarizing the chapter": "正在总结本章",
  Working: "处理中",
  "Stopping… waiting for the backend to confirm it is ready":
    "正在停止…等待后端确认已就绪",
  "The chapter is already written. Stopping now throws it away. Stop anyway?":
    "本章已经写完。现在停止会丢弃它。仍要停止吗?",
  "Could not reach the backend to stop it ({why}).":
    "无法连接后端来停止({why})。",
  "Your project is using about {pct}% of the autosave space this browser allows. Use Save project to keep a copy before it fills up.":
    "你的项目已占用浏览器自动保存空间的约 {pct}%。请用“保存项目”保留一份副本,以免空间用尽。",
  "Your saved project could not be read, so the page started empty. The unreadable text is kept in this browser as pmcg_project_unreadable.":
    "已保存的项目无法读取,页面已从空白开始。无法读取的原文已保存在此浏览器中,名称为 pmcg_project_unreadable。",
  "Your saved project could not be read, and no copy could be kept (browser storage is full). The page started empty.":
    "已保存的项目无法读取,也无法保留副本(浏览器存储空间已满)。页面已从空白开始。",
  "{name}: is too large to import ({size} KB; the limit is {max} KB).":
    "{name}:文件太大,无法导入({size} KB;上限为 {max} KB)。",
  "Too many files: only the first {max} of {n} were read.":
    "文件过多:只读取了前 {max} 个(共 {n} 个)。",
  "The backend did not answer within {s} seconds.": "后端在 {s} 秒内没有响应。",
  "Lost contact with the backend. Retrying… (a running job keeps going there)":
    "与后端失去联系,正在重试……(正在运行的任务会在后端继续)",
  "Lost contact with the backend for too long. The chapter may still finish there: reload this page once the connection is back to pick it up.":
    "与后端失联时间过长。章节可能仍在后端完成:连接恢复后请重新加载此页面以继续接收。",
  "Lost contact with the backend for too long, so this card was not received. Check the backend, then generate it again.":
    "与后端失联时间过长,未能收到这张卡片。请检查后端,然后重新生成。",
  "Stopped. Nothing from this attempt was kept.":
    "已停止。这次尝试没有保留任何内容。",
  "Stopped before it finished. Nothing was changed.":
    "未完成就被停止了。没有任何改动。",
  "Enter the backend URL first.": "请先输入后端地址。",
  "Backend returned {status}: {body}": "后端返回 {status}:{body}",
  "Too much text for this card: {used} characters ({ch} of them the example chapter), and the model can take {limit} here. Shorten the {what}.":
    "这张卡片的文本过多:共 {used} 个字符(其中 {ch} 个来自粘贴的章节),而模型在这里最多能处理 {limit} 个。请缩短{what}。",
  "Too much text for this card: {used} characters, and the model can take {limit} here. Shorten the {what}.":
    "这张卡片的文本过多:共 {used} 个字符,而模型在这里最多能处理 {limit} 个。请缩短{what}。",
  "example chapter": "示例章节",
  notes: "笔记",
  "Clear the {card} card for chapter {k}? Your notes for it stay, so you can generate it again from scratch.":
    "要清空第{k}章的{card}卡片吗?你为它写的备注会保留,之后可以从头重新生成。",
  "used {n}×": "已用 {n} 次",
  "How many chapters this was handed to the writer in. The least-used items are handed over next.":
    "已有多少章把它交给了写作模型。下一章会优先交出用得最少的条目。",
  "Remove “{name}” from this card? This cannot be undone.":
    "要从这张卡片中删除“{name}”吗?此操作无法撤销。",
  "Clear card": "清空卡片",
  "Remove this card so it can be generated again from scratch. Your notes stay.":
    "移除这张卡片,以便从头重新生成。你的备注会保留。",
  "Regenerate the {card} card for chapter {k}? It replaces the card as it stands on this page.":
    "要为第{k}章重新生成{card}卡片吗?它会替换此页面上现有的卡片。",
  "the ending cards": "结局卡片",
  "chapter {k}'s cards": "第{k}章的卡片",
  "The cards were not updated, so {what} were left as they were.":
    "卡片没有更新,因此{what}保持原样。",
  "You edited {what} while this chapter was being written, so your edits were kept and the new ending cards were not applied.":
    "本章撰写期间你修改了{what},所以保留了你的修改,没有应用新的结局卡片。",
  "That is not a Pulpermill project file.": "这不是 Pulpermill 项目文件。",
  "This project has no pages.": "此项目没有任何页面。",
  "This project file is damaged.": "此项目文件已损坏。",
  "This file does not contain a project.": "此文件不包含项目。",
  "That file is not valid JSON.": "该文件不是有效的 JSON。",
  "Wait for the current generation to finish before loading a project.":
    "请等当前生成结束后再载入项目。",
  "Loading replaces everything on the page. Continue?":
    "载入会替换页面上的所有内容。要继续吗?",
  "Autosave failed (browser storage is full). Use Save project to keep your work.":
    "自动保存失败(浏览器存储空间已满)。请用“保存项目”保存你的工作。",
  "{name}: could not be read ({why})": "{name}:无法读取({why})",
  "{name}: is not valid JSON ({why})": "{name}:不是有效的 JSON({why})",
  "The backend could not check these cards, so nothing was imported ({why}). Test the connection and try again.":
    "后端无法检查这些卡片,因此没有导入任何内容({why})。请测试连接后重试。",
  "(empty)": "(空)",
  "was: {old}": "原为:{old}",
  " (one per line)": "(每行一项)",
  new: "新增",
  changed: "已改动",
  "Item {k}": "第 {k} 项",
  "Remove this item": "删除此项",
  "Add item": "添加一项",
  "{n} characters (test the connection to see the limit)":
    "{n} 个字符(测试连接后可看到上限)",
  "{n} / {limit} characters (about {w} words)": "{n} / {limit} 个字符",
  "the card text is not written in {language}. Rewrite every text value of the card in {language}, keeping the JSON keys and fixed option values as they are":
    "卡片文字不是用{language}写的。请把卡片里每一项文字都改用{language}重写,JSON 键和固定选项值保持不变。",
  "move {obj}": "移动 {obj}",
  "chapter {n}: it reveals '{truth}', which is not one of your hidden truths, so that reveal was left out":
    "第{n}章:它揭示了“{truth}”,但这不是你的隐藏真相之一,因此略去了这条揭示",
  "the main character '{who}' is not in your cast, so {name} was used; check the setup":
    "主角“{who}”不在你的角色表里,因此改用了{name};请检查开篇卡片",
  "the main character '{who}' is not in the cast": "主角“{who}”不在角色表里",
  "chapter {n}: '{place}' was not in your World, so it was added to the World card; fill in its description":
    "第{n}章:“{place}”不在你的世界观里,因此已加入世界观卡片;请补上它的描述",
  nobody: "无人",
  character: "角色",
  location: "地点",
  "chapter numbers are not 1..{n} in sequence: {nums}":
    "章节序号不是按 1..{n} 顺序排列的:{nums}",
  "chapter {n} ('{text}')": "第{n}章(“{text}”)",
  "(nothing)": "(无)",
  "after chapter {n} the story's {what} was changed. Now: {new} Before: {old}":
    "第{n}章之后,故事的{what}已被修改。现在:{new} 之前:{old}",
  "chapter {n} may repeat chapter {k}; check its beat":
    "第{n}章可能与第{k}章重复;请检查它的要点",
  "character arcs": "角色弧线",
  ending: "结局",
  premise: "故事前提",
  "reason given for the changes after chapter {n}: {why}":
    "第{n}章之后修改的原因:{why}",
  theme: "主题",
  "things left open": "保持悬而未决的事项",
  "group_updates: unknown group '{group}'": "group_updates:未知的群体“{group}”",
  "location_updates: unknown location '{place}'":
    "location_updates:未知的地点“{place}”",
  "object_updates: unknown object '{obj}'": "object_updates:未知的物品“{obj}”",
  "{name} changed: {text}": "{name}发生了变化:{text}",
  "{name} dropped a habit: {text}": "{name}改掉了一个习惯:{text}",
  "{name} now wants: {text}": "{name}现在想要:{text}",
  "{name} picked up a habit: {text}": "{name}养成了一个习惯:{text}",
  "{name}: the habit '{text}' is not on the card, so it was not dropped":
    "{name}:卡片上没有“{text}”这个习惯,因此没有删除",
  "{name}'s want changed: {text}": "{name}想要的东西变了:{text}",
  "{name}'s blind spot changed: {text}": "{name}的盲点变了:{text}",
  "a chapter can be about at most {max} characters, the main character included; {n} were chosen":
    "每章最多写 {max} 位角色(含主角);你选了 {n} 位",
  "The beat for chapter {n} named people who are not in this chapter's cast, so it was written again for the cast you chose.":
    "第{n}章的要点里有不在本章角色名单中的人,因此已按你选择的角色重新写了一遍。",
  "chapter {n}: more than {max} people were present, so only the first {max} were kept":
    "第{n}章:在场的人超过 {max} 位,因此只保留了前 {max} 位",
  "Chapter {n} had no beat, so one was written now.":
    "第{n}章原本没有章节要点,现已补写。",
  "The beat for chapter {next} could not be written ({why}). It will be written when you start that chapter.":
    "第{next}章的要点没能写出({why})。开始写那一章时会重新生成。",
  "chapter {n}: '{truth}' was already revealed earlier, so it was not revealed again":
    "第{n}章:“{truth}”之前已经揭示过,因此这里没有再次揭示",
  "chapter {n}: the payoff '{text}' matches no plant that is still open, so it was left out":
    "第{n}章:回收项“{text}”对不上任何尚未回收的伏笔,已略去",
  "chapter_count must be a number from 1 to {max}: how many chapters the whole story has":
    "chapter_count 必须是 1 到 {max} 之间的数字:整个故事一共有多少章",
  "the setup has {n} chapter beats but the story has {total} chapters":
    "开篇里有 {n} 章的要点,但故事一共只有 {total} 章",
  "payoffs with no earlier plant: {items}. Plant them earlier or remove them":
    "前面没有伏笔的回收:{items}。请在前文埋下伏笔,或删掉它们",
  "stray markdown asterisks in output": "输出中混入了多余的 Markdown 星号",
  "no beat for chapter {n}": "第{n}章没有章节要点",
  "some chapters have no story stage (1-6); set one on every chapter":
    "有些章节没有故事阶段(1-6);请给每一章都设置一个阶段",
  "story stages go backwards between chapters: {stages}":
    "章节之间的故事阶段出现了倒退:{stages}",
  "the last chapter should be story stage {last} (Aftermath), not {got}":
    "最后一章应为故事阶段 {last}(尾声),而不是 {got}",
  "{label}: unknown {kind} '{value}'": "{label}:未知的{kind}“{value}”",
  "object_moves: unknown object '{obj}'": "object_moves:未知的物品“{obj}”",
  "{obj} is no longer held by {was}": "{obj}不再由{was}持有",
  "{obj} is no longer at {was}": "{obj}不再位于{was}",
  "reveals: unknown truth '{truth}'": "reveals:未知的真相“{truth}”",
  "character_updates: unknown character '{who}'":
    "character_updates:未知的角色“{who}”",
  "object {id}: unknown owner '{who}'": "物品 {id}:未知的持有者“{who}”",
  "object {id}: unknown location '{where}'": "物品 {id}:未知的地点“{where}”",
  "arc: unknown character '{who}'": "角色弧线:未知的角色“{who}”",
  "ch{n}: unknown location '{where}'": "第{n}章:未知的地点“{where}”",
  "ch{n}: the main character '{who}' is not in present":
    "第{n}章:主角“{who}”不在在场人物中",
  "{truth} is revealed in chapters {where}; reveal each hidden truth once":
    "{truth}在第 {where} 章被揭示;每条隐藏真相只应揭示一次",
  "{name}: feelings toward '{other}' were dropped, because nobody in the cast has that name":
    "{name}:对“{other}”的态度已被去掉,因为角色表里没有叫这个名字的人",
  "object '{obj}': the owner '{who}' is not in the cast, so its owner was left empty":
    "物品“{obj}”:持有者“{who}”不在角色表里,因此持有者留空",
  "object '{obj}': the place '{place}' is not one of your locations, so its location was left empty":
    "物品“{obj}”:地点“{place}”不在你的地点列表里,因此所在地点留空",
  "hidden truth {n}: {names} is not in the cast, so left out of who knows it":
    "隐藏真相 {n}:{names}不在角色表里,因此没有计入知情者",
  "hidden truth {n}: {names} are not in the cast, so left out of who knows it":
    "隐藏真相 {n}:{names}不在角色表里,因此没有计入知情者",
  "chapter {n}: '{who}' is not in your cast, so it was left out of {where} (it can still appear in the events)":
    "第{n}章:“{who}”不在你的角色表里,因此没有放进{where}(仍可出现在事件描述中)",
  "'{who}' is not in your cast, so it was left out of {where} (it can still appear in the events)":
    "“{who}”不在你的角色表里,因此没有放进{where}(仍可出现在事件描述中)",
  "{obj} is now held by {who} (was {was})": "{obj}现在由{who}持有(原为{was})",
  "{obj} is now held by {who}": "{obj}现在由{who}持有",
  "{obj} is now at {where} (was {was})": "{obj}现在位于{where}(原为{was})",
  "{obj} is now at {where}": "{obj}现在位于{where}",
  "style mentions character name '{name}'": "文风里提到了角色名“{name}”",
  "{id}: core mentions world id '{wid}'":
    "{id}:核心设定里出现了世界观编号“{wid}”",
  "{id}: toward unknown character '{who}'": "{id}:对未知角色“{who}”的态度",
  "{id}: role is empty. Say what this person is and does in this story; a bare title leaves the model to fill in its own idea of it":
    "{id}:身份为空。请写明这个人在故事里是谁、做什么;只写一个头衔会让模型自己去想象",
  "{id}: role is one word ('{role}'). Say what this person is and does in this story; a bare title leaves the model to fill in its own idea of it":
    "{id}:身份只有一个词(“{role}”)。请写明这个人在故事里是谁、做什么;只写一个头衔会让模型自己去想象",
  "{a} and {b} have the same sample line: '{line}'":
    "{a}和{b}有相同的台词示例:“{line}”",
  "{id}: unknown known_by '{who}'": "{id}:未知的知情者“{who}”",
  "ch{n}: unknown character '{who}'": "第{n}章:未知的角色“{who}”",
  "ch{n}: reveals unknown truth '{truth}'": "第{n}章:揭示了未知的真相“{truth}”",
  "{name}: an attitude toward themselves was dropped":
    "{name}:对自己的态度已被去掉",
  "{name}'s condition: {text}": "{name}的状态:{text}",
  "the arcs": "角色弧线",
  "{who} now knows: {fact}": "{who}现在知道了:{fact}",
  "the shifts": "变动",
  "the people present": "在场人物",
  "the model could not produce valid output after {n} tries: {why}":
    "模型尝试 {n} 次后仍未能给出有效输出:{why}",
  "the model's reply hit the {limit}-token limit before the JSON was complete, after {n} tries. Try again, or ask for less in one go.":
    "模型的回复在 JSON 写完之前就达到了 {limit} 个 token 的上限(共尝试 {n} 次)。请重试,或一次少要一些内容。",
  "no JSON object found in the reply": "回复中没有找到 JSON 对象",
  "too much input: the prompt is about {need} tokens and the answer needs at least {least}, but the model holds {ctx}. Shorten the notes or the example chapter.":
    "输入过多:提示词约有 {need} 个 token,答案至少还需要 {least} 个,而模型的上限是 {ctx}。请缩短笔记或粘贴的章节。",
  "the style uses '{word}', a name-like word from your input; style should not name story details":
    "文风里用到了“{word}”,这像是你输入中的人名;文风不应出现故事细节",
  "too many characters ({n}); write at most {max}, keeping the ones who matter most":
    "角色过多({n} 个);最多写 {max} 个,保留最重要的",
  "generate the characters first": "请先生成角色",
  "generate the characters and the world first": "请先生成角色和世界观",
  "chapter {n}: state update did not validate after {tries} attempt(s)":
    "第{n}章:尝试 {tries} 次后,状态更新仍未通过校验",
  "chapter {n}: the state update hit the {limit}-token limit before it was complete, after {tries} attempt(s)":
    "第{n}章:状态更新在写完之前就达到了 {limit} 个 token 的上限(尝试 {tries} 次)",
  "too much to send: chapter {n}'s prompt is {prompt} tokens, which leaves {room} for writing, and a {target}-word chapter needs about {need}. Lower the target word count or shorten the cards.":
    "要发送的内容过多:第{n}章的提示词有 {prompt} 个 token,留给写作的只有 {room} 个,而 {target} 字的章节大约需要 {need} 个。请降低目标字数或缩短卡片。",
  "missing cards: {names}": "缺少卡片:{names}",
  "the story has {total} chapter(s); there is no chapter {n}":
    "故事共有 {total} 章,没有第{n}章",
  "chapter {n} needs the text of chapter {prev}": "第{n}章需要第{prev}章的正文",
  "The chapter stopped at the length limit, so its ending may be cut off.":
    "本章在达到长度上限时停止,结尾可能被截断了。",
  "Copied from a card, word for word: {what}": "逐字照抄了卡片内容:{what}",
  "State update skipped: {why}": "已跳过的状态更新:{why}",
  "the cards do not validate: {why}": "卡片未通过校验:{why}",
  "chapter {n} needs {k} earlier summary, got {got}":
    "第{n}章需要 {k} 份之前的章节摘要,实际收到 {got} 份",
  "chapter {n} needs {k} earlier summaries, got {got}":
    "第{n}章需要 {k} 份之前的章节摘要,实际收到 {got} 份",
  "The cards were NOT updated for this chapter ({why}). Edit the next chapter's starting cards by hand.":
    "本章没有更新卡片({why})。请手动修改下一章的起始卡片。",
  "{name}'s sample line: {line}": "{name}的台词示例:{line}",
  "style exemplar: {line}": "文风范例句:{line}",
  "an object": "一个对象",
  "a list": "一个列表",
  text: "文本",
  "a number": "一个数字",
  "true/false": "真/假",
  null: "空值",
  style: "文风",
  characters: "角色",
  world: "世界观",
  setup: "开篇",
  "too many problems to repair": "问题太多,无法修复",
  "{label}: character #{n}": "{label}:第 {n} 个角色",
  "expected an object, found {kind}": "应为对象,实际是{kind}",
  "{label}: character #{n} ({name})": "{label}:第 {n} 个角色({name})",
  "{label}: ignored unrelated field(s): {fields} (+{n} more)":
    "{label}:忽略了无关字段:{fields}(另有 {n} 个)",
  "{label}: ignored unrelated field(s): {fields}":
    "{label}:忽略了无关字段:{fields}",
  "{tag} is {kind}, not an object; skipped": "{tag}是{kind},不是对象;已跳过",
  "{tag}: had no id, so it was given '{id}'": "{tag}:没有编号,已分配“{id}”",
  "{tag}: not imported ({why})": "{tag}:未导入({why})",
  "{tag}: id '{id}' is already used by an earlier character; skipped":
    "{tag}:编号“{id}”已被前面的角色使用;已跳过",
  "...and {n} more": "……另有 {n} 条",
  "{name}: '{kind}' should be an object, found {found}; skipped":
    "{name}:“{kind}”应为对象,实际是{found};已跳过",
  "{name}: a {kind} card was already given in {src}; using this one instead":
    "{name}:{src}中已经给出了{kind}卡片;改用这一份",
  "{name}: ignored unrelated top-level field(s): {fields}":
    "{name}:忽略了无关的顶层字段:{fields}",
  "{name}: expected a JSON object or list, found {kind}; skipped":
    "{name}:应为 JSON 对象或列表,实际是{kind};已跳过",
  "{name}: this is a whole-project file; use Load project to open it. Skipped.":
    "{name}:这是整个项目文件;请用“载入项目”打开。已跳过。",
  "{name}: not recognised as a style, character, world or setup card (its fields: {fields}); skipped":
    "{name}:无法识别为文风、角色、世界观或开篇卡片(它的字段:{fields});已跳过",
  "{name}: {kind}": "{name}:{kind}",
  "No valid characters were found, so the cast was left as it was.":
    "没有找到有效的角色,因此角色表保持原样。",
  "{name}: 'characters' should be a list of characters, found {kind}; skipped":
    "{name}:“characters”应为角色列表,实际是{kind};已跳过",
  "{name}: a character list was already given in {src}; using this one instead":
    "{name}:{src}中已经给出了角色列表;改用这一份",
  "{name}: could not be read as cards ({why}); skipped":
    "{name}:无法作为卡片读取({why});已跳过",
  "{name}: {kind} not imported ({why})": "{name}:{kind}未导入({why})",
  "characters ({n})": "角色({n} 个)",
  "characters ({touched} added or updated, {n} in the cast)":
    "角色(新增或更新 {touched} 个,角色表共 {n} 个)",
  "{label}: dropped {path} ({why})": "{label}:去掉了 {path}({why})",
  "{path}: {why}": "{path}:{why}",
  none: "无",
  "the card": "这张卡片",
  "Another generation is still running on the backend. Wait for it to finish, then try again.":
    "后端还有另一个生成任务在运行。请等它结束后再试。",
  "The model has not responded for {minutes} minutes and cannot be stopped from here. Restart the notebook session, then run its cells again.":
    "模型已经 {minutes} 分钟没有响应,无法从这里停止。请重启笔记本会话,然后重新运行其中的单元格。",
  "The backend ran out of memory. Try again. If it keeps happening, send less text (fewer cards, shorter summaries or a shorter previous chapter), or restart the notebook session.":
    "后端内存不足。请重试。如果仍然出现,请减少发送的文本(更少的卡片、更短的摘要或更短的上一章),或重启笔记本会话。",
  "The GPU reported an error, and the model may not work any more. Try again; if it fails again, restart the notebook session.":
    "GPU 报告了错误,模型可能已无法正常工作。请重试;如果再次失败,请重启笔记本会话。",
  "The model failed while processing the text. Try again; if it fails again, restart the notebook session.":
    "模型在处理文本时失败。请重试;如果再次失败,请重启笔记本会话。",
  "unknown job (did the notebook restart?)": "未知的任务(笔记本是否重启过?)",
  "unknown stage '{stage}'": "未知的阶段“{stage}”",
  "The import failed unexpectedly: {why}": "导入意外失败:{why}",
  "{name}, new lasting change: {text}": "{name},新的持久变化:{text}",
  "{name}, new established detail: {text}": "{name},新确立的细节:{text}",
  arcs: "角色弧线",
  attitude: "态度",
  avoid: "要避免的",
  "blind spot": "盲点",
  "chapter beats": "章节要点",
  "chapter num": "章节序号",
  "chapter shapes": "章节结构",
  "total chapters": "章节总数",
  turn: "本章转变",
  protagonist: "主角",
  condition: "当前状态",
  description: "描述",
  end: "终点",
  "ends on": "结尾落点",
  events: "事件",
  exemplars: "范例句",
  fact: "事实",
  goal: "目标",
  groups: "团体",
  habits: "习惯",
  "hidden truths": "隐藏真相",
  history: "过往",
  id: "编号",
  "known by": "知情者",
  label: "标签",
  "leave open": "保持开放",
  locations: "地点列表",
  look: "外貌",
  list: "列表",
  movement: "变化",
  name: "名称",
  objects: "物品",
  obstacle: "阻碍",
  owner: "持有者",
  "pays off": "回收",
  plants: "伏笔",
  pov: "视角",
  present: "在场人物",
  "prose habits": "行文习惯",
  "recent changes": "近期变化",
  "recent details": "近期细节",
  reveals: "揭示",
  role: "身份",
  rules: "规则",
  "sample lines": "台词示例",
  setting: "背景设定",
  shifts: "变动",
  stage: "阶段",
  tense: "时态",
  uses: "已用次数",
  tone: "基调",
  toward: "对待",
  voice: "口吻",
  want: "渴望",
  wants: "诉求",
  when: "时间",
  wrap: "实时状态",
  "option first person": "第一人称",
  "option third limited": "第三人称限知",
  "option third omniscient": "第三人称全知",
  "option past": "过去时",
  "option present": "现在时",
  "Motivation & history": "动机与过往",
  Presentation: "外在表现",
  Relationships: "人物关系",
  "Export this character": "导出这个角色",
  "Export this card": "导出这张卡",
  added: "已添加",
  'Mixing and matching between stories: each character has its own "Export this character" button on the Characters card. Importing one character file only adds or updates that person — the rest of the cast is left alone.':
    '在故事之间混搭：角色卡上的每个角色都有自己的"导出这个角色"按钮。导入单个角色文件只会新增或更新那一个人，其余角色不受影响。',
  /* section titles and descriptions (sections.js) */
  "Who is telling the story": "谁在讲这个故事",
  'Choose who is speaking and when. Point of view is whose eyes we see the story through: "I" (first person), or "she" or "he" staying close to one character (third person). Tense is whether events are told as already over (past) or as they happen (present).':
    "选择由谁来讲、在什么时间讲。视角是我们透过谁的眼睛看这个故事:“我”(第一人称),或者“她”“他”紧贴着某一个角色(第三人称)。时态是事情被讲成已经发生过(过去时),还是正在发生(现在时)。",
  "How the narrator sounds": "叙述者的声音",
  "Describe the narrator's personality: calm or sarcastic, chatty or stiff, serious or funny. The sample passages show that voice at work, so write them about ordinary situations, not about your plot.":
    "描述叙述者的性格:冷静还是讽刺,健谈还是拘谨,严肃还是风趣。范例段落用来展示这种口吻,所以请写日常的场景,不要写你的情节。",
  "Writing rules": "写作规则",
  "Concrete rules a reader could check on the page, such as short sentences or little description of the weather, and a list of habits the writing must never show.":
    "读者能在文字中直接检查的具体规则,比如句子要短、少写天气描写,以及行文绝不能出现的习惯。",
  "Chapter shapes": "章节结构",
  "Templates for how a single chapter is built: how it opens, how it closes, how much is dialogue. They describe structure only, never plot.":
    "一章如何搭建的模板:怎样开头、怎样收尾、对话占多少。它们只描述结构,从不涉及情节。",
  "Who they are": "他们是谁",
  "The basics: what to call them, what job or place they have in the story, and a few physical details a reader would notice.":
    "基本信息:叫什么名字,在故事里担任什么工作或处于什么位置,以及读者会注意到的几处外貌细节。",
  "What drives them": "驱动他们的是什么",
  "A want is something concrete they are actively chasing. A blind spot is a flaw they cannot see in themselves, such as someone who believes they are honest but keeps lying to themselves. History is past events that still shape how they act today.":
    "渴望是他们正在积极追求的具体目标。盲点是他们自己看不到的缺陷,比如一个自认诚实、却一直在欺骗自己的人。过往是至今仍在影响他们行为的旧事。",
  "How they act and speak": "他们的行为与说话方式",
  "What they do again and again, especially when nervous or lying, and how they talk. Give each character a different way of speaking, so the example lines should sound like them and no one else.":
    "他们反复做的事,尤其是紧张或撒谎时,以及他们怎么说话。每个角色的说话方式要不同,所以台词示例应该只像他们自己。",
  "How they feel about others": "他们如何看待别人",
  "One entry for each person they have a stake in: what they want from that person and how they act around them.":
    "对每一个与他们利害相关的人写一条:他们想从对方那里得到什么,以及在对方面前怎么表现。",
  "Where they are now": "他们现在的状态",
  "This fills in as the story goes. You normally do not need to edit it.":
    "这部分会随着故事推进自动填写,通常不需要你修改。",
  "Setting and rules": "背景与规则",
  "The time and place, and what counts as normal there. Rules are plain facts about how this world works (laws, limits, mechanics), stated as settled fact, not as writing advice.":
    "时间和地点,以及那里什么算正常。规则是关于这个世界如何运转的朴素事实(法律、限制、机制),按既定事实来写,不是写作建议。",
  Places: "地点",
  "The settings where scenes happen. A few concrete sensory details for each (what it looks, sounds and smells like) are enough.":
    "场景发生的地方。每处写几个具体的感官细节(看起来、听起来、闻起来是什么样)就够了。",
  "Objects and groups": "物品与团体",
  "Objects are things that matter to the plot, with who holds them and where they are. Groups are factions or organizations; only say what a group wants if it affects the story.":
    "物品是对情节重要的东西,写明谁拿着、放在哪里。团体是派系或组织;只有当它的诉求会影响故事时,才写它想要什么。",
  Secrets: "秘密",
  "Facts that are true in your world but have not appeared on the page yet. They steer the story from behind the scenes, and you choose which characters already know each one. Readers learn a secret when a chapter reveals it.":
    "在你的世界里为真、但尚未在文中出现的事实。它们在幕后推动故事,你来选择哪些角色已经知道。读者会在某一章揭示它时才得知。",
  "The story's core": "故事的核心",
  "Premise is the story in one or two sentences: who wants what, and what goes wrong. Protagonist is the one character the story follows. Theme is the idea underneath, a condition that must be met before things can change; no character ever says it aloud. Ending is what is concretely true at the close, not just what people have learned.":
    "故事前提是用一两句话讲清楚的故事:谁想要什么,哪里出了问题。主角是故事始终跟随的那一个角色。主题是藏在底下的想法,是事情发生改变之前必须满足的条件,没有角色会把它说出口。结局是结尾时具体成立的事实,而不只是人们明白了什么。",
  "Character arcs and open questions": "角色弧线与悬而未决的问题",
  'An arc is how a person changes from start to finish, paired with something they do or say that shows it. "Leave open" lists questions you want the story to deliberately never answer.':
    "弧线是一个人从头到尾的变化,并配上能体现这种变化的一个具体言行。“保持开放”列出你希望故事有意不作回答的问题。",
  "Length and chapter plan": "篇幅与章节计划",
  "How many chapters the whole story has, fixed from the start, and the plan for each one. Only the chapter you are working on has a plan; the next is planned after it is written.":
    "整个故事共有多少章(一开始就定下),以及每一章的计划。只有你正在写的这一章有计划;下一章在这一章写完之后再规划。",
  Scene: "场景",
  "When and where the chapter starts, who is there, and what mood it carries.":
    "这一章在何时何地开始,谁在场,带着什么情绪。",
  "Conflict and action": "冲突与行动",
  "What the main character wants in this chapter, what stands in the way, the three to five things that happen in order, and the situation the chapter stops on.":
    "主角这一章想要什么,什么在阻挡他,按顺序发生的三到五件事,以及这一章停在怎样的局面上。",
  "What changes": "发生了什么变化",
  "One sentence on what is true at the end that was not true at the start, which characters visibly change, and how far along the story's six steps the chapter ends: Setup, Spark, Friction, Shift, Peak, Aftermath.":
    "用一句话写出结尾时成立、而开头时不成立的事,哪些角色发生了明显变化,以及这一章结束时故事走到六个阶段的哪一步:开篇、触发、阻力、转折、高潮、尾声。",
  "Planting and payoff": "伏笔与回收",
  "A plant is something shown now that a later chapter uses again; a payoff is that later use. Reveals are the secrets from the World card that come out in this chapter.":
    "伏笔是现在展示、之后某一章会再次用到的东西;回收就是后来的那次使用。揭示是世界卡里的秘密在这一章被说出来。",
  Other: "其他",
  /* card tabs (views.js) */
  Cards: "卡片",
  complete: "已完成",
  generating: "生成中",
};
const PYD = [
  ["^Field required$", "缺少必填项"],
  ["^Input should be a valid string$", "应为文本"],
  ["^Input should be a valid list$", "应为列表"],
  ["^Input should be a valid dictionary or object to validate$", "应为对象"],
  ["^Input should be a valid dictionary$", "应为对象"],
  ["^Input should be a valid integer.*$", "应为整数"],
  ["^Input should be a valid number.*$", "应为数字"],
  [
    "^List should have at least (\\d+) items? after validation, not (\\d+)$",
    "列表至少需要 $1 项,现在只有 $2 项",
  ],
  [
    "^List should have at most (\\d+) items? after validation, not (\\d+)$",
    "列表最多 $1 项,现在有 $2 项",
  ],
  [
    "^String should have at least (\\d+) characters?$",
    "文本至少需要 $1 个字符",
  ],
  ["^Input should be (.+)$", "取值应为 $1"],
  ["^Value error, (.*)$", "$1"],
];
