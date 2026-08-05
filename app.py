#!/usr/bin/env python3
"""灵感收件箱 — 打字/粘贴 → AI自动分类 → 带日期归档"""
import os, re, json, shutil, urllib.request, urllib.error, zipfile, io
from datetime import date, datetime
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel

BASE_DIR = Path(__file__).parent
MEMO_DIR = BASE_DIR / "memos"
CAT_FILE = BASE_DIR / "categories.json"

# 默认分类（首次运行 / 文件缺失时用）
DEFAULT_CATEGORIES = ["日记", "自媒体选题", "好句", "小说灵感", "摘录", "Todo", "其他"]


def load_categories() -> list:
    """读取分类列表（有序）。保证『其他』兜底分类永远存在。"""
    if CAT_FILE.exists():
        try:
            data = json.loads(CAT_FILE.read_text(encoding="utf-8"))
            cats = data.get("categories", [])
            if cats:
                # 保证『其他』存在（用户可能删了或改名，兜底需要它）
                if "其他" not in cats:
                    cats.append("其他")
                    save_categories(cats)
                return cats
        except Exception:
            pass
    save_categories(DEFAULT_CATEGORIES)
    return list(DEFAULT_CATEGORIES)


def save_categories(cats: list) -> None:
    CAT_FILE.write_text(json.dumps({"categories": cats}, ensure_ascii=False, indent=2), encoding="utf-8")


def build_classify_prompt(cats: list) -> str:
    """根据动态分类列表生成 AI 分类 prompt。每类一行说明；无法匹配的归入『其他』。"""
    lines = ["你是一个内容分类助手。请将下面用户随手记的内容，分类到以下类别之一，并给出一个简短主题标签。", ""]
    for c in cats:
        if c == "其他":
            continue
        desc = {
            "日记": "个人日记、心情记录、当天发生的事情",
            "自媒体选题": "适合做短视频/文章/公众号的内容选题、点子、标题",
            "好句": "一句或一段有感染力的话，适合摘抄收藏（注意：如果是\"觉得某句话好\"的评论，则归入摘录）",
            "小说灵感": "故事设定、人物、情节、世界观、对话点子等小说创作素材",
            "摘录": "从书/文章/视频里摘抄的好内容（原文引用）",
            "Todo": "待办事项、要做的事、提醒",
        }.get(c, "")
        if desc:
            lines.append(f"- {c}：{desc}")
    lines.append("- 其他：不属于以上任何类")
    lines.append("")
    lines.append(f"只输出 JSON，格式：{{\"category\": \"{'|'.join(cats)}\", \"topic\": \"简短主题标签，4-10个字\"}}")
    lines.append("")
    lines.append("内容：")
    return "\n".join(lines)


# API 配置 — 优先读环境变量（云端部署），回退到本地 settings.json
def _load_settings():
    api_base = os.environ.get("ANTHROPIC_BASE_URL", "")
    api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
    if api_base and api_key:
        return api_base, api_key
    try:
        s = json.loads((Path.home() / ".claude/settings.json").read_text())
        env = s.get("env", {})
        return env.get("ANTHROPIC_BASE_URL", "https://www.ccsub.net"), env.get("ANTHROPIC_AUTH_TOKEN", "")
    except Exception:
        return "https://www.ccsub.net", ""


API_BASE, API_KEY = _load_settings()
MODEL = "claude-haiku-4-5"  # 便宜、快、不思考，分类足够


class MemoIn(BaseModel):
    text: str
    source: str = "web"


def classify(text: str) -> dict:
    """调用 AI 分类，返回 {"category": ..., "topic": ...}。失败自动重试最多2次。"""
    cats = load_categories()
    prompt = build_classify_prompt(cats)
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt + text}],
        "max_tokens": 300,
        "temperature": 0.2,
    }).encode()
    req = urllib.request.Request(
        f"{API_BASE}/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
    )
    last_err = None
    for attempt in range(3):  # 首次 + 重试2次
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
            content = data["choices"][0]["message"]["content"]
            # 提取 JSON（模型偶尔会带 ```json 包裹或多余文字）
            m = re.search(r"\{.*\}", content, re.S)
            if not m:
                raise ValueError(f"无法解析分类结果: {content[:200]}")
            return json.loads(m.group(0))
        except Exception as e:
            last_err = e
            # 网络/解析失败才重试；连续3次失败则抛出
            if attempt < 2:
                import time
                time.sleep(1)
    raise last_err


def sanitize(name: str) -> str:
    """清理文件名非法字符"""
    return re.sub(r'[\\/:*?"<>|]', "", name).strip() or "未命名"


def save_memo(text: str, result: dict, source: str = "web") -> dict:
    """保存 memo 为 md 文件：memos/{类别}/{日期}-{主题}.md"""
    cats = load_categories()
    cat = result.get("category", "其他")
    if cat not in cats:
        cat = "其他"  # 兜底（load_categories 保证它存在）
    topic = result.get("topic", "未命名")
    now = datetime.now()
    today = now.date().isoformat()
    ttime = now.strftime("%H:%M")
    folder = MEMO_DIR / cat
    folder.mkdir(parents=True, exist_ok=True)
    fname = f"{today}-{sanitize(topic)}.md"
    path = folder / fname
    n = 1
    while path.exists():
        path = folder / f"{today}-{sanitize(topic)}-{n}.md"
        n += 1
    path.write_text(f"# {topic}\n\n> {text}\n\n- 日期: {today}\n- 时间: {ttime}\n", encoding="utf-8")
    return {"file": str(path.relative_to(MEMO_DIR)), "category": cat, "topic": topic, "time": ttime}


app = FastAPI(title="灵感收件箱")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# ---------- 分类管理 ----------

@app.get("/api/categories")
def api_categories():
    """返回分类列表（有序）"""
    cats = load_categories()
    return {"categories": cats}


class CategoryIn(BaseModel):
    name: str


@app.post("/api/categories")
def api_add_category(body: CategoryIn):
    """添加新分类"""
    name = sanitize(body.name)
    if not name:
        return JSONResponse({"error": "分类名不能为空"}, status_code=400)
    cats = load_categories()
    if name in cats:
        return JSONResponse({"error": "分类已存在"}, status_code=400)
    cats.append(name)
    save_categories(cats)
    (MEMO_DIR / name).mkdir(parents=True, exist_ok=True)
    return {"categories": cats}


class CategoryRename(BaseModel):
    old: str
    new: str


@app.put("/api/categories/rename")
def api_rename_category(body: CategoryRename):
    """改名：更新配置 + 重命名 memos 文件夹"""
    old = sanitize(body.old)
    new = sanitize(body.new)
    if not new or old == new:
        return JSONResponse({"error": "新分类名无效"}, status_code=400)
    cats = load_categories()
    if old not in cats:
        return JSONResponse({"error": "分类不存在"}, status_code=404)
    if new in cats:
        return JSONResponse({"error": "新分类名已存在"}, status_code=400)
    cats = [new if c == old else c for c in cats]
    save_categories(cats)
    old_dir = MEMO_DIR / old
    if old_dir.is_dir():
        old_dir.rename(MEMO_DIR / new)
    return {"categories": cats}


class CategoryOrder(BaseModel):
    categories: list


@app.put("/api/categories/order")
def api_order_categories(body: CategoryOrder):
    """排序：接收完整有序分类列表，校验后保存"""
    new_cats = [sanitize(c) for c in body.categories if sanitize(c)]
    existing = load_categories()
    if set(new_cats) != set(existing):
        return JSONResponse({"error": "分类列表不完整"}, status_code=400)
    save_categories(new_cats)
    return {"categories": new_cats}


@app.delete("/api/categories")
def api_delete_category(body: CategoryIn):
    """删除分类：移除配置 + 删除 memos 文件夹（含内容）。不删『其他』。"""
    name = sanitize(body.name)
    cats = load_categories()
    if name not in cats:
        return JSONResponse({"error": "分类不存在"}, status_code=404)
    if name == "其他":
        return JSONResponse({"error": "『其他』分类不能删除"}, status_code=400)
    cats.remove(name)
    save_categories(cats)
    folder = MEMO_DIR / name
    if folder.is_dir():
        shutil.rmtree(folder)
    return {"categories": cats}


# ---------- 内容 ----------

@app.post("/api/classify")
def api_classify(memo: MemoIn):
    text = memo.text.strip()
    if not text:
        return JSONResponse({"error": "内容为空"}, status_code=400)
    try:
        result = classify(text)
        saved = save_memo(text, result, memo.source)
        return saved
    except Exception as e:
        return JSONResponse({"error": f"分类失败: {e}"}, status_code=500)


@app.get("/api/memos")
def api_memos():
    """列出所有 memo，按日期倒序分组"""
    items = []
    for folder in MEMO_DIR.iterdir():
        if not folder.is_dir():
            continue
        for f in folder.glob("*.md"):
            txt = f.read_text(encoding="utf-8", errors="ignore")
            # 提取日期、主题、时间
            fmatch = re.match(r"# (.+)", txt)
            topic = fmatch.group(1) if fmatch else f.stem
            tm = re.search(r"- 时间: (.+)", txt)
            # 正文 = 引用块内容（> 开头的那部分）
            body = ""
            for line in txt.splitlines():
                if line.startswith("> "):
                    body = line[2:].strip()
                    break
            items.append({
                "file": str(f.relative_to(MEMO_DIR)),
                "category": folder.name,
                "topic": topic,
                "date": f.name[:10],
                "time": tm.group(1).strip() if tm else "",
                "preview": txt[:200],
                "content": body,
            })
    items.sort(key=lambda x: x["date"], reverse=True)
    return {"items": items}


@app.delete("/api/memos")
def api_delete(file: str):
    """删除单条 memo。file 为相对路径，如 '好句/2026-08-05-xxx.md'。防路径穿越。"""
    rel = Path(file)
    if rel.is_absolute() or ".." in rel.parts:
        return JSONResponse({"error": "非法路径"}, status_code=400)
    path = (MEMO_DIR / rel).resolve()
    if not path.is_relative_to(MEMO_DIR.resolve()):
        return JSONResponse({"error": "非法路径"}, status_code=400)
    if not path.exists() or not path.is_file():
        return JSONResponse({"error": "文件不存在"}, status_code=404)
    path.unlink()
    return {"ok": True}

class MemoMove(BaseModel):
    file: str
    category: str


@app.post("/api/memos/move")
def api_move_memo(body: MemoMove):
    """移动 memo 到其他分类：移动文件到新分类文件夹"""
    rel = Path(body.file)
    if rel.is_absolute() or ".." in rel.parts:
        return JSONResponse({"error": "非法路径"}, status_code=400)
    src = (MEMO_DIR / rel).resolve()
    if not src.is_relative_to(MEMO_DIR.resolve()):
        return JSONResponse({"error": "非法路径"}, status_code=400)
    if not src.exists() or not src.is_file():
        return JSONResponse({"error": "文件不存在"}, status_code=404)
    new_cat = sanitize(body.category)
    cats = load_categories()
    if new_cat not in cats:
        return JSONResponse({"error": "目标分类不存在"}, status_code=400)
    dest_dir = MEMO_DIR / new_cat
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    n = 1
    while dest.exists():
        dest = dest_dir / f"{src.stem}-{n}{src.suffix}"
        n += 1
    src.rename(dest)
    return {"ok": True, "file": str(dest.relative_to(MEMO_DIR)), "category": new_cat}


@app.get("/api/export")
def api_export(category: str = ""):
    """导出 zip：category 为空=全部，否则=单一分类。文件名: 灵感收件箱-2026-08-06.zip"""
    if category:
        folder = MEMO_DIR / category
        if not folder.is_dir():
            return JSONResponse({"error": "分类不存在"}, status_code=404)
        dirs = [folder]
        prefix = category
    else:
        dirs = [d for d in MEMO_DIR.iterdir() if d.is_dir()]
        prefix = "全部"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for d in dirs:
            for f in sorted(d.glob("*.md")):
                zf.write(f, arcname=f"{prefix}/{f.name}")
    today = date.today().isoformat()
    fname = f"灵感收件箱-{prefix}-{today}.zip"
    from urllib.parse import quote
    encoded = quote(fname)  # RFC 5987 编码，支持中文
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )


@app.get("/")
def index():
    return FileResponse(BASE_DIR / "static" / "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8787)
