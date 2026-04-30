import argparse
import os
import time
import json
import re
import requests
from collections import deque
from ebooklib import epub
# Use pymupdf directly to avoid fitz namespace collisions
import pymupdf

TYPHOON_API_URL = "https://api.opentyphoon.ai/v1/ocr"

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
            
        self.calls_sec.append(now)
        self.calls_min.append(now)

# Initialize global rate limiter: 5 req/s and 200 req/m
ocr_rate_limiter = RateLimiter(max_calls_sec=5, max_calls_min=200)

def perform_ocr(image_bytes, api_key):
    """
    Performs OCR on a given image bytes using Typhoon OCR endpoint.
    Respects rate limits.
    """
    if not api_key:
        raise ValueError("Typhoon API key is required for OCR.")

    try:
        # Pass image bytes directly without saving to disk
        files = {'file': ('image.jpg', image_bytes, 'image/jpeg')}
        data = {
            'model': 'typhoon-ocr',
            'task_type': 'default',
            'max_tokens': '16384',
            'temperature': '0.1',
            'top_p': '0.6',
            'repetition_penalty': '1.2'
        }

        headers = {
            'Authorization': f'Bearer {api_key}'
        }
        
        # Enforce rate limits before making the request
        ocr_rate_limiter.wait()
        
        response = requests.post(TYPHOON_API_URL, files=files, data=data, headers=headers)
        
        if response.status_code == 200:
            result = response.json()

            # Extract text from successful results
            extracted_texts = []
            for page_result in result.get('results', []):
                if page_result.get('success') and page_result.get('message'):
                    content = page_result['message']['choices'][0]['message']['content']
                    try:
                        # Try to parse as JSON if it's structured output
                        parsed_content = json.loads(content)
                        text = parsed_content.get('natural_text', content)
                    except json.JSONDecodeError:
                        text = content
                    extracted_texts.append(text)
                elif not page_result.get('success'):
                    print(f"Error processing {page_result.get('filename', 'unknown')}: {page_result.get('error', 'Unknown error')}")

            return '\n'.join(extracted_texts)
        else:
            response.raise_for_status() 
            
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Network error during Typhoon OCR: {e}")
    except Exception as e:
        raise RuntimeError(f"An error occurred during Typhoon OCR: {e}")

def process_text_formatting(text):
    """
    Processes plain text to handle paragraphs and line breaks properly.
    Double newlines become paragraph boundaries.
    Single newlines become <br/>.
    """
    if not text:
        return ""
        
    # Standardize line endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    
    # Split into paragraphs based on double newlines (or more)
    # The regex \n\s*\n matches two newlines with optional whitespace in between
    paragraphs = re.split(r'\n\s*\n', text.strip())
    
    formatted_html = ""
    for p in paragraphs:
        if not p.strip():
            continue
        # Replace single newlines within a paragraph with <br/>
        p_html = p.replace('\n', '<br/>\n')
        # Wrap the whole block in <p> tags
        formatted_html += f"<p>{p_html}</p>\n"
        
    return formatted_html

def extract_formatted_text_from_pdf(page, skip_rects=None):
    """
    Attempts to extract text from a PDF page while preserving basic formatting
    like bold, italic, and underline using PyMuPDF's dict extraction.
    Ignores text that falls inside any of the skip_rects.
    """
    if skip_rects is None:
        skip_rects = []
        
    html_out = ""
    
    # Extract text as a dictionary containing font information
    page_dict = page.get_text("dict")
    blocks = page_dict.get("blocks", [])
    
    for block in blocks:
        if block.get("type") == 0:  # Text block
            block_rect = pymupdf.Rect(block.get("bbox"))
            
            # Check if block is entirely inside a skip rect
            skip = False
            for s_rect in skip_rects:
                 # Check overlap
                 if s_rect.intersects(block_rect):
                     # For simplicity, if it intersects a skip area, we skip the whole block
                     # A more precise implementation would check line by line or span by span
                     skip = True
                     break
            if skip:
                continue

            html_out += "<p>"
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    # PyMuPDF span flags: bit 0 = superscript, bit 1 = italic, bit 2 = serif, bit 3 = monospaced, bit 4 = bold
                    flags = span.get("flags", 0)
                    
                    is_italic = flags & 2
                    is_bold = flags & 16
                    
                    if is_bold: text = f"<b>{text}</b>"
                    if is_italic: text = f"<i>{text}</i>"
                    
                    html_out += text
                html_out += "<br/>\n" # Line break at end of line
            html_out += "</p>\n" # End of block (paragraph)
            
    return html_out

def crop_image_from_page(page, rect):
    """
    Crops an area from a page and returns it as image bytes.
    """
    # Ensure the rect is within page bounds
    rect = rect.intersect(page.rect)
    if rect.is_empty:
        return None
    
    pix = page.get_pixmap(clip=rect)
    return pix.tobytes("png")
    
def convert_project(project_data, project_dir, api_key, progress_callback=None):
    """
    Main conversion function intended to be called from the web backend.
    """
    pdf_path = os.path.join(project_dir, project_data['pdf_path'])
    epub_filename = f"{project_data.get('project_name', 'output')}.epub"
    epub_path = os.path.join(project_dir, epub_filename)
    
    settings = project_data.get('settings', {})
    global_skips_norm = settings.get('global_skip_areas', [])
    page_configs = settings.get('page_configs', {})

    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found at '{pdf_path}'")

    doc = pymupdf.open(pdf_path)
    book = epub.EpubBook()
    book.set_title(project_data.get('project_name', 'Converted Book'))
    book.set_language('en') # TODO: Make configurable

    chapters = []
    image_counter = 1
    
    total_pages = len(doc)
    
    current_chapter_content = ""
    current_chapter_title = "Start" # Default first chapter title

    for page_idx in range(total_pages):
        page_num_human = page_idx + 1
        page = doc.load_page(page_idx)
        p_width = page.rect.width
        p_height = page.rect.height
        
        # Get settings for this page
        p_config = page_configs.get(str(page_num_human), {})
        is_front_cover = p_config.get('isFrontCover', False)
        is_full_image = p_config.get('isFullImage', False)
        
        # Convert normalized UI coordinates to PyMuPDF Rect objects
        # Note: UI coordinates are (x, y, width, height) where x,y are top-left
        # PyMuPDF Rect is (x0, y0, x1, y1)
        
        # Global skip areas
        global_skip_rects = []
        for box in global_skips_norm:
             r = pymupdf.Rect(box['x'] * p_width, box['y'] * p_height, 
                           (box['x'] + box['width']) * p_width, (box['y'] + box['height']) * p_height)
             global_skip_rects.append(r)

        # Page-specific boxes
        page_skip_rects = []
        page_image_rects = []
        page_chapter_rects = []
        
        for box in p_config.get('boxes', []):
            r = pymupdf.Rect(box['x'] * p_width, box['y'] * p_height,
                           (box['x'] + box['width']) * p_width, (box['y'] + box['height']) * p_height)
            if box['type'] == 'skip':
                page_skip_rects.append(r)
            elif box['type'] == 'image':
                page_image_rects.append(r)
            elif box['type'] == 'chapter_start':
                page_chapter_rects.append(r)
        
        all_skip_rects = global_skip_rects + page_skip_rects
        
        page_content_html = ""
        new_chapter_title_found = None

        # --- Handle Special Page Types ---
        if is_front_cover or is_full_image:
             # Render the whole page as an image
             pix = page.get_pixmap()
             image_bytes = pix.tobytes("png")
             img_filename = f"image_{image_counter}.png"
             image_item = epub.EpubImage(
                 uid=f"img_{image_counter}",
                 file_name=f"images/{img_filename}",
                 media_type="image/png",
                 content=image_bytes
             )
             book.add_item(image_item)
             page_content_html += f'<p><img src="images/{img_filename}" alt="Page {page_num_human}" style="max-width: 100%;"/></p>\n'
             image_counter += 1
             
        else:
            # --- Process Marked Image Areas ---
            for img_rect in page_image_rects:
                image_bytes = crop_image_from_page(page, img_rect)
                if image_bytes:
                    img_filename = f"image_{image_counter}.png"
                    image_item = epub.EpubImage(
                        uid=f"img_{image_counter}",
                        file_name=f"images/{img_filename}",
                        media_type="image/png",
                        content=image_bytes
                    )
                    book.add_item(image_item)
                    page_content_html += f'<p><img src="images/{img_filename}" alt="Image {image_counter}"/></p>\n'
                    # Add image rect to skip rects so we don't OCR it or extract text from it
                    all_skip_rects.append(img_rect)
                    image_counter += 1
            
            # --- Process Chapter Start Markings ---
            for chap_rect in page_chapter_rects:
                 # Try to extract text natively first
                 text = page.get_text("text", clip=chap_rect).strip()
                 if not text:
                     # If empty, try OCR
                     chap_img_bytes = crop_image_from_page(page, chap_rect)
                     if chap_img_bytes:
                         text_ocr = perform_ocr(chap_img_bytes, api_key)
                         if text_ocr: text = text_ocr.strip()
                 if text:
                     new_chapter_title_found = text.replace('\n', ' ')
                 all_skip_rects.append(chap_rect) # Don't duplicate the title in body text

            # --- Extract Main Text ---
            # Fast check for text density outside of skip rects
            raw_text_all = page.get_text("text")
            
            # Create a temporary page copy to redact skip areas for OCR
            temp_page_for_ocr = doc.load_page(page_idx)
            for s_rect in all_skip_rects:
                temp_page_for_ocr.draw_rect(s_rect, color=(1, 1, 1), fill=(1, 1, 1)) # Draw white box to redact
            
            # If the page is mostly images or has very little native text, OCR it
            if len(raw_text_all.strip()) < 100: # Heuristic: if less than 100 chars, consider it sparse
                pix = temp_page_for_ocr.get_pixmap()
                page_img_bytes = pix.tobytes("png")
                ocr_text = perform_ocr(page_img_bytes, api_key)
                if ocr_text:
                    page_content_html += process_text_formatting(ocr_text)
            else:
                 # Otherwise, extract text natively, respecting skip areas
                 page_content_html += extract_formatted_text_from_pdf(page, all_skip_rects)
                 
        # --- Chapter Breaking Logic ---
        if new_chapter_title_found or (page_idx == 0 and not current_chapter_content): # Force first page to be a chapter if no explicit mark
            # Finalize the previous chapter if content exists
            if current_chapter_content:
                c = epub.EpubHtml(title=current_chapter_title, file_name=f'chap_{len(chapters)+1}.xhtml', lang='en')
                c.content = f'<h1>{current_chapter_title}</h1>\n{current_chapter_content}'
                book.add_item(c)
                chapters.append(c)
            
            # Start a new chapter
            current_chapter_title = new_chapter_title_found if new_chapter_title_found else f"Chapter {len(chapters)+1}"
            current_chapter_content = page_content_html
        else:
            # Append to current chapter
            current_chapter_content += page_content_html

        # Update progress
        if progress_callback:
            progress_callback(int((page_idx + 1) / total_pages * 100))

    # Finalize the very last chapter
    if current_chapter_content:
        c = epub.EpubHtml(title=current_chapter_title, file_name=f'chap_{len(chapters)+1}.xhtml', lang='en')
        c.content = f'<h1>{current_chapter_title}</h1>\n{current_chapter_content}'
        book.add_item(c)
        chapters.append(c)

    if not chapters:
         # Fallback if somehow no chapters were created (e.g., empty PDF)
         c = epub.EpubHtml(title="Content", file_name='chap_1.xhtml', lang='en')
         c.content = "<h1>Content</h1>"
         book.add_item(c)
         chapters.append(c)

    book.toc = tuple(chapters)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # Define CSS style
    style = 'BODY {color: black;}' # TODO: Make configurable
    nav_css = epub.EpubItem(uid="style_nav", file_name="style/nav.css", media_type="text/css", content=style)
    book.add_item(nav_css)

    book.spine = ['nav'] + chapters
    epub.write_epub(epub_path, book, {})
    return epub_filename

# --- CLI Compatibility ---
def pdf_to_epub_cli(pdf_path, epub_path, api_key):
    """
    Legacy CLI wrapper for backward compatibility.
    """
    # Create a dummy project_data structure for CLI usage
    project_name = os.path.splitext(os.path.basename(pdf_path))[0]
    project_data = {
        'project_name': project_name,
        'pdf_path': os.path.basename(pdf_path),
        'settings': {
            'page_size': 'default', # CLI doesn't configure this
            'global_skip_areas': [],
            'page_configs': {}
        }
    }
    
    # The project_dir needs to be the directory containing the PDF for convert_project
    project_dir = os.path.dirname(os.path.abspath(pdf_path))
    if not project_dir: project_dir = "." # If path is just filename, assume current dir

    print(f"Starting conversion for '{pdf_path}'...")
    try:
        final_epub_filename = convert_project(project_data, project_dir, api_key)
        print(f"\nePub created successfully at '{os.path.join(project_dir, final_epub_filename)}'")
    except Exception as e:
        print(f"\nError during conversion: {e}")

def main():
    parser = argparse.ArgumentParser(description="Convert a PDF ebook to an ePub file with Typhoon OCR and embedded images support.")
    parser.add_argument("input", help="Path to the input PDF file.")
    parser.add_argument("-o", "--output", help="Path to the output ePub file (optional).")
    parser.add_argument("-k", "--api-key", help="Typhoon API Key for OCR. Alternatively, set the TYPHOON_API_KEY environment variable.", default=os.environ.get("TYPHOON_API_KEY"))
    
    args = parser.parse_args()

    input_file = args.input
    output_file = args.output # Note: output_file is not directly used by convert_project, it uses project_name
    
    if not args.api_key:
        print("Warning: No Typhoon API Key provided. OCR will be skipped. Use -k or set TYPHOON_API_KEY environment variable.")

    pdf_to_epub_cli(input_file, output_file, args.api_key)

if __name__ == "__main__":
    main()
