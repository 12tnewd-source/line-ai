from fastapi import FastAPI, Request
import requests
import os

app = FastAPI()

print("■■■■ 起動確認 ■■■■")

LINE_ACCESS_TOKEN = os.getenv("6h41NNLXlj9bQ4rnrD6zA2ZHwkogPQBA4zmThlv+hYHfwi7L+WseAEs6aZcqyx9nGRkOPity8DBhjkmyzhmJAu1h0rnlb4ZxMYRh5Xmp6dBfMP7aHz6mm7whitbd8H+tR7LdpvQ1fdFbES+6/zWnGQdB04t89/1O/w1cDnyilFU=")

print("TOKEN:", LINE_ACCESS_TOKEN)

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
