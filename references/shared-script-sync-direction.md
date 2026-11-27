# 共享脚本同步：「新」≠「对」——必须用损坏样本实测两个版本

> 📌 **姊妹 KB 同源**：本文件与姊妹 skill 的
> `inexbot-open-knowledge-base/references/shared-script-sync-direction.md` **内容同步**
> （改一份要同步另一份）。姊妹侧若没有本文件，把本文件整份复制过去。
>
> 姊妹 KB 侧的对应条目写在 `references/cron-completion-discipline.md`
> 「同步共享脚本到姊妹 KB」一节。

## 核心结论（一句话）

> **同步共享脚本时，「哪个版本更新」与「哪个版本正确」是两个独立问题。**
> **「新版」不等于「更好」** —— 必须把**两个版本都跑一遍损坏样本**，
> 看**谁能报出损坏**，再决定采纳哪个。

## 为什么这条必须存在

§陷阱 23 / 45 解决的是「**同步方向**」（谁的内容该被采纳），
判据是「独有行集合」/「变化行是否全部与本次改动相关」。
**但那两条判据只能告诉你「对方有没有独有内容」，不能告诉你「对方的内容对不对」。**

⇒ 一个**内容不同但同样自洽**的版本，会被「变化行是否全部相关」判为「可以覆盖」，
然后你把一个**有缺陷的**版本覆盖了姊妹 —— 而两边跑的是**同一个 proxy**。

## 2026-11-26 现场（我方踩坑全过程）

### 背景

- 11-25：姊妹 KB 把 `scripts/check_shared_pitfalls_structure.py` 重写为
  **带 `SIG_LINES = 8` 固定长度前缀签名**的版本，并写入 **§陷阱 48**
  （「移植别人的『重写版』审计脚本 = 可能丢判据」）。
- 11-25：我方**独立重写**了同一脚本（新增「正文交错」检测、跳过围栏代码块、
  删除旧 `warnings` 通道），并在 SKILL.md 里写「两库现已统一为同一版」。
- 11-26 开局：发现姊妹 HEAD 里有 **37 行我方没有**的内容（陷阱 48）。

### 两版的判据差异

| 判据 | 我方 11-25 重写版 | 姊妹版（带 `SIG_LINES`） |
|---|---|---|
| 重复标题 | `DUPLICATE_HEADING` | 同 |
| 重复正文（整段 sha256） | `DUPLICATE_SECTION` | 同 |
| 空节 | `EMPTY_SECTION` | 同 |
| 正文交错 | `INTERLEAVED_BODY` | 同 |
| 子标题多于 section | `SUSPECT_ORPHAN` | 同 |
| **末尾孤儿体**（把最后一节正文抄一份追加到 EOF） | ❌ **无判据** | ✅ **`SIG_LINES=8` 固定长度前缀签名** |

### 实证（构造损坏文件跑两个版本）

损坏样本 = 真实共享文件 + 「把最后一节正文抄一份追加到 EOF」：

| 版本 | 结果 | 判读 |
|---|---|---|
| 我方 11-25 重写版 | **exit 0** | ❌ **假绿！真损坏漏报** |
| 姊妹版（带 `SIG_LINES`） | **exit 1**（报 `DUPLICATE_BLOCK`） | ✅ 正确抓到 |

### 根因

**「整段正文 sha256」无法替代「固定长度前缀签名」**：
最后一节的正文区间**延伸到 EOF** ⇒ 孤儿体（它的复制体）**被吸进它自己** ⇒
该节的 sha256 **唯一** ⇒ 判据 #2 根本看不到「两份」⇒ 孤儿体漏检。

⇒ 姊妹版（保留 `SIG_LINES`）才是正确的那个。
⇒ **「我方更新」≠「我方更对」** —— 这次是我方自己的重写引入了回归。

### 处置

1. 共享文档 `references/shared-proxy-service-pitfalls.md` + 脚本
   `scripts/check_shared_pitfalls_structure.py` **同步为姊妹版**
   （sha1 两侧逐项一致）。
2. 新增 `scripts/test_shared_pitfalls_structure.py`（姊妹版的回归测试）
   → **在我方 repo 实跑 exit 0**（case1 完好文件 → exit 0；case2 末尾孤儿体 → exit 1）。
3. SKILL.md 补记「统一方向取错」的实证 + 版本号递增。

## ✅ 标准动作：同步共享脚本的「五步纪律」

```bash
# ① 造一个**真实的损坏样本**（不是凭空写的合成样本 —— 要用真文件的真实结构）
#    典型形态：把最后一节正文抄一份追加到 EOF（§陷阱 31 要抓的就是这个）
python3 - <<'PY'
import pathlib
src = pathlib.Path("references/shared-proxy-service-pitfalls.md").read_text(encoding="utf-8")
lines = src.splitlines()
i = max(k for k, l in enumerate(lines) if l.startswith("## "))
body = lines[i+1:]
while body and not body[-1].strip():
    body.pop()
pathlib.Path("/tmp/shared_CORRUPT.md").write_text(
    "\n".join(lines) + "\n\n" + "\n".join(body[:20]) + "\n", encoding="utf-8")
PY

# ② 两个版本各跑一次**损坏样本**（必须用同一个 --file 参数！）
/usr/bin/python3 <our_repo>/scripts/check_shared_pitfalls_structure.py --file /tmp/shared_CORRUPT.md; echo "ours exit=$?"
/usr/bin/python3 <sis_repo>/scripts/check_shared_pitfalls_structure.py --file /tmp/shared_CORRUPT.md; echo "sister exit=$?"

# ③ 两个版本各跑一次**完好样本**（防止「永远 FAIL」也要防）
/usr/bin/python3 <our_repo>/scripts/check_shared_pitfalls_structure.py; echo "ours clean exit=$?"
/usr/bin/python3 <sis_repo>/scripts/check_shared_pitfalls_structure.py; echo "sister clean exit=$?"

# ④ 采纳「能报出损坏」的那个版本；若两个都报不出 ⇒ **两个都坏**，必须自己写判据
# ⑤ 同步后 sha1 双向核对（§陷阱 37 的三问之三）
sha1sum <our>/scripts/check_shared_pitfalls_structure.py \
        <sis>/scripts/check_shared_pitfalls_structure.py
```

### 判读表

| 损坏样本 | 完好样本 | 结论 | 动作 |
|---|---|---|---|
| exit 1 | exit 0 | ✅ **好版本** | 采纳它 |
| exit 0 | exit 0 | ❌ **假绿**（漏报真损坏） | 换版本 |
| exit 1 | exit 1 | ❌ **恒红**（把正常当损坏，§陷阱 47） | 换版本 / 修判据 |
| exit 0 | exit 1 | ❌ **恒绿**（什么都不查） | 两个都坏 → 自己写判据 |

> ⚠️ **「恒红」与「恒绿」同样无用**（§陷阱 47）。只跑完好样本会漏掉「假绿」；
> 只跑损坏样本会漏掉「恒红」。**两个样本都要跑。**

## ⚠️ 三个必须避开的坑

### 坑 1：只跑**完好样本**验收 → 假绿查不出来

「在两个真实文件上都 PASS」**不能证明脚本有用** —— 一个什么都不查的脚本也 PASS。
⇒ **必须额外造一个损坏样本**。

### 坑 2：直接粘贴判据 → `NameError`

姊妹版依赖 `SIG_LINES` / `nonempty` 等**辅助定义**。
若只粘贴「判据那一段」而不带定义 ⇒ 运行时 `NameError`。
⇒ **移植整个判据块（含常量与辅助函数），或直接采纳整个文件。**

### 坑 3：以为姊妹的成品就是可用的成品

姊妹 KB 自己的 cron 与本 cron 同窗口跑 ⇒ 姊妹那边「刚固化 / 刚重写」的状态
**可能还没被任何人验证过**（§陷阱 46 的同一根因）。
⇒ **凡是「从姊妹那边拿过来」的东西，都要当未经测试的第三方代码对待。**

## 📌 与既有陷阱的关系

| 陷阱 | 管什么 | 本条补什么 |
|---|---|---|
| §陷阱 23 | 共享**文档**同步方向（姊妹独有行 = 0 ⇒ cp） | —— |
| §陷阱 45 | 共享**脚本**同步方向（变化行是否全部相关） | **方向对了，还需验证「对错」** |
| §陷阱 46 | 新脚本入库前必须真跑一次 | 本条把「跑」拆成**完好样本 + 损坏样本**两遍 |
| §陷阱 47 | 恒红比没脚本更危险 | 本条补上**恒绿**这一侧（假绿 = 漏报真损坏） |
| §陷阱 48 | 移植重写版可能丢判据 | **本条是它的可执行版本** |

## 📌 产物位置

- 共享文档：`references/shared-proxy-service-pitfalls.md` §陷阱 48
- 姊妹版脚本：`scripts/check_shared_pitfalls_structure.py`
- 回归测试：`scripts/test_shared_pitfalls_structure.py`
  （**入库前必须真跑一次**：case1 完好 → exit 0；case2 末尾孤儿体 → exit 1）
- 本轮现场全记录：`references/crawl-state-2026-11-26.md` §三②
