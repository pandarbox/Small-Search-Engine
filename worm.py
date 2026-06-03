import os
import time
import json
import chardet
import threading
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor

with open("config.json", encoding="utf-8") as f:
    cfg = json.load(f)

SITES = cfg.get("sites", [])
EXCLUDE_SUFFIXES = tuple(cfg.get("exclude_suffixes", []))
DOCUMENT_SUFFIXES = tuple(cfg.get("document_suffixes", []))
SNAPSHOT_DIR = cfg.get("snapshot_dir",  "html_snapshots")
STATE_DIR = cfg.get("state_dir",     "state")
JSON_DIR = cfg.get("json_dir",      "json")
BATCH_SIZE = cfg.get("batch_size",    50)     # 每 50 条写一次 JSON
STATE_INTERVAL = cfg.get("state_interval",30)     # 每 30 秒写一次 state

os.makedirs(STATE_DIR,    exist_ok=True)
os.makedirs(SNAPSHOT_DIR, exist_ok=True)
os.makedirs(JSON_DIR,     exist_ok=True)

total_count = 0
total_lock = threading.Lock()
stop_event = threading.Event()
MAX_TOTAL = cfg.get("max_total", 120000)

# 启动时累加已有 JSON 条目数
for fn in os.listdir(JSON_DIR):
    if fn.endswith(".json"):
        try:
            with open(os.path.join(JSON_DIR, fn), "r", encoding="utf-8") as jf:
                total_count += len(json.load(jf))
        except:
            pass
print(f"启动时已加载历史数据，total_count = {total_count}")

def is_valid_url(url: str) -> bool:
    p = urlparse(url)
    return p.scheme in ("http","https") and bool(p.netloc)

def get_page(url: str, timeout: float=10.0):
    resp = requests.get(url, timeout=timeout)
    enc = chardet.detect(resp.content)["encoding"] or "utf-8"
    resp.encoding = enc
    return resp

def save_html_to_file(site_name: str, url: str, html: str) -> str:
    out = os.path.join(SNAPSHOT_DIR, site_name)
    os.makedirs(out, exist_ok=True)
    name = urlparse(url).path.strip("/") or "index"
    base = os.path.join(out, os.path.basename(name)+".html")
    fn   = base
    i = 1
    while os.path.exists(fn):
        fn = f"{os.path.splitext(base)[0]}_{i}.html"
        i += 1
    with open(fn, "w", encoding="utf-8") as f:
        f.write(html)
    return os.path.relpath(fn)

def load_state(site_name: str):
    fn = os.path.join(STATE_DIR, f"{site_name}_state.json")
    if os.path.exists(fn):
        with open(fn,"r",encoding="utf-8") as f:
            st = json.load(f)
        return set(st.get("visited",[])), st.get("queue",[])
    return None, None

def save_state(site_name: str, visited, queue):
    fn = os.path.join(STATE_DIR, f"{site_name}_state.json")
    with open(fn,"w",encoding="utf-8") as f:
        json.dump({"visited": list(visited), "queue": queue}, f, ensure_ascii=False, indent=2)

#爬虫主逻辑
def crawl_site(site_cfg):
    global total_count
    start_url = site_cfg["start_url"]
    whitelist = site_cfg.get("domain_whitelist", [])
    site_name = urlparse(start_url).netloc.replace(".", "_")
    json_path = os.path.join(JSON_DIR, f"{site_name}.json")

    # 加载已有结果和状态
    if os.path.exists(json_path):
        with open(json_path,"r",encoding="utf-8") as jf:
            results = json.load(jf)
    else:
        results = []
    visited, queue = load_state(site_name)
    if visited is None:
        visited = set(e["url"] for e in results)
        queue   = [start_url]
    last_state_save = time.time()
    unsaved_count = 0

    while queue and not stop_event.is_set():
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)

        old_len = len(results)
        try:
            resp = get_page(url)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                # 遍历 <a>
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    full = href if is_valid_url(href) else urljoin(url, href)
                    if not is_valid_url(full):
                        continue
                    p2 = urlparse(full)
                    # 文档链接
                    if any(p2.path.lower().endswith(ext) for ext in DOCUMENT_SUFFIXES):
                        text = a.get_text(strip=True)
                        title = text or os.path.basename(p2.path) or full
                        results.append({
                            "source": site_name,
                            "type":   "document",
                            "title":  title,
                            "url":    full
                        })
                    # 普通页面
                    elif any(dom in p2.netloc for dom in whitelist) \
                         and not p2.path.lower().endswith(EXCLUDE_SUFFIXES + DOCUMENT_SUFFIXES):
                        if full not in visited and full not in queue:
                            queue.append(full)
                # 保存页面快照
                snap = save_html_to_file(site_name, url, resp.text)
                title   = soup.title.string.strip() if soup.title else ""
                content = soup.get_text(strip=True, separator=" ")
                results.append({
                    "source":   site_name,
                    "type":     "html",
                    "url":      url,
                    "title":    title,
                    "content":  content,
                    "snapshot": snap
                })
            else:
                pass

            # 计算本次新增条数
            delta = len(results) - old_len
            if delta:
                unsaved_count += delta
                with total_lock:
                    total_count += delta
                    print(f"▶ 全局已爬取 total_count = {total_count}")
                    if total_count >= MAX_TOTAL:
                        stop_event.set()

            now = time.time()
            # 触发批量写 JSON 或定时写 STATE
            if unsaved_count >= BATCH_SIZE:
                with open(json_path,"w",encoding="utf-8") as jf:
                    json.dump(results, jf, ensure_ascii=False, indent=2)
                unsaved_count = 0
                print(f"[{site_name}] 批量写入 JSON，共 {len(results)} 条")
            if now - last_state_save > STATE_INTERVAL:
                save_state(site_name, visited, queue)
                last_state_save = now
                print(f"[{site_name}] 定时保存状态，queue 剩余 {len(queue)} 条")

            time.sleep(cfg.get("delay",0.5))

        except Exception as e:
            print(f"[{site_name}] 错误({url}): {e}")
            save_state(site_name, visited, queue)

    # 爬完或停止后，写入剩余结果 & 删除 state 文件
    if unsaved_count > 0:
        with open(json_path,"w",encoding="utf-8") as jf:
            json.dump(results, jf, ensure_ascii=False, indent=2)
    save_state(site_name, visited, queue)
    stf = os.path.join(STATE_DIR, f"{site_name}_state.json")
    if os.path.exists(stf):
        os.remove(stf)
    print(f"[{site_name}] 完成，总计 {len(results)} 条")

#并发启动
if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=cfg.get("max_workers",10)) as execu:
        for site in SITES:
            execu.submit(crawl_site, site)


