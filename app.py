import streamlit as st
import json
import os
import datetime
import google.generativeai as genai
from PIL import Image

# --- AIの目の準備 ---
if "GEMINI_API_KEY" in st.secrets:
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    except:
        pass

DATA_FILE = "learning_history.json"
PENDING_FILE = "pending_races.json"
SCORE_FILE = "mark_scores.json"

# 初期状態の印スコア
DEFAULT_MARK_SCORES = {
    "◎": 10.0, "◯": 8.0, "△": 6.0, "✕": 4.0, "×": 4.0,
    "⑳": 0.0, "●": 0.0, "▲": 0.0, "✖": 0.0, "☆": 0.0, "T": 0.0, "": 0.0
}

# --- データ保存・読み込み機能 ---
def load_json(file_path, default_val):
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default_val

def save_json(file_path, data):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def save_pending_race(race_data):
    pending = load_json(PENDING_FILE, [])
    pending.append(race_data)
    save_json(PENDING_FILE, pending)

def update_mark_scores_and_get_line_result(actual_result_str, race_players):
    """実際の着順から印のスコアを増減させ、決着ラインの文字列を生成する"""
    try:
        places = [int(x.strip()) for x in actual_result_str.replace("ー", "-").split("-")]
    except:
        return "入力エラー"

    scores = load_json(SCORE_FILE, DEFAULT_MARK_SCORES)
    rewards = {0: 1.0, 1: 0.5, 2: 0.2} # 1着:+1.0, 2着:+0.5, 3着:+0.2
    line_result = []

    for i, car_num in enumerate(places):
        for p in race_players:
            if p["車番"] == car_num:
                # ライン結果の記録（単騎の場合は L番号 なし）
                l_num = p.get("ライン情報", {}).get("ライン番号")
                pos = p.get("ライン情報", {}).get("ポジション", "")
                if l_num is not None:
                    line_result.append(f"L{l_num}({pos})")
                else:
                    line_result.append("単騎")
                
                # 印スコアの加算
                mark = p.get("基本印", "")
                if mark in scores:
                    scores[mark] += rewards.get(i, 0.0)

    # 着外の印からは少しだけ減点(-0.1)してバランスを取る
    for p in race_players:
        if p["車番"] not in places:
            mark = p.get("基本印", "")
            if mark in scores:
                scores[mark] -= 0.1
                
    # 小数点第2位までに丸める
    for k in scores:
        scores[k] = round(scores[k], 2)
        
    save_json(SCORE_FILE, scores)
    return " - ".join(line_result)

def extract_data_from_image(image):
    model = genai.GenerativeModel('gemini-flash-latest')
    prompt = """
    This is a Keirin (cycling) race card. Extract player data and line predictions into JSON format.
    Output ONLY valid JSON matching this exact schema:
    {
      "選手": [
        {
          "車番": 1, "選手名": "名前", "競走得点": 100.50, "基本印": "◎", "ライン役割": "先頭",
          "H": 5, "B": 4, "逃": 2, "捲": 1, "差": 0, "マ": 0
        }
      ],
      "並び予想": [ [1, 7, 2], [5], [4, 3, 6] ]
    }
    """
    response = model.generate_content([prompt, image])
    json_text = response.text.replace('```json', '').replace('```', '').strip()
    return json.loads(json_text)

def apply_custom_marks(data):
    """単騎はライン番号に含めず分離してマスターのカスタム印を適用"""
    players = data.get("選手", [])
    lines = data.get("並び予想", [])
    
    player_dict = {p["車番"]: p for p in players}
    original_marks = {p["車番"]: p.get("基本印", "") for p in players}
    used_special_marks = set()
    
    # デフォルトは単騎設定
    for p in players:
        p["ライン情報"] = {"ライン番号": None, "ポジション": "単騎"}

    real_line_count = 0
    for line in lines:
        if len(line) >= 2:
            real_line_count += 1
            for i in range(len(line)):
                current_car = line[i]
                if current_car not in player_dict:
                    continue
                    
                curr_p = player_dict[current_car]
                pos_name = "先頭" if i == 0 else ("番手" if i == 1 else f"{i+1}番手")
                curr_p["ライン情報"] = {"ライン番号": real_line_count, "ポジション": pos_name}
                
                if original_marks[current_car] == "":
                    neighbor_marks = []
                    if i > 0:
                        prev_car = line[i-1]
                        if prev_car in original_marks:
                            neighbor_marks.append(original_marks[prev_car])
                    if i < len(line) - 1:
                        next_car = line[i+1]
                        if next_car in original_marks:
                            neighbor_marks.append(original_marks[next_car])
                            
                    if "◎" in neighbor_marks and "⑳" not in used_special_marks:
                        curr_p["基本印"] = "⑳"
                        used_special_marks.add("⑳")
                    elif "◯" in neighbor_marks and "●" not in used_special_marks:
                        curr_p["基本印"] = "●"
                        used_special_marks.add("●")
                    elif "△" in neighbor_marks and "▲" not in used_special_marks:
                        curr_p["基本印"] = "▲"
                        used_special_marks.add("▲")
                    elif ("✕" in neighbor_marks or "×" in neighbor_marks) and "✖" not in used_special_marks:
                        curr_p["基本印"] = "✖"
                        used_special_marks.add("✖")
                    else:
                        curr_p["基本印"] = "☆"
        elif len(line) == 1:
            current_car = line[0]
            if current_car in player_dict:
                curr_p = player_dict[current_car]
                curr_p["ライン情報"] = {"ライン番号": None, "ポジション": "単騎"}
                if original_marks[current_car] == "":
                    curr_p["基本印"] = "T"

    for curr_p in player_dict.values():
        if curr_p.get("基本印", "") == "":
            if curr_p["ライン情報"]["ポジション"] == "単騎":
                curr_p["基本印"] = "T"
            else:
                curr_p["基本印"] = "☆"
            
    return list(player_dict.values()), lines

def calculate_brain_score(player, current_scores):
    score = player.get("競走得点", 0.0)
    mark = player.get("基本印", "")
    
    score += current_scores.get(mark, 0.0)
    score += (player.get("H", 0) + player.get("B", 0)) * 0.5 
    
    role = player.get("ライン情報", {}).get("ポジション", "不明")
    if role == "先頭" or role == "単騎":
        score += (player.get("逃", 0) + player.get("捲", 0)) * 0.8
    else:
        score += (player.get("差", 0) + player.get("マ", 0)) * 0.8
    return round(score, 2)

def get_p_str(car, players):
    """車番にライン情報を付けて表示する（例: 1(L1), 5(単) ）"""
    for p in players:
        if p["車番"] == car:
            l_num = p.get("ライン情報", {}).get("ライン番号")
            if l_num is not None:
                return f"{car}(L{l_num})"
            else:
                return f"{car}(単)"
    return str(car)

def generate_bets(players, max_2t_points, max_3t_points):
    sorted_players = sorted(players, key=lambda x: x["AIスコア"], reverse=True)
    if len(sorted_players) < 3:
        return {"単勝": [], "2連単": [], "3連単": []}
    
    p1, p2, p3 = sorted_players[0]["車番"], sorted_players[1]["車番"], sorted_players[2]["車番"]
    p4 = sorted_players[3]["車番"] if len(sorted_players) > 3 else p3
    p5 = sorted_players[4]["車番"] if len(sorted_players) > 4 else p4
    p6 = sorted_players[5]["車番"] if len(sorted_players) > 5 else p5
    
    nitantan = [
        f"{get_p_str(p1, players)} - {get_p_str(p2, players)}", f"{get_p_str(p1, players)} - {get_p_str(p3, players)}",
        f"{get_p_str(p2, players)} - {get_p_str(p1, players)}", f"{get_p_str(p1, players)} - {get_p_str(p4, players)}",
        f"{get_p_str(p2, players)} - {get_p_str(p3, players)}", f"{get_p_str(p3, players)} - {get_p_str(p1, players)}"
    ]
    
    santantan = [
        f"{get_p_str(p1, players)} - {get_p_str(p2, players)} - {get_p_str(p3, players)}", 
        f"{get_p_str(p1, players)} - {get_p_str(p2, players)} - {get_p_str(p4, players)}",
        f"{get_p_str(p1, players)} - {get_p_str(p3, players)} - {get_p_str(p2, players)}",
        f"{get_p_str(p1, players)} - {get_p_str(p3, players)} - {get_p_str(p4, players)}",
        f"{get_p_str(p2, players)} - {get_p_str(p1, players)} - {get_p_str(p3, players)}",
        f"{get_p_str(p2, players)} - {get_p_str(p1, players)} - {get_p_str(p4, players)}",
        f"{get_p_str(p1, players)} - {get_p_str(p4, players)} - {get_p_str(p2, players)}",
        f"{get_p_str(p1, players)} - {get_p_str(p4, players)} - {get_p_str(p3, players)}",
        f"{get_p_str(p1, players)} - {get_p_str(p2, players)} - {get_p_str(p5, players)}",
        f"{get_p_str(p1, players)} - {get_p_str(p3, players)} - {get_p_str(p5, players)}",
        f"{get_p_str(p2, players)} - {get_p_str(p3, players)} - {get_p_str(p1, players)}",
        f"{get_p_str(p1, players)} - {get_p_str(p5, players)} - {get_p_str(p2, players)}"
    ]
    
    return {
        "単勝": [f"{get_p_str(p1, players)}"],
        "2連単": nitantan[:max_2t_points],
        "3連単": santantan[:max_3t_points]
    }

# --- UI画面 ---
st.set_page_config(page_title="バトルバンク君 - 競輪AI予想", page_icon="🚴‍♂️")
st.title("🤖 バトルバンク君")
st.markdown("進化版：学習で「印スコア」が自動成長＆単騎を正しく分離表示！")

tab1, tab2, tab3 = st.tabs(["🎯 解析と予想", "📚 結果の学習（ストック）", "📊 収支・データ分析"])

with tab1:
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        max_2t_points = st.slider("2連単の点数", 2, 6, 4)
    with col_s2:
        max_3t_points = st.slider("3連単の点数", 6, 25, 12, step=1)

    input_mode = st.radio("入力方法を選んでください", ["📷 画像からAI自動読み取り", "✍️ 手動でデータを入力（API消費ゼロ）"])

    if input_mode == "📷 画像からAI自動読み取り":
        uploaded_file = st.file_uploader("出走表をアップロード", type=["png", "jpg", "jpeg"])
        if uploaded_file is not None:
            image = Image.open(uploaded_file)
            st.image(image, caption="解析中...", use_column_width=True)
            with st.spinner("バトルバンク君が画像を解析しています..."):
                try:
                    raw_data = extract_data_from_image(image)
                    players, lines = apply_custom_marks(raw_data)
                    
                    current_scores = load_json(SCORE_FILE, DEFAULT_MARK_SCORES)
                    for p in players:
                        p["AIスコア"] = calculate_brain_score(p, current_scores)
                        
                    bets = generate_bets(players, max_2t_points, max_3t_points)
                    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    save_pending_race({
                        "id": str(datetime.datetime.now().timestamp()),
                        "date": now_str, "データ": players, "並び予想": lines, "予測": bets
                    })
                    st.success("解析完了！結果待ちリストにストックしました。")
                    
                    st.markdown("### 🎯 バトルバンク君の買い目 (L1=ライン1, 単=単騎)")
                    st.markdown("#### 🥇 【単勝】")
                    for b in bets["単勝"]: st.code(b)
                    st.markdown(f"#### 🥈 【2連単 ({len(bets['2連単'])}点)】")
                    for b in bets["2連単"]: st.code(b)
                    st.markdown(f"#### 🥉 【3連単 ({len(bets['3連単'])}点)】")
                    for b in bets["3連単"]: st.code(b)
                except Exception as e:
                    st.error(f"エラーが発生しました: {e}")

    else:
        st.subheader("✍️ 手動データ入力モード")
        num_players = st.number_input("出走人数（7車 or 9車）", min_value=7, max_value=9, value=7)
        manual_players = []
        for c in range(1, int(num_players) + 1):
            with st.expander(f"車番 {c} の選手"):
                m_name = st.text_input(f"選手名 (車番{c})", value=f"選手{c}", key=f"m_name_{c}")
                m_score = st.number_input(f"競走得点 (車番{c})", min_value=70.0, max_value=120.0, value=90.0, step=0.01, key=f"m_score_{c}")
                m_mark = st.selectbox(f"基本印 (車番{c})", ["", "◎", "◯", "△", "✕", "⑳", "●", "▲", "✖", "☆", "T"], key=f"m_mark_{c}")
                col_hb1, col_hb2 = st.columns(2)
                with col_hb1:
                    m_h = st.number_input(f"H回数", 0, 50, 0, key=f"m_h_{c}")
                    m_b = st.number_input(f"B回数", 0, 50, 0, key=f"m_b_{c}")
                with col_hb2:
                    m_run = st.number_input(f"逃", 0, 50, 0, key=f"m_run_{c}")
                    m_roll = st.number_input(f"捲", 0, 50, 0, key=f"m_roll_{c}")
                    m_diff = st.number_input(f"差", 0, 50, 0, key=f"m_diff_{c}")
                    m_ma = st.number_input(f"マ", 0, 50, 0, key=f"m_ma_{c}")
                manual_players.append({
                    "車番": c, "選手名": m_name, "競走得点": m_score, "基本印": m_mark,
                    "H": m_h, "B": m_b, "逃": m_run, "捲": m_roll, "差": m_diff, "マ": m_ma
                })
        
        st.markdown("#### 並び予想（ライン）の入力")
        st.caption("※2車以上のラインのみ入力してください。ラインに入力しなかった車番は自動的に「単騎」扱いになります。")
        line_str_1 = st.text_input("ライン1（例: 1,7,2）", value="1, 7, 2")
        line_str_2 = st.text_input("ライン2（例: 4,3,6）", value="4, 3, 6")
        line_str_3 = st.text_input("ライン3（任意）", value="")
        line_str_4 = st.text_input("ライン4（任意）", value="")
        line_str_5 = st.text_input("ライン5（任意）", value="")
        
        if st.button("✍️ 手動データを解析・ストックする"):
            try:
                lines = []
                for l_str in [line_str_1, line_str_2, line_str_3, line_str_4, line_str_5]:
                    if l_str.strip():
                        cars = [int(x.strip()) for x in l_str.split(",") if x.strip().isdigit()]
                        if cars: lines.append(cars)
                            
                raw_data = {"選手": manual_players, "並び予想": lines}
                players, lines = apply_custom_marks(raw_data)
                
                current_scores = load_json(SCORE_FILE, DEFAULT_MARK_SCORES)
                for p in players:
                    p["AIスコア"] = calculate_brain_score(p, current_scores)
                    
                bets = generate_bets(players, max_2t_points, max_3t_points)
                now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                save_pending_race({
                    "id": str(datetime.datetime.now().timestamp()),
                    "date": now_str, "データ": players, "並び予想": lines, "予測": bets
                })
                st.success("手動データの解析完了！ストックしました。")
                
                st.markdown("### 🎯 バトルバンク君の買い目 (L1=ライン1, 単=単騎)")
                for b in bets["単勝"]: st.code(b)
                for b in bets["2連単"]: st.code(b)
                for b in bets["3連単"]: st.code(b)
            except Exception as e:
                st.error(f"入力エラー: {e}")

with tab2:
    st.subheader("📝 結果待ちのレース一覧")
    pending_races = load_json(PENDING_FILE, [])
    
    if not pending_races:
        st.info("現在ストックされているレースはありません。")
    else:
        for i, race in enumerate(pending_races):
            with st.expander(f"📅 {race['date']}"):
                st.write("**【AIの予測】**")
                st.write(f"2連単: {', '.join(race['予測']['2連単'])}")
                st.write(f"3連単: {', '.join(race['予測']['3連単'])}")
                
                actual_result = st.text_input("実際の着順（例: 1-2-3）", key=f"res_{race['id']}")
                col_i1, col_i2 = st.columns(2)
                with col_i1:
                    investment = st.number_input("投資金額 (円)", min_value=0, value=1000, step=100, key=f"inv_{race['id']}")
                with col_i2:
                    payout = st.number_input("払戻金額 (円)", min_value=0, value=0, step=100, key=f"pay_{race['id']}")
                memo = st.text_area("レースメモ", key=f"memo_{race['id']}")
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("学習させる（印スコア自動更新）", key=f"btn_{race['id']}"):
                        if actual_result:
                            line_str = update_mark_scores_and_get_line_result(actual_result, race['データ'])
                            
                            history = load_json(DATA_FILE, [])
                            history.append({
                                "date": race['date'],
                                "実際の着順": actual_result,
                                "決着ライン": line_str,
                                "投資額": investment, "払戻額": payout, "収支": payout - investment,
                                "メモ": memo
                            })
                            save_json(DATA_FILE, history)
                            
                            pending_races.pop(i)
                            save_json(PENDING_FILE, pending_races)
                            st.success(f"決着ライン【{line_str}】として学習しました！印のスコアも進化しました！")
                            st.rerun()
                        else:
                            st.warning("着順を入力してください！")
                with col_btn2:
                    if st.button("🗑️ 削除", key=f"del_{race['id']}"):
                        pending_races.pop(i)
                        save_json(PENDING_FILE, pending_races)
                        st.rerun()

with tab3:
    st.subheader("🧠 現在の印スコア（AI自己学習済み）")
    current_scores = load_json(SCORE_FILE, DEFAULT_MARK_SCORES)
    st.json(current_scores)
    
    st.markdown("---")
    st.subheader("📊 収支・データ分析")
    history_data = load_json(DATA_FILE, [])
    
    if not history_data:
        st.info("データがありません。")
    else:
        total_inv = sum(h.get("投資額", 0) for h in history_data)
        total_pay = sum(h.get("払戻額", 0) for h in history_data)
        total_profit = total_pay - total_inv
        recovery_rate = (total_pay / total_inv * 100) if total_inv > 0 else 0
        
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("総投資額", f"{total_inv:,} 円")
        col_m2.metric("総払戻額", f"{total_pay:,} 円")
        col_m3.metric("総収支", f"{total_profit:+,} 円")
        col_m4.metric("回収率", f"{recovery_rate:.1f}%")
        
        st.markdown("---")
        st.subheader("📝 過去のレース履歴")
        for h in history_data:
            profit_str = f"{h.get('収支', 0):+,} 円"
            line_result = h.get('決着ライン', '不明')
            with st.expander(f"📅 {h['date']} | 結果: {h.get('実際の着順', '不明')} ({line_result}) | 収支: {profit_str}"):
                st.write(f"**投資**: {h.get('投資額', 0):,}円 / **払戻**: {h.get('払戻額', 0):,}円")
                st.write(f"**決着ライン**: {line_result}")
                if h.get("メモ"): st.write(f"**メモ**: {h.get('メモ')}")
