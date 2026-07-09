#!/usr/bin/env node
/**
 * Generate docs/CODEBASE_GUIDE.pdf from docs/CODEBASE_GUIDE.md
 * Usage: npm run generate:codebase-guide  (from docs/scripts/)
 */

import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { marked } from "marked";
import puppeteer from "puppeteer";

const __dirname = dirname(fileURLToPath(import.meta.url));
const docsDir = resolve(__dirname, "..");
const markdownPath = join(docsDir, "CODEBASE_GUIDE.md");
const cssPath = join(__dirname, "pdf-styles.css");
const htmlPath = join(docsDir, "CODEBASE_GUIDE.html");
const pdfPath = join(docsDir, "CODEBASE_GUIDE.pdf");

function toFileUrl(relativePath) {
  return `file://${join(docsDir, relativePath).replace(/\\/g, "/")}`;
}

function preprocessMarkdown(source) {
  let output = source;

  // Rewrite relative image paths to absolute file URLs for Puppeteer.
  output = output.replace(
    /!\[([^\]]*)\]\((images\/[^)]+)\)/g,
    (_, alt, imagePath) => `![${alt}](${toFileUrl(imagePath)})`,
  );

  return output;
}

function renderMarkdown(source) {
  const renderer = new marked.Renderer();

  renderer.code = ({ text, lang }) => {
    if (lang === "mermaid") {
      return `<pre class="mermaid">${text}</pre>`;
    }
    const escaped = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    const language = lang ? ` language-${lang}` : "";
    return `<pre><code class="${language.trim()}">${escaped}</code></pre>`;
  };

  marked.setOptions({
    gfm: true,
    breaks: false,
    renderer,
  });

  return marked.parse(source);
}

function buildHtml(bodyHtml) {
  const css = readFileSync(cssPath, "utf8");
  const generatedAt = new Date().toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  return `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>CAP Codebase Architecture Guide</title>
    <style>${css}</style>
  </head>
  <body>
    <section class="cover">
      <div class="cover-kicker">Coding Assessment Platform</div>
      <h1>Codebase Architecture Guide</h1>
      <p>
        A complete map of CAP services, authentication flows, data models,
        business workflows, frontend features, and the best places to start
        reading source code.
      </p>
      <div class="cover-meta">
        <div><span>Document</span><strong>Architecture Guide</strong></div>
        <div><span>Generated</span><strong>${generatedAt}</strong></div>
        <div><span>Repository</span><strong>CAP CodeBase</strong></div>
      </div>
    </section>
    <main class="content">${bodyHtml}</main>
    <script type="module">
      import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
      mermaid.initialize({
        startOnLoad: false,
        theme: "base",
        themeVariables: {
          primaryColor: "#dbeafe",
          primaryTextColor: "#0f172a",
          primaryBorderColor: "#2563eb",
          lineColor: "#475569",
          secondaryColor: "#ecfdf5",
          tertiaryColor: "#fef3c7",
          fontFamily: "Segoe UI, Helvetica Neue, Arial, sans-serif",
        },
        flowchart: { htmlLabels: true, curve: "basis" },
        sequence: { actorMargin: 40, messageMargin: 30 },
      });
      await mermaid.run({ querySelector: ".mermaid" });
    </script>
  </body>
</html>`;
}

async function generatePdf(htmlFilePath, outputPdfPath) {
  const browser = await puppeteer.launch({
    headless: true,
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  });

  try {
    const page = await browser.newPage();
    await page.goto(`file://${htmlFilePath.replace(/\\/g, "/")}`, {
      waitUntil: "networkidle0",
      timeout: 120_000,
    });

    // Allow Mermaid SVG layout to settle.
    await page.waitForFunction(
      () => document.querySelectorAll(".mermaid svg").length >= 3,
      { timeout: 60_000 },
    ).catch(() => undefined);

    await page.pdf({
      path: outputPdfPath,
      format: "A4",
      printBackground: true,
      preferCSSPageSize: true,
      margin: {
        top: "16mm",
        bottom: "18mm",
        left: "14mm",
        right: "14mm",
      },
      displayHeaderFooter: true,
      headerTemplate: `
        <div style="font-size:8px; width:100%; padding:0 14mm; color:#64748b;
          font-family:Segoe UI, Helvetica Neue, Arial, sans-serif;">
          CAP Codebase Architecture Guide
        </div>`,
      footerTemplate: `
        <div style="font-size:8px; width:100%; padding:0 14mm; color:#64748b;
          display:flex; justify-content:space-between;
          font-family:Segoe UI, Helvetica Neue, Arial, sans-serif;">
          <span>Coding Assessment Platform</span>
          <span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span>
        </div>`,
    });
  } finally {
    await browser.close();
  }
}

async function main() {
  const markdown = readFileSync(markdownPath, "utf8");
  const processed = preprocessMarkdown(markdown);
  const bodyHtml = renderMarkdown(processed);
  const html = buildHtml(bodyHtml);

  writeFileSync(htmlPath, html, "utf8");
  console.log(`Wrote HTML preview: ${htmlPath}`);

  await generatePdf(htmlPath, pdfPath);
  console.log(`Wrote PDF: ${pdfPath}`);
}

main().catch((error) => {
  console.error("Failed to generate PDF:", error);
  process.exit(1);
});
