@app.post("/callback")
async def callback(request: Request):
    body = await request.json()

    for event in body["events"]:
        if event["type"] != "message":
            continue
        if event["message"]["type"] != "text":
            continue

        reply_token = event["replyToken"]
        user_msg = event["message"]["text"]

        headers = {
            "Authorization": f"Bearer {LINE_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }

        data = {
            "replyToken": reply_token,
            "messages": [{
                "type": "text",
                "text": "動いたで！"
            }]
        }

        requests.post(
            "https://api.line.me/v2/bot/message/reply",
            headers=headers,
            json=data
        )

    return "OK"
