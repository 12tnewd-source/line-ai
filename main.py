from fastapi import FastAPI, Request
import requests
import os

app = FastAPI()

# 環境変数から取得
LINE_ACCESS_TOKEN = os.getenv("LINE_ACCESS_TOKEN")

@app.post("/callback")
async def callback(request: Request):
    body = await request.json()

    print("=== 受信データ ===")
    print(body)

    for event in body.get("events", []):
        if event.get("type") != "message":
            continue

        if event["message"].get("type") != "text":
            continue

        reply_token = event["replyToken"]
        user_msg = event["message"]["text"]

        headers = {
            "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }

        data = {
            "replyToken": reply_token,
            "messages": [
                {
                    "type": "text",
                    "text": f"お前『{user_msg}』って言ったなｗ"
                }
            ]
        }

        res = requests.post(
            "https://api.line.me/v2/bot/message/reply",
            headers=headers,
            json=data
        )

        print("=== LINE返信結果 ===")
        print("status:", res.status_code)
        print("body:", res.text)

    return "OK"
