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
                "relation":{"distance":0.0},
                "score":{"boke":0.5,"tsukkomi":0.5},
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
# スコア更新
# =========================
def update_score(user, text):
    s = user["score"]

    if "w" in text or "笑" in text:
        s["boke"] += 0.05
        user["flow"]["momentum"] += 0.2
    else:
        user["flow"]["momentum"] *= 0.8

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
        return getattr(res, "output_text", "なんかバグったわｗ").strip()

def ai_talk(prompt, max_tokens):
    try:
        res = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt,
            max_output_tokens=max_tokens
        )
        return safe_get_text(res)
    except:
        return "ちょい調子悪いわｗ"

# =========================
# 解析
# =========================
def analyze(text):
    return {
        "gap": any(k in text for k in ["なんで","意味わからん","急に"]),
        "topic": text[:8]
    }

# =========================
# 状態
# =========================
def detect_state(text):
    if "w" in text or "笑" in text:
        return "laugh"
    if "?" in text or "？" in text:
        return "question"
    return "normal"

# =========================
# モード
# =========================
def decide_mode(user):
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
# 記憶
# =========================
def store_memory(user, text, a):
    user["memory"].append({"topic":a["topic"],"text":text})
    user["memory"] = user["memory"][-20:]

def recall_memory(user):
    if not user["memory"]:
        return None
    return random.choice(user["memory"])

# =========================
# 応答生成（最終）
# =========================
def generate(user, text, a):

    if len(text.strip()) < 2:
        return "何言うてるか分からんわｗ"

    state = detect_state(text)
    mode = decide_mode(user)
    recall = recall_memory(user)

    rules = ["関西弁", "ユーザー発言の一つに反応する"]

    # ===== state =====
    if state == "laugh":
        max_tokens = 40
        rules += ["短くテンポよく","1文でもOK","軽くノる"]

    elif state == "question":
        max_tokens = 70
        rules += ["1つ答える","その後軽く返す"]

    else:
        max_tokens = 50
        rules += ["1文目で反応","2文目で少し広げる"]

    # ===== ツッコミ（最優先）=====
    if a["gap"] and random.random() < user["score"]["tsukkomi"]:
        return random.choice([
            "なんでやねんｗ",
            "急にどうしたｗ"
        ])

    # ===== mode =====
    if mode in ["light","flow"]:
        rules.append("関連する範囲で自然に広げる")
    elif mode == "free":
        rules.append("少し自由に発想してよい")

    # ===== 爆発 or 視点ズラし（排他）=====
    roll = random.random()
    trigger = 0.3 + user["score"]["boke"] * 0.4

    if mode in ["free","boke"] and roll < trigger:
        rules.append("一瞬だけズレた発想を入れて自然に戻す")

    elif roll < (0.25 + user["score"]["boke"] * 0.3):
        if user["flow"]["momentum"] > 0.6:
            rules.append("少しズラしてそのままノリを広げる")
        elif user["relation"]["distance"] > 0.4:
            rules.append("少しズラして軽くイジる")
        else:
            rules.append("少しズラして元に戻す")

    # ===== 流れ強化 =====
    if user["flow"]["momentum"] > 0.7:
        rules.append("テンションや言い回しを強めに合わせる")

    # ===== イジり =====
    if user["relation"]["distance"] > 0.4 and random.random() < 0.25:
        rules.append("軽くイジって自然に流す")

    # ===== 記憶 =====
    if recall and random.random() < 0.2:
        rules.append(f"過去の話題({recall['topic']})を軽く絡める")

    # ===== 最終 =====
    if state != "laugh":
        rules.append("ダラダラせず短く")

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
