from fastapi import FastAPI, UploadFile, File, HTTPException, Form 
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import os
import json
import re
import numpy as np
from numpy.linalg import norm
import base64
from io import BytesIO
import tempfile
import shutil
import uuid
import plotly.graph_objects as go
import logging
import time
from pathlib import Path
from datetime import datetime

# Document processing
from PyPDF2 import PdfReader
import docx

# Updated Google GenAI import
from google import genai

from dotenv import load_dotenv
import sounddevice as sd
import soundfile as sf

# For vectorization
from gensim.models.doc2vec import Doc2Vec

# Speech recognition
import speech_recognition as sr

from contextlib import asynccontextmanager

# PDF Generation
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.pdfgen import canvas

# Initialize logging first
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables 
load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")

# Initialize the new genai client
genai_client = None
if API_KEY:
    genai_client = genai.Client(api_key=API_KEY)
    logger.info("Google GenAI client configured successfully")
else:
    logger.warning("GOOGLE_API_KEY not found in environment or .env file!")

# Define directories
TEMP_DIR = "temp_files"
RECORDINGS_DIR = Path("recordings")
VIDEOS_DIR = Path("videos")
PROFILES_DIR = Path("profiles")
REPORTS_DIR = Path("reports")

# Cache the Doc2Vec model
DOC2VEC_MODEL = None

# Storage for interview evaluations (for PDF report generation)
INTERVIEW_EVALUATIONS = {}

# Setup the lifespan events
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize directories and load models
    logger.info("Starting application...")
    
    # Ensure all required directories exist
    os.makedirs(TEMP_DIR, exist_ok=True)
    RECORDINGS_DIR.mkdir(exist_ok=True)
    VIDEOS_DIR.mkdir(exist_ok=True)
    PROFILES_DIR.mkdir(exist_ok=True)
    REPORTS_DIR.mkdir(exist_ok=True)
    
    # Check Gemini API key
    if not API_KEY:
        logger.warning("GOOGLE_API_KEY not found! Please set it in your environment or .env file")
    else:
        logger.info("Google API key configured successfully")
    
    logger.info("Application startup complete")
    yield
    
    # Shutdown: Cleanup temp files
    logger.info("Shutting down application...")
    
    for temp_file in os.listdir(TEMP_DIR):
        try:
            os.remove(os.path.join(TEMP_DIR, temp_file))
        except Exception as e:
            logger.error(f"Failed to clean up temp file {temp_file}: {str(e)}")
    
    logger.info("Application shutdown complete")

# Create FastAPI app
app = FastAPI(
    title="Resume Analyzer and Interview API",
    lifespan=lifespan,
    description="API for resume analysis, job matching, interview questions, and video analysis",
    version="2.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Define models
class ResumeAnalysisResponse(BaseModel):
    summary: dict
    skills: List[str]

class JobMatchRequest(BaseModel):
    resume_summary: str
    job_description: str

class JobMatchResponse(BaseModel):
    match_percentage: float
    recommendation: str

class InterviewQuestionRequest(BaseModel):
    job_description: str
    role: str  # NEW: User specifies role
    num_questions: Optional[int] = 10

class InterviewQuestion(BaseModel):
    question: str
    category: str
    difficulty: str  # NEW: "easy", "medium", "hard"

class InterviewQuestionsResponse(BaseModel):
    questions: List[InterviewQuestion]

class InterviewResponseConfig(BaseModel):
    question: str
    max_duration: int = 60
    sample_rate: int = 44100
    channels: int = 1

class InterviewEvaluationResult(BaseModel):
    question: str
    question_difficulty: str  # NEW
    transcription: str
    evaluation: dict
    relevance_score: float
    clarity_score: float
    confidence_score: float
    keyword_usage_score: float  # NEW
    overall_score: float
    session_id: str  # NEW: For tracking

class VideoTimestamp(BaseModel):
    timestamp: str
    text: str
    visuals: str
    emotion: str

class VideoAnalysisResult(BaseModel):
    timestamps: List[VideoTimestamp]
    overall_emotion: str
    transcription: str
    confidence_score: float
    clarity_score: float
    relevance_score: float
    vocal_quality_score: float
    overall_score: float

class SkillGapRequest(BaseModel):
    resume_summary: str
    job_description: str

class SkillGapResponse(BaseModel):
    missing_skills: List[str]
    recommendations: List[str]
    additional_training: List[str]

class ProfileUpdateRequest(BaseModel):
    user_id: str
    age: Optional[int] = None
    years_of_experience: Optional[float] = None
    notice_period_days: Optional[int] = None
    current_ctc: Optional[float] = None
    expected_ctc: Optional[float] = None
    preferred_location: Optional[str] = None
    willing_to_relocate: Optional[bool] = None

class ProfileUpdateResponse(BaseModel):
    user_id: str
    profile: Dict[str, Any]
    message: str

class PDFReportRequest(BaseModel):
    session_id: str
    user_name: str
    role: str
    resume_summary: Optional[str] = None

# Helper functions
def load_doc2vec_model():
    """Load and cache the Doc2Vec model"""
    global DOC2VEC_MODEL
    if DOC2VEC_MODEL is None:
        logger.info("Loading Doc2Vec model...")
        start_time = time.time()
        try:
            DOC2VEC_MODEL = Doc2Vec.load(os.path.join(os.getcwd(), "cv_job_maching.model"))
            logger.info(f"Model loaded in {time.time() - start_time:.2f} seconds")
        except Exception as e:
            logger.error(f"Error loading Doc2Vec model: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to load the Doc2Vec model")
    return DOC2VEC_MODEL

def process_file(file_path):
    """Extract text from uploaded files"""
    file_extension = os.path.splitext(file_path)[1].lower()
    
    if file_extension == '.pdf':
        reader = PdfReader(file_path)
        return " ".join([page.extract_text() for page in reader.pages])
    
    elif file_extension in ['.docx', '.doc']:
        doc = docx.Document(file_path)
        return " ".join([para.text for para in doc.paragraphs])
    
    elif file_extension == '.txt':
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    else:
        raise ValueError(f"Unsupported file format: {file_extension}")

def analyze_resume(resume_text):
    """Analyze resume using Gemini with updated API"""
    prompt = f"""
    Analyze this resume and extract key information:
    
    {resume_text}
    
    Return ONLY a valid JSON object with the following structure:
    {{
        "name": "Full name of the candidate",
        "email": "Email address",
        "phone": "Phone number",
        "summary": "Brief professional summary",
        "experience_years": 0,
        "key_skills": ["skill1", "skill2", "skill3"],
        "education": ["degree1", "degree2"],
        "work_experience": [
            {{"company": "Company Name", "role": "Job Title", "duration": "Years"}}
        ],
        "certifications": ["cert1", "cert2"]
    }}
    
    Ensure the response is strictly valid JSON format with no additional text.
    """
    
    response = genai_client.models.generate_content(
        model="gemini-2.0-flash-exp",
        contents=prompt
    )
    
    response_text = response.text
    
    try:
        json_match = re.search(r'({[\s\S]*})', response_text)
        if json_match:
            response_text = json_match.group(1)
        
        response_text = re.sub(r'```json|```', '', response_text).strip()
        return json.loads(response_text)
    except Exception as e:
        logger.error(f"Failed to parse resume analysis: {str(e)}")
        raise ValueError(f"Failed to parse resume: {str(e)}")

def clean_text(text):
    """Clean text for vectorization"""
    text = re.sub(r'[^a-zA-Z0-9\s]', '', text)
    return text.lower()

def calculate_match(resume_summary, job_description):
    """Calculate match percentage between resume and job description"""
    try:
        start_time = time.time()
        model = load_doc2vec_model()
        
        resume_processed = clean_text(resume_summary)
        jd_processed = clean_text(job_description)
        
        v1 = model.infer_vector(resume_processed.split())
        v2 = model.infer_vector(jd_processed.split())
        
        dot_product = np.dot(v1, v2)
        norm_product = norm(v1) * norm(v2)
        similarity = 100 * (dot_product / norm_product)
        
        logger.info(f"Matching completed in {time.time() - start_time:.2f} seconds")
        return round(similarity, 2)
    except Exception as e:
        logger.error(f"Match calculation error: {str(e)}")
        raise ValueError(f"Match calculation failed: {str(e)}")

def get_match_recommendation(match_percentage):
    """Get recommendation based on match percentage"""
    if match_percentage < 50:
        return "Low chance, need to modify your CV!"
    elif 50 <= match_percentage < 70:
        return "Good chance but you can improve further!"
    else:
        return "Excellent! You can submit your CV."

def generate_interview_questions(job_description, role, num_questions=10):
    """
    Generate adaptive interview questions with difficulty levels
    Mix of Tech (60%) and HR (40%) questions
    """
    # Calculate question distribution
    tech_questions = int(num_questions * 0.6)  # 60% tech
    hr_questions = num_questions - tech_questions  # 40% HR
    
    # Difficulty distribution: 30% easy, 40% medium, 30% hard
    easy_count = int(num_questions * 0.3)
    medium_count = int(num_questions * 0.4)
    hard_count = num_questions - easy_count - medium_count
    
    prompt = f"""
    Generate {num_questions} interview questions for the role: {role}
    Based on this job description: {job_description}
    
    Requirements:
    1. Generate {tech_questions} TECHNICAL questions and {hr_questions} HR/BEHAVIORAL questions
    2. Difficulty distribution:
       - {easy_count} EASY questions (foundational concepts, basic scenarios)
       - {medium_count} MEDIUM questions (practical application, moderate complexity)
       - {hard_count} HARD questions (advanced concepts, complex scenarios, problem-solving)
    
    3. TECHNICAL questions should cover:
       - Programming/coding concepts
       - System design
       - Problem-solving
       - Technical tools and frameworks mentioned in job description
    
    4. HR/BEHAVIORAL questions should cover:
       - Behavioral scenarios (STAR method)
       - Cultural fit
       - Motivation and career goals
       - Team collaboration
       - Conflict resolution
    
    Return ONLY a valid JSON array with this exact structure:
    [
        {{
            "question": "Your question here",
            "category": "technical" or "hr",
            "difficulty": "easy" or "medium" or "hard"
        }}
    ]
    
    IMPORTANT: 
    - Start with EASY questions, then MEDIUM, then HARD (sorted by difficulty)
    - Do not include any additional text, only return the valid JSON array
    - Ensure exactly {num_questions} questions total
    """
    
    response = genai_client.models.generate_content(
        model="gemini-2.0-flash-exp",
        contents=prompt
    )
    
    response_text = response.text
    
    try:
        json_match = re.search(r'(\[.*\])', response_text.replace('\n', ' '), re.DOTALL)
        if json_match:
            questions = json.loads(json_match.group(0))
        else:
            questions = json.loads(response_text)
        
        # Ensure questions are sorted by difficulty
        difficulty_order = {"easy": 1, "medium": 2, "hard": 3}
        questions.sort(key=lambda x: difficulty_order.get(x.get('difficulty', 'medium'), 2))
        
        return questions
    except Exception as e:
        logger.error(f"Failed to parse questions: {str(e)}")
        logger.error(f"Raw response: {response_text}")
        raise ValueError(f"Failed to parse questions: {str(e)}")

def process_video(video_file):
    """Process video file and return analysis"""
    with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp_file:
        tmp_file.write(video_file.read())
        video_path = tmp_file.name

    try:
        # Upload video to Gemini
        prompt = """
        Analyze this video resume and evaluate it as if you were an HR professional.
        
        Provide a detailed analysis including:
        1. Timestamps with key moments
        2. Overall emotional tone
        3. Full transcription
        4. Confidence score (0-1)
        5. Clarity score (0-1)
        6. Relevance score (0-1)
        7. Vocal quality score (0-1)
        8. Overall score (average of above)
        
        Return ONLY a valid JSON object with this structure:
        {{
            "timestamps": [
                {{"timestamp": "0:00", "text": "...", "visuals": "...", "emotion": "..."}}
            ],
            "overall_emotion": "professional/nervous/confident",
            "transcription": "Full transcription...",
            "confidence_score": 0.8,
            "clarity_score": 0.7,
            "relevance_score": 0.9,
            "vocal_quality_score": 0.85,
            "overall_score": 0.8
        }}
        """
        
        # Read video as base64
        with open(video_path, 'rb') as f:
            video_data = base64.b64encode(f.read()).decode('utf-8')
        
        response = genai_client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=[
                {"text": prompt},
                {"inline_data": {"mime_type": "video/mp4", "data": video_data}}
            ]
        )
        
        response_text = response.text
        
        try:
            json_match = re.search(r'({[\s\S]*})', response_text)
            if json_match:
                response_text = json_match.group(1)
            
            response_text = re.sub(r'```json|```', '', response_text).strip()
            analysis = json.loads(response_text)
            logger.info("Successfully parsed video analysis JSON")
            return analysis
            
        except Exception as e:
            logger.error(f"Failed to parse video analysis: {str(e)}")
            logger.error(f"Raw response: {response_text[:500]}...")
            raise ValueError(f"Failed to parse video analysis: {str(e)}")
    finally:
        os.unlink(video_path)

def analyze_skill_gap(resume_summary, job_description):
    """Analyze skill gap between resume and job description"""
    prompt = f"""
    Compare this resume summary:
    
    {resume_summary}
    
    With this job description:
    
    {job_description}
    
    Identify the skill gaps and provide recommendations for the candidate.
    
    Return ONLY a valid JSON object with the following structure:
    {{
        "missing_skills": ["List of skills mentioned in the job description but not found in the resume"],
        "recommendations": ["Specific recommendations for how the candidate can address the skill gaps"],
        "additional_training": ["Suggested courses, certifications, or experiences that would help bridge the gaps"]
    }}
    
    Ensure the response is strictly valid JSON format with no additional text.
    """
    
    response = genai_client.models.generate_content(
        model="gemini-2.0-flash-exp",
        contents=prompt
    )
    
    response_text = response.text
    
    try:
        json_match = re.search(r'({[\s\S]*})', response_text)
        if json_match:
            response_text = json_match.group(1)
        
        response_text = re.sub(r'```json|```', '', response_text).strip()
        analysis = json.loads(response_text)
        logger.info("Successfully parsed skill gap analysis JSON")
        return analysis
        
    except Exception as e:
        logger.error(f"Failed to parse skill gap analysis: {str(e)}")
        logger.error(f"Raw response: {response_text[:500]}...")
        raise ValueError(f"Failed to parse skill gap analysis: {str(e)}")

def save_profile(request: ProfileUpdateRequest):
    """Save profile data to JSON file"""
    profile_data = {
        "age": request.age,
        "years_of_experience": request.years_of_experience,
        "notice_period_days": request.notice_period_days,
        "current_ctc": request.current_ctc,
        "expected_ctc": request.expected_ctc,
        "preferred_location": request.preferred_location,
        "willing_to_relocate": request.willing_to_relocate,
        "updated_at": datetime.now().isoformat()
    }
    
    profile_path = PROFILES_DIR / f"{request.user_id}.json"
    
    with open(profile_path, 'w') as f:
        json.dump(profile_data, f, indent=2)
    
    return profile_data

def get_profile(user_id):
    """Get profile data from JSON file"""
    profile_path = PROFILES_DIR / f"{user_id}.json"
    
    if not profile_path.exists():
        return {}
    
    with open(profile_path, 'r') as f:
        return json.load(f)

def extract_keywords_from_question(question, job_description):
    """Extract expected keywords from question using AI"""
    prompt = f"""
    Given this interview question: "{question}"
    And this job description context: "{job_description[:500]}..."
    
    Extract 5-10 key technical terms or concepts that should ideally be mentioned in a good answer.
    
    Return ONLY a JSON array of keywords: ["keyword1", "keyword2", ...]
    """
    
    try:
        response = genai_client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=prompt
        )
        
        response_text = response.text
        json_match = re.search(r'(\[.*\])', response_text.replace('\n', ' '), re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
        return []
    except Exception as e:
        logger.error(f"Failed to extract keywords: {str(e)}")
        return []

def calculate_keyword_usage_score(transcription, keywords):
    """Calculate how many expected keywords were used"""
    if not keywords:
        return 0.5  # Neutral score if no keywords available
    
    transcription_lower = transcription.lower()
    matches = sum(1 for keyword in keywords if keyword.lower() in transcription_lower)
    return min(matches / len(keywords), 1.0)

def get_difficulty_threshold(difficulty):
    """Get scoring threshold based on difficulty"""
    thresholds = {
        "easy": {"pass": 0.6, "good": 0.75, "excellent": 0.85},
        "medium": {"pass": 0.65, "good": 0.78, "excellent": 0.88},
        "hard": {"pass": 0.70, "good": 0.80, "excellent": 0.90}
    }
    return thresholds.get(difficulty, thresholds["medium"])

def generate_pdf_report(session_id, user_name, role, resume_summary=None):
    """Generate comprehensive PDF report for interview session"""
    
    # Get all evaluations for this session
    evaluations = INTERVIEW_EVALUATIONS.get(session_id, [])
    
    if not evaluations:
        raise ValueError(f"No evaluations found for session {session_id}")
    
    # Create PDF
    pdf_filename = f"interview_report_{session_id}_{int(time.time())}.pdf"
    pdf_path = REPORTS_DIR / pdf_filename
    
    doc = SimpleDocTemplate(str(pdf_path), pagesize=letter)
    story = []
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1a237e'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#283593'),
        spaceAfter=12,
        spaceBefore=12
    )
    
    # Title
    story.append(Paragraph("Interview Performance Report", title_style))
    story.append(Spacer(1, 0.3*inch))
    
    # Candidate Info
    story.append(Paragraph("Candidate Information", heading_style))
    candidate_data = [
        ['Name:', user_name],
        ['Role:', role],
        ['Date:', datetime.now().strftime('%Y-%m-%d %H:%M')],
        ['Session ID:', session_id]
    ]
    candidate_table = Table(candidate_data, colWidths=[2*inch, 4*inch])
    candidate_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e8eaf6')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
    ]))
    story.append(candidate_table)
    story.append(Spacer(1, 0.3*inch))
    
    # Overall Performance Summary
    story.append(Paragraph("Overall Performance Summary", heading_style))
    
    avg_relevance = sum(e['relevance_score'] for e in evaluations) / len(evaluations)
    avg_clarity = sum(e['clarity_score'] for e in evaluations) / len(evaluations)
    avg_confidence = sum(e['confidence_score'] for e in evaluations) / len(evaluations)
    avg_keyword = sum(e.get('keyword_usage_score', 0.5) for e in evaluations) / len(evaluations)
    avg_overall = sum(e['overall_score'] for e in evaluations) / len(evaluations)
    
    summary_data = [
        ['Metric', 'Score', 'Rating'],
        ['Relevance', f'{avg_relevance:.2f}', get_rating(avg_relevance)],
        ['Clarity', f'{avg_clarity:.2f}', get_rating(avg_clarity)],
        ['Confidence', f'{avg_confidence:.2f}', get_rating(avg_confidence)],
        ['Keyword Usage', f'{avg_keyword:.2f}', get_rating(avg_keyword)],
        ['Overall Score', f'{avg_overall:.2f}', get_rating(avg_overall)]
    ]
    
    summary_table = Table(summary_data, colWidths=[2.5*inch, 1.5*inch, 1.5*inch])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3f51b5')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 0.3*inch))
    
    # Resume Analysis (if provided)
    if resume_summary:
        story.append(Paragraph("Resume Analysis", heading_style))
        resume_text = Paragraph(resume_summary[:500] + "...", styles['BodyText'])
        story.append(resume_text)
        story.append(Spacer(1, 0.2*inch))
    
    # Question-by-Question Analysis
    story.append(PageBreak())
    story.append(Paragraph("Detailed Question Analysis", heading_style))
    
    for idx, evaluation in enumerate(evaluations, 1):
        story.append(Paragraph(f"Question {idx} ({evaluation['question_difficulty'].upper()})", 
                              ParagraphStyle('QuestionHeading', parent=styles['Heading3'], 
                                           textColor=colors.HexColor('#5c6bc0'))))
        
        story.append(Paragraph(f"<b>Q:</b> {evaluation['question']}", styles['BodyText']))
        story.append(Spacer(1, 0.1*inch))
        
        # Scores table for this question
        question_scores = [
            ['Metric', 'Score'],
            ['Relevance', f"{evaluation['relevance_score']:.2f}"],
            ['Clarity', f"{evaluation['clarity_score']:.2f}"],
            ['Confidence', f"{evaluation['confidence_score']:.2f}"],
            ['Keyword Usage', f"{evaluation.get('keyword_usage_score', 0.5):.2f}"],
            ['Overall', f"{evaluation['overall_score']:.2f}"]
        ]
        
        question_table = Table(question_scores, colWidths=[2*inch, 1.5*inch])
        question_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#7986cb')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
        ]))
        story.append(question_table)
        story.append(Spacer(1, 0.15*inch))
        
        # Transcription
        story.append(Paragraph("<b>Your Response:</b>", styles['BodyText']))
        transcription_text = evaluation.get('transcription', 'No transcription available')
        story.append(Paragraph(transcription_text, styles['BodyText']))
        story.append(Spacer(1, 0.15*inch))
        
        # Feedback
        feedback = evaluation.get('evaluation', {})
        
        if feedback.get('strengths'):
            story.append(Paragraph("<b>Strengths:</b>", styles['BodyText']))
            for strength in feedback['strengths']:
                story.append(Paragraph(f"• {strength}", styles['BodyText']))
            story.append(Spacer(1, 0.1*inch))
        
        if feedback.get('improvements'):
            story.append(Paragraph("<b>Areas for Improvement:</b>", styles['BodyText']))
            for improvement in feedback['improvements']:
                story.append(Paragraph(f"• {improvement}", styles['BodyText']))
            story.append(Spacer(1, 0.1*inch))
        
        story.append(Spacer(1, 0.2*inch))
    
    # Final Recommendations
    story.append(PageBreak())
    story.append(Paragraph("Final Recommendations", heading_style))
    
    recommendations = generate_final_recommendations(avg_overall, evaluations)
    for rec in recommendations:
        story.append(Paragraph(f"• {rec}", styles['BodyText']))
        story.append(Spacer(1, 0.1*inch))
    
    # Build PDF
    doc.build(story)
    logger.info(f"PDF report generated: {pdf_path}")
    
    return pdf_filename

def get_rating(score):
    """Convert score to rating"""
    if score >= 0.85:
        return "Excellent"
    elif score >= 0.75:
        return "Good"
    elif score >= 0.65:
        return "Average"
    else:
        return "Needs Improvement"

def generate_final_recommendations(overall_score, evaluations):
    """Generate personalized recommendations based on performance"""
    recommendations = []
    
    # Analyze weak areas
    avg_relevance = sum(e['relevance_score'] for e in evaluations) / len(evaluations)
    avg_clarity = sum(e['clarity_score'] for e in evaluations) / len(evaluations)
    avg_confidence = sum(e['confidence_score'] for e in evaluations) / len(evaluations)
    avg_keyword = sum(e.get('keyword_usage_score', 0.5) for e in evaluations) / len(evaluations)
    
    if avg_relevance < 0.7:
        recommendations.append("Focus on directly answering the question asked. Practice the STAR method for behavioral questions.")
    
    if avg_clarity < 0.7:
        recommendations.append("Work on structuring your answers more clearly. Use frameworks like 'First, Second, Finally' to organize thoughts.")
    
    if avg_confidence < 0.7:
        recommendations.append("Practice mock interviews to build confidence. Record yourself and review your tone and pace.")
    
    if avg_keyword < 0.6:
        recommendations.append("Study technical terminology related to the role. Use industry-specific keywords naturally in your responses.")
    
    # Performance-based recommendations
    if overall_score >= 0.85:
        recommendations.append("Excellent performance! You're well-prepared for this role. Keep practicing to maintain consistency.")
    elif overall_score >= 0.75:
        recommendations.append("Good performance overall. Focus on the specific areas mentioned above to reach excellence.")
    else:
        recommendations.append("Consider more preparation and practice. Review common interview questions and practice with a mentor.")
    
    # Question difficulty analysis
    hard_questions = [e for e in evaluations if e.get('question_difficulty') == 'hard']
    if hard_questions:
        avg_hard_score = sum(e['overall_score'] for e in hard_questions) / len(hard_questions)
        if avg_hard_score < 0.65:
            recommendations.append("Work on complex problem-solving and advanced concepts. Take online courses or work on challenging projects.")
    
    return recommendations if recommendations else ["Keep up the good work and continue practicing!"]

# API Endpoints
@app.post("/api/resume/upload", response_model=ResumeAnalysisResponse)
async def upload_resume(file: UploadFile = File(...)):
    """Upload and analyze resume"""
    temp_file_path = os.path.join(TEMP_DIR, f"temp_{uuid.uuid4()}{os.path.splitext(file.filename)[1]}")
    
    try:
        with open(temp_file_path, "wb") as temp_file:
            shutil.copyfileobj(file.file, temp_file)
        
        resume_text = process_file(temp_file_path)
        analysis_json = analyze_resume(resume_text)
        
        return {
            "summary": analysis_json,
            "skills": analysis_json.get("key_skills", [])
        }
    
    except Exception as e:
        logger.error(f"Resume upload error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

@app.post("/api/job/match", response_model=JobMatchResponse)
async def match_job(request: JobMatchRequest):
    """Match resume summary with job description"""
    try:
        start_time = time.time()
        match_percentage = calculate_match(request.resume_summary, request.job_description)
        
        logger.info(f"Total job matching time: {time.time() - start_time:.2f} seconds")
        
        return {
            "match_percentage": match_percentage,
            "recommendation": get_match_recommendation(match_percentage),
        }
    
    except Exception as e:
        logger.error(f"Job matching error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/interview/questions", response_model=InterviewQuestionsResponse)
async def create_interview(request: InterviewQuestionRequest):
    """
    Generate adaptive interview questions with difficulty levels
    Now includes role parameter and generates both Tech + HR questions
    """
    try:
        questions = generate_interview_questions(
            request.job_description, 
            request.role,
            request.num_questions
        )
        return {"questions": questions}
    except Exception as e:
        logger.error(f"Generate interview questions error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/evaluate-interview-response/", response_model=InterviewEvaluationResult)
async def evaluate_interview_response(
    question: str = Form(...),
    question_difficulty: str = Form("medium"),  # NEW
    question_category: str = Form("technical"),  # NEW
    job_description: str = Form(""),  # NEW: for keyword extraction
    audio_file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),  # NEW: for tracking
    max_duration: int = Form(60)
):
    """
    Evaluate interview response with adaptive scoring based on difficulty
    Includes keyword usage analysis
    """
    temp_audio_path = RECORDINGS_DIR / f"response_{int(time.time())}.wav"
    
    # Generate session_id if not provided
    if not session_id:
        session_id = str(uuid.uuid4())
    
    try:
        # Save uploaded audio
        contents = await audio_file.read()
        with open(temp_audio_path, "wb") as f:
            f.write(contents)

        # Extract expected keywords
        expected_keywords = extract_keywords_from_question(question, job_description)
        logger.info(f"Expected keywords: {expected_keywords}")
        
        # Get difficulty thresholds
        thresholds = get_difficulty_threshold(question_difficulty)
        
        # Evaluation prompt with difficulty context
        evaluation_prompt = f"""
        Your task is to evaluate an interview response to this {question_difficulty.upper()} difficulty {question_category.upper()} question: "{question}"
        
        Difficulty Level: {question_difficulty.upper()}
        Expected Standards for {question_difficulty}:
        - Pass threshold: {thresholds['pass']}
        - Good threshold: {thresholds['good']}
        - Excellent threshold: {thresholds['excellent']}
        
        Expected keywords/concepts: {', '.join(expected_keywords)}
        
        IMPORTANT: You must return ONLY a valid JSON object with no additional text, markdown formatting, or code blocks.
        Be appropriately strict based on the difficulty level.
        
        The JSON MUST follow this exact structure:
        {{
            "transcription": "Full transcription of the audio",
            "relevance": 0.8,  // Content relevance to the question (0-1)
            "clarity": 0.7,    // Clarity of expression (0-1)
            "confidence": 0.9, // Perceived confidence (0-1)
            "overall_score": 0.8, // Average of relevance, clarity, and confidence
            "feedback": {{
                "strengths": ["List specific strengths", "Add at least 2-3 points"],
                "improvements": ["List specific areas for improvement", "Add at least 2-3 points"]
            }}
        }}
        
        DO NOT include any explanations, introductions, or additional text outside the JSON object.
        """
        
        # Read audio file as base64
        with open(temp_audio_path, 'rb') as f:
            audio_data = base64.b64encode(f.read()).decode('utf-8')
        
        # Get evaluation from Gemini
        response = genai_client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=[
                {"text": evaluation_prompt},
                {"inline_data": {"mime_type": "audio/wav", "data": audio_data}}
            ]
        )
        
        response_text = response.text
        logger.info(f"Gemini response received, length: {len(response_text)}")
        
        # Parse response
        try:
            json_match = re.search(r'({[\s\S]*})', response_text)
            if json_match:
                response_text = json_match.group(1)
                
            evaluation = json.loads(response_text)
            logger.info("Successfully parsed JSON evaluation")
            
            # Calculate keyword usage score
            transcription = evaluation.get("transcription", "")
            keyword_score = calculate_keyword_usage_score(transcription, expected_keywords)
            
            # Adjust overall score to include keyword usage
            original_overall = evaluation.get("overall_score", 0)
            adjusted_overall = (original_overall * 0.75) + (keyword_score * 0.25)
            
            evaluation["keyword_usage_score"] = keyword_score
            evaluation["overall_score"] = adjusted_overall
            
        except Exception as parsing_error:
            logger.error(f"Error parsing response: {parsing_error}")
            logger.error(f"Raw response: {response_text}")
            evaluation = {
                "transcription": f"Could not parse response: {str(parsing_error)[:100]}...",
                "relevance": 0,
                "clarity": 0,
                "confidence": 0,
                "keyword_usage_score": 0,
                "overall_score": 0,
                "feedback": {
                    "strengths": [],
                    "improvements": ["Evaluation failed - check server logs for details"]
                }
            }

        # Store evaluation for PDF report
        if session_id not in INTERVIEW_EVALUATIONS:
            INTERVIEW_EVALUATIONS[session_id] = []
        
        INTERVIEW_EVALUATIONS[session_id].append({
            "question": question,
            "question_difficulty": question_difficulty,
            "question_category": question_category,
            "transcription": evaluation.get("transcription", ""),
            "relevance_score": evaluation.get("relevance", 0),
            "clarity_score": evaluation.get("clarity", 0),
            "confidence_score": evaluation.get("confidence", 0),
            "keyword_usage_score": evaluation.get("keyword_usage_score", 0),
            "overall_score": evaluation.get("overall_score", 0),
            "evaluation": evaluation.get("feedback", {})
        })
        
        # Clean up
        temp_audio_path.unlink(missing_ok=True)
        
        return InterviewEvaluationResult(
            question=question,
            question_difficulty=question_difficulty,
            transcription=evaluation.get("transcription", ""),
            evaluation=evaluation.get("feedback", {}),
            relevance_score=evaluation.get("relevance", 0),
            clarity_score=evaluation.get("clarity", 0),
            confidence_score=evaluation.get("confidence", 0),
            keyword_usage_score=evaluation.get("keyword_usage_score", 0),
            overall_score=evaluation.get("overall_score", 0),
            session_id=session_id
        )

    except Exception as e:
        logger.error(f"Interview evaluation error: {str(e)}")
        if temp_audio_path.exists():
            temp_audio_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/interview/generate-report")
async def generate_interview_report(request: PDFReportRequest):
    """
    Generate comprehensive PDF report for completed interview
    """
    try:
        pdf_filename = generate_pdf_report(
            session_id=request.session_id,
            user_name=request.user_name,
            role=request.role,
            resume_summary=request.resume_summary
        )
        
        pdf_path = REPORTS_DIR / pdf_filename
        
        return FileResponse(
            path=str(pdf_path),
            filename=pdf_filename,
            media_type='application/pdf'
        )
    
    except Exception as e:
        logger.error(f"PDF report generation error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/interview/session/{session_id}")
async def get_interview_session(session_id: str):
    """Get all evaluations for a session"""
    evaluations = INTERVIEW_EVALUATIONS.get(session_id, [])
    
    if not evaluations:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "session_id": session_id,
        "total_questions": len(evaluations),
        "evaluations": evaluations,
        "average_score": sum(e['overall_score'] for e in evaluations) / len(evaluations)
    }

# Video Analysis Endpoint
@app.post("/api/video-resume/analyze", response_model=VideoAnalysisResult)
async def analyze_video_resume(
    video_file: UploadFile = File(...),
):
    """Upload and analyze video resume"""
    try:
        video_analysis = process_video(video_file.file)
        
        return VideoAnalysisResult(
            timestamps=video_analysis.get("timestamps", []),
            overall_emotion=video_analysis.get("overall_emotion", "neutral"),
            transcription=video_analysis.get("transcription", ""),
            confidence_score=video_analysis.get("confidence_score", 0.0),
            clarity_score=video_analysis.get("clarity_score", 0.0),
            relevance_score=video_analysis.get("relevance_score", 0.0),
            vocal_quality_score=video_analysis.get("vocal_quality_score", 0.0),
            overall_score=video_analysis.get("overall_score", 0.0)
        )
    
    except Exception as e:
        logger.error(f"Video resume analysis error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Skill Gap Analysis Endpoint
@app.post("/api/skill-gap/analyze", response_model=SkillGapResponse)
async def analyze_skill_gaps(
    request: SkillGapRequest
):
    """Analyze skill gaps between resume summary and job description"""
    try:
        analysis = analyze_skill_gap(request.resume_summary, request.job_description)
        
        return SkillGapResponse(
            missing_skills=analysis.get("missing_skills", []),
            recommendations=analysis.get("recommendations", []),
            additional_training=analysis.get("additional_training", [])
        )
    
    except Exception as e:
        logger.error(f"Skill gap analysis error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Profile Management Endpoints
@app.post("/api/profile/update", response_model=ProfileUpdateResponse)
async def update_profile(
    request: ProfileUpdateRequest
):
    """Update user profile with basic information"""
    try:
        updated_profile = save_profile(request)
        
        return ProfileUpdateResponse(
            user_id=request.user_id,
            profile=updated_profile,
            message="Profile updated successfully"
        )
    
    except Exception as e:
        logger.error(f"Profile update error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/profile/{user_id}")
async def get_user_profile(user_id: str):
    """Get user profile data"""
    try:
        profile = get_profile(user_id)
        
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        
        return {
            "user_id": user_id,
            "profile": profile
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get profile error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "message": "Resume Analyzer and Interview API v2.0",
        "features": [
            "Resume parsing (PDF, DOCX)",
            "Adaptive interview questions (Tech + HR)",
            "Speech analysis with difficulty-based scoring",
            "Keyword usage tracking",
            "PDF report generation",
            "Video resume analysis",
            "Skill gap analysis"
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)