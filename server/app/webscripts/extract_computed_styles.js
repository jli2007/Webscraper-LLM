const extract_css_info = () => {
  const styles = {};

  // Get styles for key elements
  const selectors = [
    "body",
    "header",
    "main",
    "nav",
    "footer",
    "h1",
    "h2",
    "h3",
    "p",
    "a",
    "button",
  ];

  selectors.forEach((selector) => {
    const element = document.querySelector(selector);
    if (element) {
      const computedStyle = window.getComputedStyle(element);
      styles[selector] = {
        color: computedStyle.color,
        backgroundColor: computedStyle.backgroundColor,
        fontSize: computedStyle.fontSize,
        fontFamily: computedStyle.fontFamily,
        fontWeight: computedStyle.fontWeight,
        lineHeight: computedStyle.lineHeight,
        margin: computedStyle.margin,
        padding: computedStyle.padding,
        borderRadius: computedStyle.borderRadius,
        boxShadow: computedStyle.boxShadow,
        textAlign: computedStyle.textAlign,
        display: computedStyle.display,
        position: computedStyle.position,
        width: computedStyle.width,
        height: computedStyle.height,
      };
    }
  });

  return styles;
};

console.log("extract_css_info injected");
window.extract_css_info = extract_css_info;
