function generate_critical_css() {
  const css = [];

  // Body styles
  const bodyStyles = window.getComputedStyle(document.body);
  css.push(`body {
                    font-family: ${bodyStyles.fontFamily};
                    font-size: ${bodyStyles.fontSize};
                    line-height: ${bodyStyles.lineHeight};
                    color: ${bodyStyles.color};
                    background-color: ${bodyStyles.backgroundColor};
                    margin: 0;
                    padding: 0;
                }`);

  // Container
  const container = document.querySelector(".container, .wrapper, main");
  if (container) {
    const containerStyles = window.getComputedStyle(container);
    css.push(`.container {
                        max-width: ${containerStyles.maxWidth};
                        margin: 0 auto;
                        padding: ${containerStyles.padding};
                    }`);
  }

  // Headings
  const h1 = document.querySelector("h1");
  if (h1) {
    const h1Styles = window.getComputedStyle(h1);
    css.push(`h1 {
                        font-size: ${h1Styles.fontSize};
                        font-weight: ${h1Styles.fontWeight};
                        color: ${h1Styles.color};
                        margin: ${h1Styles.margin};
                    }`);
  }

  // Buttons
  const button = document.querySelector("button, .btn");
  if (button) {
    const buttonStyles = window.getComputedStyle(button);
    css.push(`button, .btn {
                        background-color: ${buttonStyles.backgroundColor};
                        color: ${buttonStyles.color};
                        border: ${buttonStyles.border};
                        border-radius: ${buttonStyles.borderRadius};
                        padding: ${buttonStyles.padding};
                        font-size: ${buttonStyles.fontSize};
                        cursor: pointer;
                    }`);
  }

  return css.join("\\n\\n");
}

console.log("generate_critical_css injected");
window.generate_critical_css = generate_critical_css;
