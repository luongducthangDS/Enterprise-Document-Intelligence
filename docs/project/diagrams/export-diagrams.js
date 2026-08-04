const http = require("http");
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const root = __dirname;
const outDir = path.join(root, "images");
const port = 8765;

const mimeTypes = {
  ".html": "text/html; charset=utf-8",
  ".mermaid": "text/plain; charset=utf-8",
  ".mmd": "text/plain; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
};

const diagrams = [
  ["System Overview", "system_overview_diagram.png"],
  ["Agent Flow", "agent_flow_diagram.png"],
  ["Deployment", "deployment_diagram.png"],
  ["Workflow", "workflow.png"],
];

function serveFile(req, res) {
  const urlPath = decodeURIComponent(new URL(req.url, `http://localhost:${port}`).pathname);
  const safePath = path.normalize(urlPath).replace(/^([/\\])+/, "");
  const filePath = path.join(root, safePath || "viewer.html");

  if (!filePath.startsWith(root)) {
    res.writeHead(403);
    res.end("Forbidden");
    return;
  }

  fs.readFile(filePath, (error, data) => {
    if (error) {
      res.writeHead(404);
      res.end("Not found");
      return;
    }
    res.writeHead(200, { "Content-Type": mimeTypes[path.extname(filePath)] || "application/octet-stream" });
    res.end(data);
  });
}

async function waitForDiagram(page) {
  await page.waitForFunction(() => {
    const status = document.querySelector("#status");
    const svg = document.querySelector("#diagram svg");
    return status && status.textContent.trim() === "" && svg;
  }, { timeout: 30000 });
}

(async () => {
  fs.mkdirSync(outDir, { recursive: true });

  const server = http.createServer(serveFile);
  await new Promise((resolve) => server.listen(port, "127.0.0.1", resolve));

    const browser = await chromium.launch({
      executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    });
  try {
    const page = await browser.newPage({ viewport: { width: 1800, height: 1200 }, deviceScaleFactor: 2 });
    await page.goto(`http://127.0.0.1:${port}/viewer.html`, { waitUntil: "networkidle" });

    for (const [label, filename] of diagrams) {
      await page.getByRole("button", { name: label }).click();
      await waitForDiagram(page);
      const element = page.locator("#diagram svg");
      await element.screenshot({ path: path.join(outDir, filename), omitBackground: false });
      console.log(path.join(outDir, filename));
    }
  } finally {
    await browser.close();
    server.close();
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
