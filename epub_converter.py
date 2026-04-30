import argparse
import os
import io
import base64
import time
import requests
from collections import deque
from ebooklib import epub
from PIL import Image
import fitz  # PyMuPDF
from tqdm import tqdm

TYPHOON_API_URL = "https://api.scb10x.com/typhoon/v1/chat/completions"

class RateLimiter:
    def __init__(self, max_calls_sec, max_calls_min):
        self.max_calls_sec = max_calls_sec
        self.max_calls_min = max_calls_min
        self.calls_sec = deque()
        self.calls_min = deque()

    def wait(self):
        now = time.time()
        
        # Clean up old timestamps
        while self.calls_sec and now - self.calls_sec[0] >= 1.0:
            self.calls_sec.popleft()
        while self.calls_min and now - self.calls_min[0] >= 60.0:
            self.calls_min.popleft()

        sleep_time = 0
        
        if len(self.calls_min) >= self.max_calls_min:
            sleep_time = max(sleep_time, 60.0 - (now - self.calls_min[0]))
            
        if len(self.calls_sec) >= self.max_calls_sec:
            sleep_time = max(sleep_time, 1.0 - (now - self.calls_sec[0]))
            
        if sleep_time > 0:
            time.sleep(sleep_time)
            # Update now after sleeping
            now = time.time()
            # It's possible we need to clean up again after sleeping, 
            # but appending the new 'now' is generally sufficient for basic limiting
            
        self.calls_sec.append(now)
        self.calls_min.append(now)

# Initialize global rate limiter: 5 req/s and 200 req/m
ocr_rate_limiter = RateLimiter(max_calls_sec=5, max_calls_min=200)

def perform_ocr(image_bytes, api_key):
    """
    Performs OCR on a given image bytes using Typhoon OCR.
    Respects rate limits.
    """
    if not api_key:
        print("Error: Typhoon API key is required for OCR.")
        return ""

    try:
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "typhoon-v1.5-vision-preview", # Check for latest version on SCB10X portal
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Extract all the text from this image. Only return the extracted text, nothing else."
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 1024,
            "temperature": 0.0
        }
        
        # Enforce rate limits before making the request
        ocr_rate_limiter.wait()
        
        response = requests.post(TYPHOON_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        
        response_json = response.json()
        if "choices" in response_json and len(response_json["choices"]) > 0:
            return response_json["choices"][0]["message"]["content"]
        else:
            print("Warning: Unexpected response format from Typhoon API.")
            return ""
            
    except requests.exceptions.RequestException as e:
        print(f"Network error during Typhoon OCR: {e}")
        return ""
    except Exception as e:
        print(f"An error occurred during Typhoon OCR: {e}")
        return ""

def pdf_to_epub(pdf_path, epub_path, api_key):
    """
    Converts a PDF file to an ePub file, with OCR support.
    """
    if not os.path.exists(pdf_path):
        print(f"Error: PDF file not found at '{pdf_path}'")
        return

    doc = fitz.open(pdf_path)
    book = epub.EpubBook()
    book.set_title(os.path.basename(pdf_path).replace('.pdf', ''))
    book.set_language('en')

    chapters = []
    image_counter = 1

    for page_num in tqdm(range(len(doc)), desc="Converting PDF to ePub"):
        page = doc.load_page(page_num)
        
        # Extract text
        text = page.get_text("text")
        
        # Extract images
        img_list = page.get_images(full=True)
        for img_index, img in enumerate(img_list):
            xref = img[0]
            base_image = doc.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]
            
            # OCR if text is sparse on this page
            if len(text.strip()) < 100: # Heuristic to decide if OCR is needed
                text += perform_ocr(image_bytes, api_key)

            # Embed image in the ePub
            img_filename = f"image_{image_counter}.{image_ext}"
            image_item = epub.EpubImage(
                uid=f"img_{image_counter}",
                file_name=f"images/{img_filename}",
                media_type=f"image/{image_ext}",
                content=image_bytes
            )
            book.add_item(image_item)
            text += f'<p><img src="images/{img_filename}" alt="Image {image_counter}"/></p>'
            image_counter += 1

        # Clean text
        text = text.replace('\n', '<br/>')

        # Create chapter
        chapter_title = f'Page {page_num + 1}'
        chapter = epub.EpubHtml(title=chapter_title, file_name=f'chap_{page_num + 1}.xhtml', lang='en')
        chapter.content = f'<h1>{chapter_title}</h1><p>{text}</p>'
        book.add_item(chapter)
        chapters.append(chapter)

    book.toc = tuple(chapters)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # Define CSS style
    style = 'BODY {color: black;}'
    nav_css = epub.EpubItem(uid="style_nav", file_name="style/nav.css", media_type="text/css", content=style)
    book.add_item(nav_css)

    book.spine = ['nav'] + chapters
    epub.write_epub(epub_path, book, {})
    print(f"\nePub created successfully at '{epub_path}'")

def main():
    parser = argparse.ArgumentParser(description="Convert a PDF ebook to an ePub file with Typhoon OCR and embedded images support.")
    parser.add_argument("input", help="Path to the input PDF file.")
    parser.add_argument("-o", "--output", help="Path to the output ePub file (optional).")
    parser.add_argument("-k", "--api-key", help="Typhoon API Key for OCR. Alternatively, set the TYPHOON_API_KEY environment variable.", default=os.environ.get("TYPHOON_API_KEY"))
    
    args = parser.parse_args()

    input_file = args.input
    output_file = args.output
    
    if not output_file:
        output_file = os.path.splitext(input_file)[0] + ".epub"

    if not args.api_key:
        print("Warning: No Typhoon API Key provided. OCR will be skipped. Use -k or set TYPHOON_API_KEY environment variable.")

    pdf_to_epub(input_file, output_file, args.api_key)

if __name__ == "__main__":
    main()
