import os
import json
import re
import jieba
from collections import defaultdict

JSON_DIR = "json_dedupe"
OUTPUT_DIR = "index_data"

INVERTED_INDEX_FILE = os.path.join(OUTPUT_DIR, "inverted_index.json")
DOC_META_FILE = os.path.join(OUTPUT_DIR, "doc_meta.json")
STOPWORDS_FILE = "stopwords.txt"

def load_stopwords(path=STOPWORDS_FILE):
    stopwords = set()
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            w = line.strip()
            if w:
                stopwords.add(w)
    return stopwords

STOPWORDS = load_stopwords()


def tokenize(text):
    tokens = []
    # 匹配连续英文/数字 OR 连续中文字符
    pattern = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]+")
    for seg in pattern.findall(text):
        # 如果全为英文/数字，则直接当一个 token
        if re.fullmatch(r"[A-Za-z0-9]+", seg):
            w = seg.lower()
            tokens.append(w)
        else:
            # 纯中文片段，交给 jieba 做细分
            for w in jieba.lcut(seg):
                w = w.strip()
                if not w:
                    continue
                if w in STOPWORDS:
                    continue
                tokens.append(w)
    return tokens

# 构建倒排索引与文档元信息
def build_index():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    inverted_index = defaultdict(lambda: defaultdict(list))
    doc_meta = {}

    next_doc_id = 1

    # 遍历 JSON_DIR 下所有 .json 文件
    for fn in os.listdir(JSON_DIR):
        if not fn.lower().endswith(".json"):
            continue
        full_path = os.path.join(JSON_DIR, fn)
        with open(full_path, "r", encoding="utf-8") as f:
            try:
                records = json.load(f)
            except Exception as e:
                print(f"跳过无法解析的文件 {fn}：{e}")
                continue

        for rec in records:
            rec_type = rec.get("type", "html")
            title = rec.get("title", "").strip()
            url = rec.get("url", "").strip()
            snippet = ""

            # 区分 html vs document
            if rec_type == "html":
                content  = rec.get("content", "").strip()
                snippet  = content[:100] + ("..." if len(content) > 100 else "")
                raw_snap = rec.get("snapshot", "").strip()
            else:
                # document 类型只用 title 作为可检索内容
                content  = title
                snippet  = title[:100] + ("..." if len(title) > 100 else "")
                raw_snap = ""

            # 处理 snapshot 路径：
            if raw_snap:
                normalized = raw_snap.replace("\\", "/")
                prefix = "html_snapshots/"
                if normalized.startswith(prefix):
                    snap = normalized[len(prefix):]
                else:
                    snap = os.path.basename(normalized)
            else:
                snap = ""

            # 分配 doc_id
            doc_id = str(next_doc_id)
            next_doc_id += 1

            # 存储文档元信息
            doc_meta[doc_id] = {
                "title":    title,
                "url":      url,
                "snippet":  snippet,
                "type":     rec_type,
                "snapshot": snap
            }

            # 将 title + content 拼成一个大字符串，分词并记录位置
            full_text = f"{title} {content}"
            tokens_list = tokenize(full_text)
            for pos, term in enumerate(tokens_list):
                inverted_index[term][doc_id].append(pos)

    # 序列化写入磁盘
    serializable_index = {}
    for term, posting_dict in inverted_index.items():
        postings = []
        for doc_id, pos_list in posting_dict.items():
            postings.append((doc_id, pos_list))
        serializable_index[term] = postings

    with open(INVERTED_INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(serializable_index, f, ensure_ascii=False, indent=2)
    print(f"倒排索引已写入：{INVERTED_INDEX_FILE}，共 {len(serializable_index)} 个词条")

    with open(DOC_META_FILE, "w", encoding="utf-8") as f:
        json.dump(doc_meta, f, ensure_ascii=False, indent=2)
    print(f"文档元数据已写入：{DOC_META_FILE}，共 {len(doc_meta)} 篇文档")


if __name__ == "__main__":
    build_index()

