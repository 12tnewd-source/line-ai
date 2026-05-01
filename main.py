import os, random, json, time
from fastapi import FastAPI, Request
from pydantic import BaseModel
from openai import OpenAI

# LINE SDK
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from linebot.exceptions import InvalidSignatureError

app = FastAPI()

# ===== API =====
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

users = {}

# =========================
# ■ 保存
# =========================
def save():
    with open("users.json","w",encoding="utf-8") as f:
        json.dump(users,f,ensure_ascii=False)

def load():
    global users
    try:
        with open("users.json","r",encoding="utf-8") as f:
            users=json.load(f)
    except:
        users={}

# =========================
# ■ ユーザー
# =========================
def get_user(uid):
    if uid not in users:
        users[uid] = {
            "name":"お前",
            "paid":False,

            "emotion":{"positive":0.5,"negative":0.5},
            "memory":[],
            "relation":{"distance":0.0},
            "experience":{"success":[],"fail":[]},
            "style":{"tsukkomi":1.0,"sarcasm":1.0,"self_deprecate":1.0},

            "history":[],

            "interest_flag":False,
            "interest_time":0
        }
    return users[uid]

# =========================
# ■ テンプレ
# =========================
TEMPLATES = {
    "tsukkomi":["いやそれどういうことやねんｗ","話飛びすぎやろｗ"],
    "soft_exit":["おおｗ全然ええでｗまた来いｗ","まぁ今日はここまでやなｗ"],
    "reoffer":["そういやさっきのやつ、まだ気になってる？ｗ"]
}

# =========================
# ■ ロジック
# =========================
def detect_leave(text):
    return len(text) < 5 or text in ["うん","まぁ","また"]

def store_memory(user, text):
    if len(text) < 10:
        return
    user["memory"].append({"text":text,"time":time.time()})
    user["memory"]=user["memory"][-20:]

def pick_memory(user):
    return random.choice(user["memory"]) if user["memory"] else None

# ===== 履歴 =====
def build_history(user):
    history_text = ""
    for h in user["history"]:
        history_text += f"ユーザー:{h['user']}\nAI:{h['ai']}\n"
    return history_text

def update_history(user, user_text, ai_text):
    user["history"].append({"user":user_text,"ai":ai_text})
    user["history"] = user["history"][-5:]

# =========================
# ■ AI
# =========================
def call_ai(user, text):
    mem = pick_memory(user)
    mem_text = mem["text"] if mem else ""
    history_text = build_history(user)

    if len(text) > 100:
        text = text[:100]

    prompt = f"""
あなたは関西弁のツッコミAI。
少し皮肉、でも嫌われない。
短くテンポ良く返す。
絶対に標準語にならない。

過去の会話:
{history_text}

過去記憶:{mem_text}

ユーザー:{user["name"]}
"""

    res = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt + "\nユーザー:" + text,
        max_output_tokens=80
    )

    return res.output_text

# =========================
# ■ メイン返信
# =========================
def reply(uid, text, name="お前"):

    user = get_user(uid)
    user["name"]=name

    if detect_leave(text):
        return random.choice(TEMPLATES["soft_exit"])

    store_memory(user,text)

    base = call_ai(user,text)

    if random.random()<0.3:
        base += "\n" + random.choice(TEMPLATES["tsukkomi"])

    update_history(user, text, base)

    save()

    return base.replace("お前", user["name"])

# =========================
# ■ LINE Webhook
# =========================
@app.post("/callback")
async def callback(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Line-Signature")

    try:
        handler.handle(body.decode("utf-8"), signature)
    except InvalidSignatureError:
        return {"status": "invalid signature"}

    return {"status": "ok"}

# =========================
# ■ LINEイベント
# =========================
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text

    ai_text = reply(user_id, text)

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=ai_text)
    )

# =========================
# ■ 起動
# =========================
load()
