# MineruCustom

MineruCustom 是一套用于 PDF 提取内容的后处理工具集，基于 MinerU 框架，提供了丰富的功能用于处理和优化从 PDF 中提取的内容，使其更适合在 Markdown 格式中展示。

## 主要功能

### 核心功能

- **middle.json 处理**：处理 middle.json 中的 discarded_blocks，将页面底部内容合并到正文
- **中间数据转换**：将 middle.json 转换为 content_list.json 或 Markdown 文件
- **脚注处理**：从 discarded_blocks 中提取和处理脚注，并添加到 Markdown 文档中

### 工具功能

- **图片 OCR 替换**：将 Markdown 中的图片引用替换为 OCR 内容
- **脚注合并**：将页码标记和脚注内容合并到一个文档中
- **页面标记生成**：为 Markdown 文档添加页码标记
- **内容格式化**：优化 Markdown 内容结构和格式

## 项目结构

```
minerucustom/
├── __init__.py          # 包初始化文件
├── __main__.py          # 主入口文件
├── core/                # 核心处理模块
│   ├── middle2content.py    # middle.json 转换为 content_list.json
│   ├── middle2md.py         # middle.json 直接转换为 Markdown
│   └── reprocess_discarded.py  # 处理 discarded_blocks
├── tool/                # 工具模块
│   ├── content2md.py        # content_list.json 转换为 Markdown
│   ├── footnotes2mineru.py  # 处理脚注
│   ├── generate_footnote_md.py  # 生成脚注 Markdown
│   ├── generate_page_md.py  # 生成页码标记 Markdown
│   ├── merge_footnotes.py   # 合并页码和脚注
│   └── model2middle.py      # 模型数据转换
└── utils/               # 工具函数
    └── image2mineru.py      # 图片 OCR 替换功能
```

## 使用方法

### 安装

```bash
# 从当前目录安装
pip install -e .
```

### 基本使用流程

1. **处理 middle.json 文件**

   ```bash
   python -m minerucustom
   ```
   
   根据交互式提示选择 middle.json 文件，并设置处理参数。

2. **脚注处理**

   ```bash
   python -m minerucustom.tool.footnotes2mineru
   ```
   
   根据提示选择 middle.json 和对应的 Markdown 文件，设置相似度阈值和其他参数。

3. **图片 OCR 替换**

   ```bash
   python -m minerucustom.utils.image2mineru
   ```
   
   选择主 Markdown 文件和包含 OCR 内容的文件夹。

## 主要功能详解

### 脚注处理

脚注处理工具会从 middle.json 的 discarded_blocks 中提取脚注内容，并根据上下文匹配将它们插入到 Markdown 文档的适当位置。支持以下特性：

- 根据相似度匹配上下文
- 按页码插入或按关键词匹配插入
- 可定制化的脚注格式
- 预设管理，保存和加载处理参数

### discarded_blocks 处理

通过设置页面底部百分比阈值，将页面底部的 discarded_blocks 移动到 para_blocks，解决因排版问题被错误分类为 discarded 的内容。

### 图片 OCR 替换

将 Markdown 文档中的图片引用替换为对应的 OCR 文本内容，并可选择性地合并图片文件。

## 依赖项

- MinerU 核心库（magic_pdf）
- rich - 用于交互式界面
- tqdm - 进度条显示
- rapidfuzz - 用于文本相似度匹配

## 注意事项

- 本工具需要配合 MinerU 框架使用
- 处理大文件时可能需要较多内存
- 建议在处理前备份原始文件