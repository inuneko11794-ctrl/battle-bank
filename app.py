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
    model = genai.GenerativeModel('gemini-flash-latest')
    
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
        [3, 1, 7],
        [4, 2, 5, 6]
      ]
    }
    基本印がない場合は "" にしてください。選手名が読み取れない場合や塗りつぶされている場合は "" (空白) にしてください。
    並び予想は、画像の下部にある矢印（←）の並び通りに、車番の数字の配列の配列として作ってください。
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
        for i in range(1, len(line)):
            current_car = line[i]
            prev_car = line[i-1]
            
            if current_car in player_dict and prev_car in player_dict:
                curr_p = player_dict[current_car]
                prev_p = player_dict[prev_car]
                
                # 自分自身が無印（""）の場合のみ、前の選手の印を見て「化ける」
                if curr_p.get("基本印", "") == "":
                    prev_mark = prev_p.get("基本印", "")
                    if prev_mark == "◎":
                        curr_p["基本印"] = "⑳"
                    elif prev_mark == "◯":
                        curr_p["基本印"] = "●"
                    elif prev_mark == "△":
                        curr_p["基本印"] = "▲"
                    elif prev_mark in ["✕", "×"]:
                        curr_p["基本印"] = "✖"
                    else:
                        curr_p["基本印"] = "☆★"
    return list(player_dict.values())

def calculate_brain_score(player):
    score = player.get("競走得点", 0.0)
    
    # ★ここに新ルールの印を追加！（今はマスターの指示通り全て0点にしています）
    mark_scores = {
        "◎": 10, "◯": 8, "△": 6, "✕": 4, "×": 4,
        "⑳": 0, "●": 0, "▲": 0, "✖": 0, "☆★": 0 
    }
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
    
    nitantan_candidates = [
        f"{p1} - {p2}", f"{p1} - {p3}", f"{p2} - {p1}",
        f"{p1} - {p4}", f"{p2} - {p3}", f"{p3} - {p1}", f"{p1} - {p5}"
    ]
    
    santantan_candidates = [
        f"{p1} - {p2} - {p3}", f"{p1} - {p2} - {p4}", f"{p1} - {p3} - {p2}",
        f"{p1} - {p3} - {p4}", f"{p2} - {p1} - {p3}", f"{p2} - {p1} - {p4}",
        f"{p1} - {p4} - {p2}", f"{p1} - {p4} - {p3}", f"{p1} - {p2} - {p5}",
        f"{p1} - {p3} - {p5}", f"{p2} - {p3} - {p1}", f"{p1} - {p5} - {p2}"
    ]
    
    return {
        "単勝": [f"{p1}"],
        "2連単": nitantan_candidates[:max_2t_points],
        "3連単": santantan_candidates[:max_3t_points]
    }

# --- UI画面 ---
st.set_page_config(page_title="バトルバンク君 - 競輪AI予想", page_icon="🚴‍♂️")
st.title("🤖 バトルバンク君")
st.markdown("新機能：画像の解析をストックして、後からまとめて結果を学習できます！")

tab1, tab2 = st.tabs(["🎯 解析と予想", "📚 結果の学習（ストック）"])

with tab1:
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        max_2t_points = st.slider("2連単の点数", 2, 6, 4)
    with col_s2:
        max_3t_points = st.slider("3連単の点数", 3, 12, 6)

    uploaded_file = st.file_uploader("出走表をアップロード", type=["png", "jpg", "jpeg"])

    if uploaded_file is not None:
        image = Image.open(uploaded_file)
        st.image(image, caption="解析中...", use_column_width=True)
        
        with st.spinner("バトルバンク君が新ルールで画像を読み取っています..."):
            try:
                raw_data = extract_data_from_image(image)
                # マスターの新ルールを適用！
                players = apply_custom_marks(raw_data)
                
                for p in players:
                    p["AIスコア"] = calculate_brain_score(p)
                    
                bets = generate_bets(players, max_2t_points, max_3t_points)
                
                # 自動的に「結果待ち（ストック）」に保存する
                now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                save_pending_race({
                    "id": str(datetime.datetime.now().timestamp()),
                    "date": now_str,
                    "データ": players,
                    "予測": bets
                })
                
                st.success("解析完了！結果待ちリストにストックしました。")
                
                st.markdown("### 🎯 バトルバンク君の買い目")
                st.markdown("#### 🥇 【単勝】")
                for b in bets["単勝"]: st.code(b)
                st.markdown(f"#### 🥈 【2連単 ({len(bets['2連単'])}点)】")
                for b in bets["2連単"]: st.code(b)
                st.markdown(f"#### 🥉 【3連単 ({len(bets['3連単'])}点)】")
                for b in bets["3連単"]: st.code(b)
                    
                with st.expander("🔍 読み取った詳細データを見る（新ルールの印も確認できます）"):
                    st.json(players)
                        
            except Exception as e:
                st.error(f"エラーが発生しました: {e}")

with tab2:
    st.subheader("📝 結果待ちのレース一覧")
    st.write("予想したレースがここに溜まります。レースが終わったら着順を入力して学習させましょう！")
    
    pending_races = load_json(PENDING_FILE)
    
    if not pending_races:
        st.info("現在ストックされているレースはありません。")
    else:
        for i, race in enumerate(pending_races):
            with st.expander(f"レース日時: {race['date']}"):
                st.write("**【AIの予測】**")
                st.write(f"2連単: {', '.join(race['予測']['2連単'])}")
                st.write(f"3連単: {', '.join(race['予測']['3連単'])}")
                
                actual_result = st.text_input("実際の着順を入力（例: 1-2-3）", key=f"res_{race['id']}")
                
                if st.button("この結果を学習させる", key=f"btn_{race['id']}"):
                    if actual_result:
                        # 学習履歴に追加
                        history = load_json(DATA_FILE)
                        history.append({
                            "date": race['date'],
                            "データ": race['データ'],
                            "予測": race['予測'],
                            "実際の着順": actual_result
                        })
                        save_json(DATA_FILE, history)
                        
                        # ストックから削除
                        pending_races.pop(i)
                        save_json(PENDING_FILE, pending_races)
                        
                        st.success("学習データを保存しました！")
                        st.rerun() # 画面をリフレッシュ
                    else:
                        st.warning("着順を入力してください！")
