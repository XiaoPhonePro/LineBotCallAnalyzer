import time  # 用於計時
from flask import Flask, request, abort, current_app
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, MessagingApiBlob, ReplyMessageRequest,
    PushMessageRequest, TextMessage  # 移除了 ReplyMessageRequest，因為我們將主要用 Push
)
from linebot.v3.webhooks import MessageEvent, AudioMessageContent, FileMessageContent
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
    with flask_app_context:
        user_id = event_data['source']['userId']
        message_id = event_data['message']['id']
        original_file_name = event_data['message'].get('fileName', f"audio_{message_id}")
        
        app.logger.info(f"背景處理開始 - 用戶: {user_id}, 訊息ID: {message_id}, 檔案名: {original_file_name}")
        
        unique_file_prefix = str(uuid.uuid4())
        temp_audio_path = f"temp_audio_{unique_file_prefix}.m4a"
        transcript_file_name_local = f"transcript_{unique_file_prefix}.txt"
        
        final_message_to_user = "抱歉，處理您的請求時發生了未知的錯誤。"
        analysis_duration_text = ""
        transcript_url = None

        audio_data_bytes = None
        api_response_status_for_logging = None # 用於記錄最終的API狀態

        try:
            # --- 下載音訊 (包含針對 HTTP 202 的重試機制) ---
            with ApiClient(configuration) as api_client_blob:
                messaging_api_blob = MessagingApiBlob(api_client_blob)
                app.logger.info(f"背景：開始下載 message_id: {message_id} 的內容 (含重試機制)")
                
                MAX_RETRIES = 5  # 最多重試5次
                retry_delay_seconds = 3 # 初始延遲3秒

                for attempt in range(MAX_RETRIES):
                    app.logger.info(f"背景：下載嘗試 {attempt + 1}/{MAX_RETRIES} for message_id: {message_id}")
                    try:
                        api_response = messaging_api_blob.get_message_content_with_http_info(message_id=message_id)
                        api_response_status_for_logging = api_response.status_code # 更新狀態碼記錄
                        
                        if api_response.status_code == 200: # 成功
                            if isinstance(api_response.data, bytes):
                                audio_data_bytes = api_response.data
                                app.logger.info(f"背景：成功下載音訊 (message_id: {message_id})")
                                break # 成功下載，跳出重試迴圈
                            else:
                                app.logger.error(f"背景：HTTP 200 但回傳的 data 不是 bytes 型態: {type(api_response.data)}. Message_id: {message_id}")
                                # 這種情況也視為本次嘗試失敗
                        elif api_response.status_code == 202: # 接受請求，內容處理中
                            app.logger.info(f"背景：收到 HTTP 202 (Accepted) for message_id: {message_id}. 等待 {retry_delay_seconds} 秒後重試...")
                            if attempt < MAX_RETRIES - 1: # 如果不是最後一次嘗試
                                time.sleep(retry_delay_seconds)
                                retry_delay_seconds = min(retry_delay_seconds * 2, 30) # 指數退避，最長等待30秒
                            else:
                                app.logger.error(f"背景：達到最大重試次數 ({MAX_RETRIES})，message_id: {message_id} 內容仍未準備好 (HTTP 202)。")
                        else: # 其他 HTTP 錯誤 (例如 400, 401, 403, 404, 500 等)
                            response_body_preview = api_response.data
                            if isinstance(response_body_preview, bytes):
                                try:
                                    response_body_preview = response_body_preview.decode('utf-8', errors='ignore')[:200]
                                except Exception: pass
                            app.logger.error(f"背景：下載音訊失敗 (message_id: {message_id})，HTTP 狀態碼: {api_response.status_code}, 回應 Body (預覽): {response_body_preview}")
                            break # 確定性錯誤，跳出重試迴圈
                    except Exception as e_sdk_attempt: # SDK 本身拋出的錯誤 (例如網路問題)
                        app.logger.error(f"背景：第 {attempt + 1} 次下載嘗試時發生 SDK 錯誤 (message_id: {message_id}): {e_sdk_attempt}", exc_info=True)
                        if hasattr(e_sdk_attempt, 'status') and e_sdk_attempt.status: # 有些 SDK 錯誤物件可能包含 status 屬性
                             api_response_status_for_logging = e_sdk_attempt.status
                        if attempt < MAX_RETRIES - 1:
                            time.sleep(retry_delay_seconds)
                            retry_delay_seconds = min(retry_delay_seconds * 2, 30)
                        else:
                            app.logger.error(f"背景：達到最大重試次數 ({MAX_RETRIES})，SDK 錯誤持續 for message_id: {message_id}。")
                        # 如果是網路錯誤等，繼續下一次重試或結束迴圈

            # --- 下載音訊部分結束 ---

            if audio_data_bytes is None: # 檢查最終是否成功下載到音訊
                app.logger.error(f"背景：最終下載音訊失敗 (message_id: {message_id})。最後記錄的 API 狀態: {api_response_status_for_logging}")
                error_detail = f" (API 狀態: {api_response_status_for_logging})" if api_response_status_for_logging else ""
                final_message_to_user = f"抱歉，無法取得您傳送的音訊內容{error_detail}。可能檔案較大正在處理中或暫時無法存取，請稍後再試。"
            elif isinstance(audio_data_bytes, bytes):
                # 音訊下載成功，繼續後續處理
                app.logger.info(f"背景：音訊內容已成功獲取，準備寫入檔案 (message_id: {message_id})")
                with open(temp_audio_path, "wb") as f:
                    f.write(audio_data_bytes)
                app.logger.info(f"背景：音訊已儲存到 {temp_audio_path}")

                analysis_start_time = time.time()
                text = transcribe_audio(temp_audio_path)
                app.logger.info(f"背景：語音轉文字結果 (前100字): {text[:100]}...")
                
                is_transcription_error = "語音轉文字服務目前暫時無法使用" in text or \
                                         "Expected key.size" in text or \
                                         "Key and Value must have the same sequence length" in text
                
                if is_transcription_error:
                    app.logger.warning(f"背景：Whisper 錯誤: {text}")
                    final_message_to_user = f"抱歉，語音轉錄似乎出了一點小問題：\n「{text}」"
                    analysis_end_time = time.time()
                    duration = analysis_end_time - analysis_start_time
                    analysis_duration_text = f"\n\n(處理耗時約 {duration:.1f} 秒)"
                    final_message_to_user += analysis_duration_text
                else:
                    try:
                        with open(transcript_file_name_local, "w", encoding="utf-8") as tf:
                            tf.write(text)
                        app.logger.info(f"背景：逐字稿已儲存到本地檔案: {transcript_file_name_local}")
                        # 【重要】上傳逐字稿檔案到公開網路空間，並獲取其 URL
                        # transcript_url = upload_file_to_cloud(transcript_file_name_local) # 您需要實現這個函式
                        # 為了測試，暫時設為 None，或者您可以提供一個固定的測試 URL
                        transcript_url = None 
                        if transcript_url:
                             app.logger.info(f"背景：逐字稿已上傳，URL: {transcript_url}")
                        else:
                             app.logger.warning(f"背景：逐字稿URL未設定，將不會提供下載連結。請實現檔案上傳邏輯。")
                    except Exception as e_file_save:
                        app.logger.error(f"背景：儲存或處理逐字稿檔案失敗: {e_file_save}", exc_info=True)
                        transcript_url = None

                    summary = summarize_text(text)
                    app.logger.info(f"背景：摘要結果 (前100字): {summary[:100]}...")
                    
                    analysis_end_time = time.time()
                    duration = analysis_end_time - analysis_start_time
                    analysis_duration_text = f"\n\n(分析處理時間：{duration:.1f} 秒)"

                    is_summary_error = "摘要服務發生錯誤" in summary or "摘要服務暫時無法提供" in summary
                    if is_summary_error:
                        app.logger.warning(f"背景：Summarizer 錯誤: {summary}")
                        message_parts = [f"語音轉錄完成，但摘要服務有點小狀況。{analysis_duration_text}"]
                        if transcript_url:
                            message_parts.append(f"\n\n您可以點擊連結下載完整逐字稿：\n{transcript_url}")
                        else:
                            message_parts.append(f"\n\n逐字稿內容：\n{text[:300]}..." if len(text) > 300 else f"\n\n逐字稿內容：\n{text}")
                        final_message_to_user = "".join(message_parts)
                    else:
                        message_parts = [summary]
                        if transcript_url:
                            message_parts.append(f"\n\n您可以點擊以下連結下載完整逐字稿：\n{transcript_url}")
                        message_parts.append(analysis_duration_text)
                        final_message_to_user = "".join(message_parts)
            else: # audio_data_bytes is not None and not bytes, and not handled by 200/202 logic. Should be rare.
                app.logger.error(f"背景：下載音訊時 get_message_content_with_http_info 返回了未預期的資料結構 (message_id: {message_id})")
                final_message_to_user = "處理音訊檔案時發生了非預期的內部錯誤。"
        
        except Exception as e:
            app.logger.error(f"背景：處理語音或摘要時發生嚴重錯誤 (用戶 {user_id}, message_id: {message_id}): {e}", exc_info=True)
            # ... (設定 final_message_to_user 的錯誤訊息邏輯，可以與之前類似) ...
            final_message_to_user = "哎呀，處理您的請求時遇到了一些技術問題，請稍後再試。"


        finally:
            if os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)
                app.logger.info(f"背景：臨時音訊檔案已刪除: {temp_audio_path}")
            if os.path.exists(transcript_file_name_local):
                try:
                    os.remove(transcript_file_name_local)
                    app.logger.info(f"背景：本地逐字稿檔案已刪除: {transcript_file_name_local}")
                except Exception as e_remove_transcript:
                    app.logger.error(f"背景：刪除本地逐字稿檔案失敗: {e_remove_transcript}")
        
        # --- 推送最終訊息給用戶 ---
        # (您原有的推送和長度檢查邏輯可以保持不變)
        if user_id:
            # ... (推送邏輯) ...
            if len(final_message_to_user) > 4900: 
                app.logger.warning(f"推送訊息過長 ({len(final_message_to_user)} 字元)，將進行截斷。")
                ending_part = ""
                if analysis_duration_text and final_message_to_user.endswith(analysis_duration_text):
                    ending_part = analysis_duration_text
                    max_len_for_summary = 4900 - len(ending_part) - 20 
                    final_message_to_user = final_message_to_user[:max_len_for_summary] + "...\n（內容過長，部分訊息已截斷）" + ending_part
                else:
                    final_message_to_user = final_message_to_user[:4900] + "...\n（內容過長，部分訊息已截斷）"
                app.logger.info(f"截斷後的訊息長度: {len(final_message_to_user)}")
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
def handle_file_message(event):
    user_id = event.source.user_id
    message_id = event.message.id
    reply_token = event.reply_token

    file_name = event.message.file_name
    file_size = event.message.file_size
    app.logger.info(f"Webhook 收到來自用戶 {user_id} 的檔案訊息: {file_name}, 大小: {file_size} bytes, message_id: {message_id}")

    # 判斷是否為我們想處理的音訊檔案類型 (例如 .m4a)
    allowed_audio_extensions = ['.m4a', '.mp3', '.wav', '.aac', '.amr'] # 您想支援的音訊格式
    is_audio_file = any(file_name.lower().endswith(ext) for ext in allowed_audio_extensions)

    if is_audio_file:
        app.logger.info(f"檔案 {file_name} 被識別為音訊檔案，準備進行處理。")
        
        # --- 立即回覆「處理中」 ---
        try:
            with ApiClient(configuration) as api_client:
                ack_messaging_api = MessagingApi(api_client)
                ack_messaging_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=reply_token,
                        messages=[TextMessage(text=f"收到您的音訊檔案 '{file_name}'，我正在努力分析中，請稍候...⏳")]
                    )
                )
            app.logger.info(f"已向用戶 {user_id} 發送檔案接收確認")
        except Exception as e:
            app.logger.error(f"發送檔案接收確認回覆失敗 (用戶 {user_id}): {e}", exc_info=True)

        # --- 準備背景處理 ---
        event_data = {
            "source": {"userId": user_id},
            "message": {"id": message_id, "type": "file", "fileName": file_name}, 
        }
        flask_app_context = current_app.app_context()
        thread = threading.Thread(target=process_audio_in_background, args=(event_data, flask_app_context))
        thread.start()
        app.logger.info(f"已為檔案訊息 message_id {message_id} ({file_name}) 啟動背景處理執行緒。")

    else:
        app.logger.info(f"檔案 {file_name} 不是支援的音訊格式，不進行處理。")
        try:
            with ApiClient(configuration) as api_client:
                error_messaging_api = MessagingApi(api_client)
                error_messaging_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=reply_token,
                        messages=[TextMessage(text=f"抱歉，我目前只支援處理常見的音訊檔案格式喔。您傳送的是：{file_name}")]
                    )
                )
        except Exception as e:
            app.logger.error(f"回覆檔案類型不支援訊息失敗: {e}", exc_info=True)


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)), debug=True)