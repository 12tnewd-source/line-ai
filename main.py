import os, random, json, time
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

# ===== MODE切替 =====
MODE = "advanced"  # "simple" or "advanced"

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
            "name":"お前",
            "memory":[],
            "history":[],
            "mood":0.0,
            "relation":{"distance":0.0},
            "pending_topics":[]
        }
    return users[uid]

# =========================
# ■ テンプレ
# =========================
TEMPLATES = {
    "soft_exit":[
        "おおｗ全然ええでｗまた来いｗ",
        "まぁ今日はここまでやなｗ"
    ]
}

def detect_leave(text):
    return len(text.strip()) < 3

# =========================
# ■ 履歴
# =========================
def build_history(user):
    return "\n".join([f"ユーザー:{h['user']}\nAI:{h['ai']}" for h in user["history"]])

def update_history(user, user_text, ai_text):
    user["history"].append({"user":user_text,"ai":ai_text})
    user["history"] = user["history"][-5:]

# =========================
# ■ 解析
# =========================
def analyze(text):
    if len(text) < 10:
        return {"emotion":0,"topic":text,"intent":"雑談"}

    prompt = f"""
必ずJSONのみで出力：
{{
"emotion": 数値(-1〜1),
"topic": "単語",
"intent": "雑談/相談/報告/質問"
}}
文: {text}
"""
    try:
        res = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
            max_output_tokens=60
        )
        data = json.loads(res.output_text)
        return data
    except:
        return {"emotion":0,"topic":text[:6],"intent":"雑談"}

# =========================
# ■ 状態
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
    user["memory"] = user["memory"][-20:]

def add_pending(user, analysis):
    if analysis.get("intent") in ["相談","報告"]:
        user["pending_topics"].append(analysis)
        user["pending_topics"] = user["pending_topics"][-10:]

def maybe_recall(user):
    if user["pending_topics"] and random.random() < 0.3:
        return random.choice(user["pending_topics"])
    return None

# =========================
# ■ フラグ（advanced用）
# =========================
def detect_request(text):
    return any(k in text for k in ["して","やって","言って","教えて","みて"])

def should_be_funny(user, analysis, text):
    if detect_request(text):
        return True
    if analysis.get("intent") == "相談":
        return False
    return user["relation"]["distance"] > 0.4

def should_lead(text, analysis):
    return len(text) < 5 or analysis.get("intent") == "雑談"

# =========================
# ■ 応答（simple）
# =========================
def generate_simple(user, text, analysis):
    prompt = f"""
関西弁で自然に返す。短く1〜2文。
ユーザー:{text}
"""
    try:
        res = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
            max_output_tokens=80
        )
        return res.output_text.strip()
    except:
        return "ちょいバグったわｗ"

# =========================
# ■ 応答（advanced）
# =========================
def generate_advanced(user, text, analysis):

    request_flag = detect_request(text)
    funny_flag = should_be_funny(user, analysis, text)
    lead_flag = should_lead(text, analysis)

    history = build_history(user)
    recall = maybe_recall(user)

    prompt = f"""
関西弁ツッコミAI。

【ルール】
- ユーザー中心
- 主語混同禁止

【構造】
①拾う ②リアクション ③軽く広げる

【フラグ】
request:{request_flag}
funny:{funny_flag}
lead:{lead_flag}

ユーザー:{text}
履歴:{history}
"""

    try:
        res = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
            max_output_tokens=90
        )
        return res.output_text.strip().replace("\n"," ")
    except:
        return "今バグったｗもっかい頼むｗ"

# =========================
# ■ メイン
# =========================
def reply(uid, text):

    user = get_user(uid)

    if detect_leave(text):
        return random.choice(TEMPLATES["soft_exit"])

    analysis = analyze(text)

    update_mood(user, analysis.get("emotion",0))
    update_relation(user)

    store_memory(user, analysis)
    add_pending(user, analysis)

    if MODE == "simple":
        ai_text = generate_simple(user, text, analysis)
    else:
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
