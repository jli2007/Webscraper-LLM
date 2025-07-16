import os
import asyncio
import json
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
from bs4 import Tag, BeautifulSoup

load_dotenv()

# Create FastAPI instance
app = FastAPI(
    title="webscrape llm project", description="fastapi backend", version="1.0.0"
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
openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_KEY"))


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


# WEBSOCKET MANAGER
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
    use_browserbase=False,  # true to use browserbase (1hr cap total), false to use local
    browserbase_api_key=os.getenv("BROWSERBASE_KEY") or "",
)


################# ROOT
@app.get("/")
async def root():
    return {
        "message": "Website Cloner API",
        "status": "running",
        # yo like this gotta be fixed
        "endpoints": {
            "start_clone": "POST /api/clone",
            "check_status": "GET /api/clone/{job_id}/status",
            "get_result": "GET /api/clone/{job_id}/result",
        },
    }


#################


# clone website
@app.post("/api/clone", response_model=CloneResponse)
async def clone_url(clone_request: CloneRequest, background_tasks: BackgroundTasks):
    try:
        job_id = str(uuid.uuid4())

        job = CloneJob(
            job_id=job_id,
            status=CloneStatus.PENDING,
            url=str(clone_request.url),
            progress=0,
            created_at=str(datetime.now()),
        )

        # Store job
        jobs_db[job_id] = job

        # Start background processing
        background_tasks.add_task(process_clone_job, job_id, str(clone_request.url))

        return CloneResponse(
            job_id=job_id, status=CloneStatus.PENDING, message="Cloning process started"
        )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to start cloning: {str(e)}"
        )


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
            },
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
                    "error_message": jobs_db[job_id].error_message,
                },
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
            },
        )

        # Update progress
        jobs_db[job_id].progress = 70
        jobs_db[job_id].status = CloneStatus.GENERATING

        await manager.send_update(
            job_id,
            {
                "status": jobs_db[job_id].status.value,
                "progress": jobs_db[job_id].progress,
            },
        )

        # Step 3: Generate HTML with LLM (placeholder for now)
        generated_html = await generate_html_with_llm(scraping_result)

        # Step 4: Update job as completed
        jobs_db[job_id].status = CloneStatus.COMPLETED
        jobs_db[job_id].progress = 100

        await manager.send_update(
            job_id,
            {
                "status": jobs_db[job_id].status.value,
                "progress": jobs_db[job_id].progress,
            },
        )

        jobs_db[job_id].completed_at = str(datetime.now())
        jobs_db[job_id].result_data = {
            "original_url": url,
            "generated_html": generated_html,
            "scraping_metadata": {
                # Visual hierarchy information
                "visual_hierarchy": scraping_result.visual_hierarchy,
                "has_header": scraping_result.visual_hierarchy.get("header") is not None,
                "has_navigation": scraping_result.visual_hierarchy.get("navigation") is not None,
                "has_hero": scraping_result.visual_hierarchy.get("hero_section") is not None,
                "content_sections": len(scraping_result.visual_hierarchy.get("main_content", [])),
                
                # Design tokens
                "color_palette": scraping_result.design_tokens.get("colors", {}).get("background", []),
                "text_colors": scraping_result.design_tokens.get("colors", {}).get("text", []),
                "primary_colors": scraping_result.design_tokens.get("colors", {}).get("primary", []),
                "dominant_color": (
                    scraping_result.design_tokens.get("colors", {}).get("background", [None])[0] 
                    if scraping_result.design_tokens.get("colors", {}).get("background") 
                    else None
                ),
                
                # Typography
                "typography": scraping_result.design_tokens.get("typography", {}),
                "fonts_found": scraping_result.design_tokens.get("typography", {}).get("font_families", []),
                "heading_font": scraping_result.design_tokens.get("typography", {}).get("headings", {}).get("fontFamily"),
                "body_font": scraping_result.design_tokens.get("typography", {}).get("body", {}).get("fontFamily"),
                
                # Layout and components
                "layout_patterns": scraping_result.layout_patterns,
                "components_identified": scraping_result.component_library,
                "component_count": len(scraping_result.component_library),
                "has_grid_layout": len(scraping_result.layout_patterns.get("grid_layouts", [])) > 0,
                "has_flex_layout": len(scraping_result.layout_patterns.get("flex_layouts", [])) > 0,
                
                # Responsive information
                "responsive_screenshots": list(scraping_result.responsive_previews.keys()),
                "breakpoints_captured": len(scraping_result.responsive_previews),
                
                # Simplified code references
                "reference_html": scraping_result.critical_html,
                "reference_css": scraping_result.critical_css,
                
                # Legacy compatibility (if you need to maintain some old structure)
                "screenshots_taken": ["primary_screenshot", "annotated_screenshot"] + list(scraping_result.responsive_previews.keys()),
                "layout_type": "responsive" if scraping_result.responsive_previews else "desktop",
                
                # Page metadata (if you still extract this)
                "title": scraping_result.visual_hierarchy.get("header", {}).get("text", "")[:100] if scraping_result.visual_hierarchy.get("header") else "Unknown",
                "description": scraping_result.visual_hierarchy.get("hero_section", {}).get("text", "")[:200] if scraping_result.visual_hierarchy.get("hero_section") else "",
                
                # Success indicators
                "scraping_success": scraping_result.success,
                "error_message": scraping_result.error_message,
                
                # Quality metrics
                "data_quality": {
                    "has_visual_hierarchy": bool(scraping_result.visual_hierarchy),
                    "has_design_tokens": bool(scraping_result.design_tokens),
                    "has_components": bool(scraping_result.component_library),
                    "has_primary_screenshot": bool(scraping_result.primary_screenshot),
                    "completeness_score": sum([
                        bool(scraping_result.visual_hierarchy),
                        bool(scraping_result.design_tokens),
                        bool(scraping_result.component_library),
                        bool(scraping_result.primary_screenshot),
                        bool(scraping_result.critical_html),
                        bool(scraping_result.critical_css)
                    ]) / 6.0
                }
            }
        }

    except Exception as e:
        # Handle any errors
        jobs_db[job_id].status = CloneStatus.FAILED
        jobs_db[job_id].progress = 0
        jobs_db[job_id].error_message = str(e)
        jobs_db[job_id].completed_at = str(datetime.now())

        await manager.send_update(
            job_id,
            {
                "status": jobs_db[job_id].status.value,
                "progress": jobs_db[job_id].progress,
                "error_message": jobs_db[job_id].error_message,
            },
        )


async def generate_html_with_llm(scraping_result: ScrapingResult) -> str:
        """Optimized LLM generation with visual-first prompting"""
        try:
            # Create optimized prompt focused on visual data
            prompt = _create_optimized_prompt(scraping_result)
            
            # Use optimized model parameters
            response = openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": _get_optimized_system_prompt()
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                max_tokens=12000,  # Increased for better output
                temperature=0.1,   # Lower for more consistent results
                top_p=0.9,        # Focus on high-probability tokens
                frequency_penalty=0.1,  # Reduce repetition
                presence_penalty=0.1    # Encourage variety
            )
            
            generated_html = response.choices[0].message.content
            
            if not generated_html:
                return _create_fallback_html(scraping_result)
            
            # Clean and validate HTML
            return _clean_generated_html(generated_html)
            
        except Exception as e:
            print(f"Error generating HTML with LLM: {e}")
            return _create_fallback_html(scraping_result)
        
def _get_optimized_system_prompt() -> str:
    """Optimized system prompt for visual-first generation"""
    return """You are an expert web developer specializing in visual website recreation. 

    Your task is to generate pixel-perfect HTML recreations based on visual analysis data. 

    KEY PRINCIPLES:
    1. Screenshots are your PRIMARY reference - match them exactly
    2. Use the visual hierarchy data to structure your HTML semantically
    3. Apply design tokens for consistent styling
    4. Implement responsive design using the provided breakpoint data
    5. Create clean, modern code with inline CSS
    6. Focus on visual accuracy over complex functionality

    OUTPUT REQUIREMENTS:
    - Complete HTML document with DOCTYPE
    - All CSS inline (no external stylesheets)
    - Responsive design with proper media queries
    - Semantic HTML5 structure
    - Modern CSS (flexbox, grid, custom properties)
    - Smooth hover effects and transitions
    - Accessibility considerations (ARIA labels, semantic structure)

    Return ONLY the HTML code, no explanations or markdown formatting."""

def _create_optimized_prompt(result: ScrapingResult) -> str:
    """Create optimized prompt focusing on visual data"""

    # Build prompt sections efficiently
    sections = []

    # 1. Visual Reference (Most Important)
    sections.append(f"""
    # VISUAL RECREATION TASK
    URL: {result.url}

    ## 📸 PRIMARY VISUAL REFERENCES
    - Desktop Screenshot: {len(result.primary_screenshot)} characters of base64 data
    - Annotated Screenshot: {len(result.annotated_screenshot)} characters with UI annotations
    - Responsive Previews: {len(result.responsive_previews)} breakpoints captured

    **CRITICAL**: Use these screenshots as your absolute reference for layout, colors, spacing, and visual hierarchy.
    """)
            
    # 2. Visual Hierarchy (Core Structure)
    if result.visual_hierarchy:
        sections.append(f"""
        ## 🏗️ VISUAL HIERARCHY & STRUCTURE
        {json.dumps(result.visual_hierarchy, indent=2)[:2000]}

    Use this hierarchy to structure your HTML semantically. Each section should be a proper HTML element.
    """)
    
    # 3. Design Tokens (Styling)
    if result.design_tokens:
        sections.append(f"""
        ## 🎨 DESIGN TOKENS
        {json.dumps(result.design_tokens, indent=2)[:1500]}

    Apply these tokens for consistent colors, typography, spacing, and effects throughout your recreation.
    """)
            
    # 4. Component Library (Reusable Elements)
    if result.component_library:
        sections.append(f"""
        ## 🧩 COMPONENT LIBRARY
        Found {len(result.component_library)} reusable components:
        {json.dumps(result.component_library[:3], indent=2)[:1500]}

    Implement these as reusable styled elements in your HTML.
    """)
            
    # 5. Layout Patterns (CSS Structure)
    if result.layout_patterns:
        sections.append(f"""
        ## 📐 LAYOUT PATTERNS
        {json.dumps(result.layout_patterns, indent=2)[:1000]}

    Use these patterns to implement proper CSS grid/flexbox layouts.
    """)
            
    # 6. Critical HTML/CSS (Base Structure)
    if result.critical_html:
        sections.append(f"""
        ## 🔧 CRITICAL HTML STRUCTURE
        {result.critical_html[:2000]}

    Use this as your base semantic structure.
    """)
            
    if result.critical_css:
        sections.append(f"""
        ## 💅 CRITICAL CSS
        {result.critical_css[:1500]}

    Apply these essential styles.
    """)
            
    # 7. Responsive Requirements
    if result.responsive_previews:
        breakpoints = list(result.responsive_previews.keys())
        sections.append(f"""
        ## 📱 RESPONSIVE REQUIREMENTS
        Breakpoints captured: {', '.join(breakpoints)}
    Use CSS media queries for responsive behavior.
    """)
            
    # 8. Implementation Checklist
    sections.append("""
    ## ✅ IMPLEMENTATION CHECKLIST
    1. Start with the primary screenshot as visual reference
    2. Use visual hierarchy for HTML structure
    3. Apply design tokens for consistent styling
    4. Implement components as shown in screenshots
    5. Make responsive using breakpoint data
    6. Add smooth hover effects and transitions
    7. Ensure accessibility with semantic HTML
    8. Test visual accuracy against screenshots

    Generate complete, production-ready HTML with inline CSS that precisely matches the visual references.
    """)
            
    return "\n".join(sections)
    
def _clean_generated_html(html: str) -> str:
        """Clean and validate generated HTML"""
        # Remove markdown code blocks
        if "```html" in html:
            html = html.split("```html")[1].split("```")[0].strip()
        elif "```" in html:
            # Handle generic code blocks
            parts = html.split("```")
            if len(parts) >= 3:
                html = parts[1].strip()
        
        # Ensure HTML starts with DOCTYPE
        if not html.strip().startswith("<!DOCTYPE"):
            if html.strip().startswith("<html"):
                html = "<!DOCTYPE html>\n" + html
        
        # Basic validation
        if not html.strip():
            return ""
        
        # Remove any extra whitespace
        lines = html.split('\n')
        cleaned_lines = []
        for line in lines:
            if line.strip():  # Skip empty lines
                cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)
    
def _create_fallback_html(result: ScrapingResult) -> str:
        """Create fallback HTML using scraped data"""
        
        # Extract basic info from scraped data
        colors = ["#ffffff", "#000000"]  # Default colors
        title = "Cloned Website"
        
        # Try to extract colors from design tokens
        if result.design_tokens and "colors" in result.design_tokens:
            color_data = result.design_tokens["colors"]
            if isinstance(color_data, dict) and "primary" in color_data:
                colors = [color_data["primary"], color_data.get("secondary", "#000000")]
            elif isinstance(color_data, list) and len(color_data) > 0:
                colors = color_data[:2]
        
        # Try to extract title from visual hierarchy
        if result.visual_hierarchy and "title" in result.visual_hierarchy:
            title = result.visual_hierarchy["title"]
        
        return f"""<!DOCTYPE html>
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
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        background-color: {colors[0]};
                        color: {colors[1]};
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
                        background: linear-gradient(135deg, {colors[0]}, {colors[1]}20);
                        border-radius: 10px;
                    }}
                    
                    h1 {{
                        font-size: 2.5rem;
                        margin-bottom: 10px;
                        color: {colors[1]};
                    }}
                    
                    .content {{
                        background: white;
                        padding: 30px;
                        border-radius: 10px;
                        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                    }}
                    
                    .error {{
                        background: #fee;
                        color: #c33;
                        padding: 20px;
                        border-radius: 5px;
                        margin-top: 20px;
                    }}
                    
                    @media (max-width: 768px) {{
                        .container {{
                            padding: 10px;
                        }}
                        
                        h1 {{
                            font-size: 2rem;
                        }}
                        
                        .content {{
                            padding: 20px;
                        }}
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>{title}</h1>
                        <p>Website Recreation</p>
                    </div>
                    
                    <div class="content">
                        <h2>Website Clone Generated</h2>
                        <p>This is a fallback version. The main generation process encountered an issue.</p>
                        
                        <div style="margin-top: 20px;">
                            <h3>Source Information:</h3>
                            <ul>
                                <li>Original URL: {result.url}</li>
                                <li>Visual Hierarchy: {'✓' if result.visual_hierarchy else '✗'}</li>
                                <li>Design Tokens: {'✓' if result.design_tokens else '✗'}</li>
                                <li>Components: {len(result.component_library) if result.component_library else 0} found</li>
                            </ul>
                        </div>
                    </div>
                </div>
            </body>
            </html>"""
    
def _create_error_html(url: str, error_message: str) -> str:
    """Create error HTML when scraping fails"""
    return f"""<!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Error - Website Clone</title>
            <style>
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}
                
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    background-color: #f5f5f5;
                    color: #333;
                    line-height: 1.6;
                    padding: 20px;
                }}
                
                .container {{
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                
                .error-box {{
                    background: #fee;
                    color: #c33;
                    padding: 30px;
                    border-radius: 10px;
                    text-align: center;
                    border: 1px solid #fcc;
                }}
                
                h1 {{
                    font-size: 2rem;
                    margin-bottom: 20px;
                }}
                
                .url {{
                    background: #f0f0f0;
                    padding: 10px;
                    border-radius: 5px;
                    margin: 20px 0;
                    font-family: monospace;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="error-box">
                    <h1>Website Cloning Error</h1>
                    <p>Failed to scrape and generate website</p>
                    <div class="url">{url}</div>
                    <p><strong>Error:</strong> {error_message}</p>
                </div>
            </div>
        </body>
        </html>"""



# result
@app.get("/api/clone/{job_id}/result")
async def get_clone_result(job_id: str):
    if job_id not in jobs_db:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs_db[job_id]

    if job.status != CloneStatus.COMPLETED:
        raise HTTPException(
            status_code=400, detail=f"Job not completed. Current status: {job.status}"
        )

    if not job.result_data:
        raise HTTPException(status_code=500, detail="No result data available")

    return {
        "job_id": job_id,
        "original_url": job.result_data["original_url"],
        "generated_html": job.result_data["generated_html"],
        "metadata": job.result_data["scraping_metadata"],
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
        "active_jobs": len(
            [
                job
                for job in jobs_db.values()
                if job.status not in [CloneStatus.COMPLETED, CloneStatus.FAILED]
            ]
        ),
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
    uvicorn.run("hello:app", host="127.0.0.1", port=8000, reload=True)


if __name__ == "__main__":
    main()
