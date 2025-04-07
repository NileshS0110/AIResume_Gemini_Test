import streamlit as st
import google.generativeai as genai
import docx2txt
import PyPDF2
import pandas as pd
import base64
from datetime import datetime
import re
import io
import json

# --- Gemini Setup ---
if "GEMINI_API_KEY" not in st.secrets:
    st.error("API key missing! Add to Streamlit Secrets.")
    st.stop()

genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-1.5-pro-latest')

# --- Initialize Session State ---
if 'jd_text' not in st.session_state:
    st.session_state.jd_text = ""
if 'candidates' not in st.session_state:
    st.session_state.candidates = []
if 'email' not in st.session_state:
    st.session_state.email = ""

# --- Utility Functions ---
def extract_text(file):
    if file.type == "application/pdf":
        reader = PyPDF2.PdfReader(file)
        return " ".join(page.extract_text() for page in reader.pages if page.extract_text())
    elif file.type.endswith('document'):
        return docx2txt.process(file)
    return file.read().decode()



def analyze_resume(jd, resume_text):
    prompt = f"""
    Analyze this resume against the job description and return STRICT JSON format only:
    
    {{
        "score": 0-100,
        "matches": ["skill1", "skill2", "skill3"],
        "gaps": ["requirement1", "requirement2", "requirement3"],
        "summary": "3 bullet points max"
    }}
    
    Job Description: {jd[:3000]}
    Resume: {resume_text[:3000]}
    """
    
    try:
        response = model.generate_content(prompt)
        
        # Extract JSON string from response
        json_str = response.text.strip().replace('```json', '').replace('```', '').strip()
        
        # Parse JSON safely
        return json.loads(json_str)
        
    except json.JSONDecodeError as e:
        st.error(f"Failed to parse JSON: {str(e)}\nRaw response: {response.text}")
        return {
            "score": 0,
            "matches": [],
            "gaps": [],
            "summary": "Analysis failed - invalid response format"
        }
    except Exception as e:
        st.error(f"Analysis failed: {str(e)}")
        return None

def generate_email(candidate, jd):
    prompt = f"""
    Write a professional outreach email for this candidate:
    Name: {candidate.get('name', 'Candidate')}
    Score: {candidate['score']}/100
    Matches: {', '.join(candidate['matches'])}
    
    Job: {jd}
    """
    return model.generate_content(prompt).text

# --- UI Flow ---
st.set_page_config(layout="wide", page_title="RecruitAI Pro")
st.title("🚀 RecruitAI Pro - End-to-End Hiring Assistant")

# --- Step 1: Upload JD ---
st.subheader("📋 1. Upload Job Description")
jd_file = st.file_uploader("Upload JD (PDF/DOCX)", type=["pdf","docx"], key="jd_uploader")
if jd_file:
    st.session_state.jd_text = extract_text(jd_file)
    if st.checkbox("Show Parsed JD Text"):
        st.text_area("Job Description Text", st.session_state.jd_text[:2000] + "...", height=200)

# --- Step 2: Batch Resume Processing ---
if st.session_state.jd_text:
    st.subheader("📚 2. Upload Resumes (Batch)")
    resumes = st.file_uploader("Upload Multiple Resumes", 
                             type=["pdf","docx","txt"], 
                             accept_multiple_files=True,
                             key="resume_uploader")
    
    if resumes and st.button("Analyze Batch", key="analyze_btn"):
        st.session_state.candidates = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for i, resume in enumerate(resumes):
            status_text.text(f"Processing {i+1}/{len(resumes)}: {resume.name}")
            progress_bar.progress((i+1)/len(resumes))
            
            text = extract_text(resume)
            analysis = analyze_resume(st.session_state.jd_text, text)
            if analysis:
                analysis['name'] = resume.name.split('.')[0]
                analysis['resume'] = text[:500] + "..."
                st.session_state.candidates.append(analysis)
        
        status_text.success(f"Completed analysis of {len(resumes)} resumes!")
        progress_bar.empty()

# --- Step 3: Results Dashboard ---
if st.session_state.candidates:
    st.divider()
    st.subheader("📊 3. Candidate Evaluation Dashboard")
    
    # Convert to DataFrame
    df = pd.DataFrame(st.session_state.candidates)
    df = df[['name','score','matches','gaps']]
    
    # Interactive table
    st.dataframe(df.sort_values('score', ascending=False), 
                use_container_width=True,
                column_config={
                    "score": st.column_config.ProgressColumn(
                        "Match Score",
                        help="JD match percentage",
                        format="%d%%",
                        min_value=0,
                        max_value=100,
                    )
                })
    
    # Candidate drill-down
    selected = st.selectbox("View details", df['name'], key="candidate_select")
    candidate = next(c for c in st.session_state.candidates if c['name'] == selected)
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"### {selected} ({candidate['score']}/100)")
        st.markdown("**✅ Matches:** " + ", ".join(candidate['matches']))
        st.markdown("**⚠️ Gaps:** " + ", ".join(candidate['gaps']))
        st.text_area("Summary", candidate['summary'], height=150, key="summary_area")
    
    with col2:
        st.markdown("### ✉️ Outreach Tools")
        if st.button("Generate Email Template", key="email_btn"):
            st.session_state.email = generate_email(candidate, st.session_state.jd_text)
        if st.session_state.email:
            st.text_area("Email Draft", st.session_state.email, height=200, key="email_draft")
            st.download_button("Download Email", st.session_state.email, file_name=f"email_{selected}.txt", key="email_download")

# --- Step 4: Export ---
if st.session_state.candidates:
    st.divider()
    st.subheader("📤 4. Export Results")
    
    # Excel Export
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False)
    
    st.download_button(
        label="📥 Export to Excel",
        data=excel_buffer.getvalue(),
        file_name=f"candidate_report_{datetime.now().date()}.xlsx",
        mime="application/vnd.ms-excel",
        key="excel_export"
    )
    
    # ATS Integration Placeholder
    st.markdown("### 🔗 ATS Integration")
    st.selectbox("Select ATS", ["Greenhouse", "Lever", "Workday"], key="ats_select")
    st.button("Sync Selected Candidates", key="ats_sync")

# --- Debug Section ---
if st.checkbox("Show Debug Info"):
    st.write(st.session_state)
