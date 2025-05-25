from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, TextMessage, MessagingApiBlob # <--- 加入 MessagingApiBlob
from linebot.v3.webhooks import MessageEvent, AudioMessageContent
from whisper_helper import transcribe_audio
from summarizer import summarize_text
import os
from dotenv import load_dotenv
import uuid # 新增，用於生成唯一檔名

# 載入 .env 檔案中的環境變數
load_dotenv()

app = Flask(__name__)

# v3 版本的配置和 API 客戶端初始化
# 注意：v3 的 MessagingApi 和 WebhookHandler 不再直接接收 token 和 secret
# 而是在 Configuration 中設定，然後傳給 ApiClient
configuration = Configuration(
    access_token=os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
)

handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except Exception as e:
        print(f"處理 Webhook 錯誤: {e}")
        # 如果發生錯誤，通常返回 400 Bad Request
        abort(400)
    
    return "OK"

@handler.add(MessageEvent, message=AudioMessageContent)
def handle_audio(event):
    message_id = event.message.id

    # 確保臨時檔案名是唯一的，以避免衝突
    temp_audio_path = f"temp_audio_{uuid.uuid4()}.m4a"

@handler.add(MessageEvent, message=AudioMessageContent)
def handle_audio(event):
    message_id = event.message.id
    temp_audio_path = f"temp_audio_{uuid.uuid4()}.m4a"

    try:
        with ApiClient(configuration) as api_client:
            messaging_api = MessagingApiBlob(api_client) # 確保這是 MessagingApiBlob
            print(f"DEBUG: Type of messaging_api: {type(messaging_api)}") # 這行可以保留或移除

            print(f"DEBUG: Attempting to get content for message_id: {message_id}")
            audio_data_bytes = messaging_api.get_message_content(message_id) # 直接接收 bytes 資料
            print(f"DEBUG: Type of value returned: {type(audio_data_bytes)}")
            # 您可以印出一小部分 bytes 來確認，但不要印全部，因為可能很長
            # print(f"DEBUG: Value returned by get_message_content (first 100 bytes): {audio_data_bytes[:100]}")

            if audio_data_bytes is None:
                print(f"ERROR: get_message_content returned None for message_id: {message_id}")
                # 可以在這裡回覆錯誤訊息給用戶
                with ApiClient(configuration) as error_api_client:
                    error_messaging_api = MessagingApi(error_api_client)
                    error_messaging_api.reply_message(
                        ReplyMessageRequest(
                            reply_token=event.reply_token,
                            messages=[TextMessage(text="抱歉，無法取得您傳送的音訊內容。")]
                        )
                    )
                return # 提前結束，不再處理

            elif isinstance(audio_data_bytes, bytes):
                print(f"DEBUG: Successfully received audio data as bytes for message_id: {message_id}")
                with open(temp_audio_path, "wb") as f:
                    f.write(audio_data_bytes) # 直接將 bytes 寫入檔案
                print(f"DEBUG: Audio content written to {temp_audio_path}")
            else:
                # 理論上不太可能走到這裡，因為上面已經確認是 bytes 或 None
                print(f"ERROR: get_message_content returned an unexpected type: {type(audio_data_bytes)}")
                # 也可以在這裡回覆錯誤訊息給用戶
                return # 提前結束

        # --- 音訊已成功儲存，接下來進行轉錄和摘要 ---
        text = transcribe_audio(temp_audio_path)
        summary = summarize_text(text)

        # 使用 v3 的 TextMessage 和 ReplyMessageRequest
        with ApiClient(configuration) as api_client:
            messaging_api_reply = MessagingApi(api_client) # 為了清晰，可以改個名字
            messaging_api_reply.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=summary)]
                )
            )
            print(f"回覆成功: {summary}")

    except Exception as e:
        print(f"處理語音或摘要時發生錯誤: {e}")
        # 在這裡可以發送錯誤訊息給用戶
        with ApiClient(configuration) as api_client:
            messaging_api_error = MessagingApi(api_client) # 為了清晰，可以改個名字
            messaging_api_error.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text="抱歉，處理您的請求時發生內部錯誤。")]
                )
            )
    finally:
        # 確保臨時檔案被刪除
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)
            print(f"臨時音訊檔案已刪除: {temp_audio_path}")

if __name__ == "__main__":
    app.run(port=5000)