import os
import json

DATA_DIR = r"D:\web搜索引擎\json_dedupe"
ARRAY_EXTS = {".json"}

def count_in_array_file(path):
    """一次性读取整个 JSON 数组文件，返回元素个数。"""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        data = json.load(f)
        if isinstance(data, list):
            return len(data)
        else:
            # 如果不是数组，就当作 1 条记录
            return 1

def main():
    total = 0
    for root, _, files in os.walk(DATA_DIR):
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            full = os.path.join(root, fn)
            try:
                c = count_in_array_file(full)
                print(f"{fn}: {c} 条记录")
                total += c
            except Exception as e:
                print(f"跳过 {fn}（{e}）")

    print("="*40)
    print(f"所有 JSON 文件共计 {total} 条记录")

if __name__ == "__main__":
    main()
