"""AI Job Copilot - Streamlit Application.

Professional multi-page interface for the AI Resume Intelligence Platform.
"""
import io
import PyPDF2
import streamlit as st
import requests
from datetime import datetime

# ─── Configuration ───────────────────────────────────────────────────────────

API_BASE_URL = "http://localhost:8000"

# Actionable suggestions for AI tools commonly listed in JDs
AI_TOOL_SUGGESTIONS: dict = {
    "cursor": (
        "Cursor is an AI-powered code editor. Build a small project using Cursor "
        "and mention it - e.g. 'Built X using Cursor for AI-assisted development.' "
        "It's free to try and takes an afternoon to pick up."
    ),
    "copilot": (
        "GitHub Copilot is an AI coding assistant built into VS Code. Enable it on "
        "any personal project, then add 'Used GitHub Copilot to accelerate development' "
        "to your resume. Free trial available."
    ),
    "claude": (
        "Claude is Anthropic's AI assistant. If you've used it for coding, writing, "
        "or data tasks, mention it explicitly - e.g. 'Leveraged Claude for code review "
        "and documentation.' Consider building a small Claude API integration project."
    ),
    "chatgpt": (
        "ChatGPT/GPT-4 is OpenAI's assistant. If you've used it in a project workflow, "
        "make that explicit on your resume. A small GPT API integration project is easy "
        "to build and shows hands-on LLM experience."
    ),
    "gemini": (
        "Gemini is Google's AI model. Try integrating the Gemini API into a side project "
        "and add it to your GitHub. Mention it as 'Built X using Gemini API.'"
    ),
    "tabnine": (
        "Tabnine is an AI code completion tool. It has a free tier - install it, use it "
        "on a project, and add it to your tools section."
    ),
    "codeium": (
        "Codeium is a free AI coding assistant. Install it in VS Code, use it on a "
        "project, and mention it in your resume tools section."
    ),
}

st.set_page_config(
    page_title="AI Job Copilot",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Session State Initialization ────────────────────────────────────────────

if "current_resume_id" not in st.session_state:
    st.session_state.current_resume_id = None
if "current_jd_id" not in st.session_state:
    st.session_state.current_jd_id = None
if "current_analysis_id" not in st.session_state:
    st.session_state.current_analysis_id = None
if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None
if "analysis_polling" not in st.session_state:
    st.session_state.analysis_polling = False
if "page" not in st.session_state:
    st.session_state.page = "Dashboard"

# ─── Sidebar Navigation ─────────────────────────────────────────────────────

with st.sidebar:
    st.title("AI Job Copilot")
    st.markdown("---")

    page = st.radio(
        "Navigation",
        [
            "Dashboard",
            "Resume Upload",
            "Job Description",
            "ATS Analysis",
            "Skills Gap",
            "Resume Optimization",
            "Skill Validation",
        ],
        key="nav_radio",
    )
    st.session_state.page = page

    st.markdown("---")
    st.caption(f"v2.0.0 | {datetime.now().strftime('%Y-%m-%d')}")

# ─── Helper Functions ────────────────────────────────────────────────────────


def api_call(method: str, endpoint: str, **kwargs):
    """Make an API call with error handling."""
    try:
        url = f"{API_BASE_URL}{endpoint}"
        response = getattr(requests, method)(url, **kwargs, timeout=180)
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"API Error: {response.status_code} - {response.text}")
            return None
    except requests.ConnectionError:
        st.warning("API server not running. Start with: `uvicorn src.api.main:app`")
        return None
    except Exception as e:
        st.error(f"Error: {str(e)}")
        return None


# ─── Pages ───────────────────────────────────────────────────────────────────

if st.session_state.page == "Dashboard":
    st.header("Dashboard")
    st.markdown("### Analysis History & Score Trends")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Analyses", "-")
    with col2:
        st.metric("Avg Score", "-")
    with col3:
        st.metric("Cache Hit Rate", "-")

    # Fetch history
    history = api_call("get", "/history?limit=10")
    if history and history.get("items"):
        st.markdown("### Recent Analyses")
        for item in history["items"]:
            with st.expander(
                f"{item.get('jd_title', 'Untitled')} - Score: {item.get('overall_score', 'N/A')}%"
            ):
                st.write(f"**Status:** {item['status']}")
                st.write(f"**Date:** {item['created_at']}")
                st.write(f"**Resume:** {item.get('resume_filename', 'N/A')}")
    else:
        st.info("No analyses yet. Upload a resume and job description to get started.")

    # Cache metrics
    metrics = api_call("get", "/metrics/cache")
    if metrics and metrics.get("metrics"):
        st.markdown("### Cache Performance")
        m = metrics["metrics"]
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Hit Rate", f"{m.get('hit_rate', 0)}%")
        with col2:
            st.metric("Total Requests", m.get("total_requests", 0))
        with col3:
            st.metric("Latency Saved", f"{m.get('total_latency_saved_ms', 0):.0f}ms")
        with col4:
            st.metric("Cache Size", f"{m.get('current_size', 0)}/{m.get('max_size', 0)}")


elif st.session_state.page == "Resume Upload":
    st.header("Resume Upload")
    st.markdown("Upload your resume for parsing and analysis.")

    upload_method = st.radio("Upload Method", ["Paste Text", "Upload PDF"])

    if upload_method == "Paste Text":
        resume_text = st.text_area(
            "Paste your resume text",
            height=400,
            placeholder="Paste your full resume text here...",
        )

        if st.button("Process Resume", type="primary"):
            if resume_text and len(resume_text) >= 50:
                with st.spinner("Parsing and embedding resume..."):
                    result = api_call(
                        "post",
                        "/resume/upload",
                        json={"text": resume_text, "filename": "pasted_resume.txt"},
                    )
                    if result:
                        st.session_state.current_resume_id = result["resume_id"]
                        st.success(f"Resume processed! ID: {result['resume_id']}")
                        st.markdown("**Parsed Sections:**")
                        for section in result.get("parsed_sections", []):
                            st.write(f"- {section}")
            else:
                st.warning("Resume text must be at least 50 characters.")

    else:
        uploaded_file = st.file_uploader("Upload PDF", type=["pdf"])

        if uploaded_file:
            st.info(f"Selected file: {uploaded_file.name}")

            if st.button("Process Resume PDF", type="primary"):
                try:
                    pdf_reader = PyPDF2.PdfReader(io.BytesIO(uploaded_file.getvalue()))

                    resume_text = ""
                    for page in pdf_reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            resume_text += page_text + "\n"

                    if len(resume_text.strip()) < 50:
                        st.error(
                            "Could not extract enough text from this PDF. "
                            "Use a text-based resume PDF or paste the resume text manually."
                        )
                    else:
                        with st.spinner("Parsing and embedding resume PDF..."):
                            result = api_call(
                                "post",
                                "/resume/upload",
                                json={
                                    "text": resume_text,
                                    "filename": uploaded_file.name,
                                },
                            )

                        if result:
                            st.session_state.current_resume_id = result["resume_id"]
                            st.success(f"Resume processed! ID: {result['resume_id']}")
                            st.markdown("**Parsed Sections:**")
                            for section in result.get("parsed_sections", []):
                                st.write(f"- {section}")

                except Exception as e:
                    st.error(f"PDF processing failed: {str(e)}")

    if st.session_state.current_resume_id:
        st.success(f"Active Resume ID: `{st.session_state.current_resume_id}`")


elif st.session_state.page == "Job Description":
    st.header("Job Description Upload")
    st.markdown("Paste the job description you want to analyze against.")

    jd_title = st.text_input("Job Title (optional)")
    jd_company = st.text_input("Company (optional)")
    jd_text = st.text_area(
        "Job Description Text",
        height=400,
        placeholder="Paste the full job description here...",
    )

    if st.button("Process Job Description", type="primary"):
        if jd_text and len(jd_text) >= 50:
            with st.spinner("Parsing job description..."):
                result = api_call(
                    "post",
                    "/job/upload",
                    json={
                        "text": jd_text,
                        "title": jd_title or None,
                        "company": jd_company or None,
                    },
                )
                if result:
                    st.session_state.current_jd_id = result["jd_id"]
                    st.success(f"Job description processed! ID: {result['jd_id']}")
                    st.markdown("**Parsed Sections:**")
                    for section in result.get("parsed_sections", []):
                        st.write(f"- {section}")
        else:
            st.warning("Job description must be at least 50 characters.")

    if st.session_state.current_jd_id:
        st.success(f"Active JD ID: `{st.session_state.current_jd_id}`")


elif st.session_state.page == "ATS Analysis":
    st.header("ATS Analysis")
    st.markdown("Run a comprehensive ATS compatibility analysis.")

    if not st.session_state.current_resume_id or not st.session_state.current_jd_id:
        st.warning("Please upload both a resume and job description first.")
    else:
        st.info(
            f"Resume: `{st.session_state.current_resume_id}`\n\n"
            f"Job Description: `{st.session_state.current_jd_id}`"
        )

        # Custom weights
        with st.expander("Advanced: Custom Scoring Weights"):
            st.caption("Defaults are tuned for ATS matching. Adjust only if you want to prioritize differently.")
            col_w1, col_w2, col_w3 = st.columns(3)
            with col_w1:
                kw = st.slider("Keyword Weight", 0.0, 1.0, 0.5, 0.05,
                    help="Exact and near-exact skill matches. Most ATS systems weight this highest.")
            with col_w2:
                sw = st.slider("Semantic Weight", 0.0, 1.0, 0.3, 0.05,
                    help="Contextual similarity - catches synonyms and related experience.")
            with col_w3:
                cw = st.slider("Category Weight", 0.0, 1.0, 0.2, 0.05,
                    help="How well your skill categories (technical, functional, etc.) align with the JD.")
            total_w = kw + sw + cw
            if abs(total_w - 1.0) > 0.01:
                st.warning(f"Weights should sum to 1.0 (current: {total_w:.2f}). Consider adjusting.")

        if st.button("Run Analysis", type="primary"):
            payload = {
                "resume_id": st.session_state.current_resume_id,
                "jd_id": st.session_state.current_jd_id,
            }
            result = api_call("post", "/analysis/run", json=payload)
            if result:
                st.session_state.current_analysis_id = result["analysis_id"]
                st.session_state.analysis_result = None  # clear previous
                st.session_state.analysis_polling = True
                st.rerun()

        # Polling loop - runs on each rerun until analysis is complete
        if st.session_state.get("analysis_polling") and st.session_state.current_analysis_id:
            import time as _time
            steps = ["Extracting skills...", "Normalizing skills...", "Retrieving evidence...", "Generating report..."]
            status_box = st.empty()
            progress_bar = st.progress(0)
            poll_count = 0
            while True:
                poll_result = api_call("get", f"/analysis/{st.session_state.current_analysis_id}")
                if poll_result:
                    status = poll_result.get("status", "processing")
                    if status == "completed":
                        st.session_state.analysis_result = poll_result
                        st.session_state.analysis_polling = False
                        status_box.empty()
                        progress_bar.empty()
                        st.rerun()
                    elif status == "failed":
                        st.session_state.analysis_polling = False
                        status_box.error("Analysis failed. Please try again.")
                        progress_bar.empty()
                        break
                    else:
                        step_label = steps[min(poll_count // 3, len(steps) - 1)]
                        progress = min(0.1 + poll_count * 0.04, 0.9)
                        status_box.info(f"⏳ {step_label} (this takes ~60s on first run)")
                        progress_bar.progress(progress)
                        poll_count += 1
                        _time.sleep(2)
                else:
                    break

        # Display results
        if st.session_state.analysis_result:
            result = st.session_state.analysis_result
            score = result.get("score", {})

            # Score display
            st.markdown("---")
            st.markdown("### Score Breakdown")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Overall Score", f"{score.get('overall_score', 0):.1f}%")
            with col2:
                st.metric("Keyword Score", f"{score.get('keyword_score', 0):.1f}%")
            with col3:
                st.metric("Semantic Score", f"{score.get('semantic_score', 0):.1f}%")

            # Category scores
            if score.get("category_scores"):
                st.markdown("### Category Scores")
                for cat, data in score["category_scores"].items():
                    st.write(
                        f"**{cat.title()}**: {data.get('score', 0)}% "
                        f"({data.get('matched', 0)}/{data.get('total', 0)} matched)"
                    )

            # Explainability
            explanation = result.get("explainability", {})
            if explanation:
                st.markdown("### Explainability Report")
                st.write(explanation.get("summary", ""))

                with st.expander("Points Awarded"):
                    for item in explanation.get("points_awarded", []):
                        st.write(f"+ {item.get('reason', '')} ({item.get('points', 0)} pts)")

                with st.expander("Points Deducted"):
                    for item in explanation.get("points_deducted", []):
                        st.write(f"- {item.get('reason', '')} ({item.get('points', 0)} pts)")

            # Processing time
            if result.get("processing_time_ms"):
                st.caption(f"Processing time: {result['processing_time_ms']}ms")


elif st.session_state.page == "Skills Gap":
    st.header("Skills Gap Analysis")

    if not st.session_state.analysis_result:
        st.warning("Run an ATS analysis first to see skills gap.")
    else:
        result = st.session_state.analysis_result

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### Matched Skills")
            for skill in result.get("matched_skills", []):
                st.write(f"✅ **{skill['skill']}** ({skill.get('match_type', 'matched')})")

        with col2:
            st.markdown("### Missing Skills")
            for skill in result.get("missing_skills", []):
                skill_name = skill['skill']
                category = skill.get('category', 'unknown')
                suggestion = AI_TOOL_SUGGESTIONS.get(skill_name.lower())
                st.write(f"❌ **{skill_name}** ({category})")
                if suggestion:
                    st.info(f"💡 {suggestion}")

        # Evidence
        evidence = result.get("evidence", [])
        if evidence:
            st.markdown("### Evidence")
            for item in evidence[:10]:
                with st.expander(f"{item.get('skill', 'Unknown')}"):
                    if item.get("found_in_resume"):
                        st.write("✅ Found in resume")
                        st.write(f"Similarity: {item.get('similarity', 0):.2%}")
                        for snippet in item.get("evidence_snippets", []):
                            st.code(snippet, language=None)
                    else:
                        st.write("❌ Not found in resume")


elif st.session_state.page == "Resume Optimization":
    st.header("Resume Optimization")
    st.markdown("AI-powered bullet point rewriting for ATS optimization.")

    if not st.session_state.analysis_result:
        st.warning("Run an ATS analysis first.")
    else:
        result = st.session_state.analysis_result
        explanation = result.get("explainability", {})

        # Recommendations
        recommendations = result.get("recommendations", [])
        if recommendations:
            st.markdown("### Improvement Priority")
            for i, rec in enumerate(recommendations[:5], 1):
                st.write(f"{i}. {rec}")

        # Optimized bullets
        st.markdown("### Optimized Bullet Points")
        optimized_bullets = result.get("optimized_bullets") or []
        if not optimized_bullets:
            st.info("Re-run analysis to generate optimized bullets.")
        else:
            for i, item in enumerate(optimized_bullets, 1):
                with st.expander(f"Bullet {i}: {item.get('original', '')[:80]}..."):
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.markdown("**Original**")
                        st.write(item.get("original", ""))
                    with col_b:
                        st.markdown("**Optimized ✨**")
                        st.success(item.get("optimized", ""))
                    if item.get("keywords_added"):
                        st.caption(f"Keywords added: {', '.join(item['keywords_added'])}")
                    if item.get("score_impact"):
                        st.caption(f"Score impact: {item['score_impact']}")


elif st.session_state.page == "Skill Validation":
    st.header("Skill Validation Quiz")
    st.markdown("Test your knowledge of skills identified in the analysis.")

    if not st.session_state.current_analysis_id:
        st.warning("Run an ATS analysis first.")
    else:
        skill_to_test = st.text_input("Skill to test", placeholder="e.g., Python, React, SQL")
        difficulty = st.select_slider("Difficulty", ["easy", "medium", "hard"], value="medium")
        num_questions = st.slider("Number of questions", 3, 10, 5)

        if st.button("Generate Quiz", type="primary"):
            with st.spinner("Generating quiz questions..."):
                result = api_call(
                    "post",
                    "/quiz/start",
                    json={
                        "analysis_id": st.session_state.current_analysis_id,
                        "skill": skill_to_test,
                        "difficulty": difficulty,
                        "num_questions": num_questions,
                    },
                )
                if result:
                    st.session_state.quiz_data = result
                    st.session_state.quiz_answers = {}

        # Display quiz
        if "quiz_data" in st.session_state and st.session_state.quiz_data:
            quiz = st.session_state.quiz_data
            st.markdown(f"### Quiz: {quiz.get('skill', '')}")

            with st.form("quiz_form"):
                answers = []
                for q in quiz.get("questions", []):
                    st.markdown(f"**Q{q['question_id']}:** {q['question']}")
                    answer = st.radio(
                        f"Select answer for Q{q['question_id']}",
                        q["options"],
                        key=f"q_{q['question_id']}",
                    )
                    answers.append({"answer": answer[0] if answer else ""})

                submitted = st.form_submit_button("Submit Answers")
                if submitted:
                    result = api_call(
                        "post",
                        "/quiz/submit",
                        json={
                            "quiz_id": quiz["quiz_id"],
                            "answers": answers,
                        },
                    )
                    if result:
                        st.markdown("### Results")
                        st.metric("Score", f"{result.get('score', 0):.0f}%")
                        st.write(f"**Status:** {result.get('passed', 'unknown')}")
                        st.write(
                            f"**Correct:** {result.get('correct_answers', 0)}"
                            f"/{result.get('total_questions', 0)}"
                        )
