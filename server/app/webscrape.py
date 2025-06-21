import os
import requests
import asyncio
import random
import re
import base64
import logging
from browserbase import Browserbase
from urllib.parse import urlparse
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from pathlib import Path

# types
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
    screenshots: Dict[str, str]  # base64 images
    video_recording: Optional[str]
    dom_structure: str
    computed_styles: Dict[str, Any]
    visual_elements: Dict[str, Any]
    typography: Dict[str, bool]
    color_palette: List[str]
    layout_info: Dict[str, bool]
    assets: Dict[str, List[str]]  # urls
    metadata: Dict[str, bool]
    interaction_states: Dict[str, str]
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
        self.session = requests.Session()
        self.session.headers.update(
            {
                # sets a realistic browser User-Agent to avoid being blocked or misidentified by websites during scraping
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
        )

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
            await page.wait_for_timeout(3000)

            # INJECT SCRIPTS
            script_dir = Path(__file__).parent
            js_folder = script_dir / "webscripts"
            # logger.info(f"Looking in: {js_folder}, exists: {js_folder.exists()}, files: {list(js_folder.iterdir()) if js_folder.exists() else 'N/A'}")
            for js_file in js_folder.glob("*.js"):
                content = js_file.read_text()
                content += f"\n//# sourceURL={js_file.name}"  # append sourceURL so logs/errors reference this filename
                await page.add_script_tag(content=content)

            # Take screenshots at different viewport sizes
            screenshots = await self._capture_screenshots(page)

            # Capture interaction states
            interaction_states = await self._capture_interaction_states(page)

            # Detect visual elements
            visual_elements = await self._detect_visual_elements(page)

            # Extract DOM structure
            dom_structure = await page.content()

            # Extract CSS information
            computed_styles = await self._extract_computed_styles(page)

            # Extract color palette
            color_palette = await self._extract_color_palette(page)

            # Extract typography
            typography = await self._extract_typography(page)

            # Extract layout information
            layout_info = await self._extract_layout_info(page)

            # Extract assets from requests and DOM
            assets = await self._extract_assets(page, requests_log, url)

            # Extract metadata
            metadata = await self._extract_metadata(page)

            # Capture video recording
            video_recording = await self._get_video_recording(page)

            await page.close()

            return ScrapingResult(
                url=url,
                screenshots=screenshots,
                video_recording=video_recording,
                dom_structure=self._clean_dom(dom_structure),
                computed_styles=computed_styles,
                visual_elements=visual_elements,
                color_palette=color_palette,
                typography=typography,
                layout_info=layout_info,
                assets=assets,
                metadata=metadata,
                interaction_states=interaction_states,
                success=True,
            )

        except Exception as e:
            logger.error(f"Scraping execution failed: {str(e)}")
            return self._create_error_result(url, str(e))

    # SCREENSHOT DATA FROM WEBSITE
    async def _capture_screenshots(self, page: Page) -> Dict[str, str]:
        screenshots = {}

        viewports: Dict[str, ViewportSize] = {
            "desktop": {"width": 1920, "height": 1080},
            "desktop_wide": {"width": 2560, "height": 1440},
            "tablet": {"width": 768, "height": 1024},
            "tablet_landscape": {"width": 1024, "height": 768},
            "mobile": {"width": 375, "height": 667},
            "mobile_large": {"width": 414, "height": 896},
        }

        try:
            for viewport_name, viewport_size in viewports.items():
                await page.set_viewport_size(viewport_size)
                await page.wait_for_timeout(1000)

                # Full page screenshot
                screenshot_bytes = await page.screenshot(
                    full_page=True,
                    type="png",
                    animations="disabled",  # Consistent screenshots
                )
                screenshots[f"{viewport_name}_full"] = base64.b64encode(
                    screenshot_bytes
                ).decode("utf-8")

                # Above-the-fold screenshot
                above_fold_bytes = await page.screenshot(
                    type="png",
                    animations="disabled",
                    clip={
                        "x": 0,
                        "y": 0,
                        "width": viewport_size["width"],
                        "height": viewport_size["height"],
                    },
                )
                screenshots[f"{viewport_name}_fold"] = base64.b64encode(
                    above_fold_bytes
                ).decode("utf-8")

            return screenshots

        except Exception as e:
            logger.error(f"Screenshot capture failed: {str(e)}")
            return {}

    async def _capture_interaction_states(self, page: Page) -> Dict[str, str]:
        interaction_states = {}

        try:
            # Find interactive elements
            interactive_selectors = [
                "button",
                "a",
                "input",
                "select",
                "textarea",
                '[role="button"]',
                "[tabindex]",
                ".btn",
                ".button",
            ]

            for selector in interactive_selectors:
                elements = await page.query_selector_all(selector)

                for i, element in enumerate(
                    elements[:3]
                ):  # Limit to first 3 of each type
                    try:
                        # Scroll element into view
                        await element.scroll_into_view_if_needed()
                        await page.wait_for_timeout(500)

                        # Hover state
                        await element.hover()
                        await page.wait_for_timeout(500)

                        screenshot_bytes = await page.screenshot(type="png")
                        interaction_states[
                            f"{selector.replace('[', '').replace(']', '')}_{i}_hover"
                        ] = base64.b64encode(screenshot_bytes).decode("utf-8")

                    except Exception as e:
                        logger.debug(
                            f"Failed to capture interaction state for {selector}: {e}"
                        )
                        continue
            
            return interaction_states

        except Exception as e:
            logger.error(f"Interaction state capture failed: {str(e)}")
            return {}

    async def _extract_computed_styles(self, page: Page) -> Dict[str, Any]:
        try:
            # Extract all CSS info in a single page.evaluate call for better performance
            styles = await page.evaluate("() => extract_computed_styles()")

            return styles
        except Exception as e:
            logger.error(f"CSS extraction failed: {str(e)}")
            return {}

    async def _detect_visual_elements(self, page: Page) -> Dict[str, Any]:
        try:
            visual_elements = await page.evaluate("() => detect_visual_elements()")

        except Exception as e:
            logger.error(f"Visual element detection failed: {str(e)}")
            return {}

        return visual_elements

    async def _normalize_css_data(self, css_info: Dict) -> Dict:
        def clean_styles(styles):
            if not styles:
                return {}

            cleaned = {}
            for key, value in styles.items():
                if value and value not in [
                    "none",
                    "initial",
                    "inherit",
                    "unset",
                    "auto",
                ]:
                    # Convert rgb() to hex for colors
                    if "color" in key and value.startswith("rgb"):
                        try:
                            rgb_match = re.findall(r"\d+", value)
                            if len(rgb_match) >= 3:
                                r, g, b = map(int, rgb_match[:3])
                                value = f"#{r:02x}{g:02x}{b:02x}"
                        except:
                            pass

                    # Simplify font families
                    if key == "font-family":
                        value = value.split(",")[0].strip("\"'")

                    cleaned[key] = value

            return cleaned

        # Clean all style objects
        css_info["body_styles"] = clean_styles(css_info.get("body_styles"))
        css_info["header_styles"] = clean_styles(css_info.get("header_styles"))
        css_info["main_content_styles"] = clean_styles(
            css_info.get("main_content_styles")
        )

        # Clean common patterns
        if css_info.get("common_patterns"):
            cleaned_patterns = []
            for pattern in css_info["common_patterns"]:
                cleaned_pattern = {
                    "selector": pattern["selector"],
                    "styles": clean_styles(pattern["styles"]),
                    "count": pattern.get("count", 1),
                }
                if cleaned_pattern["styles"]:  # Only keep patterns with actual styles
                    cleaned_patterns.append(cleaned_pattern)
            css_info["common_patterns"] = cleaned_patterns[
                :15
            ]  # Limit to 15 most important

        return css_info

    # COLOR DATA FROM WEBSITE
    async def _extract_color_palette(self, page: Page) -> List[str]:
        try:
            colors = await page.evaluate("() => extract_color_palette()")

            print(f"Extracted {len(colors)} colors: {colors}")

            return (
                list(set(colors))[:15] if colors else ["#4a90e2", "#f39c12", "#e74c3c"]
            )

        except Exception as e:
            print(f"Error extracting colors: {e}")
            return ["#4a90e2", "#f39c12", "#e74c3c"]

    # TYPOGRAPHY FROM WEBSITE
    async def _extract_typography(self, page: Page) -> Dict[str, Any]:
        try:
            typography = await page.evaluate("() => extract_typography()")

            return typography

        except Exception as e:
            logger.error(f"Typography extraction failed: {str(e)}")
            return {"fonts": [], "headings": {}, "body_text": {}}

    # LAYOUT FROM WEBSITE
    async def _extract_layout_info(self, page: Page) -> Dict[str, Any]:
        try:
            layout = await page.evaluate("() => extract_layout_info()")

            return layout

        except Exception as e:
            logger.error(f"Layout extraction failed: {str(e)}")
            return {"structure": [], "grid_info": {}}

    # ASSETS FROM WEBSITE
    async def _extract_assets(
        self, page: Page, requests_log: List, base_url: str
    ) -> Dict[str, List[str]]:
        assets = {
            "images": [],
            "stylesheets": [],
            "fonts": [],
            "icons": [],
            "scripts": [],
        }

        try:
            # Extract from DOM
            dom_assets = await page.evaluate("() => extract_assets()")

            # Merge DOM assets
            for asset_type, urls in dom_assets.items():
                assets[asset_type].extend(urls)

            # Extract from network requests
            for request in requests_log:
                url = request["url"]
                resource_type = request["resource_type"]

                if resource_type == "image":
                    assets["images"].append(url)
                elif resource_type == "stylesheet":
                    assets["stylesheets"].append(url)
                elif resource_type == "font":
                    assets["fonts"].append(url)
                elif resource_type == "script":
                    assets["scripts"].append(url)

            # Remove duplicates and limit count
            for asset_type in assets:
                assets[asset_type] = list(set(assets[asset_type]))[:20]

            return assets

        except Exception as e:
            logger.error(f"Asset extraction failed: {str(e)}")
            return {}

    async def _extract_metadata(self, page: Page) -> Dict[str, Any]:
        try:
            metadata = await page.evaluate("() => extract_metadata()")

            return metadata

        except Exception as e:
            logger.error(f"Metadata extraction failed: {str(e)}")
            return {}

    # GET VIDEO RECORDING
    async def _get_video_recording(self, page: Page) -> Optional[str]:
        """Get video recording if available"""
        try:
            if hasattr(page, "video") and page.video:
                video_path = await page.video.path()
                if video_path and os.path.exists(video_path):
                    with open(video_path, "rb") as video_file:
                        video_bytes = video_file.read()
                    return base64.b64encode(video_bytes).decode("utf-8")
        except Exception as e:
            logger.debug(f"Video recording not available: {str(e)}")

        return None

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
            screenshots={},
            video_recording=None,
            dom_structure="",
            computed_styles={},
            visual_elements={},
            color_palette=[],
            typography={},
            layout_info={},
            assets={},
            metadata={},
            interaction_states={},
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
