import streamlit as st
import json
import os
import datetime
from collections import Counter

# --- データファイル設定 ---
DATA_FILE = "byn_history.json"
PENDING_FILE = "byn_pending.json"

def load_json(file_path, default_val):
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default_val

def save_json(file_path, data):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def analyze_byn_match(b_rare, y_rare, n_rare, b_axis, y_axis, n_axis):
    """B・Y・Nの重なり具合を自動判定"""
    # 荒れ指定の重なり数 (0〜3)
    rare_count = sum([1 for r in [b_rare, y_rare, n_rare] if r])
    if rare_count == 3:
        rare_pattern = "🔥 3サイト一致 (3/3)"
    elif rare_count == 2:
        rare_pattern = "⚡ 2サイト一致 (2/3)"
    elif rare_count == 1:
        rare_pattern = "💧 1サイトのみ (1/3)"
    else:
        rare_pattern = "🟩 荒れ指定なし (0/3)"

    # 軸車番の重なり
    axes = [a for a in [b_axis, y_axis, n_axis] if a is not None and a > 0]
    if len(axes) == 3:
        if axes[0] == axes[1] == axes[2]:
            axis_pattern = "🎯 軸3サイト一致"
        elif axes[0] == axes[1] or axes[1] == axes[2] or axes[0] == axes[2]:
            axis_pattern = "⚔️ 軸2サイト一致"
        else:
            axis_pattern = "❓ 軸完全不一致"
    else:
        axis_pattern = "未設定"

    return rare_pattern, axis_pattern, rare_count
# --- ここから Part 2 ---

st.set_page_config(page_title="BYN - 競輪3サイト重なり検証", page_icon="🎲")
st.title("🎲 BYN (B × Y × N) クロスアナリティクス")
st.markdown("予想サイト **B・Y・N** の荒れ予想＆軸の重なりと配当傾向を検証！")

tab1, tab2, tab3 = st.tabs(["✍️ レース＆BYN予想入力", "📝 結果の入力・蓄積", "📊 BYNデータ分析"])

with tab1:
    st.subheader("✍️ レース情報とBYN予想の入力")
    
    col_r1, col_r2, col_r3 = st.columns(3)
    with col_r1:
        race_date = st.date_input("日付", value=datetime.date.today())
    with col_r2:
        place_name = st.text_input("競輪場", value="平塚")
    with col_r3:
        race_num = st.number_input("レース番号", min_value=1, max_value=12, value=11)

    st.markdown("---")
    st.markdown("#### 🤖 サイト B・Y・N の予想内容")
    
    col_b, col_y, col_n = st.columns(3)
    
    with col_b:
        st.markdown("### 【 サイト B 】")
        b_rare = st.checkbox("🔥 荒れ予想指定", key="b_rare")
        b_axis = st.number_input("本命・軸車番", min_value=0, max_value=9, value=1, key="b_axis")
        b_memo = st.text_input("Bのメモ", value="", key="b_memo")
        
    with col_y:
        st.markdown("### 【 サイト Y 】")
        y_rare = st.checkbox("🔥 荒れ予想指定", key="y_rare")
        y_axis = st.number_input("本命・軸車番", min_value=0, max_value=9, value=1, key="y_axis")
        y_memo = st.text_input("Yのメモ", value="", key="y_memo")

    with col_n:
        st.markdown("### 【 サイト N 】")
        n_rare = st.checkbox("🔥 荒れ予想指定", key="n_rare")
        n_axis = st.number_input("本命・軸車番", min_value=0, max_value=9, value=1, key="n_axis")
        n_memo = st.text_input("Nのメモ", value="", key="n_memo")

    rare_pat, axis_pat, _ = analyze_byn_match(b_rare, y_rare, n_rare, b_axis, y_axis, n_axis)
    
    st.info(f"💡 **自動判定** ｜ 荒れ重なり: **{rare_pat}** ｜ 軸重なり: **{axis_pat}**")

    if st.button("📥 レースを保存（結果待ちにストック）"):
        pending = load_json(PENDING_FILE, [])
        race_data = {
            "id": str(datetime.datetime.now().timestamp()),
            "date": str(race_date),
            "place": place_name,
            "race_num": race_num,
            "B": {"rare": b_rare, "axis": b_axis, "memo": b_memo},
            "Y": {"rare": y_rare, "axis": y_axis, "memo": y_memo},
            "N": {"rare": n_rare, "axis": n_axis, "memo": n_memo},
            "rare_pattern": rare_pat,
            "axis_pattern": axis_pat
        }
        pending.append(race_data)
        save_json(PENDING_FILE, pending)
        st.success(f"{place_name}{race_num}R の予想をストックしました！")

with tab2:
    st.subheader("📝 結果待ちレースの着順・払戻金入力")
    pending = load_json(PENDING_FILE, [])
    
    if not pending:
        st.info("現在、結果待ちのレースはありません。")
    else:
        for idx, race in enumerate(pending):
            title = f"📅 {race['date']} {race['place']} {race['race_num']}R ({race['rare_pattern']})"
            with st.expander(title):
                st.write(f"**B**: {'🔥荒れ' if race['B']['rare'] else '通常'} (軸:{race['B']['axis']}) / **Y**: {'🔥荒れ' if race['Y']['rare'] else '通常'} (軸:{race['Y']['axis']}) / **N**: {'🔥荒れ' if race['N']['rare'] else '通常'} (軸:{race['N']['axis']})")
                
                col_p1, col_p2, col_p3 = st.columns(3)
                with col_p1:
                    actual_res = st.text_input("着順 (例: 1-2-3)", key=f"res_{race['id']}")
                with col_p2:
                    payout = st.number_input("3連単 払戻金 (円)", min_value=0, value=0, step=100, key=f"pay_{race['id']}")
                with col_p3:
                    investment = st.number_input("投資額 (円)", min_value=0, value=1000, step=100, key=f"inv_{race['id']}")
                
                col_b1, col_b2 = st.columns(2)
                with col_b1:
                    if st.button("💾 学習データとして確定・保存", key=f"save_{race['id']}"):
                        if actual_res:
                            history = load_json(DATA_FILE, [])
                            race["actual_result"] = actual_res
                            race["payout"] = payout
                            race["investment"] = investment
                            race["profit"] = payout - investment
                            history.append(race)
                            save_json(DATA_FILE, history)
                            
                            pending.pop(idx)
                            save_json(PENDING_FILE, pending)
                            st.success("結果を蓄積しました！")
                            st.rerun()
                        else:
                            st.warning("着順を入力してください！")
                with col_b2:
                    if st.button("🗑️ 削除", key=f"del_p_{race['id']}"):
                        pending.pop(idx)
                        save_json(PENDING_FILE, pending)
                        st.rerun()
# --- ここから Part 3 ---

with tab3:
    st.subheader("📊 BYN クロス分析・蓄積データ")
    history = load_json(DATA_FILE, [])
    
    if not history:
        st.info("まだ蓄積データがありません。「結果の入力・蓄積」で結果を保存してください！")
    else:
        # 期間絞り込み
        dates = [h['date'] for h in history if 'date' in h]
        min_d = datetime.datetime.strptime(min(dates), "%Y-%m-%d").date() if dates else datetime.date.today()
        max_d = datetime.datetime.strptime(max(dates), "%Y-%m-%d").date() if dates else datetime.date.today()
        
        col_d1, col_d2 = st.columns(2)
        with col_d1: start_d = st.date_input("開始日", value=min_d, key="s_d")
        with col_d2: end_d = st.date_input("終了日", value=max_d, key="e_d")
        
        filtered = []
        for h in history:
            try:
                h_d = datetime.datetime.strptime(h['date'], "%Y-%m-%d").date()
                if start_d <= h_d <= end_d:
                    filtered.append(h)
            except:
                filtered.append(h)
                
        st.markdown(f"### 📈 蓄積データ数: **{len(filtered)}** 件")
        
        if filtered:
            # 荒れ一致パターン別分析
            st.markdown("#### 🔥 1. 「荒れ予想指定」重なり別の傾向")
            patterns = ["🔥 3サイト一致 (3/3)", "⚡ 2サイト一致 (2/3)", "💧 1サイトのみ (1/3)", "🟩 荒れ指定なし (0/3)"]
            
            for pat in patterns:
                pat_data = [h for h in filtered if h.get("rare_pattern") == pat]
                cnt = len(pat_data)
                if cnt > 0:
                    avg_pay = sum(h.get("payout", 0) for h in pat_data) / cnt
                    max_pay = max(h.get("payout", 0) for h in pat_data)
                    tot_profit = sum(h.get("profit", 0) for h in pat_data)
                    tot_inv = sum(h.get("investment", 0) for h in pat_data)
                    rec_rate = (sum(h.get("payout", 0) for h in pat_data) / tot_inv * 100) if tot_inv > 0 else 0
                    
                    st.write(f"**【{pat}】** ({cnt}件)")
                    st.write(f"- 平均払戻金: `{int(avg_pay):,} 円` ｜ 最高配当: `{max_pay:,} 円` ｜ 回収率: `{rec_rate:.1f}%` (収支: `{tot_profit:+,} 円`)")
            
            st.markdown("---")
            st.markdown("#### 🎯 2. 「軸車番」重なり別の傾向")
            axis_pats = ["🎯 軸3サイト一致", "⚔️ 軸2サイト一致", "❓ 軸完全不一致"]
            for apat in axis_pats:
                apat_data = [h for h in filtered if h.get("axis_pattern") == apat]
                cnt = len(apat_data)
                if cnt > 0:
                    avg_pay = sum(h.get("payout", 0) for h in apat_data) / cnt
                    st.write(f"**【{apat}】** ({cnt}件) ｜ 平均払戻金: `{int(avg_pay):,} 円`")

        st.markdown("---")
        st.subheader("📝 レース履歴一覧")
        for idx, h in enumerate(history):
            title = f"📅 {h['date']} {h.get('place','')} {h.get('race_num','')}R ｜ 結果:{h.get('actual_result','')} ｜ 払戻:{h.get('payout',0):,}円"
            with st.expander(title):
                st.write(f"**荒れ指定パターン**: {h.get('rare_pattern')} ｜ **軸パターン**: {h.get('axis_pattern')}")
                st.write(f"**投資**: {h.get('investment',0):,}円 / **払戻**: {h.get('payout',0):,}円 / **収支**: {h.get('profit',0):+,}円")
                
                if st.button("🗑️ 履歴から削除", key=f"del_h_{idx}"):
                    history.pop(idx)
                    save_json(DATA_FILE, history)
                    st.success("削除しました！")
                    st.rerun()
