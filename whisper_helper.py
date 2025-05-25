import whisper
# 如果你想使用 OpenAI API 的 Whisper 服務，則需要 from openai import OpenAI

# 載入 Whisper 模型 (本地運行)
# 只在文件最頂層載入一次，避免每次調用函式都重新載入
model = whisper.load_model("large") # 或其他模型大小如 "small", "medium", "large"

def transcribe_audio(filepath: str) -> str:
    """
    使用本地 Whisper 模型將音訊檔案轉錄為文字。

    Args:
        filepath: 音訊檔案的路徑。

    Returns:
        轉錄後的文字。
    """
    try:
        result = model.transcribe(filepath)
        return result["text"]
    except Exception as e:
        print(f"Whisper 轉錄音訊時發生錯誤: {e}")
        # 這裡可以根據需要，返回一個錯誤訊息或重新拋出異常
        return "語音轉文字服務暫時無法使用。"