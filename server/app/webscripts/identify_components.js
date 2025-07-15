function identify_components() {
  const components = [];

  // Cards
  const cards = document.querySelectorAll(
    '.card, .item, .product, .post, [class*="card"]'
  );
  if (cards.length > 1) {
    components.push({
      type: "card",
      count: cards.length,
      example: {
        bounds: cards[0].getBoundingClientRect(),
        hasImage: !!cards[0].querySelector("img"),
        hasButton: !!cards[0].querySelector("button, .btn, a"),
        structure: cards[0].innerHTML.length > 100 ? "complex" : "simple",
      },
    });
  }

  // Buttons
  const buttons = document.querySelectorAll(
    'button, .btn, .button, input[type="submit"]'
  );
  if (buttons.length > 0) {
    const buttonStyles = window.getComputedStyle(buttons[0]);
    components.push({
      type: "button",
      count: buttons.length,
      example: {
        text: buttons[0].textContent?.trim(),
        backgroundColor: buttonStyles.backgroundColor,
        borderRadius: buttonStyles.borderRadius,
        padding: buttonStyles.padding,
      },
    });
  }

  // Navigation items
  const navItems = document.querySelectorAll("nav a, .nav a, .menu a");
  if (navItems.length > 2) {
    components.push({
      type: "nav_item",
      count: navItems.length,
      example: {
        text: navItems[0].textContent?.trim(),
        bounds: navItems[0].getBoundingClientRect(),
      },
    });
  }

  return components;
}

console.log("identify_components injected");
window.identify_components = identify_components;
