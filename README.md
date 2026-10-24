# SEP Converter

[![Python checks](https://github.com/npc0451/sep-converter/actions/workflows/tests.yml/badge.svg)](https://github.com/npc0451/sep-converter/actions/workflows/tests.yml)

将 Stanford Encyclopedia of Philosophy（SEP）的文章网页转换为 EPUB、PDF 或 UTF-8 TXT。提供中文 Tkinter GUI、交互命令行、单篇/多篇转换与合并输出。

**仅供学习、研究与个人非商业使用。请先阅读 [版权与使用声明](NOTICE.md)。**

这是轻量网页转换工具，不包含本地文库、数据库、分类、翻译或全站归档功能。PDF 由公开文章 HTML 生成；不是下载 Friends of the SEP 的会员 PDF，不绕过登录或付费访问。

## 安装和启动 GUI

需要 Python 3.11 或更新版本，并提供 Tkinter 图形组件。这是 Python 源码项目，不包含独立 EXE 或 BAT 启动器。

1. 在仓库点击 **Code → Download ZIP**，完整解压源码。不要在压缩包内部运行。
2. 在项目目录打开终端，安装依赖：

   ```bash
   python -m pip install -r requirements.txt
   ```

3. 启动中文 GUI：

   ```bash
   python sep.py --gui
   ```

   直接运行 `python sep.py` 也会优先启动 GUI。如果环境中的命令叫 `python3`，将上述 `python` 换成 `python3`。
4. 在“词条链接”中每行粘贴一篇文章 URL，例如 `https://plato.stanford.edu/entries/descartes/`。选择 EPUB、PDF 或 TXT，选择“每篇一个文件”或“多篇合并为一个文件”，并设置“保存目录”。
5. 合并模式可填写文件名，不用加扩展名；留空自动命名。点击“开始转换”，查看“运行记录”。出现“已生成 N 个文件”后，到保存目录打开结果。

PDF/EPUB 可选择嵌入图片；TXT 只保留图片说明和来源，不下载图片，因此图片选项自动禁用。首次转换会先核实 robots.txt；相邻网络请求至少相隔 5 秒，日志暂时不更新不一定表示卡住。请等待当前转换完成后关闭窗口。

如果 GUI 无法启动，在终端运行 `python -m tkinter` 检查图形组件；缺少 Tkinter 时需为当前 Python 环境安装对应组件。提示 `No module named ...` 时检查依赖是否安装在同一 Python 环境。也可以执行 `python sep.py --cli` 使用命令行向导。

## 命令行

```powershell
# 单篇 PDF
python sep.py https://plato.stanford.edu/entries/descartes/ -f pdf -o output

# 多篇合并 PDF
python sep.py https://plato.stanford.edu/entries/lacan/ https://plato.stanford.edu/entries/descartes/ -f pdf -m merge --name reading -o output

# EPUB（默认嵌入图片）
python sep.py https://plato.stanford.edu/entries/descartes/ -f epub -o output

# TXT（保留文字、章节、公式源表达和表格文本；不下载图片）
python sep.py https://plato.stanford.edu/entries/descartes/ -f txt -o output

# 多篇合并 TXT
python sep.py https://plato.stanford.edu/entries/lacan/ https://plato.stanford.edu/entries/descartes/ -f txt -m merge --name reading -o output

# 交互命令行向导
python sep.py --cli

# 独立 PDF / EPUB 入口
python sep2pdf.py https://plato.stanford.edu/entries/descartes/ -o output/descartes.pdf
python sep2epub.py --embed-images https://plato.stanford.edu/entries/descartes/ -o output/descartes.epub
python sep2txt.py https://plato.stanford.edu/entries/descartes/ -o output/descartes.txt
```

独立的 `sep2epub.py` 沿用旧行为，须显式传入 `--embed-images` 才嵌入图片。统一入口 `sep.py` 默认开启。

## 下载规则

只访问 `plato.stanford.edu`，主文、图片与重定向共享至少 5 秒的请求间隔，并服从 robots.txt 的更严格限制。禁止跨站重定向。403 停止后续下载；429 按 Retry-After 冷却。程序不无限重试，失败原因显示在日志中。

PDF 渲染阶段不允许自行下载资源，图片在抓取阶段嵌入；图片失败或未选择嵌入时，PDF 显示替代说明。生成使用临时文件，成功后替换成品，避免错误输出覆盖已有文件。

每次转换独立抓取，不维护本地缓存；换格式后重新转换会重新请求文章。这是本项目的设计范围。

## 内容与排版限制

- 保留主页面可解析的标题、发表信息、正文、章节、表格和图片。此初版不递归收集独立脚注页及补充文档，不承诺整篇所有依赖完全离线。
- PDF 使用 xhtml2pdf，支持常规文本、图片和简单表格；复杂 CSS、SVG 动画、JavaScript 与 MathJax 公式不保证正确呈现。不会把这个后端描述为官网 PDF 的等价副本。
- 默认使用系统/内置字体。不打包未经核对许可的字体。部分语言字符可能需要用户自行配置字体。
- 图片抓取失败会输出 WARNING；来源页面仍可正常转出文字，因此应查看日志。robots 限制的资源不会绕过下载。
- 不附带 SEP 全文、生成的电子书、下载词典、个人资料或账号信息。

## 项目文件

`sep.py` 为统一入口，`sep_gui.py` / `sep_cli.py` 是前端，`sep_app.py` 组织任务，`sep_common.py` 解析正文，`sep_network.py` 管理下载规则，`sep2epub.py` / `sep2pdf.py` / `sep2txt.py` 负责输出。项目不引用父目录或其他文库项目。

## 测试

```powershell
python -m unittest discover -s tests -v
```

测试使用自建 HTML 和模拟网络，检查 PDF/EPUB/TXT、图片、表格、多篇合并、限速与失败保护，默认不请求官网。GitHub Actions 使用同一套测试。

## 权利说明

此代码与 Stanford University、SEP 没有官方隶属关系。文章及图片著作权属于原权利人。请遵守 [SEP 使用条款](https://plato.stanford.edu/info.html#terms)，生成文件供个人阅读，不将公开可读误解为可任意再分发。

完整说明见 [NOTICE.md](NOTICE.md)。本项目仅供学习、研究与个人非商业使用，未附通用开源许可证，不应标为 MIT 等许可。第三方依赖遵循各自许可证。“仅供学习”的标注不替代 SEP 或其他权利人的授权。

## 常见问题

- **PDF 和官网会员 PDF 一样吗？** 不是。这是从公开网页重新排版生成的文件。
- **为什么图片缺失？** 查看 WARNING 日志。资源可能被 robots 禁止、下载失败或不受当前格式支持。程序不会绕过访问限制。
- **为什么复杂公式显示不正确？** 此初版 PDF 后端不执行 MathJax。请用官网核对公式；不要把转换结果当作完整的数学排版副本。
- **能一次输入多篇吗？** 可以，每行一篇；“每篇一个文件”分别生成，“多篇合并为一个文件”合并输出。
- **TXT 能保存什么？** 可保存标题、来源、发表信息、可解析正文、章节、表格文字、图片说明及已保留的公式源表达。表格以制表符分列，不保留网页视觉样式；不额外下载图片。
- **为什么导出不同格式又请求网页？** 本项目不带缓存或文库；每次转换都是独立操作。
- **如何关闭窗口？** 等待当前转换完成后关闭，避免中断生成。原有成品不会在失败时被未完成文件替换。
- **能直接上传哪些文件？** 源码、测试、使用说明和声明可以整理备份。不要附带文章全文、生成电子书、下载词典、字体、虚拟环境或个人配置。
