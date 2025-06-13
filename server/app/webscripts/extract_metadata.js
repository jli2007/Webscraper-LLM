function extract_metadata() {
  const meta = {
    title: "",
    description: "",
    keywords: "",
    viewport: "",
    charset: "",
    og_data: {},
  };

  // Title
  const title = document.querySelector("title");
  if (title) meta.title = title.textContent.trim();

  // Meta tags
  document.querySelectorAll("meta").forEach((metaTag) => {
    const name = metaTag.getAttribute("name") || "";
    const property = metaTag.getAttribute("property") || "";
    const content = metaTag.getAttribute("content") || "";

    if (name.toLowerCase() === "description") {
      meta.description = content;
    } else if (name.toLowerCase() === "keywords") {
      meta.keywords = content;
    } else if (name.toLowerCase() === "viewport") {
      meta.viewport = content;
    } else if (metaTag.hasAttribute("charset")) {
      meta.charset = metaTag.getAttribute("charset");
    } else if (property.startsWith("og:")) {
      meta.og_data[property] = content;
    }
  });

  return meta;
}

console.log("extract_metadata injected");
window.extract_metadata = extract_metadata;
