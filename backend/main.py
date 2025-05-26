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
GROQ_API_KEY = os.getenv("groq_api_key")

# Voice IDs
VOICES = {
    "host": "cgSgspJ2msm6clMCkdW9",  # samantha samalytics
    "cohost": "pwMBn0SsmN1220Aorv15",  # ben
    "highlights": "pwMBn0SsmN1220Aorv15",
    "voice1": "21m00Tcm4TlvDq8ikWAM",  # Rachel
    "voice2": "AZnzlk1XvdvUeBnXmlld"   # Domi
}

# Models
class TextInput(BaseModel):
    text: str
    voice_preference: Optional[str] = "host"
    podcast_length: Optional[int] = 3  # fixed at 3 minutes
    num_key_points: Optional[int] = 3
    num_major_issues: Optional[int] = 2
    host_voice: Optional[str] = "host"
    cohost_voice: Optional[str] = "cohost"
    custom_prompt: Optional[str] = None

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
    podcast_length: int
    num_key_points: int
    num_major_issues: int
    host_voice: str
    cohost_voice: str

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
def collect_text_input(state: PodcastState, text: str, podcast_length: int, num_key_points: int, num_major_issues: int, host_voice: str, cohost_voice: str) -> PodcastState:
    """Node: Collect text input"""
    print(f"\n📥 Collecting input with parameters:")
    print(f"Podcast Length: {podcast_length}")
    print(f"Number of Key Points: {num_key_points}")
    print(f"Number of Major Issues: {num_major_issues}")
    print(f"Host Voice: {host_voice}")
    print(f"Co-host Voice: {cohost_voice}\n")
    
    return {
        "raw_text": text,
        "output_dir": state.get("output_dir", ""),
        "podcast_length": podcast_length,
        "num_key_points": num_key_points,
        "num_major_issues": num_major_issues,
        "host_voice": host_voice,
        "cohost_voice": cohost_voice
    }

def generate_script(state: PodcastState) -> PodcastState:
    """Node: Generate podcast script"""
    # Log state parameters
    print(f"\n📝 Generating script with parameters:")
    print(f"Podcast Length: {state.get('podcast_length', 3)}")
    print(f"Number of Key Points: {state.get('num_key_points', 3)}")
    print(f"Number of Major Issues: {state.get('num_major_issues', 2)}")
    print(f"Host Voice: {state.get('host_voice', 'host')}")
    print(f"Co-host Voice: {state.get('cohost_voice', 'cohost')}\n")
    
    # Use custom prompt if provided, otherwise use default
    prompt = state.get('custom_prompt', f"""Create a {state.get('podcast_length', 3)}-minute podcast script with:
1. Engaging intro
2. Two hosts alternating dialogue
3. EXACTLY {state.get('num_key_points', 3)} key points from provided text
4. EXACTLY {state.get('num_major_issues', 2)} major issues discussed
5. Natural outro

Format strictly EXACTLY like:
**Host 1:** [text]
**Host 2:** [text]

Make it engaging like including short one word expressive diaglogs by one the hosts during conversation.
IMPORTANT: You MUST include EXACTLY {state.get('num_key_points', 3)} key points and EXACTLY {state.get('num_major_issues', 2)} major issues.

The script should be structured to fit within {state.get('podcast_length', 3)} minutes.""")
    
    messages = [
        SystemMessage(content=prompt),
        HumanMessage(content=state["raw_text"])
    ]
    response = llm.invoke(messages)
    
    script_path = os.path.join(state["output_dir"], "script.txt")
    with open(script_path, "w", encoding='utf-8') as f:
        f.write(response.content)
    
    return {
        "script": response.content,
        "podcast_length": state.get("podcast_length", 3),
        "num_key_points": state.get("num_key_points", 3),
        "num_major_issues": state.get("num_major_issues", 2),
        "host_voice": state.get("host_voice", "host"),
        "cohost_voice": state.get("cohost_voice", "cohost")
    }

def create_podcast(state: PodcastState) -> PodcastState:
    """Node: Generate full podcast audio"""
    segments = []
    failed_lines = []
    
    for line in state["script"].split('\n'):
        line = line.strip()
        if not line:
            continue
            
        if line.startswith("**Host 1:**"):
            speaker = state.get("host_voice", "host")
            text = line[10:].strip()
        elif line.startswith("**Host 2:**"):
            speaker = state.get("cohost_voice", "cohost")
            text = line[10:].strip()
        else:
            continue
            
        if text:
            try:
                print(f"Attempting to generate audio for: {text[:50]}... (speaker: {speaker})")
                segment = generate_audio_segment(text, VOICES[speaker])
                segments.append(segment)
                print(f"✅ Successfully generated segment")
            except Exception as e:
                print(f"⚠️ Failed to generate: '{text[:50]}...' - Error: {str(e)}")
                failed_lines.append(text)
                continue
    
    if not segments:
        error_msg = "No valid audio segments created. Failed lines:\n" + "\n".join(failed_lines[:5])
        print(error_msg)
        raise HTTPException(status_code=400, detail=error_msg)
    
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
        SystemMessage(content=f"""Analyze this podcast script and return a JSON object in this exact format:
{{
    "key_points": [
        {", ".join([f'"Key point {i+1} (20-30 words)"' for i in range(state.get("num_key_points", 3))])}
    ],
    "major_issues": [
        {", ".join([f'"Major issue {i+1} discussed"' for i in range(state.get("num_major_issues", 2))])}
    ],
    "conclusions": [
        "The main conclusion"
    ]
}}
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
            
        return {
            "analysis": analysis,
            "podcast_length": state.get("podcast_length", 3),
            "num_key_points": state.get("num_key_points", 3),
            "num_major_issues": state.get("num_major_issues", 2),
            "host_voice": state.get("host_voice", "host"),
            "cohost_voice": state.get("cohost_voice", "cohost")
        }
        
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
def run_podcast_workflow(input_text: str, job_id: str, podcast_length: int = 3, num_key_points: int = 3, num_major_issues: int = 2, host_voice: str = "host", cohost_voice: str = "cohost"):
    """Run the complete podcast generation workflow"""
    try:
        output_dir = create_output_dir()
        jobs[job_id] = {"status": "running", "output_dir": output_dir}
        
        # Log workflow parameters
        print(f"\n🎙️ Starting workflow with parameters:")
        print(f"Podcast Length: {podcast_length}")
        print(f"Number of Key Points: {num_key_points}")
        print(f"Number of Major Issues: {num_major_issues}")
        print(f"Host Voice: {host_voice}")
        print(f"Co-host Voice: {cohost_voice}\n")
        
        # Define workflow
        workflow = StateGraph(PodcastState)
        
        # Add nodes with modified versions that take initial state
        workflow.add_node("collect_input", lambda state: collect_text_input(state, input_text, podcast_length, num_key_points, num_major_issues, host_voice, cohost_voice))
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
        print(f"\n❌ Error in workflow: {str(e)}")
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["message"] = str(e)

# --- API Endpoints ---
@app.post("/generate-from-text", response_model=PodcastResponse)
async def generate_from_text(input: TextInput, background_tasks: BackgroundTasks):
    """Generate podcast from text input"""
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "queued"}
    
    # Log the input parameters
    print(f"\n🔧 Received parameters:")
    print(f"Podcast Length: {input.podcast_length}")
    print(f"Number of Key Points: {input.num_key_points}")
    print(f"Number of Major Issues: {input.num_major_issues}")
    print(f"Host Voice: {input.host_voice}")
    print(f"Co-host Voice: {input.cohost_voice}\n")
    
    background_tasks.add_task(
        run_podcast_workflow,
        input.text,
        job_id,
        input.podcast_length,
        input.num_key_points,
        input.num_major_issues,
        input.host_voice,
        input.cohost_voice
    )
    
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