# 多语种词形还原（Lemmatization）开源项目调研

覆盖语种：英语 `en`、德语 `de`、法语 `fr`、西班牙语 `es`、韩语 `ko`、日语 `ja`、俄语 `ru`。

调研方式：以项目官方 README / 官方文档 / 仓库内容为准（不采用二手博客）。每条结论后的 `[n]` 为来源编号，见文末「来源」。
标注约定：**✅ 已验证**（来源直接陈述）、**≈ 推断**（由来源事实推得，来源未直接陈述）、**? 未知**（未找到一手来源，不应据此决策）。

---

## 1. 摘要（TL;DR）

这 7 个语种实际分成两类，不能用一个方案通吃：

| 类型 | 语种 | 词形还原的含义 | 主流可行方案 |
| --- | --- | --- | --- |
| **屈折语**（词形变化丰富，但词边界清晰） | `en` `de` `fr` `es` `ru` | 把屈折形式映射到词典原形 | 词典查表 + 规则；或 UD 序列标注模型 |
| **黏着语 / 无空格分词** | `ja` `ko` | 「lemma」等价于形态素分析后的辞书形 / 語彙素 | 必须先做形态素分析，lemma 是其副产品 |

**关键发现：没有任何一个主流「词典 + 多语」词形还原库覆盖 `ja` / `ko`。**

- Simplemma 支持 54 种语言，语言表中**没有** `ja` / `ko` / `zh`。[1]
- `michmech/lemmatization-lists` 覆盖 25 种语言，同样**没有** `ja` / `ko`。[11]
- FreeLing 的 `data/` 目录实际只有 15 种语言，**没有** `ja` / `ko`。[19]

所以一个真正可用的多语种 pipeline 至少需要两个后端：拉丁/西里尔字母语种走查表或 UD 模型，日语/韩语走各自的分词器（Sudachi/MeCab、Kiwi/Khaiii）。

若要「7 语种全覆盖 + 可离线 + 依赖轻」，推荐组合：

| 语种 | 首选 | 备选 / 升级路径 |
| --- | --- | --- |
| en | LemmInflect（95.6%）[8] 或 spaCy `rule` [2] | Stanza / UDPipe（上下文消歧） |
| de | Simplemma（0.97）[1] | spaCy `lookup` ≈ [2]、IWNLP [10]、Stanza / UDPipe |
| fr | Simplemma（0.96）[1] | spaCy `rule` [2]、Stanza / UDPipe / FreeLing |
| es | Simplemma（0.96）[1] | spaCy `rule` [2]、FreeLing、Stanza / UDPipe |
| ru | **pymorphy3**（形态分析器，强于查表）[12][13] | Simplemma（0.94）[1]、Natasha [13]、Stanza / UDPipe |
| ja | **SudachiPy** `dictionary_form()` [18] | MeCab + 词典 [17]、Janome [21] |
| ko | **Kiwi / kiwipiepy** [16] | Khaiii [17b]、mecab-ko |

---

## 2. 四条技术路线

| 路线 | 原理 | 代表项目 | 优点 | 代价 |
| --- | --- | --- | --- | --- |
| **A. 词典查表（lookup）** | `form → lemma` 静态映射表 | Simplemma [1]、`lemmatization-lists` [11]、spaCy `lookup` [2]、IWNLP [10] | 极快、无模型、可离线 | 无法消歧（一词多 lemma 只能给一个），未登录词退化 |
| **B. 规则 / 有限状态（rule, FST）** | 词尾规则 + 词性条件 + 不规则表 | spaCy `rule` [2]、GermaLemma [9]、FreeLing [19]、Apertium [20] | 体积小、可解释 | 规则维护成本高，通常需要词性输入 |
| **C. UD 序列标注（trainable tagger）** | 在 CoNLL-U 上训练 token 级 lemma 分类器 | Stanza [3]、UDPipe [4][5]、Trankit [7]、spaCy `EditTreeLemmatizer` [2] | 上下文消歧、语种覆盖最广 | 需下载模型（数十~数百 MB）、CPU 推理慢 |
| **D. 神经 / Transformer** | 多语预训练 + adapter / 语言模型 | Trankit（XLM-R large）[7]、Kiwi 的 CoNg 模型 [16] | 精度最高 | 体积、算力、（常被忽略的）许可证 |

工程上常见的折中是 **A/B 做默认、C/D 做升级**。Simplemma 的自我定位正是「比神经 pipeline 低几个点、快几百倍」的 baseline。[1]

---

## 3. 跨语种通用工具

### 3.1 纯查表 / 轻量

**Simplemma** — 最贴近「轻量多语种」需求的库。[1]

- 54 种语言，纯 Python 无依赖，安装包 19 MB，无需按语言下载模型。
- 语言表含 `en`(0.96)、`de`(0.97)、`fr`(0.96)、`es`(0.96)、`ru`(0.94)；**不含 `ja`/`ko`**。
- 精度口径：各语言表现最优的通用 UD treebank 的 dev+test，train split 被排除。
- 特性：`greedy` 二次归约（`ausgezeichneten` → `ausgezeichnet` → `auszeichnen`）、多语言链式回退（`lang=('de','en')`）、脚本感知分词器、规则句切分（部分语言带缩写表）、基于词典的语种识别、三档内存模式（~175 MB / `low_memory=True` ~50 MB / trie ~30 MB 每语言）。
- 自述局限：无形态句法信息 → 多 lemma 时无法消歧；派生小称、罕见形式可能缺失。
- 数据是拼装的：`lemmatization-lists`、Kaikki（Wiktionary 打包）、FreeLing、`spacy-lookups-data`、UniMorph、Wikinflection。

**michmech/lemmatization-lists** — 是数据不是工具。`lemma \t token` 两列纯文本（UTF-8 + Windows 换行），ODbL 许可。[11]

| 语种 | 词对数量 | 语种 | 词对数量 |
| --- | --- | --- | --- |
| es | 497,560 | de | 358,473 |
| ru | 537,810 | fr | 224,002 |
| en | 41,760 | | |

共 25 种语言，`ja`/`ko` 不在其中。数据来源：Hunspell 词典（OpenOffice）、Daniel Naber 的德语形态词典、Lexique、Multext-East 中自由许可部分、FreeLing 形态词典、SALDO、OpenRussian 等。

### 3.2 spaCy 的 Lemmatizer 组件 [2]

- 组件名 `lemmatizer`，模式 `lookup`（查表，查不到原样返回）、`rule`（基于 POS 的规则）、`pos_lookup`（需前序 `tagger` 提供 `Token.pos`）；无语言专用实现时默认 `lookup`。
- 默认数据来自 `spacy-lookups-data` 扩展包。
- **各语言默认模式**（官方表格；未列出的语言即用默认 `lookup`）：

| 语言 | 默认模式 | 语言 | 默认模式 |
| --- | --- | --- | --- |
| en | `rule` | it | `pos_lookup` |
| es | `rule` | pl | `pos_lookup` |
| fr | `rule` | ca | `pos_lookup` |
| el | `rule` | nb | `rule` |
| fa | `rule` | nl | `rule` |
| mk | `rule` | sv | `rule` |
| bn | `rule` | **ru** | **`pymorphy3`** |
| | | **uk** | **`pymorphy3`** |

- 表中**没有 `de`**，故德语走默认 `lookup` ≈。
- 俄语/乌克兰语不是查表，而是委派给 pymorphy3——这点对 `ru` 的选型很关键。
- 可训练的替代实现：`EditTreeLemmatizer`（编辑树，训练后小体积）。

### 3.3 UD 生态（CoNLL-U 训练，语种覆盖最广）

**Stanza**（Stanford）[3]

- 60+ 语言，模型覆盖 **UD v2.8 全部 treebank**（README 原话：models for all of the Universal Dependencies treebanks v2.8）。
- tokenizer / MWT 展开 / POS+形态特征 tagger / **lemmatizer** / parser 均可**用 CoNLL-U 数据自训练**。
- Apache-2.0。

**UDPipe**（ÚFAL）[4]

- 定位：「tokenization, tagging, **lemmatization** and dependency parsing of CoNLL-U files」，语种无关，给 CoNLL-U 即可训练；模型覆盖「几乎全部 UD treebank」。
- 交付形态最全：Linux/Windows/OSX 二进制、C++/Python/Perl/Java/C# 库、Web 服务，另有第三方 R CRAN 包。
- **许可证双轨**：代码 MPL-2.0，**语言模型 CC BY-NC-SA（禁止商业使用）**，且部分模型叠加原始数据的附加限制。

**UDPipe 2** [5]

- Python 原型，做 tagging + lemmatization + 语法分析，**不做分词**（输入须是 CoNLL-U）；比 UDPipe 1 更耗算力。
- 源码在 UDPipe 仓库的 `udpipe-2` 分支；模型经 LINDAT REST 服务获取。
- 战绩：CoNLL 2018 UD Shared Task 优胜之一、SIGMORPHON 2019 Shared Task 2 优胜之一、EvaLatin 2020 冠军。

**Trankit** [7]

- 100+ 语言可训练；56 种语言共 90 个预训练 pipeline；XLM-Roberta large + Adapter；Auto Mode 自动语种识别。
- README 明确说「MWT expander 与 **lemmatizer 的实现改编自 Stanza**」，但其列出的支持任务清单（分句/分词/MWT/POS/形态特征/依存/NER）中**没有单列 lemmatization** ?——需要 lemma 输出时应自行确认 API 行为。

### 3.4 传统 NLP 套件

**Stanford CoreNLP** [6]

- `lemma` annotator = `MorphaAnnotator`（依赖 tokens + sentences + POS）。
- 一方语言包：`ar` `zh` `fr` `de` `hu` `it` `es`（均为 4.6.0），但官方能力矩阵中 **Lemma 一行只标注了英语**——非英语语言包的主体是分词/词性/依存/NER。
- 结论：可作 `en` 的 lemma 来源；不宜当作多语 lemma 方案。

**FreeLing**（TALP-UPC）[19]

- 仓库 `data/` 下实际语言目录（一手事实）：`as` `ca` `cs` `cy` `de` `en` `es` `fr` `gl` `hr` `it` `nb` `pt` `ru` `sl` —— 共 15 种。
- 覆盖本调研的 `en` `de` `fr` `es` `ru`；**不含 `ja`/`ko`**。
- 形态分析 + lemma 生成是其传统强项，同时是 `lemmatization-lists` 的数据源之一 [11]。

**Apertium** [20]

- 自由/开源 **RBMT（规则机器翻译）平台**，51 组稳定语言对。
- 对本次调研有用的部分：语言对背后的规则式形态分析词典（含原形），可复用为规则式 lemma 来源。
- 51 组稳定语言对中，与本调研相关的是 `en` `es` `fr` `ru` `uk`（`bel-rus`、`rus-ukr`、`eng-spa`、`fr-es`、`spa-cat` 等）；**稳定对里没有德语、也没有 `ja`/`ko`**（德语语言对可能在其他仓库的开发分支中 ?）。

**NLTK** — `WordNetLemmatizer`（英语，基于 WordNet 词表）。作基线极快（12 µs/lemma），但在 AGID 基准上仅 52.6% [8]。

---

## 4. 各语种专项

### 4.1 英语 `en`

| 项目 | 方法 | 精度（AGID） | 备注 |
| --- | --- | --- | --- |
| **LemmInflect** [8] | 词典（NIH SPECIALIST Lexicon）+ 神经网络判 OOV 词形 | **95.6%** | 42 µs/lemma；唯一依赖 `numpy`；可作 spaCy 扩展（`Token._.lemma()`）；同作者另有 `pyInflect` |
| Stanza 1.5.0 + CoreNLP 4.5.4 [8] | 由 Stanza 调用 CoreNLP 的 Morpha | 95.5% | 30 µs/lemma（全部语料合并为单次调用，JVM 启动开销被摊薄） |
| spaCy 3.5.0 [8] | `rule` | 84.7% | 393 µs/lemma（仅开 lemmatizer） |
| NLTK 3.8.1 [8] | WordNet 查表 | 52.6% | 12 µs/lemma |
| Simplemma [1] | 查表 | 0.96（UD EN-LinES） | 非同一口径，勿与上表直接比 |

> 上表四行精度同出 LemmInflect 自评测，基准 AGID（119,194 个屈折形式，非 gold 但足够广），同一口径下横向可比。

### 4.2 德语 `de`

| 项目 | 方法 | 状态 | 备注 |
| --- | --- | --- | --- |
| **Simplemma** [1] | 查表（1,116k forms → 334k lemmas） | 维护中 | 0.97 on UD DE-GSD，性价比最高 |
| **IWNLP** [10] | 德语 Wiktionary 逆向词典 | 维护中 | 需另下 `IWNLP.Lemmatizer_20181001.zip`；有 spaCy 扩展 `spacy-iwnlp`；论文 ACL-IJCNLP 2015 |
| **GermaLemma** [9] | TIGER lemma 词典 + CLiPS Pattern + 复合词切分 | **已停止维护**（README 首行） | 696 词人工样本 99.43%（同样本 Pattern 95.11%）；只处理 N/V/ADJ/ADV 四类 STTS 标签，其余抛 `ValueError` |
| spaCy `de` [2] | `lookup` ≈ | 维护中 | 德语不在「特殊默认模式」表中 |
| Stanza / UDPipe [3][4] | UD 序列标注 | 维护中 | de 有多个 UD treebank |

德语特有难点是复合词切分（`Feinstaubbelastungen` → `Feinstaubbelastung`）：GermaLemma 内建切分 [9]；Simplemma 的可选复合词切分仍在 roadmap（issue #141）[1]。

### 4.3 法语 `fr`

- spaCy `fr` 默认 `rule` [2]。
- Simplemma：250k forms → 37k lemmas，0.96 on UD FR-Sequoia [1]。
- `lemmatization-lists`：224,002 词对，数据源自 Lexique [11]。
- FreeLing 有 `data/fr` [19]；Stanza / UDPipe 有 UD French 模型 [3][4]。
- 需注意 MWT 展开：`des` 在部分语境应拆成 `de` + `les`，UD 体系的 lemma 是展开后的 [4][7]。查表方案若不处理 MWT，会把 `des` 当成单一词。

### 4.4 西班牙语 `es`

- spaCy `es` 默认 `rule` [2]。
- Simplemma：824k forms → 88k lemmas，0.96 on UD ES-AnCora [1]。
- `lemmatization-lists`：497,560 词对，本调研五个拉丁/西里尔语种中仅次于 `ru` [11]。
- FreeLing 的 `data/es` 是其原生强项 [19]；CoreNLP 有西班牙语语言包 [6]。
- 同样存在 MWT（`del`、`al`），需先处理缩写再查表。

### 4.5 俄语 `ru`

| 项目 | 方法 | 备注 |
| --- | --- | --- |
| **pymorphy3** [12] | 形态分析器（POS + 屈折引擎），非查表 | pymorphy2 的续作（原项目无人维护）；支持 **ru + uk**；Python 3.9–3.14；spaCy 的 ru/uk 直接调用它 [2] |
| **Natasha** [13] | `Doc`/`Token` 流水线，lemma 由 Pymorphy 提供 | 同时给分词（Razdel）、形态（Slovnet）、句法、NER、事实抽取；CPU + Numpy；模型为新闻语料优化，其他领域质量可能下降 |
| Simplemma [1] | 查表（1,362k forms → 131k lemmas） | 0.94 on UD RU-SynTagRus |
| `lemmatization-lists` [11] | 查表 | 537,810 词对，来源含 OpenRussian.org |
| FreeLing [19] / Stanza [3] / UDPipe [4] | 规则 / UD 模型 | 有 `data/ru` 或 ru UD 模型 |

> 俄语是「查表打不过形态分析器」的典型：pymorphy3 有屈折引擎，能对未登录词做范式预测；查表只能覆盖词典内形式。

### 4.6 日语 `ja`

日语没有独立的 lemma 任务——必须先分词为形态素，原形（辞書形 / 語彙素）是形态素属性。

| 项目 | 取原形的 API | 备注 |
| --- | --- | --- |
| **SudachiPy** [18] | `Morpheme.dictionary_form()`，另有 `normalized_form()`、`reading_form()` | 例：`食べ` → `食べる`；词典三档 `small`/`core`(~70 MB)/`full`；**注意 0.6+ 已迁到 Rust 实现 Sudachi.rs**，本仓库只对应 0.5.* |
| **MeCab** [17] | 由输出模板取素性列 | 输出格式完全可重定义：`%H` 为 CSV 素性，`%f[N]` 取第 N 列；**是否存在原形字段取决于词典的字段布局**（`-d unidic` 与 `-d ipadic` 不同） |
| **Janome** [21] | 纯 Python，MeCab-IPADIC 词典 | 其素性输出可见 9 列（品詞×4、活用型、活用形、原形、読み、発音），如 `すもも 名詞,一般,*,*,*,*,すもも,スモモ,スモモ` |
| Stanza / UDPipe [3][4] | UD 序列标注 | UD 有 ja GSD/PUD，故有对应模型 ≈ |

### 4.7 韩语 `ko`

同日语：分词（形态素分析）是前提，lemma 为各形态素的辞书形。

| 项目 | 备注 |
| --- | --- |
| **Kiwi / kiwipiepy** [16] | C++ 内核 + Python API；**세종（Sejong）tagset 改良版**；用户词典（可批量注册活用形、异形态、기분석 形态）；拼写/空格/사이시옷/사투리 处理；`join()` 能把形态素序列还原成表面句（`('길','NNG') ('을','JKO') ('묻','VV') ('어요','EF')` → `길을 물어요`）；0.22+ 默认模型换成 CoNg（上下文 n-gram），x86-64 有优化内核，Apple Silicon 上较慢 |
| **Khaiii** [17b] | Kakao，**CNN** 数据驱动（约 85 万句 / 千万 어절，21 世纪世宗）；Apache-2.0；F-score 96.71(large) / 94.96(base)；内置기분석 사전 + 오분석 패치 两级用户干预 |
| mecab-ko | MeCab 的韩语移植 + `mecab-ko-dic`（KoNLPy 常用后端）? |
| Stanza / UDPipe [3][4] | UD 有 ko GSD/Kaist/PUD，故有模型 ≈ |

> Kiwi 与 Khaiii 的取舍：Kiwi 的形态素可控、能 `join` 回原文、有用户词典与方言支持，Python 侧体验最好；Khaiii 需 C++ 构建环境，但原生速度与精度稳定。

---

## 5. 覆盖矩阵

`✅` = 一手来源明确覆盖；`≈` = 由一手事实推得；`—` = 明确不覆盖；`?` = 未知。

| 工具 | en | de | fr | es | ru | ja | ko | 形态 | 许可证 |
| --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: | --- | --- |
| Simplemma [1] | ✅ | ✅ | ✅ | ✅ | ✅ | — | — | 查表 + 贪心规则 | MIT（数据分源授权） |
| lemmatization-lists [11] | ✅ | ✅ | ✅ | ✅ | ✅ | — | — | 纯数据 | ODbL |
| spaCy [2] | ✅ | ✅≈ | ✅ | ✅ | ✅(pymorphy3) | ? | ? | rule/lookup/pos_lookup | MIT |
| pymorphy3 [12] | — | — | — | — | ✅ | — | — | 形态分析器 | ? |
| Natasha [13] | — | — | — | — | ✅ | — | — | 流水线 | ? |
| IWNLP [10] | — | ✅ | — | — | — | — | — | 词典 | ? |
| GermaLemma [9] | — | ✅ | — | — | — | — | — | 词典 + 规则 | Apache-2.0（TIGER 另议） |
| LemmInflect [8] | ✅ | — | — | — | — | — | — | 词典 + NN | ? |
| Stanza [3] | ✅ | ✅ | ✅ | ✅ | ✅ | ✅≈ | ✅≈ | UD 序列标注 | Apache-2.0 |
| UDPipe [4][5] | ✅ | ✅ | ✅ | ✅ | ✅ | ✅≈ | ✅≈ | UD 序列标注 | 代码 MPL-2.0 / 模型 CC BY-NC-SA |
| Trankit [7] | ✅ | ✅ | ✅ | ✅ | ✅ | ✅≈ | ✅≈ | XLM-R + Adapter | ? |
| FreeLing [19] | ✅ | ✅ | ✅ | ✅ | ✅ | — | — | 规则 / 形态分析 | ? |
| CoreNLP [6] | ✅ | — | — | — | — | — | — | Morpha | ? |
| Apertium [20] | ✅ | — | ✅ | ✅ | ✅ | — | — | FST 规则 | ? |
| SudachiPy [18] | — | — | — | — | — | ✅ | — | 形态素分析 | Apache-2.0 |
| MeCab [17] | — | — | — | — | — | ✅ | ✅(mecab-ko) | 形态素分析 | 三选一（GPL/LGPL/BSD）? |
| Kiwi [16] | — | — | — | — | — | — | ✅ | 形态素分析 | ? |
| Khaiii [17b] | — | — | — | — | — | — | ✅ | CNN 形态素分析 | Apache-2.0 |

表里大量 `?` 是**有意留白**：本次未逐项核验许可证与 API 现状，不应据此做合规判断；需要时逐个查仓库 `LICENSE`。

---

## 6. 许可证陷阱（最容易踩的三处）

1. **UDPipe 的模型不是自由许可**：代码 MPL-2.0，但**语言模型 CC BY-NC-SA，禁止商业使用**，部分模型还叠加原始树库限制。[4] 商用只能自己用 CoNLL-U 重训。
2. **GermaLemma 依赖 TIGER**：TIGER 语料不在仓库内，需单独下载并遵守**非商业**许可；项目自述「currently not maintained」。[9]
3. **Simplemma 是「代码 MIT + 数据各自授权」**：README 明说各语言数据许可见 `licenses/` 目录，其中 `lemmatization-lists` 为 ODbL（有署名/传染性要求）。[1][11]

---

## 7. 给本仓库（`multi-lang-lemmatization`）的落地建议

1. **分两层抽象**：`lemmatize(token, lang)` 与 `analyze(text, lang) -> [(surface, lemma, pos)]`。屈折语用前者即可；`ja`/`ko` 必须走后者，因为 lemma 依赖分词结果。
2. **后端按语种可插拔注册**：
   - `en` → LemmInflect（精度高、无模型）
   - `de`/`fr`/`es` → Simplemma 词典（或 `lemmatization-lists` 自建表）
   - `ru` → pymorphy3（不要用查表）
   - `ja` → SudachiPy `dictionary_form()`
   - `ko` → Kiwi
3. **保留「升级到 UD 模型」的接口**：Stanza/UDPipe 一套代码覆盖全部 7 语种，适合做高精度对照基线；注意 UDPipe 模型的 NC 限制。
4. **评测口径统一到 UD treebank**，这样能直接对齐 Simplemma 已发布的分语种精度（en .96 / de .97 / fr .96 / es .96 / ru .94）[1]，不必自造指标。
5. **不要给 `ja`/`ko` 上查表方案**——这是这一类库的共同空白，也是最可能踩坑的地方。

---

## 8. 未解决 / 待核验

以下问题本次未取得一手证据，列出来避免被当成结论：

- spaCy 的 `ja` / `ko` pipeline 是否内置 lemmatizer（不在官方默认模式表中，行为未知）。
- Trankit 的 lemma 是否在公开 API 中可获取（任务清单未列，仅说明实现改编自 Stanza）。
- pymorphy3、Kiwi、IWNLP、Natasha、FreeLing、Apertium 的**具体许可证**未逐个核验。
- MeCab 的许可证表述（README 称 GPL/LGPL/BSD 三选）与各发行版实际条款的对应关系未核验。
- `spacy-iwnlp`、`GermaLemma` 是否已有社区维护的 fork。
- 各工具在 `ja`/`ko` 上的**实测 lemma 精度**（未见公开横向评测）。
- 纯神经/共享任务路线（SIGMORPHON 屈折共享任务的 T5/ByT5 系统、HuggingFace 上的多语 lemma 模型）本次未展开。

---

## 来源

1. Simplemma — https://github.com/adbar/simplemma （README：`https://raw.githubusercontent.com/adbar/simplemma/main/README.md`）
2. spaCy `Lemmatizer` API — https://spacy.io/api/lemmatizer
3. Stanza — https://github.com/stanfordnlp/stanza
4. UDPipe (v1) — https://github.com/ufal/udpipe
5. UDPipe 2 — https://ufal.mff.cuni.cz/udpipe/2
6. Stanford CoreNLP — https://stanfordnlp.github.io/CoreNLP/lemma.html 、 https://stanfordnlp.github.io/CoreNLP/human-languages.html
7. Trankit — https://github.com/nlp-uoregon/trankit
8. LemmInflect — https://github.com/bjascob/LemmInflect （含 AGID 横向基准表）
9. GermaLemma — https://github.com/WZBSocialScienceCenter/germalemma
10. spacy-iwnlp — https://github.com/Liebeck/spacy-iwnlp ；IWNLP 数据 — https://dbs.cs.uni-duesseldorf.de/datasets/iwnlp/
11. lemmatization-lists — https://github.com/michmech/lemmatization-lists
12. pymorphy3 — https://github.com/no-plagiarism/pymorphy3
13. Natasha — https://github.com/natasha/natasha
16. Kiwi / kiwipiepy — https://github.com/bab2min/kiwipiepy
17. MeCab 输出格式规范 — https://taku910.github.io/mecab/format.html
17b. Khaiii — https://github.com/kakao/khaiii
18. SudachiPy — https://github.com/WorksApplications/SudachiPy
19. FreeLing — https://github.com/TALP-UPC/FreeLing （语言目录取自 `data/` 内容列表）
20. Apertium — https://wiki.apertium.org/wiki/Main_Page
21. Janome — https://github.com/mocobeta/janome

（编号 14、15 在写作中被合并进 13 与 19，保留空号以免与正文引用错位。）
