import os, random, json
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from openai import OpenAI

from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = FastAPI()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN) if LINE_CHANNEL_ACCESS_TOKEN else None
handler = WebhookHandler(LINE_CHANNEL_SECRET) if LINE_CHANNEL_SECRET else None

DATA_DIR = "user_data"
os.makedirs(DATA_DIR, exist_ok=True)

users = {}

# =========================
# 保存 / 読込
# =========================
def save_user(uid, user):
    try:
        with open(os.path.join(DATA_DIR, f"{uid}.json"), "w", encoding="utf-8") as f:
            json.dump(user, f, ensure_ascii=False)
    except:
        pass

def load_user(uid):
    path = os.path.join(DATA_DIR, f"{uid}.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return None

# =========================
# ユーザー
# =========================
def get_user(uid):
    if uid not in users:
        loaded = load_user(uid)
        if loaded:
            users[uid] = loaded
        else:
            users[uid] = {
                "history":[]
            }
    return users[uid]

# =========================
# 履歴
# =========================
def update_history(user, u, a):
    user["history"].append({"user":u,"ai":a})
    user["history"] = user["history"][-10:]

# =========================
# AI
# =========================
def safe_get_text(res):
    try:
        return res.output[0].content[0].text.strip()
    except:
        return getattr(res, "output_text", "なんかバグったわｗ").strip()

def ai_talk(prompt, max_tokens):
    try:
        res = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
            max_output_tokens=max_tokens
        )
        return safe_get_text(res)
    except Exception as e:
        print("AI error:", e)
        return "ちょい調子悪いわｗ"

# =========================
# 役割決定
# =========================
def decide_role(text):
    gap = any(k in text for k in ["なんで","意味わからん","急に"])
    is_q = "?" in text or "？" in text

    r = random.random()

    if gap and r < 0.7:
        return "tsukkomi"

    if is_q:
        return "answer"

    if r < 0.15:
        return "boke"

    return "normal"

# =========================
# 応答生成（シンプル版）
# =========================
def generate(user, text):
    role = decide_role(text)

    prompt = f"""
関西弁で話すノリのいい友達になれ。

役割:{role}

ルール:
・1〜2文
・自然な会話
・ズレがある時だけツッコむ
・たまに軽くボケる

ユーザー:{text}

返答:
"""

    return ai_talk(prompt, 60)

# =========================
# メイン
# =========================
def reply(uid, text):
    user = get_user(uid)

    ai = generate(user, text)

    update_history(user, text, ai)
    save_user(uid, user)

    return ai

# =========================
# WEB
# =========================
@app.get("/")
def ui():
    user = get_user("web_user")

    chat = ""
    for h in user["history"]:
        chat += f"<div><b>あなた:</b>{h['user']}</div>"
        chat += f"<div style='margin-left:20px;color:blue;'><b>AI:</b>{h['ai']}</div><hr>"

    return HTMLResponse(f"""
    <h2>チャット</h2>
    <div style="height:300px;overflow:auto;border:1px solid #ccc;">{chat}</div>
    <form action="/test" method="post">
    <input name="text"><button>送信</button>
    </form>
    """)

@app.post("/test")
async def test(request: Request):
    form = await request.form()
    reply("web_user", form.get("text"))
    return HTMLResponse('<meta http-equiv="refresh" content="0; url=/" />')

# =========================
# LINE
# =========================
@app.post("/callback")
async def callback(request: Request):
    if not handler:
        return {"status":"no line"}

    body = await request.body()
    signature = request.headers.get("X-Line-Signature")

    try:
        handler.handle(body.decode("utf-8"), signature)
    except:
        return {"status":"error"}

    return {"status":"ok"}

if handler:
    @handler.add(MessageEvent, message=TextMessage)
    def handle(event):
        ai = reply(event.source.user_id, event.message.text)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=ai))
