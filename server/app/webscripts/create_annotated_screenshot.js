function create_annotated_screenshot() {
  return new Promise((resolve) => {
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    const img = new Image();

    img.onload = () => {
      canvas.width = img.width;
      canvas.height = img.height;
      ctx.drawImage(img, 0, 0);

      // Add colored overlays for different sections
      ctx.strokeStyle = "rgba(255, 0, 0, 0.8)";
      ctx.lineWidth = 2;

      if (hierarchy.header) {
        const rect = hierarchy.header.bounds;
        ctx.strokeRect(rect.x, rect.y, rect.width, rect.height);
        ctx.fillStyle = "rgba(255, 0, 0, 0.2)";
        ctx.fillRect(rect.x, rect.y, rect.width, rect.height);
      }

      // Convert to base64
      const base64 = canvas.toDataURL().split(",")[1];
      resolve(base64);
    };

    img.src = "data:image/png;base64," + arguments[1];
  });
}

console.log("create_annotated_screenshot injected");
window.create_annotated_screenshot = create_annotated_screenshot;
