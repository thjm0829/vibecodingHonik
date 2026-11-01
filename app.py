import json
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

import streamlit as st
from openai import OpenAI
from pypdf import PdfReader
from pypdf.errors import PyPdfError
from supabase import create_client


QUIZ_SYSTEM_PROMPT = """
당신은 학습 퀴즈를 만드는 도우미입니다.
주어진 요약을 바탕으로 4지선다 퀴즈 3문항을 만드세요.
각 문항은 question, options(4개), answer(정답 인덱스, 0부터 시작), explanation을 포함해야 합니다.
결과는 {"questions": [...]} 형태의 JSON으로 반환하세요.
"""

STUDY_DOG_IMAGE = Path(__file__).parent / "assets" / "study-dog.png"


st.set_page_config(
    page_title="AI 학습 정리 노트",
    page_icon=":material/auto_stories:",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.html("""
<style>
    :root {
        --notes-title: #214C3B;
        --notes-blue: #2563EB;
        --notes-green: #267052;
        --notes-orange: #A65A16;
        --notes-red: #B4232D;
        --study-cream: #FFF9F2;
        --study-lilac: #EEEAFE;
        --study-sky: #EAF5FF;
    }

    .stApp {
        background:
            radial-gradient(circle at 12% 12%, rgba(255, 224, 174, 0.34), transparent 28%),
            radial-gradient(circle at 86% 18%, rgba(191, 220, 255, 0.42), transparent 31%),
            linear-gradient(135deg, var(--study-cream) 0%, var(--study-sky) 52%, var(--study-lilac) 100%);
    }

    [data-testid="stHeader"] { background: transparent; }
    [data-testid="stAppViewContainer"] { background: transparent; }
    [data-testid="stMainBlockContainer"] {
        position: relative;
        z-index: 1;
    }
    [data-testid="stSidebar"] > div:first-child {
        background: linear-gradient(180deg, rgba(232, 243, 238, 0.94), rgba(242, 237, 255, 0.92));
        backdrop-filter: blur(12px);
    }

    .study-scene {
        position: fixed;
        inset: 0;
        z-index: 0;
        overflow: hidden;
        pointer-events: none;
    }
    .study-glow {
        position: absolute;
        width: 18rem;
        height: 18rem;
        border-radius: 50%;
        filter: blur(12px);
        opacity: 0.28;
        animation: study-glow-drift 16s ease-in-out infinite alternate;
    }
    .study-glow--sun {
        top: 7%;
        right: 12%;
        background: #FFE2A9;
    }
    .study-glow--sky {
        bottom: 6%;
        left: 21%;
        background: #C8E7FF;
        animation-delay: -7s;
    }
    .study-paw,
    .study-note {
        position: absolute;
        opacity: 0.16;
        user-select: none;
        animation: study-float 12s ease-in-out infinite;
    }
    .study-paw {
        color: #7B72C8;
        font-size: 2.2rem;
    }
    .study-note {
        color: #D49A59;
        font-size: 1.8rem;
        animation-duration: 15s;
    }
    .study-paw--one { top: 22%; left: 7%; }
    .study-paw--two { top: 68%; right: 9%; animation-delay: -4s; }
    .study-paw--three { top: 84%; left: 48%; font-size: 1.5rem; animation-delay: -8s; }
    .study-note--one { top: 17%; right: 38%; animation-delay: -3s; }
    .study-note--two { bottom: 18%; left: 12%; animation-delay: -10s; }

    @keyframes study-float {
        0%, 100% { transform: translate3d(0, 0, 0) rotate(-5deg); }
        50% { transform: translate3d(8px, -14px, 0) rotate(5deg); }
    }
    @keyframes study-glow-drift {
        0% { transform: translate3d(-8px, 8px, 0) scale(0.92); }
        100% { transform: translate3d(18px, -14px, 0) scale(1.08); }
    }
    @media (prefers-reduced-motion: reduce) {
        .study-glow,
        .study-paw,
        .study-note { animation: none; }
    }

    [data-testid="stHeading"] :is(h1, h2, h3, h4) {
        color: var(--notes-title);
    }

    [data-testid="stTab"][data-key="0"] { color: var(--notes-blue); }
    [data-testid="stTab"][data-key="1"] { color: var(--notes-green); }
    [data-testid="stTab"][data-key="2"] { color: var(--notes-orange); }
    [data-testid="stTab"][data-key="3"] { color: var(--notes-blue); }
    [data-testid="stTab"][aria-selected="true"][data-key="0"] .react-aria-SelectionIndicator {
        background-color: var(--notes-blue) !important;
    }
    [data-testid="stTab"][aria-selected="true"][data-key="1"] .react-aria-SelectionIndicator {
        background-color: var(--notes-green) !important;
    }
    [data-testid="stTab"][aria-selected="true"][data-key="2"] .react-aria-SelectionIndicator {
        background-color: var(--notes-orange) !important;
    }
    [data-testid="stTab"][aria-selected="true"][data-key="3"] .react-aria-SelectionIndicator {
        background-color: var(--notes-blue) !important;
    }

    [data-testid="stExpander"] details {
        background-color: #FFFFFF;
        border-color: #C6D9E8;
    }
    [data-testid="stExpander"] summary { color: var(--notes-blue); }
    [data-testid="stMetricValue"] { color: var(--notes-green); }

    [data-testid="stButton"] button[kind="secondary"]:enabled {
        color: var(--notes-green);
        background-color: #EDF6F0;
        border-color: #B8D9C5;
    }
    [data-testid="stButton"] button[kind="secondary"]:enabled:hover {
        background-color: #E0EEE6;
        border-color: var(--notes-green);
    }

    .st-key-refresh_history [data-testid="stButton"] button:enabled {
        color: var(--notes-orange);
        background-color: #FFF4E8;
        border-color: #E4BD9B;
    }
    .st-key-refresh_history [data-testid="stButton"] button:enabled:hover {
        background-color: #FCE8D1;
        border-color: var(--notes-orange);
    }

    [class*="st-key-delete_summary_"] [data-testid="stButton"] button:enabled {
        color: var(--notes-red);
        background-color: #FFF1F0;
        border-color: #F2C2C0;
    }
    [class*="st-key-delete_summary_"] [data-testid="stButton"] button:enabled:hover {
        background-color: #FDE5E3;
        border-color: var(--notes-red);
    }
</style>
""")

st.html("""
<div class="study-scene" aria-hidden="true">
    <div class="study-glow study-glow--sun"></div>
    <div class="study-glow study-glow--sky"></div>
    <div class="study-paw study-paw--one">🐾</div>
    <div class="study-paw study-paw--two">🐾</div>
    <div class="study-paw study-paw--three">🐾</div>
    <div class="study-note study-note--one">✦</div>
    <div class="study-note study-note--two">✎</div>
</div>
""")

st.title("AI 학습 정리 노트")

with st.sidebar:
    st.header("문서")
    uploaded_pdf = st.file_uploader("PDF 업로드", type=["pdf"])
    if STUDY_DOG_IMAGE.exists():
        st.image(
            str(STUDY_DOG_IMAGE),
            caption="강아지 스터디 도우미",
            width="stretch",
        )

original_tab, summary_tab, quiz_tab, history_tab = st.tabs(["원문", "요약", "퀴즈", "저장 기록"])

try:
    supabase_client = create_client(
        st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"]
    )
except Exception:
    supabase_client = None

storage_notice = st.session_state.pop("storage_notice", None)
if storage_notice:
    st.toast(storage_notice)

with history_tab:
    st.subheader("저장 기록")
    st.button("새로고침", icon=":material/refresh:", key="refresh_history")

    if supabase_client is None:
        st.warning("Supabase 연결 설정을 확인해 주세요. SUPABASE_URL과 SUPABASE_KEY가 필요합니다.")
    else:
        try:
            records = (
                supabase_client.table("summaries")
                .select("id, filename, summary, created_at")
                .order("created_at", desc=True)
                .execute()
                .data
            )
        except Exception:
            records = None
            st.error("저장 기록을 불러오지 못했습니다. 네트워크와 summaries 테이블의 조회 권한을 확인해 주세요.")

        if records == []:
            st.info("저장된 요약이 없습니다.")

        for record in records or []:
            saved_summary = record.get("summary") or {}
            preview = saved_summary.get("summary", "") if isinstance(saved_summary, dict) else ""
            if isinstance(preview, list):
                preview = " ".join(str(sentence) for sentence in preview)
            preview = " ".join(str(preview).split())
            preview = preview[:120] + ("..." if len(preview) > 120 else "")

            saved_at = str(record.get("created_at") or "")
            try:
                saved_at = (
                    datetime.fromisoformat(saved_at.replace("Z", "+00:00"))
                    .astimezone(timezone(timedelta(hours=9)))
                    .strftime("%Y-%m-%d %H:%M:%S (KST)")
                )
            except ValueError:
                saved_at = saved_at or "알 수 없음"

            details_column, actions_column = st.columns([6, 1])
            with details_column:
                st.text(str(record.get("filename") or "이름 없는 문서"))
                st.caption(f"저장 시각: {saved_at}")
                st.text(preview or "핵심 요약 없음")

            with actions_column:
                if st.button("삭제", icon=":material/delete:", key=f"delete_summary_{record['id']}"):
                    try:
                        deleted = (
                            supabase_client.table("summaries")
                            .delete()
                            .eq("id", record["id"])
                            .execute()
                        )
                        if deleted.data:
                            st.session_state["storage_notice"] = "요약 기록을 삭제했습니다."
                            st.rerun()
                        else:
                            st.warning("삭제된 기록이 없습니다. 이미 삭제됐거나 삭제 권한이 없을 수 있습니다.")
                    except Exception:
                        st.error("삭제하지 못했습니다. 네트워크와 summaries 테이블의 삭제 권한을 확인해 주세요.")
            st.divider()

if uploaded_pdf is None:
    with original_tab:
        st.info("선택된 문서가 없습니다.")
    with summary_tab:
        st.info("PDF를 업로드하면 요약할 수 있습니다.")
    with quiz_tab:
        st.info("PDF를 업로드하고 요약을 만든 뒤 퀴즈를 생성할 수 있습니다.")
    st.stop()

try:
    with st.spinner("PDF를 읽는 중..."):
        reader = PdfReader(uploaded_pdf)

        if reader.is_encrypted:
            with original_tab:
                st.error("암호로 보호된 PDF입니다. 암호를 해제한 파일을 업로드해 주세요.")
            st.stop()

        page_count = len(reader.pages)
        page_texts = [page.extract_text() or "" for page in reader.pages]
except (PyPdfError, ValueError, OSError):
    with original_tab:
        st.error("PDF를 읽을 수 없습니다. 파일이 손상되지 않았는지 확인해 주세요.")
    st.stop()

with st.sidebar:
    st.divider()
    st.subheader("문서 정보")
    st.caption("파일명")
    st.text(uploaded_pdf.name)
    st.metric("총 페이지 수", page_count)

full_text = "\n\n".join(
    f"[{page_number}페이지]\n{page_text}"
    for page_number, page_text in enumerate(page_texts, start=1)
).strip()

document_key = f"{uploaded_pdf.name}:{sha256(uploaded_pdf.getvalue()).hexdigest()}"
if st.session_state.get("summary_document_key") != document_key:
    st.session_state["summary_document_key"] = document_key
    st.session_state.pop("summary_result", None)
    st.session_state.pop("saved_summary_id", None)
    st.session_state.pop("quiz_result", None)
    st.session_state["quiz_version"] = st.session_state.get("quiz_version", 0) + 1

with original_tab:
    for page_number, page_text in enumerate(page_texts, start=1):
        with st.expander(f"{page_number}페이지"):
            if page_text.strip():
                st.text(page_text)
            else:
                st.warning("추출할 텍스트가 없습니다. 이미지로만 된 스캔 PDF는 OCR 처리가 필요합니다.")

with summary_tab:
    st.subheader("AI 요약")

    if st.button("요약하기", type="primary", disabled=not full_text):
        try:
            api_key = st.secrets["OPENAI_API_KEY"]
        except Exception:
            st.error("OPENAI_API_KEY가 설정되지 않았습니다.")
        else:
            try:
                with st.spinner("PDF 내용을 요약하는 중..."):
                    client = OpenAI(api_key=api_key)
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        response_format={"type": "json_object"},
                        messages=[
                            {
                                "role": "system",
                                "content": (
                                    "PDF 텍스트를 분석해 반드시 JSON으로만 응답하세요. "
                                    "핵심 요약은 정확히 3문장으로 작성하고 키는 summary로 하세요. "
                                    "주요 키워드 5개를 keywords 배열로 반환하세요. "
                                    "난이도는 '상', '중', '하' 중 하나로 difficulty 키에 반환하세요."
                                ),
                            },
                            {"role": "user", "content": full_text[:100000]},
                        ],
                    )
                    result = json.loads(response.choices[0].message.content)
                    st.session_state["summary_result"] = result
                    st.session_state.pop("saved_summary_id", None)
                    st.session_state.pop("quiz_result", None)
                    st.session_state["quiz_version"] = st.session_state.get("quiz_version", 0) + 1
            except Exception as exc:
                st.error(f"요약 중 오류가 발생했습니다: {exc}")

    result = st.session_state.get("summary_result")
    if result:
        st.markdown("#### 핵심 요약")
        summary = result.get("summary", "")
        if isinstance(summary, list):
            summary = "\n".join(summary)
        st.write(summary)

        st.markdown("#### 주요 키워드")
        keywords = result.get("keywords", [])
        if isinstance(keywords, list) and keywords:
            st.write(" · ".join(str(keyword) for keyword in keywords[:5]))
        else:
            st.write("-")

        st.markdown("#### 난이도")
        st.write(result.get("difficulty", "-"))

        if supabase_client is None:
            st.warning("Supabase 연결 설정이 없어 저장할 수 없습니다.")

        if st.button("저장", icon=":material/save:", disabled=supabase_client is None):
            if supabase_client is not None:
                try:
                    saved = (
                        supabase_client.table("summaries")
                        .insert({"filename": uploaded_pdf.name, "summary": result})
                        .execute()
                    )
                    if saved.data:
                        saved_record = saved.data[0] if isinstance(saved.data, list) else saved.data
                        if isinstance(saved_record, dict) and saved_record.get("id") is not None:
                            st.session_state["saved_summary_id"] = saved_record["id"]
                        st.session_state["storage_notice"] = "요약을 저장했습니다."
                        st.rerun()
                    else:
                        st.warning("저장 결과를 확인하지 못했습니다. 저장 기록을 새로고침해 주세요.")
                except Exception:
                    st.error("저장하지 못했습니다. 네트워크와 summaries 테이블의 저장 권한을 확인해 주세요.")

with quiz_tab:
    st.subheader("AI 퀴즈")
    quiz_summary = st.session_state.get("summary_result")
    saved_summary_id = st.session_state.get("saved_summary_id")

    if not quiz_summary:
        st.info("먼저 요약 탭에서 요약을 만들어 주세요.")
    else:
        st.caption("현재 요약 결과를 바탕으로 4지선다 퀴즈 3문항을 만듭니다.")
        if st.button("퀴즈 생성", type="primary", disabled=supabase_client is None):
            if saved_summary_id is None:
                st.warning("먼저 저장해주세요.")
            else:
                try:
                    api_key = st.secrets["OPENAI_API_KEY"]
                except Exception:
                    st.error("OPENAI_API_KEY가 설정되지 않았습니다.")
                else:
                    try:
                        with st.spinner("요약을 바탕으로 퀴즈를 만드는 중..."):
                            client = OpenAI(api_key=api_key)
                            response = client.chat.completions.create(
                                model="gpt-4o-mini",
                                response_format={"type": "json_object"},
                                messages=[
                                    {"role": "system", "content": QUIZ_SYSTEM_PROMPT},
                                    {
                                        "role": "user",
                                        "content": json.dumps(quiz_summary, ensure_ascii=False),
                                    },
                                ],
                            )
                            generated_quiz = json.loads(response.choices[0].message.content)
                            questions = generated_quiz.get("questions")
                            if not isinstance(questions, list) or not questions:
                                raise ValueError("퀴즈 문항이 올바른 형식으로 반환되지 않았습니다.")

                            updated = (
                                supabase_client.table("summaries")
                                .update({"quiz": generated_quiz})
                                .eq("id", saved_summary_id)
                                .execute()
                            )
                            if not updated.data:
                                raise ValueError("저장된 요약 행을 업데이트하지 못했습니다.")

                            st.session_state["quiz_result"] = generated_quiz
                            st.session_state["quiz_version"] = st.session_state.get("quiz_version", 0) + 1
                            st.session_state["storage_notice"] = "퀴즈를 저장된 요약에 연결했습니다."
                            st.rerun()
                    except Exception as exc:
                        st.error(f"퀴즈 생성 중 오류가 발생했습니다: {exc}")

    quiz_result = st.session_state.get("quiz_result")
    if quiz_result:
        questions = quiz_result.get("questions", [])
        quiz_version = st.session_state.get("quiz_version", 0)
        for question_number, question in enumerate(questions, start=1):
            question_text = question.get("question", "문항 내용을 불러오지 못했습니다.")
            options = question.get("options", [])
            st.markdown(f"#### {question_number}. {question_text}")

            if not isinstance(options, list) or len(options) != 4:
                st.error("보기 4개가 있는 문항만 표시할 수 있습니다.")
                continue

            selected = st.radio(
                "보기 선택",
                options=[str(option) for option in options],
                index=None,
                key=f"quiz_answer_{quiz_version}_{question_number}",
            )
            if selected is not None:
                selected_index = [str(option) for option in options].index(selected)
                try:
                    answer_index = int(question.get("answer", -1))
                except (TypeError, ValueError):
                    answer_index = -1

                if selected_index == answer_index:
                    st.success("정답입니다!")
                else:
                    correct_option = (
                        str(options[answer_index])
                        if 0 <= answer_index < len(options)
                        else "확인할 수 없음"
                    )
                    st.error(f"오답입니다. 정답: {correct_option}")
                st.info(f"해설: {question.get('explanation', '해설이 없습니다.')}")
