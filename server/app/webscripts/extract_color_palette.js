function extract_color_palette(){
  const colors = new Set();

  // Helper to normalize colors to hex
  function normalizeColor(color) {
    if (!color || color === "transparent" || color === "none") return null;

    // Already hex?
    if (color.startsWith("#")) {
      return color.length === 4
        ? color.replace(/./g, (c, i) => (i ? c + c : c))
        : color;
    }

    // Handle rgb/rgba
    const rgbMatch = color.match(
      /rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)(?:,\\s*([\\d.]+))?\\)/
    );
    if (rgbMatch) {
      const [, r, g, b, a] = rgbMatch;

      // Skip very transparent colors
      if (a !== undefined && parseFloat(a) < 0.3) return null;

      const toHex = (n) => parseInt(n).toString(16).padStart(2, "0");
      return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
    }

    // Handle named colors
    const namedColors = {
      red: "#ff0000",
      blue: "#0000ff",
      green: "#008000",
      yellow: "#ffff00",
      orange: "#ffa500",
      purple: "#800080",
      pink: "#ffc0cb",
      brown: "#a52a2a",
      gray: "#808080",
      grey: "#808080",
      cyan: "#00ffff",
      magenta: "#ff00ff",
    };

    return namedColors[color.toLowerCase()] || null;
  }

  // 1. Extract from all elements with explicit colors
  const allElements = document.querySelectorAll("*");

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
        styles.columnRuleColor,
      ];

      colorProps.forEach((color) => {
        const normalized = normalizeColor(color);
        if (
          normalized &&
          normalized !== "#000000" &&
          normalized !== "#ffffff"
        ) {
          colors.add(normalized);
        }
      });

      // Check for background images with gradients!!
      const bgImage = styles.backgroundImage;
      if (bgImage && bgImage !== "none") {
        // Extract colors from gradients
        const gradientColors = bgImage.match(
          /#[0-9a-fA-F]{3,6}|rgb\\([^)]+\\)|rgba\\([^)]+\\)/g
        );
        if (gradientColors) {
          gradientColors.forEach((color) => {
            const normalized = normalizeColor(color);
            if (normalized) {
              colors.add(normalized);
            }
          });
        }
      }
    }
  });

  // 2. Extract from inline styles
  const elementsWithStyle = document.querySelectorAll("[style]");
  elementsWithStyle.forEach((element) => {
    const style = element.getAttribute("style");
    const colorMatches = style.match(
      /#[0-9a-fA-F]{3,6}|rgb\\([^)]+\\)|rgba\\([^)]+\\)/g
    );
    if (colorMatches) {
      colorMatches.forEach((color) => {
        const normalized = normalizeColor(color);
        if (normalized) {
          colors.add(normalized);
        }
      });
    }
  });

  // 3. Extract from CSS stylesheets
  try {
    Array.from(document.styleSheets).forEach((sheet) => {
      try {
        const rules = sheet.cssRules || sheet.rules || [];
        Array.from(rules).forEach((rule) => {
          if (rule.cssText) {
            const colorMatches = rule.cssText.match(
              /#[0-9a-fA-F]{3,6}|rgb\\([^)]+\\)|rgba\\([^)]+\\)/g
            );
            if (colorMatches) {
              colorMatches.forEach((color) => {
                const normalized = normalizeColor(color);
                if (
                  normalized &&
                  normalized !== "#000000" &&
                  normalized !== "#ffffff"
                ) {
                  colors.add(normalized);
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
    console.log("Could not access stylesheets");
  }

  const finalColors = Array.from(colors);
  return finalColors.slice(0, 20);
};

console.log("extract_color_palette injected");
window.extract_color_palette = extract_color_palette;