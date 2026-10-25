# 按文档名/标题查找 KB 页面（filename → page）

适用场景：用户给你一个文档标题、PDF 文件名、或一段章节名（例如 "user manual — register data communication.pdf"、"Modbus 寄存器数据通信"、"register data communication"），让你找到 KB 里对应的页面。

## 核心问题

hermes-skill-proxy 的 jieba 关键词检索是**语义级**的，对"标题/文件名级别的强指针"很弱：

- 用户给的可能是英文标题，但 doc.inexbot.com 上大部分文档只有中文标题
- 反之 open.inexbot.com 上中文/英文/韩文三套 md 文件名带 locale 前缀，文件名匹配要走全路径
- 文件名中的破折号、空格、中英混合（"user manual——register"）不会直接映射到 KB 里的中文文档名
- 中文文件名翻译成英文或反过来，几乎不会命中

## 推荐工作流

### 第 1 步：先看 proxy 注入结果

不要绕过 proxy 自己去 grep。直接看 system prompt 里是否已经注入了相关文档——很多时候标题里有英文关键词（如 "Register"、"Modbus"、"Communication"）就能命中。

### 第 2 步：proxy 没命中时，按文件名/标题变体逐个查

在 index.json 的 `title` 字段上做**包含匹配**（不是分词），覆盖中英文 + 关键词同义词：

```python
import json
from pathlib import Path
idx = json.loads(Path.home().joinpath(".hermes/kb/inexbot/index.json").read_text(encoding="utf-8"))

# keywords: 从用户给的标题里拆出来
queries = ["寄存器", "数据通信", "register", "data", "communication", "Modbus"]

for url, doc in idx.items():
    title = doc.get("title", "")
    desc = doc.get("description", "")
    if any(q.lower() in title.lower() for q in queries):
        print(url, "->", title)
```

注意：也要扫 inexbot-open 的 index.json（用户给的可能是开放平台/二次开发文档）。

### 第 3 步：如果还是没命中，用 KB 文件名反查

文件名通常带文档类别前缀，对英文标题做猜测：

```bash
# 列出所有 md 文件名（含前缀）方便人眼/grep 匹配
ls ~/.hermes/kb/inexbot/md/ | head -50
ls ~/.hermes/kb/inexbot-open/md/ | head -50

# 按关键词快速反查
grep -li "寄存器\|Modbus\|register" ~/.hermes/kb/inexbot/md/*.md | head -20
ls ~/.hermes/kb/inexbot-open/md/ | grep -i -E "Modbus|EIP|OPCUA|register|communication" | head -20
```

inexbot-open 的 md 文件名前缀 = locale（zh- / en- / kr-），同一文档三个语种各一份。如果用户给的是英文标题，优先看 `en-*.md` 列表。

### 第 4 步：原始 HTML 也别忘了

`raw/` 目录是原始 vitepress HTML，文件名保留 URL path 的目录结构（用 `-` 拼接），对英文标题查询更直接：

```bash
# 英文文档名常出现在 raw/ 里（en- 前缀 / 中文 kebab-case）
ls ~/.hermes/kb/inexbot-open/raw/ | grep -i -E "register|modbus|communi|数据"
ls ~/.hermes/kb/inexbot/raw/ | grep -i -E "Modbus|Modbus功能|寄存器|数据通信"
```

### 第 5 步：确认"真的没有"再回复用户

避免一上来就回"未找到"。先扫三个面：proxy 注入、index.json 标题匹配、文件名反查。全部 0 命中才告知用户文档不在 KB，并提示可能原因：

- 用户给的可能是公司内部/项目专属 PDF，未公开发布到 doc.inexbot.com 或 open.inexbot.com
- 翻译差异：用户的中文标题可能对应 KB 里另一个中文命名（常见如「寄存器数据通信」↔「Modbus 功能使用手册」↔「外设_通讯」章节）
- 版本差异：旧版本手册可能已被新版替代

回复模板：

```
知识库中检索了所有 markdown 和 HTML 文件（中英文/24.03/25.01），未找到标题
为 "X" 的文档。

相关但不完全匹配的文档（仅供参考）：
- 链接 1
- 链接 2

知识库中未找到名为 "X" 的具体文档，可能该文件不在纳博特官方文档体系内，
或名称不完全一致。请问您指的是哪一类？我可以进一步定位：
- 选项 A
- 选项 B
- 选项 C
```

## 常见陷阱

### 不要直接在文件名上做模糊匹配

inexbot 和 inexbot-open 的 md 文件名规则不一样：

- inexbot: `类别-子类别-...-标题.md`（中文 kebab-case）
- inexbot-open: `locale-路径-...-标题.md`（locale 前缀是 zh/en/kr，无裸名）

不要混着 grep；分别扫两次。

### 用 `grep -i` 扫中文文件名时小心编码

`grep` 默认按字节匹配中文 OK，但如果你要扫「register」「Modbus」这类英文关键词，对中文文件名无效，要走内容 (`grep -l 'register' *.md` 在中文 md 里也能命中英文段落)。

### 用户给的标题可能是翻译过来的，**别死磕字面**

英文 "Register Data Communication" 中文文档里可能是：
- 「Modbus 寄存器通讯」
- 「外设_通讯-Modbus」
- 「通讯协议与地址码」
- 「IO_Modbus 与远程功能使用手册」

要做关键词放宽：拆成 register / data / communication / 寄存器 / 数据 / 通讯 / Modbus / RTU / TCP 全部试一遍，再让用户确认。

### KB 不收录的常见类别

- 用户专属定制文档
- 早期内部草稿（未上线 doc.inexbot.com）
- 第三方组件手册（如某些 PLC、相机品牌手册）—— 不在纳博特 KB 范围
- 培训材料 / PPT / 视频脚本