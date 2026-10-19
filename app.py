import streamlit as st
import json
import os
import datetime
import google.generativeai as genai
from PIL import Image

# --- AIの目の準備 ---
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.error("APIキーが設定されていません。Streamlitの設定(Secrets)を確認してください。")

DATA_FILE = "learning_history.json"
PENDING_FILE = "pending_races.json"

# --- データ保存・読み込み機能 ---
def load_json(file_path):
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_json(file_path, data):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def save_pending_race(race_data):
    pending = load_json(PENDING_FILE)
    pending.append(race_data)
    save_json(PENDING_FILE, pending)

def extract_data_from_image(image):
    """Geminiを使って画像からデータと『並び予想』を抽出"""
    # ★システムが不安定な場合は 'gemini-2.5-flash' に戻してみてください
    model = genai.GenerativeModel('gemini-flash-latest')
    
    # ★単騎の場合の書き方をお手本に追加し、AIのパニックを防止！
    prompt = """
    この競輪の出走表画像から、選手のデータと「並び予想（ライン）」を抽出してJSON形式で出力してください。
    以下のフォーマットのみを出力し、他のテキストは含めないでください。
    {
      "選手": [
        {
          "車番": 1,
          "選手名": "名前",
          "競走得点": 100.50,
          "基本印": "◎",
          "ライン役割": "先頭",
          "H": 5,
          "B": 4,
          "逃": 2,
          "捲": 1,
          "差": 0,
          "マ": 0
        }
      ],
      "並び予想": [
        [1, 7, 2],
        [5],
        [4, 3, 6]
      ]
    }
    基本印がない場合は "" にしてください。選手名が読み取れない場合や塗りつぶされている場合は "" (空白) にしてください。
    並び予想は、画像の下部にある矢印（←）の並び通りに、車番の数字の配列の配列として作ってください（単騎の場合は [5] のように1つの数字だけの配列にしてください）。
    """
    response = model.generate_content([prompt, image])
    json_text = response.text.replace('```json', '').replace('```', '').strip()
    return json.loads(json_text)

def apply_custom_marks(data):
    """マスター直伝！ライン相乗効果（新ルール）を適用"""
    players = data.get("選手", [])
    lines = data.get("並び予想", [])
    
    player_dict = {p["車番"]: p for p in players}
    
    for line in lines:
        if len(line) == 1:
            # ★単騎の場合の処理
            current_car = line[0]
            if current_car in player_dict:
                curr_p = player_dict[current_car]
                if curr_p.get("基本印", "") == "":
                    curr
