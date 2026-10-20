import streamlit as st
import json
import os
import datetime
import google.generativeai as genai
from PIL import Image
from collections import Counter

# --- AIの目の準備 ---
if "GEMINI_API_KEY" in st.secrets:
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    except:
        pass

DATA_FILE = "learning_history.json"
PENDING_FILE = "pending_races.json"
SCORE_FILE = "mark_scores.json"
LINE_SCORE_FILE = "line_scores.json"

DEFAULT_MARK_SCORES = {
    "◎": 10.0, "◯": 8.0, "△": 6.0, "✕": 4.0, "×": 4.0,
    "⑳": 0.0, "●": 0.0, "▲": 0.0, "✖": 0.0, "☆": 0.0, "T": 0.0, "": 0.0
}

DEFAULT_LINE_SCORES = {
    "1": 5.0, "2": 3.0, "3": 2.0, "4": 1.0, "5": 0.0
}

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

def get_payout_category(payout):
    """払戻金から配当帯ゾーンを判定"""
    if payout <= 4900:
        return "4,900円以下（堅実）"
    elif 5000 <= payout <= 9900:
        return "5,000円〜9,900円（中配）"
    elif 10000 <= payout <= 49000:
        return "10,000円〜49,000円（万車）"
    else:
        return "50,000円以上（大穴）"

def update_scores_and_get_details(actual_result_str, race_players):
    """着順情報、印、車番、ラインの決着詳細を取得しスコアを更新"""
    try:
        places = [int(x.strip()) for x in actual_result_str.replace("ー", "-").split("-")]
    except:
        return "入力エラー", []

    mark_scores = load_json(SCORE_FILE, DEFAULT_MARK_SCORES)
    line_scores = load_json(LINE_SCORE_FILE, DEFAULT_LINE_SCORES)
    rewards = {0: 1.0, 1: 0.5, 2: 0.2}
    
    line_result = []
    place_details = [] # 着順ごとの詳細情報（車番・印・ライン位置）

    for i, car_num in enumerate(places):
        for p in race_players:
            if p["車番"] == car_num:
                l_num = p.get("ライン情報", {}).get("ライン番号")
                pos = p.get("ライン情報", {}).get("ポジション", "")
                mark = p.get("基本印", "")
                
                line_str = f"L{l_num}({pos})" if l_num is not None else "単騎"
                line_result.append(line_str)
                
                place_details.append({
                    "着順": i + 1,
                    "車番": car_num,
                    "印": mark if mark else "印なし",
                    "ライン情報": line_str
                })
                
                # スコア加算
                if l_num is not None and str(l_num) in line_scores:
                    line_scores[str(l_num)] += rewards.get(i, 0.0)
                if mark in mark_scores:
                    mark_scores[mark] += rewards.get(i, 0.0)

    # 着外の微減
    for p in race_players:
        if p["車番"] not in places:
            mark = p.get("基本印", "")
            if mark in mark_scores: mark_scores[mark] -= 0.1
            l_num = p.get("ライン情報", {}).get("ライン番号")
            if l_num is not None and str(l_num) in line_scores:
                line_scores[str(l_num)] -= 0.1

    for k in mark_scores: mark_scores[k] = round(mark_scores[k], 2)
    for k in line_scores: line_scores[k] = round(line_scores[k], 2)
        
    save_json(SCORE_FILE, mark_scores)
    save_json(LINE_SCORE_FILE, line_scores)
    return " - ".join(line_result), place_details

def extract_data_from_image(image):
    model = genai.GenerativeModel('gemini-flash-latest')
    prompt = """
    This is a Keirin race card. Extract player data and line predictions into JSON format.
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
    players = data.get("選手", [])
    lines = data.get("並び予想", [])
    
    player_dict = {p["車番"]: p for p in players}
    original_marks = {p["車番"]: p.get("基本印", "") for p in players}
    used_special_marks = set()
    
    for p in players:
        p["ライン情報"] = {"ライン番号": None, "ポジション": "単騎"}

    real_line_count = 0
    for line in lines:
        if len(line) >= 2:
            real_line_count += 1
            for i in range(len(line)):
                current_car = line[i]
                if current_car not in player_dict: continue
                curr_p = player_dict[current_car]
                pos_name = "先頭" if i == 0 else ("番手" if i == 1 else f"{i+1}番手")
                curr_p["ライン情報"] = {"ライン番号": real_line_count, "ポジション": pos_name}
                
                if original_marks[current_car] == "":
                    neighbor_marks = []
                    if i > 0 and line[i-1] in original_marks: neighbor_marks.append(original_marks[line[i-1]])
                    if i < len(line) - 1 and line[i+1] in original_marks: neighbor_marks.append(original_marks[line[i+1]])
                            
                    if "◎" in neighbor_marks and "⑳" not in used_special_marks:
                        curr_p["基本印"] = "⑳"; used_special_marks.add("⑳")
                    elif "◯" in neighbor_marks and "●" not in used_special_marks:
                        curr_p["基本印"] = "●"; used_special_marks.add("●")
                    elif "△" in neighbor_marks and "▲" not in used_special_marks:
                        curr_p["基本印"] = "▲"; used_special_marks.add("▲")
                    elif ("✕" in neighbor_marks or "×" in neighbor_marks) and "✖" not in used_special_marks:
                        curr_p["基本印"] = "✖"; used_special_marks.add("✖")
                    else:
                        curr_p["基本印"] = "☆"
        elif len(line) == 1:
            current_car = line[0]
            if current_car in player_dict:
                curr_p = player_dict[current_car]
                curr_p["ライン情報"] = {"ライン番号": None, "ポジション": "単騎"}
                if original_marks[current_car] == "": curr_p["基本印"] = "T"

    for curr_p in player_dict.values():
        if curr_p.get("基本印", "") == "":
            curr_p["基本印"] = "T" if curr_p["ライン情報"]["ポジション"] == "単騎" else "☆"
            
    return list(player_dict.values()), lines

def calculate_brain_score(player, current_mark_scores, current_line_scores):
    score = player.get("競走得点", 0.0)
    mark = player.get("基本印", "")
    score += current_mark_scores.get(mark, 0.0)
    
    l_num = player.get("ライン情報", {}).get("ライン番号")
    if l_num is not None:
        score += current_line_scores.get(str(l_num), 0.0)
    
    score += (player.get("H", 0) + player.get("B", 0)) * 0.5 
    role = player.get("ライン情報", {}).get("ポジション", "不明")
    if role == "先頭" or role == "単騎":
        score += (player.get("逃", 0) + player.get("捲", 0)) * 0.8
    else:
        score += (player.get("差", 0) + player.get("マ", 0)) * 0.8
    return round(score, 2)

def get_p_str(car, players):
    for p in players:
        if p["車番"] == car:
            l_num = p.get("ライン情報", {}).get("ライン番号")
            return f"{car}(L{l_num})" if l_num is not None else f"{car}(単)"
    return str(car)

def generate_bets(players, max_2t_points, max_3t_points):
    sorted_players = sorted(players, key=lambda x: x["AIスコア"], reverse=True)
    if len(sorted_players) < 3: return {"単勝": [], "2連単": [], "3連単": []}
    
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
    return {"単勝": [f"{get_p_str(p1, players)}"], "2連単": nitantan[:max_2t_points], "3連単": santantan[:max_3t_points]}

# --- UI画面 ---
st.set_page_config(page_title="バトルバンク君 - 競輪AI予想", page_icon="🚴‍♂️")
st.title("🤖 バトルバンク君")
st.markdown("超進化版：配当帯ごとの印・車番・ライン傾向のデータ分析に対応！")

tab1, tab2, tab3 = st.tabs(["🎯 解析と予想", "📚 結果の学習（ストック）", "📊 収支・配当帯データ分析"])

with tab1:
    col_s1, col_s2 = st.columns(2)
    with col_s1: max_2t_points = st.slider("2連単の点数", 2, 6, 4)
    with col_s2: max_3t_points = st.slider("3連単の点数", 6, 25, 12, step=1)

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
                    
                    current_mark_scores = load_json(SCORE_FILE, DEFAULT_MARK_SCORES)
                    current_line_scores = load_json(LINE_SCORE_FILE, DEFAULT_LINE_SCORES)
                    for p in players: p["AIスコア"] = calculate_brain_score(p, current_mark_scores, current_line_scores)
                        
                    bets = generate_bets(players, max_2t_points, max_3t_points)
                    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    save_pending_race({"id": str(datetime.datetime.now().timestamp()), "date": now_str, "データ": players, "並び予想": lines, "予測": bets})
                    st.success("解析完了！結果待ちリストにストックしました。")
                    
                    st.markdown("### 🎯 バトルバンク君の買い目")
                    st.markdown("#### 🥇 【単勝】"); st.code(bets["単勝"][0])
                    st.markdown(f"#### 🥈 【2連単 ({len(bets['2連単'])}点)】")
                    for b in bets["2連単"]: st.code(b)
                    st.markdown(f"#### 🥉 【3連単 ({len(bets['3連単'])}点)】")
                    for b in bets["3連単"]: st.code(b)
                except Exception as e: st.error(f"エラーが発生しました: {e}")

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
                manual_players.append({"車番": c, "選手名": m_name, "競走得点": m_score, "基本印": m_mark, "H": m_h, "B": m_b, "逃": m_run, "捲": m_roll, "差": m_diff, "マ": m_ma})
        
        st.markdown("#### 並び予想（ライン）の入力")
        line_str_1 = st.text_input("ライン1 (例: 1,7,2)", value="1, 7, 2")
        line_str_2 = st.text_input("ライン2 (例: 4,3,6)", value="4, 3, 6")
        line_str_3 = st.text_input("ライン3 (任意)", value="")
        line_str_4 = st.text_input("ライン4 (任意)", value="")
        line_str_5 = st.text_input("ライン5 (任意)", value="")
        
        if st.button("✍️ 手動データを解析・ストックする"):
            try:
                lines = []
                for l_str in [line_str_1, line_str_2, line_str_3, line_str_4, line_str_5]:
                    if l_str.strip():
                        cars = [int(x.strip()) for x in l_str.split(",") if x.strip().isdigit()]
                        if cars: lines.append(cars)
                            
                raw_data = {"選手": manual_players, "並び予想": lines}
                players, lines = apply_custom_marks(raw_data)
                
                current_mark_scores = load_json(SCORE_FILE, DEFAULT_MARK_SCORES)
                current_line_scores = load_json(LINE_SCORE_FILE, DEFAULT_LINE_SCORES)
                for p in players: p["AIスコア"] = calculate_brain_score(p, current_mark_scores, current_line_scores)
                    
                bets = generate_bets(players, max_2t_points, max_3t_points)
                now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                save_pending_race({"id": str(datetime.datetime.now().timestamp()), "date": now_str, "データ": players, "並び予想": lines, "予測": bets})
                st.success("手動データの解析完了！ストックしました。")
                
                st.markdown("### 🎯 バトルバンク君の買い目")
                st.code(bets["単勝"][0])
                for b in bets["2連単"]: st.code(b)
                for b in bets["3連単"]: st.code(b)
            except Exception as e: st.error(f"入力エラー: {e}")

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
                with col_i1: investment = st.number_input("投資金額 (円)", min_value=0, value=1000, step=100, key=f"inv_{race['id']}")
                with col_i2: payout = st.number_input("払戻金額 (円)", min_value=0, value=0, step=100, key=f"pay_{race['id']}")
                memo = st.text_area("レースメモ", key=f"memo_{race['id']}")
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("学習させる（配当帯＆スコア自動分類）", key=f"btn_{race['id']}"):
                        if actual_result:
                            line_str, place_details = update_scores_and_get_details(actual_result, race['データ'])
                            category = get_payout_category(payout)
                            
                            history = load_json(DATA_FILE, [])
                            history.append({
                                "date": race['date'],
                                "実際の着順": actual_result,
                                "配当帯ゾーン": category,
                                "決着ライン": line_str,
                                "着順詳細": place_details,
                                "投資額": investment, "払戻額": payout, "収支": payout - investment,
                                "メモ": memo
                            })
                            save_json(DATA_FILE, history)
                            
                            pending_races.pop(i)
                            save_json(PENDING_FILE, pending_races)
                            st.success(f"配当帯【{category}】・決着【{line_str}】として学習しました！")
                            st.rerun()
                        else: st.warning("着順を入力してください！")
                with col_btn2:
                    if st.button("🗑️ 削除", key=f"del_{race['id']}"):
                        pending_races.pop(i)
                        save_json(PENDING_FILE, pending_races)
                        st.rerun()

with tab3:
    st.subheader("📊 配当帯別データ・アナリティクス")
    history_data = load_json(DATA_FILE, [])
    
    if not history_data:
        st.info("まだ学習データがありません。「結果の学習」からレース結果と払戻金を入力してください！")
    else:
        # 配当帯フィルター選択
        zone_options = ["すべて", "4,900円以下（堅実）", "5,000円〜9,900円（中配）", "10,000円〜49,000円（万車）", "50,000円以上（大穴）"]
        selected_zone = st.selectbox("🎯 分析したい配当帯（オッズ）ゾーンを選んでください", zone_options)
        
        filtered_data = history_data if selected_zone == "すべて" else [h for h in history_data if h.get("配当帯ゾーン") == selected_zone]
        
        st.markdown(f"### 📈 【{selected_zone}】の傾向と学習データ ({len(filtered_data)}件)")
        
        if not filtered_data:
            st.warning("この配当帯のデータはまだありません。")
        else:
            # 配当帯ごとの統計処理
            all_marks = []
            all_cars = []
            all_lines = []
            
            for h in filtered_data:
                for detail in h.get("着順詳細", []):
                    all_marks.append(detail.get("印", "印なし"))
                    all_cars.append(f"{detail.get('車番')}番車")
                    all_lines.append(detail.get("ライン情報", "不明"))
            
            mark_counts = Counter(all_marks).most_common(5)
            car_counts = Counter(all_cars).most_common(5)
            line_counts = Counter(all_lines).most_common(5)
            
            col_a1, col_a2, col_a3 = st.columns(3)
            
            with col_a1:
                st.markdown("#### 🎯 来やすい【印】")
                for mark, cnt in mark_counts:
                    st.write(f"- **{mark}**: {cnt}回")
                    
            with col_a2:
                st.markdown("#### 🚲 来やすい【車番】")
                for car, cnt in car_counts:
                    st.write(f"- **{car}**: {cnt}回")
                    
            with col_a3:
                st.markdown("#### 🚩 来やすい【ライン位置】")
                for line, cnt in line_counts:
                    st.write(f"- **{line}**: {cnt}回")

        st.markdown("---")
        st.subheader("🧠 現在の学習済みAIスコア")
        col_sc1, col_sc2 = st.columns(2)
        with col_sc1:
            st.markdown("#### 1. 印のスコア")
            st.json(load_json(SCORE_FILE, DEFAULT_MARK_SCORES))
        with col_sc2:
            st.markdown("#### 2. ライン番号のスコア (1〜5)")
            st.json(load_json(LINE_SCORE_FILE, DEFAULT_LINE_SCORES))
            
        st.markdown("---")
        st.subheader("📝 過去のレース履歴")
        for idx, h in enumerate(history_data):
            profit_str = f"{h.get('収支', 0):+,} 円"
            zone = h.get('配当帯ゾーン', '未分類')
            line_result = h.get('決着ライン', '不明')
            with st.expan
