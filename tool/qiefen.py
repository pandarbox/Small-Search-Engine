#将大文件切分为小的文件

import ijson
import json

input_path = 'a'
output_prefix = 'a'
chunk_size = 10000

def split_json_array_stream(input_path, output_prefix, chunk_size):
    with open(input_path, 'r', encoding='utf-8') as f:
        # ijson.items(f, 'item') 用来逐个读取数组中的元素
        parser = ijson.items(f, 'item')

        chunk = []
        file_idx = 1
        for idx, item in enumerate(parser, start=1):
            chunk.append(item)
            if idx % chunk_size == 0:
                out_path = f'{output_prefix}{file_idx}.json'
                with open(out_path, 'w', encoding='utf-8') as wf:
                    json.dump(chunk, wf, ensure_ascii=False)
                print(f'写入 {out_path}，包含 {len(chunk)} 条记录')
                file_idx += 1
                chunk = []

        # 写出剩余不满 chunk_size 的部分
        if chunk:
            out_path = f'{output_prefix}{file_idx}.json'
            with open(out_path, 'w', encoding='utf-8') as wf:
                json.dump(chunk, wf, ensure_ascii=False)
            print(f'写入 {out_path}，包含 {len(chunk)} 条记录')

if __name__ == '__main__':
    split_json_array_stream(input_path, output_prefix, chunk_size)



