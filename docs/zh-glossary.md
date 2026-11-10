# Simplified Chinese translation glossary

Written for steps 10 to 15 of the localization plan. Every term below appears in `web/data/text.en.json`, in `pulpermill/schema/text/en/*.yaml` or in `README.md`. A translator needs only this page to translate any one file.

Where one English word has two meanings, the table gives one row per meaning. Never use the same Chinese word for two different things on the same screen.

## Style rules

1. Simplified Chinese only. No Traditional forms, no pinyin.
2. Address the writer as 你, never 您. The model is 模型, never “AI” or “助手”.
3. Full-width punctuation: ，。：；！？、（）. List joiners are 、 or ，; clauses are joined with ；.
4. Quotes are curly: “ ” (inner quotes ‘ ’). Never straight quotes, never 「」.
5. No space between Han and Latin text or digits (`第3章`, `3个人物`), unless the English string already has one around a `{mark}`. Keep the ellipsis `…` and the arrow `→` as they are.
6. Keep `{marks}`, ids, keys, option values, emoji marks (🔒 🔓 ✓ ● △ ✕) and file extensions (`.md`, `.zip`) exactly. A mark may move inside a sentence when Chinese word order needs it.
7. Buttons are two to four characters where possible (`保存`, `打开…`, `模型填写`). A button that is a full action may be longer (`用模型规划第{n}章`).
8. No plural handling. Where the English has a singular and a plural key (for example `characterOne` and `characterMany`), keep both keys and write each in the one natural form (`1个人物`, `{n}个人物`).
9. Chapters are numbered 第{n}章; “{n} of {total}” is 第{n}/{total}章 (or 共{total}章 when that reads better).
10. Prefer words Chinese fiction writers already use (章节, 人物, 世界观, 大纲, 细纲, 主角, 文风, 人称, 视角) over literal translations.
11. Placeholder examples start with 例如：. Rewrite the example itself in Chinese so it reads like a real story, not a literal copy.
12. Model-facing keys (`expand`, `lead_in`, `item_template`, `item_join`, `judge_prompt`) are not translated.

## Terms

### The cards

| English | Chinese | Note |
| --- | --- | --- |
| card | 卡片 | Always 卡片, never 卡 alone in sentences. |
| Style | 文风 | Card name and label. |
| Characters | 人物 | Card name. Use 人物, not 角色. |
| Character | 人物 | One character. |
| World | 世界观 | Card name. |
| Entanglements | 关系网 | Card name: ties and holdings. |
| Setup | 开局 | Card name: who we follow, what broke, how long. |
| Outline | 大纲 | Card name. |
| Shifts | 变动 | The record of what changed. Pipeline-only. |
| Summary: Events | 事件摘要 | Pipeline-only record, one entry per chapter. |
| after-story copy | 结局副本 | The copy made when the story is finished. |

### Story parts

| English | Chinese | Note |
| --- | --- | --- |
| chapter | 章节 | In headings and counts, 第{n}章. |
| beat | 细纲 | One chapter's springboard entry in the Outline. Writers say 细纲 for the per-chapter outline. |
| plan (noun) | 方案 | The beat's “Plan” field and “the plan”. |
| plan (verb) | 规划 | Buttons and progress: 规划第{n}章. |
| protagonist | 主角 | Never 主人公 or 男/女主. |
| cast | 出场人物 | Who is on stage in a chapter. |
| spotlight | 聚焦 | Field label and “spotlight tie” (聚焦关系). |
| pressure | 压力 | Field “World pressure” is 世界压力. |
| tie | 关系 | A directed connection; never 联系. |
| bond | 纽带 | The standing label of a tie, e.g. “owes her since the fire”. |
| edge (of a tie) | 所求 | What the tie makes “from” want. Not 边缘. See the Style row for the other “Edge”. |
| holding | 持有 | Who holds or controls a thing or place. The group label is 持有. |
| Normal | 日常 | Setup field: the protagonist's ordinary life. |
| Disruption | 变故 | Setup field: an event that broke the normal. |
| Chapter count | 章数 | Setup field. |
| place | 地点 | World item. |
| thing | 物件 | World item (“Things”). |
| group (World “Groups”) | 势力 | World item with power. |
| rule | 规则 | World rule. A card “rule” in checks is also 规则; context tells them apart. |
| vocabulary | 术语 | World item: term and meaning. |
| aim | 目标 | “What the protagonist is after”: 主角这一章想要的。 |
| outcome / planned ending | 预定结局 | The beat's planned ending of a chapter. |

### Character and World fields

| English | Chinese | Note |
| --- | --- | --- |
| Identity | 身份 | Character group. |
| Drive | 驱动力 | Character group. |
| Inner conflict | 内心冲突 | Character group. |
| Texture | 特质 | Character group. |
| Past | 过往 | Character group. |
| Name | 名字 | Field label. |
| Age | 年龄 | |
| Sex | 性别 | Options 女 / 男 / 其他. |
| Appearance | 外貌 | |
| Sketch | 速写 | A short character sketch. |
| Wants / Want | 渴望 | |
| Fear | 恐惧 | |
| Flaw | 缺陷 | |
| Values / Value | 价值观 | |
| Behaviors | 行为模式 | “When … they …” pairs: 当…时 / 他们会…. |
| Competence | 擅长 | |
| Vulnerability | 软肋 | |
| Speech | 说话方式 | |
| History | 过往 (Character), 历史 (World) | Two meanings, two words. |
| Overview | 概览 | World group. |
| Era and technology | 时代与科技 | |
| Everyday life | 日常生活 | |
| What it does to people | 对人的影响 | Place field. |
| Why it matters | 为何重要 | Thing field. |
| What it is | 是什么 | Group field. |
| How it holds power | 如何掌权 | Group field. |
| How people feel it | 人们的感受 | Group field. |
| Statement / Cost / When broken | 内容 / 代价 / 被打破时 | Rule fields. |
| Term / Meaning | 词语 / 含义 | Vocabulary fields. |

### Style card fields and options

Chinese has no verb tense. Keep the setting and name it 时态 with the options 过去时 and 现在时, and describe the effect in the help text.

| English | Chinese | Note |
| --- | --- | --- |
| Narration | 叙述 | Style group. |
| Narrator | 叙述者 | Style group. |
| Sentences and words | 句式与用词 | Style group. |
| Stance | 立场 | Style group (not the Attitude field). |
| Dialogue | 对话 | Style group. |
| Genre and lens | 类型与视角 | Style group. |
| Person | 人称 | Options 第一人称 / 第三人称. |
| Tense | 时态 | See the note above. |
| Distance | 叙述距离 | Options 外部 / 贴近 / 深入. |
| Humor | 幽默 | Options 无 / 冷幽默 / 荒诞 / 黑色幽默. |
| Pacing | 叙事节奏 | Options 舒缓 / 张弛有度 / 紧凑. |
| Rhythm | 句式节奏 | Options 简短 / 错落 / 绵长. Not the same word as Pacing. |
| Diction | 措辞 | Options 朴素 / 华丽. |
| Register | 语体 | Options 书面 / 口语. |
| Imagery | 意象 | Options 直白 / 偶尔 / 浓烈. |
| Edge (Style field) | 语言尺度 | Options 干净 / 粗粝. Not 所求; that is the tie's edge. |
| Explicitness | 描写尺度 | Options 含蓄 / 直白呈现. |
| Attitude | 态度 | Options 郑重 / 温暖 / 戏谑 / 嘲讽 / 冷静客观 / 忧郁 / 惊叹. |
| Amount | 对话量 | Options 少 / 多. |
| Directness | 表达方式 | Options 直说 / 潜台词. |
| Polish | 修饰程度 | Options 自然 / 风格化. |
| Voice difference | 声音差异 | Options 各具特色 / 统一. |
| Lens | 视角 | A habit of attention, e.g. 留意谁欠谁、东西值多少钱. |
| Genre | 类型 | Examples such as noir or cozy mystery are translated into familiar Chinese genre names (黑色悬疑, 治愈系推理). |
| note (a free-text field, as in “Narrator note”) | 备注 | “Narrator note” is 叙述者备注. |

### Page and workflow

| English | Chinese | Note |
| --- | --- | --- |
| project | 项目 | |
| Design (column) | 设计 | Left workspace column. |
| Write (column) | 写作 | Right workspace column. |
| Guide | 指南 | |
| Welcome | 欢迎 | |
| Fill | 填写 | Button “Fill with the model” is 模型填写. |
| Validate | 校验 | The card's own checks. |
| Check (connection button) | 检测 | Tests the model address. Not the same word as Validate. |
| Generate | 生成 | Used for “stops generation” (阻止生成). Writing a chapter is 写作 / 写第{n}章. |
| Judge | 评判 | The model's check of a rule; the heading “The model's opinion” is 模型的意见. |
| style fit | 文风契合 | The check that the protagonist suits the voice. |
| lock | 锁定 | Also 已锁定; unlock is 解锁. Keep 🔒 and 🔓. |
| fixed (never changes) | 固定 | Tag: 始终不变. |
| live (changes as the story runs) | 随故事变化 | Tag. |
| example chapter | 示例章节 | “Shared by every card”: 所有卡片共用. |
| note (your rough notes for a card) | 笔记 | The writer's notes sent to the model. Not 备注. |
| Model draft | 模型草稿 | Tag on filled fields. |
| stale | 已过期 | Badge: a beat that may no longer fit. |
| written | 已写 | Chapter badge. |
| model connection | 模型连接 | |
| access token | 访问令牌 | |
| backend | 后端 | |
| sample model / mock | 内置示例模型 | The built-in model that writes placeholder text. |
| Stop | 停止 | |
| Save | 保存 | |
| Open | 打开 | “Open…” is 打开…. |
| Import | 导入 | “Import card…” is 导入卡片…. |
| Export | 导出 | |
| Download | 下载 | |
| Undo | 撤销 | |
| Cancel | 取消 | |
| Continue | 继续 | |
| Delete | 删除 | |
| Add | 添加 | “+ Add” is + 添加. |
| Clear choice | 清除选择 | |
| Start the story | 开始故事 | The step that locks the cards. |
| Finish the story | 完结故事 | The step that makes the after-story copy. |

### Severities

| English | Chinese | Note |
| --- | --- | --- |
| warning (warn) | 提醒 | Advice only. Label “Worth a look” is 值得看看. Never 警告, which sounds stronger than it is. |
| block | 阻止生成 | The card cannot generate until fixed. Label “Stops generation” is 阻止生成. |
| reject | 拒绝 | The value cannot be stored. |

## Reserved terms (not in the current text files)

“Knowledge” appears in `pulpermill/schema/CONVENTIONS.md` as a planned card. If it reaches the text files, use 认知 (what a character knows or believes), and keep it apart from 知识.

## Stays English on purpose

`Pulpermill`, `JSON`, `Markdown` (written `Markdown 文件`), `ngrok`, model names, the typed word `mock`, `localhost:8000`, and the marker `FLAG ME`. In the sentence “Type “mock”, or something like localhost:8000” keep the typed values exactly.

## Words the writer already knows

Use these as they are: 章节, 人物, 世界观, 大纲, 细纲, 主角, 文风, 人称, 视角, 设定, 草稿. Where a literal translation sounds like software (for example “条目” for “entry”), choose the word a fiction writer would use.
