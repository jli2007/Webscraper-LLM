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
    dom_structure: str
    extracted_css: Dict[str, bool]
    typography: Dict[str, bool]
    color_palette: List[str]
    layout_info: Dict[str, bool]
    assets: Dict[str, List[str]] # urls
    metadata: Dict[str, bool]
    success: bool
    error_message: Optional[str] = None

class ViewportSize(TypedDict):
    width: int
    height: int
    
class WebScrape:
    logger.info("scraping website")
    
    def __init__(self, use_browserbase: bool = True, browserbase_api_key: str = ""):
        self.use_browserbase = use_browserbase
        self.browserbase_api_key = browserbase_api_key
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })

        
    async def scrape_website(self, url: str, max_retries: int = 3) -> ScrapingResult:
        for attempt in range(max_retries):
            try:
                logger.info(f"attempt {attempt} for {url} ")
                
                if not self._is_valid_url(url):
                    return self._create_error_result(url, "not valid");
                
                await self._initialize_browser()

                result = await self._perform_scraping(url)
                
                if result.success:
                    return result
                
            except Exception as e:
                logger.error(f"Scraping attempt {attempt + 1} failed: {str(e)}")
                if attempt == max_retries - 1:
                    return self._create_error_result(url, str(e));
                
                
                # sleep
                jitter = random.uniform(0, 1)
                await asyncio.sleep((2 ** attempt) + jitter) 
            finally:
                await self._cleanup_browser()
        
        # fallback failure
        return ScrapingResult(
            url=url, screenshots={}, dom_structure="", 
            extracted_css={}, color_palette=[], typography={}, 
            layout_info={}, assets={}, metadata={},
            success=False, error_message="Max retries exceeded"
        )
        
    async def _initialize_browser(self):
        try:
            playwright = await async_playwright().start()
            
            if self.use_browserbase and self.browserbase_api_key:
                # Connect to Browserbase
                self.browser = await playwright.chromium.connect_over_cdp(
                    f"wss://connect.browserbase.com?apiKey={self.browserbase_api_key}"
                )
            else:
                # Launch local browser
                self.browser = await playwright.chromium.launch(
                    headless=True,
                    args=[
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                        '--disable-web-security',
                        '--disable-features=VizDisplayCompositor'
                    ]
                )
            
            # Create context with mobile user agent for better compatibility
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
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
                logger.error(f"self.context does not exist???")
                raise RuntimeError("Browser context is not initialized")
            
            # Set up request/response interception for better asset tracking
            requests_log = []
            
            async def handle_request(request):
                requests_log.append({
                    'url': request.url,
                    'resource_type': request.resource_type,
                    'method': request.method
                })
            
            page.on('request', handle_request)
            
            # Navigate to URL with timeout
            await page.goto(url, wait_until='networkidle', timeout=30000)
            
            # Wait for page to be fully loaded
            await page.wait_for_timeout(2000)
            
            # Take screenshots at different viewport sizes
            screenshots = await self._capture_screenshots(page)
            
            # Extract DOM structure
            dom_structure = await page.content()
            
            # Extract CSS information
            extracted_css = await self._extract_css_info(page)
            
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
      
            await page.close()
            
            return ScrapingResult(
                url=url,
                screenshots=screenshots,
                dom_structure=self._clean_dom(dom_structure),
                extracted_css=extracted_css,
                color_palette=color_palette,
                typography=typography,
                layout_info=layout_info,
                assets=assets,
                metadata=metadata,
                success=True
            )
            
        except Exception as e:
            logger.error(f"Scraping execution failed: {str(e)}")
            return self._create_error_result(url, str(e))
    
    # SCREENSHOT DATA FROM WEBSITE  
    async def _capture_screenshots(self, page: Page) -> Dict[str, str]:
        screenshots = {}
        
        viewports: Dict[str, ViewportSize] = {
            "desktop": {"width": 1920, "height": 1080},
            "tablet": {"width": 768, "height": 1024},
            "mobile": {"width": 375, "height": 667}
        }
        
        try:
            for viewport_name, viewport_size in viewports.items():
                # Set viewport
                await page.set_viewport_size(viewport_size)
                await page.wait_for_timeout(1000)
                
                # Take full page screenshot
                screenshot_bytes = await page.screenshot(
                    full_page=True,
                    type='png'
                )
                
                # Convert to base64
                screenshots[viewport_name] = base64.b64encode(screenshot_bytes).decode('utf-8')
                
        except Exception as e:
            logger.error(f"Screenshot capture failed: {str(e)}")
        
        return screenshots

    
    async def _extract_css_info(self, page: Page) -> Dict[str, Any]:
        css_info = {
            "body_styles": {},
            "header_styles": {},
            "main_content_styles": {},
            "common_patterns": [],
            "layout_info": {},
            "responsive_breakpoints": [],
            "animations": []
        }
        
        try:
            # Extract all CSS info in a single page.evaluate call for better performance
            extracted_data = await page.evaluate("""
                () => {
                    const getComputedStyles = (element, properties) => {
                        if (!element) return null;
                        const styles = window.getComputedStyle(element);
                        const result = {};
                        properties.forEach(prop => {
                            result[prop] = styles[prop];
                        });
                        return result;
                    };
                    
                    const importantProps = [
                        'background-color', 'font-family', 'font-size', 'font-weight',
                        'line-height', 'color', 'margin', 'padding', 'display',
                        'position', 'width', 'height', 'border', 'border-radius',
                        'box-shadow', 'text-align', 'flex-direction', 'justify-content',
                        'align-items', 'grid-template-columns', 'z-index'
                    ];
                    
                    const result = {
                        body_styles: getComputedStyles(document.body, importantProps),
                        header_styles: getComputedStyles(document.querySelector('header, .header, [role="banner"]'), importantProps),
                        main_content_styles: getComputedStyles(document.querySelector('main, .main, .content, #content'), importantProps),
                        common_patterns: [],
                        layout_info: {},
                        responsive_breakpoints: [],
                        animations: []
                    };
                    
                    // Extract common element styles
                    const selectors = [
                        'h1', 'h2', 'h3', 'h4', 'p', 'a', 'button', 'input',
                        '.container', '.wrapper', '.content', '.header', '.footer',
                        'nav', '.nav', '.menu', '.btn', '.card', '.hero'
                    ];
                    
                    selectors.forEach(selector => {
                        const elements = document.querySelectorAll(selector);
                        if (elements.length > 0) {
                            const styles = getComputedStyles(elements[0], importantProps);
                            if (styles) {
                                result.common_patterns.push({
                                    selector: selector,
                                    styles: styles,
                                    count: elements.length
                                });
                            }
                        }
                    });
                    
                    // Extract layout information
                    const body = document.body;
                    const bodyStyles = window.getComputedStyle(body);
                    result.layout_info = {
                        layout_type: bodyStyles.display === 'flex' ? 'flexbox' : 
                                    bodyStyles.display === 'grid' ? 'grid' : 'block',
                        max_width: bodyStyles.maxWidth,
                        container_width: document.querySelector('.container, .wrapper, main')?.offsetWidth || body.offsetWidth,
                        has_sidebar: !!document.querySelector('.sidebar, .side-nav, aside'),
                        is_responsive: window.innerWidth !== document.documentElement.scrollWidth
                    };
                    
                    // Extract CSS custom properties (CSS variables)
                    const rootStyles = window.getComputedStyle(document.documentElement);
                    const cssVars = {};
                    for (let i = 0; i < rootStyles.length; i++) {
                        const prop = rootStyles.item(i);
                        if (prop.startsWith('--')) {
                            cssVars[prop] = rootStyles.getPropertyValue(prop).trim();
                        }
                    }
                    result.css_variables = cssVars;
                    
                    // Detect animations
                    const animatedElements = document.querySelectorAll('*');
                    const animations = [];
                    animatedElements.forEach(el => {
                        const styles = window.getComputedStyle(el);
                        if (styles.animationName !== 'none' || styles.transitionProperty !== 'none') {
                            animations.push({
                                selector: el.tagName.toLowerCase() + (el.className ? '.' + el.className.split(' ')[0] : ''),
                                animation: styles.animationName,
                                transition: styles.transitionProperty,
                                duration: styles.animationDuration || styles.transitionDuration
                            });
                        }
                    });
                    result.animations = animations.slice(0, 10); // Limit to 10
                    
                    // Extract media query breakpoints from stylesheets
                    const breakpoints = new Set();
                    try {
                        Array.from(document.styleSheets).forEach(sheet => {
                            try {
                                Array.from(sheet.cssRules || sheet.rules || []).forEach(rule => {
                                    if (rule.type === CSSRule.MEDIA_RULE) {
                                        const mediaText = rule.media.mediaText;
                                        const widthMatch = mediaText.match(/\\((min|max)-width:\\s*(\\d+)px\\)/);
                                        if (widthMatch) {
                                            breakpoints.add(parseInt(widthMatch[2]));
                                        }
                                    }
                                });
                            } catch (e) {
                                // Cross-origin stylesheets may throw errors
                            }
                        });
                    } catch (e) {
                        // Fallback to common breakpoints
                        [768, 1024, 1200, 1400].forEach(bp => breakpoints.add(bp));
                    }
                    result.responsive_breakpoints = Array.from(breakpoints).sort((a, b) => a - b);
                    
                    return result;
                }
            """)
            
            # Merge extracted data
            css_info.update(extracted_data)
            
            # Clean up null values and normalize data
            css_info = self._normalize_css_data(css_info)
            
        except Exception as e:
            logger.error(f"CSS extraction failed: {str(e)}")
        
        return css_info

    def _normalize_css_data(self, css_info: Dict) -> Dict:
        def clean_styles(styles):
            if not styles:
                return {}
            
            cleaned = {}
            for key, value in styles.items():
                if value and value not in ['none', 'initial', 'inherit', 'unset', 'auto']:
                    # Convert rgb() to hex for colors
                    if 'color' in key and value.startswith('rgb'):
                        try:
                            rgb_match = re.findall(r'\d+', value)
                            if len(rgb_match) >= 3:
                                r, g, b = map(int, rgb_match[:3])
                                value = f"#{r:02x}{g:02x}{b:02x}"
                        except:
                            pass
                    
                    # Simplify font families
                    if key == 'font-family':
                        value = value.split(',')[0].strip('"\'')
                    
                    cleaned[key] = value
            
            return cleaned
        
        # Clean all style objects
        css_info['body_styles'] = clean_styles(css_info.get('body_styles'))
        css_info['header_styles'] = clean_styles(css_info.get('header_styles'))
        css_info['main_content_styles'] = clean_styles(css_info.get('main_content_styles'))
        
        # Clean common patterns
        if css_info.get('common_patterns'):
            cleaned_patterns = []
            for pattern in css_info['common_patterns']:
                cleaned_pattern = {
                    'selector': pattern['selector'],
                    'styles': clean_styles(pattern['styles']),
                    'count': pattern.get('count', 1)
                }
                if cleaned_pattern['styles']:  # Only keep patterns with actual styles
                    cleaned_patterns.append(cleaned_pattern)
            css_info['common_patterns'] = cleaned_patterns[:15]  # Limit to 15 most important
        
        return css_info

    # COLOR DATA FROM WEBSITE
    async def _extract_color_palette(self, page: Page) -> List[str]:
        try:
            colors = await page.evaluate("""
                () => {
                    const colors = new Set();
                    
                    // Helper to normalize colors to hex
                    function normalizeColor(color) {
                        if (!color || color === 'transparent' || color === 'none') return null;
                        
                        // Already hex?
                        if (color.startsWith('#')) {
                            return color.length === 4 ? 
                                color.replace(/./g, (c, i) => i ? c + c : c) : color;
                        }
                        
                        // Handle rgb/rgba
                        const rgbMatch = color.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)(?:,\\s*([\\d.]+))?\\)/);
                        if (rgbMatch) {
                            const [, r, g, b, a] = rgbMatch;
                            
                            // Skip very transparent colors
                            if (a !== undefined && parseFloat(a) < 0.3) return null;
                            
                            const toHex = n => parseInt(n).toString(16).padStart(2, '0');
                            return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
                        }
                        
                        // Handle named colors
                        const namedColors = {
                            'red': '#ff0000', 'blue': '#0000ff', 'green': '#008000',
                            'yellow': '#ffff00', 'orange': '#ffa500', 'purple': '#800080',
                            'pink': '#ffc0cb', 'brown': '#a52a2a', 'gray': '#808080',
                            'grey': '#808080', 'cyan': '#00ffff', 'magenta': '#ff00ff'
                        };
                        
                        return namedColors[color.toLowerCase()] || null;
                    }
                    
                    // 1. Extract from all elements with explicit colors
                    console.log('Scanning elements...');
                    const allElements = document.querySelectorAll('*');
                    
                    Array.from(allElements).forEach((element, index) => {
                        if (index > 500) return; // Limit for performance
                        
                        const styles = window.getComputedStyle(element);
                        const rect = element.getBoundingClientRect();
                        
                        // Only check visible elements
                        if (rect.width > 5 && rect.height > 5) {
                            const colorProps = [
                                styles.backgroundColor,
                                styles.color,
                                styles.borderTopColor,
                                styles.borderRightColor,
                                styles.borderBottomColor,
                                styles.borderLeftColor,
                                styles.outlineColor,
                                styles.textDecorationColor,
                                styles.caretColor,
                                styles.columnRuleColor
                            ];
                            
                            colorProps.forEach(color => {
                                const normalized = normalizeColor(color);
                                if (normalized && normalized !== '#000000' && normalized !== '#ffffff') {
                                    colors.add(normalized);
                                    console.log(`Found color: ${normalized} on element:`, element.tagName);
                                }
                            });
                            
                            // Check for background images with gradients!!
                            const bgImage = styles.backgroundImage;
                            if (bgImage && bgImage !== 'none') {
                                // Extract colors from gradients
                                const gradientColors = bgImage.match(/#[0-9a-fA-F]{3,6}|rgb\\([^)]+\\)|rgba\\([^)]+\\)/g);
                                if (gradientColors) {
                                    gradientColors.forEach(color => {
                                        const normalized = normalizeColor(color);
                                        if (normalized) {
                                            colors.add(normalized);
                                            console.log(`Found gradient color: ${normalized}`);
                                        }
                                    });
                                }
                            }
                        }
                    });
                    
                    // 2. Extract from inline styles
                    console.log('Scanning inline styles...');
                    const elementsWithStyle = document.querySelectorAll('[style]');
                    elementsWithStyle.forEach(element => {
                        const style = element.getAttribute('style');
                        const colorMatches = style.match(/#[0-9a-fA-F]{3,6}|rgb\\([^)]+\\)|rgba\\([^)]+\\)/g);
                        if (colorMatches) {
                            colorMatches.forEach(color => {
                                const normalized = normalizeColor(color);
                                if (normalized) {
                                    colors.add(normalized);
                                    console.log(`Found inline style color: ${normalized}`);
                                }
                            });
                        }
                    });
                    
                    // 3. Extract from CSS stylesheets
                    console.log('Scanning stylesheets...');
                    try {
                        Array.from(document.styleSheets).forEach(sheet => {
                            try {
                                const rules = sheet.cssRules || sheet.rules || [];
                                Array.from(rules).forEach(rule => {
                                    if (rule.cssText) {
                                        const colorMatches = rule.cssText.match(/#[0-9a-fA-F]{3,6}|rgb\\([^)]+\\)|rgba\\([^)]+\\)/g);
                                        if (colorMatches) {
                                            colorMatches.forEach(color => {
                                                const normalized = normalizeColor(color);
                                                if (normalized && normalized !== '#000000' && normalized !== '#ffffff') {
                                                    colors.add(normalized);
                                                    console.log(`Found CSS color: ${normalized}`);
                                                }
                                            });
                                        }
                                    }
                                });
                            } catch (e) {
                                // Skip CORS-restricted stylesheets
                            }
                        });
                    } catch (e) {
                        console.log('Could not access stylesheets');
                    }
         
                    const finalColors = Array.from(colors);
                    console.log(`Total unique colors found: ${finalColors.length}`, finalColors);
                    
                    return finalColors.slice(0, 20);
                }
            """)
            
            print(f"Extracted {len(colors)} colors: {colors}")
            
            return list(set(colors))[:15] if colors else ['#4a90e2', '#f39c12', '#e74c3c']
            
        except Exception as e:
            print(f"Error extracting colors: {e}")
            return ['#4a90e2', '#f39c12', '#e74c3c']
    
    # TYPOGRAPHY FROM WEBSITE     
    async def _extract_typography(self, page: Page) -> Dict[str, Any]:
        try:
            typography = await page.evaluate("""
                () => {
                    const fonts = new Set();
                    const headings = {};
                    const bodyText = {};
                    
                    // Extract font families
                    const elements = Array.from(document.querySelectorAll('*')).slice(0, 50);
                    elements.forEach(element => {
                        const fontFamily = window.getComputedStyle(element).fontFamily;
                        if (fontFamily) fonts.add(fontFamily);
                    });
                    
                    // Extract heading styles
                    for (let i = 1; i <= 6; i++) {
                        const heading = document.querySelector(`h${i}`);
                        if (heading) {
                            const styles = window.getComputedStyle(heading);
                            headings[`h${i}`] = {
                                'font-size': styles.fontSize,
                                'font-weight': styles.fontWeight,
                                'line-height': styles.lineHeight,
                                'margin': styles.margin,
                                'font-family': styles.fontFamily
                            };
                        }
                    }
                    
                    // Extract body text styles
                    const paragraph = document.querySelector('p');
                    if (paragraph) {
                        const styles = window.getComputedStyle(paragraph);
                        bodyText = {
                            'font-size': styles.fontSize,
                            'line-height': styles.lineHeight,
                            'font-weight': styles.fontWeight,
                            'font-family': styles.fontFamily
                        };
                    }
                    
                    return {
                        fonts: Array.from(fonts),
                        headings: headings,
                        body_text: bodyText
                    };
                }
            """)
            
            return typography
            
        except Exception as e:
            logger.error(f"Typography extraction failed: {str(e)}")
            return {"fonts": [], "headings": {}, "body_text": {}}

    # LAYOUT FROM WEBSITE
    async def _extract_layout_info(self, page: Page) -> Dict[str, Any]:
        try:
            layout = await page.evaluate("""
                () => {
                    const structure = [];
                    const gridInfo = {};
                    
                    // Identify main structural elements
                    const structuralTags = ['header', 'nav', 'main', 'section', 'aside', 'footer', 'article'];
                    
                    structuralTags.forEach(tag => {
                        const elements = document.querySelectorAll(tag);
                        if (elements.length > 0) {
                            structure.push({
                                tag: tag,
                                count: elements.length,
                                classes: Array.from(elements).slice(0, 3).map(el => 
                                    el.className ? el.className.split(' ') : []
                                )
                            });
                        }
                    });
                    
                    // Check for grid/flexbox layouts
                    const allElements = Array.from(document.querySelectorAll('*')).slice(0, 30);
                    allElements.forEach(element => {
                        const styles = window.getComputedStyle(element);
                        const display = styles.display;
                        
                        if (display === 'grid' || display === 'flex') {
                            const tagName = element.tagName.toLowerCase();
                            const className = element.className || 'no-class';
                            
                            gridInfo[`${tagName}.${className}`] = {
                                display: display,
                                'justify-content': styles.justifyContent,
                                'align-items': styles.alignItems,
                                'grid-template-columns': styles.gridTemplateColumns,
                                'flex-direction': styles.flexDirection
                            };
                        }
                    });
                    
                    return {
                        structure: structure,
                        grid_info: gridInfo
                    };
                }
            """)
            
            return layout
            
        except Exception as e:
            logger.error(f"Layout extraction failed: {str(e)}")
            return {"structure": [], "grid_info": {}}

    
    # ASSETS FROM WEBSITE
    async def _extract_assets(self, page: Page, requests_log: List, base_url: str) -> Dict[str, List[str]]:
        assets = {
            "images": [],
            "stylesheets": [],
            "fonts": [],
            "icons": [],
            "scripts": []
        }
        
        try:
            # Extract from DOM
            dom_assets = await page.evaluate("""
                () => {
                    const assets = {
                        images: [],
                        stylesheets: [],
                        fonts: [],
                        icons: [],
                        scripts: []
                    };
                    
                    // Images
                    document.querySelectorAll('img').forEach(img => {
                        if (img.src) assets.images.push(img.src);
                    });
                    
                    // Stylesheets
                    document.querySelectorAll('link[rel="stylesheet"]').forEach(link => {
                        if (link.href) assets.stylesheets.push(link.href);
                    });
                    
                    // Fonts
                    document.querySelectorAll('link').forEach(link => {
                        const href = link.href || '';
                        if (href.includes('fonts') || href.includes('font')) {
                            assets.fonts.push(href);
                        }
                    });
                    
                    // Icons
                    document.querySelectorAll('link[rel*="icon"]').forEach(link => {
                        if (link.href) assets.icons.push(link.href);
                    });
                    
                    // Scripts
                    document.querySelectorAll('script[src]').forEach(script => {
                        if (script.src) assets.scripts.push(script.src);
                    });
                    
                    return assets;
                }
            """)
            
            # Merge DOM assets
            for asset_type, urls in dom_assets.items():
                assets[asset_type].extend(urls)
            
            # Extract from network requests
            for request in requests_log:
                url = request['url']
                resource_type = request['resource_type']
                
                if resource_type == 'image':
                    assets['images'].append(url)
                elif resource_type == 'stylesheet':
                    assets['stylesheets'].append(url)
                elif resource_type == 'font':
                    assets['fonts'].append(url)
                elif resource_type == 'script':
                    assets['scripts'].append(url)
            
            # Remove duplicates and limit count
            for asset_type in assets:
                assets[asset_type] = list(set(assets[asset_type]))[:20]
                
        except Exception as e:
            logger.error(f"Asset extraction failed: {str(e)}")
        
        return assets
    
    async def _extract_metadata(self, page: Page) -> Dict[str, Any]:
        try:
            metadata = await page.evaluate("""
                () => {
                    const meta = {
                        title: '',
                        description: '',
                        keywords: '',
                        viewport: '',
                        charset: '',
                        og_data: {}
                    };
                    
                    // Title
                    const title = document.querySelector('title');
                    if (title) meta.title = title.textContent.trim();
                    
                    // Meta tags
                    document.querySelectorAll('meta').forEach(metaTag => {
                        const name = metaTag.getAttribute('name') || '';
                        const property = metaTag.getAttribute('property') || '';
                        const content = metaTag.getAttribute('content') || '';
                        
                        if (name.toLowerCase() === 'description') {
                            meta.description = content;
                        } else if (name.toLowerCase() === 'keywords') {
                            meta.keywords = content;
                        } else if (name.toLowerCase() === 'viewport') {
                            meta.viewport = content;
                        } else if (metaTag.hasAttribute('charset')) {
                            meta.charset = metaTag.getAttribute('charset');
                        } else if (property.startsWith('og:')) {
                            meta.og_data[property] = content;
                        }
                    });
                    
                    return meta;
                }
            """)
            
            return metadata
            
        except Exception as e:
            logger.error(f"Metadata extraction failed: {str(e)}")
            return {}
        
    def _clean_dom(self, html: str) -> str:
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Remove scripts
            for script in soup.find_all("script"):
                script.decompose()
            
            # Remove style tags (we extract CSS separately)
            for style in soup.find_all("style"):
                style.decompose()
            
            # Remove comments
            for comment in soup.find_all(string=lambda text: isinstance(text, str) and text.strip().startswith('<!--')):
                comment.extract()
            
            # Remove tracking elements
            tracking_selectors = [
                '[id*="analytics"]', '[class*="analytics"]',
                '[id*="tracking"]', '[class*="tracking"]',
                '[id*="gtm"]', '[class*="gtm"]',
                '[id*="facebook"]', '[class*="facebook"]'
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
            url=url, screenshots={}, dom_structure="", 
            extracted_css={}, color_palette=[], typography={}, 
            layout_info={}, assets={}, metadata={},
            success=False, error_message=error_message
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
        