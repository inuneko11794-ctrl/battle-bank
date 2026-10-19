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
    This is a Keirin (cycling) race card, which may show '終了' (finished) status. Regardless of the race status, extract player data and line predictions into JSON format.
    Output ONLY valid JSON matching this exact schema, with no markdown formatting or other text:
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
    """マスター直伝！左から優先・1個限定ルールを適用しつつ、ラインの所属情報も選手データに付与する"""
    players = data.get("選手", [])
    lines = data.get("並び予想", [])
    
    player_dict = {p["車番"]: p for p in players}
    original_marks = {p["車番"]: p.get("基本印", "") for p in players}
    used_special_marks = set()
    
    for p in players:
        p["ライン情報"] = {"ライン番号": -1, "ポジション": "不明"}

    for line_idx, line in enumerate(lines):
        if len(line) == 1:
            current_car = line[0]
            if current_car in player_dict:
                curr_p = player_dict[current_car]
                curr_p["ライン情報"] = {"ライン番号": line_idx + 1, "ポジション": "単騎"}
                if original_marks[current_car] == "":
                    curr_p["基本印"] = "T" 
        else:
            for i in range(len(line)):
                current_car = line[i]
                if current_car not in player_dict:
                    continue
                    
                curr_p = player_dict[current_car]
                pos_name = "先頭" if i == 0 else ("番手" if i == 1 else f"{i+1}番手")
                curr_p["ライン情報"] = {"ライン番号": line_idx + 1, "ポジション": pos_name}
                
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
                        
    for curr_p in player_dict.values():
        if curr_p.get("基本印", "") == "":
            curr_p["基本印"] = "☆"
            
    return list(player_dict.values()), lines

def calculate_brain_score(player):
    score = player.get("競走得点", 0.0)
    mark_scores = {
        "◎": 10, "◯": 8, "△": 6, "✕": 4, "×": 4,
        "⑳": 0, "●": 0, "▲": 0, "✖": 0, "☆": 0, "T": 0
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
    p6 = sorted_players[5]["車番"] if len(sorted_players) > 5 else p5
    
    nitantan_candidates = [
        f"{p1} - {p2}", f"{p1} - {p3}", f"{p2} - {p1}",
        f"{p1} - {p4}", f"{p2} - {p3}", f"{p3} - {p1}", f"{p1} - {p5}"
    ]
    
    santantan_candidates = [
        f"{p1} - {p2} - {p3}", f"{p1} - {p2} - {p4}", f"{p1} - {p3} - {p2}",
        f"{p1} - {p3} - {p4}", f"{p2} - {p1} - {p3}", f"{p2} - {p1} - {p4}",
        f"{p1} - {p4} - {p2}", f"{p1} - {p4} - {p3}", f"{p1} - {p2} - {p5}",
        f"{p1} - {p3} - {p5}", f"{p2} - {p3} - {p1}", f"{p1} - {p5} - {p2}",
        f"{p2} - {p1} - {p4}", f"{p2} - {p3} - {p4}", f"{p3} - {p1} - {p2}",
        f"{p3} - {p1} - {p4}", f"{p1} - {p2} - {p6}", f"{p1} - {p3} - {p6}",
        f"{p1} - {p4} - {p6}", f"{p2} - {p3} - {p5}", f"{p3} - {p2} - {p1}",
        f"{p1} - {p5} - {p3}", f"{p2} - {p5} - {p1}", f"{p3} - {p2} - {p4}",
        f"{p1} - {p6} - {p2}"
    ]
    
    return {
        "単勝": [f"{p1}"],
        "2連単": nitantan_candidates[:max_2t_points],
        "3連単": santantan_candidates[:max_3t_points]
    }

# --- UI画面 ---
st.set_page_config(page_title="バトルバンク君 - 競輪AI予想", page_icon="🚴‍♂️")
st.title("🤖 バトルバンク君")
st.markdown("完全ハイブリッド版：AI自動読み取り ＆ 手動入力に対応！")

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
                    
                    for p in players:
                        p["AIスコア"] = calculate_brain_score(p)
                        
                    bets = generate_bets(players, max_2t_points, max_3t_points)
                    
                    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    save_pending_race({
                        "id": str(datetime.datetime.now().timestamp()),
                        "date": now_str,
                        "データ": players,
                        "並び予想": lines,
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
                        
                    with st.expander("🔍 読み取った詳細データを見る"):
                        st.json({"選手データ": players, "並び予想": lines})
                            
                except Exception as e:
                    st.error(f"エラーが発生しました: {e}")

    else:
        # --- 手動入力モード ---
        st.subheader("✍️ 手動データ入力モード")
        st.write("APIの制限を気にせず、選手データと並びを直接入力して予想・ストックできます。")
        
        num_players = st.number_input("出走人数（7車 or 9車）", min_value=7, max_value=9, value=7)
        
        manual_players = []
        st.markdown("#### 各選手のデータ入力")
        for c in range(1, int(num_players) + 1):
            with st.expander(f"車番 {c} の選手"):
                m_name = st.text_input(f"選手名 (車番{c})", value=f"選手{c}", key=f"m_name_{c}")
                m_score = st.number_input(f"競走得点 (車番{c})", min_value=70.0, max_value=120.0, value=90.0, step=0.01, key=f"m_score_{c}")
                m_mark = st.selectbox(f"基本印 (車番{c})", ["", "◎", "◯", "△", "✕"], key=f"m_mark_{c}")
                m_role = st.selectbox(f"役割 (車番{c})", ["先頭", "マーク", "単騎"], key=f"m_role_{c}")
                
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
                    "車番": c,
                    "選手名": m_name,
                    "競走得点": m_score,
                    "基本印": m_mark,
                    "ライン役割": m_role,
                    "H": m_h, "B": m_b, "逃": m_run, "捲": m_roll, "差": m_diff, "マ": m_ma
                })
        
        st.markdown("#### 並び予想（ライン）の入力")
        st.write("例: `1,7,2` または `5` のように車番をカンマ区切りで入力し、行ごとに改行（または複数入力）してください。")
        line_str_1 = st.text_input("ライン1（例: 1,7,2）", value="1, 7, 2")
        line_str_2 = st.text_input("ライン2（例: 5 または 4,3,6）", value="5")
        line_str_3 = st.text_input("ライン3（任意）", value="")
        
        if st.button("✍️ 手動データを解析・ストックする"):
            try:
                # 入力されたライン文字列を配列に変換
                lines = []
                for l_str in [line_str_1, line_str_2, line_str_3]:
                    if l_str.strip():
                        cars = [int(x.strip()) for x in l_str.split(",") if x.strip().isdigit()]
                        if cars:
                            lines.append(cars)
                            
                raw_data = {"選手": manual_players, "並び予想": lines}
                players, lines = apply_custom_marks(raw_data)
                
                for p in players:
                    p["AIスコア"] = calculate_brain_score(p)
                    
                bets = generate_bets(players, max_2t_points, max_3t_points)
                
                now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                save_pending_race({
                    "id": str(datetime.datetime.now().timestamp()),
                    "date": now_str,
                    "データ": players,
                    "並び予想": lines,
                    "予測": bets
                })
                
                st.success("手動データの解析完了！結果待ちリストにストックしました。")
                
                st.markdown("### 🎯 バトルバンク君の買い目")
                st.markdown("#### 🥇 【単勝】")
                for b in bets["単勝"]: st.code(b)
                st.markdown(f"#### 🥈 【2連単 ({len(bets['2連単'])}点)】")
                for b in bets["2連単"]: st.code(b)
                st.markdown(f"#### 🥉 【3連単 ({len(bets['3連単'])}点)】")
                for b in bets["3連単"]: st.code(b)
                    
            except Exception as e:
                st.error(f"入力形式にエラーがあります: {e}")

with tab2:
    st.subheader("📝 結果待ちのレース一覧")
    st.write("予想したレースがここに溜まります。レース終了後に着順、収支、メモを入力して学習させましょう！")
    
    pending_races = load_json(PENDING_FILE)
    
    if not pending_races:
        st.info("現在ストックされているレースはありません。")
    else:
        for i, race in enumerate(pending_races):
            with st.expander(f"レース日時: {race['date']}"):
                st.write("**【AIの予測】**")
                st.write(f"2連単: {', '.join(race['予測']['2連単'])}")
                st.write(f"3連単: {', '.join(race['予測']['3連単'])}")
                
                actual_result = st.text_input("実際の着順（例: 1-2-3）", key=f"res_{race['id']}")
                
                col_i1, col_i2 = st.columns(2)
                with col_i1:
                    investment = st.number_input("投資金額 (円)", min_value=0, value=1000, step=100, key=f"inv_{race['id']}")
                with col_i2:
                    payout = st.number_input("払戻金額 (円)", min_value=0, value=0, step=100, key=f"pay_{race['id']}")
                
                memo = st.text_area("レースメモ・感想（例: 展開が向いた、固かった等）", key=f"memo_{race['id']}")
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    if st.button("学習させる（収支を記録）", key=f"btn_{race['id']}"):
                        if actual_result:
                            history = load_json(DATA_FILE)
                            history.append({
                                "date": race['date'],
                                "データ": race['データ'],
                                "並び予想": race.get("並び予想", []),
                                "予測": race['予測'],
                                "実際の着順": actual_result,
                                "投資額": investment,
                                "払戻額": payout,
                                "収支": payout - investment,
                                "メモ": memo
                            })
                            save_json(DATA_FILE, history)
                            
                            pending_races.pop(i)
                            save_json(PENDING_FILE, pending_races)
                            
                            st.success("収支データを含めて学習を保存しました！")
                            st.rerun()
                        else:
                            st.warning("着順を入力してください！")
                
                with col_btn2:
                    if st.button("🗑️ 削除", key=f"del_{race['id']}"):
                        pending_races.pop(i)
                        save_json(PENDING_FILE, pending_races)
                        st.success("ストックを削除しました！")
                        st.rerun()

with tab3:
    st.subheader("📊 収支・データ分析")
    history_data = load_json(DATA_FILE)
    
    if not history_data:
        st.info("まだ学習・収支データがありません。「結果の学習」タブからレース結果と収支を入力してください！")
    else:
        st.markdown("#### 📅 表示する期間の絞り込み")
        col_d1, col_d2 = st.columns(2)
        
        dates = [h['date'][:10] for h in history_data if 'date' in h]
        min_date_str = min(dates) if dates else "2026-01-01"
        max_date_str = max(dates) if dates else "2026-12-31"
        
        default_start = datetime.datetime.strptime(min_date_str, "%Y-%m-%d").date()
        default_end = datetime.datetime.strptime(max_date_str, "%Y-%m-%d").date()
        
        with col_d1:
            start_date = st.date_input("開始日", value=default_start)
        with col_d2:
            end_date = st.date_input("終了日", value=default_end)
            
        filtered_history = []
        for h in history_data:
            h_date_str = h.get('date', '')[:10]
            try:
                h_date = datetime.datetime.strptime(h_date_str, "%Y-%m-%d").date()
                if start_date <= h_date <= end_date:
                    filtered_history.append(h)
            except:
                filtered_history.append(h)
                
        st.markdown("---")
        
        if not filtered_history:
            st.warning("指定された期間のデータはありません。")
        else:
            total_inv = sum(h.get("投資額", 0) for h in filtered_history)
            total_pay = sum(h.get("払戻額", 0) for h in filtered_history)
            total_profit = total_pay - total_inv
            recovery_rate = (total_pay / total_inv * 100) if total_inv > 0 else 0
            
            col_m1, col_m2, col_m3, col_m4 = st.columns(4)
            col_m1.metric("期間内 投資額", f"{total_inv:,} 円")
            col_m2.metric("期間内 払戻額", f"{total_pay:,} 円")
            col_m3.metric("期間内 収支", f"{total_profit:+,} 円", delta_color="normal" if total_profit >= 0 else "inverse")
            col_m4.metric("期間内 回収率", f"{recovery_rate:.1f}%")
            
            st.markdown("---")
            st.subheader(f"📝 選択期間のレース履歴 ({len(filtered_history)}件)")
            for h in filtered_history:
                profit_str = f"{h.get('収支', 0):+,} 円"
                with st.expander(f"📅 {h['date']} | 結果: {h.get('実際の着順', '不明')} | 収支: {profit_str}"):
                    st.write(f"**投資**: {h.get('投資額', 0):,}円 / **払戻**: {h.get('払戻額', 0):,}円")
                    if h.get("メモ"):
                        st.write(f"**メモ**: {h.get('メモ')}")
                    st.json(h)
