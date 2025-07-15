function extract_design_tokens() {
  const tokens = {
    colors: {
      primary: [],
      secondary: [],
      text: [],
      background: [],
    },
    typography: {
      headings: {},
      body: {},
      font_families: [],
    },
    spacing: {
      margins: [],
      paddings: [],
      gaps: [],
    },
    borders: {
      radius: [],
      widths: [],
    },
    shadows: [],
  };

  // Extract colors from computed styles
  const elements = document.querySelectorAll("*");
  const colorSet = new Set();
  const backgroundSet = new Set();

  Array.from(elements).forEach((el) => {
    const styles = window.getComputedStyle(el);

    // Colors
    if (styles.color && styles.color !== "rgb(0, 0, 0)") {
      colorSet.add(styles.color);
    }

    // Backgrounds
    if (
      styles.backgroundColor &&
      styles.backgroundColor !== "rgba(0, 0, 0, 0)"
    ) {
      backgroundSet.add(styles.backgroundColor);
    }
  });

  tokens.colors.text = Array.from(colorSet).slice(0, 5);
  tokens.colors.background = Array.from(backgroundSet).slice(0, 5);

  // Extract typography
  const headings = document.querySelectorAll("h1, h2, h3, h4, h5, h6");
  const bodyText = document.querySelector("p, body");

  if (headings.length > 0) {
    const h1Style = window.getComputedStyle(headings[0]);
    tokens.typography.headings = {
      fontSize: h1Style.fontSize,
      fontWeight: h1Style.fontWeight,
      fontFamily: h1Style.fontFamily,
      lineHeight: h1Style.lineHeight,
    };
  }

  if (bodyText) {
    const bodyStyle = window.getComputedStyle(bodyText);
    tokens.typography.body = {
      fontSize: bodyStyle.fontSize,
      fontFamily: bodyStyle.fontFamily,
      lineHeight: bodyStyle.lineHeight,
    };
  }

  return tokens;
}

console.log("extract_design_tokens injected");
window.extract_design_tokens = extract_design_tokens;
