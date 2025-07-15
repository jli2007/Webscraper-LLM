function analyze_layout_patterns() {
  const patterns = {
    grid_layouts: [],
    flex_layouts: [],
    columns: 0,
    max_width: null,
  };

  // Find grid layouts
  const gridElements = document.querySelectorAll("*");
  Array.from(gridElements).forEach((el) => {
    const styles = window.getComputedStyle(el);
    if (styles.display === "grid") {
      patterns.grid_layouts.push({
        selector:
          el.tagName.toLowerCase() +
          (el.className ? "." + el.className.split(" ")[0] : ""),
        gridTemplateColumns: styles.gridTemplateColumns,
        gap: styles.gap,
      });
    }
    if (styles.display === "flex") {
      patterns.flex_layouts.push({
        selector:
          el.tagName.toLowerCase() +
          (el.className ? "." + el.className.split(" ")[0] : ""),
        flexDirection: styles.flexDirection,
        justifyContent: styles.justifyContent,
        alignItems: styles.alignItems,
      });
    }
  });

  // Detect column layout
  const container = document.querySelector(".container, .wrapper, main, body");
  if (container) {
    const containerStyles = window.getComputedStyle(container);
    patterns.max_width = containerStyles.maxWidth;
  }

  return patterns;
}

console.log("analyze_layout_patterns injected");
window.analyze_layout_patterns = analyze_layout_patterns;
