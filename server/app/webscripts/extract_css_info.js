const extract_css_info = () => {
  const getComputedStyles = (element, properties) => {
    if (!element) return null;
    const styles = window.getComputedStyle(element);
    const result = {};
    properties.forEach((prop) => {
      result[prop] = styles[prop];
    });
    return result;
  };

  const importantProps = [
    "background-color",
    "font-family",
    "font-size",
    "font-weight",
    "line-height",
    "color",
    "margin",
    "padding",
    "display",
    "position",
    "width",
    "height",
    "border",
    "border-radius",
    "box-shadow",
    "text-align",
    "flex-direction",
    "justify-content",
    "align-items",
    "grid-template-columns",
    "z-index",
  ];

  const result = {
    body_styles: getComputedStyles(document.body, importantProps),
    header_styles: getComputedStyles(
      document.querySelector('header, .header, [role="banner"]'),
      importantProps
    ),
    main_content_styles: getComputedStyles(
      document.querySelector("main, .main, .content, #content"),
      importantProps
    ),
    common_patterns: [],
    layout_info: {},
    responsive_breakpoints: [],
    animations: [],
  };

  // Extract common element styles
  const selectors = [
    "h1",
    "h2",
    "h3",
    "h4",
    "p",
    "a",
    "button",
    "input",
    ".container",
    ".wrapper",
    ".content",
    ".header",
    ".footer",
    "nav",
    ".nav",
    ".menu",
    ".btn",
    ".card",
    ".hero",
  ];

  selectors.forEach((selector) => {
    const elements = document.querySelectorAll(selector);
    if (elements.length > 0) {
      const styles = getComputedStyles(elements[0], importantProps);
      if (styles) {
        result.common_patterns.push({
          selector: selector,
          styles: styles,
          count: elements.length,
        });
      }
    }
  });

  // Extract layout information
  const body = document.body;
  const bodyStyles = window.getComputedStyle(body);
  result.layout_info = {
    layout_type:
      bodyStyles.display === "flex"
        ? "flexbox"
        : bodyStyles.display === "grid"
        ? "grid"
        : "block",
    max_width: bodyStyles.maxWidth,
    container_width:
      document.querySelector(".container, .wrapper, main")?.offsetWidth ||
      body.offsetWidth,
    has_sidebar: !!document.querySelector(".sidebar, .side-nav, aside"),
    is_responsive: window.innerWidth !== document.documentElement.scrollWidth,
  };

  // Extract CSS custom properties (CSS variables)
  const rootStyles = window.getComputedStyle(document.documentElement);
  const cssVars = {};
  for (let i = 0; i < rootStyles.length; i++) {
    const prop = rootStyles.item(i);
    if (prop.startsWith("--")) {
      cssVars[prop] = rootStyles.getPropertyValue(prop).trim();
    }
  }
  result.css_variables = cssVars;

  // Detect animations
  const animatedElements = document.querySelectorAll("*");
  const animations = [];
  animatedElements.forEach((el) => {
    const styles = window.getComputedStyle(el);
    const classAttr = el.getAttribute("class") || "";
    if (
      styles.animationName !== "none" ||
      styles.transitionProperty !== "none"
    ) {
      animations.push({
        selector:
          el.tagName.toLowerCase() +
          (classAttr ? "." + classAttr.split(/\s+/)[0] : ""),
        animation: styles.animationName,
        transition: styles.transitionProperty,
        duration: styles.animationDuration || styles.transitionDuration,
      });
    }
  });
  result.animations = animations.slice(0, 10); // Limit to 10

  // Extract media query breakpoints from stylesheets
  const breakpoints = new Set();
  try {
    Array.from(document.styleSheets).forEach((sheet) => {
      try {
        Array.from(sheet.cssRules || sheet.rules || []).forEach((rule) => {
          if (rule.type === CSSRule.MEDIA_RULE) {
            const mediaText = rule.media.mediaText;
            const widthMatch = mediaText.match(
              /\\((min|max)-width:\\s*(\\d+)px\\)/
            );
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
    [768, 1024, 1200, 1400].forEach((bp) => breakpoints.add(bp));
  }
  result.responsive_breakpoints = Array.from(breakpoints).sort((a, b) => a - b);

  return result;
};

console.log("extract_css_info injected");
window.extract_css_info = extract_css_info;
