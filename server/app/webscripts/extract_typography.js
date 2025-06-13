function extract_typography() {
  const fonts = new Set();
  const headings = {};
  let bodyText = {};

  // Extract font families
  const elements = Array.from(document.querySelectorAll("*")).slice(0, 50);
  elements.forEach((element) => {
    const fontFamily = window.getComputedStyle(element).fontFamily;
    if (fontFamily) fonts.add(fontFamily);
  });

  // Extract heading styles
  for (let i = 1; i <= 6; i++) {
    const heading = document.querySelector(`h${i}`);
    if (heading) {
      const styles = window.getComputedStyle(heading);
      headings[`h${i}`] = {
        "font-size": styles.fontSize,
        "font-weight": styles.fontWeight,
        "line-height": styles.lineHeight,
        margin: styles.margin,
        "font-family": styles.fontFamily,
      };
    }
  }

  // Extract body text styles
  const paragraph = document.querySelector("p");
  if (paragraph) {
    const styles = window.getComputedStyle(paragraph);
    bodyText = {
      "font-size": styles.fontSize,
      "line-height": styles.lineHeight,
      "font-weight": styles.fontWeight,
      "font-family": styles.fontFamily,
    };
  }

  return {
    fonts: Array.from(fonts),
    headings: headings,
    body_text: bodyText,
  };
}

console.log("extract_typography injected");
window.extract_typography = extract_typography;