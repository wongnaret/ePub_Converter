# PDF to ePub Converter (Web Version)

A web-based tool to convert PDF ebooks to ePub files. This tool features a web interface to preview PDFs, select areas to skip or keep as images, configure page settings, and perform Optical Character Recognition (OCR) using Typhoon OCR.

## Features (In Progress)
- Web interface for PDF upload and project management.
- (Coming Soon) Interactive PDF viewer to select skipping areas (e.g., page numbers).
- (Coming Soon) Page size optimization settings.
- (Coming Soon) Mark pages as covers or full-page images.
- (Coming Soon) Select areas within a page to embed as images in the ePub.
- (Coming Soon) Real-time OCR progress reporting via WebSockets.
- (Coming Soon) WYSIWYG editor for post-OCR corrections and styling.

## Installation

See `MANUAL.md` for a detailed guide on how to set up the environment.

## Quick Start
```bash
# Set your API key
export TYPHOON_API_KEY="your-api-key"

# Run the web server
python app.py
```
Then, open your browser and go to `http://localhost:5000`

## License
MIT License