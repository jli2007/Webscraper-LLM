function extract_visual_hierarchy() {
  const hierarchy = {
    header: null,
    navigation: null,
    main_content: [],
    sidebar: null,
    footer: null,
    hero_section: null,
  };

  // Find header
  const header = document.querySelector('header, .header, [role="banner"]');
  if (header) {
    hierarchy.header = {
      bounds: header.getBoundingClientRect(),
      text: header.textContent?.trim().substring(0, 200),
      hasNav: !!header.querySelector("nav"),
      hasLogo: !!header.querySelector("img, svg"),
    };
  }

  // Find navigation
  const nav = document.querySelector('nav, .nav, [role="navigation"]');
  if (nav) {
    const links = Array.from(nav.querySelectorAll("a")).map((a) => ({
      text: a.textContent?.trim(),
      href: a.href,
    }));
    hierarchy.navigation = {
      bounds: nav.getBoundingClientRect(),
      links: links.slice(0, 10),
    };
  }

  // Find main content sections
  const mainSections = document.querySelectorAll(
    "main section, .section, article, .content-block"
  );
  hierarchy.main_content = Array.from(mainSections)
    .slice(0, 5)
    .map((section) => ({
      bounds: section.getBoundingClientRect(),
      heading: section.querySelector("h1, h2, h3")?.textContent?.trim(),
      text: section.textContent?.trim().substring(0, 300),
      hasImages: !!section.querySelector("img"),
      hasButtons: !!section.querySelector("button, .btn, .button"),
    }));

  // Find hero section
  const hero = document.querySelector(".hero, .banner, .jumbotron, .intro");
  if (hero) {
    hierarchy.hero_section = {
      bounds: hero.getBoundingClientRect(),
      heading: hero.querySelector("h1, h2")?.textContent?.trim(),
      text: hero.textContent?.trim().substring(0, 200),
      hasBackground: window.getComputedStyle(hero).backgroundImage !== "none",
    };
  }

  return hierarchy;
}


console.log("extract_visual_hierarchy injected");
window.extract_visual_hierarchy = extract_visual_hierarchy;