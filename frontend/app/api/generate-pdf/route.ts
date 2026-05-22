import { NextRequest, NextResponse } from "next/server"
import puppeteer from "puppeteer"

export async function POST(req: NextRequest) {
  // Security check: Validate Authorization header matches JWT_SECRET or PDF_GENERATION_SECRET
  const authHeader = req.headers.get("authorization")
  const pdfSecret = process.env.PDF_GENERATION_SECRET || process.env.JWT_SECRET

  if (pdfSecret) {
    if (!authHeader || !authHeader.startsWith("Bearer ") || authHeader.substring(7) !== pdfSecret) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
    }
  }

  let browser = null
  try {
    const { html } = await req.json()

    if (!html) {
      return NextResponse.json({ error: "No HTML content provided" }, { status: 400 })
    }

    // Launch puppeteer with system chromium
    browser = await puppeteer.launch({
      executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || undefined,
      args: ["--no-sandbox", "--disable-setuid-sandbox", "--font-render-hinting=none"],
      headless: true,
    })

    const page = await browser.newPage()

    // Set viewport to A4 dimensions at 96 DPI for layout calculation
    await page.setViewport({
      width: 794,
      height: 1123,
      deviceScaleFactor: 2, // Higher scale factor for better quality rendering (shadows, paths)
    })

    // Inject necessary CSS adjustments for printing
    const styledHtml = `
      <style>
        body {
          margin: 0 !important;
          padding: 0 !important;
          background: white !important;
          display: block !important;
          -webkit-print-color-adjust: exact !important;
          print-color-adjust: exact !important;
        }
        * {
          -webkit-print-color-adjust: exact !important;
          print-color-adjust: exact !important;
        }
      </style>
      ${html}
    `

    // Set content and wait for network to be idle (important for fonts/images from external URLs)
    try {
      await page.setContent(styledHtml, {
        waitUntil: "networkidle2",
        timeout: 10000, // 10-second limit to prevent hanging on hot-reload/WS connections
      })
    } catch (loadError: any) {
      console.warn("Puppeteer content loading timed out, proceeding to generate PDF anyway:", loadError.message)
    }

    // Generate PDF - Respect CSS page size
    const pdfBuffer = await page.pdf({
      printBackground: true,
      margin: {
        top: "0px",
        right: "0px",
        bottom: "0px",
        left: "0px",
      },
      preferCSSPageSize: true,
    })

    await browser.close()

    // Return the PDF as response
    return new NextResponse(pdfBuffer as any, {
      status: 200,
      headers: {
        "Content-Type": "application/pdf",
        "Content-Disposition": 'attachment; filename="offer-letter.pdf"',
        "Content-Length": pdfBuffer.length.toString(),
      },
    })
  } catch (error: any) {
    console.error("PDF Generation Error:", error)
    if (browser) await (browser as any).close()
    return NextResponse.json({ error: `Failed to generate PDF: ${error.message}` }, { status: 500 })
  }
}
