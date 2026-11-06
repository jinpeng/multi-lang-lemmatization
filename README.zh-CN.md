# multi-lang-lemmatization

[English](README.md) | **简体中文**

一个支持 **7 种语言**的词形还原（lemmatization）HTTP 服务：FastAPI 后端 + Next.js 管理控制台，单镜像全语言离线运行。

每种语言使用该语种最合适的开源分析器，而不是一个库通吃：

| 语言 | 后端 | POS 输出 | 接受 POS 输入 | 自行分词 | 请求级选项 |
|------|------|:---:|:---:|:---:|------|
| `en` 英语 | [lemminflect](https://github.com/bjascob/LemmInflect) | — | ✅ | — | — |
| `de` 德语 | [simplemma](https://github.com/adbar/simplemma) | — | — | — | `greedy`（默认 true） |
| `fr` 法语 | simplemma | — | — | — | `greedy`（默认 false） |
| `es` 西班牙语 | simplemma | — | — | — | `greedy`（默认 false） |
| `ru` 俄语 | [pymorphy3](https://github.com/pymorphy2/pymorphy3) | ✅ | — | — | — |
| `ja` 日语 | [SudachiPy](https://github.com/WorksApplications/SudachiPy)（core 词典） | ✅ | — | ✅ | `split_mode`: A/B/C |
| `ko` 韩语 | [kiwipiepy](https://github.com/bab2min/kiwipiepy) | ✅ | — | ✅ | — |

> 为什么是这些后端：`ja`/`ko` 是黏着语，"lemma" 是形态素分析的副产品，必须先分词；`en`/`de`/`fr`/`es`/`ru` 是屈折语，查表/规则即可。完整调研见 [`docs/lemmatization-survey.md`](docs/lemmatization-survey.md)。

## 快速开始

```bash
uv venv --python 3.12
uv pip install -e ".[dev]"
uv run uvicorn api.main:app --reload --port 8000
```

试试：

```bash
curl -s localhost:8000/v1/lemmatize \
  -H 'content-type: application/json' \
  -d '{"lang": "ja", "text": "私は東京へ行きました"}'
```

```json
{
  "lang": "ja",
  "segmented_by": "backend",
  "offset_unit": "unicode_code_point",
  "items": [
    {"surface": "行き", "lemma": "行く", "pos": "動詞,...", "start": 5, "end": 7}
  ]
}
```

## API

| Method | Path | 说明 |
|--------|------|------|
| GET | `/v1/health` | 各语言后端就绪状态 |
| GET | `/v1/languages` | 能力矩阵 + 各语言可用选项 |
| POST | `/v1/lemmatize` | 唯一的计算端点 |
| POST/GET/... | `/admin/*` | 密钥、设置、审计、请求日志（需管理员会话） |

### `POST /v1/lemmatize`

请求体：`text` 与 `tokens` 二选一（必须恰好一个）。

```json
{
  "lang": "en",
  "tokens": ["was", "left"],
  "pos": ["VERB", "VERB"],
  "options": {}
}
```

每个返回 item 携带 `surface` / `lemma` / `pos` / `prov` / `start` / `end`（ja 额外有 `reading`）。`prov` 表明 lemma 的产生方式（`dict` / `rule` / `model` / `identity` / `candidates`），便于下游区分真实词典命中与直通输出。

**三个使用方必须知道的语义：**

1. **offsets 是码点（code point）偏移**，指向请求原文；传 `tokens` 时省略。Python 数码点、JavaScript 数 UTF-16 码元——含 BMP 之外字符（emoji、U+FFFF 以上表意文字）时，`text.slice(start, end)` 需要先做换算。
2. **`surface` 不总是等于 `text[start:end]`。** 韩语缩略形会分解：`갔` → `가/VV` + `었/EP`，二者共享 span `[0:1]`。span 是对的，但 `surface` 是语素而非子串。
3. `pos`（后端产出标签：ru/ja/ko）与 `pos_accepted`（后端消费标签：en）是两回事。英语会因 POS 输入改变答案：`left`+VERB → `leave`，`left`+NOUN → `left`。

## 仓库结构

```
api/        FastAPI 服务（backends/ 下是 7 个语言适配器）
console/    Next.js 管理控制台（密钥管理、语言矩阵、日志、设置）
deploy/     Docker Compose 部署（api + console）
tests/      pytest 套件（含跨语言黄金用例）
scripts/    UD 测试集下载与准确率评测
docs/       调研报告与设计规范
```

## 测试

```bash
uv run pytest -m "not slow"   # 快速：跳过 ja/ko 词典加载
uv run pytest                 # 全量：230 个用例，含 7 语言黄金集
uv run ruff check . && uv run ruff format --check .
```

测试分两层：`tests/backends/` 是各语言适配器的专项测试（形态还原、offsets 契约、选项覆盖）；`tests/test_golden.py` 是经真实 API 的跨语言黄金用例（`was→be`、`Häuser→Haus`、`食べました→食べる`、`먹었습니다→먹다` …）。

## 准确率评测

黄金用例是冒烟测试，不是准确率测量。真实数字来自随仓库提供的、针对 Universal Dependencies 官方测试集的评测脚本：

```bash
./scripts/download_ud.sh                        # 下载 UD 测试集到 data/ud/
uv run python -m scripts.evaluate_ud            # 7 语言报告
uv run python -m scripts.evaluate_ud --json     # 机器可读
uv run python -m scripts.evaluate_ud --langs ja ko
```

最新结果，仅统计内容词（NOUN/VERB/ADJ/ADV/PROPN/NUM）：

| 语言 | 后端 | 准确率 | 命中样本 | 说明 |
|------|------|-------:|-------:|------|
| en | lemminflect | **95.83%** | 12,324 | 利用 gold UPOS 消歧 |
| de | simplemma | **95.46%** | 7,999 | greedy=true |
| fr | simplemma | **94.45%** | 4,507 | greedy=false |
| es | simplemma | **93.66%** | 5,550 | greedy=false |
| ru | pymorphy3 | **93.25%** | 6,784 | OpenCorpora 词典 |
| ja | sudachipy | **88.89%** | 5,554 | UD 汉字 lemma 与 Sudachi 假名辞典形经读音归一化后比较 |
| ko | kiwipiepy | **94.02%** | 7,946 | UD 复合 lemma（`있+다`）与 Kiwi 辞典形（`있다+다`）对齐后比较 |

UD 与后端分词粒度不一致的 gold token（ja 801、ko 1,687）记为 `unaligned`，从分母中剔除而非判错——逐个比较它们衡量的是分词而非词形还原。

## 部署

见 [`deploy/README.md`](deploy/README.md)。要点：所有命令在 `deploy/` 下运行；`.env` 必须放在 `docker-compose.yml` 旁边；`LEMMA_MASTER_KEY` / `LEMMA_SERVICE_TOKEN` / 管理员口令哈希三个值都要用脚本生成，不要手编。

```bash
cd deploy && cp .env.example .env
# …生成密钥后…
docker compose up -d --build
```

控制台在 http://localhost:3000，API 在 http://localhost:8000。

## 文档

- [`docs/lemmatization-survey.md`](docs/lemmatization-survey.md) — 7 语种开源方案调研（后端选型依据）
- [`docs/superpowers/specs/2026-10-29-multilingual-lemmatization-design.md`](docs/superpowers/specs/2026-10-29-multilingual-lemmatization-design.md) — 设计规范
- [`api/README.md`](api/README.md) — API 细节（POS 语义、offset 契约）
- [`deploy/README.md`](deploy/README.md) — 运维手册

## License

[MIT](LICENSE)
