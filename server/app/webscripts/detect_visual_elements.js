const detect_visual_elements = () => {
  const elements = {
    cards: [],
    buttons: [],
    forms: [],
    navigation: [],
    images: [],
    sections: [],
  };

  // Detect card-like elements
  const potentialCards = document.querySelectorAll("div, article, section");
  potentialCards.forEach((el) => {
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();

    // Heuristics for card detection
    if (
      style.boxShadow !== "none" ||
      style.border !== "none" ||
      style.borderRadius !== "0px"
    ) {
      if (rect.width > 100 && rect.height > 100) {
        elements.cards.push({
          tagName: el.tagName,
          className: el.className,
          styles: {
            backgroundColor: style.backgroundColor,
            borderRadius: style.borderRadius,
            boxShadow: style.boxShadow,
            padding: style.padding,
          },
          dimensions: {
            width: rect.width,
            height: rect.height,
          },
        });
      }
    }
  });

  // Detect buttons
  const buttons = document.querySelectorAll(
    'button, [role="button"], .btn, .button, input[type="submit"]'
  );
  buttons.forEach((btn) => {
    const style = window.getComputedStyle(btn);
    const rect = btn.getBoundingClientRect();

    elements.buttons.push({
      text: btn.textContent?.trim(),
      tagName: btn.tagName,
      className: btn.className,
      styles: {
        backgroundColor: style.backgroundColor,
        color: style.color,
        borderRadius: style.borderRadius,
        padding: style.padding,
        fontSize: style.fontSize,
        fontWeight: style.fontWeight,
      },
      dimensions: {
        width: rect.width,
        height: rect.height,
      },
    });
  });

  return elements;
};

console.log("detect_visual_elements injected");
window.detect_visual_elements = detect_visual_elements;
