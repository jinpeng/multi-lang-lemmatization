# 多语种 Lemmatization 服务 — 技术设计

**日期**：2026-10-29
**状态**：待评审
**前置调研**：`docs/lemmatization-survey.md`

---

## 0. 已锁定的决策

| # | 决策 | 选择 |
|---|---|---|
| 1 | 租户模型 | **Key/Secret 分离 + HMAC + Admin 口令 + 无用户账号** |
| 2 | 语种范围 | **单镜像、全 7 语种、不按 extra 拆分依赖** |
| 3 | API 契约 | **单一 `/v1/lemmatize`、`pos` 可空、`/v1/languages` 能力矩阵** |
| 4 | 凭证事实来源 | **Next.js 作 BFF；Python 是 Key 的唯一事实来源；Secret/Admin 口令不进浏览器** |
| 5 | 存储 | **SQLite 单文件、单容器、API 无状态** |
| 6 | 配置深度 | **启动期只读诊断 + 运行期白名单可改 + 审计** |

### 0.1 对第 1 项决策的纠正（重要）

**原表述有误。** 讨论中我曾写「secret 服务端只存哈希」，这与 HMAC 不可共存：HMAC 验证必须持有 secret 原文。

**修正为**：secret 以 **AES-256-GCM 加密存库**，master key 来自环境变量 `LEMMA_MASTER_KEY`。另存 `secret_fingerprint`（`SHA-256(secret)[:8]`）供 console 展示，用于人工辨认「当前生效的是哪一版 secret」，不含可用于验证的信息。

---

## 1. 目标与非目标

### 1.1 目标

- 一个 HTTP 服务，对 `en de fr es ru ja ko` 七语种提供词形还原，行为差异由能力矩阵显式声明。
- 一个 Web console，提供演示、Key/Secret 管理、配置管理。
- 安全边界清晰：任何凭证（API secret、admin 口令）不进入浏览器。

### 1.2 非目标（明确不做）

- 用户注册/登录/密码找回/多租户隔离。
- 计费与配额结算。
- API 多实例水平扩展（SQLite 单写者）。
- 模型训练、微调、评估界面。
- 自定义词典上传（留 v2）。
- 分词之外的句法/实体分析。

---

## 2. 总体架构

```
                         ┌──────────────────────────────┐
   外部 API 使用者 ──────►│  Python API (FastAPI, :8000) │
   (Bearer / HMAC)       │                              │
                         │  ┌────────────────────────┐  │
                         │  │ Auth  (key + HMAC)     │  │
                         │  ├────────────────────────┤  │
                         │  │ Backend Registry       │  │
                         │  │  en  → LemmInflect     │  │
                         │  │  de  → Simplemma       │  │
                         │  │  fr  → Simplemma       │  │
                         │  │  es  → Simplemma       │  │
                         │  │  ru  → pymorphy3       │  │
                         │  │  ja  → SudachiPy       │  │
                         │  │  ko  → Kiwi            │  │
                         │  ├────────────────────────┤  │
                         │  │ Settings (whitelist)   │  │
                         │  ├────────────────────────┤  │
                         │  │ SQLite  lemming.db     │  │
                         │  └────────────────────────┘  │
                         └──────────────▲───────────────┘
                                        │ 内部 HTTP
                                        │ X-Service-Token
                                        │ X-Admin-Token
                         ┌──────────────┴───────────────┐
   浏览器 ──────────────►│  Next.js Console (:3000)     │
   (仅 httpOnly cookie) │  App Router / BFF            │
                         │  持有 admin 口令、service tok│
                         └──────────────────────────────┘
```

**关键约束**：浏览器只能访问 Next.js。Next.js 的 Server Component / Route Handler 才持有 `LEMMA_SERVICE_TOKEN` 与 admin 会话。

---

## 3. 后端抽象

调研的核心结论：7 个语种分成两类，**不能用一个接口表达**。

### 3.1 唯一接口 + 能力声明

```python
# api/backends/base.py
from dataclasses import dataclass
from typing import Literal, Protocol

Prov = Literal["dict", "rule", "model", "identity", "candidates"]

@dataclass(frozen=True)
class Capabilities:
    pos: bool              # 是否产出词性
    pos_required: bool     # 是否必须由调用方提供 pos
    candidates: bool       # 是否可能返回多个候选 lemma
    reading: bool          # 是否产出读音（ja）
    mwt: bool              # 是否展开多词单元
    tokenizes: bool        # 是否自行分词（ja/ko = True）

@dataclass(frozen=True)
class LemmaItem:
    surface: str
    lemma: str
    pos: str | None
    prov: Prov
    reading: str | None = None
    candidates: tuple[str, ...] = ()

class Backend(Protocol):
    lang: str
    name: str
    version: str
    capabilities: Capabilities

    def lemmatize(self, text: str | None,
                  tokens: list[str] | None,
                  pos: list[str | None] | None) -> list[LemmaItem]: ...
```

**为什么不是两个接口**：`ja`/`ko` 的 `tokenizes=True` 已经通过能力位表达了「我会重新分词」这一事实；响应里的 `segmented_by` 字段把这个差异显式告诉调用方。两个 endpoint 会让 console 写两套渲染，而决策 3 已经选了单一契约。

### 3.2 各后端实现要点

| 语种 | 库 | 调用 | pos 处理 | 备注 |
|---|---|---|---|---|
| en | LemmInflect | `getLemma(word, upos=?)` | 传入则用；未传则启发式推断 UD tag，`prov="rule"` | `pos_required=False` |
| de | Simplemma | `lemmatize(token, lang="de", greedy=?)` | 不产出（`pos=False`） | `greedy` 默认 `True`（复数名词 → 词干） |
| fr | Simplemma | 同上 | 同上 | |
| es | Simplemma | 同上 | 同上 | |
| ru | **pymorphy3** | `morph.parse(w)[0].normal_form` | 产出 POS（`pos=True`） | **不用 Simplemma 查表**，理由见调研 §4.5 |
| ja | SudachiPy | `Morpheme.dictionary_form()` | 产出品词（`pos=True`） | 切分模式 A/B/C 可配；`reading_form()` → `reading` |
| ko | Kiwi | `Token.form` 为词形，`join()` 用于还原 | 产出 tag（`pos=True`） | 需从 tagset 映射到统一 POS |

**未登录词策略**：全部返回 `lemma == surface` 且 `prov="identity"`，并在响应 `warnings` 追加 `{"code":"UNRESOLVED","surface":"..."}`。**绝不抛错**——单个生僻词不应让整个请求失败。

### 3.3 启动探测与降级

启动时逐个 `try: backend = build(lang)`：

- 成功 → 注册，`status="ok"`
- 导入失败/词典缺失 → 注册为 `status="unavailable"`，`reason` 记录异常摘要
- **不因单语种失败而崩溃**

访问 `unavailable` 语种返回 `503 LANGUAGE_UNAVAILABLE`，响应体列出原因。`/v1/languages` 同样反映该状态。

> 决策 2 说全语种单镜像，所以正常情况下不该出现 `unavailable`。这个机制是给「镜像里词典被裁掉」「模型加载 OOM」这类真实故障兜底的，成本仅几十行。

---

## 4. API 契约

### 4.1 `POST /v1/lemmatize`

```json
{
  "lang": "ja",
  "text": "東京へ行きました",
  "tokens": null,
  "pos": null,
  "options": { "split_mode": "C" }
}
```

- `text` 与 `tokens` **二选一**（同时给 → `400 INVALID_REQUEST`）。
- `pos`：`null` | 单值（长度须等于 tokens）| 数组。仅当后端 `pos_required` 时必填。
- `options`：使用**短名**（`greedy`、`split_mode`），与 §7.1 注册表里的**点分键**（`langs.de.greedy`）不是同一命名空间——前者是单次请求的临时覆盖，后者是服务端持久化默认值。未知键 → `400 UNKNOWN_OPTION`。
- 请求级 `options` 只接受该语种在 `/v1/languages` 中声明过的键，且只在 `hot=True` 的项上生效。

响应：

```json
{
  "request_id": "req_01J...",
  "offset_unit": "unicode_code_point",
  "lang": "ja",
  "backend": { "name": "sudachipy", "version": "0.6.10", "dict": "core-20240716" },
  "segmented_by": "backend",
  "capabilities": { "pos": true, "pos_accepted": false, "pos_required": false,
                    "candidates": false, "reading": true, "mwt": false,
                    "tokenizes": true },
  "items": [
    { "surface": "東京", "lemma": "東京", "pos": "名詞-固有名詞-地名", "prov": "dict",
      "reading": "トウキョウ", "start": 0, "end": 2 },
    { "surface": "へ", "lemma": "へ", "pos": "助詞-格助詞", "prov": "dict",
      "start": 2, "end": 3 },
    { "surface": "行き", "lemma": "行く", "pos": "動詞-非自立可能", "prov": "dict",
      "reading": "イキ", "start": 3, "end": 5 },
    { "surface": "ました", "lemma": "ます", "pos": "助動詞", "prov": "dict",
      "start": 5, "end": 8 }
  ],
  "warnings": [],
  "elapsed_ms": 3.1
}
```

`offset_unit` 取值与语义（决策见 §13）：

- `"unicode_code_point"` — `start`/`end` 是 `text` 的 **码点**偏移
- `null` — 本次响应不含偏移（调用方传的是 `tokens`，没有源串可指）

字段 `start`/`end` 在无偏移时**整体省略**（不输出 `null`），因为半开区间缺一半是无意义的。

» **JavaScript 消费者必须转换**：Python 与 ja/ko 分析器都按码点数，JS 字符串按 UTF-16 码元索引。二者在 BMP 内一致，一旦文本含 emoji、U+FFFF 以上的生僻汉字或数学字母就会出现**静默错位**（不报错、只是高亮范围偏移）。Console 的 `codePointToUtf16()` 负责这一步。

» **`surface` 不一定等于 `text[start:end]`**：韩语「갔」会被分析为 `가/VV` + `었/EP`，两个形态素共享同一区间 `[0,1]`。`surface` 是形态素，不是原文子串。

`segmented_by` 取值：

- `"input"` — 忠实于调用方给的 tokens（en/de/fr/es/ru）
- `"backend"` — 后端重新分词（ja/ko），`items[].surface` 可能与请求不同

> **这是最容易误解的一处**，因此放在顶层而非埋在 `items` 里。

### 4.2 `GET /v1/languages`

```json
{
  "languages": [
    {
      "lang": "ja", "status": "ok",
      "backend": { "name": "sudachipy", "version": "0.6.10", "dict": "core-20240716" },
      "capabilities": { "pos": true, "pos_required": false, "candidates": false,
                        "reading": true, "mwt": false, "tokenizes": true },
      "pos_scheme": "sudachi",
      "options": { "split_mode": { "type": "enum", "values": ["A","B","C"], "default": "C" } },
      "enabled": true
    },
    {
      "lang": "de", "status": "ok",
      "backend": { "name": "simplemma", "version": "1.2.0" },
      "capabilities": { "pos": false, "pos_required": false, "candidates": false,
                        "reading": false, "mwt": false, "tokenizes": false },
      "pos_scheme": null,
      "options": { "greedy": { "type": "bool", "default": true } },
      "enabled": true
    }
  ]
}
```

`enabled=false`（被管理员在 Settings 关掉）的语种仍出现在列表里，但请求返回 `403 LANG_NOT_ENABLED`。**让调用方能区分「不存在」和「被禁用」。**

`pos_scheme` 声明该语种 `pos` 的标签体系：`"ud"`（en，UPOS）、`"pymorphy"`（ru）、`"sudachi"`（ja）、`"sejong-kiwi"`（ko）、`null`（该语种不产出 pos）。见 §13 开放项 1。

### 4.3 其他端点

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/v1/health` | 存活 + 各后端就绪状态（无需鉴权） |
| `GET` | `/v1/usage` | 当前 key 的限流余量 |
| `GET/POST` | `/admin/keys` | 列出 / 创建 |
| `POST` | `/admin/keys/{key_id}/rotate` | 轮换 secret |
| `POST` | `/admin/keys/rotate-all` | master key 丢失时的兜底全量轮换（需 admin 口令，二次确认） |
| `DELETE` | `/admin/keys/{key_id}` | 吊销 |
| `GET/PATCH` | `/admin/settings` | 读 / 改（白名单 + 审计） |
| `GET` | `/admin/diagnostics` | 只读：版本、词典、uptime、非白名单 env 摘要（脱敏） |
| `GET` | `/admin/audit` | 审计日志分页 |
| `POST` | `/admin/session` | 校验 admin 口令，签发 admin token |

### 4.4 错误信封（统一）

```json
{
  "error": {
    "code": "SIGNATURE_INVALID",
    "message": "HMAC signature does not match",
    "details": {},
    "request_id": "req_01J..."
  }
}
```

| code | HTTP | 触发 |
|---|---|---|
| `INVALID_REQUEST` | 400 | 参数校验失败 |
| `UNKNOWN_OPTION` | 400 | `options` 含白名单外键 |
| `UNAUTHORIZED` | 401 | 缺凭证 / key 不存在 / secret 错 |
| `SIGNATURE_INVALID` | 401 | HMAC 不匹配 |
| `TIMESTAMP_OUT_OF_WINDOW` | 401 | 时间戳超出 ±300s |
| `NONCE_REPLAYED` | 401 | nonce 已用 |
| `LANG_NOT_ENABLED` | 403 | 语种被管理员禁用 |
| `LANG_FORBIDDEN` | 403 | key 的 `langs` 不含该语种 |
| `RATE_LIMITED` | 429 | 超限，带 `Retry-After` |
| `PAYLOAD_TOO_LARGE` | 413 | body 或 tokens 数超限 |
| `LANGUAGE_UNAVAILABLE` | 503 | 后端初始化失败 |
| `INTERNAL` | 500 | 兜底，`details` 不含堆栈 |

---

## 5. 鉴权设计

### 5.1 Key 模型

- `key_id`：`lk_` + base32(16B)，**公开标识**，进请求头
- `secret`：`ls_` + base32(32B)，**仅创建/轮换时明文返回一次**

两者分离的意义：**轮换 secret 不必更换 key_id**，因此调用方只需换一个值，日志/审计/key 身份保持连续。

### 5.2 两种调用模式（都必须携带 secret）

> 修正：`key_id` 单独不能完成鉴权，它只是身份标识。我最初的口径有误。

**模式 1 — Bearer（简单）**

```
Authorization: Bearer lk_XXXX.ls_YYYY
```

适合服务端到服务端（TLS 内传输）。服务端 login：拆出 `key_id`，解密取出 secret，**常数时间比较**。

**模式 2 — HMAC（secret 不出客户端）**

```
X-Api-Key:   lk_XXXX
X-Timestamp: 1761792000
X-Nonce:     8f3a...
X-Signature: base64(HMAC-SHA256(signing_key, canonical))
```

`canonical` =
```
{METHOD}\n{PATH}\n{timestamp}\n{nonce}\n{sha256(body) hex}
```

校验链：时间窗 → nonce 未用过 → 签名 → key 状态。任一步失败即拒。

`signing_key = HKDF(secret, info=b"lemma-hmac-v1", length=32)`，与 Bearer 用的 secret 同源但不同用途，避免同一密钥材料跨用途复用。

**Replay 防护**：`nonce` 进内存 LRU（TTL 600s，容量 10 万）。单实例部署（决策 5）所以无需跨进程共享。这一点在文档里必须写明：**若将来扩多实例，nonce 存储需外置**。

### 5.3 存储与加密

| 字段 | 内容 |
|---|---|
| `key_id` | 明文，UNIQUE |
| `secret_enc` | AES-256-GCM(master_key, secret)，附 12B nonce，AAD = key_id |
| `secret_fingerprint` | `sha256(secret)[:8]` — 仅供展示识别 |
| `secret_prev_enc` | 上一版 secret，`prev_expires_at` 后逻辑失效 |

`LEMMA_MASTER_KEY` = base64(32B)，从 env 读。**丢失 = 所有 secret 不可验证，只能全量轮换。** 这写进运维文档的醒目位置。

### 5.4 轮换与吊销

- 轮换：旧 secret 移入 `secret_prev_enc`，宽限 24h（可配）；期间两版都接受，响应头 `X-Secret-Rotated: true` 提醒调用方切换；宽限期满后旧版拒绝。
- 吊销：`revoked_at` 置位，立即失效；无需删除行（保留审计）。

### 5.5 Admin 会话

1. 浏览器 `POST /api/session {passphrase}` → Next.js 转发 `POST /admin/session`
2. Python 用 argon2id 校验 `LEMMA_ADMIN_PASSPHRASE_HASH`，签发 `admin_token`（不透明随机串，TTL 2h，内存表）
3. Next.js 把 `admin_token` 写入 **httpOnly + Secure + SameSite=Lax** cookie
4. 后续 admin 请求由 Next.js 服务端附加 `X-Service-Token` + `X-Admin-Token`

浏览器始终拿不到 `admin_token` 的明文（httpOnly）、也拿不到 `LEMMA_SERVICE_TOKEN`。

**CSRF**：mutating 请求额外要求 `X-CSRF-Token`（双提交，值由 Next.js 下发的非 httpOnly cookie 提供）。

---

## 6. 数据模型

```sql
CREATE TABLE api_keys (
  id                TEXT PRIMARY KEY,
  name              TEXT NOT NULL,
  key_id            TEXT NOT NULL UNIQUE,
  secret_enc        BLOB NOT NULL,
  secret_fingerprint TEXT NOT NULL,
  secret_prev_enc   BLOB,
  prev_expires_at   TEXT,
  scopes            TEXT NOT NULL DEFAULT '["lemmatize"]',
  langs             TEXT NOT NULL DEFAULT '[]',   -- 空数组 = 全部允许
  allow_hmac        INTEGER NOT NULL DEFAULT 0,
  rate_limit_rpm    INTEGER NOT NULL DEFAULT 600,
  created_at        TEXT NOT NULL,
  created_by        TEXT NOT NULL,
  last_used_at      TEXT,
  expires_at        TEXT,
  revoked_at        TEXT,
  revoked_reason    TEXT
);

CREATE TABLE settings (
  key         TEXT PRIMARY KEY,
  value_json  TEXT NOT NULL,
  updated_at  TEXT NOT NULL,
  updated_by  TEXT NOT NULL
);

CREATE TABLE audit_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  at         TEXT NOT NULL,
  actor      TEXT NOT NULL,
  action     TEXT NOT NULL,
  target     TEXT NOT NULL,
  before_json TEXT,
  after_json TEXT,
  request_id TEXT,
  ip         TEXT
);

CREATE TABLE request_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  at         TEXT NOT NULL,
  request_id TEXT NOT NULL,
  key_id     TEXT,
  lang       TEXT,
  n_tokens   INTEGER,
  bytes_in   INTEGER,
  latency_ms INTEGER,
  status     INTEGER,
  error_code TEXT,
  ip         TEXT
);
```

`request_log` 保留 7 天（启动时与每小时清理），避免 SQLite 无界增长。

---

## 7. 配置分层（决策 6）

### 7.1 白名单（代码内注册表）

```python
# api/settings/registry.py
EDITABLE = {
  "langs.enabled":            Spec(kind="lang_set", hot=True,  default=["en","de","fr","es","ru","ja","ko"]),
  "langs.de.greedy":          Spec(kind="bool",     hot=True,  default=True),
  "langs.fr.greedy":          Spec(kind="bool",     hot=True,  default=False),
  "langs.es.greedy":          Spec(kind="bool",     hot=True,  default=False),
  "langs.ja.split_mode":      Spec(kind="enum",     hot=True,  default="C", values=["A","B","C"]),
  "langs.ko.model_type":      Spec(kind="enum",     hot=False, default="cong", values=["cong","knlm"]),
  "ratelimit.default_rpm":    Spec(kind="int",      hot=True,  default=600, min=1, max=100000),
  "ratelimit.burst":          Spec(kind="int",      hot=True,  default=60,  min=1, max=10000),
  "request.max_tokens":       Spec(kind="int",      hot=True,  default=5000, min=1, max=100000),
  "request.max_body_bytes":   Spec(kind="int",      hot=True,  default=1048576, min=1024, max=16777216),
}
```

**入选标准**：改错了最坏是「效果变差 / 稍慢 / 拒得更多」，不会让服务起不来或 console 失联。模型路径、数据库 DSN、master key 一律不进白名单。

`hot=False` 的项（如 `ko.model_type`）在 UI 上明确标注「需重启生效」，落库后不即时应用。

### 7.2 只读诊断

`GET /admin/diagnostics` 返回：

- 各后端 `name/version`、词典标识与来源、`status`、加载耗时
- 能力矩阵快照
- 进程 uptime、Python/库版本
- **脱敏后的**关键 env（`LEMMA_MASTER_KEY` → `set(len=32)`，`LEMMA_SERVICE_TOKEN` → `set`）
- SQLite 路径、大小、`request_log` 行数

**只读，不可 PATCH。** 这是与 Settings 页的物理分隔——避免把 console 做成「能改坏服务的开关面板」。

### 7.3 审计

每次 PATCH 写 `audit_log`：`actor`（admin 会话标识）、`target`（配置键）、`before_json`、`after_json`、`request_id`。UI 上每个配置项旁展示「最后修改：谁 / 何时」。

---

## 8. Console（Next.js）

### 8.1 页面

| 路由 | 类型 | 内容 |
|---|---|---|
| `/` | Server Component | **Playground**：语种 tab、文本输入、结果表格（surface / lemma / pos / prov / reading）、耗时、后端徽章、等价 `curl` |
| `/languages` | Server Component | 能力矩阵表（直接渲染 `/v1/languages`），`unavailable`/`disabled` 高亮 |
| `/keys` | Client + Server Action | Key 列表、创建、轮换、吊销、每 key 限流与语种限制 |
| `/settings` | Client + Server Action | 上半 **Diagnostics（只读）**，下半 **Settings（可改）** + 变更审计 |
| `/logs` | Server Component | 最近请求样本 + 审计日志，分页 |

### 8.2 Playground 的数据流（关键）

```
浏览器 ──POST /api/playground──► Next.js Route Handler
                                   ├─ 用内置 demo key（env 注入）调 Python
                                   └─ 返回结果 + 生成的 curl 片段
```

**浏览器不持有任何 key。** demo key 由服务端注入，scope 限 `lemmatize`、限流较低、可在 Settings 关闭。UI 同时展示 `curl`，让「演示」与「真实调用」保持一致。

### 8.3 技术选型

- Next.js 15 App Router + TypeScript
- Tailwind CSS（不引入完整组件库，保持 5 个页面可控）
- Server Actions 处理 mutating 操作；Route Handler 仅用于 Playground 与 session
- 无客户端状态库（用 `useState` + `revalidatePath`）

---

## 9. 部署

```yaml
# docker-compose.yml
services:
  api:
    build: { context: ., dockerfile: deploy/api.Dockerfile }
    environment:
      LEMMA_MASTER_KEY: ${LEMMA_MASTER_KEY}
      LEMMA_SERVICE_TOKEN: ${LEMMA_SERVICE_TOKEN}
      LEMMA_ADMIN_PASSPHRASE_HASH: ${LEMMA_ADMIN_PASSPHRASE_HASH}
      LEMMA_DB_PATH: /data/lemming.db
    volumes: [ "lemmadata:/data" ]
    command: uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4
    # 不暴露端口到宿主机；仅 console 可达
  console:
    build: { context: ., dockerfile: deploy/console.Dockerfile }
    environment:
      LEMMA_API_URL: http://api:8000
      LEMMA_SERVICE_TOKEN: ${LEMMA_SERVICE_TOKEN}
      LEMMA_DEMO_KEY: ${LEMMA_DEMO_KEY}   # 完整 Bearer 凭证，由 init 脚本铸造并落库为 name="console-demo" 的普通 key
    ports: [ "3000:3000" ]
volumes:
  lemmadata:
```

**并发模型**：`uvicorn --workers N`（进程级）。Simplemma/Simplemma-Greedy 是纯 Python CPU 密集型，GIL 下线程无收益；用多进程。后端实例随进程各持一份，启动时懒加载。

**镜像体积**（决策 2 已接受）：`sudachidict_core` ≈70 MB + `kiwipiepy_model` CoNg ≈58.7 MB，预计 api 镜像 400–500 MB。

---

## 10. 测试策略

| 层 | 工具 | 覆盖 |
|---|---|---|
| 后端单元 | pytest | 每语种 ≥10 组 `surface → lemma`（含未登录词、日韩分词、俄语格变化） |
| API | pytest + httpx ASGI | 契约、错误码、`pos` 可空语义、`segmented_by` |
| 鉴权 | pytest | Bearer、HMAC 正/负、时间窗、nonce 重放、轮换宽限期 |
| 配置 | pytest | 白名单拒绝、审计落库、`hot=False` 不即时生效 |
| Console | Vitest | 组件与 fetch 封装 |
| E2E | Playwright | 登录 → 建 key（secret 只显示一次）→ Playground 演示 → 改配置 → 审计可见 |

**黄金用例**（跨语种契约一致性）：

```
en  was      → be        (pos=VERB)
de  Häuser   → Haus
fr  mangées  → manger
es  corriendo→ correr
ru  шёл      → идти
ja  食べました→ 食べる (segmented_by=backend)
ko  먹었습니다→ 먹다  (segmented_by=backend)
```

---

## 11. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| `LEMMA_MASTER_KEY` 丢失 | 所有 secret 不可验证 | 运维文档置顶；提供 `POST /admin/keys/rotate-all` 兜底（需 admin 口令） |
| Kiwi CoNg 在 Apple Silicon 慢 | 本地开发 `ko` 卡 | 开发默认 `langs.ko.model_type="knlm"`，生产 `cong` |
| Simplemma `greedy` 语义差异 | de 与 fr/es 行为不一致 | 按语种独立配置，默认值按调研取值（de=True，fr/es=False） |
| SQLite 写竞争（audit 高频） | 写锁等待 | audit 走单写队列；`request_log` 批量落盘 |
| 单实例 nonce 表 | 扩多实例即失效 | 文档显式标注为「单实例假设」 |
| 日韩分词与调用方不一致 | 调用方按 tokens 对不齐 | `segmented_by` 顶层字段；字符偏移见 §13 开放项 2 |

---

## 12. 交付里程碑

| 里程碑 | 内容 | 出口标准 |
|---|---|---|
| **M1 后端骨架** | Backend 协议 + 5 语种（en/de/fr/es/ru）+ `/v1/lemmatize` 无鉴权 | 黄金用例 5 条通过 |
| **M2 日韩** | SudachiPy + Kiwi 接入，`segmented_by` 生效 | 黄金用例 7 条全通过 |
| **M3 鉴权** | Key/Secret、Bearer、HMAC、限流、SQLite | 鉴权测试全绿 |
| **M4 Console** | 5 个页面 + BFF + admin 会话 | Playwright 主链路通过 |
| **M5 配置与审计** | 白名单、诊断、审计日志 | 配置改动可追溯到人 |
| **M6 加固** | 镜像、compose、运维文档、备份演练 | `docker compose up` 一键起 |

---

## 13. 开放项 — 已定稿

三项均已在评审时确认，实施计划已按此实现。

**13.1 `ja`/`ko` 的 `pos`：原样透出，不映射到 UD UPOS。**
响应新增 `pos_scheme` 声明标签体系（`"ud"` / `"pymorphy"` / `"sudachi"` / `"sejong-kiwi"` / `null`）。映射到 UPOS 会丢掉 Sudachi 的 6 段品词与 Kiwi 的世宗细分标签，且需长期维护一张映射表。

**13.1b `pos` 与 `pos_accepted` 必须分开（评审后追加的修正）**
实现时发现英语（LemmInflect）**接受** `upos` 但**不产出**标签，而 `ru`/`ja`/`ko` 反过来。原本单一的 `pos` 字段会向客户端谎称「英语忽略词性」，让调用方在每个歧义词上白白损失精度：

```
left  + upos=VERB → leave     ← 动词的正确结果
left  + upos=NOUN → left
left  无 pos      → left      ← 取字典序，与动词用法不符
```

故 `Capabilities` 拆为 `pos`（产出）与 `pos_accepted`（接受）。

**13.2 字符偏移：M1 就进 schema，采用码点。**
理由：后加是破坏性变更。单位选码点因为它是 Python 与两个分析器的原生单位，无需在热路径上做 O(n) 转换；同时用顶层 `offset_unit` 显式声明，让 JS 消费者知道要转换。已用真实分析器验证：Sudachi 的 `begin()/end()` 精确切片；Kiwi 的 `start/len` 是合法区间但契约变形时不等于 `form`。

**13.3 `request_log` 不保留请求文本。**
只存形状：`lang`、`n_tokens`、`bytes_in`、`latency_ms`、`status`、`error_code`。存正文会让本服务变成 PII 存储点。已有测试 `test_no_request_text_column_is_stored` 钉住列集合，防止将来被加回。

**13.4 顺带发现：Pydantic 违约与模块级导入崩溃**
（实现阶段发现，已修正，记录以备回溯）

- FastAPI 的 `RequestValidationError` 默认返回 422 + `{"detail": [...]}`，绕过了 §4.4 要求的统一错误信封——客户端解析 `error.code` 会失败。已加处理器映射为 `INVALID_REQUEST` / 400。
- `build_registry` 原本在模块级导入全部后端模块，导致少装一个包就在所有 `try/except` 之外抛 `ImportError`，**七个语种全部起不来**，与 §3.3 的「单语种降级」承诺矛盾。已改为惰性导入。
