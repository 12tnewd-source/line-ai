import os, random, json, time, requests
from fastapi import FastAPI, Request
from pydantic import BaseModel
from openai import OpenAI

app = FastAPI()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

LINE_ACCESS_TOKEN = os.getenv("LINE_ACCESS_TOKEN")

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
            "interest_flag":False,
            "interest_time":0
        }
    return users[uid]

# =========================
# ■ テンプレ
# =========================
TEMPLATES = {
    "tsukkomi":["いやそれどういうことやねんｗ","話飛びすぎやろｗ"],
    "sarcasm":["なるほどな天才の発想やな（逆）"],
    "self_deprecate":["まぁワシが言うのもなんか違うけどなｗ"],
    "soft_exit":["おおｗ全然ええでｗまた来いｗ","まぁ今日はここまでやなｗ"],
    "reoffer":["そういやさっきのやつ、まだ気になってる？ｗ"],
    "paid_intro":["エンジン温まってきたでーｗ","ほなちょいギア上げるで"]
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

def call_ai(user, text):
    mem = pick_memory(user)
    mem_text = mem["text"] if mem else ""

    prompt = f"""
あなたは関西弁のツッコミAI。
少し皮肉、でも嫌われない。
短くテンポ良く返す。
絶対に標準語にならない。

ユーザー:{user["name"]}
過去:{mem_text}
"""

    res = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt + "\nユーザー:" + text
    )

    return res.output_text

def reply(uid, text, name="お前"):
    user = get_user(uid)
    user["name"]=name

    if detect_leave(text):
        return random.choice(TEMPLATES["soft_exit"])

    store_memory(user,text)

    base = call_ai(user,text)

    if random.random()<0.3:
        base += "\n" + random.choice(TEMPLATES["tsukkomi"])

    save()
    return base.replace("お前", user["name"])

# =========================
# ■ LINE Webhook
# =========================
@app.post("/callback")
async def callback(request: Request):
    body = await request.json()

    for event in body.get("events", []):
        if event.get("type") != "message":
            continue
        if event["message"].get("type") != "text":
            continue

        reply_token = event["replyToken"]
        user_msg = event["message"]["text"]
        user_id = event["source"]["userId"]

        # AI生成
        ai_text = reply(user_id, user_msg)

        headers = {
            "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }

        data = {
            "replyToken": reply_token,
            "messages": [
                {"type": "text", "text": ai_text}
            ]
        }

        requests.post(
            "https://api.line.me/v2/bot/message/reply",
            headers=headers,
            json=data
        )

    return "OK"

# =========================
# ■ 起動
# =========================
load()
