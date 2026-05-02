import os, random, json
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
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
# ■ 応答（改善融合版）
# =========================
def generate_advanced(user, text, analysis):

    funny = should_be_funny(user, analysis)
    recall = maybe_recall(user)

    parts = []

    # 今の発言を中心
    parts.append(f"ユーザー:{text}")

    # ★ 会話改善ポイント
    parts.append("ユーザーの発言を理解して自然に反応する")
    parts.append("軽く1つだけツッコミか質問を返す")
    parts.append("会話を続ける意識を持つ")
    parts.append("今の発言を最優先にする")

    # ノリ
    if funny:
        parts.append("ノリよく軽くボケてツッコむ")
    else:
        parts.append("自然に優しく返す")

    # 記憶は弱く補助
    if recall:
        parts.append(f"少し関係ある過去:{recall['topic']}")

    # 直前だけ軽く参照
    if user["history"]:
        parts.append(f"直前:{user['history'][-1]['user']}")

    # 出力制御（人格維持）
    parts.append("関西弁で1〜2文")
    parts.append("短くテンポ良く")
    parts.append("説明しない")
    parts.append("自然な会話")
    parts.append("軽くツッコむ")
    parts.append("箇条書き禁止")
    parts.append("番号禁止")
    parts.append("例: なんやそれｗ どうなったん？")

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
# ■ WEB UI
# =========================
@app.get("/")
def ui():
    return HTMLResponse("""
    <h2>チャットテスト</h2>
    <form action="/test" method="post">
        <input name="text" style="width:300px;">
        <button type="submit">送信</button>
    </form>
    """)

@app.post("/test")
async def test(request: Request):
    form = await request.form()
    text = form.get("text")

    if not text:
        return HTMLResponse("テキスト入れてやｗ")

    ai_text = reply("web_user", text)

    return HTMLResponse(f"""
    <p>AI: {ai_text}</p>
    <a href="/">戻る</a>
    """)

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
