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
                "memory":[],
                "history":[],
                "mood":0.0,
                "relation":{"distance":0.0},
                "style":{"playfulness":0.5},
                "score":{
                    "boke":0.5,
                    "tsukkomi":0.5,
                    "sensitivity":0.5,
                    "memory_preference":0.5
                },
                "flow":{"momentum":0.0}
            }
    return users[uid]

# =========================
# 履歴
# =========================
def update_history(user, u, a):
    user["history"].append({"user":u,"ai":a})
    user["history"] = user["history"][-10:]

# =========================
# スコア
# =========================
def update_score(user, text):
    s = user["score"]

    if "w" in text or "笑" in text:
        s["boke"] += 0.05
        user["flow"]["momentum"] += 0.2

    if "なんで" in text or "いや" in text:
        s["tsukkomi"] += 0.03

    for k in s:
        s[k] = min(1.0, s[k])

    user["flow"]["momentum"] = min(1.0, user["flow"]["momentum"])

# =========================
# AI
# =========================
def safe_get_text(res):
    try:
        return res.output[0].content[0].text.strip()
    except:
        return getattr(res, "output_text", "").strip()

def ai_talk(prompt):
    try:
        res = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
            max_output_tokens=80
        )
        return safe_get_text(res)
    except:
        return "ちょい調子悪いわｗ"

# =========================
# 解析（軽く強化）
# =========================
def analyze(text):
    return {
        "intent":"質問" if "?" in text or "？" in text else "雑談",
        "energy":0.7 if "w" in text else 0.5,
        "gap": any(k in text for k in ["なんで","意味わからん","急に"]),
        "topic": text[:8]
    }

# =========================
# 記憶
# =========================
def store_memory(user, text, a):
    user["memory"].append({
        "topic":a["topic"],
        "text":text
    })
    user["memory"] = user["memory"][-20:]

def recall_memory(user, topic):
    if not user["memory"]:
        return None

    # 軽く関連優先（でも遊び残す）
    candidates = [m for m in user["memory"] if topic in m["topic"]]

    if candidates and random.random() < 0.7:
        return random.choice(candidates)

    return random.choice(user["memory"])

# =========================
# モード
# =========================
def decide_mode(user, a):
    r = random.random()

    if user["flow"]["momentum"] > 0.6:
        return "flow" if r < 0.6 else "boke"

    if r < 0.6:
        return "stable"
    elif r < 0.85:
        return "light"
    else:
        return "free"

# =========================
# 記憶使用率
# =========================
def decide_memory_mix(user):
    base = 0.7

    if user["relation"]["distance"] > 0.5:
        base -= 0.2

    if user["flow"]["momentum"] > 0.6:
        base -= 0.1

    base -= user["score"]["memory_preference"] * 0.2

    base += random.uniform(-0.1,0.1)

    return max(0.3, min(0.9, base))

# =========================
# 応答生成
# =========================
def generate(user, text, a):

    if len(text.strip()) < 2:
        return "何言うてるかちょい分からんわｗ"

    mode = decide_mode(user, a)
    recall = recall_memory(user, a["topic"])
    ratio = decide_memory_mix(user)

    rules = ["関西弁"]

    # 軸
    rules.append("ユーザー発言の一つの要素を軸にする")

    # モード
    if mode == "stable":
        rules.append("軸から外れない")
    elif mode in ["light","flow"]:
        rules.append("軸を保ちながら関連する範囲で広げる")
        rules.append("広げた場合は元に戻る")
    elif mode == "free":
        rules.append("少し自由に発想してよいが違和感は出さない")

    # 新規要素
    rules.append("新しい要素はユーザー発言か記憶と関連させる")

    # 記憶
    if recall and random.random() > ratio:
        rules.append(f"過去の話題『{recall['topic']}』を軽く絡める")

    # 笑い
    if random.random() < user["score"]["boke"]:
        rules.append("軸の要素を少しズラして面白くする")

    # ツッコミ
    if a["gap"] and random.random() < user["score"]["tsukkomi"]:
        return random.choice([
            "なんでやねんｗでどういうこと？",
            "急すぎるやろｗ説明くれｗ"
        ])

    # 流れ
    if user["flow"]["momentum"] > 0.5:
        rules.append("流れを優先して軽く乗る")

    rules.append("1〜2文で自然に返す")

    prompt = f"""
ユーザー:{text}
ルール:{",".join(rules)}

自然な会話を返せ
"""

    return ai_talk(prompt)

# =========================
# メイン
# =========================
def reply(uid, text):
    user = get_user(uid)

    a = analyze(text)

    update_score(user, text)
    store_memory(user, text, a)

    ai = generate(user, text, a)

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
