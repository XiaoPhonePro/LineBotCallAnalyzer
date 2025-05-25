import os
from dotenv import load_dotenv
import google.generativeai as genai

# 載入 .env 檔案中的環境變數
load_dotenv()

# 從環境變數中取得 Gemini API 金鑰
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 配置 Gemini API
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable not set. Please set it in your .env file.")
genai.configure(api_key=GEMINI_API_KEY)

# 初始化 Gemini 模型
# 選擇適合摘要的模型，gemini-1.5-flash 速度快且費用相對低廉
# 如果需要更高品質的摘要，可以嘗試 gemini-1.5-pro
GEMINI_MODEL_NAME = "Gemini-2.5-Flash"
model = genai.GenerativeModel(GEMINI_MODEL_NAME)

def summarize_text(text: str) -> str:
    """
    使用 Google Gemini API 對文本進行摘要。

    Args:
        text: 需要摘要的原始文本。

    Returns:
        摘要後的文本。
    """
    if not text.strip():
        return "無法對空內容進行摘要。"

    # 設計一個清晰的提示語 (prompt)
    # 這裡可以根據需求調整摘要的風格、長度等
    prompt = f"""請將以下文本內容進行簡潔的摘要。重點提取關鍵資訊，並以條列式或一段話的形式呈現，控制在100字以內。

文本內容：
{text}

摘要：
"""
    try:
        # 使用 generate_content 進行文本生成
        # stream=False 表示等待完整回應
        # safety_settings 可以調整內容過濾嚴格度，通常預設即可
        response = model.generate_content(prompt,
                                          safety_settings={'HARASSMENT': 'BLOCK_NONE',
                                                           'HATE': 'BLOCK_NONE',
                                                           'SEXUAL': 'BLOCK_NONE',
                                                           'DANGEROUS': 'BLOCK_NONE'})
        
        # 檢查是否有回應內容
        if response.candidates:
            # 獲取第一個候選的回應文本
            summary = response.candidates[0].content.parts[0].text
            return summary.strip()
        else:
            # 如果沒有候選，可能發生了內容過濾或其他問題
            # 可以打印 response.prompt_feedback 來看具體原因
            print(f"Gemini API 沒有產生回應，可能的原因：{response.prompt_feedback}")
            return "摘要服務暫時無法提供，請稍後再試。"

    except Exception as e:
        print(f"調用 Gemini API 時發生錯誤: {e}")
        return "摘要服務發生錯誤，請聯絡管理員。"

# 測試用 (可選)
if __name__ == "__main__":
    test_text_short = "今天天氣很好，陽光普照，適合出遊。我打算下午去公園散步，晚上和朋友聚餐。"
    test_text_long = """
    人工智慧（Artificial Intelligence，簡稱 AI）是研究、開發用於模擬、延伸和擴展人的智慧的理論、方法、技術及應用系統的一門新的技術科學。它的目標是讓機器能夠像人類一樣思考、學習、推理和解決問題。AI 的應用領域非常廣泛，包括自然語言處理、電腦視覺、機器學習、機器人學等。近年來，隨著深度學習等技術的突破，AI 在許多領域取得了顯著進展，例如語音識別、圖像識別、自動駕駛和醫療診斷等。然而，AI 的發展也伴隨著倫理、安全和社會影響等方面的討論。AI 的未來充滿挑戰，但也充滿了無限的可能性，將對人類社會產生深遠影響。
    """
    test_text_empty = ""

    print(f"原始文本 (短): {test_text_short}")
    print(f"摘要 (短): {summarize_text(test_text_short)}\n")

    print(f"原始文本 (長): {test_text_long}")
    print(f"摘要 (長): {summarize_text(test_text_long)}\n")

    print(f"原始文本 (空): {test_text_empty}")
    print(f"摘要 (空): {summarize_text(test_text_empty)}\n")