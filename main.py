from fastapi import FastAPI, Request
import requests
import os

app = FastAPI()

LINE_ACCESS_TOKEN = os.getenv("LINE_ACCESS_TOKEN")

@app.get("/")
def root():
    return {"msg": "ok"}

@app.post("/callback")
async def callback(request: Request):
    body = await request.json()

    for event in body["events"]:
        reply_token = event["replyToken"]
        user_msg = event["message"]["text"]

        # とりあえずオウム返し
        reply_msg = f"お前『{user_msg}』って言ったやろｗ"

        headers = {
            "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }

        data = {
            "replyToken": reply_token,
            "messages": [
                {"type": "text", "text": reply_msg}
            ]
        }

        requests.post(
            "https://api.line.me/v2/bot/message/reply",
            headers=headers,
            json=data
        )

    return {"status": "ok"}
