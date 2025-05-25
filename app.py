from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, MessagingApiBlob,
    PushMessageRequest, TextMessage  # 移除了 ReplyMessageRequest，因為我們將主要用 Push
)
from linebot.v3.webhooks import MessageEvent, AudioMessageContent
from whisper_helper import transcribe_audio
from summarizer import summarize_text
import os
from dotenv import load_dotenv
import uuid
import threading # <--- 引入 threading 模組

# ... (其他載入和設定，保持不變) ...
load_dotenv()
app = Flask(__name__)
configuration = Configuration(access_token=os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

# 這個函式將包含您原本 handle_audio 的主要邏輯，並在背景執行緒中運行
def process_audio_in_background(event_data, app_context):
    # 在新的執行緒中，我們需要 Flask 的應用程式上下文
    with app_context:
        user_id = event_data['source']['userId']
        message_id = event_data['message']['id']
        # reply_token = event_data['replyToken'] # reply_token 可能很快失效，推送時不需要

        app.logger.info(f"背景處理開始 - 用戶: {user_id}, 訊息ID: {message_id}")
        temp_audio_path = f"temp_audio_{uuid.uuid4()}.m4a"
        final_message_to_user = "抱歉，處理您的請求時發生了未知的錯誤。"

        try:
            with ApiClient(configuration) as api_client_blob:
                messaging_api_blob = MessagingApiBlob(api_client_blob)
                app.logger.info(f"背景：正在下載 message_id: {message_id} 的內容")
                audio_data_bytes = messaging_api_blob.get_message_content(message_id)
                
                if audio_data_bytes is None:
                    app.logger.error(f"背景：下載音訊失敗 (message_id: {message_id})，get_message_content 返回 None")
                    final_message_to_user = "抱歉，無法取得您傳送的音訊內容。"
                elif isinstance(audio_data_bytes, bytes):
                    app.logger.info(f"背景：成功下載音訊 (message_id: {message_id})")
                    with open(temp_audio_path, "wb") as f:
                        f.write(audio_data_bytes)
                    app.logger.info(f"背景：音訊已儲存到 {temp_audio_path}")

                    text = transcribe_audio(temp_audio_path)
                    app.logger.info(f"背景：語音轉文字結果 (前100字): {text[:100]}...")
                    
                    if "語音轉文字服務目前暫時無法使用" in text or "Expected key.size" in text or "Key and Value must have the same sequence length" in text:
                        app.logger.warning(f"背景：Whisper 錯誤: {text}")
                        final_message_to_user = "抱歉，語音轉錄似乎出了一點小問題，請稍後再試一次喔！"
                    else:
                        summary = summarize_text(text)
                        app.logger.info(f"背景：摘要結果 (前100字): {summary[:100]}...")
                        if "摘要服務發生錯誤" in summary or "摘要服務暫時無法提供" in summary:
                            app.logger.warning(f"背景：Summarizer 錯誤: {summary}")
                            final_message_to_user = "抱歉，內容摘要似乎出了一點小問題，請稍後再試一次喔！"
                        else:
                            final_message_to_user = summary 
                else:
                    app.logger.error(f"背景：下載音訊時 get_message_content 返回了未預期的型別: {type(audio_data_bytes)}")
                    final_message_to_user = "處理音訊檔案時發生了非預期的錯誤。"
            
        except Exception as e:
            app.logger.error(f"背景：處理語音或摘要時發生錯誤 (用戶 {user_id}): {e}", exc_info=True)
            final_message_to_user = "哎呀，處理您的請求時遇到了一些麻煩，請稍後再試。"
        finally:
            if os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)
                app.logger.info(f"背景：臨時音訊檔案已刪除: {temp_audio_path}")

        if user_id:
            try:
                with ApiClient(configuration) as api_client_push:
                    push_api = MessagingApi(api_client_push)
                    push_api.push_message(
                        PushMessageRequest(
                            to=user_id,
                            messages=[TextMessage(text=final_message_to_user)]
                        )
                    )
                    app.logger.info(f"背景：已成功推送訊息給用戶 {user_id}")
            except Exception as e:
                app.logger.error(f"背景：推送訊息給用戶 {user_id} 失敗: {e}", exc_info=True)

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    app.logger.info(f"Webhook 請求 Body: {body}")

    try:
        # WebhookHandler 解析事件，並觸發對應的 @handler.add 裝飾的函數
        # 我們讓 handler.handle 保持同步，但它呼叫的 handle_audio_event 將會啟動一個線程
        handler.handle(body, signature)
    except Exception as e:
        app.logger.error(f"處理 Webhook 時發生嚴重錯誤: {e}", exc_info=True)
        abort(400) # 如果 handle 過程本身出錯，例如簽名驗證失敗
    
    return "OK" # <<< 關鍵：快速返回 OK 給 LINE

@handler.add(MessageEvent, message=AudioMessageContent)
def handle_audio_event(event): # 重新命名以區分，或者您可以保持原名並修改其內部
    # 為了將 event 物件或其內容傳遞給新執行緒，最好是傳遞可序列化的資料
    # 或者確保 event 物件可以在執行緒間安全傳遞
    # 這裡我們直接傳遞 event，但要注意如果 event 物件複雜且不可序列化，可能需要轉換
    
    # 獲取當前的 Flask 應用程式上下文
    current_app_context = app.app_context()

    # 創建並啟動一個新的執行緒來處理耗時任務
    # 注意：event 物件本身可能包含不可序列化或執行緒不安全的內容，
    # 更安全的方式是僅提取必要的信息（如 user_id, message_id, reply_token）並作為字典傳遞。
    # 但為了簡化，我們先嘗試直接傳遞 event。
    # 為了安全，我們將 event 轉換為字典
    event_data = {
        "source": {"userId": event.source.user_id},
        "message": {"id": event.message.id, "type": event.message.type},
        "reply_token": event.reply_token # 雖然推送時不用，但先留著
    }
    thread = threading.Thread(target=process_audio_in_background, args=(event_data, current_app_context))
    thread.start()

    # 這個 handle_audio_event 函數現在會很快返回，
    # 讓 callback 路由也能夠快速返回 "OK" 給 LINE
    app.logger.info(f"已為 message_id {event.message.id} 啟動背景處理執行緒。")


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)), debug=True)