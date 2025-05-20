from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import os
import json
from typing import Dict, List, Optional
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.graph import END, StateGraph
from pydub import AudioSegment
import requests
from dotenv import load_dotenv
from datetime import datetime
import uuid
import asyncio
from typing import TypedDict

# Load environment variables
load_dotenv()

app = FastAPI(title="Podcast Generator API",
              description="API for generating podcasts from text content",
              version="1.0.0")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
BASE_OUTPUT_DIR = "podcasts"
os.makedirs(BASE_OUTPUT_DIR, exist_ok=True)

# API Keys
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Voice IDs
VOICES = {
    "host": "cgSgspJ2msm6clMCkdW9",  # samantha samalytics
    "cohost": "pwMBn0SsmN1220Aorv15",  # ben
    "highlights": "pwMBn0SsmN1220Aorv15"
}

# Models
class TextInput(BaseModel):
    text: str
    voice_preference: Optional[str] = "host"

class PodcastResponse(BaseModel):
    job_id: str
    status: str
    message: str
    output_dir: Optional[str] = None

# Define the workflow state
class PodcastState(TypedDict):
    raw_text: str
    script: str
    podcast_audio: AudioSegment
    analysis: Dict
    soundbites: List[str]
    output_dir: str

# Initialize LLM
llm = ChatGroq(temperature=0.7, model_name="gemma2-9b-it", api_key=GROQ_API_KEY)

# Global job tracking
jobs = {}

# --- Helper Functions ---
def create_output_dir() -> str:
    """Create a unique output directory for each podcast"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    unique_id = str(uuid.uuid4())[:8]
    output_dir = os.path.join(BASE_OUTPUT_DIR, f"podcast_{timestamp}_{unique_id}")
    os.makedirs(output_dir, exist_ok=True)
    return output_dir

def generate_audio_segment(text: str, voice_id: str) -> AudioSegment:
    """Generate single audio segment using ElevenLabs API"""
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }
    data = {
        "text": text,
        "voice_settings": {"stability": 0.7, "similarity_boost": 0.8}
    }
    
    try:
        response = requests.post(url, json=data, headers=headers)
        response.raise_for_status()
        temp_file = os.path.join(BASE_OUTPUT_DIR, f"temp_{hash(text)}.mp3")
        with open(temp_file, "wb") as f:
            f.write(response.content)
        segment = AudioSegment.from_mp3(temp_file)
        os.remove(temp_file)
        return segment
    except requests.exceptions.RequestException as e:
        error_msg = f"API Error for voice {voice_id}: {str(e)}"
        if hasattr(e.response, 'text'):
            error_msg += f"\nResponse: {e.response.text}"
        raise HTTPException(status_code=500, detail=error_msg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating audio: {str(e)}")

# --- Nodes ---
def collect_text_input(state: PodcastState, text: str) -> PodcastState:
    """Node: Collect text input"""
    return {"raw_text": text, "output_dir": state.get("output_dir", "")}

def generate_script(state: PodcastState) -> PodcastState:
    """Node: Generate podcast script"""
    messages = [
        SystemMessage(content="Create a 3-minute podcast script with:\n"
                      "1. Engaging intro\n2. Two hosts alternating dialogue\n"
                      "3. Key points from provided text\n4. Natural outro\n"
                      "Format strictly EXACTLY like:\n**Host 1:** [text]\n**Host 2:** [text]\n"
                      "Make it engaging like including short one word expressive diaglogs by one the hosts during conversation"),
        HumanMessage(content=state["raw_text"])
    ]
    response = llm.invoke(messages)
    
    script_path = os.path.join(state["output_dir"], "script.txt")
    with open(script_path, "w", encoding='utf-8') as f:
        f.write(response.content)
    
    return {"script": response.content}

def create_podcast(state: PodcastState) -> PodcastState:
    """Node: Generate full podcast audio"""
    segments = []
    
    for line in state["script"].split('\n'):
        line = line.strip()
        if not line:
            continue
            
        if line.startswith("**Host 1:**"):
            speaker = "host"
            text = line[10:].strip()
        elif line.startswith("**Host 2:**"):
            speaker = "cohost"
            text = line[10:].strip()
        else:
            continue
            
        if text:
            try:
                segment = generate_audio_segment(text, VOICES[speaker])
                segments.append(segment)
            except Exception as e:
                print(f"⚠️ Failed to generate: '{text[:50]}...'")
                continue
    
    if not segments:
        raise HTTPException(status_code=400, detail="No valid audio segments created")
    
    podcast = segments[0]
    for seg in segments[1:]:
        podcast += AudioSegment.silent(duration=500) + seg
    
    podcast = AudioSegment.silent(duration=1000) + podcast + AudioSegment.silent(duration=1500)
    output_file = os.path.join(state["output_dir"], "podcast.mp3")
    podcast.export(output_file, format="mp3")
    
    return {"podcast_audio": podcast}

def analyze_content(state: PodcastState) -> PodcastState:
    """Node: Analyze script for sound bites"""
    print("\n💎 Analyzing content...")
    messages = [
        SystemMessage(content="""Analyze this podcast script and return a JSON object in this exact format:
{
    "key_points": [
        "First key point (20-30 words)",
        "Second key point (20-30 words)",
        "Third key point (25-30 words)"
    ],
    "major_issues": [
        "First major issue discussed",
        "Second major issue discussed"
    ],
    "conclusions": [
        "The main conclusion"
    ]
}
Important: Return ONLY valid JSON, no additional text or formatting."""),
        HumanMessage(content=state["script"])
    ]
    
    try:
        response = llm.invoke(messages)
        content = response.content.strip()
        
        # Try to extract JSON if it's wrapped in other text
        if not content.startswith('{'):
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                content = json_match.group()
            else:
                raise ValueError("No JSON found in response")
        
        analysis = json.loads(content)
        
        # Save analysis to file
        analysis_path = os.path.join(state["output_dir"], "analysis.json")
        with open(analysis_path, "w", encoding='utf-8') as f:
            json.dump(analysis, f, indent=2, ensure_ascii=False)
            
        return {"analysis": analysis}
        
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON response. Raw content:\n{content}")
        raise ValueError("Invalid JSON format received from API") from e
    except Exception as e:
        print(f"Error during analysis: {str(e)}")
        raise

def create_soundbites(state: PodcastState) -> PodcastState:
    """Node: Generate sound bite audio clips"""
    soundbites = []
    analysis = state["analysis"]
    
    for i, point in enumerate(analysis["key_points"]):
        audio = generate_audio_segment(point, VOICES["highlights"])
        output_file = os.path.join(state["output_dir"], f"keypoint_{i}.mp3")
        audio.export(output_file, format="mp3")
        soundbites.append(output_file)
    
    for i, issue in enumerate(analysis["major_issues"]):
        audio = generate_audio_segment(issue, VOICES["highlights"])
        output_file = os.path.join(state["output_dir"], f"issue_{i}.mp3")
        audio.export(output_file, format="mp3")
        soundbites.append(output_file)
    
    for i, conclusion in enumerate(analysis["conclusions"]):
        text = f"Conclusion: {conclusion}"
        audio = generate_audio_segment(text, VOICES["highlights"])
        output_file = os.path.join(state["output_dir"], f"conclusion_{i}.mp3")
        audio.export(output_file, format="mp3")
        soundbites.append(output_file)
    
    return {"soundbites": soundbites}

# --- Workflow Construction ---
def run_podcast_workflow(input_text: str, job_id: str):
    """Run the complete podcast generation workflow"""
    try:
        output_dir = create_output_dir()
        jobs[job_id] = {"status": "running", "output_dir": output_dir}
        
        # Define workflow
        workflow = StateGraph(PodcastState)
        
        # Add nodes with modified versions that take initial state
        workflow.add_node("collect_input", lambda state: collect_text_input(state, input_text))
        workflow.add_node("generate_script", generate_script)
        workflow.add_node("create_podcast", create_podcast)
        workflow.add_node("analyze_content", analyze_content)
        workflow.add_node("create_soundbites", create_soundbites)
        
        # Define edges
        workflow.set_entry_point("collect_input")
        workflow.add_edge("collect_input", "generate_script")
        workflow.add_edge("generate_script", "create_podcast")
        workflow.add_edge("create_podcast", "analyze_content")
        workflow.add_edge("analyze_content", "create_soundbites")
        workflow.add_edge("create_soundbites", END)
        
        # Compile and run
        app = workflow.compile()
        initial_state = {"output_dir": output_dir}
        app.invoke(initial_state)
        
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["message"] = "Podcast generation completed successfully"
        
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["message"] = str(e)

# --- API Endpoints ---
@app.post("/generate-from-text", response_model=PodcastResponse)
async def generate_from_text(input: TextInput, background_tasks: BackgroundTasks):
    """Generate podcast from text input"""
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "queued"}
    
    background_tasks.add_task(run_podcast_workflow, input.text, job_id)
    
    return {
        "job_id": job_id,
        "status": "queued",
        "message": "Podcast generation started"
    }

@app.get("/get-analysis/{job_id}")
async def get_analysis(job_id: str):
    """Get analysis data for a completed job"""
    if job_id not in jobs or jobs[job_id]["status"] != "completed":
        raise HTTPException(status_code=404, detail="Analysis not available")
    
    output_dir = jobs[job_id]["output_dir"]
    analysis_path = os.path.join(output_dir, "analysis.json")
    
    if not os.path.exists(analysis_path):
        raise HTTPException(status_code=404, detail="Analysis file not found")
    
    with open(analysis_path, "r") as f:
        analysis_data = json.load(f)
    
    return JSONResponse(content=analysis_data)

@app.get("/job-status/{job_id}", response_model=PodcastResponse)
async def get_job_status(job_id: str):
    """Check the status of a podcast generation job"""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return {
        "job_id": job_id,
        "status": jobs[job_id]["status"],
        "message": jobs[job_id].get("message", ""),
        "output_dir": jobs[job_id].get("output_dir")
    }

@app.get("/download-podcast/{job_id}")
async def download_podcast(job_id: str):
    """Download the generated podcast"""
    if job_id not in jobs or jobs[job_id]["status"] != "completed":
        raise HTTPException(status_code=404, detail="Podcast not available or not ready")
    
    output_dir = jobs[job_id]["output_dir"]
    podcast_path = os.path.join(output_dir, "podcast.mp3")
    
    if not os.path.exists(podcast_path):
        raise HTTPException(status_code=404, detail="Podcast file not found")
    
    return FileResponse(
        podcast_path,
        media_type="audio/mpeg",
        filename="podcast.mp3"
    )

@app.get("/soundbites/{job_id}/{filename}")
async def get_soundbite(job_id: str, filename: str):
    """Serve individual soundbite audio files"""
    if job_id not in jobs or jobs[job_id]["status"] != "completed":
        raise HTTPException(status_code=404, detail="Job not found or incomplete")
    
    soundbite_path = os.path.join(jobs[job_id]["output_dir"], filename)
    
    if not os.path.exists(soundbite_path):
        raise HTTPException(status_code=404, detail="Soundbite not found")
    
    return FileResponse(soundbite_path, media_type="audio/mpeg")

@app.get("/list-jobs")
async def list_jobs():
    """List all current jobs"""
    return JSONResponse(content=jobs)

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)