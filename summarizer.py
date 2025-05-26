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
GEMINI_MODEL_NAME = "models/gemini-1.5-flash-latest"
model = genai.GenerativeModel(GEMINI_MODEL_NAME)

def summarize_text(text: str) -> str:
    """
    使用 Google Gemini API 對文本進行摘要，並根據要求進行處理。

    Args:
        text: 需要摘要的原始文本。

    Returns:
        處理後的摘要文本。
    """
    if not text.strip():
        return "嗯...您好像沒有提供內容喔，我無法進行摘要呢！🤔"

    # 設計一個更詳細、更友善的提示語 (prompt)
    prompt = f"""你好呀！我是一個聰明又樂於助人的 AI 小助手 🤖。請你幫我分析一下這段從語音轉錄過來的文字：

    '''
    {text}
    '''

    請你按照下面的步驟來幫我整理：

    1.  語言判斷：首先，請你判斷這段文字最可能是用哪一種語言說的。然後用繁體中文告訴我，例如：「這段語音的原始語言聽起來像是：英文」。

    3.  重點摘要 (繁體中文)：
        接下來，請把這段文字的主要內容翻譯成繁體中文，並且整理出一個簡潔的重點大綱或摘要。
        目標是讓我能快速抓住核心資訊，所以請幫我把重點條理分明地列出來，或者用一段流暢的話總結。
        摘要的長度請盡量控制在 100~200 字左右就好，如果原文比較短，摘要就簡短一點也沒關係。
        為了讓內容看起來更活潑，可以在摘要中穿插 1 到 2 個相關的表情符號 (emoji) 喔！😉
        輸出格式：請確保最終的摘要是純文字 (plain text)，不要包含任何 Markdown 格式的標記 (例如 `*`、`#`、`-`、`[]()` 等)，讓輸出看起來乾淨整潔。


    請用親切友善幽默的語氣呈現結果，謝謝你啦！😊
    """
    try:
        response = model.generate_content(prompt,
                                          safety_settings={'HARASSMENT': 'BLOCK_NONE',
                                                           'HATE': 'BLOCK_NONE',
                                                           'SEXUAL': 'BLOCK_NONE',
                                                           'DANGEROUS': 'BLOCK_NONE'})
        
        # 檢查是否有回應內容
        if response.candidates and response.candidates[0].content.parts:
            summary = response.candidates[0].content.parts[0].text
            return summary.strip()
        else:
            # 如果沒有候選，可能發生了內容過濾或其他問題
            print(f"Gemini API 沒有產生回應，可能的原因：{response.prompt_feedback}")
            return "哎呀，我好像有點轉不過來，摘要服務暫時無法提供，請稍後再試試看。😥"

    except Exception as e:
        print(f"調用 Gemini API 時發生錯誤: {e}")
        return "糟糕！摘要服務好像出了點小問題，麻煩稍後再試一次，或聯絡管理員喔。🛠️"

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