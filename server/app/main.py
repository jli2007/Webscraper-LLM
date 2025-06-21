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
    use_browserbase=True,  # true to use browserbase (1hr cap total), false to use local
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
            },
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
            },
        )

        jobs_db[job_id].completed_at = str(datetime.now())
        jobs_db[job_id].result_data = {
            "original_url": url,
            "generated_html": generated_html,
            "scraping_metadata": {
                "colors_found": scraping_result.color_palette,
                "images_found": scraping_result.assets.get("images", []),
                "fonts_found": scraping_result.typography.get("fonts", []),
                "screenshots_taken": list(scraping_result.screenshots.keys()),
                "video_taken": scraping_result.video_recording,
                "layout_type": scraping_result.layout_info.get("type"),
                "interaction_states": scraping_result.interaction_states,
                "visual_elements": scraping_result.visual_elements,
                "dominant_color": (
                    scraping_result.color_palette[0]
                    if scraping_result.color_palette
                    else None
                ),
                "title": scraping_result.metadata.get("title"),
                "description": scraping_result.metadata.get("description"),
            },
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


async def process_scraping_data(scraping_result: ScrapingResult) -> Dict:
    # send to llm to re-create
    await asyncio.sleep(1)

    return {
        "url": scraping_result.url,
        "screenshots": scraping_result.screenshots,
        "video_recording": scraping_result.video_recording,
        "dom_structure": scraping_result.dom_structure[:10000],  # Limit size
        "computed_styles": scraping_result.computed_styles,
        "visual_elements": scraping_result.visual_elements,
        "color_palette": scraping_result.color_palette,
        "typography": scraping_result.typography,
        "layout_info": scraping_result.layout_info,
        "assets": scraping_result.assets,
        "metadata": scraping_result.metadata,
        "interaction_states": scraping_result.interaction_states,
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
                    Make it responsive and professional. Only return the HTML code, no explanations.""",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=10000,  # MAX TOKENS
            temperature=0.3,
        )

        generated_html = response.choices[0].message.content

        if generated_html is None:
            return ""

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
    """
    Create a comprehensive prompt for HTML generation using enhanced scraping data.
    Focuses on visual analysis and provides structured data for accurate recreation.
    """

    # Extract core information
    url = processed_data.get("url", "")
    screenshots = processed_data.get("screenshots", {})
    computed_styles = processed_data.get("computed_styles", {})
    visual_elements = processed_data.get("visual_elements", {})
    color_palette = processed_data.get("color_palette", [])
    typography = processed_data.get("typography", {})
    layout_info = processed_data.get("layout_info", {})
    assets = processed_data.get("assets", {})
    metadata = processed_data.get("metadata", {})
    interaction_states = processed_data.get("interaction_states", {})
    dom_structure = processed_data.get("dom_structure", "")

    # Build comprehensive prompt sections
    prompt_sections = []

    # Header section
    prompt_sections.append(
        f"""
# Website Recreation Task

Recreate the website at **{url}** as a complete HTML document with inline CSS. Use the comprehensive data below to build an accurate replica.
"""
    )

    # Visual Analysis Section (Most Important)
    if screenshots:
        screenshot_analysis = _build_screenshot_analysis(screenshots)
        prompt_sections.append(
            f"""
## 📸 Visual Analysis (PRIMARY REFERENCE)
{screenshot_analysis}

**CRITICAL:** Use the screenshots as your primary reference for layout, spacing, colors, and visual hierarchy. The screenshots show the ACTUAL appearance that must be replicated.
"""
        )

    # Design System Section
    design_system = _build_design_system(computed_styles, color_palette, typography)
    prompt_sections.append(
        f"""
## 🎨 Design System & Computed Styles
{design_system}
"""
    )

    # Component Analysis
    if visual_elements:
        component_analysis = _build_component_analysis(visual_elements)
        prompt_sections.append(
            f"""
## 🧩 Detected Components & Visual Elements
{component_analysis}
"""
        )

    # Layout & Structure
    layout_analysis = _build_layout_analysis(layout_info, dom_structure)
    prompt_sections.append(
        f"""
## 📐 Layout & Structure Analysis
{layout_analysis}
"""
    )

    # Interactive Elements
    if interaction_states:
        interaction_analysis = _build_interaction_analysis(interaction_states)
        prompt_sections.append(
            f"""
## ⚡ Interactive Elements & States
{interaction_analysis}
"""
        )

    # Assets & Resources
    if assets:
        asset_analysis = _build_asset_analysis(assets)
        prompt_sections.append(
            f"""
## 📁 Assets & Resources
{asset_analysis}
"""
        )

    # Metadata & SEO
    metadata_section = _build_metadata_section(metadata)
    prompt_sections.append(
        f"""
## 📋 Page Metadata
{metadata_section}
"""
    )

    # Implementation Requirements
    requirements = _build_requirements_section()
    prompt_sections.append(
        f"""
## ✅ Implementation Requirements
{requirements}
"""
    )

    # Quality Checklist
    checklist = _build_quality_checklist()
    prompt_sections.append(
        f"""
## 🔍 Quality Checklist
{checklist}
"""
    )

    return "\n".join(prompt_sections)


def _build_screenshot_analysis(screenshots: Dict) -> str:
    """Build detailed screenshot analysis section"""
    analysis = []

    # Prioritize screenshots by importance
    priority_order = [
        "desktop_full",
        "desktop_fold",
        "tablet_full",
        "mobile_full",
        "desktop_wide_full",
        "tablet_landscape_full",
        "mobile_large_full",
    ]

    available_screenshots = []
    for screenshot_key in priority_order:
        if screenshot_key in screenshots:
            available_screenshots.append(screenshot_key)

    # Add any remaining screenshots
    for key in screenshots:
        if key not in available_screenshots:
            available_screenshots.append(key)

    analysis.append(f"**Available Screenshots:** {len(screenshots)} viewports captured")
    analysis.append(f"**Primary Screenshots:** {', '.join(available_screenshots[:3])}")

    if available_screenshots:
        analysis.append(
            f"""
**Screenshot Analysis Instructions:**
- Use `{available_screenshots[0]}` as the primary reference for desktop layout
- Compare with `{available_screenshots[1] if len(available_screenshots) > 1 else 'mobile views'}` for responsive behavior
- Pay attention to spacing, typography scale, and visual hierarchy shown in screenshots
- Match colors, shadows, and visual effects exactly as they appear
"""
        )

    return "\n".join(analysis)


def _build_design_system(
    computed_styles: Dict, color_palette: List, typography: Dict
) -> str:
    """Build design system section with computed styles"""
    design_elements = []

    # Color Palette
    if color_palette:
        primary_colors = color_palette[:8]  # Top 8 colors
        design_elements.append(f"**Primary Colors:** {', '.join(primary_colors)}")

        # Suggest color usage
        if len(primary_colors) >= 3:
            design_elements.append(
                f"""
**Suggested Color Usage:**
- Primary: {primary_colors[0]}
- Secondary: {primary_colors[1]}
- Accent: {primary_colors[2]}
- Background: {primary_colors[-1] if len(primary_colors) > 3 else '#ffffff'}
"""
            )

    # Typography from computed styles
    if computed_styles:
        typography_info = _extract_typography_from_computed_styles(computed_styles)
        if typography_info:
            design_elements.append(f"**Typography System:**\n{typography_info}")

    # Additional typography data
    if typography:
        fonts = typography.get("fonts", [])
        if fonts:
            design_elements.append(f"**Detected Fonts:** {', '.join(fonts[:5])}")

        headings = typography.get("headings", {})
        if headings:
            design_elements.append(f"**Heading Styles:** {headings}")

    # Key element styles from computed styles
    if computed_styles:
        key_styles = _format_key_computed_styles(computed_styles)
        if key_styles:
            design_elements.append(f"**Key Element Styles:**\n{key_styles}")

    return "\n".join(design_elements)


def _build_component_analysis(visual_elements: Dict) -> str:
    """Analyze detected visual components"""
    components = []

    for component_type, elements in visual_elements.items():
        if elements and len(elements) > 0:
            components.append(f"**{component_type.title()}:** {len(elements)} detected")

            # Add details for key components
            if component_type == "buttons" and elements:
                button_styles = _analyze_button_components(elements[:3])  # Top 3
                if button_styles:
                    components.append(f"  Button Styles: {button_styles}")

            elif component_type == "cards" and elements:
                card_styles = _analyze_card_components(elements[:3])  # Top 3
                if card_styles:
                    components.append(f"  Card Styles: {card_styles}")

    return "\n".join(components) if components else "No specific components detected"


def _build_layout_analysis(layout_info: Dict, dom_structure: str) -> str:
    """Build layout analysis section"""
    layout_elements = []

    if layout_info:
        # Layout type and structure
        layout_type = layout_info.get("type", "unknown")
        layout_elements.append(f"**Layout Type:** {layout_type}")

        # Grid information
        grid_info = layout_info.get("grid_info", {})
        if grid_info:
            layout_elements.append(f"**Grid System:** {grid_info}")

        # Structure information
        structure = layout_info.get("structure", [])
        if structure:
            layout_elements.append(f"**Page Structure:** {', '.join(structure[:5])}")

    # DOM structure preview (cleaned and shortened)
    if dom_structure:
        cleaned_dom = _extract_dom_preview(dom_structure)
        layout_elements.append(
            f"**DOM Structure Preview:**\n```html\n{cleaned_dom}\n```"
        )

    return "\n".join(layout_elements)


def _build_interaction_analysis(interaction_states: Dict) -> str:
    """Build interaction states analysis"""
    interactions = []

    if interaction_states:
        interactions.append(
            f"**Captured States:** {len(interaction_states)} interaction states"
        )

        # Group by interaction type
        hover_states = [k for k in interaction_states.keys() if "hover" in k]
        focus_states = [k for k in interaction_states.keys() if "focus" in k]

        if hover_states:
            interactions.append(
                f"**Hover Effects:** {len(hover_states)} elements with hover states"
            )
        if focus_states:
            interactions.append(
                f"**Focus States:** {len(focus_states)} elements with focus states"
            )

        interactions.append(
            "**Implementation Note:** Recreate hover and focus effects as shown in interaction screenshots"
        )

    return "\n".join(interactions)


def _build_asset_analysis(assets: Dict) -> str:
    """Build assets analysis section"""
    asset_info = []

    for asset_type, asset_list in assets.items():
        if asset_list:
            asset_info.append(f"**{asset_type.title()}:** {len(asset_list)} files")

            # Show key assets
            if asset_type == "images" and asset_list:
                # Show first few image URLs
                key_images = asset_list[:3]
                asset_info.append(f"  Key Images: {', '.join(key_images)}")

            elif asset_type == "fonts" and asset_list:
                asset_info.append(f"  Font Files: {', '.join(asset_list[:3])}")

    return "\n".join(asset_info) if asset_info else "No external assets detected"


def _build_metadata_section(metadata: Dict) -> str:
    """Build metadata section"""
    meta_elements = []

    title = metadata.get("title", "Untitled Page")
    description = metadata.get("description", "No description available")

    meta_elements.append(f"**Title:** {title}")
    meta_elements.append(f"**Description:** {description}")

    # Additional metadata
    for key, value in metadata.items():
        if key not in ["title", "description"] and value:
            meta_elements.append(f"**{key.title()}:** {value}")

    return "\n".join(meta_elements)


def _build_requirements_section() -> str:
    """Build implementation requirements"""
    return """
1. **Complete HTML Document:** Include DOCTYPE, html, head, and body tags
2. **Inline CSS:** All styles must be inline (no external stylesheets)
3. **Responsive Design:** Must work on desktop, tablet, and mobile (use media queries)
4. **Visual Accuracy:** Match screenshots as closely as possible
5. **Interactive Elements:** Include hover effects and smooth transitions
6. **Semantic HTML:** Use proper HTML5 semantic elements
7. **Cross-browser Compatibility:** Ensure consistent appearance across browsers
8. **Performance:** Optimize for fast loading and smooth interactions
9. **Accessibility:** Include proper ARIA labels and semantic structure
10. **Modern CSS:** Use modern CSS features (flexbox, grid, custom properties)
"""


def _build_quality_checklist() -> str:
    """Build quality checklist"""
    return """
Before submitting, verify:
- [ ] Visual appearance matches screenshots
- [ ] Colors match the extracted palette
- [ ] Typography matches computed styles
- [ ] Layout is responsive across all viewports
- [ ] Interactive elements have proper hover/focus states
- [ ] All images and assets are properly referenced
- [ ] HTML is semantic and accessible
- [ ] CSS is clean and well-organized
- [ ] No console errors or warnings
- [ ] Smooth animations and transitions
"""


# Helper functions for data processing
def _extract_typography_from_computed_styles(computed_styles: Dict) -> str:
    """Extract typography information from computed styles"""
    typography = []

    for selector, styles in computed_styles.items():
        if isinstance(styles, dict):
            font_info = []

            if styles.get("fontSize"):
                font_info.append(f"size: {styles['fontSize']}")
            if styles.get("fontFamily"):
                font_info.append(f"family: {styles['fontFamily']}")
            if styles.get("fontWeight"):
                font_info.append(f"weight: {styles['fontWeight']}")
            if styles.get("lineHeight"):
                font_info.append(f"line-height: {styles['lineHeight']}")

            if font_info:
                typography.append(f"  {selector}: {', '.join(font_info)}")

    return "\n".join(typography)


def _format_key_computed_styles(computed_styles: Dict) -> str:
    """Format key computed styles for display"""
    formatted_styles = []

    priority_selectors = ["body", "h1", "h2", "h3", "p", "button", "a"]

    for selector in priority_selectors:
        if selector in computed_styles:
            styles = computed_styles[selector]
            if isinstance(styles, dict):
                style_parts = []

                # Key style properties
                key_props = [
                    "color",
                    "backgroundColor",
                    "fontSize",
                    "fontFamily",
                    "padding",
                    "margin",
                    "borderRadius",
                ]

                for prop in key_props:
                    if styles.get(prop) and styles[prop] not in [
                        "none",
                        "initial",
                        "inherit",
                    ]:
                        style_parts.append(f"{prop}: {styles[prop]}")

                if style_parts:
                    formatted_styles.append(f"  {selector}: {'; '.join(style_parts)}")

    return "\n".join(formatted_styles)


def _analyze_button_components(buttons: List) -> str:
    """Analyze button components"""
    if not buttons:
        return ""

    button_analysis = []
    for i, button in enumerate(buttons[:2]):  # Analyze first 2 buttons
        styles = button.get("styles", {})
        dimensions = button.get("dimensions", {})

        style_info = []
        if styles.get("backgroundColor"):
            style_info.append(f"bg: {styles['backgroundColor']}")
        if styles.get("borderRadius"):
            style_info.append(f"radius: {styles['borderRadius']}")
        if dimensions.get("width") and dimensions.get("height"):
            style_info.append(f"size: {dimensions['width']}x{dimensions['height']}")

        if style_info:
            button_analysis.append(f"Button {i+1}: {', '.join(style_info)}")

    return "; ".join(button_analysis)


def _analyze_card_components(cards: List) -> str:
    """Analyze card components"""
    if not cards:
        return ""

    card_analysis = []
    for i, card in enumerate(cards[:2]):  # Analyze first 2 cards
        styles = card.get("styles", {})
        dimensions = card.get("dimensions", {})

        style_info = []
        if styles.get("borderRadius"):
            style_info.append(f"radius: {styles['borderRadius']}")
        if styles.get("boxShadow"):
            style_info.append(f"shadow: {styles['boxShadow'][:30]}...")
        if dimensions.get("width") and dimensions.get("height"):
            style_info.append(f"size: {dimensions['width']}x{dimensions['height']}")

        if style_info:
            card_analysis.append(f"Card {i+1}: {', '.join(style_info)}")

    return "; ".join(card_analysis)


def _extract_dom_preview(dom_structure: str) -> str:
    """Extract a clean preview of DOM structure"""
    try:

        soup = BeautifulSoup(dom_structure, "html.parser")

        # Extract main structure elements
        preview_elements = []

        # Get main structural elements
        for tag in ["header", "nav", "main", "section", "article", "aside", "footer"]:
            elements = soup.find_all(tag)
            for elem in elements[:2]:  # Max 2 of each
                # Only process Tag objects, skip NavigableString and other types
                if isinstance(elem, Tag):
                    # Simplify the element
                    elem_preview = f"<{elem.name}"
                    if elem.get("class"):
                        elem_preview += (
                            f' class="{" ".join(elem["class"][:2])}"'  # Max 2 classes
                        )
                    if elem.get("id"):
                        elem_preview += f' id="{elem["id"]}"'
                    elem_preview += ">"
                    preview_elements.append(elem_preview)

        # Limit preview length
        preview = "\n".join(preview_elements[:10])
        return preview[:500] + "..." if len(preview) > 500 else preview

    except Exception:
         # Fallback to simple text truncation
        return dom_structure[:500] + "..."


# FALLBACK HTML IF GENERATION FAILS
def create_fallback_html(processed_data: Dict) -> str:
    colors = processed_data.get("color_palette", ["#ffffff", "#000000"])
    fonts = processed_data.get("typography", {}).get("fonts", ["Arial", "sans-serif"])
    title = processed_data.get("metadata", {}).get("title", "Cloned Website")

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
