import time  # 用於計時
from flask import Flask, request, abort, current_app
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, MessagingApiBlob, ReplyMessageRequest,
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
def process_audio_in_background(event_data, flask_app_context):
    with flask_app_context: # 確保在執行緒中有 Flask 的應用程式上下文
        user_id = event_data['source']['userId']
        message_id = event_data['message']['id']
        
        app.logger.info(f"背景處理開始 - 用戶: {user_id}, 訊息ID: {message_id}")
        temp_audio_path = f"temp_audio_{uuid.uuid4()}.m4a" # uuid.uuid4() is an object, f-string handles it
        final_message_to_user = "抱歉，處理您的請求時發生了未知的錯誤。"
        analysis_duration_text = "" # 初始化分析時間的文字

        try:
            # --- 下載音訊 ---
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

                # --- 開始計時：語音轉文字 和 摘要 ---
                analysis_start_time = time.time()

                text = transcribe_audio(temp_audio_path)
                app.logger.info(f"背景：語音轉文字結果 (前100字): {text[:100]}...")
                
                is_transcription_error = "語音轉文字服務目前暫時無法使用" in text or \
                                         "Expected key.size" in text or \
                                         "Key and Value must have the same sequence length" in text
                
                if is_transcription_error:
                    app.logger.warning(f"背景：Whisper 錯誤: {text}")
                    final_message_to_user = f"抱歉，語音轉錄似乎出了一點小問題：\n「{text}」" # 包含 Whisper 的錯誤訊息
                    analysis_end_time = time.time() # 即使失敗也記錄時間
                    duration = analysis_end_time - analysis_start_time
                    analysis_duration_text = f"\n\n(處理耗時約 {duration:.1f} 秒)"
                    final_message_to_user += analysis_duration_text
                else:
                    # --- 文本摘要 ---
                    summary = summarize_text(text) # 這是 AI 生成的摘要本文
                    app.logger.info(f"背景：摘要結果 (前100字): {summary[:100]}...")
                    
                    analysis_end_time = time.time() # 記錄結束時間
                    duration = analysis_end_time - analysis_start_time
                    analysis_duration_text = f"\n\n(分析處理時間：{duration:.1f} 秒)"

                    is_summary_error = "摘要服務發生錯誤" in summary or "摘要服務暫時無法提供" in summary
                    if is_summary_error:
                        app.logger.warning(f"背景：Summarizer 錯誤: {summary}")
                        # 如果摘要失敗，可以選擇回傳原始轉錄文字和處理時間
                        final_message_to_user = f"這是為您轉錄的文字內容：\n「{text}」{analysis_duration_text}\n\n(摘要服務暫時有點小狀況，請稍後再試喔！)"
                    else:
                        final_message_to_user = f"{summary}{analysis_duration_text}" # 成功，附加時間
            else: # audio_data_bytes is not None and not bytes
                app.logger.error(f"背景：下載音訊時 get_message_content 返回了未預期的型別: {type(audio_data_bytes)}")
                final_message_to_user = "處理音訊檔案時發生了非預期的錯誤。"
        
        except Exception as e:
            app.logger.error(f"背景：處理語音或摘要時發生嚴重錯誤 (用戶 {user_id}): {e}", exc_info=True)
            try:
                # 嘗試計算到錯誤發生前的時間 (如果 analysis_start_time 已定義)
                if 'analysis_start_time' in locals() and analysis_start_time:
                    error_time = time.time()
                    duration = error_time - analysis_start_time
                    analysis_duration_text = f"\n\n(處理至錯誤發生約耗時 {duration:.1f} 秒)"
                    final_message_to_user = f"哎呀，處理您的請求時遇到了一些技術問題，請稍後再試。{analysis_duration_text}"
                else:
                    final_message_to_user = "哎呀，處理您的請求時遇到了一些技術問題，請稍後再試。"
            except Exception: # 防一手，如果上面 try-except 內還有問題
                 final_message_to_user = "哎呀，處理您的請求時遇到了一些技術問題，請稍後再試。"

        finally:
            if os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)
                app.logger.info(f"背景：臨時音訊檔案已刪除: {temp_audio_path}")

        # --- 推送最終訊息給用戶 ---
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
                    app.logger.info(f"背景：已成功推送訊息給用戶 {user_id}: {final_message_to_user}")
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
def handle_audio_event(event): # 這個函數由 Line SDK 同步調用
    reply_token = event.reply_token
    user_id = event.source.user_id
    message_id = event.message.id

    app.logger.info(f"Webhook 收到來自用戶 {user_id} 的音訊訊息，message_id: {message_id}。")

    # --- 步驟 1: 立即回覆「處理中」訊息 ---
    try:
        with ApiClient(configuration) as api_client:
            ack_messaging_api = MessagingApi(api_client)
            ack_messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text="收到您的語音訊息，我正在努力分析中，請稍候片刻...⏳")]
                )
            )
        app.logger.info(f"已向用戶 {user_id} 發送確認收到的回覆")
    except Exception as e:
        app.logger.error(f"發送確認回覆失敗 (用戶 {user_id}): {e}", exc_info=True)
        # 即使這個即時回覆失敗了，我們還是要繼續處理後續的任務

    # 準備傳遞給背景執行緒的資料
    event_data = {
        "source": {"userId": user_id},
        "message": {"id": message_id, "type": event.message.type},
    }
    
    flask_app_context = current_app.app_context()

    # --- 步驟 2: 創建並啟動背景執行緒來處理耗時任務 ---
    thread = threading.Thread(target=process_audio_in_background, args=(event_data, flask_app_context))
    thread.start()
    
    app.logger.info(f"已為 message_id {message_id} 啟動背景處理執行緒。Webhook 將立即返回 OK。")
    # handle_audio_event 函數到此結束並快速返回，讓 /callback 路由可以快速回應 LINE


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)), debug=True)