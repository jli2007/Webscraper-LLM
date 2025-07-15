import asyncio
import random
import base64
import logging

# from browserbase import Browserbase
from urllib.parse import urlparse
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from pathlib import Path
from typing import List, Dict, Optional, TypedDict, Any
from dataclasses import dataclass
from playwright.async_api import async_playwright, Page

# CONFIGURE LOGGING
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# load dotenv
load_dotenv()

# HOLDS ALL INFORMATION SCRAPED FROM WEBSITE
@dataclass
class ScrapingResult:
    url: str
    # Visual-first approach
    primary_screenshot: str  # Main desktop screenshot
    annotated_screenshot: str  # Screenshot with element annotations
    responsive_previews: Dict[str, str]  # Key breakpoints only

    # Structured visual data
    visual_hierarchy: Dict[str, Any]  # Semantic structure
    design_tokens: Dict[str, Any]  # Colors, typography, spacing
    component_library: List[Dict[str, Any]]  # Reusable components
    layout_patterns: Dict[str, Any]  # Grid, flexbox patterns

    # Minimal but essential code
    critical_html: str  # Simplified, semantic HTML
    critical_css: str  # Only essential styles

    success: bool
    error_message: Optional[str] = None


class ViewportSize(TypedDict):
    width: int
    height: int


class WebScrape:
    logger.info("SCRAPING WEBSITE")

    def __init__(self, use_browserbase: bool = True, browserbase_api_key: str = ""):
        self.use_browserbase = use_browserbase
        self.browserbase_api_key = browserbase_api_key
        self.logger = logging.getLogger(__name__)

    async def scrape_website(self, url: str, max_retries: int = 3) -> ScrapingResult:
        for attempt in range(max_retries):
            try:
                logger.info(f"attempt {attempt} for {url} ")

                if not self._is_valid_url(url):
                    return self._create_error_result(url, "not valid")

                await self._initialize_browser()

                result = await self._perform_scraping(url)

                if result.success:
                    return result

            except Exception as e:
                logger.error(f"Scraping attempt {attempt + 1} failed: {str(e)}")
                if attempt == max_retries - 1:
                    return self._create_error_result(url, str(e))

                # sleep
                jitter = random.uniform(0, 1)
                await asyncio.sleep((2**attempt) + jitter)
            finally:
                await self._cleanup_browser()

        # fallback failure return
        return self._create_error_result(url, "Max retries exceeded")

    async def _initialize_browser(self):
        try:
            playwright = await async_playwright().start()

            if self.use_browserbase and self.browserbase_api_key:
                # Connect to Browserbase if given keys
                self.browser = await playwright.chromium.connect_over_cdp(
                    f"wss://connect.browserbase.com?apiKey={self.browserbase_api_key}"
                )
            else:
                # Launch local browser
                self.browser = await playwright.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--disable-web-security",
                        "--disable-features=VizDisplayCompositor",
                    ],
                )

            # Create context with mobile user agent for better compatibility
            self.context = await self.browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                record_video_dir="./videos/" if not self.use_browserbase else None,
                record_video_size={"width": 1920, "height": 1080},
            )

        except Exception as e:
            logger.error(f"Browser initialization failed: {str(e)}")
            raise

    async def _perform_scraping(self, url: str) -> ScrapingResult:
        try:
            if self.context:
                # Create new page
                page = await self.context.new_page()

            else:
                logger.error(f"self.context does not exist")
                raise RuntimeError("Browser context is not initialized")

            # Set up request/response interception for better asset tracking
            requests_log = []
            css_responses = []

            async def handle_request(request):
                requests_log.append(
                    {
                        "url": request.url,
                        "resource_type": request.resource_type,
                        "method": request.method,
                    }
                )

            async def handle_response(response):
                if response.request.resource_type == "stylesheet":
                    try:
                        css_content = await response.text()
                        css_responses.append(
                            {"url": response.url, "content": css_content}
                        )
                    except:
                        pass

            page.on("request", handle_request)
            page.on("response", handle_response)

            # console.log event handler
            page.on(
                "console",
                lambda msg: logger.info(
                    f"SCRIPT LOG [{msg.location.get('url', '')}]: {msg.text}"
                ),
            )

            # Navigate to URL with timeout
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)

            # INJECT SCRIPTS
            script_dir = Path(__file__).parent
            js_folder = script_dir / "webscripts"
            # logger.info(f"Looking in: {js_folder}, exists: {js_folder.exists()}, files: {list(js_folder.iterdir()) if js_folder.exists() else 'N/A'}")
            for js_file in js_folder.glob("*.js"):
                content = js_file.read_text()
                content += f"\n//# sourceURL={js_file.name}"  # append sourceURL so logs/errors reference this filename
                await page.add_script_tag(content=content)

            # 1. VISUAL-FIRST APPROACH
            screenshots = await self._capture_strategic_screenshots(page)

            # 2. EXTRACT VISUAL HIERARCHY
            visual_hierarchy = await self._extract_visual_hierarchy(page)

            # 3. EXTRACT DESIGN TOKENS
            design_tokens = await self._extract_design_tokens(page)

            # 4. IDENTIFY REUSABLE COMPONENTS
            components = await self._identify_components(page)

            # 5. ANALYZE LAYOUT PATTERNS
            layout_patterns = await self._analyze_layout_patterns(page)

            # 6. GENERATE CRITICAL HTML/CSS
            critical_html = await self._generate_critical_html(page)
            critical_css = await self._generate_critical_css(page)

            # 7. CREATE ANNOTATED SCREENSHOT
            annotated_screenshot = await self._create_annotated_screenshot(
                page, visual_hierarchy
            )

            await page.close()

            return ScrapingResult(
                url=url,
                primary_screenshot=screenshots["desktop"],
                annotated_screenshot=annotated_screenshot,
                responsive_previews=screenshots["responsive"],
                visual_hierarchy=visual_hierarchy,
                design_tokens=design_tokens,
                component_library=components,
                layout_patterns=layout_patterns,
                critical_html=critical_html,
                critical_css=critical_css,
                success=True,
            )

        except Exception as e:
            self.logger.error(f"scraping failed: {str(e)}")
            return self._create_error_result(url, "scrap")

    async def _capture_strategic_screenshots(self, page: Page) -> Dict[str, Any]:
        """Capture only the most important screenshots for visual cloning"""
        screenshots = {}

        # Primary desktop screenshot (1920x1080)
        await page.set_viewport_size({"width": 1920, "height": 1080})
        await page.wait_for_timeout(1000)

        primary_bytes = await page.screenshot(full_page=True, type="png")
        screenshots["desktop"] = base64.b64encode(primary_bytes).decode("utf-8")

        # Key responsive breakpoints only
        responsive = {}
        breakpoints: Dict[str, ViewportSize] = {
            "tablet": {"width": 768, "height": 1024},
            "mobile": {"width": 375, "height": 667},
        }

        for name, size in breakpoints.items():
            await page.set_viewport_size(size)
            await page.wait_for_timeout(1000)

            screenshot_bytes = await page.screenshot(full_page=True, type="png")
            responsive[name] = base64.b64encode(screenshot_bytes).decode("utf-8")

        screenshots["responsive"] = responsive
        return screenshots

    async def _extract_visual_hierarchy(self, page: Page) -> Dict[str, Any]:
        """Extract semantic visual structure"""
        return await page.evaluate("() => extract_visual_hierarchy()")

    async def _extract_design_tokens(self, page: Page) -> Dict[str, Any]:
        """Extract reusable design tokens"""
        return await page.evaluate("() => extract_design_tokens()")

    async def _identify_components(self, page: Page) -> List[Dict[str, Any]]:
        """Identify reusable UI components"""
        return await page.evaluate("() => identify_components()")

    async def _analyze_layout_patterns(self, page: Page) -> Dict[str, Any]:
        """Analyze layout patterns (grid, flexbox, etc.)"""
        return await page.evaluate("() => analyze_layout_patterns()")

    async def _generate_critical_html(self, page: Page) -> str:
        """Generate simplified, semantic HTML"""
        return await page.evaluate("() => generate_critical_html()")

    async def _generate_critical_css(self, page: Page) -> str:
        """Generate essential CSS rules"""
        return await page.evaluate("() => generate_critical_css()")

    async def _create_annotated_screenshot(
        self, page: Page, hierarchy: Dict[str, Any]
    ) -> str:
        """Create a screenshot with element annotations"""
        # Take base screenshot
        screenshot_bytes = await page.screenshot(full_page=True, type="png")

        # Convert to base64 for JavaScript processing
        screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")

        # Add annotations using JavaScript canvas overlay
        annotated_base64 = await page.evaluate(
            """
                (args) => {
                    const hierarchy = args.hierarchy;
                    const imageBase64 = args.imageBase64;
                    return new Promise((resolve) => {
                        const canvas = document.createElement('canvas');
                        const ctx = canvas.getContext('2d');
                        const img = new Image();
                        
                        img.onload = () => {
                            canvas.width = img.width;
                            canvas.height = img.height;
                            ctx.drawImage(img, 0, 0);
                            
                            // Add colored overlays for different sections
                            ctx.strokeStyle = 'rgba(255, 0, 0, 0.8)';
                            ctx.lineWidth = 3;
                            ctx.font = '16px Arial';
                            ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
                            
                            // Annotate header
                            if (hierarchy.header && hierarchy.header.bounds) {
                                const rect = hierarchy.header.bounds;
                                ctx.strokeRect(rect.x, rect.y, rect.width, rect.height);
                                ctx.fillRect(rect.x, rect.y - 25, 80, 25);
                                ctx.fillStyle = 'red';
                                ctx.fillText('HEADER', rect.x + 5, rect.y - 5);
                            }
                            
                            // Annotate navigation
                            if (hierarchy.navigation && hierarchy.navigation.bounds) {
                                const rect = hierarchy.navigation.bounds;
                                ctx.strokeStyle = 'rgba(0, 255, 0, 0.8)';
                                ctx.strokeRect(rect.x, rect.y, rect.width, rect.height);
                                ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
                                ctx.fillRect(rect.x, rect.y - 25, 80, 25);
                                ctx.fillStyle = 'green';
                                ctx.fillText('NAV', rect.x + 5, rect.y - 5);
                            }
                            
                            // Annotate main content sections
                            if (hierarchy.main_content && Array.isArray(hierarchy.main_content)) {
                                hierarchy.main_content.forEach((section, index) => {
                                    if (section.bounds) {
                                        const rect = section.bounds;
                                        ctx.strokeStyle = 'rgba(0, 0, 255, 0.8)';
                                        ctx.strokeRect(rect.x, rect.y, rect.width, rect.height);
                                        ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
                                        ctx.fillRect(rect.x, rect.y - 25, 100, 25);
                                        ctx.fillStyle = 'blue';
                                        ctx.fillText(`SECTION ${index + 1}`, rect.x + 5, rect.y - 5);
                                    }
                                });
                            }
                            
                            // Annotate hero section
                            if (hierarchy.hero_section && hierarchy.hero_section.bounds) {
                                const rect = hierarchy.hero_section.bounds;
                                ctx.strokeStyle = 'rgba(255, 165, 0, 0.8)';
                                ctx.strokeRect(rect.x, rect.y, rect.width, rect.height);
                                ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
                                ctx.fillRect(rect.x, rect.y - 25, 60, 25);
                                ctx.fillStyle = 'orange';
                                ctx.fillText('HERO', rect.x + 5, rect.y - 5);
                            }
                            
                            // Convert to base64
                            const base64 = canvas.toDataURL('image/png').split(',')[1];
                            resolve(base64);
                        };
                        
                        img.onerror = () => {
                            resolve(null);
                        };
                        
                        img.src = 'data:image/png;base64,' + imageBase64;
                    });
                }
            """,
            {"hierarchy": hierarchy, "imageBase64": screenshot_base64},
        )

        return annotated_base64 or screenshot_base64

    # CLEAN DOM
    def _clean_dom(self, html: str) -> str:
        try:
            soup = BeautifulSoup(html, "html.parser")

            # Remove scripts
            for script in soup.find_all("script"):
                script.decompose()

            # Remove style tags (we extract CSS separately)
            for style in soup.find_all("style"):
                style.decompose()

            # Remove comments
            for comment in soup.find_all(
                string=lambda text: isinstance(text, str)
                and text.strip().startswith("<!--")
            ):
                comment.extract()

            # Remove tracking elements
            tracking_selectors = [
                '[id*="analytics"]',
                '[class*="analytics"]',
                '[id*="tracking"]',
                '[class*="tracking"]',
                '[id*="gtm"]',
                '[class*="gtm"]',
                '[id*="facebook"]',
                '[class*="facebook"]',
            ]

            for selector in tracking_selectors:
                for element in soup.select(selector):
                    element.decompose()

            return str(soup)

        except Exception as e:
            logger.error(f"DOM cleaning failed: {str(e)}")
            return html

    # CHECK URL VALIDITY
    def _is_valid_url(self, url: str) -> bool:
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except:
            return False

    # ERROR RESULT
    def _create_error_result(self, url: str, error_message: str) -> ScrapingResult:
        return ScrapingResult(
            url=url,
            primary_screenshot="",
            annotated_screenshot="",
            responsive_previews={},
            visual_hierarchy={},
            design_tokens={},
            component_library=[],
            layout_patterns={},
            critical_html="",
            critical_css="",
            success=False,
            error_message=error_message,
        )

    # BROWSER CLEANUP
    async def _cleanup_browser(self):
        try:
            if self.context:
                await self.context.close()
                self.context = None
            if self.browser:
                await self.browser.close()
                self.browser = None
        except Exception as e:
            logger.error(f"Browser cleanup failed: {str(e)}")
