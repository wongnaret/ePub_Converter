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

Install the required Python packages using pip. Since we have upgraded to a Web UI, you must install the updated requirements.
```bash
pip install -r requirements.txt
```

## 3. Typhoon API Key

To use the OCR functionality, you need a Typhoon API key. You can get one from the [SCB 10X Typhoon API Portal](https://opentyphoon.ai/).

Set an environment variable named `TYPHOON_API_KEY` before starting the application:
- Windows (Command Prompt): `set TYPHOON_API_KEY=your_key`
- Windows (PowerShell): `$env:TYPHOON_API_KEY="your_key"`
- macOS / Linux: `export TYPHOON_API_KEY="your_key"`

## 4. How to Start the Web Interface

The application now runs as a local web server, providing a UI for managing projects and PDFs.

1. Ensure your virtual environment is activated and dependencies are installed.
2. Start the web server by running the following command:
   ```bash
   python app.py
   ```
3. Open your web browser and go to:
   **http://localhost:5000**

From the web interface, you can upload new PDFs to create projects, resume existing projects, and eventually configure the OCR settings and page properties.

## 5. Using the Command Line Tool (Legacy)

If you still prefer the fully automated CLI version without the interactive web UI, you can use the original script:

### Basic Conversion
```bash
python epub_converter.py "My Book.pdf"
```

### Specifying an Output File
```bash
python epub_converter.py "My Book.pdf" -o "/path/to/save/Converted_Book.epub"
```

### Providing the API Key directly
```bash
python epub_converter.py "My Book.pdf" -k "YOUR_API_KEY_HERE"
```

## 6. Troubleshooting
**"No Typhoon API Key provided"**
The script could not find an API key. OCR will be skipped or fail. Ensure you set the `TYPHOON_API_KEY` environment variable.

**"Network error during Typhoon OCR"**
Ensure you have an active internet connection, as the OCR runs through the cloud API.
