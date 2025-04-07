import re
import streamlit as st
import google.generativeai as genai
import docx2txt
import PyPDF2
import pandas as pd
from datetime import datetime

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

# --- Enhanced Parser Functions ---
def extract_personal_details(text):
    details = {
        "name": "N/A",
        "email": "N/A",
        "phone": "N/A",
        "linkedin": "N/A",
        "education": "N/A"
    }
    
    # Name (First 2 lines usually contain name)
    name_match = re.search(r"^(.*?)\n", text[:200])
    if name_match:
        details["name"] = name_match.group(1).strip()
    
    # Email
    email_match = re.search(r'[\w\.-]+@[\w\.-]+', text)
    if email_match:
        details["email"] = email_match.group(0)
    
    # Phone (US/International formats)
    phone_match = re.search(r'(\+?\d{1,3}[-\.\s]?)?\(?\d{3}\)?[-\.\s]?\d{3}[-\.\s]?\d{4}', text)
    if phone_match:
        details["phone"] = phone_match.group(0)
    
    # LinkedIn
    linkedin_match = re.search(r'(https?://)?(www\.)?linkedin\.com/in/[^\s]+', text)
    if linkedin_match:
        details["linkedin"] = linkedin_match.group(0)
    
    # Education (Extract most prominent university)
    education_match = re.search(r'(Education|Academic Background)[\s\S]*?(University|College|Institute)[^\n]+', text, re.IGNORECASE)
    if education_match:
        details["education"] = education_match.group(0).replace("\n", " ").strip()[:100]
    
    return details

def extract_text(file):
    if file.type == "application/pdf":
        reader = PyPDF2.PdfReader(file)
        text = " ".join(page.extract_text() for page in reader.pages if page.extract_text())
    elif file.type.endswith('document'):
        text = docx2txt.process(file)
    else:
        text = file.read().decode()
    
    personal_details = extract_personal_details(text)
    return text, personal_details

# --- Analysis Function ---
def analyze_resume(jd, resume_text):
    prompt = f"""
    Analyze this resume against the job description:
    
    Job Requirements:
    {jd}
    
    Resume:
    {resume_text}
    
    Return JSON with:
    - "score" (0-100)
    - "matches" (top 3 skills)
    - "gaps" (top 3 missing)
    - "summary" (3 bullet points)
    """
    try:
        response = model.generate_content(prompt)
        return eval(response.text)
    except:
        return {
            "score": 0,
            "matches": [],
            "gaps": [],
            "summary": "Analysis failed"
        }

# --- UI Flow ---
st.set_page_config(layout="wide", page_title="RecruitAI Pro")
st.title("🚀 RecruitAI Pro - Enhanced Parser")

# --- Step 1: Upload JD ---
st.subheader("📋 1. Upload Job Description")
jd_file = st.file_uploader("Upload JD (PDF/DOCX)", type=["pdf","docx"], key="jd_uploader")
if jd_file:
    st.session_state.jd_text, _ = extract_text(jd_file)
    with st.expander("View Parsed JD"):
        st.write(st.session_state.jd_text[:2000] + "...")

# --- Step 2: Batch Resume Processing ---
if st.session_state.jd_text:
    st.subheader("📚 2. Upload Resumes (Batch)")
    resumes = st.file_uploader("Upload Multiple Resumes", type=["pdf","docx","txt"], accept_multiple_files=True)
    
    if resumes and st.button("Analyze Batch"):
        st.session_state.candidates = []
        progress_bar = st.progress(0)
        
        for i, resume in enumerate(resumes):
            progress_bar.progress((i+1)/len(resumes))
            text, details = extract_text(resume)
            analysis = analyze_resume(st.session_state.jd_text, text)
            
            if analysis:
                candidate = {
                    **details,
                    **analysis,
                    "resume_text": text[:500] + "..."
                }
                st.session_state.candidates.append(candidate)

# --- Step 3: Enhanced Dashboard ---
if st.session_state.candidates:
    st.divider()
    st.subheader("👥 Candidate Evaluation Dashboard")
    
    # DataFrame with all details
    df = pd.DataFrame(st.session_state.candidates)
    df = df[['name', 'email', 'phone', 'education', 'score', 'matches', 'gaps']]
    
    # Interactive table
    st.dataframe(
        df.sort_values('score', ascending=False),
        column_config={
            "score": st.column_config.ProgressColumn(
                "Match Score",
                format="%d%%",
                min_value=0,
                max_value=100,
            ),
            "email": st.column_config.LinkColumn("Email"),
            "linkedin": st.column_config.LinkColumn("LinkedIn")
        },
        hide_index=True,
        use_container_width=True
    )
    
    # Candidate Details Expandable Section
    selected_name = st.selectbox("View full details", df['name'])
    candidate = next(c for c in st.session_state.candidates if c['name'] == selected_name)
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"### 📝 {candidate['name']}")
        st.markdown(f"**📧 Email:** {candidate['email']}")
        st.markdown(f"**📞 Phone:** {candidate['phone']}")
        st.markdown(f"**🎓 Education:** {candidate['education']}")
        if candidate['linkedin'] != "N/A":
            st.markdown(f"**🔗 LinkedIn:** [View Profile]({candidate['linkedin']})")
        
    with col2:
        st.markdown(f"### ⚡ Match Score: {candidate['score']}/100")
        st.markdown("**✅ Top Matches:**")
        for match in candidate['matches']:
            st.markdown(f"- {match}")
        
        st.markdown("**⚠️ Key Gaps:**")
        for gap in candidate['gaps']:
            st.markdown(f"- {gap}")
    
    st.divider()
    st.markdown("**📄 Resume Excerpt:**")
    st.text(candidate['resume_text'])
