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
            "relation":{"distance":0.0}
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
            max_output_tokens=60
        )
        return safe_get_text(res)
    except Exception as e:
        print("AIエラー:", e)
        return "ちょい調子悪いわｗ"

# =========================
# 軽量解析
# =========================
def analyze(text):
    if len(text) < 15:
        return {
            "emotion":0,
            "topic":text[:8],
            "intent":"雑談",
            "energy":0.5,
            "serious":0.3
        }

    prompt = f"""
JSONのみ：
{{
"emotion":-1〜1,
"topic":"単語",
"intent":"雑談/相談/質問",
"energy":0〜1,
"serious":0〜1
}}
文:{text}
"""
    try:
        res = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
            max_output_tokens=60
        )
        return json.loads(safe_get_text(res))
    except:
        return {
            "emotion":0,
            "topic":text[:8],
            "intent":"雑談",
            "energy":0.5,
            "serious":0.5
        }

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
# 記憶保存
# =========================
def store_memory(user, analysis):
    mem = {
        "topic":analysis.get("topic",""),
        "emotion":analysis.get("emotion",0)
    }
    user["memory"].append(mem)
    user["memory"] = user["memory"][-20:]

# =========================
# 記憶スコア
# =========================
def recall_memory(user, current_topic):
    scored = []

    for m in user["memory"]:
        score = 0

        if current_topic and current_topic in m.get("topic",""):
            score += 2

        score += 0.3
        score += abs(m.get("emotion",0))

        scored.append((score, m))

    scored.sort(reverse=True, key=lambda x: x[0])

    if scored and scored[0][0] > 1.2:
        return scored[0][1]

    return None

# =========================
# ノリ判定
# =========================
def decide_mode(user, analysis):
    if analysis["intent"] == "相談":
        return "care"
    if user["relation"]["distance"] > 0.4:
        return "fun"
    return "normal"

# =========================
# 応答生成（改善融合版）
# =========================
def generate(user, text, analysis):

    mode = decide_mode(user, analysis)
    recall = recall_memory(user, analysis.get("topic"))

    parts = []

    parts.append(f"ユーザー発言:{text}")

    # ===== 会話理解（柔らかく）=====
    parts.append("ユーザーの発言の感情か出来事に自然に反応する")
    parts.append("基本は中心に反応しつつ、たまに少しズレてもいい")

    # 言葉拾い（確率化）
    if random.random() < 0.4:
        parts.append("ユーザーの言葉を少しだけ自然に使ってもいい")

    # 共感（確率）
    if random.random() < 0.8:
        parts.append("一言だけ軽く自然に共感する")

    # 揺らぎ
    tone = random.random()

    if mode == "care":
        parts.append("優しく短く返す")

    elif mode == "fun":
        if tone < 0.3:
            parts.append("ちょい雑にツッコむ")
        elif tone < 0.6:
            parts.append("軽くツッコむ")
        else:
            parts.append("少しだけ優しめにツッコむ")

    else:
        if tone < 0.3:
            parts.append("少し雑に返す")
        elif tone < 0.7:
            parts.append("自然に会話する")
        else:
            parts.append("軽く共感して返す")

    # mood反映
    if user["mood"] < -0.3:
        parts.append("少し落ち着いたトーンで返す")

    if user["mood"] > 0.3:
        parts.append("少しテンション高めで返す")

    # 記憶
    if recall:
        parts.append(f"自然に少しだけ過去の話題に触れてもいい:{recall['topic']}")

    # 出力制御
    parts.append("関西弁で1〜2文")
    parts.append("短く")
    parts.append("説明しない")
    parts.append("自然な会話を優先する")

    return ai_talk("\n".join(parts))

# =========================
# メイン
# =========================
def reply(uid, text):
    user = get_user(uid)

    analysis = analyze(text)

    update_mood(user, analysis.get("emotion",0))
    update_relation(user, analysis.get("intent","雑談"))
    store_memory(user, analysis)

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
