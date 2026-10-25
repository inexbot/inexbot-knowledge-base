# 产品图片检索指南

当用户问到"XXX 控制器/示教器长什么样"、"有图吗"、"外观尺寸"等图片类问题时适用。

## 已知模式

doc.inexbot.com 的 VitePress 站点中，产品尺寸/外观图的引用路径格式为：
```
assets/Pasted image YYYYMMDDHHMMSS.png
```

在 markdown 中写作：
```markdown
![说明](assets/Pasted image 20260303162528.png)
```

## 已知的图片 URL

| 产品 | 文件名 | 状态 |
|------|--------|------|
| C2200 控制器 | `assets/Pasted image 20260303162528.png` | ❌ 404（在静态 HTML 中路径失效） |

## 正确的在线获取方式

不要直接拼接 `doc.inexbot.com/assets/文件名`，因为 VitePress 的 assets 在静态导出后路径会失效。

**正确做法**：直接访问对应的在线页面，让浏览器渲染 VitePress 的运行时资源解析：
1. 访问 `https://doc.inexbot.com/<path>` （path 即 index.json 中的键，如 `/产品资料/控制系统/工业机器人控制器C2200系列`）
2. 检查页面中实际 `<img>` 标签的完整 URL（通常在 VitePress 运行时才解析出正确的 CDN 路径）

## 本地知识库的局限

当前爬虫只下载了 HTML 文本，**不会下载图片文件**。产品图片不会出现在 `~/.hermes/kb/inexbot/assets/` 中。

如果用户需要看图，回答策略：
1. 先检索知识库获取产品参数
2. 告知用户图片无法从本地知识库获取，提供官网链接让用户自行查看
3. 引导用户提供已有的图片，或联系纳博特技术支持获取正式产品资料包
