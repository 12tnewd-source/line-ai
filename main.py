import os, random, json
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from openai import OpenAI

from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = FastAPI()

# ===== API =====
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN) if LINE_CHANNEL_ACCESS_TOKEN else None
handler = WebhookHandler(LINE_CHANNEL_SECRET) if LINE_CHANNEL_SECRET else None

users = {}

# =========================
# ユーザー
# =========================
def get_user(uid):
    if uid not in users:
        users[uid] = {
            "memory":[],
            "history":[],
            "relation":{"distance":0.0},
            "score":{"boke":0.5,"tsukkomi":0.6},
            "flow":{"momentum":0.0}
        }
    return users[uid]

# =========================
# 解析
# =========================
def analyze(text):
    return {
        "gap": any(k in text for k in ["なんで","意味わからん","急に","は？"]),
        "topic": text[:10]
    }

def detect_state(text):
    if "w" in text or "笑" in text:
        return "laugh"
    if "?" in text or "？" in text:
        return "question"
    return "normal"

# =========================
# スコア
# =========================
def update_score(user, text):
    if "w" in text or "笑" in text:
        user["score"]["boke"] += 0.05
        user["flow"]["momentum"] += 0.2
    else:
        user["flow"]["momentum"] *= 0.85

    if "なんで" in text or "いや" in text:
        user["score"]["tsukkomi"] += 0.03

    user["score"]["boke"] = min(1.0, user["score"]["boke"])
    user["score"]["tsukkomi"] = min(1.0, user["score"]["tsukkomi"])
    user["flow"]["momentum"] = min(1.0, user["flow"]["momentum"])

# =========================
# 記憶
# =========================
def store_memory(user, text, a):
    user["memory"].append({"topic":a["topic"],"text":text})
    user["memory"] = user["memory"][-20:]

def recall_memory(user, topic):
    if not user["memory"]:
        return None
    if random.random() < 0.5:
        related = [m for m in user["memory"] if topic in m.get("topic","")]
        if related:
            return random.choice(related)
    return random.choice(user["memory"])

# =========================
# 役割
# =========================
def decide_role(user, a):
    r = random.random()

    if a["gap"] and r < user["score"]["tsukkomi"]:
        return "tsukkomi"

    if user["flow"]["momentum"] > 0.6:
        return "flow" if r < 0.65 else "light"

    if r < 0.65:
        return "natural"
    elif r < 0.9:
        return "light"
    else:
        return "boke"

# =========================
# AI
# =========================
def ai_talk(prompt, max_tokens):
    try:
        res = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
            max_output_tokens=max_tokens
        )
        return res.output[0].content[0].text.strip()
    except:
        return "ちょい調子悪いわｗ"

# =========================
# 応答生成（完成）
# =========================
def generate(user, text, a):

    if len(text.strip()) < 2:
        return "何言うてるか分からんわｗ"

    # ===== 軽い余白 =====
    if random.random() < 0.06:
        return random.choice([
            "で、結局どうなん？",
            "ほんでどうなったん？",
            "それ気になるやつやん"
        ])

    state = detect_state(text)
    role = decide_role(user, a)
    recall = recall_memory(user, a["topic"])

    rules = ["関西弁"]

    # ===== 状態 =====
    if state == "laugh":
        max_tokens = 40
        rules += ["短く","テンポよく","ノる"]
    elif state == "question":
        max_tokens = 70
        rules += ["1つ答える","軽く返す"]
    else:
        max_tokens = 55
        rules += ["1文目で反応","自然に続ける"]

    # ===== ツッコミ =====
    if role == "tsukkomi":
        return random.choice([
            "なんでやねんｗ",
            "急にどうしたｗ",
            "話飛びすぎやろｗ"
        ])

    # ===== 爆発ボケ =====
    if role == "boke" and random.random() < 0.25:
        return random.choice([
            "いや設定どうなってんねんｗ",
            "それ現実なん？バグってへん？",
            "情報量多すぎて脳バグるわｗ"
        ])

    # ===== 軽ボケ =====
    if role == "boke":
        rules.append("少しズラして軽くボケる")

    elif role == "flow":
        rules.append("ユーザーのノリを強めに真似る")

    elif role == "light":
        rules.append("軽く共感して少し広げる")

    else:
        rules.append("自然に短く返す")

    # ===== ★広げ（神調整復活）=====
    if role in ["natural","light","flow"] and random.random() < 0.45:
        rules.append("ユーザーの話を1つだけ自然に広げる（脱線しない）")

    # ===== 記憶 =====
    if recall and random.random() < 0.2:
        rules.append(f"過去の話題({recall['topic']})を軽く絡める")

    rules.append("ダラダラしない")

    prompt = f"""
ユーザー:{text}

・{",".join(rules)}

返答：
"""

    return ai_talk(prompt, max_tokens)

# =========================
# メイン
# =========================
def reply(uid, text):
    user = get_user(uid)

    a = analyze(text)
    update_score(user, text)
    store_memory(user, text, a)

    ai = generate(user, text, a)

    user["history"].append({"user":text,"ai":ai})
    user["history"] = user["history"][-10:]

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

    handler.handle(body.decode("utf-8"), signature)
    return {"status":"ok"}

if handler:
    @handler.add(MessageEvent, message=TextMessage)
    def handle(event):
        ai = reply(event.source.user_id, event.message.text)
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=ai)
        )
