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
    if payout <= 4900:
        return "4,900円以下（堅実）"
    elif 5000 <= payout <= 9900:
        return "5,000円〜9,900円（中配）"
    elif 10000 <= payout <= 49000:
        return "10,000円〜49,000円（万車）"
    else:
        return "50,000円以上（大穴）"

def get_race_pattern(lines):
    real_lines = [l for l in lines if len(l) >= 2]
    cnt = len(real_lines)
    if cnt == 2: return "2分戦"
    elif cnt == 3: return "3分戦"
    elif cnt >= 4: return "細切れ戦"
    else: return "先行一車/その他"

def update_scores_and_get_details(actual_result_str, race_players, lines):
    try:
        places = [int(x.strip()) for x in actual_result_str.replace("ー", "-").split("-")]
    except:
        return "入力エラー", [], "不明"

    mark_scores = load_json(SCORE_FILE, DEFAULT_MARK_SCORES)
    line_scores = load_json(LINE_SCORE_FILE, DEFAULT_LINE_SCORES)
    rewards = {0: 1.0, 1: 0.5, 2: 0.2}
    
    sorted_p = sorted(race_players, key=lambda x: x.get("AIスコア", 0), reverse=True)
    rank_map = {p["車番"]: idx + 1 for idx, p in enumerate(sorted_p)}
    
    line_result = []
    place_details = []

    for i, car_num in enumerate(places):
        for p in race_players:
            if p["車番"] == car_num:
                l_num = p.get("ライン情報", {}).get("ライン番号")
                pos = p.get("ライン情報", {}).get("ポジション", "")
                mark = p.get("基本印", "")
                leg = p.get("脚質", "不明")
                
                line_str = f"L{l_num}({pos})" if l_num is not None else "単騎"
                line_result.append(line_str)
                
                place_details.append({
                    "着順": i + 1,
                    "車番": car_num,
                    "印": mark if mark else "印なし",
                    "ライン情報": line_str,
                    "脚質_ポジション": f"{leg}・{pos}",
                    "AI順位": rank_map.get(car_num, 99)
                })
                
                if l_num is not None and str(l_num) in line_scores:
                    line_scores[str(l_num)] += rewards.get(i, 0.0)
                if mark in mark_scores:
                    mark_scores[mark] += rewards.get(i, 0.0)

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
    
    pattern = get_race_pattern(lines)
    return " - ".join(line_result), place_details, pattern

def extract_data_from_image(image):
    model = genai.GenerativeModel('gemini-flash-latest')
    prompt = """
    This is a Keirin race card. Extract player data and line predictions into JSON format.
    Output ONLY valid JSON matching this exact schema:
    {
      "選手": [
        {
          "車番": 1, "選手名": "名前", "競走得点": 100.50, "基本印": "◎", "ライン役割": "先頭", "脚質": "逃",
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
# --- ここから Part 2 ---

st.set_page_config(page_title="バトルバンク君 - 競輪AI予想", page_icon="🚴‍♂️")
st.title("🤖 バトルバンク君")
st.markdown("超進化版：期間絞り込み＆AIスコア成長度メーター機能対応！")

tab1, tab2, tab3 = st.tabs(["🎯 解析と予想", "📚 結果の学習（ストック）", "📊 期間・配当＆展開データ分析"])

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
                m_leg = st.selectbox(f"脚質 (車番{c})", ["逃", "両", "追"], key=f"m_leg_{c}")
                col_hb1, col_hb2 = st.columns(2)
                with col_hb1:
                    m_h = st.number_input(f"H回数", 0, 50, 0, key=f"m_h_{c}")
                    m_b = st.number_input(f"B回数", 0, 50, 0, key=f"m_b_{c}")
                with col_hb2:
                    m_run = st.number_input(f"逃", 0, 50, 0, key=f"m_run_{c}")
                    m_roll = st.number_input(f"捲", 0, 50, 0, key=f"m_roll_{c}")
                    m_diff = st.number_input(f"差", 0, 50, 0, key=f"m_diff_{c}")
                    m_ma = st.number_input(f"マ", 0, 50, 0, key=f"m_ma_{c}")
                manual_players.append({"車番": c, "選手名": m_name, "競走得点": m_score, "基本印": m_mark, "脚質": m_leg, "H": m_h, "B": m_b, "逃": m_run, "捲": m_roll, "差": m_diff, "マ": m_ma})
        
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
# --- ここから Part 3 ---

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
                    if st.button("学習させる（マルチデータ自動分類）", key=f"btn_{race['id']}"):
                        if actual_result:
                            line_str, place_details, pattern = update_scores_and_get_details(actual_result, race['データ'], race.get('並び予想', []))
                            category = get_payout_category(payout)
                            
                            history = load_json(DATA_FILE, [])
                            history.append({
                                "date": race['date'],
                                "実際の着順": actual_result,
                                "配当帯ゾーン": category,
                                "展開パターン": pattern,
                                "決着ライン": line_str,
                                "着順詳細": place_details,
                                "投資額": investment, "払戻額": payout, "収支": payout - investment,
                                "メモ": memo
                            })
                            save_json(DATA_FILE, history)
                            
                            pending_races.pop(i)
                            save_json(PENDING_FILE, pending_races)
                            st.success(f"配当【{category}】・展開【{pattern}】として学習完了！")
                            st.rerun()
                        else: st.warning("着順を入力してください！")
                with col_btn2:
                    if st.button("🗑️ 削除", key=f"del_{race['id']}"):
                        pending_races.pop(i)
                        save_json(PENDING_FILE, pending_races)
                        st.rerun()

with tab3:
    st.subheader("📊 期間・配当＆展開データ・マルチアナリティクス")
    
    st.markdown("### 🧠 AIスコア成長度メーター (初期値からの変化)")
    col_sc1, col_sc2 = st.columns(2)
    current_mark_scores = load_json(SCORE_FILE, DEFAULT_MARK_SCORES)
    current_line_scores = load_json(LINE_SCORE_FILE, DEFAULT_LINE_SCORES)
    
    with col_sc1:
        st.markdown("#### 🎯 印スコアの成長")
        for mark, score in current_mark_scores.items():
            if mark != "":
                base = DEFAULT_MARK_SCORES.get(mark, 0.0)
                diff = score - base
                diff_str = f"(+{diff:.2f})" if diff >= 0 else f"({diff:.2f})"
                st.write(f"- **{mark}**: `{score:.2f}`点 {diff_str}")
                
    with col_sc2:
        st.markdown("#### 🚩 ライン番号スコアの成長")
        for line, score in current_line_scores.items():
            base = DEFAULT_LINE_SCORES.get(line, 0.0)
            diff = score - base
            diff_str = f"(+{diff:.2f})" if diff >= 0 else f"({diff:.2f})"
            st.write(f"- **ライン{line}**: `{score:.2f}`点 {diff_str}")

    st.markdown("---")
    
    history_data = load_json(DATA_FILE, [])
    
    if not history_data:
        st.info("まだ学習データがありません。「結果の学習」からレース結果と払戻金を入力してください！")
    else:
        st.markdown("### 🔍 分析フィルター設定")
        
        dates = [h['date'][:10] for h in history_data if 'date' in h]
        min_d = datetime.datetime.strptime(min(dates), "%Y-%m-%d").date() if dates else datetime.date.today()
        max_d = datetime.datetime.strptime(max(dates), "%Y-%m-%d").date() if dates else datetime.date.today()
        
        col_d1, col_d2 = st.columns(2)
        with col_d1: start_date = st.date_input("開始日", value=min_d)
        with col_d2: end_date = st.date_input("終了日", value=max_d)
            
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            zone_options = ["すべて", "4,900円以下（堅実）", "5,000円〜9,900円（中配）", "10,000円〜49,000円（万車）", "50,000円以上（大穴）"]
            selected_zone = st.selectbox("🎯 配当帯ゾーン", zone_options)
        with col_f2:
            pattern_options = ["すべて", "2分戦", "3分戦", "細切れ戦", "先行一車/その他"]
            selected_pattern = st.selectbox("🏁 展開パターン", pattern_options)
        
        filtered_data = []
        for h in history_data:
            h_date_str = h.get('date', '')[:10]
            try:
                h_date = datetime.datetime.strptime(h_date_str, "%Y-%m-%d").date()
                in_date_range = (start_date <= h_date <= end_date)
            except:
                in_date_range = True
                
            in_zone = (selected_zone == "すべて" or h.get("配当帯ゾーン") == selected_zone)
            in_pattern = (selected_pattern == "すべて" or h.get("展開パターン") == selected_pattern)
            
            if in_date_range and in_zone and in_pattern:
                filtered_data.append(h)
        
        st.markdown(f"### 📈 抽出データ ({len(filtered_data)}件)")
        
        if not filtered_data:
            st.warning("条件に合うデータがまだありません。")
        else:
            total_inv = sum(h.get("投資額", 0) for h in filtered_data)
            total_pay = sum(h.get("払戻額", 0) for h in filtered_data)
            total_profit = total_pay - total_inv
            recovery_rate = (total_pay / total_inv * 100) if total_inv > 0 else 0
            
            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            col_m1.metric("期間内 投資額", f"{total_inv:,} 円")
            col_m2.metric("期間内 払戻額", f"{total_pay:,} 円")
            col_m3.metric("期間内 収支", f"{total_profit:+,} 円")
            col_m4.metric("期間内 回収率", f"{recovery_rate:.1f}%")
            
            st.markdown("---")
            
            all_marks, all_cars, all_lines, all_legs, ai_ranks = [], [], [], [], []
            for h in filtered_data:
                for detail in h.get("着順詳細", []):
                    all_marks.append(detail.get("印", "印なし"))
                    all_cars.append(f"{detail.get('車番')}番車")
                    all_lines.append(detail.get("ライン情報", "不明"))
                    all_legs.append(detail.get("脚質_ポジション", "不明"))
                    if detail.get("着順") == 1:
                        ai_ranks.append(detail.get("AI順位", 99))
            
            col_a1, col_a2 = st.columns(2)
            with col_a1:
                st.markdown("#### 🎯 来やすい【印】TOP3")
                for item, cnt in Counter(all_marks).most_common(3): st.write(f"- **{item}**: {cnt}回")
                
                st.markdown("#### 🚩 来やすい【ライン位置】TOP3")
                for item, cnt in Counter(all_lines).most_common(3): st.write(f"- **{item}**: {cnt}回")
                
            with col_a2:
                st.markdown("#### 🚴‍♂️ 決まり手【脚質×位置】TOP3")
                for item, cnt in Counter(all_legs).most_common(3): st.write(f"- **{item}**: {cnt}回")
                
                st.markdown("#### 🧠 AI1位評価の勝率（1着率）")
                rank1_cnt = ai_ranks.count(1)
                win_rate = (rank1_cnt / len(filtered_data) * 100) if filtered_data else 0
                st.metric("AI 1位のアタマ信頼度", f"{win_rate:.1f}%", f"{rank1_cnt}/{len(filtered_data)}勝")

        st.markdown("---")
        st.subheader("📝 過去のレース履歴")
        for idx, h in enumerate(history_data):
            profit_str = f"{h.get('収支', 0):+,} 円"
            zone = h.get('配当帯ゾーン', '未分類')
            pat = h.get('展開パターン', '不明')
            line_result = h.get('決着ライン', '不明')
            with st.expander(f"📅 {h['date']} | 【{zone}・{pat}】 | 収支: {profit_str}"):
                st.write(f"**払戻金**: {h.get('払戻額', 0):,}円 (投資: {h.get('投資額', 0):,}円)")
                st.write(f"**決着ライン**: {line_result}")
                if h.get("メモ"): st.write(f"**メモ**: {h.get('メモ')}")
                if st.button("🗑️ この履歴を削除する", key=f"del_hist_{idx}_{h.get('date', '')}"):
                    history_data.pop(idx)
                    save_json(DATA_FILE, history_data)
                    st.success("削除しました！")
                    st.rerun()
