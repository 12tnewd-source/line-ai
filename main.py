import os, random, json
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from openai import OpenAI

from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from linebot.exceptions import InvalidSignatureError

app = FastAPI()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN) if LINE_CHANNEL_ACCESS_TOKEN else None
handler = WebhookHandler(LINE_CHANNEL_SECRET) if LINE_CHANNEL_SECRET else None

users = {}

# =========================
# 保存
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
# ユーザー
# =========================
def get_user(uid):
    if uid not in users:
        users[uid] = {
            "memory":[],
            "history":[],
            "mood":0.0,
            "relation":{"distance":0.0},
            "style":{"playfulness":0.5}
        }
    return users[uid]

# =========================
# 履歴
# =========================
def update_history(user, user_text, ai_text):
    user["history"].append({"user":user_text,"ai":ai_text})
    user["history"] = user["history"][-10:]

# =========================
# AI安全取得
# =========================
def safe_get_text(res):
    try:
        return res.output[0].content[0].text.strip()
    except:
        return getattr(res, "output_text", "なんかバグったわｗ").strip()

# =========================
# AI呼び出し
# =========================
def ai_talk(prompt):
    try:
        res = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
            max_output_tokens=80
        )
        return safe_get_text(res)
    except Exception as e:
        print("AIエラー:", e)
        return "ちょい調子悪いわｗ"

# =========================
# 軽量解析
# =========================
def analyze(text):
    base = {
        "emotion":0,
        "topic":text[:8],
        "intent":"雑談",
        "energy":0.5,
        "serious":0.5
    }

    # 簡易補強（軽量＆安定）
    if "？" in text or "?" in text:
        base["intent"] = "質問"

    if any(k in text for k in ["悩", "つらい", "しんどい", "どうしたら"]):
        base["intent"] = "相談"

    if "！" in text or "w" in text:
        base["energy"] += 0.2

    if any(k in text for k in ["なんで", "意味わからん", "急に"]):
        base["gap"] = True
    else:
        base["gap"] = False

    return base

# =========================
# 状態更新
# =========================
def update_mood(user, emotion):
    user["mood"] = max(-1, min(1, user["mood"] + float(emotion)*0.3))

def update_relation(user, intent):
    if intent == "相談":
        user["relation"]["distance"] += 0.05
    else:
        user["relation"]["distance"] += 0.01
    user["relation"]["distance"] = min(1, user["relation"]["distance"])

# =========================
# 記憶
# =========================
def store_memory(user, text, analysis):
    user["memory"].append({
        "topic":analysis.get("topic",""),
        "detail":text,
        "emotion":analysis.get("emotion",0)
    })
    user["memory"] = user["memory"][-20:]

def recall_memory(user, topic):
    for m in reversed(user["memory"]):
        if topic and topic in m["topic"]:
            return m
    return None

# =========================
# 役割
# =========================
def decide_role(analysis, user):
    base = random.random()

    if analysis["intent"] == "相談":
        return "listener"

    if user["relation"]["distance"] < 0.2:
        return "react"

    if analysis["energy"] > 0.6:
        if base < 0.4:
            return "react"
        elif base < 0.75:
            return "tsukkomi"
        else:
            return "topic_shift"

    return "react"

# =========================
# ツッコミ判定
# =========================
def should_tsukkomi(analysis, user):
    if analysis["intent"] == "相談":
        return False
    if user["relation"]["distance"] < 0.3:
        return False
    if not analysis.get("gap"):
        return False
    if analysis.get("serious",0) > 0.6:
        return False
    return random.random() < 0.6

# =========================
# 応答生成
# =========================
def generate(user, text, analysis):

    # 意味不明対策
    if len(text.strip()) < 2:
        return "ちょい何言うてるかわからんわｗ"

    role = decide_role(analysis, user)
    recall = recall_memory(user, analysis.get("topic"))

    # ツッコミ（成立時のみ）
    if should_tsukkomi(analysis, user):
        return random.choice([
            "いやなんでやねんｗ",
            "急すぎるやろｗ",
            "どういう流れやねんそれｗ"
        ])

    # ルール（性格ベース）
    rules = ["関西弁"]

    if analysis["energy"] > 0.5:
        rules.append("テンポよく")

    if user["relation"]["distance"] > 0.4:
        rules.append("少し砕ける")

    if user["style"]["playfulness"] > 0.6:
        if random.random() < user["style"]["playfulness"]:
            rules.append("ちょい雑に")

    # 会話生成
    prompt = f"""
ユーザー:{text}
役割:{role}
ルール:{",".join(rules)}

自然な会話を1〜2文で返せ
"""

    return ai_talk(prompt)

# =========================
# メイン
# =========================
def reply(uid, text):
    user = get_user(uid)

    analysis = analyze(text)

    update_mood(user, analysis.get("emotion",0))
    update_relation(user, analysis.get("intent","雑談"))
    store_memory(user, text, analysis)

    ai_text = generate(user, text, analysis)

    update_history(user, text, ai_text)
    save()

    return ai_text

# =========================
# WEB UI
# =========================
@app.get("/")
def ui():
    user = get_user("web_user")

    chat_html = ""
    for h in user["history"]:
        chat_html += f"<div><b>あなた:</b> {h['user']}</div>"
        chat_html += f"<div style='margin-left:20px;color:blue;'><b>AI:</b> {h['ai']}</div><hr>"

    return HTMLResponse(f"""
    <h2>チャット</h2>
    <div style="height:300px;overflow:auto;border:1px solid #ccc;padding:10px;">
        {chat_html}
    </div>
    <form action="/test" method="post">
        <input name="text" style="width:70%;">
        <button type="submit">送信</button>
    </form>
    """)

@app.post("/test")
async def test(request: Request):
    form = await request.form()
    text = form.get("text")
    if not text:
        return HTMLResponse("なんか入れろやｗ")

    reply("web_user", text)
    return HTMLResponse('<meta http-equiv="refresh" content="0; url=/" />')

# =========================
# LINE
# =========================
@app.post("/callback")
async def callback(request: Request):
    if not handler:
        return {"status": "LINE未設定"}

    body = await request.body()
    signature = request.headers.get("X-Line-Signature")

    try:
        handler.handle(body.decode("utf-8"), signature)
    except InvalidSignatureError:
        return {"status": "invalid"}

    return {"status": "ok"}

if handler:
    @handler.add(MessageEvent, message=TextMessage)
    def handle_message(event):
        if not line_bot_api:
            return

        user_id = event.source.user_id
        text = event.message.text

        ai_text = reply(user_id, text)

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=ai_text)
        )

load()
