# doovvv · Personal Notes

首页参考 [Memory-Blog](https://github.com/LinMoQC/Memory-Blog) 的全屏背景、左侧自我介绍、右侧圆形头像布局，搭配已有山景照片和博客头像。顶部导航保持现有外观；文章列表沿用白底、皇家蓝与等宽字体。默认英文、浅色，可切换中文或深色模式。

中英切换覆盖导航、页面说明、分类、搜索、阅读控件和评论界面，浏览器会记住语言选择。文章标题、摘要、正文和目录保留原文。

## 本地预览

在本目录运行，或双击 `preview.cmd`：

```powershell
python -m http.server 8001 --bind 127.0.0.1
```

浏览器访问 <http://127.0.0.1:8001/>。页面使用站点根路径，应通过 HTTP 服务查看。

## 内容与构建

- `content/site.json`：20 篇已恢复文章的正文、标题、标签、日期，以及旧站页面路径。正文是发布后 HTML 的原样快照。
- `content/ui.json`：英文和中文界面文案；新增界面文字应同时补齐两种语言。
- `assets/i18n.js`：界面翻译、语言记忆与评论表单语言同步；`assets/ui-messages.js` 由构建生成。
- `tools/build.py`：使用 Python 标准库生成页面、搜索索引与文章封面，无需安装构建依赖。
- `assets/site.css`：视觉样式与手机适配；颜色集中在文件开头的 CSS 变量中。
- `assets/fonts/`：本地 IBM Plex Mono 字体和 SIL Open Font License。
- `assets/site.js`：主题记忆、全文搜索、精选切换、手机菜单、阅读目录、代码复制和评论加载。
- `assets/images/`：本地摄影、文章配图和历史中找回的图片。
- `assets/vendor/`：本地 MathJax、Valine 及各自许可证。
- `assets/social-card.jpg`：1200 × 630 的分享预览图，渲染源保存在 `tools/social-card.html`。

修改内容或模板后运行：

```powershell
python tools/build.py
python -m unittest discover -s tests -v
node --test tests/i18n.test.cjs
node --check assets/site.js
node --check assets/i18n.js
```

构建会更新原有 46 条公开页面路径，并生成一页“关于”。`lib/pace/README.html` 是旧依赖中的说明文件，保持原样。已有文章的图片和 PDF 路径继续使用。

### 自动文章封面

首页、精选区、分页和标签列表统一使用文章正文里的第一张 `<img>` 图片作为封面。每次构建都会重新读取正文，无需填写单独的封面字段；后续新增文章或调整正文图片顺序时，也使用同一规则。

新图片可放在 `assets/uploads/`，在正文中使用 `<img src="/assets/uploads/文件名.jpg">` 引用，然后运行 `python tools/build.py`。也支持相对于文章路径的图片、外部图片链接和常见的 `data-src` 懒加载图片。

正文没有图片，或第一张本地图片尚未上传、无法恢复时，保留该主题的默认封面，不会跳过首图改用第二张。外部首图加载失败也会回退到默认封面。正文图片作为封面时保留原色并完整展示，避免公式或截图被裁切、反相。

`image_aliases` 保存已恢复图片的本地副本对应关系，文章正文和封面共用这一份配置。

## 部署

正式域名为 <https://doovvv.cn>，在 `content/site.json` 的 `url` 字段配置。生成结果是普通 HTML、CSS、JavaScript 与本地资源，通过 `doovvv/doovvv.github.io` 仓库的 `main` 分支根目录部署。`.nojekyll` 已包含在项目中。

仓库根目录的 `CNAME` 文件保留一行 `doovvv.cn`，每次发布都应随其他文件一起提交。`python tools/build.py` 会原地更新生成页面并保留这个文件。

本地开发副本在 `D:\Blog\redesign`，分支为 `ui/memory-inspired`。已同步远端的域名绑定提交 `74fd834`；原始恢复备份仍在 `D:\Blog\website`。

## 保留的限制

旧站 40 张从未上传的 Typora 本地图片无法恢复，页面会显示“原图片暂缺”。两张在历史提交中找回的图片和两张外链文章图片，已接入本地副本。

评论沿用原站的 Valine 后端及路径，点击“展开评论”后才加载，不会迁移或新建评论数据库。评论服务的可用性取决于原来的后端。

## 素材

视觉参考：[LinMoQC/Memory-Blog](https://github.com/LinMoQC/Memory-Blog) 的首页构图、[nuonuo-888/devportfolio](https://github.com/nuonuo-888/devportfolio) 的文章区风格。当前布局和样式在现有静态生成器中重新实现，无需安装参考项目的框架依赖。

此前使用的摄影素材来自 Unsplash，保留在本地素材目录中：

- [日间山谷与雪峰](https://images.unsplash.com/photo-1464822759023-fed622ff2c3b)
- [雪山与星空](https://images.unsplash.com/photo-1519681393784-d120267933ba)
- [建筑](https://images.unsplash.com/photo-1487958449943-2429e8be8625)
- [森林](https://images.unsplash.com/photo-1441974231531-c6227db76b6e)

线条图标与七种文章封面为代码绘制的 SVG。文章继续保留原站的 CC BY-NC-SA 4.0 声明；第三方依赖的许可证随文件保存。
