import streamlit as st
import json
import os

# 学習データ（的中履歴やフィードバック）を保存するファイル名
DATA_FILE = "learning_history.json"

def load_history():
    """保存された学習データを読み込む"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_history(new_data):
    """新しい結果を学習データとして追記・保存する"""
    history = load_history()
    history.append(new_data)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=4)

# ==========================================
# 1. バトルバンク君（脳レーシングAI） コアロジック
# ==========================================
def calculate_brain_score(player):
    """選手のデータからバトルバンクAIスコアを算出"""
    score = player.get("競走得点", 0.0)
    
    # 基本印スコア
    mark_scores = {"◎": 10, "◯": 8, "△": 6, "✕": 4}
    mark = player.get("基本印", "")
    score += mark_scores.get(mark, 0)
    
    # H/Bボーナス
    hb_total = player.get("H", 0) + player.get("B", 0)
    score += hb_total * 0.5 
    
    # 決まり手（逃捲差マ）ボーナス
    role = player.get("ライン役割", "不明")
    if role == "先頭":
        score += (player.get("逃", 0) + player.get("捲", 0)) * 0.8
    else:
        score += (player.get("差", 0) + player.get("マ", 0)) * 0.8
        
    return round(score, 2)

def generate_bets(players, max_points):
    """指定された点数に合わせて買い目を生成"""
    sorted_players = sorted(players, key=lambda x: x["AIスコア"], reverse=True)
    
    if len(sorted_players) < 3:
        return {"単勝": [], "2連単": [], "3連単": []}
    
    p1 = sorted_players[0]["車番"]
    p2 = sorted_players[1]["車番"]
    p3 = sorted_players[2]["車番"]
    p4 = sorted_players[3]["車番"] if len(sorted_players) > 3 else p3
    
    # 単勝（1点）
    tansho = [f"{p1}"]
    
    # 2連単（上位候補の折り返しなど）
    nitantan = [
        f"{p1} - {p2}", 
        f"{p1} - {p3}", 
        f"{p2} - {p1}"
    ]
    
    # 3連単（指定点数に合わせてスライス）
    santantan = [
        f"{p1} - {p2} - {p3}",
        f"{p1} - {p2} - {p4}",
        f"{p1} - {p3} - {p2}",
        f"{p1} - {p3} - {p4}",
        f"{p2} - {p1} - {p3}",
        f"{p2} - {p1} - {p4}",
        f"{p1} - {p4} - {p2}",
        f"{p1} - {p4} - {p3}",
    ]
    santantan = santantan[:max_points]
    
    return {
        "単勝": tansho,
        "2連単": nitantan,
        "3連単": santantan
    }

# ==========================================
# 2. バトルバンク君 UI設計
# ==========================================
st.set_page_config(page_title="バトルバンク君 - 競輪AI予想システム", page_icon="🚴‍♂️")
st.title("🤖 バトルバンク君")
st.markdown("出走表の画像をアップロードし、点数を指定して買い目を自動生成。レース結果を入力してバトルバンク君を賢く育てましょう！")

# サイドバー：学習データの管理
st.sidebar.header("📊 バトルバンク君の学習状況")
history = load_history()
st.sidebar.write(f"蓄積された学習データ: **{len(history)} 件**")
if history:
    if st.sidebar.button("学習データをリセット"):
        if os.path.exists(DATA_FILE):
            os.remove(DATA_FILE)
            st.sidebar.success("学習データをクリアしました！")
            st.rerun()

# メイン画面：画像アップロード
uploaded_file = st.file_uploader("出走表の画像をアップロード (PNG/JPG)", type=["png", "jpg", "jpeg"])

# 点数指定のスライダー
max_3t_points = st.slider("3連単の最大買い目点数を指定", min_value=3, max_value=12, value=6)

if uploaded_file is not None:
    st.image(uploaded_file, caption="解析中の出走表", use_column_width=True)
    
    # ダミー抽出データ（※本番ではここにOCR/Gemini APIの抽出結果が入ります）
    extracted_data = [
        {"車番": 1, "選手名": "選手A", "競走得点": 105.0, "基本印": "◎", "ライン役割": "先頭", "H": 8, "B": 10, "逃": 5, "捲": 3, "差": 0, "マ": 0},
        {"車番": 2, "選手名": "選手B", "競走得点": 102.0, "基本印": "◯", "ライン役割": "番手", "H": 0, "B": 0, "逃": 0, "捲": 0, "差": 6, "マ": 3},
        {"車番": 3, "選手名": "選手C", "競走得点": 98.0,  "基本印": "",  "ライン役割": "3番手", "H": 0, "B": 0, "逃": 0, "捲": 0, "差": 4, "マ": 2},
        {"車番": 4, "選手名": "選手D", "競走得点": 100.0, "基本印": "△", "ライン役割": "先頭", "H": 4, "B": 3, "逃": 2, "捲": 4, "差": 1, "マ": 0},
    ]
    
    # AIスコア計算
    for p in extracted_data:
        p["AIスコア"] = calculate_brain_score(p)
        
    # 買い目生成
    bets = generate_bets(extracted_data, max_3t_points)
    
    st.markdown("---")
    st.subheader("🎯 バトルバンク君のおすすめ買い目")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**【単勝】**")
        for b in bets["単勝"]:
            st.code(b)
    with col2:
        st.markdown("**【2連単】**")
        for b in bets["2連単"]:
            st.code(b)
    with col3:
        st.markdown(f"**【3連単 (上位{max_3t_points}点)】**")
        for b in bets["3連単"]:
            st.code(b)
            
    st.markdown("---")
    st.subheader("📝 レース結果の入力 ＆ 学習")
    with st.form("learning_form"):
        actual_result = st.text_input("実際の着順を入力してください（例: 1-2-3）", placeholder="1-2-3")
        submit_btn = st.form_submit_button("結果を保存してバトルバンク君に学習させる")
        
        if submit_btn and actual_result:
            feedback_data = {
                "予測買い目": bets,
                "実際の着順": actual_result
            }
            save_history(feedback_data)
            st.success(f"結果「{actual_result}」を保存しました！バトルバンク君がデータを学習しました。")
