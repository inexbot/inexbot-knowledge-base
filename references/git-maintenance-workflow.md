# Git 维护工作流

## 拉取远程更新（本地有修改时）

当 skill 目录有本地修改 + 新文件，标准 `git pull` 会失败。正确步骤：

```bash
cd ~/.hermes/skills/<category>/<skill-name>

# 1. 确认当前状态（是否落后 origin/main）
git fetch origin main   # 必须先 fetch，否则 origin/main 是上次缓存的旧指针
git status -sb           # 看 "## branch...origin/branch" 后面有没有落后标记

# 2. 强制同步到远程（丢失本地修改）
git reset --hard origin/main

# 3. 验证
git log --oneline -3     # 确认已同步到 origin/main
```

> **为什么不用 `git pull`**：网络超时或大仓库时 `git pull` 容易卡住。`git fetch` + `git reset --hard` 可以精确控制，超时后重试成本低。
> **为什么必须先 `fetch`**：`git reset --hard origin/main` 使用本地缓存的 origin 指针，未 fetch 时 origin/main 不会更新，等于什么都没拉。

## 备份本地修改

如果需要保留本地定制化内容：

```bash
# 备份
cp SKILL.md /tmp/SKILL.md.local

# 强制同步
git fetch origin main && git reset --hard origin/main

# 恢复
cp /tmp/SKILL.md.local SKILL.md
```

> `git stash` 只能处理已跟踪文件的修改，无法处理"untracked files will be overwritten"错误（新增文件与远程冲突）。上述流程更可靠。

## 验证

```bash
git diff origin/main   # 确认本地 diff 符合预期
git log --oneline -3   # 确认已同步到 origin/main
```
