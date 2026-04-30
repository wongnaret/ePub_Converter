# PDF to ePub Converter

A command-line interface (CLI) Python tool to convert PDF ebooks to ePub files. This tool supports extracting both text and embedded images from the PDF, and it features Optical Character Recognition (OCR) fallback for scanned pages or image-heavy pages, using Typhoon OCR.

## Features
- Converts PDF files directly to ePub.
- Extracts text natively from the PDF document.
- Extracts and embeds images correctly inside the generated ePub file.
- Built-in OCR support using Typhoon OCR for scanned pages (excellent Thai support).
- Progress bar support for large files.
- Command-line interface with customizable settings.

## Installation

See `MANUAL.md` for a detailed guide on how to set up the environment and prerequisites for this project.

## Quick Start
```bash
# Set your API key in environment or pass via -k
export TYPHOON_API_KEY="your-api-key"
python epub_converter.py input_book.pdf
```
This will generate `input_book.epub` in the same directory using Typhoon OCR as fallback.

```bash
python epub_converter.py input_book.pdf -o output_book.epub -k "your-api-key"
```
This specifies the output file name and explicitly provides the API key.

## Requirements
Check `requirements.txt` for Python dependencies. You need an active internet connection and a valid API key for Typhoon API.

## License
MIT License
