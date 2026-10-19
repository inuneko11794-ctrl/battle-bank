import streamlit as st
import json
import os
import google.generativeai as genai
from PIL import Image

# --- AIの目の準備 ---
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.error("APIキーが設定されていません。Streamlitの設定(Secrets)を確認してください。")

DATA_FILE = "learning_history.json"

def load_history():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_history(new_data):
    history = load_history()
    history.append(new_data)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=4)

def extract_data_from_image(image):
    """Geminiを使って画像から出走表データを抽出"""
    model = genai.GenerativeModel('gemini-1.5-pro')
    prompt = """
    この競輪の出走表画像から、選手のデータを抽出してJSON形式で出力してください。
    以下のフォーマットの配列（リスト）のみを出力し、他のテキストは含めないでください。
    [
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
    ]
    基本印がない場合は "" にしてください。ライン役割は「先頭」「番手」「3番手」「単騎」から推測してください。
    """
    response = model.generate_content([prompt, image])
    json_text = response.text.replace('```json', '').replace('```', '').strip()
    return json.loads(json_text)

def calculate_brain_score(player):
    score = player.get("競走得点", 0.0)
    mark_scores = {"◎": 10, "◯": 8, "△": 6, "✕": 4}
    score += mark_scores.get(player.get("基本印", ""), 0)
    score += (player.get("H", 0) + player.get("B", 0)) * 0.5 
    
    role = player.get("ライン役割", "不明")
    if role == "先頭" or role == "単騎":
        score += (player.get("逃", 0) + player.get("捲", 0)) * 0.8
    else:
        score += (player.get("差", 0) + player.get("マ", 0)) * 0.8
    return round(score, 2)

def generate_bets(players, max_2t_points, max_3t_points):
    sorted_players = sorted(players, key=lambda x: x["AIスコア"], reverse=True)
    if len(sorted_players) < 3:
        return {"単勝": [], "2連単": [], "3連単": []}
    
    p1 = sorted_players[0]["車番"]
    p2 = sorted_players[1]["車番"]
    p3 = sorted_players[2]["車番"]
    p4 = sorted_players[3]["車番"] if len(sorted_players) > 3 else p3
    p5 = sorted_players[4]["車番"] if len(sorted_players) > 4 else p4
    
    # 2連単の買い目候補
    nitantan_candidates = [
        f"{p1} - {p2}",
        f"{p1} - {p3}",
        f"{p2} - {p1}",
        f"{p1} - {p4}",
        f"{p2} - {p3}",
        f"{p3} - {p1}",
        f"{p1} - {p5}"
    ]
    
    # 3連単の買い目候補
    santantan_candidates = [
        f"{p1} - {p2} - {p3}", f"{p1} - {p2} - {p4}", f"{p1} - {p3} - {p2}",
        f"{p1} - {p3} - {p4}", f"{p2} - {p1} - {p3}", f"{p2} - {p1} - {p4}",
        f"{p1} - {p4} - {p2}", f"{p1} - {p4} - {p3}", f"{p1} - {p2} - {p5}",
        f"{p1} - {p3} - {p5}", f"{p2} - {p3} - {p1}", f"{p1} - {p5} - {p2}"
    ]
    
    return {
        "単勝": [f"{p1}"],
        "2連単": nitantan_candidates[:max_2t_points],
        "3连単": santantan_candidates[:max_3t_points]
    }

# --- UI画面 ---
st.set_page_config(page_title="バトルバンク君 - 競輪AI予想", page_icon="🚴‍♂️")
st.title("🤖 バトルバンク君")
st.markdown("出走表の画像をアップロードするとAIがデータを自動で読み取ります！")

col_s1, col_s2 = st.columns(2)
with col_s1:
    max_2t_points = st.slider("2連単の点数", 2, 6, 4)
with col_s2:
    max_3t_points = st.slider("3連単の点数", 3, 12, 6)

uploaded_file = st.file_uploader("出走表をアップロード", type=["png", "jpg", "jpeg"])

if uploaded_file is not None:
    image = Image.open(uploaded_file)
    st.image(image, caption="解析中...", use_column_width=True)
    
    with st.spinner("バトルバンク君が画像を読み取っています..."):
        try:
            extracted_data = extract_data_from_image(image)
            
            for p in extracted_data:
                p["AIスコア"] = calculate_brain_score(p)
                
            bets = generate_bets(extracted_data, max_2t_points, max_3t_points)
            
            st.success("解析完了！")
            
            st.markdown("### 🎯 バトルバンク君の買い目")
            
            st.markdown("#### 🥇 【単勝】")
            for b in bets["単勝"]:
                st.code(b)
                
            st.markdown(f"#### 🥈 【2連単 ({len(bets['2連単'])}点)】")
            for b in bets["2連単"]:
                st.code(b)
                
            st.markdown(f"#### 🥉 【3連単 ({len(bets['3連単'])}点)】")
            for b in bets["3連単"]:
                st.code(b)
                
            with st.expander("🔍 読み取った詳細データを見る"):
                st.json(extracted_data)
                
            st.markdown("---")
            st.subheader("📝 結果を入力して学習")
            with st.form("learning_form"):
                actual_result = st.text_input("実際の着順（例: 1-2-3）")
                if st.form_submit_button("学習させる") and actual_result:
                    save_history({"予測": bets, "結果": actual_result})
                    st.success("学習完了！")
                    
        except Exception as e:
            st.error(f"エラーが発生しました: {e}")
