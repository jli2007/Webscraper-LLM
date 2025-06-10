import os
import asyncio
import uvicorn
import uuid
import openai 
from fastapi import FastAPI, WebSocket, BackgroundTasks, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from typing import Dict, List, Optional
from enum import Enum
from datetime import datetime
from webscrape import ScrapingResult, WebScrape
from dotenv import load_dotenv

load_dotenv()

# Create FastAPI instance
app = FastAPI(
    title="Orchids Challenge API",
    description="A starter FastAPI template for the Orchids Challenge backend",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize OpenAI client
openai_client = openai.OpenAI(
    api_key=  os.getenv("OPENAI_KEY")
)

#  MODELS
class CloneStatus(str, Enum):
    PENDING = "pending"
    SCRAPING = "scraping" 
    PROCESSING = "processing"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"

class CloneRequest(BaseModel):
    url: str

class CloneJob(BaseModel):
    job_id: str
    status: CloneStatus
    url: str
    progress: int
    created_at: str
    completed_at: Optional[str] = None 
    error_message: Optional[str] = None
    result_data: Optional[Dict] = None
    

class CloneResponse(BaseModel):
    job_id: str
    status: CloneStatus
    message: str

# db
jobs_db: Dict[str, CloneJob] = {}

#WEBSOCKET MANAGER
class ConnectionManager:
    def __init__(self):
        # maps job_id → active WebSocket
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, job_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[job_id] = websocket

    def disconnect(self, job_id: str):
        # clean up when done
        if job_id in self.active_connections:
            del self.active_connections[job_id]

    async def send_update(self, job_id: str, data: dict):        
        # Sends a JSON dict down the socket for job_id, if still connected.

        ws = self.active_connections.get(job_id)
        if ws:
            await ws.send_json(data)

manager = ConnectionManager()

# Initialize scraper
scraper = WebScrape(
    use_browserbase=False,  # Set to True with API key for production
    browserbase_api_key=os.getenv("BROWSERBASE_KEY")
)

################# ROOT
@app.get("/")
async def root():
    return {
        "message": "Website Cloner API", 
        "status": "running",
        "endpoints": {
            "start_clone": "POST /api/clone",
            "check_status": "GET /api/clone/{job_id}/status", 
            "get_result": "GET /api/clone/{job_id}/result"
        }
    }
#################

# clone website
@app.post("/api/clone", response_model=CloneResponse) 
async def clone_url(clone_request: CloneRequest, background_tasks: BackgroundTasks):
    try:
        job_id = str(uuid.uuid4())
        
        job = CloneJob(
            job_id=job_id,
            status  =CloneStatus.PENDING,
            url=str(clone_request.url),
            progress=0,
            created_at=str(datetime.now())
        )
        
        # Store job
        jobs_db[job_id] = job
        
        # Start background processing
        background_tasks.add_task(process_clone_job, job_id, str(clone_request.url))
        
        return CloneResponse(
            job_id=job_id,
            status=CloneStatus.PENDING,
            message="Cloning process started"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start cloning: {str(e)}")

# PROCESS CLONE JOB
async def process_clone_job(job_id: str, url: str):
    try:
        while job_id not in manager.active_connections:
            await asyncio.sleep(0.1)
            
        jobs_db[job_id].status = CloneStatus.SCRAPING
        jobs_db[job_id].progress = 10
        
        await manager.send_update(
            job_id,
            {
                "status": jobs_db[job_id].status.value,
                "progress": jobs_db[job_id].progress,
            }
        )
        
        # Step 1: Scrape the website
        scraping_result = await scraper.scrape_website(url)
        
        if not scraping_result.success:
            jobs_db[job_id].status = CloneStatus.FAILED
            jobs_db[job_id].progress = 0
            jobs_db[job_id].error_message = scraping_result.error_message
            
            await manager.send_update(
                job_id,
                {
                    "status": jobs_db[job_id].status.value,
                    "progress": jobs_db[job_id].progress,
                    "error_message": jobs_db[job_id].error_message 
                }
            )
                    
            return
        
        # Update progress
        jobs_db[job_id].progress = 50
        jobs_db[job_id].status = CloneStatus.PROCESSING
        
        await manager.send_update(
            job_id,
            {
                "status": jobs_db[job_id].status.value,
                "progress": jobs_db[job_id].progress,
            }
        )
        
        # Step 2: Process the scraped data for LLM
        processed_data = await process_scraping_data(scraping_result)
        
        # Update progress
        jobs_db[job_id].progress = 70
        jobs_db[job_id].status = CloneStatus.GENERATING
        
        await manager.send_update(
            job_id,
            {
                "status": jobs_db[job_id].status.value,
                "progress": jobs_db[job_id].progress,
            }
        )
        
        # Step 3: Generate HTML with LLM (placeholder for now)
        generated_html = await generate_html_with_llm(processed_data)
        
        # Step 4: Update job as completed
        jobs_db[job_id].status = CloneStatus.COMPLETED
        jobs_db[job_id].progress = 100
        
        await manager.send_update(
            job_id,
            {
                "status": jobs_db[job_id].status.value,
                "progress": jobs_db[job_id].progress,
            }
        )
                    
        jobs_db[job_id].completed_at = datetime.now()
        jobs_db[job_id].result_data = {
            "original_url": url,
            "generated_html": generated_html,
            "scraping_metadata": {
            "colors_found": len(scraping_result.color_palette),
            "images_found": len(scraping_result.assets.get("images", [])),
            "fonts_found": len(scraping_result.typography.get("fonts", [])),
            "screenshots_taken": list(scraping_result.screenshots.keys()),
            "layout_type": scraping_result.layout_info.get("type"),
            "dominant_color": scraping_result.color_palette[0] if scraping_result.color_palette else None,
            "title": scraping_result.metadata.get("title"),
            "description": scraping_result.metadata.get("description"),
            }
        }
        
    except Exception as e:
        # Handle any errors
        jobs_db[job_id].status = CloneStatus.FAILED
        jobs_db[job_id].progress = 0
        jobs_db[job_id].error_message = str(e)
        jobs_db[job_id].completed_at = datetime.now()
        
        await manager.send_update(
            job_id,
            {
                "status": jobs_db[job_id].status.value,
                "progress": jobs_db[job_id].progress,
                "error_message": jobs_db[job_id].error_message 
            }
        )

async def process_scraping_data(scraping_result: ScrapingResult) -> Dict:
    # send to llm to re-create
    await asyncio.sleep(1)
    
    return {
        "url": scraping_result.url,
        "screenshots": scraping_result.screenshots,
        "dom_structure": scraping_result.dom_structure[:10000],  # Limit size
        "color_palette": scraping_result.color_palette,
        "typography": scraping_result.typography,
        "layout_info": scraping_result.layout_info,
        "css_info": scraping_result.extracted_css,
        "metadata": scraping_result.metadata,
    }
    
    
async def generate_html_with_llm(processed_data: Dict) -> str:
    # generate the website with llm
    
    try:
        # Prepare the prompt with scraped data
        prompt = create_html_generation_prompt(processed_data)
        
        response = openai_client.chat.completions.create(
            model="gpt-4o",  # or "gpt-3.5-turbo" for cheaper option
            messages=[
                {
                    "role": "system",
                    "content": """You are an expert web developer who recreates websites based on scraped data. 
                    Generate clean, modern HTML with inline CSS that closely matches the original design.
                    Make it responsive and professional. Only return the HTML code, no explanations."""
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_tokens=4000,
            temperature=0.3
        )
        
        generated_html = response.choices[0].message.content
        
        # Clean up the response (remove markdown code blocks if present)
        if "```html" in generated_html:
            generated_html = generated_html.split("```html")[1].split("```")[0].strip()
        elif "```" in generated_html:
            generated_html = generated_html.split("```")[1].split("```")[0].strip()
            
        return generated_html
        
    except Exception as e:
        print(f"Error generating HTML with OpenAI: {e}")
        return create_fallback_html(processed_data)

def create_html_generation_prompt(processed_data: Dict) -> str:    
    # Extract key information
    url = processed_data.get('url', '')
    colors = processed_data.get('color_palette', [])
    fonts = processed_data.get('typography', {}).get('fonts', [])
    layout_info = processed_data.get('layout_info', {})
    metadata = processed_data.get('metadata', {})
    dom_structure = processed_data.get('dom_structure', '')
    
    # Include screenshot data if available
    screenshot_info = ""
    if processed_data.get('screenshots'):
        screenshot_info = f"Screenshots available: {list(processed_data['screenshots'].keys())}"
    
    prompt = f"""
        Please recreate this website as HTML with inline CSS based on the following scraped data:

        **Original URL:** {url}

        **Page Metadata:**
        - Title: {metadata.get('title', 'N/A')}
        - Description: {metadata.get('description', 'N/A')}

        **Design Elements:**
        - Color Palette: {colors[:5]}  # Top 5 colors
        - Fonts: {fonts[:3]}  # Top 3 fonts
        - Layout Type: {layout_info.get('type', 'unknown')}

        **DOM Structure Preview:**
        {dom_structure[:2000]}...

        **Screenshots:** {screenshot_info}

        **Requirements:**
        1. Create a complete HTML document with inline CSS
        2. Use the extracted colors and fonts
        3. Make it responsive and modern
        4. Include proper semantic HTML structure
        5. Match the layout and visual hierarchy as closely as possible
        6. Add hover effects and smooth transitions
        7. Ensure cross-browser compatibility

        Generate clean, professional HTML that captures the essence and design of the original website as accurately as possible.
        """
    
    return prompt

#FALLBACK HTML IF GENERATION FAILS
def create_fallback_html(processed_data: Dict) -> str:
    colors = processed_data.get('color_palette', ['#ffffff', '#000000'])
    fonts = processed_data.get('typography', {}).get('fonts', ['Arial', 'sans-serif'])
    title = processed_data.get('metadata', {}).get('title', 'Cloned Website')
    
    return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{title}</title>
            <style>
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}
                
                body {{
                    font-family: {fonts[0] if fonts else 'Arial'}, sans-serif;
                    background-color: {colors[0] if colors else '#ffffff'};
                    color: {colors[1] if len(colors) > 1 else '#000000'};
                    line-height: 1.6;
                    padding: 20px;
                }}
                
                .container {{
                    max-width: 1200px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                
                .header {{
                    text-align: center;
                    margin-bottom: 40px;
                    padding: 40px 0;
                    background: linear-gradient(135deg, {colors[0] if colors else '#f0f0f0'}, {colors[1] if len(colors) > 1 else '#e0e0e0'});
                    border-radius: 10px;
                }}
                
                h1 {{
                    font-size: 2.5rem;
                    margin-bottom: 10px;
                    color: {colors[2] if len(colors) > 2 else '#333'};
                }}
                
                .content {{
                    background: white;
                    padding: 30px;
                    border-radius: 10px;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{title}</h1>
                    <p>Successfully cloned from: {processed_data.get('url', '')}</p>
                </div>
                
                <div class="content">
                    <h2>Website Clone Generated</h2>
                    <p>This is a basic clone. The OpenAI API would generate more sophisticated HTML based on the scraped data.</p>
                    
                    <div style="margin-top: 20px;">
                        <h3>Detected Elements:</h3>
                        <ul>
                            <li>Colors: {len(colors)} found</li>
                            <li>Fonts: {len(fonts)} found</li>
                            <li>Original URL: {processed_data.get('url', '')}</li>
                        </ul>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """

# result
@app.get("/api/clone/{job_id}/result")
async def get_clone_result(job_id: str):
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs_db[job_id]
    
    if job.status != CloneStatus.COMPLETED:
        raise HTTPException(status_code=400, detail=f"Job not completed. Current status: {job.status}")
    
    if not job.result_data:
        raise HTTPException(status_code=500, detail="No result data available")
    
    return{
        "job_id": job_id,
        "original_url": job.result_data["original_url"],
        "generated_html": job.result_data["generated_html"],
        "metadata": job.result_data["scraping_metadata"]
    }

# delete job
@app.delete("/api/clone/{job_id}")
async def delete_clone_job(job_id: str):
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="Job not found")
    
    del jobs_db[job_id]
    return {"message": f"Job {job_id} deleted successfully"}
        

# health check
@app.get("/health")
async def health_check():
    return {
        "status": "healthy", 
        "service": "website-cloner-api",
        "active_jobs": len([job for job in jobs_db.values() if job.status not in [CloneStatus.COMPLETED, CloneStatus.FAILED]])
    }

# websocket
@app.websocket("/ws/clone/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    await manager.connect(job_id, websocket)

    try:
        while True:
            # We don't actually need the client to send any payload—
            # we only want to keep the socket open so the server can push.
            # However, if the client ever sends a ping or text, we can ignore it:
            await websocket.receive_text()
    except Exception:
        # if client disconnects, or any error, clean up:
        pass
    finally:
        manager.disconnect(job_id)

# RUN APPLICATION
def main():
    uvicorn.run(
        "hello:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )


if __name__ == "__main__":
    main()
