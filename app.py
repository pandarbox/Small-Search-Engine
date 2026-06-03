import os
import json
import re
import math
import datetime
import uuid
import jieba
from flask import Flask, request, render_template, redirect, url_for, send_from_directory, session, flash

INDEX_DIR = "index_data"
INVERTED_INDEX_FILE = os.path.join(INDEX_DIR, "inverted_index.json")
DOC_META_FILE = os.path.join(INDEX_DIR, "doc_meta.json")

SNAPSHOT_DIR = "html_snapshots"
QUERY_LOG = "query.log"
CLICK_LOG = "click.log"
USERS_FILE = "users.json"

app = Flask(__name__)
app.secret_key = "123"

# 加载倒排索引和文档元数据
print("正在加载倒排索引和文档元数据……")
with open(INVERTED_INDEX_FILE, "r", encoding="utf-8") as f:
    inverted_index = json.load(f)
with open(DOC_META_FILE, "r", encoding="utf-8") as f:
    doc_meta = json.load(f)


# 预计算：N、df、doc_norm（文档向量长度）
N = len(doc_meta)
df = {term: len(postings) for term, postings in inverted_index.items()}
doc_norm = {}
for term, postings in inverted_index.items():
    idf = math.log(N / df[term]) if df[term] > 0 else 0.0
    for doc_id, pos_list in postings:
        tf = len(pos_list)
        w = tf * idf
        doc_norm[doc_id] = doc_norm.get(doc_id, 0.0) + w * w
for doc_id in doc_norm:
    doc_norm[doc_id] = math.sqrt(doc_norm[doc_id])


# 加载/保存用户数据
def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_users(users_dict):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users_dict, f, ensure_ascii=False, indent=2)


# 为访客生成 user_id
@app.before_request
def ensure_user_session():
    if "visitor_id" not in session:
        session["visitor_id"] = "visitor_" + str(uuid.uuid4())

def tokenize(text):
    tokens = []
    pattern = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]+")
    for seg in pattern.findall(text):
        if re.fullmatch(r"[A-Za-z0-9]+", seg):
            tokens.append(seg.lower())
        else:
            for w in jieba.lcut(seg):
                if w.strip(): tokens.append(w.strip())
    return tokens


# 短语检索
def phrase_query(phrase, candidate_docs=None):
    terms = tokenize(phrase)
    if not terms:
        return []
    all_postings = [inverted_index.get(t, []) for t in terms]
    if not all_postings[0]: return []
    if candidate_docs is not None:
        all_postings[0] = [(d,p) for d,p in all_postings[0] if d in candidate_docs]
    if len(terms) == 1:
        return [d for d,_ in all_postings[0]]
    candidate = {d for d,_ in all_postings[0]}
    for i in range(1, len(terms)):
        prev = {d:pos for d,pos in all_postings[i-1]}
        curr_list = all_postings[i]
        if candidate_docs is not None:
            curr_list = [(d,p) for d,p in curr_list if d in candidate_docs]
        curr = dict(curr_list)
        new_cand = set()
        for doc in candidate:
            if doc in curr:
                shifted = {p+1 for p in prev.get(doc, [])}
                if shifted & set(curr[doc]):
                    new_cand.add(doc)
        if not new_cand: return []
        all_postings[i] = [(d,curr[d]) for d in new_cand]
        candidate = new_cand
    return list(candidate)


# 通配检索
def wildcard_query(pattern, candidate_docs=None):
    regex = re.compile("^" + re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".") + "$" )
    counts = {}
    for term, postings in inverted_index.items():
        if regex.match(term):
            for doc,pos in postings:
                if not candidate_docs or doc in candidate_docs:
                    counts[doc] = counts.get(doc,0) + len(pos)
    return [d for d,_ in sorted(counts.items(), key=lambda x:-x[1])]


# 向量空间检索
def search_vsm(query, candidate_docs=None, top_k=50, boost_terms=None, boost_score=1.0):
    terms = tokenize(query)
    if not terms: return []
    tfidf_q = {}
    for t in terms:
        if t in df:
            fq=terms.count(t)
            idf=math.log(N/df[t])
            tfidf_q[t]=fq*idf
    norm_q=math.sqrt(sum(w*w for w in tfidf_q.values()))
    score={}
    for t,wq in tfidf_q.items():
        idf=math.log(N/df[t])
        for doc,pos in inverted_index.get(t,[]):
            if not candidate_docs or doc in candidate_docs:
                wd=len(pos)*idf
                score[doc]=score.get(doc,0)+wq*wd
    for doc in list(score):
        score[doc]=score[doc]/(norm_q*doc_norm.get(doc,1)) if norm_q and doc in doc_norm else 0
    if boost_terms:
        for doc in list(score):
            text=(doc_meta[doc]["title"]+" "+doc_meta[doc]["snippet"]).lower()
            if any(bt.lower() in text for bt in boost_terms): score[doc]+=boost_score
    return [d for d,_ in sorted(score.items(), key=lambda x:-x[1])[:top_k]]


# 记录查询日志
def log_query(user_id, query_text):
    rec = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user":      user_id,
        "query":     query_text
    }
    with open(QUERY_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# 读取历史查询
def read_history(user_id, top_n=10):
    history_list = []
    try:
        with open(QUERY_LOG, "r", encoding="utf-8") as f:
            lines = f.readlines()
        for line in reversed(lines):
            rec = json.loads(line.strip())
            if rec.get("user") == user_id:
                history_list.append(rec.get("query"))
                if len(history_list) >= top_n:
                    break
    except FileNotFoundError:
        pass
    return history_list


# 记录点击日志
@app.route("/click", methods=["POST"])
def click():
    data = request.get_json()
    doc_id = data.get("doc_id")
    user_id = session.get("username", session.get("visitor_id"))
    rec = {"user": user_id, "doc_id": doc_id}
    with open(CLICK_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return "", 204


# 读取点击日志：用于个性化排序
def read_clicks(user_id):
    clicked = set()
    try:
        with open(CLICK_LOG, "r", encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line.strip())
                if rec.get("user") == user_id:
                    clicked.add(rec.get("doc_id"))
    except FileNotFoundError:
        pass
    return clicked

def reorder_by_click(user_id, doc_ids):
    clicked_set = read_clicks(user_id)
    clicked_list = [d for d in doc_ids if d in clicked_set]
    others = [d for d in doc_ids if d not in clicked_set]
    return clicked_list + others


# /history 接口
@app.route("/history", methods=["GET"])
def history():
    user_id = session.get("username", session.get("visitor_id"))
    hist = read_history(user_id, top_n=10)
    return json.dumps(hist, ensure_ascii=False)


# /snapshot/<path:path>：展示本地保存的网页快照
@app.route("/snapshot/<path:path>")
def view_snapshot(path):
    return send_from_directory(os.path.abspath(SNAPSHOT_DIR), path)


# 注册页面：GET 显示表单，POST 处理注册信息
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        confirm  = request.form.get("confirm", "").strip()
        prefs    = request.form.get("prefs", "").strip()

        if not username or not password:
            flash("用户名和密码不能为空", "error")
            return redirect(url_for("register"))
        if password != confirm:
            flash("两次输入的密码不一致", "error")
            return redirect(url_for("register"))

        users = load_users()
        if username in users:
            flash("用户名已存在，请换一个", "error")
            return redirect(url_for("register"))

        # 解析用户偏好关键词
        if prefs:
            # 按逗号分割，去掉多余空格
            pref_list = [kw.strip() for kw in prefs.split(",") if kw.strip()]
        else:
            pref_list = []

        users[username] = {
            "password": password,
            "prefs": pref_list
        }
        save_users(users)
        flash("注册成功，请登录", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


# 登录页面：GET 显示表单，POST 验证身份
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        users = load_users()
        if username not in users or users[username]["password"] != password:
            flash("用户名或密码错误", "error")
            return redirect(url_for("login"))
        # 登录成功，存入 session
        session["username"] = username
        flash(f"欢迎，{username}", "success")
        return redirect(url_for("search_page"))
    return render_template("login.html")


# 登出
@app.route("/logout")
def logout():
    session.pop("username", None)
    flash("已登出", "info")
    return redirect(url_for("search_page"))


# /search 页面：GET 显示、POST 处理检索
@app.route("/", methods=["GET"])
def home():
    return redirect(url_for("search_page"))

@app.route("/search", methods=["GET", "POST"])
def search_page():
    query = ""      # 传给模板回显的“用户看到的输入框文字”
    results = []
    page = request.args.get("page", default=1, type=int)
    total_pages = None

    # 先读取当前登录用户名以获取偏好关键词
    username = session.get("username")
    users = load_users()
    if username and username in users:
        user_prefs = users[username].get("prefs", [])
    else:
        user_prefs = []

    if request.method == "POST":
        raw_q = request.form.get("q", "").strip()
        # 决定传给模板回显的内容
        prefix = "type:document "
        if raw_q.startswith(prefix):
            display_q = raw_q[len(prefix):].strip()
        else:
            display_q = raw_q

        # 先把 display_q 存到 query，传给模板回显
        query = display_q

        if raw_q:
            user_id = username if username else session.get("visitor_id")
            log_query(user_id, raw_q)

            # 如果以 type:document 开头，就只在文档集合里搜索
            if raw_q.startswith(prefix):
                actual_q = raw_q[len(prefix):].strip()
                candidate_docs = {doc_id for doc_id, meta in doc_meta.items() if meta.get("type") == "document"}
                matched = search_vsm(actual_q, candidate_docs, boost_terms=user_prefs, boost_score=1.0)
            else:
                matched = search_vsm(raw_q, None, boost_terms=user_prefs, boost_score=1.0)

            matched = reorder_by_click(user_id, matched)
            doc_ids_to_show = matched

            for doc_id in doc_ids_to_show:
                meta = doc_meta.get(doc_id, {})
                results.append({
                    "doc_id":   doc_id,
                    "title":    meta.get("title", ""),
                    "url":      meta.get("url", ""),
                    "snippet":  meta.get("snippet", ""),
                    "type":     meta.get("type", "html"),
                    "snapshot": meta.get("snapshot", "")
                })

    return render_template("search.html",
                           query=query,
                           results=results,
                           page=page,
                           total_pages=total_pages,
                           username=username)



# /suggest 路由：接受 GET 参数 prefix，返回 JSON 数组形式的候选联想词
@app.route("/suggest", methods=["GET"])
def suggest():
    prefix = request.args.get("prefix", "").strip().lower()
    if not prefix:
        return json.dumps([] , ensure_ascii=False)

    # 找出所有以 prefix 开头的 term
    candidates = []
    for term in inverted_index.keys():
        if term.startswith(prefix):
            candidates.append((term, df.get(term, 0)))
    if not candidates:
        return json.dumps([], ensure_ascii=False)

    # 按 df 降序排序，再按 term 字典序，最多取前 5 个
    candidates.sort(key=lambda x: (-x[1], x[0]))
    top_terms = [t for t, _ in candidates[:5]]

    return json.dumps(top_terms, ensure_ascii=False)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

