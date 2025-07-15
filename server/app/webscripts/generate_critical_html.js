function generate_critical_html() {
  const createSimpleHTML = (element) => {
    if (!element) return "";

    const tagName = element.tagName.toLowerCase();
    const text = element.textContent?.trim().substring(0, 100);
    const src = element.src || "";
    const href = element.href || "";

    // Simplify to semantic elements
    if (tagName === "img" && src) {
      return `<img src="${src}" alt="${element.alt || ""}" />`;
    }
    if (tagName === "a" && href) {
      return `<a href="${href}">${text}</a>`;
    }
    if (["h1", "h2", "h3", "h4", "h5", "h6"].includes(tagName)) {
      return `<${tagName}>${text}</${tagName}>`;
    }
    if (tagName === "p" && text) {
      return `<p>${text}</p>`;
    }
    if (tagName === "button" && text) {
      return `<button>${text}</button>`;
    }

    return "";
  };

  let html = '<div class="simplified-page">\\n';

  // Header
  const header = document.querySelector("header, .header");
  if (header) {
    html += "  <header>\\n";
    const logo = header.querySelector("img, .logo");
    if (logo) html += "    " + createSimpleHTML(logo) + "\\n";
    const nav = header.querySelector("nav");
    if (nav) {
      html += "    <nav>\\n";
      const links = nav.querySelectorAll("a");
      Array.from(links)
        .slice(0, 5)
        .forEach((link) => {
          html += "      " + createSimpleHTML(link) + "\\n";
        });
      html += "    </nav>\\n";
    }
    html += "  </header>\\n";
  }

  // Main content
  html += "  <main>\\n";
  const sections = document.querySelectorAll("main section, .section, article");
  Array.from(sections)
    .slice(0, 3)
    .forEach((section) => {
      html += "    <section>\\n";
      const heading = section.querySelector("h1, h2, h3");
      if (heading) html += "      " + createSimpleHTML(heading) + "\\n";
      const paragraphs = section.querySelectorAll("p");
      Array.from(paragraphs)
        .slice(0, 2)
        .forEach((p) => {
          html += "      " + createSimpleHTML(p) + "\\n";
        });
      html += "    </section>\\n";
    });
  html += "  </main>\\n";

  html += "</div>";
  return html;
}

console.log("generate_critical_html injected");
window.generate_critical_html = generate_critical_html;
