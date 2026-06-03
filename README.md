# 校内搜索引擎

这是一个基于 Python 和 Flask 的校内站点搜索引擎示例项目。项目包含站点爬取、网页快照保存、JSON 数据清洗/去重、倒排索引构建、向量空间检索、搜索联想、历史记录、用户注册登录和基于点击/偏好关键词的简单个性化排序。

当前配置主要面向南开大学多个二级站点，站点入口和文件类型规则可在 `config.json` 中调整。

## 功能概览

- 多站点并发爬取：从 `config.json` 中的入口 URL 开始，按域名白名单抓取页面。
- 网页快照：爬取 HTML 页面时保存本地快照到 `html_snapshots/`。
- 文档链接收集：识别 `.pdf`、`.doc`、`.docx`、`.xls`、`.xlsx` 等文档链接。
- 数据预处理：提供清洗异常内容、去重和大 JSON 切分等工具脚本。
- 倒排索引：使用 `jieba` 对中文分词，英文和数字按连续片段处理，生成倒排索引和文档元数据。
- 搜索服务：Flask Web 页面支持普通关键词检索、文档检索、搜索联想和历史搜索。
- 用户系统：支持注册、登录、登出，并可在注册时填写偏好关键词。
- 个性化排序：已点击结果会优先展示，用户偏好关键词会对结果加权。

说明：`app.py` 中已经定义了短语检索和通配检索函数，前端也有对应选项；但当前 `/search` 路由实际只接入了普通向量空间检索和 `type:document` 文档检索。如果需要完整启用短语/通配检索，需要在后端搜索分支中调用 `phrase_query()` 和 `wildcard_query()`。

## 项目结构

```text
.
├── app.py                  # Flask 搜索服务入口
├── build_index.py          # 根据 json_dedupe/ 构建倒排索引
├── config.json             # 爬虫站点、白名单和文件类型配置
├── requirements.txt        # Python 第三方依赖
├── worm.py                 # 多站点爬虫
├── templates/
│   ├── login.html          # 登录页
│   ├── register.html       # 注册页
│   └── search.html         # 搜索页
└── tool/
    ├── clean.py            # 清理乱码/异常 HTML 记录
    ├── unique.py           # JSON 内容去重
    ├── qiefen.py           # 大 JSON 数组切分
    └── countnumber.py      # 统计 JSON 记录数量
```

运行过程中会生成或依赖以下目录/文件：

```text
html_snapshots/             # 爬虫保存的网页快照
json/                       # 爬虫原始 JSON 输出
json_cleaned/               # clean.py 输出目录
json_dedupe/                # uinque.py 输出目录，也是 build_index.py 的输入目录
index_data/
├── inverted_index.json     # 倒排索引
└── doc_meta.json           # 文档元数据
state/                      # 爬虫断点状态
query.log                   # 查询日志
click.log                   # 点击日志
users.json                  # 用户数据
stopwords.txt               # 停用词表，build_index.py 运行前需要准备
```

## 环境准备

```bash
pip install -r requirements.txt
```

## 运行流程

### 1. 配置爬虫

编辑 `config.json`，确认 `sites` 中的 `start_url` 和 `domain_whitelist` 符合目标站点范围。

可选配置项包括：

- `document_suffixes`：识别为文档资源的后缀。
- `exclude_suffixes`：爬虫跳过的文件后缀。
- `max_workers`：并发爬取站点数量，默认 `10`。
- `max_total`：全局最大爬取记录数，默认 `120000`。
- `delay`：单站点请求间隔，默认 `0.5` 秒。
- `snapshot_dir`、`state_dir`、`json_dir`：输出目录，未配置时分别默认为 `html_snapshots`、`state`、`json`。

### 2. 爬取数据

```bash
python worm.py
```

爬虫会将结果写入 `json/`，并将 HTML 快照写入 `html_snapshots/`。

### 3. 清洗和去重

清理乱码或异常 HTML 记录：

```bash
python tool\clean.py
```

去重：

```bash
python tool\unique.py
```


### 4. 准备停用词表

`build_index.py` 会读取项目根目录下的 `stopwords.txt`。运行索引构建前请先准备该文件，每行一个停用词

### 5. 构建索引

```bash
python build_index.py
```

索引构建完成后会生成：

- `index_data/inverted_index.json`
- `index_data/doc_meta.json`

### 6. 启动搜索服务

```bash
python app.py
```

默认监听地址：

```text
http://127.0.0.1:5000/search
```

`app.py` 启动时会立即读取 `index_data/inverted_index.json` 和 `index_data/doc_meta.json`。如果索引文件不存在，服务会启动失败，需要先执行索引构建。

## 搜索说明

- 普通检索：直接输入中文或英文关键词。
- 文档检索：前端选择“文档检索”后，会自动添加 `type:document` 前缀，只在文档类型记录中搜索。
- 搜索联想：输入时调用 `/suggest?prefix=...`，从倒排索引词项中返回最多 5 个候选词。
- 历史搜索：访问 `/history` 获取当前用户最近查询。
- 点击记录：点击搜索结果时调用 `/click`，用于后续排序。
