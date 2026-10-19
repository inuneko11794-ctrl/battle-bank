import streamlit as st
import google.generativeai as genai

st.set_page_config(page_title="AIモデル確認", page_icon="🔍")
st.title("🔍 AIモデル確認ツール")

if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    
    st.write("あなたのAPIキーで使えるAIの名前をGoogleから取得します。")
    if st.button("使えるAIモデルを調べる"):
        with st.spinner("Googleに問い合わせ中..."):
            try:
                # 画像や文章の読み取り（generateContent）が使えるモデルだけを抽出
                available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                
                if available_models:
                    st.success("取得成功！以下のリストのスクリーンショットを撮るか、文字を教えてください。")
                    for m in available_models:
                        st.code(m)
                else:
                    st.warning("使えるモデルが見つかりませんでした。")
            except Exception as e:
                st.error(f"APIキーのエラーです: {e}")
else:
    st.error("APIキーが設定されていません。StreamlitのSecrets設定を確認してください。")
