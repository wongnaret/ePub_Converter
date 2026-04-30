# PDF to ePub Converter - Manual

## 1. Setting Up the Python Environment

It is recommended to use a virtual environment.

```bash
# Create a virtual environment
python -m venv venv

# Activate the virtual environment (Windows)
venv\Scripts\activate

# Activate the virtual environment (macOS/Linux)
source venv/bin/activate
```

## 2. Installing Dependencies

Install the required Python packages using pip:
```bash
pip install -r requirements.txt
```

## 3. Typhoon API Key

To use the OCR functionality, you need a Typhoon API key. You can get one from the [SCB 10X Typhoon API Portal](https://opentyphoon.ai/).

You can provide the API key in two ways:
1. By setting an environment variable named `TYPHOON_API_KEY`:
   - Windows (Command Prompt): `set TYPHOON_API_KEY=your_key`
   - Windows (PowerShell): `$env:TYPHOON_API_KEY="your_key"`
   - macOS / Linux: `export TYPHOON_API_KEY="your_key"`
2. By passing it directly as a command-line argument using the `-k` or `--api-key` flag.

## 4. How to Use

The script operates fully via the Command Line Interface (CLI).

### Basic Conversion
To convert a PDF (assuming you have set the `TYPHOON_API_KEY` environment variable):
```bash
python epub_converter.py "My Book.pdf"
```

### Specifying an Output File
You can use the `-o` or `--output` flag to specify the output filename and location.
```bash
python epub_converter.py "My Book.pdf" -o "/path/to/save/Converted_Book.epub"
```

### Providing the API Key directly
```bash
python epub_converter.py "My Book.pdf" -k "YOUR_API_KEY_HERE"
```

## 5. Troubleshooting
**"No Typhoon API Key provided"**
The script could not find an API key. OCR will be skipped. Ensure you provide it via the `-k` argument or set the `TYPHOON_API_KEY` environment variable.

**"Network error during Typhoon OCR"**
Ensure you have an active internet connection, as the OCR runs through the cloud API.
