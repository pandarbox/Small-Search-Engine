#清除掉含有乱码的 JSON 数组记录

import os
import json
import re

# 匹配任意控制字符（除 \n \r \t）或 U+FFFD 替换符
CTRL_RE = re.compile(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F\uFFFD]')
# 匹配 ZIP 文件头
ZIP_RE  = re.compile(r'PK\x03\x04')

def drop_corrupt_html(input_dir: str, output_dir: str):
    os.makedirs(output_dir, exist_ok=True)

    for fname in os.listdir(input_dir):
        if not fname.lower().endswith('.json'):
            continue

        in_path  = os.path.join(input_dir, fname)
        out_path = os.path.join(output_dir, fname)

        with open(in_path, 'r', encoding='utf-8') as rf:
            try:
                records = json.load(rf)
            except json.JSONDecodeError:
                print(f"[跳过] 无法解析: {fname}")
                continue

        cleaned = []
        removed = 0

        for rec in records:
            if rec.get('type') == 'html':
                content = rec.get('content', '')
                # 如果发现控制字符或 ZIP 头，则丢弃
                if CTRL_RE.search(content) or ZIP_RE.search(content):
                    removed += 1
                    continue
            cleaned.append(rec)

        with open(out_path, 'w', encoding='utf-8') as wf:
            json.dump(cleaned, wf, ensure_ascii=False, indent=2)

        total = len(records)
        kept  = len(cleaned)
        print(f"{fname}: 总 {total} 条，丢弃 {removed} 条 → 保留 {kept} 条")

if __name__ == '__main__':
    drop_corrupt_html(
      'json',
      'json_cleaned'
    )
