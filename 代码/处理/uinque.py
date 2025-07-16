import os
import json

def dedupe_json_folder(clean_dir: str, dedup_dir: str):
    os.makedirs(dedup_dir, exist_ok=True)
    seen_contents = set()

    for fname in os.listdir(clean_dir):
        if not fname.lower().endswith('.json'):
            continue

        in_path  = os.path.join(clean_dir, fname)
        out_path = os.path.join(dedup_dir, fname)

        with open(in_path, 'r', encoding='utf-8') as rf:
            try:
                records = json.load(rf)
            except json.JSONDecodeError:
                print(f"[跳过] 无法解析: {fname}")
                continue

        deduped = []
        removed = 0
        for rec in records:
            content = rec.get('content')
            # 如果 content 已见，跳过；否则保留并记录
            if content is not None and content in seen_contents:
                removed += 1
                continue
            if content is not None:
                seen_contents.add(content)
            deduped.append(rec)

        # 写入去重后的 JSON
        with open(out_path, 'w', encoding='utf-8') as wf:
            json.dump(deduped, wf, ensure_ascii=False, indent=2)

        total = len(records)
        kept  = len(deduped)
        print(f"{fname}: 共 {total} 条 → 去重后 {kept} 条（移除 {removed} 条）")


if __name__ == '__main__':
    dedupe_json_folder(
        'json',     # 输入目录
        'json_dedupe'    # 输出目录
    )
