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

# =========================
# ■ ロジック
# =========================
def detect_leave(text):
    return len(text.strip()) < 3

# ===== 履歴 =====
def build_history(user):
    history_text = ""
    for h in user["history"]:
        history_text += f"ユーザー:{h['user']}\nAI:{h['ai']}\n"
    return history_text

def update_history(user, user_text, ai_text):
    user["history"].append({"user":user_text,"ai":ai_text})
    user["history"] = user["history"][-6:]

# =========================
# ■ 意図解析（安定版）
# =========================
def analyze(text):
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
            max_output_tokens=80
        )
        data = json.loads(res.output_text)
        return {
            "emotion": float(data.get("emotion",0)),
            "topic": str(data.get("topic","雑談")),
            "intent": str(data.get("intent","雑談"))
        }
    except:
        return {"emotion":0,"topic":text[:6],"intent":"雑談"}

# =========================
# ■ 状態更新
# =========================
def update_mood(user, emotion):
    try:
        user["mood"] += float(emotion) * 0.3
    except:
        pass
    user["mood"] = max(-1, min(1, user["mood"]))

def update_relation(user):
    user["relation"]["distance"] += 0.02
    user["relation"]["distance"] = min(1, user["relation"]["distance"])

# =========================
# ■ 記憶
# =========================
def store_memory(user, analysis):
    user["memory"].append({
        "topic": analysis.get("topic",""),
        "emotion": analysis.get("emotion",0),
        "intent": analysis.get("intent","雑談"),
        "time": time.time()
    })
    user["memory"] = user["memory"][-30:]

# =========================
# ■ 未回収ネタ
# =========================
def add_pending(user, analysis):
    if analysis.get("intent") in ["相談","報告"]:
        user["pending_topics"].append({
            "topic": analysis.get("topic",""),
            "time": time.time()
        })
        user["pending_topics"] = user["pending_topics"][-10:]

def maybe_recall(user):
    if not user["pending_topics"]:
        return None
    if random.random() < 0.3:
        return random.choice(user["pending_topics"])
    return None

# =========================
# ■ フォーカス
# =========================
def select_focus(analysis):
    try:
        if abs(float(analysis.get("emotion",0))) > 0.4:
            return "emotion"
    except:
        pass
    if analysis.get("intent") == "相談":
        return "intent"
    return "topic"

# =========================
# ■ 応答生成（自然化パッチ済）
# =========================
def generate_reply(user, text, analysis, focus):

    focus_value = analysis.get(focus, "")
    history_text = build_history(user)
    recall = maybe_recall(user)

    mood = user.get("mood",0)
    distance = user.get("relation",{}).get("distance",0)

    recall_text = ""
    if recall:
        recall_text = f"過去話題:{recall['topic']}"

    prompt = f"""
あなたは関西弁のツッコミAI。

【最重要】
- ユーザーの話を中心にする
- 主語を混同しない
- 自分語りしすぎない

【会話構造】
①軽く要約して拾う
②感情リアクション
③一言広げる

【制約】
- 1〜2文
- 改行禁止
- 不自然禁止
- 指定要素を無視したら失敗

【状態】
mood:{mood}
relation:{distance}

【履歴】
{history_text}

【入力】
ユーザー:{text}
重要:{focus}:{focus_value}
{recall_text}
"""

    try:
        res = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
            max_output_tokens=90
        )
        return res.output_text.strip().replace("\n"," ")
    except:
        return "なんかバグったわｗもう一回頼むｗ"

# =========================
# ■ メイン返信
# =========================
def reply(uid, text, name="お前"):

    user = get_user(uid)
    user["name"] = name

    if detect_leave(text):
        return random.choice(TEMPLATES["soft_exit"])

    analysis = analyze(text)

    update_mood(user, analysis.get("emotion",0))
    update_relation(user)

    store_memory(user, analysis)
    add_pending(user, analysis)

    focus = select_focus(analysis)

    ai_text = generate_reply(user, text, analysis, focus)

    update_history(user, text, ai_text)

    save()

    return ai_text.replace("お前", user["name"])

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
