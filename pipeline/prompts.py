"""
Prompt 模板库：支持理工科（STEM）和文科（Humanities）两类书籍。
所有生成内容均为简体中文。
"""

# ─── 课程目录生成 Prompt ──────────────────────────────────────────────────────

CURRICULUM_PROMPT_STEM = """\
请根据笔记本中上传的《{book_title}》的内容，生成完整的三级知识点目录。

严格按照以下 JSON 格式输出，不要输出任何其他内容：
[
  {{
    "id": "ch01",
    "title": "第一章 ...",
    "sections": [
      {{
        "id": "ch01_s01",
        "title": "1.1 ...",
        "topics": [
          {{"id": "ch01_s01_t01", "title": "..."}},
          {{"id": "ch01_s01_t02", "title": "..."}}
        ]
      }}
    ]
  }}
]

规则：
- 章 ID：ch01, ch02 … 补充章用 sup01, sup02 …
- 节 ID：ch01_s01, ch01_s02 …
- 知识点 ID：ch01_s01_t01, ch01_s01_t02 …
- 每节 2~5 个知识点，聚焦：定义/定理/推导/计算方法/典型例题
- 涵盖书中所有章节
- 全部使用简体中文
- 只输出合法 JSON 数组，不加任何说明文字\
"""

CURRICULUM_PROMPT_HUMANITIES = """\
请根据笔记本中上传的《{book_title}》的内容，生成完整的三级阅读要点目录。

严格按照以下 JSON 格式输出，不要输出任何其他内容：
[
  {{
    "id": "ch01",
    "title": "第一章 ...",
    "sections": [
      {{
        "id": "ch01_s01",
        "title": "1.1 ...",
        "topics": [
          {{"id": "ch01_s01_t01", "title": "..."}},
          {{"id": "ch01_s01_t02", "title": "..."}}
        ]
      }}
    ]
  }}
]

规则：
- 章 ID：ch01, ch02 … 补充章用 sup01, sup02 …
- 节 ID：ch01_s01, ch01_s02 …
- 知识点 ID：ch01_s01_t01, ch01_s01_t02 …
- 每节 2~5 个要点，聚焦：核心概念/主要论点/历史背景/典型案例/批判性思考
- 涵盖书中所有章节
- 全部使用简体中文
- 只输出合法 JSON 数组，不加任何说明文字\
"""

# ─── 视频讲解 Prompt ──────────────────────────────────────────────────────────

VIDEO_PROMPT_STEM = """\
请用简体中文，为《{book_title}》中的知识点「{topic_title}」生成一段详细的讲解视频：

1. 概念引入：从直观背景出发，说明为什么需要研究这个概念
2. 定义与定理：给出规范的数学/科学定义，陈述关键定理
3. 推导过程：完整展示证明或推导步骤，不跳步，公式清晰
4. 典型例题：用 1~2 个具体数值例题演示应用方法
5. 核心总结：提炼关键 takeaway 和常见错误

要求：语言清晰，公式完整，whiteboard 风格，适合理工科自学。\
"""

VIDEO_PROMPT_HUMANITIES = """\
请用简体中文，为《{book_title}》中的要点「{topic_title}」生成一段深度讲解视频：

1. 背景导入：介绍该话题的时代背景和研究缘起
2. 核心观点：梳理作者的主要论点和论证结构
3. 关键概念：解释重要术语，对比不同流派的界定方式
4. 典型案例：结合具体事例或文本段落加以说明
5. 批判思考：指出该观点的价值、局限，以及相关争议
6. 延伸阅读：推荐 1~2 个关联知识点

要求：逻辑清晰，引用准确，适合文科深度阅读与思辨。\
"""

# ─── 测试题 Prompt ────────────────────────────────────────────────────────────

QUIZ_PROMPT_STEM_FREE = """\
请用简体中文，为《{book_title}》中的知识点「{topic_title}」出 10 道练习题：
- 第 1~7 题：基础巩固题（概念辨析、简单计算、判断正误）
- 第 8~10 题：综合拔高题（推导、证明思路、规律推广）

每题格式：
1. 题干清晰，含 A/B/C/D 四个选项
2. 标注正确答案
3. 提供 1~2 句简要解析（说明原理）\
"""

QUIZ_PROMPT_STEM_PRO = """\
请用简体中文，为《{book_title}》中的知识点「{topic_title}」出 13 道练习题：
- 第 1~10 题：基础巩固题（概念辨析、简单计算、判断正误）
- 第 11~13 题：综合拔高题（严格推导、综合论证、难题变型）

每题格式：
1. 题干清晰，含 A/B/C/D 四个选项
2. 标注正确答案
3. 提供 1~2 句简要解析（说明原理和步骤）\
"""

QUIZ_PROMPT_HUMANITIES_FREE = """\
请用简体中文，为《{book_title}》中的要点「{topic_title}」出 10 道阅读理解题：
- 第 1~7 题：基础理解题（概念辨析、观点判断、事实核实）
- 第 8~10 题：分析拔高题（论点评析、比较对比、应用迁移）

每题格式：
1. 题干清晰，含 A/B/C/D 四个选项
2. 标注正确答案
3. 提供 1~2 句简要解析（指向文本依据或逻辑依据）\
"""

QUIZ_PROMPT_HUMANITIES_PRO = """\
请用简体中文，为《{book_title}》中的要点「{topic_title}」出 13 道阅读理解题：
- 第 1~10 题：基础理解题（概念辨析、观点判断、事实核实）
- 第 11~13 题：综合拔高题（批判性评析、跨章节联系、现实应用）

每题格式：
1. 题干清晰，含 A/B/C/D 四个选项
2. 标注正确答案
3. 提供 1~2 句简要解析（指向文本或论证依据）\
"""



# ─── 音频概述 Prompt ──────────────────────────────────────────────────────────

AUDIO_PROMPT_STEM = """\
请用简体中文，为《{book_title}》中的知识点「{topic_title}」录制一段“演示文稿解说”风格的播客音频：

内容结构：
1. 开场白：用一句话点出幻灯片的主题和核心意义（30秒内）
2. 图文导读：假定听众正在浏览幻灯片，用生活类比和生动语言逐步解释每一页的重点
3. 关键推导摘要：口述关键的逻辑推导和图表走势，不要干瘪地读符号
4. 留白思考：提出一个引发思考的问题，给听众 10 秒停顿
5. 总结收尾：用一句话帮听众合上这趟演示旅程

风格：演讲式、生动有趣，就像站在大屏幕前的专业级名师在配合 PPT 为学生讲解。\
"""

AUDIO_PROMPT_HUMANITIES = """\
请用简体中文，为《{book_title}》中的要点「{topic_title}」录制一段“演示文稿解说”风格的音频播客：

内容结构：
1. 开场引导：以幻灯片第一页抛出的核心争议或现实问题引入话题
2. 逐页解构：配合假定的演示幻灯片页面，生动讲述作者的核心论点和时代背景
3. 深度讨论：如同大师讲坛一样，模拟对这套幻灯片中所展示观点的不同回应
4. 留白思考：提出一个值得听众看着大屏幕独立去判断的思想实验或问题
5. 延伸建议：通过最后一页给出一个可供深入阅读的关联主题

风格：沉浸式讲座风格，娓娓道来，配合想象中的画面引发共鸣。\
"""

# ─── 学习报告 Prompt ──────────────────────────────────────────────────────────

REPORT_INSTRUCTIONS_STEM = """\
请用简体中文，为《{book_title}》中的知识点「{topic_title}」生成一份完整的学习指南：

包含：
- 核心概念速览（定义 + 关键公式）
- 知识点思维框架（前置知识 → 本节 → 后续应用）
- 易错点与常见误区（至少3个）
- 5道自测练习题（含答案）
- 推荐复习步骤\
"""

REPORT_INSTRUCTIONS_HUMANITIES = """\
请用简体中文，为《{book_title}》中的要点「{topic_title}」生成一份阅读简报：

包含：
- 核心观点摘要（3~5句话）
- 关键概念词汇表（术语 + 简明解释）
- 论证结构图示（主张 → 论据 → 结论）
- 批判性问题清单（至少3个值得质疑的地方）
- 相关延伸阅读推荐\
"""

# ─── 闪卡 Prompt ─────────────────────────────────────────────────────────────

FLASHCARD_PROMPT_STEM = """\
请用简体中文，为《{book_title}》中的知识点「{topic_title}」生成 15 张学习闪卡：

格式：正面（问题或术语）/ 背面（简明答案或定义）

内容分布：
- 5张：核心定义与定理（正面：术语名，背面：标准定义）
- 5张：推导关键步骤（正面：下一步是什么？背面：完整步骤）
- 5张：应用判断（正面：在此情境下应用什么方法？背面：方法和原因）\
"""

FLASHCARD_PROMPT_HUMANITIES = """\
请用简体中文，为《{book_title}》中的要点「{topic_title}」生成 15 张阅读闪卡：

格式：正面（问题）/ 背面（简洁答案）

内容分布：
- 5张：关键概念（正面：术语，背面：定义和出处）
- 5张：作者主要论点（正面：作者如何看待X？背面：核心观点）
- 5张：批判性思考（正面：这个观点有什么局限？背面：批判性分析）\
"""

# ─── 信息图 Prompt ─────────────────────────────────────────────────────────────

INFOGRAPHIC_PROMPT_STEM = """\
请用简体中文，为《{book_title}》中的知识点「{topic_title}」生成一份信息图：
突出核心逻辑流程、因果关系或系统架构，用精简的文字和清晰的结构梳理内容。\
"""
INFOGRAPHIC_PROMPT_HUMANITIES = """\
请用简体中文，为《{book_title}》中的要点「{topic_title}」生成一份信息图：
展示核心思想的演变、主题之间的网状关联，或是时间线图景，用生动的形式呈现。\
"""

# ─── 数据表格 Prompt ───────────────────────────────────────────────────────────

DATATABLE_PROMPT_STEM = """\
请用简体中文，为《{book_title}》中的知识点「{topic_title}」生成一份数据表格：
重点列出公式参数列表、对比参数、测量数据或是常见模型之间的优劣属性对比。\
"""
DATATABLE_PROMPT_HUMANITIES = """\
请用简体中文，为《{book_title}》中的要点「{topic_title}」生成一份数据表格：
用表格对比不同流派、历史分期事件、或是核心概念的多个唯独辨析。\
"""


# ─── 获取对应 Prompt 的辅助函数 ──────────────────────────────────────────────

BOOK_TYPES = {
    "stem": {
        "label": "理工科（数学/物理/化学/计算机等）",
        "curriculum": CURRICULUM_PROMPT_STEM,
        "video": VIDEO_PROMPT_STEM,
        "audio": AUDIO_PROMPT_STEM,
        "report": REPORT_INSTRUCTIONS_STEM,
        "flashcard": FLASHCARD_PROMPT_STEM,
        "infographic": INFOGRAPHIC_PROMPT_STEM,
        "datatable": DATATABLE_PROMPT_STEM,
        "quiz_free": QUIZ_PROMPT_STEM_FREE,
        "quiz_pro": QUIZ_PROMPT_STEM_PRO,
    },
    "humanities": {
        "label": "文科（历史/哲学/文学/社科等）",
        "curriculum": CURRICULUM_PROMPT_HUMANITIES,
        "video": VIDEO_PROMPT_HUMANITIES,
        "audio": AUDIO_PROMPT_HUMANITIES,
        "report": REPORT_INSTRUCTIONS_HUMANITIES,
        "flashcard": FLASHCARD_PROMPT_HUMANITIES,
        "infographic": INFOGRAPHIC_PROMPT_HUMANITIES,
        "datatable": DATATABLE_PROMPT_HUMANITIES,
        "quiz_free": QUIZ_PROMPT_HUMANITIES_FREE,
        "quiz_pro": QUIZ_PROMPT_HUMANITIES_PRO,
    },
}


def get_prompts(book_type: str) -> dict:
    """返回指定书籍类型的 Prompt 集合"""
    return BOOK_TYPES.get(book_type, BOOK_TYPES["stem"])


def select_book_type() -> str:
    """交互式选择书籍类型，返回 'stem' 或 'humanities'"""
    print("\n── 选择书籍类型 ──────────────────────────────────")
    for key, info in BOOK_TYPES.items():
        idx = list(BOOK_TYPES.keys()).index(key) + 1
        print(f"  [{idx}] {info['label']}")
    print()
    keys = list(BOOK_TYPES.keys())
    while True:
        c = input("请选择（1/2）：").strip()
        try:
            idx = int(c) - 1
            if 0 <= idx < len(keys):
                chosen = keys[idx]
                print(f"  ✓ 已选择：{BOOK_TYPES[chosen]['label']}")
                return chosen
        except ValueError:
            pass
        print("  请输入有效编号")

