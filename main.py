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

# ★ 安全ガード
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN) if LINE_CHANNEL_ACCESS_TOKEN else None
handler = WebhookHandler(LINE_CHANNEL_SECRET) if LINE_CHANNEL_SECRET else None

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
    user["history"] = user["history"][-10:]

# =========================
# ■ 安全レスポンス取得
# =========================
def safe_get_text(res):
    try:
        return res.output[0].content[0].text.strip()
    except:
        return getattr(res, "output_text", "なんか返ってこんかったわｗ").strip()

# =========================
# ■ AI呼び出し
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
        return "ちょいバグったわｗ"

# =========================
# ■ 解析
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
        raw = safe_get_text(res)

        try:
            return json.loads(raw)
        except:
            return {"emotion":0,"topic":raw[:6],"intent":"雑談"}

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
# ■ 応答（微調整版）
# =========================
def generate_advanced(user, text, analysis):

    funny = should_be_funny(user, analysis)
    recall = maybe_recall(user)

    parts = []

    # ★ 今を最優先
    parts.append(f"今のユーザー発言:{text}")
    parts.append("この発言を最優先で理解して反応する")

    # 会話性
    parts.append("軽く1つだけツッコミか質問を返す")
    parts.append("自然に会話を続ける")

    # ノリ
    if funny:
        parts.append("ノリよく軽くボケてツッコむ")
    else:
        parts.append("自然に優しく返す")

    # 記憶（弱）
    if recall:
        parts.append(f"参考の過去:{recall['topic']}")

    # ★ 直前は参考扱いに格下げ
    if user["history"]:
        parts.append(f"直前の話題（参考程度）:{user['history'][-1]['user']}")

    # 出力制御
    parts.append("関西弁で1〜2文")
    parts.append("短くテンポ良く")
    parts.append("説明しない")
    parts.append("自然な会話")
    parts.append("軽くツッコむ")

    return ai_talk("\n".join(parts))

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
# ■ WEB UI（チャット化）
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
        return HTMLResponse("テキスト入れてやｗ")

    reply("web_user", text)

    return HTMLResponse('<meta http-equiv="refresh" content="0; url=/" />')

# =========================
# ■ LINE
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
