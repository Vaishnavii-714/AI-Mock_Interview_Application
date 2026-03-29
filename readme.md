# 🚀 Updated Resume Analyzer & Interview API v2.0

## ✅ All Requirements Implemented

### 1. ✅ Resume Upload & Parsing
- Supports `.doc`, `.docx`, `.pdf`, `.txt` formats
- AI extracts: skills, experience, education, certifications, contact info
- **NEW**: User now specifies the **role** they want to interview for

### 2. ✅ AI-Powered Adaptive Questioning System
- **60% Technical Questions** + **40% HR Questions**
- **Difficulty Levels**: 30% Easy → 40% Medium → 30% Hard
- Questions sorted by difficulty (Easy first → Hard last)
- **Adaptive Scoring**: Different passing thresholds based on difficulty

### 3. ✅ Speech & Response Analysis (Scorecard)
- ✅ **Clarity Score** (0-1)
- ✅ **Relevance Score** (0-1)
- ✅ **Confidence Score** (0-1)
- ✅ **Keyword Usage Score** (0-1) - NEW!
- ✅ **Overall Score** (weighted average)
- ✅ Generates detailed scorecard with strengths & improvements

### 4. ✅ Real-Time Feedback & Suggestions
- Instant feedback after each answer
- Strengths highlighted
- Specific areas for improvement
- Difficulty-aware evaluation

### 5. ✅ PDF Report Generation
- Comprehensive interview performance report
- Resume scores included
- Question-by-question analysis
- Overall performance summary
- Personalized recommendations
- Professional formatting with tables and charts

---

## 🆕 What's New in v2.0

### Updated Google GenAI Library
```python
# OLD (deprecated)
import google.generativeai as genai
model = genai.GenerativeModel("gemini-1.5-flash")
response = model.generate_content(prompt)

# NEW (updated)
from google import genai
client = genai.Client(api_key="YOUR_API_KEY")
response = client.models.generate_content(
    model="gemini-2.0-flash-exp",
    contents=prompt
)
```

### Adaptive Difficulty System
- Questions pre-sorted by difficulty
- Different scoring thresholds:
  - **Easy**: Pass=60%, Good=75%, Excellent=85%
  - **Medium**: Pass=65%, Good=78%, Excellent=88%
  - **Hard**: Pass=70%, Good=80%, Excellent=90%

### Keyword Usage Tracking
- AI extracts expected keywords from each question
- Measures how many keywords candidate uses
- Contributes 25% to overall score

### Session Management
- Each interview gets a unique `session_id`
- All evaluations tracked per session
- Easy retrieval for PDF generation

---

## 📋 API Endpoints

### 1. Upload Resume
```http
POST /api/resume/upload
Content-Type: multipart/form-data

file: <resume.pdf|docx|txt>
```

**Response:**
```json
{
  "summary": {
    "name": "John Doe",
    "email": "john@email.com",
    "experience_years": 5,
    "key_skills": ["Python", "React", "AWS"]
  },
  "skills": ["Python", "React", "AWS"]
}
```

---

### 2. Generate Interview Questions (UPDATED!)
```http
POST /api/interview/questions
Content-Type: application/json

{
  "job_description": "We are looking for a Python developer...",
  "role": "Senior Python Developer",  // NEW: User specifies role
  "num_questions": 10
}
```

**Response:**
```json
{
  "questions": [
    {
      "question": "What is Python's GIL?",
      "category": "technical",
      "difficulty": "easy"
    },
    {
      "question": "Tell me about a time you resolved a conflict",
      "category": "hr",
      "difficulty": "easy"
    },
    {
      "question": "Design a scalable microservices architecture",
      "category": "technical",
      "difficulty": "hard"
    }
  ]
}
```

**Question Distribution:**
- 60% Technical (algorithms, coding, system design, tools)
- 40% HR/Behavioral (STAR method, culture fit, motivation)
- Sorted: Easy → Medium → Hard

---

### 3. Evaluate Interview Response (UPDATED!)
```http
POST /evaluate-interview-response/
Content-Type: multipart/form-data

question: "What is Python's GIL?"
question_difficulty: "easy"  // NEW
question_category: "technical"  // NEW
job_description: "Python developer role..."  // NEW (for keywords)
audio_file: <audio.wav>
session_id: "uuid-here"  // NEW (optional, auto-generated)
```

**Response:**
```json
{
  "question": "What is Python's GIL?",
  "question_difficulty": "easy",
  "transcription": "The GIL is a mutex that protects access...",
  "evaluation": {
    "strengths": [
      "Clear explanation of GIL concept",
      "Mentioned threading implications"
    ],
    "improvements": [
      "Could elaborate on multiprocessing alternative",
      "Missing mention of CPython specifics"
    ]
  },
  "relevance_score": 0.85,
  "clarity_score": 0.80,
  "confidence_score": 0.90,
  "keyword_usage_score": 0.75,  // NEW
  "overall_score": 0.83,
  "session_id": "abc-123-def"  // NEW
}
```

---

### 4. Generate PDF Report (NEW!)
```http
POST /api/interview/generate-report
Content-Type: application/json

{
  "session_id": "abc-123-def",
  "user_name": "John Doe",
  "role": "Senior Python Developer",
  "resume_summary": "5 years experience..." // optional
}
```

**Response:**
Downloads PDF file with:
- Candidate information
- Overall performance summary
- Resume scores (Skills: 8/10, etc.)
- Question-by-question breakdown
- Transcriptions
- Detailed feedback
- Final recommendations

---

### 5. Get Session Info (NEW!)
```http
GET /api/interview/session/{session_id}
```

**Response:**
```json
{
  "session_id": "abc-123-def",
  "total_questions": 10,
  "evaluations": [...],
  "average_score": 0.78
}
```

---

## 🎯 Frontend Integration (NO CHANGES NEEDED!)

Your existing frontend will work as-is! Just add these optional parameters:

### Before (Still Works):
```javascript
// Generate questions
const response = await fetch('/api/interview/questions', {
  method: 'POST',
  body: JSON.stringify({
    job_description: jobDesc,
    num_questions: 10
  })
});
```

### After (Recommended):
```javascript
// Generate questions with role
const response = await fetch('/api/interview/questions', {
  method: 'POST',
  body: JSON.stringify({
    job_description: jobDesc,
    role: "Senior Python Developer",  // ADD THIS
    num_questions: 10
  })
});

const { questions } = await response.json();
// questions are now sorted: easy → medium → hard
// Each has: question, category, difficulty
```

### Evaluate Responses:
```javascript
// Loop through questions
for (let i = 0; i < questions.length; i++) {
  const formData = new FormData();
  formData.append('question', questions[i].question);
  formData.append('question_difficulty', questions[i].difficulty);  // ADD
  formData.append('question_category', questions[i].category);  // ADD
  formData.append('job_description', jobDescription);  // ADD
  formData.append('audio_file', audioBlob);
  formData.append('session_id', sessionId);  // ADD (same for all)
  
  const result = await fetch('/evaluate-interview-response/', {
    method: 'POST',
    body: formData
  });
  
  // Store sessionId from first response
  if (i === 0) {
    const data = await result.json();
    sessionId = data.session_id;
  }
}
```

### Generate PDF Report:
```javascript
// After all questions answered
const response = await fetch('/api/interview/generate-report', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    session_id: sessionId,
    user_name: userName,
    role: role,
    resume_summary: resumeText
  })
});

// Download PDF
const blob = await response.blob();
const url = window.URL.createObjectURL(blob);
const a = document.createElement('a');
a.href = url;
a.download = `interview_report_${sessionId}.pdf`;
a.click();
```

---

## 🔧 Installation & Setup

### 1. Install Dependencies
```bash
pip install fastapi uvicorn python-multipart
pip install PyPDF2 python-docx
pip install python-dotenv
pip install sounddevice soundfile
pip install SpeechRecognition
pip install gensim
pip install numpy
pip install plotly
pip install reportlab  # NEW for PDF generation
pip install google-genai  # NEW updated library
```

### 2. Environment Variables
Create `.env` file:
```
GOOGLE_API_KEY=your_gemini_api_key_here
```

### 3. Run Server
```bash
python app.py
```

Server runs on: `http://localhost:8000`

---

## 📊 Adaptive Scoring Example

### Easy Question: "What is a variable in Python?"
- Pass threshold: 60%
- User scores 65% → **PASS** ✅
- Next question: **MEDIUM** difficulty

### Medium Question: "Explain list comprehension"
- Pass threshold: 65%
- User scores 80% → **GOOD** ✅
- Next question: **HARD** difficulty

### Hard Question: "Design a distributed caching system"
- Pass threshold: 70%
- User scores 68% → **NEEDS IMPROVEMENT** ⚠️
- Feedback focuses on system design fundamentals

---

## 📈 Sample PDF Report Structure

```
┌─────────────────────────────────────┐
│  Interview Performance Report        │
├─────────────────────────────────────┤
│  Candidate: John Doe                 │
│  Role: Senior Python Developer       │
│  Date: 2025-10-24                   │
│  Session ID: abc-123                 │
├─────────────────────────────────────┤
│  Overall Performance Summary         │
│  ┌───────────────┬───────┬─────────┐│
│  │ Metric        │ Score │ Rating  ││
│  ├───────────────┼───────┼─────────┤│
│  │ Relevance     │ 0.83  │ Good    ││
│  │ Clarity       │ 0.78  │ Good    ││
│  │ Confidence    │ 0.85  │ Excellent││
│  │ Keyword Usage │ 0.72  │ Average ││
│  │ Overall       │ 0.80  │ Good    ││
│  └───────────────┴───────┴─────────┘│
├─────────────────────────────────────┤
│  Resume Analysis                     │
│  Skills: 8/10                        │
│  Experience: Strong                  │
│  Education: Relevant                 │
├─────────────────────────────────────┤
│  Question 1 (EASY)                   │
│  Q: What is Python's GIL?            │
│  Scores: R:0.85 C:0.80 Conf:0.90    │
│  Your Response: "The GIL is..."      │
│  Strengths: Clear explanation        │
│  Improvements: Add more examples     │
├─────────────────────────────────────┤
│  [... more questions ...]            │
├─────────────────────────────────────┤
│  Final Recommendations               │
│  • Strong technical foundation       │
│  • Practice system design questions  │
│  • Work on explaining complex topics │
└─────────────────────────────────────┘
```

---

## 🎯 Key Features Summary

| Feature | Status | Details |
|---------|--------|---------|
| Resume Upload (DOC/DOCX/PDF) | ✅ | Extracts all key details |
| User Specifies Role | ✅ | Added to question generation |
| Tech + HR Questions | ✅ | 60% Tech, 40% HR |
| Adaptive Difficulty | ✅ | Easy→Medium→Hard progression |
| Difficulty-Based Scoring | ✅ | Different thresholds |
| Keyword Usage Analysis | ✅ | AI extracts & tracks keywords |
| Speech Analysis | ✅ | Clarity, Relevance, Confidence |
| Real-time Feedback | ✅ | Strengths & improvements |
| Session Tracking | ✅ | All responses linked |
| PDF Report Generation | ✅ | Comprehensive analysis |
| Resume Scores in PDF | ✅ | Skills: X/10 format |
| Updated GenAI Library | ✅ | Using latest `google.genai` |

---

## 🚦 How Adaptive System Works

```
┌─────────────────────────────────────────┐
│  Interview Flow (Frontend stays same!)  │
└─────────────────────────────────────────┘

1. Frontend calls: /api/interview/questions
   ↓
   Backend generates 10 questions:
   - Questions 1-3: EASY
   - Questions 4-7: MEDIUM
   - Questions 8-10: HARD
   ↓
2. Frontend displays questions in order
   ↓
3. For each answer, Frontend calls:
   /evaluate-interview-response/
   with difficulty + category + session_id
   ↓
4. Backend scores based on difficulty:
   - EASY question: Pass=60%, more lenient
   - HARD question: Pass=70%, more strict
   ↓
5. After all questions, Frontend calls:
   /api/interview/generate-report
   ↓
6. User downloads comprehensive PDF report
```

---

## 🔍 Testing the API

### Test Question Generation:
```bash
curl -X POST http://localhost:8000/api/interview/questions \
  -H "Content-Type: application/json" \
  -d '{
    "job_description": "Senior Python Developer with Django experience",
    "role": "Senior Python Developer",
    "num_questions": 10
  }'
```

### Test Health Check:
```bash
curl http://localhost:8000/health
```

---

## 🎓 Technical Implementation Details

### Adaptive Scoring Algorithm:
```python
def get_difficulty_threshold(difficulty):
    return {
        "easy": {"pass": 0.6, "good": 0.75, "excellent": 0.85},
        "medium": {"pass": 0.65, "good": 0.78, "excellent": 0.88},
        "hard": {"pass": 0.70, "good": 0.80, "excellent": 0.90}
    }[difficulty]
```

### Keyword Extraction:
- AI analyzes question + job description
- Extracts 5-10 key technical terms
- Checks candidate's transcription for usage
- Contributes 25% to overall score

### PDF Generation:
- Uses ReportLab library
- Professional formatting
- Tables, charts, sections
- Downloadable via `/api/interview/generate-report`

---

## 💡 Pro Tips

1. **Session Management**: Keep the same `session_id` for all questions in one interview
2. **Role Specification**: Always provide the `role` parameter for better question generation
3. **Keyword Context**: Pass `job_description` to evaluation endpoint for accurate keyword tracking
4. **PDF Timing**: Generate PDF only after ALL questions are answered
5. **Audio Quality**: Use clear audio recordings for best transcription accuracy

---

## 🐛 Troubleshooting

### "Model not found" error:
- Ensure Doc2Vec model file exists: `cv_job_maching.model`
- Place it in the same directory as `app.py`

### "API key not found":
- Check `.env` file exists
- Verify `GOOGLE_API_KEY=your_key_here`

### PDF generation fails:
- Install reportlab: `pip install reportlab`
- Ensure `reports/` directory exists

### Audio evaluation fails:
- Check audio file format (WAV recommended)
- Ensure file size < 20MB
- Verify Gemini API has audio processing enabled

---

## 📝 Changelog

### v2.0 (Current)
- ✅ Added adaptive difficulty system
- ✅ Integrated Tech + HR questions (60/40 split)
- ✅ Added keyword usage tracking
- ✅ Implemented PDF report generation
- ✅ Updated to new `google.genai` library
- ✅ Added role specification
- ✅ Added session management
- ✅ Enhanced scoring with difficulty thresholds

### v1.0 (Previous)
- Resume upload & parsing
- Job matching
- Static question generation
- Audio evaluation

---

## 📞 Support

For issues or questions:
1. Check logs in console
2. Verify all dependencies installed
3. Ensure `.env` file configured
4. Check API documentation at `/docs`

---

## ✅ Requirement Checklist

- [x] Resume Upload & Parsing (DOC format) ✅
- [x] User writes role for mock test ✅
- [x] AI-powered questioning (Tech + HR) ✅
- [x] Adaptive difficulty (Easy→Hard) ✅
- [x] Speech analysis scorecard ✅
- [x] Clarity, Relevance, Confidence, Keywords ✅
- [x] Real-time feedback ✅
- [x] PDF report generation ✅
- [x] Resume scores in PDF ✅
- [x] Speech evaluation in PDF ✅

**ALL REQUIREMENTS MET! 🎉**