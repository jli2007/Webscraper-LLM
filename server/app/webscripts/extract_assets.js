function extract_assets() {
  const assets = {
    images: [],
    stylesheets: [],
    fonts: [],
    icons: [],
    scripts: [],
  };

  // Images
  document.querySelectorAll("img").forEach((img) => {
    if (img.src) assets.images.push(img.src);
  });

  // Stylesheets
  document.querySelectorAll('link[rel="stylesheet"]').forEach((link) => {
    if (link.href) assets.stylesheets.push(link.href);
  });

  // Fonts
  document.querySelectorAll("link").forEach((link) => {
    const href = link.href || "";
    if (href.includes("fonts") || href.includes("font")) {
      assets.fonts.push(href);
    }
  });

  // Icons
  document.querySelectorAll('link[rel*="icon"]').forEach((link) => {
    if (link.href) assets.icons.push(link.href);
  });

  // Scripts
  document.querySelectorAll("script[src]").forEach((script) => {
    if (script.src) assets.scripts.push(script.src);
  });

  return assets;
}

console.log("extract_assets injected");
window.extract_assets = extract_assets;