function extract_layout_info() {
  const structure = [];
  const gridInfo = {};

  // Identify main structural elements
  const structuralTags = [
    "header",
    "nav",
    "main",
    "section",
    "aside",
    "footer",
    "article",
  ];

  structuralTags.forEach((tag) => {
    const elements = document.querySelectorAll(tag);
    if (elements.length > 0) {
      structure.push({
        tag: tag,
        count: elements.length,
        classes: Array.from(elements)
          .slice(0, 3)
          .map((el) => (el.className ? el.className.split(" ") : [])),
      });
    }
  });

  // Check for grid/flexbox layouts
  const allElements = Array.from(document.querySelectorAll("*")).slice(0, 30);
  allElements.forEach((element) => {
    const styles = window.getComputedStyle(element);
    const display = styles.display;

    if (display === "grid" || display === "flex") {
      const tagName = element.tagName.toLowerCase();
      const className = element.className || "no-class";

      gridInfo[`${tagName}.${className}`] = {
        display: display,
        "justify-content": styles.justifyContent,
        "align-items": styles.alignItems,
        "grid-template-columns": styles.gridTemplateColumns,
        "flex-direction": styles.flexDirection,
      };
    }
  });

  return {
    structure: structure,
    grid_info: gridInfo,
  };
}

console.log("extract_layout_info injected");
window.extract_layout_info = extract_layout_info;