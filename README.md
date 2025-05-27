# Line Bot 語音訊息分析器

一個 LINE Bot，能夠自動接收用戶的語音訊息或音訊檔案，並利用 AI 技術提供語音轉文字 (Speech-to-Text) 及智慧摘要功能。這款 Bot 旨在幫助用戶快速掌握冗長語音內容的重點，提高溝通效率。

## ✨ 主要功能

- **語音轉文字 (STT)**：自動將 LINE 用戶傳送的語音訊息或音訊檔案（支援 `.m4a`, `.mp3`, `.wav`, `.aac`, `.amr` 等格式）精準地轉錄成文字。
- **智慧摘要**：利用 Google Gemini Pro 1.5 Flash 模型對轉錄後的文字內容進行智慧摘要，提供簡潔扼要的重點歸納。
- **逐字稿下載**：為用戶提供一個公開連結，方便下載完整的逐字稿檔案，以備查閱。
- **即時回覆與背景處理**：當收到語音訊息時，Bot 會立即回覆「處理中」訊息，並在背景執行繁重的轉錄和摘要任務，確保 LINE 平台的響應時間要求。
- **彈性檔案支援**：除了 LINE 內建的語音訊息外，也支援用戶以檔案形式傳送的音訊檔。

## 🛠️ 技術棧

- **Python**: 主要開發語言
- **Flask**: 輕量級 Web 框架，用於處理 LINE Webhook
- **Line Bot SDK (v3)**: 整合 LINE Messaging API
- **Whisper**: 開源語音轉文字模型（本地運行 `medium` 模型）
- **Google Gemini 1.5 Flash API**: 用於文本摘要
- **`python-dotenv`**: 管理環境變數
- **`threading`**: 實現非同步背景處理

## 🚀 快速開始

### 環境設置

1.  **複製專案**

    ```bash
    git clone [https://github.com/XiaoPhonePro/LineBotCallAnalyzer.git](https://github.com/XiaoPhonePro/LineBotCallAnalyzer.git)
    cd LineBotCallAnalyzer
    ```

2.  **安裝依賴**

    建議使用 `venv` 建立虛擬環境：

    ```bash
    python -m venv LineBotCallingAnalyzer
    source bin/activate  #linux
    pip install -r requirements.txt
    ```

    `requirements.txt` 應包含：

    ```
    Flask
    line-bot-sdk # 或 line-bot-sdk-v3
    openai-whisper # 如果是使用 OpenAI 的 whisper 套件
    google-generativeai
    python-dotenv
    ```

    （請確保 `requirements.txt` 與您的實際依賴相符，尤其是 Whisper 模型的相關套件）

3.  **配置環境變數**

    在專案根目錄創建一個 `.env` 檔案，並填入以下資訊：

    ```
    LINE_CHANNEL_ACCESS_TOKEN="您的 LINE Channel Access Token"
    LINE_CHANNEL_SECRET="您的 LINE Channel Secret"
    GEMINI_API_KEY="您的 Google Gemini API Key"
    YOUR_PUBLIC_BASE_URL="您的 LINE Bot 的公開 HTTPS URL (例如：[https://your-ngrok-url.ngrok.io](https://your-ngrok-url.ngrok.io) 或 [https://your-domain.com](https://your-domain.com))"
    ```

    - `LINE_CHANNEL_ACCESS_TOKEN` 和 `LINE_CHANNEL_SECRET`：從 [LINE Developers](https://developers.line.biz/) 取得。
    - `GEMINI_API_KEY`：從 [Google AI Studio](https://aistudio.google.com/app/apikey) 取得。
    - `YOUR_PUBLIC_BASE_URL`：這是非常重要的設定，用於生成逐字稿的公開下載連結。如果您在本地測試，可以使用 [Ngrok](https://ngrok.com/) 等工具暴露本地服務，並將 Ngrok 生成的 HTTPS URL 填入。部署到伺服器時，請填寫您的域名。

### 運行 Bot

```bash
python app.py
```
