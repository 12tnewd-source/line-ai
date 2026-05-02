import os, random, json
from fastapi import FastAPI, Request
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
    try:
        with open("users.json","w",encoding="utf-8") as f:
            json.dump(users,f,ensure_ascii=False)
    except:
        pass

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
            "memory":[],
            "history":[],
            "mood":0.0,
            "relation":{"distance":0.0}
        }
    return users[uid]

# =========================
# ■ 履歴
# =========================
def update_history(user, user_text, ai_text):
    user["history"].append({"user":user_text,"ai":ai_text})
    user["history"] = user["history"][-3:]

# =========================
# ■ AI呼び出し（固定）
# =========================
def ai_talk(prompt):
    try:
        res = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
            max_output_tokens=60
        )
        return res.output_text.strip()
    except:
        return "ちょいバグったわｗ"

# =========================
# ■ 解析（軽量）
# =========================
def analyze(text):
    if len(text) < 10:
        return {"emotion":0,"topic":text,"intent":"雑談"}

    prompt = f"""
JSONのみ：
{{"emotion":-1〜1,"topic":"単語","intent":"雑談/相談/質問"}}
文:{text}
"""
    try:
        res = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
            max_output_tokens=40
        )
        return json.loads(res.output_text)
    except:
        return {"emotion":0,"topic":text[:6],"intent":"雑談"}

# =========================
# ■ 状態更新
# =========================
def update_mood(user, emotion):
    user["mood"] = max(-1, min(1, user["mood"] + float(emotion)*0.3))

def update_relation(user):
    user["relation"]["distance"] = min(1, user["relation"]["distance"] + 0.02)

# =========================
# ■ 記憶
# =========================
def store_memory(user, analysis):
    user["memory"].append(analysis)
    user["memory"] = user["memory"][-10:]

def maybe_recall(user):
    if user["memory"] and random.random() < 0.3:
        return random.choice(user["memory"])
    return None

# =========================
# ■ ノリ制御
# =========================
def should_be_funny(user, analysis):
    if analysis["intent"] == "相談":
        return False
    return user["relation"]["distance"] > 0.3

# =========================
# ■ 応答（修正版）
# =========================
def generate_advanced(user, text, analysis):

    funny = should_be_funny(user, analysis)
    recall = maybe_recall(user)

    parts = []

    # 🔥 今の発言を絶対基準にする
    parts.append(f"【今のユーザー発言】{text}")

    # 🔥 主語固定
    parts.append("ユーザーの発言に対してのみ返答する")
    parts.append("過去の話は補助として軽く触れるだけ")

    # ノリ
    if funny:
        parts.append("ノリよく軽くボケてツッコむ")
    else:
        parts.append("自然に優しく返す")

    # 記憶は弱める
    if recall:
        parts.append(f"（参考程度の過去話題:{recall['topic']}）")

    # 直前だけ軽く
    if user["history"]:
        parts.append(f"直前の流れ:{user['history'][-1]['user']}")

    # 出力制御
    parts.append("関西弁で一言か二言")
    parts.append("今の発言にだけ反応しろ")
    parts.append("話を勝手に広げすぎるな")
    parts.append("説明するな")
    parts.append("会話っぽく自然に")
    parts.append("軽くツッコめ")
    parts.append("箇条書き禁止")
    parts.append("番号使うな")
    parts.append("例: なんやそれｗ / マジかいなｗ")

    prompt = "\n".join(parts)

    return ai_talk(prompt)

# =========================
# ■ メイン
# =========================
def reply(uid, text):

    user = get_user(uid)

    analysis = analyze(text)

    update_mood(user, analysis.get("emotion",0))
    update_relation(user)

    store_memory(user, analysis)

    ai_text = generate_advanced(user, text, analysis)

    update_history(user, text, ai_text)
    save()

    return ai_text

# =========================
# ■ LINE
# =========================
@app.post("/callback")
async def callback(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Line-Signature")

    try:
        handler.handle(body.decode("utf-8"), signature)
    except InvalidSignatureError:
        return {"status": "invalid"}

    return {"status": "ok"}

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    text = event.message.text

    ai_text = reply(user_id, text)

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=ai_text)
    )

load()
