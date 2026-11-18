import os
import socket
socket.setdefaulttimeout(60)
import sys
import json
import io
import time
import base64
import hashlib
import webbrowser
import threading
import re
import shutil
import subprocess
import html
from pathlib import Path
from flask import Flask, render_template, request, jsonify
from PIL import Image

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

try:
    import requests
except ImportError:
    requests = None

try:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
except ImportError:
    Credentials = None
    build = None
    MediaIoBaseUpload = None
    MediaIoBaseDownload = None

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

try:
    import pypdfium2 as pdfium
except ImportError:
    pdfium = None

try:
    import numpy as np
except ImportError:
    np = None

try:
    import json_repair
except ImportError:
    json_repair = None

app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "assets" / "data"
PC_WEB_DATA_DIR = BASE_DIR / "pc_exam_web" / "data"
CONFIG_FILE = BASE_DIR / ".admin_config.json"

def save_exam_data(exam_id: str, data: dict):
    """
    Saves exam data to assets/data/{exam_id}.json for the mobile APK,
    and automatically syncs it to pc_exam_web/data/{exam_id}.json for the GitHub Web Portal.
    """
    target_file = DATA_DIR / f"{exam_id}.json"
    with open(target_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    try:
        if PC_WEB_DATA_DIR.exists():
            web_file = PC_WEB_DATA_DIR / f"{exam_id}.json"
            with open(web_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as sync_err:
        print(f"[AdminSync] Warning: Failed to sync {exam_id}.json to pc_exam_web/data: {sync_err}")

DEFAULT_API_KEY = os.environ.get("GEMINI_API_KEY", "")

def load_config():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"gemini_api_key": DEFAULT_API_KEY}

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

def get_gemini_client(api_key=None):
    if not genai:
        raise RuntimeError("google-genai package is not installed.")
    key = api_key or load_config().get("gemini_api_key") or DEFAULT_API_KEY
    return genai.Client(api_key=key)

def normalize_devanagari_numerals(text):
    """Converts any Devanagari digits (०-९) into standard English/Arabic digits (0-9)."""
    if not text or not isinstance(text, str):
        return text
    table = str.maketrans("०१२३४५६७८९", "0123456789")
    return text.translate(table)

def strip_question_numbers(text):
    """Strips leading question numbers (e.g. '16.', 'Q.16:', 'Question 16 -') and direction number ranges (e.g. '(16-20)') from question text."""
    if not text or not isinstance(text, str):
        return text
    # 1. Clean direction ranges: 'Directions (16-20):' -> 'Directions:', 'निर्देश (16-20):' -> 'निर्देश:'
    text = re.sub(r'(?i)\b(Directions?|Questions?|Study the following(?: information)?|Read the following(?: passage)?)\s*\([Qq\.\s]*\d+\s*[-–to\s]+\d+\)\s*:?', r'\1:', text)
    text = re.sub(r'(?i)\b(निर्देश|प्रश्न|निम्नलिखित जानकारी का अध्ययन(?: कीजिए| करें)?)\s*\([Qq\.\s]*\d+\s*[-–to\s]+\d+\)\s*:?', r'\1:', text)
    # Standalone (16-20): or (Q. 16-20):
    text = re.sub(r'^\s*\([Qq\.\s]*\d+\s*[-–to\s]+\d+\)\s*:?\s*', '', text)
    text = re.sub(r'^\s*\([Qq\.\s]*[०-९]+\s*[-–to\s]+[०-९]+\)\s*:?\s*', '', text)

    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        # Match '16. ', '16) ', '16 - ', 'Q.16: ', 'Question 16 - ', 'Que 16: ', 'प्रश्न 16: '
        cl = re.sub(r'^\s*(?:(?:Question|Que|Q|प्रश्न|प्र)\.?\s*\d+|\d+)\s*[\.\:\)\-\–]\s*', '', line, flags=re.IGNORECASE)
        # Also catch 'Question 16 ' without punctuation
        cl = re.sub(r'^\s*(?:Question|Que|Q|प्रश्न|प्र)\.?\s*\d+\s+', '', cl, flags=re.IGNORECASE)
        cleaned_lines.append(cl)
    return '\n'.join(cleaned_lines).strip()

def normalize_text_newlines(val):
    """Converts escaped newline literals (\\n) and carriage returns to real newlines."""
    if not isinstance(val, str):
        return val
    val = val.replace('\\n', '\n').replace(r'\n', '\n')
    val = val.replace('\\r', '').replace(r'\r', '')
    return val

def remove_watermark_from_chart(pil_img, bg_thresh=215):
    """
    Cleans faint translucent/grayish background watermarks (e.g. test series brand names)
    from cropped charts and diagrams while preserving dark lines, colored pie slices,
    bars, text, numbers, and framing borders.
    """
    if pil_img is None:
        return None
    try:
        # Handle transparency safely by compositing over white
        if pil_img.mode in ("RGBA", "LA") or (pil_img.mode == "P" and "transparency" in pil_img.info):
            bg = Image.new("RGB", pil_img.size, (255, 255, 255))
            rgba = pil_img.convert("RGBA")
            bg.paste(rgba, mask=rgba.split()[3])
            rgb_img = bg
        else:
            rgb_img = pil_img.convert("RGB")

        if np is not None:
            arr = np.array(rgb_img, dtype=np.float32)
            r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
            min_ch = np.minimum(np.minimum(r, g), b)
            max_ch = np.maximum(np.maximum(r, g), b)
            diff_ch = max_ch - min_ch

            # Faint neutral/gray watermark on light paper:
            # min channel is high (>= bg_thresh) and saturation is very low (diff < 15, neutral gray)
            mask = (min_ch >= bg_thresh) & (diff_ch < 15)
            # Preserve the outer boundary edges so framing lines are never eroded
            mask[0:2, :] = False
            mask[-2:, :] = False
            mask[:, 0:2] = False
            mask[:, -2:] = False

            cleaned = arr.copy()
            cleaned[mask] = 255.0
            return Image.fromarray(cleaned.astype(np.uint8))
        else:
            # Fallback if numpy is missing: PIL pointwise mapping
            return rgb_img.point(lambda p: 255 if p >= bg_thresh else p)
    except Exception as e:
        print(f"Warning: watermark removal skipped due to: {e}")
        return pil_img

def safe_json_loads(text):
    r"""
    Robust JSON loader that safely handles LLM outputs containing:
    - Markdown code fences (```json ... ```)
    - Unescaped inner quotes and raw unescaped newlines/tabs
    - Unescaped LaTeX backslashes (\frac, \times, \sqrt, \%, \$, \beta, \theta, etc.)
    - Truncated or partially closed JSON structures
    - Trailing commas before closing brackets
    """
    if not text:
        raise ValueError("Empty response from AI model")

    text = text.strip()
    # Strip markdown code fences if present
    if "```json" in text:
        text = text.split("```json", 1)[1]
        if "```" in text:
            text = text.split("```", 1)[0]
        text = text.strip()
    elif "```" in text:
        text = text.split("```", 1)[1]
        if "```" in text:
            text = text.split("```", 1)[0]
        text = text.strip()

    # Pass 1: Try json_repair directly (repairs unescaped inner quotes, missing brackets, unescaped newlines, etc.)
    if json_repair is not None:
        try:
            parsed = json_repair.loads(text)
            if parsed is not None and (isinstance(parsed, list) or isinstance(parsed, dict)):
                return parsed
        except Exception:
            pass

    # Pass 2: Try direct parse
    try:
        return json.loads(text, strict=False)
    except Exception:
        pass

    # Pass 3: Fix unescaped backslashes commonly emitted in LaTeX formulas
    def fix_backslash(match):
        following = match.group(1)
        next_char = match.group(2) if match.group(2) else ""
        if following == '"':
            return '\\"' + next_char
        if following == '\\':
            return '\\\\' + next_char
        if following == 'n' and (not next_char or not next_char.isalpha()):
            return '\\n' + next_char
        if following == 't' and (not next_char or not next_char.isalpha()):
            return '\\t' + next_char
        if following == 'r' and (not next_char or not next_char.isalpha()):
            return '\\r' + next_char
        return '\\\\' + following + next_char

    cleaned = re.sub(r'\\(.)([a-zA-Z0-9]?)', fix_backslash, text)
    cleaned = re.sub(r',\s*([\]\}])', r'\1', cleaned)

    try:
        return json.loads(cleaned, strict=False)
    except Exception:
        pass

    # Pass 4: json_repair on cleaned text
    if json_repair is not None:
        try:
            parsed = json_repair.repair_json(cleaned, return_objects=True)
            if parsed is not None and (isinstance(parsed, list) or isinstance(parsed, dict)):
                return parsed
        except Exception:
            pass

    # Pass 5: Brute force double all single backslashes except before quote
    cleaned2 = re.sub(r'\\(?!["])', r'\\\\', text)
    cleaned2 = re.sub(r'\\\\\\\\', r'\\\\', cleaned2)
    cleaned2 = re.sub(r',\s*([\]\}])', r'\1', cleaned2)
    try:
        return json.loads(cleaned2, strict=False)
    except Exception:
        pass

    # Pass 6: Last resort, re-raise original or cleaned parse error
    return json.loads(cleaned, strict=False)

def auto_repair_latex(text):
    if not text or not isinstance(text, str):
        return text or ""
    text = re.sub(r'[\r\n\s]+ightarrow\b', r' \\rightarrow', text)
    text = re.sub(r'(^|[^a-zA-Z\\])ightarrow\b', r'\1\\rightarrow', text)
    text = re.sub(r'[\r\n\s]+leftarrow\b', r' \\leftarrow', text)
    text = re.sub(r'(^|[^a-zA-Z\\])leftarrow\b', r'\1\\leftarrow', text)
    text = re.sub(r'(^|[^a-zA-Z\\])Rightarrow\b', r'\1\\Rightarrow', text)
    text = re.sub(r'(^|[^a-zA-Z\\])Leftarrow\b', r'\1\\Leftarrow', text)
    text = re.sub(r'(^|[^a-zA-Z\\])imes\b', r'\1\\times', text)
    text = re.sub(r'(^|[^a-zA-Z\\])rac\{', r'\1\\frac{', text)
    return text

def parse_box_coords(box, img_width, img_height):
    """
    Parses any format of bounding box (0..1 float, 0..1000 int, pixel coords, or dict)
    into clamped (left, top, right, bottom) pixel coordinates without artificial outer padding.
    """
    if not box:
        return None

    if isinstance(box, dict):
        if "width" in box and "height" in box:
            x = box.get("x", box.get("left", 0))
            y = box.get("y", box.get("top", 0))
            w = box["width"]
            h = box["height"]
            box = [y, x, y + h, x + w]
        else:
            ymin = box.get("ymin", box.get("top", 0))
            xmin = box.get("xmin", box.get("left", 0))
            ymax = box.get("ymax", box.get("bottom", 0))
            xmax = box.get("xmax", box.get("right", 0))
            box = [ymin, xmin, ymax, xmax]

    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return None

    try:
        raw = [float(v) for v in box]
    except (ValueError, TypeError):
        return None

    ymin, xmin, ymax, xmax = raw
    y1, y2 = min(ymin, ymax), max(ymin, ymax)
    x1, x2 = min(xmin, xmax), max(xmin, xmax)

    max_val = max(y2, x2)
    if max_val <= 1.0:
        top = int(y1 * img_height)
        bottom = int(y2 * img_height)
        left = int(x1 * img_width)
        right = int(x2 * img_width)
    elif max_val <= 1000:
        top = int((y1 / 1000.0) * img_height)
        bottom = int((y2 / 1000.0) * img_height)
        left = int((x1 / 1000.0) * img_width)
        right = int((x2 / 1000.0) * img_width)
    else:
        top = int(y1)
        bottom = int(y2)
        left = int(x1)
        right = int(x2)

    top = max(0, min(img_height, top))
    left = max(0, min(img_width, left))
    bottom = max(0, min(img_height, bottom))
    right = max(0, min(img_width, right))

    if (right - left) >= 15 and (bottom - top) >= 15:
        return (left, top, right, bottom)
    return None

def refine_border_crop(pil_img, left, top, right, bottom, max_snap_px=25, line_thresh=236):
    """
    Snaps candidate bounding box directly on outer rectangular border lines of charts,
    diagrams, and tables.
    GUARANTEES:
    1. NEVER snaps to page boundaries / headers (ignores lines near image edges: y < 15 or y > h - 15).
    2. NEVER snaps to internal grid lines (max_snap_px is strictly clamped to at most 25px or 8% of dimension).
    3. NEVER cuts off half of a chart or graph.
    """
    if pil_img is None:
        return (left, top, right, bottom)
    try:
        w, h = pil_img.size
        left = max(0, min(w - 1, int(left)))
        right = max(0, min(w, int(right)))
        top = max(0, min(h - 1, int(top)))
        bottom = max(0, min(h, int(bottom)))

        width = right - left
        height = bottom - top
        if width < 30 or height < 30:
            return (left, top, right, bottom)

        gray = pil_img.convert('L')
        arr = np.array(gray) if np is not None else None
        if arr is None:
            return (left, top, right, bottom)

        # Dynamic snap limit: max 25px, or 8% of width/height
        snap_x = min(max_snap_px, max(5, int(width * 0.08)))
        snap_y = min(max_snap_px, max(5, int(height * 0.08)))

        # Ignore outer page margins (header/footer black lines at y < 15 or y > h - 15)
        min_safe_y = 15
        max_safe_y = h - 15
        min_safe_x = 15
        max_safe_x = w - 15

        row_l = max(min_safe_x, left - snap_x)
        row_r = min(max_safe_x, right + snap_x)

        # 1. Search for top border row in [top - snap_y, top + snap_y]
        y_top_start = max(min_safe_y, top - snap_y)
        y_top_end = min(max_safe_y, top + snap_y)
        candidates_top = []
        for y in range(y_top_start, y_top_end + 1):
            row_slice = arr[y, row_l:row_r]
            mask = row_slice < line_thresh
            if np.any(mask):
                diff = np.diff(np.concatenate(([0], mask.astype(int), [0])))
                starts = np.where(diff == 1)[0]
                ends = np.where(diff == -1)[0]
                if len(starts) > 0 and len(ends) > 0:
                    lens = ends - starts
                    max_idx = np.argmax(lens)
                    run_len = lens[max_idx]
                    if run_len >= 0.50 * width:
                        candidates_top.append((y, run_len, row_l + starts[max_idx], row_l + ends[max_idx]))

        best_top = None
        if candidates_top:
            best_top = min(candidates_top, key=lambda c: abs(c[0] - top) - 0.2 * c[1])

        # 2. Search for bottom border row in [bottom - snap_y, bottom + snap_y]
        y_bot_start = max(min_safe_y, bottom - snap_y)
        y_bot_end = min(max_safe_y, bottom + snap_y)
        candidates_bot = []
        for y in range(y_bot_start, y_bot_end + 1):
            row_slice = arr[y, row_l:row_r]
            mask = row_slice < line_thresh
            if np.any(mask):
                diff = np.diff(np.concatenate(([0], mask.astype(int), [0])))
                starts = np.where(diff == 1)[0]
                ends = np.where(diff == -1)[0]
                if len(starts) > 0 and len(ends) > 0:
                    lens = ends - starts
                    max_idx = np.argmax(lens)
                    run_len = lens[max_idx]
                    if run_len >= 0.50 * width:
                        candidates_bot.append((y, run_len, row_l + starts[max_idx], row_l + ends[max_idx]))

        best_bot = None
        if candidates_bot:
            best_bot = min(candidates_bot, key=lambda c: abs(c[0] - bottom) - 0.2 * c[1])

        # If both top and bottom horizontal lines span the same rectangle:
        if best_top and best_bot:
            top = best_top[0]
            bottom = best_bot[0]
            top_l, top_r = best_top[2], best_top[3]
            bot_l, bot_r = best_bot[2], best_bot[3]
            if abs(top_l - bot_l) <= 15 and abs(top_r - bot_r) <= 15:
                left = min(top_l, bot_l)
                right = max(top_r, bot_r)
                return (int(left), int(top), min(w, int(right) + 1), min(h, int(bottom) + 1))

        left_span = best_top[2] if best_top else (best_bot[2] if best_bot else None)
        right_span = best_top[3] if best_top else (best_bot[3] if best_bot else None)
        if best_top:
            top = best_top[0]
        if best_bot:
            bottom = best_bot[0]

        # 3. Vertical Left border
        x_target = left_span if left_span is not None and abs(left_span - left) <= snap_x else left
        x_l_start = max(min_safe_x, x_target - snap_x)
        x_l_end = min(max_safe_x, x_target + snap_x)
        candidates_l = []
        for x in range(x_l_start, x_l_end + 1):
            col_slice = arr[top:bottom+1, x]
            mask = col_slice < line_thresh
            if np.any(mask):
                diff = np.diff(np.concatenate(([0], mask.astype(int), [0])))
                starts = np.where(diff == 1)[0]
                ends = np.where(diff == -1)[0]
                if len(starts) > 0 and len(ends) > 0:
                    run_len = np.max(ends - starts)
                    if run_len >= 0.55 * (bottom - top):
                        candidates_l.append((x, run_len))

        if candidates_l:
            best_l = min(candidates_l, key=lambda c: abs(c[0] - x_target) - 0.2 * c[1])
            left = best_l[0]
        elif left_span is not None and abs(left_span - left) <= snap_x:
            left = left_span

        # 4. Vertical Right border
        x_r_target = right_span if right_span is not None and abs(right_span - right) <= snap_x else right
        x_r_start = max(min_safe_x, x_r_target - snap_x)
        x_r_end = min(max_safe_x, x_r_target + snap_x)
        candidates_r = []
        for x in range(x_r_start, x_r_end + 1):
            col_slice = arr[top:bottom+1, x]
            mask = col_slice < line_thresh
            if np.any(mask):
                diff = np.diff(np.concatenate(([0], mask.astype(int), [0])))
                starts = np.where(diff == 1)[0]
                ends = np.where(diff == -1)[0]
                if len(starts) > 0 and len(ends) > 0:
                    run_len = np.max(ends - starts)
                    if run_len >= 0.55 * (bottom - top):
                        candidates_r.append((x, run_len))

        if candidates_r:
            best_r = min(candidates_r, key=lambda c: abs(c[0] - x_r_target) - 0.2 * c[1])
            right = best_r[0]
        elif right_span is not None and abs(right_span - right) <= snap_x:
            right = right_span

        # Safety: ensure box dimensions are sane (min 30px each side)
        if (right - left) < 30:
            right = left + 30
        if (bottom - top) < 30:
            bottom = top + 30

        return (int(left), int(top), min(w, int(right) + 1), min(h, int(bottom) + 1))
    except Exception as e:
        print('refine_border_crop exception:', e)
        return (int(left), int(top), int(right), int(bottom))

def classify_rect(arr, rect, line_thresh=225):
    """Classifies a detected rectangular region as 'table' (has multiple internal gridlines) or 'chart'."""
    l, t, r, b = rect
    w = r - l
    internal_h_lines = 0
    for y in range(t + 10, b - 10):
        row = arr[y, l:r]
        mask = row < line_thresh
        if np.any(mask):
            diff = np.diff(np.concatenate(([0], mask.astype(int), [0])))
            starts = np.where(diff == 1)[0]
            ends = np.where(diff == -1)[0]
            if len(starts) > 0 and np.max(ends - starts) >= 0.70 * w:
                internal_h_lines += 1
    return "table" if internal_h_lines >= 2 else "chart"

def find_diagram_rectangles(pil_img, min_width=100, min_height=60, line_thresh=232):
    """
    Finds all closed framing rectangular bounding boxes of charts, diagrams, and tables on a page.
    Returns a list of dicts: [{'box': (left, top, right, bottom), 'type': 'table'|'chart'}]
    """
    if pil_img is None:
        return []
    try:
        gray = pil_img.convert('L')
        arr = np.array(gray)
        h, w = arr.shape

        h_lines = []
        for y in range(15, h - 15):
            row = arr[y, :]
            mask = row < line_thresh
            if np.any(mask):
                diff = np.diff(np.concatenate(([0], mask.astype(int), [0])))
                starts = np.where(diff == 1)[0]
                ends = np.where(diff == -1)[0]
                for s, e in zip(starts, ends):
                    if (e - s) >= min_width:
                        h_lines.append((y, s, e, e - s))

        v_lines = []
        for x in range(15, w - 15):
            col = arr[:, x]
            mask = col < line_thresh
            if np.any(mask):
                diff = np.diff(np.concatenate(([0], mask.astype(int), [0])))
                starts = np.where(diff == 1)[0]
                ends = np.where(diff == -1)[0]
                for s, e in zip(starts, ends):
                    if (e - s) >= min_height:
                        v_lines.append((x, s, e, e - s))

        rects = []
        for i, (y1, s1, e1, len1) in enumerate(h_lines):
            for j in range(i + 1, len(h_lines)):
                y2, s2, e2, len2 = h_lines[j]
                box_h = y2 - y1
                if box_h < min_height:
                    continue
                if abs(s1 - s2) <= 15 and abs(e1 - e2) <= 15 and abs(len1 - len2) <= 15:
                    l = min(s1, s2)
                    r = max(e1, e2)
                    t = y1
                    b = y2
                    has_left = any(abs(vx - l) <= 12 and vs <= t + 20 and ve >= b - 20 for vx, vs, ve, vh in v_lines)
                    has_right = any(abs(vx - r) <= 12 and vs <= t + 20 and ve >= b - 20 for vx, vs, ve, vh in v_lines)
                    if has_left and has_right:
                        rects.append((l, t, r, b))

        if not rects:
            return []

        merged = []
        for rect in sorted(rects, key=lambda b: (b[2]-b[0])*(b[3]-b[1]), reverse=True):
            l, t, r_x, b = rect
            is_inside = any(ml <= l + 12 and mt <= t + 12 and mr >= r_x - 12 and mb >= b - 12 for ml, mt, mr, mb in [m['box'] for m in merged])
            if not is_inside:
                r_tuple = (int(l), int(t), int(r_x), int(b))
                r_type = classify_rect(arr, r_tuple)
                merged.append({'box': r_tuple, 'type': r_type})
        return merged
    except Exception as e:
        print("find_diagram_rectangles exception:", e)
        return []

def insert_diagram_tag_intelligently(text, tag="[img1]", is_explanation=False, reference_prefix=None):
    """
    Intelligently inserts [img1] (or [img2]) at the exact layout location:
    - For questions: after common passage and notes (e.g. 'Note: I)...') and before the specific question sentence.
    - For explanations: after initial derivation / 'calculate other values' and before 'Answer: D' or calculation steps.
    Never blindly prepends to the beginning of the text.
    """
    if not text:
        return tag
    if tag in text:
        return text

    text = text.strip()

    # If reference prefix from Q1 is available in a set
    if reference_prefix and reference_prefix.strip():
        ref_clean = reference_prefix.strip()
        if text.startswith(ref_clean):
            remainder = text[len(ref_clean):].strip()
            return f"{ref_clean}\n\n{tag}\n\n{remainder}".strip()

    if not is_explanation:
        # Check for paragraph break before common question start words
        q_start_pat = re.compile(
            r'\n+(\s*(?:If\b|What\b|Find\b|How\b|Which\b|Calculate\b|In how\b|At what\b|Out of\b|The ratio of\b|यदि\b|ज्ञात\b|कितन\b|कौन\b))',
            re.IGNORECASE
        )
        match = q_start_pat.search(text)
        if match:
            idx = match.start()
            if idx > 30:
                head = text[:idx].strip()
                tail = text[idx:].strip()
                return f"{head}\n\n{tag}\n\n{tail}".strip()

        # Check for end of Note: block
        note_pat = re.compile(r'(Note\s*:[\s\S]*?)(?=\n[A-Z]|\Z)', re.IGNORECASE)
        match_note = note_pat.search(text)
        if match_note:
            end_idx = match_note.end()
            if end_idx < len(text) - 20:
                head = text[:end_idx].strip()
                tail = text[end_idx:].strip()
                return f"{head}\n\n{tag}\n\n{tail}".strip()

        # If multiple paragraphs, insert before the last paragraph
        paras = [p.strip() for p in text.split('\n\n') if p.strip()]
        if len(paras) >= 2:
            return '\n\n'.join(paras[:-1]) + f"\n\n{tag}\n\n" + paras[-1]

        # Single paragraph: append at end
        return f"{text}\n\n{tag}"

    else:
        # Explanation text: look for 'Answer:', 'Ans:', 'Therefore', 'Hence', etc.
        ans_pat = re.compile(r'\n+(\s*(?:Answer\s*:|Ans\s*:|उत्तर\s*:|Therefore|Hence|Thus|Now,?\s+the))', re.IGNORECASE)
        match = ans_pat.search(text)
        if match:
            idx = match.start()
            if idx > 20:
                head = text[:idx].strip()
                tail = text[idx:].strip()
                return f"{head}\n\n{tag}\n\n{tail}".strip()

        # Check for phrases like 'calculate other values' or 'table below'
        table_intro_pat = re.compile(
            r'(?:calculate other values|table (?:is )?given below|following table|summary table|'
            r'arrangement (?:is )?as follows|final arrangement|final table|'
            r'तालिका (?:नीचे दी गई है|दी गई है|है)|सारणी|व्यवस्था)[\.\:]?',
            re.IGNORECASE
        )
        match_intro = table_intro_pat.search(text)
        if match_intro:
            end_idx = match_intro.end()
            head = text[:end_idx].strip()
            tail = text[end_idx:].strip()
            return f"{head}\n\n{tag}\n\n{tail}".strip()

        paras = [p.strip() for p in text.split('\n\n') if p.strip()]
        if len(paras) >= 2:
            return '\n\n'.join(paras[:-1]) + f"\n\n{tag}\n\n" + paras[-1]

        return f"{text}\n\n{tag}"

def sync_diagram_tags_in_text(text, image_count, is_explanation=False):
    """
    Synchronizes [img1], [img2] tags in the text with the actual count of attached images:
    - Removes dead tags [imgK] where K > image_count.
    - Ensures each tag [img1] ... [imgN] exists in the text at its intelligent layout location.
    """
    if not text:
        return text
    # Remove any tags [imgK] where K > image_count
    for k in range(image_count + 1, 10):
        text = re.sub(rf'\[img{k}\]\s*', '', text)
    # Ensure [img1] ... [imgN] exist
    for k in range(1, image_count + 1):
        tag = f"[img{k}]"
        if tag not in text:
            text = insert_diagram_tag_intelligently(text, tag=tag, is_explanation=is_explanation)
    return text.strip()

def resolve_page_pil_and_idx(p_idx, pils_dict, selected_pages):
    """
    Resolves both the PIL image and canonical page index from pageIndex.
    Handles:
    - 0-based sequence index among rendered pages (0, 1, 2...)
    - 1-based sequence index (1, 2, 3...)
    - Document 0-based page index (e.g. 12, 13...)
    - Document 1-based page number (e.g. 13, 14...)
    Returns (pil_img, canonical_p_idx)
    """
    if not pils_dict:
        return None, 0

    ordered_keys = [p for p in selected_pages if p in pils_dict]
    if not ordered_keys:
        ordered_keys = sorted(list(pils_dict.keys()))

    # Direct key match
    if p_idx in pils_dict:
        return pils_dict[p_idx], p_idx

    try:
        p_num = int(re.sub(r'\D', '', str(p_idx)))
    except Exception:
        p_num = 0

    if p_num in pils_dict:
        return pils_dict[p_num], p_num

    # 0-based sequence index among provided pages (e.g. 0 for first rendered page)
    if 0 <= p_num < len(ordered_keys):
        k = ordered_keys[p_num]
        return pils_dict[k], k

    # 1-based sequence index among provided pages
    if 1 <= p_num <= len(ordered_keys):
        k = ordered_keys[p_num - 1]
        return pils_dict[k], k

    # Document 1-based page number (e.g. PDF page 5 is doc index 4)
    if (p_num - 1) in pils_dict:
        return pils_dict[p_num - 1], p_num - 1

    first_k = ordered_keys[0]
    return pils_dict[first_k], first_k

def resolve_page_from_lookup(raw_idx, lookup, pils_dict, default_pages):
    """
    Bulletproof page resolver: checks direct lookup map first, then int conversion,
    and falls back to resolve_page_pil_and_idx.
    """
    if lookup:
        if raw_idx in lookup:
            return lookup[raw_idx]
        try:
            p_num = int(re.sub(r'\D', '', str(raw_idx)))
            if p_num in lookup:
                return lookup[p_num]
        except Exception:
            pass
    return resolve_page_pil_and_idx(raw_idx, pils_dict, default_pages)

def resolve_page_pil(p_idx, pils_dict, selected_pages):
    """Legacy compatibility wrapper."""
    pil_img, _ = resolve_page_pil_and_idx(p_idx, pils_dict, selected_pages)
    return pil_img

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
    return response

@app.route("/", defaults={"path": ""}, methods=["OPTIONS"])
@app.route("/<path:path>", methods=["OPTIONS"])
def options_handler(path):
    response = app.make_default_options_response()
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With"
    return response

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/config", methods=["GET", "POST"])
def config_route():
    cfg = load_config()
    if request.method == "POST":
        data = request.get_json() or {}
        new_key = data.get("gemini_api_key", "").strip()
        if new_key:
            cfg["gemini_api_key"] = new_key
            save_config(cfg)
            return jsonify({"status": "ok", "message": "API Key saved successfully!"})
        return jsonify({"status": "error", "message": "API key cannot be empty"}), 400
    
    masked = cfg.get("gemini_api_key", "")
    if len(masked) > 8:
        masked = masked[:4] + "..." + masked[-4:]
    return jsonify({
        "status": "ok",
        "has_api_key": bool(cfg.get("gemini_api_key")),
        "masked_api_key": masked,
        "api_key": cfg.get("gemini_api_key", DEFAULT_API_KEY)
    })

# ==========================================
# Google Drive API & Image Studio Endpoints
# ==========================================

EXAM_DISPLAY_NAMES = {
    "sbi_clerk": "SBI Clerk",
    "sbi_po": "SBI PO",
    "ibps_clerk": "IBPS Clerk",
    "ibps_po": "IBPS PO",
    "rrb_clerk": "RRB Clerk",
    "rrb_po": "RRB PO"
}

def get_gdrive_config():
    cfg = load_config()
    return cfg.get("gdrive", {})

def save_gdrive_config(gdrive_data):
    cfg = load_config()
    existing = cfg.get("gdrive", {})
    existing.update(gdrive_data)
    cfg["gdrive"] = existing
    save_config(cfg)

def get_drive_service():
    if not Credentials or not build:
        return None
    gdrive = get_gdrive_config()
    client_id = gdrive.get("client_id")
    client_secret = gdrive.get("client_secret")
    refresh_token = gdrive.get("refresh_token")
    access_token = gdrive.get("access_token")

    if not client_id or not client_secret or not refresh_token:
        return None

    try:
        creds = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret
        )
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        print("Error building Google Drive service:", e)
        return None

def find_drive_folder(service, folder_name, parent_id=None):
    try:
        q = "mimeType='application/vnd.google-apps.folder' and trashed=false"
        if parent_id:
            q += f" and '{parent_id}' in parents"
        else:
            q += " and 'root' in parents"

        res = service.files().list(q=q, fields="files(id, name)", spaces='drive', pageSize=100).execute()
        files = res.get('files', [])
        for f in files:
            if f.get('name', '').strip().lower() == folder_name.strip().lower():
                return f['id']
    except Exception as e:
        print(f"Error finding folder {folder_name}:", e)
    return None

def get_or_create_drive_folder(service, folder_name, parent_id=None):
    existing_id = find_drive_folder(service, folder_name, parent_id)
    if existing_id:
        return existing_id

    meta = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder'
    }
    if parent_id:
        meta['parents'] = [parent_id]
    created = service.files().create(body=meta, fields='id').execute()
    return created.get('id')

@app.route("/api/gdrive/status", methods=["GET"])
def gdrive_status():
    gdrive = get_gdrive_config()
    is_connected = bool(gdrive.get("is_connected") and gdrive.get("refresh_token"))
    return jsonify({
        "status": "ok",
        "connected": is_connected,
        "email": gdrive.get("connected_email", "") if is_connected else "",
        "has_client_config": bool(gdrive.get("client_id") and gdrive.get("client_secret")),
        "client_id_masked": (gdrive.get("client_id", "")[:8] + "..." + gdrive.get("client_id", "")[-6:]) if gdrive.get("client_id") else "",
        "client_id": gdrive.get("client_id", ""),
        "client_secret": gdrive.get("client_secret", "")
    })

@app.route("/api/gdrive/config", methods=["POST"])
def gdrive_save_config():
    data = request.get_json() or {}
    client_id = data.get("client_id", "").strip()
    client_secret = data.get("client_secret", "").strip()
    if not client_id or not client_secret:
        return jsonify({"status": "error", "message": "Both Client ID and Client Secret are required"}), 400

    save_gdrive_config({
        "client_id": client_id,
        "client_secret": client_secret
    })
    return jsonify({"status": "ok", "message": "Google Drive API credentials saved successfully!"})

@app.route("/api/gdrive/auth-url", methods=["GET"])
def gdrive_auth_url():
    gdrive = get_gdrive_config()
    client_id = gdrive.get("client_id")
    if not client_id:
        return jsonify({
            "status": "error",
            "message": "Google Client ID is not configured yet. Please enter Client ID and Client Secret first."
        }), 400

    redirect_uri = request.host_url.rstrip('/') + "/api/gdrive/oauth2callback"
    scopes = [
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/userinfo.email"
    ]
    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={client_id}&"
        f"redirect_uri={redirect_uri}&"
        f"response_type=code&"
        f"scope={' '.join(scopes)}&"
        f"access_type=offline&"
        f"prompt=consent"
    )
    return jsonify({"status": "ok", "auth_url": auth_url, "redirect_uri": redirect_uri})

@app.route("/api/gdrive/oauth2callback", methods=["GET"])
def gdrive_oauth2callback():
    code = request.args.get("code")
    error = request.args.get("error")
    if error:
        return f"<div style='font-family:sans-serif;padding:30px;'><h3>Google OAuth Error:</h3><p>{error}</p><p><a href='/'>Return to Admin Studio</a></p></div>", 400
    if not code:
        return "<div style='font-family:sans-serif;padding:30px;'><h3>Missing code parameter</h3><p><a href='/'>Return to Admin Studio</a></p></div>", 400

    gdrive = get_gdrive_config()
    client_id = gdrive.get("client_id")
    client_secret = gdrive.get("client_secret")
    redirect_uri = request.base_url

    token_url = "https://oauth2.googleapis.com/token"
    token_data = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"
    }

    try:
        token_resp = requests.post(token_url, data=token_data).json()
    except Exception as te:
        return f"<div style='font-family:sans-serif;padding:30px;'><h3>Failed to contact Google Token Endpoint:</h3><p>{te}</p></div>", 500

    if "error" in token_resp:
        return f"<div style='font-family:sans-serif;padding:30px;'><h3>Authorization Failed:</h3><p>{token_resp.get('error_description', token_resp.get('error'))}</p><p><a href='/'>Return to Admin Studio</a></p></div>", 400

    access_token = token_resp.get("access_token")
    refresh_token = token_resp.get("refresh_token") or gdrive.get("refresh_token")

    user_email = "Connected User"
    try:
        user_info = requests.get("https://www.googleapis.com/oauth2/v2/userinfo", headers={"Authorization": f"Bearer {access_token}"}).json()
        user_email = user_info.get("email", user_email)
    except Exception:
        pass

    save_gdrive_config({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "connected_email": user_email,
        "is_connected": True
    })

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <title>Google Drive Connected</title>
      <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-slate-900 text-white font-sans flex items-center justify-center min-h-screen p-6">
      <div class="bg-slate-800 border border-slate-700 rounded-2xl p-8 max-w-md w-full text-center space-y-4 shadow-2xl">
        <div class="w-16 h-16 bg-emerald-500/20 text-emerald-400 rounded-2xl flex items-center justify-center mx-auto text-3xl font-bold">✓</div>
        <h2 class="text-xl font-bold">Google Drive Connected!</h2>
        <p class="text-sm text-slate-300">Signed in as <strong class="text-white">{user_email}</strong></p>
        <p class="text-xs text-slate-400">Exam folders and public link generation are now active.</p>
        <button onclick="if(window.opener){{window.opener.postMessage({{type:'gdrive_connected',email:'{user_email}'}},'*');window.close();}}else{{window.location.href='/?gdrive=connected';}}" class="w-full py-2.5 bg-blue-600 hover:bg-blue-500 rounded-xl font-bold text-sm shadow-md transition">
          Return to Admin Studio
        </button>
      </div>
      <script>
        setTimeout(() => {{
          if (window.opener) {{
            window.opener.postMessage({{ type: 'gdrive_connected', email: '{user_email}' }}, '*');
            window.close();
          }} else {{
            window.location.href = '/?gdrive=connected';
          }}
        }}, 1600);
      </script>
    </body>
    </html>
    """

@app.route("/api/gdrive/disconnect", methods=["POST"])
def gdrive_disconnect():
    save_gdrive_config({
        "access_token": None,
        "refresh_token": None,
        "connected_email": None,
        "is_connected": False
    })
    return jsonify({"status": "ok", "message": "Disconnected from Google Drive."})

def upload_bytes_to_drive(file_bytes, exam_id="sbi_clerk", image_type="question", label="", custom_filename="", ext="png", mime_type="image/png"):
    service = get_drive_service()
    if not service:
        return None, "Google Drive is not connected. Please connect Google Drive first."

    try:
        exam_folder_name = EXAM_DISPLAY_NAMES.get(exam_id, exam_id.upper().replace("_", " "))

        # 1. First, check if the exam folder exists directly in root My Drive (as created by user: "SBI Clerk", "SBI PO", "IBPS PO", etc.)
        exam_folder_id = find_drive_folder(service, exam_folder_name, parent_id=None)
        folder_breadcrumb = exam_folder_name

        # 2. If not found in root, check/create inside "Target Bank Exam"
        if not exam_folder_id:
            root_folder_id = get_or_create_drive_folder(service, "Target Bank Exam")
            exam_folder_id = get_or_create_drive_folder(service, exam_folder_name, root_folder_id)
            folder_breadcrumb = f"Target Bank Exam / {exam_folder_name}"

        # 3. Locate or create subfolder inside the exam folder
        if image_type == "question":
            target_folder_id = find_drive_folder(service, "Questions", parent_id=exam_folder_id)
            if not target_folder_id:
                target_folder_id = find_drive_folder(service, "Questions (DI & Statements)", parent_id=exam_folder_id)
            if not target_folder_id:
                target_folder_id = get_or_create_drive_folder(service, "Questions", parent_id=exam_folder_id)
            type_folder_name = "Questions"
        else:
            target_folder_id = find_drive_folder(service, "Solutions", parent_id=exam_folder_id)
            if not target_folder_id:
                target_folder_id = find_drive_folder(service, "Solutions (Puzzles & Answers)", parent_id=exam_folder_id)
            if not target_folder_id:
                target_folder_id = find_drive_folder(service, "Answers", parent_id=exam_folder_id)
            if not target_folder_id:
                target_folder_id = get_or_create_drive_folder(service, "Solutions", parent_id=exam_folder_id)
            type_folder_name = "Solutions"

        timestamp_str = time.strftime("%Y%m%d_%H%M%S")
        type_tag = "Q" if image_type == "question" else "SOL"
        clean_label = re.sub(r'[^a-zA-Z0-9_-]+', '_', label).strip('_') if label else ""

        if custom_filename:
            final_filename = custom_filename
            if not final_filename.endswith(f".{ext}"):
                final_filename += f".{ext}"
        else:
            if clean_label:
                final_filename = f"{exam_id}_{type_tag}_{clean_label}_{timestamp_str}.{ext}"
            else:
                final_filename = f"{exam_id}_{type_tag}_{timestamp_str}.{ext}"

        media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype=mime_type, resumable=False)
        file_meta = {
            'name': final_filename,
            'parents': [target_folder_id]
        }
        uploaded = None
        last_upload_err = None
        for attempt in range(3):
            try:
                uploaded = service.files().create(body=file_meta, media_body=media, fields='id, name, webViewLink, webContentLink').execute()
                break
            except Exception as ue:
                last_upload_err = ue
                print(f"[GDrive Upload Warning] Attempt {attempt+1}/3 failed: {ue}")
                if attempt < 2:
                    time.sleep(1.5)
        if not uploaded:
            return None, f"Google Drive connection timed out after 3 attempts: {last_upload_err}"
        file_id = uploaded.get('id')

        # Make file public for mobile app CDN access
        try:
            service.permissions().create(
                fileId=file_id,
                body={'type': 'anyone', 'role': 'reader'}
            ).execute()
        except Exception as pe:
            print("Permissions warning:", pe)

        direct_url = f"https://lh3.googleusercontent.com/d/{file_id}"
        share_url = f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
        folder_path = f"{folder_breadcrumb} / {type_folder_name}"

        return {
            "status": "ok",
            "fileId": file_id,
            "directUrl": direct_url,
            "shareUrl": share_url,
            "folderPath": folder_path,
            "filename": final_filename,
            "imageType": image_type,
            "examId": exam_id,
            "message": f"Successfully uploaded to {folder_path}!"
        }, None
    except Exception as ex:
        print("Google Drive upload error:", ex)
        return None, str(ex)

@app.route("/api/gdrive/upload", methods=["POST"])
def gdrive_upload():
    data = request.get_json() or {}
    image_b64 = data.get("image")
    exam_id = data.get("examId", "sbi_clerk")
    image_type = data.get("imageType", "question") # "question" or "solution"
    label = data.get("label", "").strip()
    custom_filename = data.get("filename", "").strip()

    if not image_b64:
        return jsonify({"status": "error", "message": "No image data provided"}), 400

    mime_type = "image/png"
    if "data:" in image_b64 and ";base64," in image_b64:
        header, base64_str = image_b64.split(";base64,", 1)
        mime_type = header.replace("data:", "").strip()
    else:
        base64_str = image_b64

    try:
        file_bytes = base64.b64decode(base64_str)
    except Exception as e:
        return jsonify({"status": "error", "message": f"Invalid image base64 data: {str(e)}"}), 400

    ext = "png"
    if "jpeg" in mime_type or "jpg" in mime_type:
        ext = "jpg"
    elif "webp" in mime_type:
        ext = "webp"

    res, err = upload_bytes_to_drive(
        file_bytes=file_bytes,
        exam_id=exam_id,
        image_type=image_type,
        label=label,
        custom_filename=custom_filename,
        ext=ext,
        mime_type=mime_type
    )

    if err:
        return jsonify({"status": "error", "message": f"Google Drive upload failed: {err}"}), 500

    return jsonify(res)

@app.route("/api/proxy-image", methods=["GET"])
def proxy_image():
    raw_url = request.args.get("url", "").strip()
    if not raw_url:
        return "Missing url parameter", 400
    if raw_url.startswith("data:"):
        return "Cannot proxy data URI", 400
    try:
        # Check if it is a Google Drive URL
        match = re.search(r'/d/([a-zA-Z0-9_-]+)', raw_url) or re.search(r'id=([a-zA-Z0-9_-]+)', raw_url)
        file_id = match.group(1) if match else None

        service = get_gdrive_service()
        if service and file_id and MediaIoBaseDownload:
            try:
                drive_req = service.files().get_media(fileId=file_id)
                buf = io.BytesIO()
                downloader = MediaIoBaseDownload(buf, drive_req)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                return buf.getvalue(), 200, {
                    "Content-Type": "image/png",
                    "Cache-Control": "public, max-age=86400"
                }
            except Exception as ge:
                print("Drive API proxy download error:", ge)

        # Fallback to requests HTTP fetch
        if requests:
            resp = requests.get(raw_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                ctype = resp.headers.get("Content-Type", "image/png")
                return resp.content, 200, {
                    "Content-Type": ctype,
                    "Cache-Control": "public, max-age=86400"
                }
        return "Image not found", 404
    except Exception as e:
        print("Proxy error:", e)
        return str(e), 500

@app.route("/api/exams", methods=["GET"])
def get_exams():
    exams = []
    if not DATA_DIR.exists():
        return jsonify({"exams": []})
    
    for f in DATA_DIR.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as jf:
                data = json.load(jf)
                exam_meta = data.get("exam", {})
                dpp_meta = data.get("dppMeta", [])
                questions = data.get("questions", [])
                
                # Count questions per dpp day, topic, sectional, and memory based
                dpp_counts = {}
                topic_counts = {}
                sectional_counts = {}
                mb_counts = {}
                for q in questions:
                    qtype = q.get("type")
                    if qtype == "dpp":
                        day = q.get("dppDay")
                        if day is not None:
                            dpp_counts[day] = dpp_counts.get(day, 0) + 1
                    elif qtype in ("sectional", "sectional_test"):
                        sec_key = f"{q.get('sectionId', 'quant')}_t{q.get('testNumber', 1)}"
                        sectional_counts[sec_key] = sectional_counts.get(sec_key, 0) + 1
                    elif qtype in ("pyq", "memory_based") or q.get("year"):
                        yr = q.get("year")
                        if yr:
                            mb_counts[yr] = mb_counts.get(yr, 0) + 1
                    else:
                        top = q.get("topicId", "unknown")
                        topic_counts[top] = topic_counts.get(top, 0) + 1
                
                # Auto-sync topics from existing questions into stages/sections so NO topic is ever lost
                stages = data.get("stages", [])
                for q in questions:
                    if q.get("type") == "topicwise" or q.get("topicId"):
                        tid = q.get("topicId")
                        if tid and tid not in ("dpp_mixed", "unknown", "general") and not str(tid).startswith("pyq_"):
                            st_id = q.get("stageId", "prelims")
                            sec_id = q.get("sectionId", "quant")
                            st_obj = next((s for s in stages if s.get("id") == st_id), None)
                            if not st_obj:
                                st_obj = {"id": st_id, "name": st_id.title(), "sections": []}
                                stages.append(st_obj)
                            sec_obj = next((sec for sec in st_obj.setdefault("sections", []) if sec.get("id") == sec_id), None)
                            if not sec_obj:
                                sec_obj = {"id": sec_id, "name": sec_id.title(), "topics": []}
                                st_obj["sections"].append(sec_obj)
                            sec_topics = sec_obj.setdefault("topics", [])
                            if not any(t.get("id") == tid for t in sec_topics):
                                sec_topics.append({
                                    "id": tid,
                                    "name": tid.replace("_", " ").title(),
                                    "timerMinutes": q.get("timerMinutes", 10)
                                })

                exams.append({
                    "id": exam_meta.get("id", f.stem),
                    "name": exam_meta.get("name", f.stem.replace("_", " ").title()),
                    "organization": exam_meta.get("organization", ""),
                    "post": exam_meta.get("post", ""),
                    "filename": f.name,
                    "stages": data.get("stages", []),
                    "dppMeta": dpp_meta,
                    "memoryBasedPapers": data.get("memoryBasedPapers", []),
                    "dppCounts": dpp_counts,
                    "topicCounts": topic_counts,
                    "sectionalCounts": sectional_counts,
                    "mbCounts": mb_counts,
                    "totalQuestions": len(questions)
                })
        except Exception as e:
            print(f"Error reading {f}: {e}")
    
    # Sort with SBI and IBPS first
    exams.sort(key=lambda x: x["id"])
    return jsonify({"exams": exams})

def parse_drive_links_map(raw_text):
    """Parses bulk drive links formatted like: 1 [https://drive.google.com/...] 2 [https://...]"""
    import re
    if not raw_text:
        return {}
    link_map = {}
    # Matches: 1 [url] or Q1 [url] or 1: [url] or Q1: url
    pattern = re.compile(r'(?:q|question)?\s*(\d+)\s*[:=\-]?\s*\[\s*(https?://[^\s\]]+)\s*\]', re.IGNORECASE)
    for match in pattern.finditer(raw_text):
        qnum = int(match.group(1))
        url = match.group(2).strip()
        link_map[qnum] = url
    if not link_map:
        # Fallback simple pattern: 1 http://...
        fallback = re.compile(r'(?:q|question)?\s*(\d+)\s*[:=\-]?\s*(https?://[^\s]+)', re.IGNORECASE)
        for match in fallback.finditer(raw_text):
            qnum = int(match.group(1))
            url = match.group(2).strip()
            link_map[qnum] = url
    return link_map

def normalize_images_list(val):
    """Ensures input value is converted to a clean list of non-empty strings."""
    if not val:
        return []
    if isinstance(val, list):
        return [str(item).strip() for item in val if str(item).strip()]
    if isinstance(val, str) and val.strip():
        return [val.strip()]
    return []

def extract_question_images_payload(q_data):
    """Extracts and normalizes multi-image and bilingual fields from question payload."""
    q_images = normalize_images_list(q_data.get("questionImages"))
    if not q_images and q_data.get("questionImageDriveLink"):
        q_images = normalize_images_list(q_data.get("questionImageDriveLink"))

    q_images_hi = normalize_images_list(q_data.get("questionImagesHi"))

    exp_images = normalize_images_list(q_data.get("explanationImages"))
    if not exp_images and q_data.get("explanationImageDriveLink"):
        exp_images = normalize_images_list(q_data.get("explanationImageDriveLink"))

    exp_images_hi = normalize_images_list(q_data.get("explanationImagesHi"))

    return {
        "questionImageDriveLink": q_images[0] if q_images else (q_data.get("questionImageDriveLink") or None),
        "questionImages": q_images,
        "questionImagesHi": q_images_hi if q_images_hi else None,
        "explanationImageDriveLink": exp_images[0] if exp_images else (q_data.get("explanationImageDriveLink") or None),
        "explanationImages": exp_images,
        "explanationImagesHi": exp_images_hi if exp_images_hi else None,
    }

@app.route("/api/extract-ai", methods=["POST"])
def extract_ai():
    try:
        data = request.get_json() or {}
        question_images_b64 = data.get("question_images", [])
        solution_images_b64 = data.get("solution_images", [])
        hindi_question_images_b64 = data.get("hindi_question_images", [])
        hindi_solution_images_b64 = data.get("hindi_solution_images", [])
        legacy_images_b64 = data.get("images", [])
        question_drive_images = normalize_images_list(data.get("question_drive_images"))
        question_hi_drive_images = normalize_images_list(data.get("question_hi_drive_images"))
        solution_drive_images = normalize_images_list(data.get("solution_drive_images"))
        solution_hi_drive_images = normalize_images_list(data.get("solution_hi_drive_images"))
        is_set_based = bool(data.get("is_set_based", False))
        no_diagrams = bool(data.get("no_diagrams", False) or data.get("is_passage_only", False))
        drive_links_raw = data.get("drive_links", "").strip()
        instructions = data.get("instructions", "").strip()
        custom_key = data.get("api_key", "").strip() or None

        # Consolidate images
        if not question_images_b64 and not solution_images_b64 and not hindi_question_images_b64 and not hindi_solution_images_b64:
            question_images_b64 = legacy_images_b64

        if not question_images_b64 and not solution_images_b64 and not hindi_question_images_b64 and not hindi_solution_images_b64:
            return jsonify({"status": "error", "message": "No images provided"}), 400

        client = get_gemini_client(custom_key)
        parts = []

        # Add English Question Images
        for idx, item in enumerate(question_images_b64):
            if "," in item:
                header, b64_str = item.split(",", 1)
                mime = header.split(";")[0].replace("data:", "") if "data:" in header else "image/png"
            else:
                b64_str = item
                mime = "image/png"
            img_bytes = base64.b64decode(b64_str)
            parts.append(f"--- ENGLISH QUESTION IMAGE #{idx + 1} ---")
            parts.append(types.Part.from_bytes(data=img_bytes, mime_type=mime))

        # Add English Solution Images
        for idx, item in enumerate(solution_images_b64):
            if "," in item:
                header, b64_str = item.split(",", 1)
                mime = header.split(";")[0].replace("data:", "") if "data:" in header else "image/png"
            else:
                b64_str = item
                mime = "image/png"
            img_bytes = base64.b64decode(b64_str)
            parts.append(f"--- ENGLISH SOLUTION / ANSWER IMAGE #{idx + 1} ---")
            parts.append(types.Part.from_bytes(data=img_bytes, mime_type=mime))

        # Add Hindi Question Images
        for idx, item in enumerate(hindi_question_images_b64):
            if "," in item:
                header, b64_str = item.split(",", 1)
                mime = header.split(";")[0].replace("data:", "") if "data:" in header else "image/png"
            else:
                b64_str = item
                mime = "image/png"
            img_bytes = base64.b64decode(b64_str)
            parts.append(f"--- HINDI QUESTION IMAGE #{idx + 1} ---")
            parts.append(types.Part.from_bytes(data=img_bytes, mime_type=mime))

        # Add Hindi Solution Images
        for idx, item in enumerate(hindi_solution_images_b64):
            if "," in item:
                header, b64_str = item.split(",", 1)
                mime = header.split(";")[0].replace("data:", "") if "data:" in header else "image/png"
            else:
                b64_str = item
                mime = "image/png"
            img_bytes = base64.b64decode(b64_str)
            parts.append(f"--- HINDI SOLUTION / ANSWER IMAGE #{idx + 1} ---")
            parts.append(types.Part.from_bytes(data=img_bytes, mime_type=mime))

        has_hindi = bool(hindi_question_images_b64 or hindi_solution_images_b64)

        prompt = """
You are an expert OCR and exam question extractor for Indian Banking Competitive Examinations (SBI PO/Clerk, IBPS PO/Clerk, RRB PO/Clerk, RBI Assistant).

Analyze the provided image(s).
"""
        if has_hindi:
            prompt += """
IMAGE GROUPING RULE (BILINGUAL ENGLISH & HINDI EXTRACTION):
- The first group contains ENGLISH QUESTION image(s) with statements and options.
- The second group contains ENGLISH SOLUTION / ANSWER image(s) (if provided).
- The third group contains HINDI QUESTION image(s) with statements and options.
- The fourth group contains HINDI SOLUTION / ANSWER image(s) (if provided).
- Match English Question 1 with Hindi Question 1, English Question 2 with Hindi Question 2, etc.
- Copy Hindi question text, options, and explanations directly and faithfully from the Hindi images.

MANDATORY NUMERAL RULE FOR HINDI (CRITICAL - DO NOT VIOLATE):
- In Indian banking competitive exams, ALL numbers, digits, amounts, percentages, ratios, fractions, years, currency symbols (₹), and variables in Hindi MUST BE WRITTEN IN STANDARD ENGLISH / ARABIC DIGITS (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, e.g. 1200, 45%, 3:5, ₹500, 2024)!
- NEVER USE DEVANAGARI NUMERALS (०, १, २, ३, ४, ५, ६, ७, ८, ९) under any circumstances! If the Hindi image contains Devanagari numerals, you MUST convert them to standard English digits (0-9).
"""
        elif solution_images_b64:
            prompt += """
IMAGE GROUPING RULE:
- The first group of image(s) contains QUESTION statements, multiple-choice options, and diagrams.
- The second group of image(s) contains the SOLUTIONS, calculation steps, and ANSWER KEYS.
- Match Question 1 from the question image(s) with Solution 1 from the solution image(s), Question 2 with Solution 2, and so on.
"""
        else:
            prompt += """
- The image(s) contain question statements, options, and solutions/answer keys. If solutions are below or in subsequent sections, match each question with its corresponding solution.
"""

        if is_set_based:
            prompt += """
CRITICAL SET-BASED (DI / RC / PUZZLE / SEATING ARRANGEMENT) RULE:
- These questions share a common passage, directions, or context (e.g. 'Directions (Q. 1-5): ...').
- You MUST repeat and prepend this common passage/directions to the BEGINNING of EACH question's `questionText` (and `questionTextHi` in Hindi) so every single question is completely self-contained when answered individually!
"""

        prompt += """
CRITICAL RULE: DO NOT TRANSCRIBE DIAGRAMS / TABLES / CHARTS INTO TEXT (DIAGRAM EXCLUSION RULE):
- If any question contains a diagram, table, chart, graph, bar chart, pie chart, Venn diagram, puzzle arrangement, or visual figure:
  * DO NOT convert or transcribe the table/chart rows, numbers, or diagram contents into text or markdown tables inside `questionText` or `questionTextHi`!
  * Instead, place the tag `[img1]` (or `[img2]`, `[img3]` if there are multiple diagrams) at the exact position in the question statement where the diagram/table belongs!
  * Only extract the text directions, question statements, variables, and multiple-choice options. NEVER recreate the data inside the diagram/table as text!
- The same rule applies to solutions/explanations:
  * If the solution or explanation contains a puzzle diagram, seating arrangement figure, or graph, DO NOT draw ASCII/text diagrams or transcribe the diagram.
  * Instead, place the tag `[img1]` (or `[img2]`) in `explanation` (and `explanationHi`) at the location where the diagram belongs.

CRITICAL RULE: STRICTLY STRIP AND EXCLUDE ALL QUESTION NUMBERS AND DIRECTION RANGES:
- In exam screenshots and textbook questions, questions frequently start with printed numbers, e.g.:
  * "16.", "17.", "18.", "Q.16:", "Question 16:", "16)"
  * "Directions (16-20):" or "Direction (Q. 16-20):" or "Directions (16 to 20):" or "निर्देश (16-20):"
- You MUST STRIP AND NEVER OUTPUT THESE QUESTION NUMBERS OR NUMBER RANGES in `questionText` or `questionTextHi`!
- The question statement MUST start directly with the actual sentence without any question number (e.g. convert "16. Who sits to the immediate right of H?" into "Who sits to the immediate right of H?").
- In directions or passages, remove the number range (e.g. convert "Directions (16-20): Ten persons are sitting..." into "Directions: Ten persons are sitting...", and "निर्देश (16-20): दस व्यक्ति..." into "निर्देश: दस व्यक्ति...").

CRITICAL RULE: DITTO TYPOGRAPHY, INDENTATION, BOLDNESS & ITALICS (PRESERVE EXACT STYLING):
- Maintain EXACT formatting, boldness, italics, and line indentation as shown in the source document or image!
- If words or labels are bold in the source (e.g. statement labels 'I.', 'II.', 'III.', variable names, names of persons, conditions, column headers), use Markdown bold `**word**`.
- If words are italicized, use `*word*`.
- Preserve indentation, multiple line breaks, and paragraph structures faithfully.
- For syllogisms, puzzle statements, coded inequalities, data sufficiency, and multiple Roman numeral statements:
  Put each statement or conclusion on its own indented line, preserving bold labels like:
  **Statements:**
    I. Some cats are dogs.
    II. No dog is a bird.
  **Conclusions:**
    I. Some cats are not birds.
    II. All dogs can be cats.
- Ensure that the generated question text and solution text look DITTO identical in styling, boldness, and indentation to the original document or image.

MANDATORY RULES FOR MATHEMATICAL EQUATIONS AND SYMBOLS (CRITICAL):
1. ALL mathematical formulas, fractions, powers, roots, equations, percentages in calculations, ratios, and algebraic expressions MUST be formatted in LaTeX notation using $...$ for inline math and $$...$$ for block math!
   - Examples of proper LaTeX:
     - "Find the value of $x$: $\\frac{45}{100} \\times 600 + 35\\% \\times 400 = x$"
     - "If $x^2 - 7x + 12 = 0$ and $y = \\sqrt{144}$"
     - "The ratio is $3 : 5$ and average is $\\frac{a + b}{2} = 40$"
     - "$\\sqrt[3]{1728} + 18^2 - 15 = ?$"
   - NEVER output raw unformatted fractions like 45/100 or roots without LaTeX $...$ formatting!
2. Extract all options (usually 4 or 5 options: A, B, C, D, E). Format math inside options using LaTeX as well!
3. Identify the correct answer:
   - Determine `correctIndex` as a 0-based integer (0 for A, 1 for B, 2 for C, 3 for D, 4 for E).
   - If the answer key is visible in the image, use it. If not, solve the question accurately to determine the right option.
4. Write a detailed, step-by-step mathematical explanation using LaTeX for all calculation steps.
5. Set `difficulty` to 'Easy', 'Medium', or 'Hard' based on banking exam standards.

Output MUST be a valid, parseable JSON array of question objects matching this schema:
[
  {
    "questionText": "Question statement in English with LaTeX $...$ and optional [img1] tag",
    "questionTextHi": """ + ('"Question statement in Hindi with English digits (0-9), LaTeX $...$ and optional [img1] tag"' if has_hindi else 'null') + """,
    "options": ["Option A with $...$", "Option B with $...$", "Option C with $...$", "Option D with $...$"],
    "optionsHi": """ + ('["Option A in Hindi", "Option B in Hindi", "Option C in Hindi", "Option D in Hindi"]' if has_hindi else 'null') + """,
    "correctIndex": 0,
    "explanation": "Step-by-step explanation in English with LaTeX $...$ and optional [img1] tag",
    "explanationHi": """ + ('"Step-by-step explanation in Hindi with English digits (0-9), LaTeX $...$ and optional [img1] tag"' if has_hindi else 'null') + """,
    "difficulty": "Easy"
  }
]
"""
        if no_diagrams:
            prompt += f"""
CRITICAL TEXT-ONLY PASSAGE / READING COMPREHENSION / CASELET (NO DIAGRAM CROPPING):
- This question range ({question_range_str}) is a purely TEXT-BASED paragraph/passage set (e.g. Reading Comprehension, Cloze Test, Paragraph Completion, Text Caselet).
- There are NO visual charts, graphs, figures, or diagrams to crop!
- Strictly DO NOT output any diagrams bounding boxes. Set `"diagrams": []` and `"diagramsHi": []`.
- DO NOT insert any `[img1]` or `[img2]` tags in the text!
- You MUST repeat and prepend the COMPLETE common reading passage, story, or directions paragraph to the BEGINNING of EACH question's `questionText` (and in Hindi to `questionTextHi`) so every question is 100% self-contained with full context!
"""
        if instructions:
            prompt += f"\n\nADDITIONAL USER INSTRUCTIONS:\n{instructions}"

        contents = parts + [prompt]

        # Candidate models with automatic failover on 503 (high demand) or 429 quota limits
        candidate_models = [
            "gemini-3-flash-preview",
            "gemini-3.1-flash-lite-preview",
            "gemini-2.5-flash",
            "gemini-flash-latest",
            "gemini-3.1-pro-preview",
            "gemini-pro-latest"
        ]

        gen_config = None
        if types:
            try:
                gen_config = types.GenerateContentConfig(
                    response_mime_type="application/json",
                    max_output_tokens=32768,
                    temperature=0.1
                )
            except Exception as e:
                print("Warning creating GenerateContentConfig for single image:", e)

        questions = None
        last_error = None

        for model_name in candidate_models:
            for attempt in range(2):
                try:
                    print(f"Calling Gemini Vision model: {model_name} (attempt {attempt + 1})...")
                    if gen_config:
                        response = client.models.generate_content(
                            model=model_name,
                            contents=contents,
                            config=gen_config
                        )
                    else:
                        response = client.models.generate_content(
                            model=model_name,
                            contents=contents
                        )
                    if response and response.text:
                        raw_text = response.text.strip()
                        try:
                            candidate_q = safe_json_loads(raw_text)
                            if candidate_q and (isinstance(candidate_q, list) or isinstance(candidate_q, dict)):
                                questions = candidate_q
                                print(f"Success with {model_name}!")
                                break
                        except Exception as parse_err:
                            print(f"Model {model_name} attempt {attempt + 1} produced unparseable JSON: {parse_err}")
                except Exception as err:
                    last_error = err
                    err_str = str(err)
                    print(f"Model {model_name} attempt {attempt + 1} failed: {err_str[:120]}")
                    if "404" in err_str or "NOT_FOUND" in err_str:
                        # Model not supported on this tier/API version, skip immediately without waiting
                        break
                    elif "503" in err_str or "UNAVAILABLE" in err_str or "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        time.sleep(1.5 * (attempt + 1))
                        continue
                    else:
                        break
            if questions:
                break

        if not questions:
            msg = str(last_error) if last_error else "Could not extract questions from images."
            if "503" in msg or "UNAVAILABLE" in msg:
                clean_msg = "Gemini service is temporarily experiencing high traffic (503). Retries were attempted. Please try again in a few moments."
            elif "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                clean_msg = "Gemini API rate limit or quota exceeded (429). Please wait a moment or check your Gemini API key in Settings."
            else:
                clean_msg = msg
            return jsonify({"status": "error", "message": clean_msg}), 503 if "503" in msg else 500

        if not isinstance(questions, list):
            questions = [questions]

        # Flatten any nested lists produced by json_repair (e.g. [[{...}]])
        flat_questions = []
        for item in questions:
            if isinstance(item, dict):
                flat_questions.append(item)
            elif isinstance(item, list):
                for sub in item:
                    if isinstance(sub, dict):
                        flat_questions.append(sub)
        questions = flat_questions

        if not questions:
            raise RuntimeError("Gemini returned no valid question objects in its JSON response.")

        # Post-process: enforce English digits on Hindi text and apply drive links
        drive_map = parse_drive_links_map(drive_links_raw)
        for i, q in enumerate(questions):
            # Strip question numbers from English question statement
            if q.get("questionText"):
                q["questionText"] = strip_question_numbers(q["questionText"])
            # Normalize any Devanagari numerals in Hindi fields to English numerals and strip question numbers
            if q.get("questionTextHi"):
                q["questionTextHi"] = strip_question_numbers(normalize_devanagari_numerals(q["questionTextHi"]))
            if q.get("optionsHi") and isinstance(q["optionsHi"], list):
                q["optionsHi"] = [normalize_devanagari_numerals(str(opt)) for opt in q["optionsHi"]]
            if q.get("explanationHi"):
                q["explanationHi"] = normalize_devanagari_numerals(q["explanationHi"])

            qnum = i + 1
            if drive_map and qnum in drive_map:
                q["questionImageDriveLink"] = drive_map[qnum]
                q["questionImages"] = [drive_map[qnum]]

            # Attach direct upload drive links if provided
            if question_drive_images and not q.get("questionImages"):
                q["questionImages"] = list(question_drive_images)
                q["questionImageDriveLink"] = question_drive_images[0]
            if question_hi_drive_images and not q.get("questionImagesHi"):
                q["questionImagesHi"] = list(question_hi_drive_images)
            if solution_drive_images and not q.get("explanationImages"):
                q["explanationImages"] = list(solution_drive_images)
                q["explanationImageDriveLink"] = solution_drive_images[0]
            if solution_hi_drive_images and not q.get("explanationImagesHi"):
                q["explanationImagesHi"] = list(solution_hi_drive_images)

        return jsonify({
            "status": "ok",
            "count": len(questions),
            "questions": questions
        })

    except Exception as e:
        print("Extract AI error:", e)
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/extract-pdf", methods=["POST"])
def extract_pdf():
    try:
        if not pdfium:
            return jsonify({
                "status": "error",
                "message": "pypdfium2 is not installed. Please run: pip install pypdfium2"
            }), 500

        data = request.get_json() or {}
        en_pdf_b64 = data.get("en_pdf")
        hi_pdf_b64 = data.get("hi_pdf")
        question_range_str = str(data.get("question_range", "1-5")).strip()
        page_range_str = str(data.get("page_range", "")).strip()
        exam_id = data.get("exam_id", "sbi_clerk")
        is_set_based = bool(data.get("is_set_based", False))
        no_diagrams = bool(data.get("no_diagrams", False) or data.get("is_passage_only", False) or data.get("is_text_passage_only", False))
        instructions = data.get("instructions", "").strip()
        custom_key = data.get("api_key", "").strip() or None

        if not en_pdf_b64:
            return jsonify({"status": "error", "message": "No English / Combined PDF provided."}), 400

        # Decode English / Combined PDF
        if "," in en_pdf_b64:
            en_pdf_b64 = en_pdf_b64.split(",", 1)[1]
        try:
            en_pdf_bytes = base64.b64decode(en_pdf_b64)
            doc_en = pdfium.PdfDocument(io.BytesIO(en_pdf_bytes))
        except Exception as e:
            return jsonify({"status": "error", "message": f"Could not open English PDF: {str(e)}"}), 400

        total_en_pages = len(doc_en)

        # Parse separate Hindi PDF if provided
        doc_hi = None
        total_hi_pages = 0
        if hi_pdf_b64:
            if "," in hi_pdf_b64:
                hi_pdf_b64 = hi_pdf_b64.split(",", 1)[1]
            try:
                hi_pdf_bytes = base64.b64decode(hi_pdf_b64)
                doc_hi = pdfium.PdfDocument(io.BytesIO(hi_pdf_bytes))
                total_hi_pages = len(doc_hi)
            except Exception as e:
                print("Warning: could not open Hindi PDF:", e)

        # Parse question numbers from range e.g. "1-5", "16-20", "1,2,3", "4"
        target_q_nums = []
        if "-" in question_range_str or "–" in question_range_str:
            parts = re.split(r'[-–]', question_range_str)
            try:
                start_q = int(re.sub(r'\D', '', parts[0]))
                end_q = int(re.sub(r'\D', '', parts[1]))
                target_q_nums = list(range(start_q, end_q + 1))
            except Exception:
                target_q_nums = [1, 2, 3, 4, 5]
        elif "," in question_range_str:
            for item in question_range_str.split(","):
                try:
                    num = int(re.sub(r'\D', '', item))
                    target_q_nums.append(num)
                except Exception:
                    pass
        else:
            try:
                num = int(re.sub(r'\D', '', question_range_str))
                target_q_nums = [num]
            except Exception:
                target_q_nums = [1, 2, 3, 4, 5]

        if not target_q_nums:
            target_q_nums = [1, 2, 3, 4, 5]

        # Select pages to render
        selected_en_pages = []
        if page_range_str and page_range_str.lower() != "auto":
            if "-" in page_range_str or "–" in page_range_str:
                p_parts = re.split(r'[-–]', page_range_str)
                try:
                    p_start = max(1, int(re.sub(r'\D', '', p_parts[0])))
                    p_end = min(total_en_pages, int(re.sub(r'\D', '', p_parts[1])))
                    selected_en_pages = [p - 1 for p in range(p_start, p_end + 1)]
                except Exception:
                    pass
            elif "," in page_range_str:
                for p_item in page_range_str.split(","):
                    try:
                        p_val = int(re.sub(r'\D', '', p_item))
                        if 1 <= p_val <= total_en_pages:
                            selected_en_pages.append(p_val - 1)
                    except Exception:
                        pass
            else:
                try:
                    p_val = int(re.sub(r'\D', '', page_range_str))
                    if 1 <= p_val <= total_en_pages:
                        selected_en_pages.append(p_val - 1)
                except Exception:
                    pass

        # If not manually specified, auto-detect pages intelligently
        matched_sol_pages = set()
        matched_q_pages = set()
        if not selected_en_pages:
            if total_en_pages <= 12:
                # If document is 12 pages or fewer, include ALL pages!
                # This guarantees that question pages AND solution pages (which often sit on pages 4-10) are NEVER omitted.
                selected_en_pages = list(range(total_en_pages))
            else:
                solution_keywords = [
                    "solution", "solutions", "explanation", "explanations", "answer", "answers",
                    "answer key", "ans", "hint", "hints", "उत्तर", "हल", "व्याख्या", "विस्तृत हल"
                ]
                for p_idx in range(total_en_pages):
                    try:
                        p_text = doc_en[p_idx].get_textpage().get_text_range()
                        p_text_lower = p_text.lower()
                        has_sol_kw = any(kw in p_text_lower for kw in solution_keywords)
                        for qn in target_q_nums:
                            patterns = [
                                rf'\b{qn}\s*[\.\:\)]',
                                rf'Q(?:uestion)?\s*[\.\:\-]?\s*{qn}\b',
                                rf'\({qn}\)',
                                rf'Directions?\s*\([^\)]*{qn}[^\)]*\)',
                                rf'\(Q\.?\s*{qn}\b',
                                rf'Explanations?\s*[\.\:\-]?\s*{qn}\b',
                                rf'Solutions?\s*[\.\:\-]?\s*{qn}\b',
                                rf'हल\s*[\.\:\-]?\s*{qn}\b',
                                rf'व्याख्या\s*[\.\:\-]?\s*{qn}\b'
                            ]
                            if any(re.search(pat, p_text, re.IGNORECASE) for pat in patterns):
                                if has_sol_kw:
                                    matched_sol_pages.add(p_idx)
                                else:
                                    matched_q_pages.add(p_idx)
                    except Exception:
                        pass

                # If no solution pages matched by question regex, search for solution section headers
                if not matched_sol_pages:
                    sol_section_headers = [
                        "answer key with detailed solutions", "answers & solutions",
                        "hints & solutions", "detailed solutions", "answers and explanations",
                        "answers with explanation", "उत्तर एवं व्याख्या", "हल सहित उत्तर"
                    ]
                    for p_idx in range(total_en_pages):
                        try:
                            p_text_lower = doc_en[p_idx].get_textpage().get_text_range().lower()
                            if any(hdr in p_text_lower for hdr in sol_section_headers):
                                matched_sol_pages.add(p_idx)
                        except Exception:
                            pass

                expanded = set(matched_q_pages | matched_sol_pages)
                # Expand solution pages to next page if explanation continues
                for sp in list(matched_sol_pages):
                    if sp + 1 < total_en_pages:
                        expanded.add(sp + 1)
                for qp in list(matched_q_pages):
                    if qp + 1 < total_en_pages:
                        expanded.add(qp + 1)

                # Banking PDF solutions are almost always at the end of the document.
                # If total_en_pages > 12 and matched_sol_pages is empty, include the last 3-4 pages!
                if len(matched_sol_pages) == 0:
                    for lp in range(max(0, total_en_pages - 4), total_en_pages):
                        expanded.add(lp)
                        matched_sol_pages.add(lp)

                if expanded:
                    selected_en_pages = sorted(list(expanded))[:14]
                else:
                    selected_en_pages = sorted(list(set(list(range(min(total_en_pages, 6))) + list(range(max(0, total_en_pages - 4), total_en_pages)))))[:12]

        if not selected_en_pages:
            selected_en_pages = list(range(min(total_en_pages, 12)))

        # Also populate matched_sol_pages if all pages were selected
        if not matched_sol_pages:
            solution_keywords = ["solution", "solutions", "explanation", "explanations", "answer", "answers", "answer key", "ans", "hint", "hints", "उत्तर", "हल", "व्याख्या"]
            for p_idx in selected_en_pages:
                try:
                    p_text_lower = doc_en[p_idx].get_textpage().get_text_range().lower()
                    if any(kw in p_text_lower for kw in solution_keywords):
                        matched_sol_pages.add(p_idx)
                except Exception:
                    pass
            # If still none detected, assume pages in the second half are solution pages
            if not matched_sol_pages and len(selected_en_pages) >= 2:
                for p_idx in selected_en_pages[len(selected_en_pages)//2:]:
                    matched_sol_pages.add(p_idx)

        # Select Hindi pages if separate Hindi PDF provided
        selected_hi_pages = []
        if doc_hi:
            if total_hi_pages <= 12:
                selected_hi_pages = list(range(total_hi_pages))
            else:
                matched_hi = set()
                hi_keywords = ["उत्तर", "हल", "व्याख्या", "solution", "solutions", "answer", "answers"]
                for p_idx in range(total_hi_pages):
                    try:
                        p_text = doc_hi[p_idx].get_textpage().get_text_range()
                        p_text_lower = p_text.lower()
                        for qn in target_q_nums:
                            patterns = [
                                rf'\b{qn}\s*[\.\:\)]',
                                rf'Q(?:uestion)?\s*[\.\:\-]?\s*{qn}\b',
                                rf'\({qn}\)',
                                rf'Directions?\s*\([^\)]*{qn}[^\)]*\)',
                                rf'निर्देश\s*\([^\)]*{qn}[^\)]*\)',
                                rf'हल\s*[\.\:\-]?\s*{qn}\b',
                                rf'व्याख्या\s*[\.\:\-]?\s*{qn}\b'
                            ]
                            if any(re.search(pat, p_text, re.IGNORECASE) for pat in patterns):
                                matched_hi.add(p_idx)
                        if any(kw in p_text_lower for kw in hi_keywords):
                            for qn in target_q_nums:
                                if re.search(rf'\b{qn}\s*[\.\:\)]', p_text):
                                    matched_hi.add(p_idx)
                    except Exception:
                        pass
                if matched_hi:
                    expanded_hi = set(matched_hi)
                    for p in matched_hi:
                        if p + 1 < total_hi_pages:
                            expanded_hi.add(p + 1)
                    selected_hi_pages = sorted(list(expanded_hi))[:14]
                else:
                    selected_hi_pages = list(range(min(total_hi_pages, len(selected_en_pages))))

        en_pils = {} # canonical page_index -> PIL.Image
        page_lookup_en = {} # map (seq_idx, p_idx, aliases) -> (PIL.Image, p_idx)
        hi_pils = {} # canonical page_index -> PIL.Image
        page_lookup_hi = {}

        client = get_gemini_client(custom_key)
        parts = []

        # Render English pages (scale=2 -> 144 DPI crisp rendering)
        for seq_idx, p_idx in enumerate(selected_en_pages):
            page_pil = doc_en[p_idx].render(scale=2).to_pil()
            en_pils[p_idx] = page_pil
            buf = io.BytesIO()
            page_pil.save(buf, format="JPEG", quality=85)
            # Comprehensive lookup mapping: seq_idx, doc_pidx, 1-based, string formats
            page_lookup_en[seq_idx] = (page_pil, p_idx)
            page_lookup_en[str(seq_idx)] = (page_pil, p_idx)
            page_lookup_en[seq_idx + 1] = (page_pil, p_idx)
            page_lookup_en[str(seq_idx + 1)] = (page_pil, p_idx)
            page_lookup_en[p_idx] = (page_pil, p_idx)
            page_lookup_en[str(p_idx)] = (page_pil, p_idx)
            page_lookup_en[p_idx + 1] = (page_pil, p_idx)
            page_lookup_en[str(p_idx + 1)] = (page_pil, p_idx)
            parts.append(f"--- RENDERED PAGE #{seq_idx + 1} (pageIndex: {seq_idx}) [PDF Page {p_idx + 1}] ---")
            parts.append(types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg"))

        # Render Hindi pages if separate
        if doc_hi and selected_hi_pages:
            for seq_idx, p_idx in enumerate(selected_hi_pages):
                page_pil = doc_hi[p_idx].render(scale=2).to_pil()
                hi_pils[p_idx] = page_pil
                buf = io.BytesIO()
                page_pil.save(buf, format="JPEG", quality=85)
                page_lookup_hi[seq_idx] = (page_pil, p_idx)
                page_lookup_hi[str(seq_idx)] = (page_pil, p_idx)
                page_lookup_hi[seq_idx + 1] = (page_pil, p_idx)
                page_lookup_hi[str(seq_idx + 1)] = (page_pil, p_idx)
                page_lookup_hi[p_idx] = (page_pil, p_idx)
                page_lookup_hi[str(p_idx)] = (page_pil, p_idx)
                page_lookup_hi[p_idx + 1] = (page_pil, p_idx)
                page_lookup_hi[str(p_idx + 1)] = (page_pil, p_idx)
                parts.append(f"--- HINDI RENDERED PAGE #{seq_idx + 1} (Hindi pageIndex: {seq_idx}) [PDF Page {p_idx + 1}] ---")
                parts.append(types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg"))

        range_desc = f"{target_q_nums[0]} to {target_q_nums[-1]}" if len(target_q_nums) > 1 else str(target_q_nums[0])

        prompt = f"""
You are an expert OCR, document analyzer, and question extractor for Indian Banking Competitive Examinations (SBI PO/Clerk, IBPS PO/Clerk, RRB PO/Clerk, RBI Assistant).

You are given rendered pages of an exam question PDF.

TARGET QUESTION RANGE: Questions {range_desc} (extract ONLY questions within this range: {target_q_nums}).
"""
        prompt += """
BILINGUAL EXTRACTION & TRANSLATION RULES:
1. Examine if Hindi question text, options, and explanations are already provided in the pages (either directly below the English text, side-by-side, or in the Hindi PDF pages).
   - If Hindi IS present in the document: Extract both English and Hindi text faithfully and match them question by question.
   - If Hindi is NOT present in the document: You MUST TRANSLATE each question statement, all multiple-choice options, and the step-by-step explanation into natural, professional Hindi suitable for Indian banking competitive exams!
2. MANDATORY NUMERAL RULE FOR HINDI (CRITICAL - DO NOT VIOLATE):
   - In Indian banking competitive exams, ALL numbers, digits, amounts, percentages, ratios, fractions, years, currency symbols (₹), and variables in Hindi MUST BE WRITTEN IN STANDARD ENGLISH / ARABIC DIGITS (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, e.g. 1200, 45%, 3:5, ₹500, 2024)!
   - NEVER USE DEVANAGARI NUMERALS (०, १, २, ३, ४, ५, ६, ७, ८, ९) under any circumstances!

CRITICAL RULE: DITTO TYPOGRAPHY, INDENTATION, BOLDNESS & ITALICS (PRESERVE EXACT STYLING):
- Maintain EXACT formatting, boldness, italics, and line indentation as shown in the source document!
- If words or labels are bold in the source (e.g. statement labels 'I.', 'II.', 'III.', variable names, names of persons, conditions, column headers), use Markdown bold `**word**`.
- If words are italicized, use `*word*`.
- Preserve indentation, multiple line breaks, and paragraph structures faithfully.
- For syllogisms, puzzle statements, coded inequalities, data sufficiency, and multiple Roman numeral statements:
  Put each statement or conclusion on its own indented line, preserving bold labels like:
  **Statements:**
    I. Some cats are dogs.
    II. No dog is a bird.
  **Conclusions:**
    I. Some cats are not birds.
    II. All dogs can be cats.
- Ensure that the generated question text and solution text look DITTO identical in styling, boldness, and indentation to the original document.

CRITICAL RULE: STRICTLY STRIP AND EXCLUDE QUESTION NUMBERS:
- Questions in PDFs usually start with printed numbers, e.g. "{target_q_nums[0]}.", "Q.{target_q_nums[0]}:", "Question {target_q_nums[0]}:".
- You MUST STRIP AND NEVER OUTPUT THESE QUESTION NUMBERS in `questionText` or `questionTextHi`! The question statement MUST start directly with the actual sentence.
- In directions or passages (e.g. "Directions (1-5):"), remove the number range so it becomes "Directions:".

CRITICAL RULE: DIAGRAM, TABLE & CHART AUTO-DETECTION AND BOUNDING BOX COORDINATES:

- Banking exam questions frequently contain Data Interpretation (DI) tables, bar charts, pie charts, line graphs, Venn diagrams, seating arrangement diagrams, or floor puzzles.
- Check carefully if any question or common direction passage contains a chart, table, or visual figure.
- If YES:
  * DO NOT transcribe or convert table cells, data rows, or diagram contents into text or markdown tables inside `questionText` or `questionTextHi`!
  * In the question JSON object, you MUST provide the `"diagrams"` array so our system can automatically screenshot and crop ONLY that diagram:
    "diagrams": [
      {
        "tag": "[img1]",
        "type": "question",
        "source": "english",
        "pageIndex": 0,
        "box2d": [ymin, xmin, ymax, xmax]
      }
    ]
    - box2d: [ymin, xmin, ymax, xmax] are normalized coordinates on a 0 to 1000 scale enclosing the chart / table / diagram.
    - pageIndex: integer matching the 0-based Page Index shown in the image header (e.g. 0, 1, 2...).
  * If the document has a separate Hindi version of the diagram/chart, provide `"diagramsHi"` with the corresponding pageIndex and box2d. If no separate Hindi diagram exists, set `"diagramsHi": []`.
- If NO diagram/chart is present for that question: set `"diagrams": []` and `"diagramsHi": []`.

CRITICAL RULE: EXACT INLINE DIAGRAM / TABLE POSITIONING ([img1] TAG) - DO NOT PUT AT TOP OR BOTTOM:
- When a chart, graph, or table is placed between introductory notes/directions and the specific question problem statement (as in DI sets or puzzle sets):
  You MUST place the tag `[img1]` at that EXACT intermediate position in the text!
  Layout must look like:
  Study the following information carefully and answer the questions given below:
  The given pie chart shows the percentage distribution...
  Note:
  I). The number of people who traveled by metro train P is 70 more...

  [img1]

  If the ticket price per female on all metro trains is 50% that of per male...

- NEVER place `[img1]` at the top before the directions/passage!
- NEVER place `[img1]` at the bottom after the question!
- Place `[img1]` on its own line EXACTLY where the visual graphic appears in the source PDF layout.
- For set-based questions (e.g. Q1-5 sharing a DI chart), repeat the common directions + notes, place `[img1]` right after them, and then add the specific question sentence for EACH question in the set (both `questionText` and `questionTextHi`).

CRITICAL RULE: ZERO QUESTION TEXT IN DIAGRAM CROPS (PURE VISUAL GRAPHIC ONLY):
1. `box2d: [ymin, xmin, ymax, xmax]` MUST ENCLOSE ONLY THE GRAPHICAL CHART, TABLE, OR DIAGRAM ITSELF!
2. ABSOLUTELY FORBIDDEN IN `box2d`:
   - NEVER include question sentences, passage directions, or paragraphs (e.g. 'Study the following information...', 'The given line graph shows...', 'Directions (1-5):').
   - NEVER include introductory notes or roman numerals (e.g. 'Note:', 'I). The number of people who traveled...').
   - NEVER include specific question sentences (e.g. 'If the ticket price per female...').
   - NEVER include multiple-choice options (e.g. 'a. Rs. 6', 'b. Rs. 12').
   All of these textual sentences belong 100% inside `questionText` as text, NEVER inside the cropped image!
3. WHAT `box2d` MUST INCLUDE:
   - For a pie chart: The pie circle, percentage numbers inside slices (16%, 20%, 24%, 28%, 12%), and the legend (P, Q, R, S, T). If there is an enclosing rectangle box drawn around the pie chart and legend, snap `box2d` exactly ON that outer rectangle border!
   - For a bar chart / line graph: The vertical y-axis and its number labels (0, 20, 40, 60...), the bars or lines/points, the horizontal x-axis and category labels (A, B, C, D, E or months/years), and the legend.
   - For a table: The outer rectangular border enclosing table headers and rows/columns.
4. Coordinates must be normalized integers [ymin, xmin, ymax, xmax] on a 0 to 1000 scale.
5. If you include surrounding question sentences or passage notes inside `box2d`, it is a critical failure. Be extremely precise.

CRITICAL RULE: MANDATORY OFFICIAL SOLUTION EXTRACTION & FALLBACK SOLVING:
- Search the provided pages thoroughly for the solution/explanation corresponding to each question number ({range_desc}).
  Solutions in banking exam PDFs are typically located:
  a) Directly below each question or between questions on the same page or next page (e.g. marked as 'Answer: ...', 'Ans: ...', 'Explanation: ...', 'Sol: ...' or '1. Questions' / 'In city A,...').
  b) In an 'Answers & Solutions', 'Answer Key with Detailed Solutions', or 'Hints & Explanations' section later in the document.
- Match each solution to its question number ({target_q_nums}) and extract the EXACT step-by-step mathematical calculation, formula, table, and derivation directly from the PDF.
- CRITICAL REQUIREMENT: UNDER NO CIRCUMSTANCES should you output 'Solution not provided in the document' or leave `explanation` empty!
  If an explicit pre-printed solution is not present on the provided pages, YOU MUST SOLVE THE QUESTION COMPLETELY YOURSELF from first principles, writing out the full, rigorous step-by-step mathematical explanation, formulas, and calculations using LaTeX! Every question MUST have a complete, clear, helpful explanation.

CRITICAL RULE: AUTO-CROP SOLUTION DIAGRAMS, PUZZLE LAYOUTS & TABLES (DO NOT WRITE MANUAL TABLES):
- If the solution section in the PDF contains a table, puzzle matrix, seating arrangement diagram, or chart (e.g. calculated totals for cities/entities like a Cities × Insurance table):
  * DO NOT MANUALLY CREATE A TABLE OR TRANSCRIBE TABLE ROWS/COLUMNS INTO TEXT OR MARKDOWN!
  * You MUST provide the bounding box of that table/diagram in the `"diagrams"` array with `"type": "explanation"`, `"tag": "[img1]"` (or `[img2]`), and place the tag `[img1]` right inside the `explanation` (and `explanationHi`)!
  * In `explanation` (and `explanationHi`), insert `[img1]` at the EXACT position where the table appears in the solution — for example: after the sentence "Similarly, we can calculate other values." and BEFORE the next calculation steps or final answer.
  * Snap the bounding box snugly on the outer border lines of the table without including surrounding text (like "Similarly, we can calculate..." above or "Answer: D" below).
  * MANDATORY: snap `box2d` on the exact outer table border rectangle in the PDF — do NOT include the "Similarly..." text line above or "Answer: D" line below.
  * Our system will automatically screenshot and crop the exact table/figure directly from the PDF.
  * IMPORTANT: The `pageIndex` for solution diagrams must match the actual page where the solution table appears (which could be a DIFFERENT page from the questions). Always verify the page index shown in the image header above the solution.

CRITICAL SET-BASED (DI / RC / PUZZLE / SEATING ARRANGEMENT) RULE:
- These questions share a common passage, directions, or context (e.g. 'Directions: Study the following information carefully...').
- You MUST repeat and prepend this common passage/directions to the BEGINNING of EACH question's `questionText` (and `questionTextHi` in Hindi) so every single question is completely self-contained when answered individually!

MANDATORY RULES FOR MATHEMATICAL EQUATIONS AND SYMBOLS (CRITICAL):
1. ALL mathematical formulas, fractions, powers, roots, equations, percentages in calculations, ratios, and algebraic expressions MUST be formatted in LaTeX notation using $...$ for inline math and $$...$$ for block math!
2. When writing multi-step solutions or long derivations, break each calculation step onto its own line (using line breaks \n or separate steps) rather than writing excessively long single-line equations. This ensures clean wrapping on mobile screens.
3. Extract all options (usually 4 or 5 options: A, B, C, D, E). Format math inside options using LaTeX as well!
4. Identify the correct answer:
   - Determine `correctIndex` as a 0-based integer (0 for A, 1 for B, 2 for C, 3 for D, 4 for E).
   - If the answer key is visible, use it. If not, solve the question accurately.
5. Set `difficulty` to 'Easy', 'Medium', or 'Hard' based on banking exam standards.

Output MUST be a valid, parseable JSON array of question objects matching this schema:
[
  {
    "questionText": "Question statement in English with LaTeX $...$, Markdown **bold**, and optional [img1] tag",
    "questionTextHi": "Question statement in Hindi with English digits (0-9), LaTeX $...$, Markdown **bold**, and optional [img1] tag",
    "options": ["Option A with $...$", "Option B with $...$", "Option C with $...$", "Option D with $...$"],
    "optionsHi": ["Option A in Hindi", "Option B in Hindi", "Option C in Hindi", "Option D in Hindi"],
    "correctIndex": 0,
    "explanation": "Step-by-step explanation in English with LaTeX $...$ and optional [img1] tag",
    "explanationHi": "Step-by-step explanation in Hindi with English digits (0-9), LaTeX $...$ and optional [img1] tag",
    "difficulty": "Medium",
    "diagrams": [
      {
        "tag": "[img1]",
        "type": "question",
        "source": "english",
        "pageIndex": 0,
        "box2d": [150, 40, 520, 960]
      },
      {
        "tag": "[img1]",
        "type": "explanation",
        "source": "english",
        "pageIndex": 2,
        "box2d": [320, 60, 680, 940]
      }
    ],
    "diagramsHi": []
  }
]

DIAGRAM FIELD USAGE RULES:
- If the question or directions has an actual visual chart, graph, or table on the rendered pages: include an object with "type": "question", "tag": "[img1]", "pageIndex": <0-based pageIndex where chart appears>, and tight "box2d": [<ymin>, <xmin>, <ymax>, <xmax>].
  CRITICAL: box2d MUST tightly enclose ONLY the chart/table and legend/axis numbers. NEVER include passage sentences or question statements!
- If the solution has an actual visual table, puzzle matrix, or figure on the rendered pages: include an object with "type": "explanation", "tag": "[img1]", "pageIndex": <pageIndex where the solution table actually appears>, and tight "box2d": [<ymin>, <xmin>, <ymax>, <xmax>].
  CRITICAL: You MUST also place "[img1]" inside `explanation` (and `explanationHi`) where the table belongs!
- If a question or solution has NO visual chart or table: "diagrams" MUST be an empty array: []!
- NEVER copy or invent dummy coordinates or page indices!

MANDATORY COMPLETION REQUIREMENT (CRITICAL):
- You MUST extract and output ALL {len(target_q_nums)} questions in the requested range: {target_q_nums}.
- Do NOT stop early. Do NOT output only 3 or 4 questions.
- The returned JSON array MUST contain exactly {len(target_q_nums)} question objects, one for each question in {target_q_nums}.
"""
        if no_diagrams:
            prompt += f"""
CRITICAL TEXT-ONLY PASSAGE / READING COMPREHENSION / CASELET (NO DIAGRAM CROPPING):
- This question range ({question_range_str}) is a purely TEXT-BASED paragraph/passage set (e.g. Reading Comprehension, Cloze Test, Paragraph Completion, Text Caselet).
- There are NO visual charts, graphs, figures, or diagrams to crop!
- Strictly DO NOT output any diagrams bounding boxes. Set `"diagrams": []` and `"diagramsHi": []`.
- DO NOT insert any `[img1]` or `[img2]` tags in the text!
- You MUST repeat and prepend the COMPLETE common reading passage, story, or directions paragraph to the BEGINNING of EACH question's `questionText` (and in Hindi to `questionTextHi`) so every question is 100% self-contained with full context!
"""
        if instructions:
            prompt += f"\n\nADDITIONAL USER INSTRUCTIONS:\n{instructions}"

        contents = parts + [prompt]

        candidate_models = [
            "gemini-3-flash-preview",
            "gemini-3.1-flash-lite-preview",
            "gemini-2.5-flash",
            "gemini-flash-latest",
            "gemini-3.1-pro-preview",
            "gemini-pro-latest"
        ]

        gen_config = None
        if types:
            try:
                gen_config = types.GenerateContentConfig(
                    response_mime_type="application/json",
                    max_output_tokens=32768,
                    temperature=0.1
                )
            except Exception as e:
                print("Warning creating GenerateContentConfig for PDF:", e)

        questions = None
        last_error = None

        for model_name in candidate_models:
            for attempt in range(2):
                try:
                    print(f"Calling Gemini Vision for PDF extraction: {model_name} (attempt {attempt + 1})...")
                    if gen_config:
                        response = client.models.generate_content(
                            model=model_name,
                            contents=contents,
                            config=gen_config
                        )
                    else:
                        response = client.models.generate_content(
                            model=model_name,
                            contents=contents
                        )
                    if response and response.text:
                        raw_text = response.text.strip()
                        try:
                            candidate_q = safe_json_loads(raw_text)
                            if candidate_q and (isinstance(candidate_q, list) or isinstance(candidate_q, dict)):
                                questions = candidate_q
                                print(f"Success with {model_name}!")
                                break
                        except Exception as parse_err:
                            print(f"Model {model_name} attempt {attempt + 1} produced unparseable JSON: {parse_err}")
                except Exception as err:
                    last_error = err
                    err_str = str(err)
                    print(f"Model {model_name} attempt {attempt + 1} failed: {err_str[:120]}")
                    if "404" in err_str or "NOT_FOUND" in err_str:
                        # Model not available in this tier/version, break immediately to try next model
                        break
                    elif "503" in err_str or "UNAVAILABLE" in err_str or "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        time.sleep(1.5 * (attempt + 1))
                        continue
                    else:
                        break
            if questions:
                break

        if not questions:
            msg = str(last_error) if last_error else f"Could not parse questions from the PDF for range ({range_desc})."
            if "503" in msg or "UNAVAILABLE" in msg:
                clean_msg = "Gemini service is temporarily experiencing high traffic (503). Retries were attempted. Please wait a few seconds and click Extract again."
            elif "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                clean_msg = "Gemini API rate limit or quota exceeded (429). Please wait a moment or check your Gemini API key in Settings."
            else:
                clean_msg = msg
            return jsonify({"status": "error", "message": clean_msg}), 503 if "503" in msg else 400

        if not isinstance(questions, list):
            questions = [questions]

        # --- Defensive sanitization ---
        # json_repair or Gemini may return nested lists, wrap a single dict, etc.
        # Flatten any nested lists and discard non-dict items.
        def _flatten_questions(raw):
            result = []
            for item in raw:
                if isinstance(item, dict):
                    result.append(item)
                elif isinstance(item, list):
                    for sub in item:
                        if isinstance(sub, dict):
                            result.append(sub)
            return result

        questions = _flatten_questions(questions)
        if not questions:
            return jsonify({
                "status": "error",
                "message": f"No valid question objects found for range ({range_desc}). Please try again."
            }), 400

        # In-memory deduplication caches for this extraction batch
        upload_cache = {}  # sha256_hash -> cdn_url
        spatial_cache = [] # list of {"page": p_idx, "source": str, "type": str, "box": tuple, "url": str}

        def crop_and_upload_diagram(pil_img, box, p_idx, source_lang, d_type, d_tag, q_num):
            if not pil_img or not box:
                return None
            w, h = pil_img.size
            coords = parse_box_coords(box, w, h)
            if not coords:
                return None
            left, top, right, bottom = coords

            # Filter out tiny or degenerate boxes
            if (right - left) < 25 or (bottom - top) < 25:
                return None

            # 1. Search for closed framing rectangles (charts / tables) on this page
            rect_entries = find_diagram_rectangles(pil_img)
            best_rect = None
            best_overlap = 0.0
            cand_area = (right - left) * (bottom - top)
            for entry in rect_entries:
                rl, rt, rr, rb = entry['box']
                inter_l = max(left, rl)
                inter_t = max(top, rt)
                inter_r = min(right, rr)
                inter_b = min(bottom, rb)
                if inter_r > inter_l and inter_b > inter_t:
                    inter_area = (inter_r - inter_l) * (inter_b - inter_t)
                    rect_area = (rr - rl) * (rb - rt)
                    overlap = inter_area / min(cand_area, rect_area)
                    if overlap > best_overlap:
                        best_overlap = overlap
                        best_rect = entry['box']

            if best_rect and best_overlap >= 0.30:
                # Snap snugly to the exact closed diagram rectangle!
                left, top, right, bottom = best_rect
            else:
                # For diagrams without closed outer rectangle, refine borders safely
                snapped = refine_border_crop(pil_img, left, top, right, bottom)
                if snapped:
                    left, top, right, bottom = snapped

            # Clamp coordinates safely within image bounds
            left = max(0, min(w - 1, int(left)))
            right = max(left + 20, min(w, int(right)))
            top = max(0, min(h - 1, int(top)))
            bottom = max(top + 20, min(h, int(bottom)))

            cropped = pil_img.crop((left, top, right, bottom))
            cropped = remove_watermark_from_chart(cropped)

            buf = io.BytesIO()
            cropped.save(buf, format="PNG")
            cropped_bytes = buf.getvalue()

            img_hash = hashlib.sha256(cropped_bytes).hexdigest()

            # 1. Exact content match in cache (same chart cropped across questions)
            if img_hash in upload_cache:
                return upload_cache[img_hash]

            # 2. Spatial proximity match on same rendered page (IoU >= 0.70)
            for entry in spatial_cache:
                if entry["page"] == p_idx and entry.get("source") == source_lang and entry.get("type") == d_type:
                    el, et, er, eb = entry["box"]
                    inter_l = max(left, el)
                    inter_t = max(top, et)
                    inter_r = min(right, er)
                    inter_b = min(bottom, eb)
                    if inter_r > inter_l and inter_b > inter_t:
                        inter_area = (inter_r - inter_l) * (inter_b - inter_t)
                        area1 = (right - left) * (bottom - top)
                        area2 = (er - el) * (eb - et)
                        union_area = area1 + area2 - inter_area
                        if union_area > 0 and (inter_area / union_area) >= 0.70:
                            cached_url = entry["url"]
                            upload_cache[img_hash] = cached_url
                            return cached_url

            # 3. If not cached, upload once to Google Drive
            clean_tag = re.sub(r'[^a-zA-Z0-9]+', '', d_tag)
            label_prefix = f"PDF_Q{q_num}_{clean_tag}" if source_lang == "english" else f"PDF_HI_Q{q_num}_{clean_tag}"
            upload_res, err = upload_bytes_to_drive(
                file_bytes=cropped_bytes,
                exam_id=exam_id,
                image_type=d_type,
                label=label_prefix,
                ext="png",
                mime_type="image/png"
            )
            if upload_res and upload_res.get("directUrl"):
                cdn_url = upload_res["directUrl"]
            else:
                cdn_url = f"data:image/png;base64,{base64.b64encode(cropped_bytes).decode('utf-8')}"

            upload_cache[img_hash] = cdn_url
            spatial_cache.append({
                "page": p_idx,
                "source": source_lang,
                "type": d_type,
                "box": (left, top, right, bottom),
                "url": cdn_url
            })
            return cdn_url

        # Auto-crop diagrams and upload to Google Drive (with multi-key support & auto-fallback)
        if not no_diagrams:
            for q_idx, q in enumerate(questions):
                if not isinstance(q, dict):
                    continue  # skip any non-dict items that slipped through
                q_num = target_q_nums[q_idx] if q_idx < len(target_q_nums) else (q_idx + 1)

                # Helper to extract box from various schema formats
                def extract_box(d):
                    if isinstance(d, (list, tuple)) and len(d) == 4:
                        return d
                    if not isinstance(d, dict):
                        return None
                    for k in ["box2d", "box_2d", "bounding_box", "boundingBox", "box", "bbox", "coordinates", "coords", "rect"]:
                        v = d.get(k)
                        if v and (isinstance(v, (list, tuple)) or isinstance(v, dict)):
                            return v
                    return None

                # Helper to extract page index
                def extract_p_idx(d):
                    if not isinstance(d, dict):
                        return None
                    for k in ["pageIndex", "page_index", "page", "pageNumber", "page_number", "page_num", "pageNum", "p_idx"]:
                        v = d.get(k)
                        if v is not None:
                            return v
                    return None

                # Gather English diagrams from all potential keys
                diagram_candidates = []
                for k in ["diagrams", "diagram"]:
                    v = q.get(k)
                    if isinstance(v, list):
                        for item in v:
                            diagram_candidates.append((item, "diagrams"))
                    elif isinstance(v, dict):
                        diagram_candidates.append((v, "diagrams"))

                sol_keys = [
                    "explanationDiagrams", "explanation_diagrams", "explanationDiagram",
                    "solution_diagrams", "solutionDiagrams", "solution_diagram", "solutionDiagram",
                    "answerDiagrams", "answer_diagrams", "answerDiagram", "solution_box", "solutionBox"
                ]
                for k in sol_keys:
                    v = q.get(k)
                    if isinstance(v, list):
                        for item in v:
                            diagram_candidates.append((item, "explanation"))
                    elif isinstance(v, dict):
                        diagram_candidates.append((v, "explanation"))

                q_keys = ["questionDiagrams", "question_diagrams", "questionDiagram"]
                for k in q_keys:
                    v = q.get(k)
                    if isinstance(v, list):
                        for item in v:
                            diagram_candidates.append((item, "question"))
                    elif isinstance(v, dict):
                        diagram_candidates.append((v, "question"))

                q_images = []
                sol_images = []

                for diag, origin in diagram_candidates:
                    box = extract_box(diag)
                    if not box:
                        continue
                    p_raw = extract_p_idx(diag)

                    pil_img, canon_pidx = resolve_page_from_lookup(
                        p_raw, page_lookup_en, en_pils, selected_en_pages
                    )
                    if not pil_img:
                        continue

                    # Determine whether this diagram is for question or explanation
                    is_exp = False
                    if origin == "explanation":
                        is_exp = True
                    elif origin == "question":
                        is_exp = False
                    elif isinstance(diag, dict):
                        raw_type = str(diag.get("type") or diag.get("target") or diag.get("for") or diag.get("section") or diag.get("role") or "").lower()
                        if any(x in raw_type for x in ["exp", "sol", "ans"]):
                            is_exp = True
                        elif any(x in raw_type for x in ["quest", "prob", "dir", "pass"]):
                            is_exp = False
                        else:
                            diag_tag = str(diag.get("tag") or "").strip().lower()
                            if diag_tag:
                                if diag_tag in (q.get("explanation") or "").lower() and diag_tag not in (q.get("questionText") or "").lower():
                                    is_exp = True
                                elif diag_tag in (q.get("questionText") or "").lower() and diag_tag not in (q.get("explanation") or "").lower():
                                    is_exp = False
                            if not is_exp and canon_pidx in matched_sol_pages:
                                is_exp = True

                    d_type = "explanation" if is_exp else "question"
                    d_tag = f"[img{len(sol_images)+1}]" if is_exp else f"[img{len(q_images)+1}]"
                    if isinstance(diag, dict) and diag.get("tag"):
                        d_tag = diag.get("tag")

                    cdn_url = crop_and_upload_diagram(
                        pil_img=pil_img,
                        box=box,
                        p_idx=canon_pidx,
                        source_lang="english",
                        d_type=d_type,
                        d_tag=d_tag,
                        q_num=q_num
                    )
                    if cdn_url:
                        if is_exp:
                            if cdn_url not in sol_images:
                                sol_images.append(cdn_url)
                        else:
                            if cdn_url not in q_images:
                                q_images.append(cdn_url)

                # Auto-fallback: if sol_images is empty, check if explanation mentions table or if solution page has a table
                if not sol_images:
                    cand_sol_pages = [p for p in selected_en_pages if (p in matched_sol_pages or (len(selected_en_pages) > 2 and p >= selected_en_pages[len(selected_en_pages)//2]))]
                    for sp_idx in cand_sol_pages:
                        sp_pil = en_pils.get(sp_idx)
                        if not sp_pil:
                            continue
                        rect_list = find_diagram_rectangles(sp_pil)
                        if rect_list:
                            best_table_rect = rect_list[0]['box']
                            cdn_url = crop_and_upload_diagram(
                                pil_img=sp_pil,
                                box=best_table_rect,
                                p_idx=sp_idx,
                                source_lang="english",
                                d_type="explanation",
                                d_tag="[img1]",
                                q_num=q_num
                            )
                            if cdn_url:
                                sol_images.append(cdn_url)
                                break

                if q_images:
                    q["questionImages"] = q_images
                    q["questionImageDriveLink"] = q_images[0]
                if sol_images:
                    q["explanationImages"] = sol_images
                    q["explanationImageDriveLink"] = sol_images[0]

                # Hindi diagrams
                diagram_candidates_hi = []
                for k in ["diagramsHi", "diagramHi"]:
                    v = q.get(k)
                    if isinstance(v, list):
                        for item in v:
                            diagram_candidates_hi.append((item, "diagrams"))
                    elif isinstance(v, dict):
                        diagram_candidates_hi.append((v, "diagrams"))

                for k in ["explanationDiagramsHi", "solutionDiagramsHi", "solution_diagrams_hi", "answerDiagramsHi"]:
                    v = q.get(k)
                    if isinstance(v, list):
                        for item in v:
                            diagram_candidates_hi.append((item, "explanation"))
                    elif isinstance(v, dict):
                        diagram_candidates_hi.append((v, "explanation"))

                for k in ["questionDiagramsHi", "question_diagrams_hi"]:
                    v = q.get(k)
                    if isinstance(v, list):
                        for item in v:
                            diagram_candidates_hi.append((item, "question"))
                    elif isinstance(v, dict):
                        diagram_candidates_hi.append((v, "question"))

                q_images_hi = []
                sol_images_hi = []
                target_lookup = page_lookup_hi if page_lookup_hi else page_lookup_en
                target_pils = hi_pils if hi_pils else en_pils
                target_pages = selected_hi_pages if hi_pils else selected_en_pages

                for diag, origin in diagram_candidates_hi:
                    box = extract_box(diag)
                    if not box:
                        continue
                    p_raw = extract_p_idx(diag)

                    pil_img, canon_pidx = resolve_page_from_lookup(
                        p_raw, target_lookup, target_pils, target_pages
                    )
                    if not pil_img:
                        continue

                    is_exp = False
                    if origin == "explanation":
                        is_exp = True
                    elif origin == "question":
                        is_exp = False
                    elif isinstance(diag, dict):
                        raw_type = str(diag.get("type") or diag.get("target") or diag.get("for") or diag.get("section") or diag.get("role") or "").lower()
                        if any(x in raw_type for x in ["exp", "sol", "ans"]):
                            is_exp = True
                        elif any(x in raw_type for x in ["quest", "prob", "dir", "pass"]):
                            is_exp = False
                        else:
                            diag_tag = str(diag.get("tag") or "").strip().lower()
                            if diag_tag:
                                if diag_tag in (q.get("explanationHi") or "").lower() and diag_tag not in (q.get("questionTextHi") or "").lower():
                                    is_exp = True
                                elif diag_tag in (q.get("questionTextHi") or "").lower() and diag_tag not in (q.get("explanationHi") or "").lower():
                                    is_exp = False

                    d_type = "explanation" if is_exp else "question"
                    d_tag = f"[img{len(sol_images_hi)+1}]" if is_exp else f"[img{len(q_images_hi)+1}]"
                    if isinstance(diag, dict) and diag.get("tag"):
                        d_tag = diag.get("tag")

                    cdn_url = crop_and_upload_diagram(
                        pil_img=pil_img,
                        box=box,
                        p_idx=canon_pidx,
                        source_lang="hindi" if hi_pils else "english",
                        d_type=d_type,
                        d_tag=d_tag,
                        q_num=q_num
                    )
                    if cdn_url:
                        if is_exp:
                            if cdn_url not in sol_images_hi:
                                sol_images_hi.append(cdn_url)
                        else:
                            if cdn_url not in q_images_hi:
                                q_images_hi.append(cdn_url)

                if q_images_hi:
                    q["questionImagesHi"] = q_images_hi
                elif q_images:
                    q["questionImagesHi"] = list(q_images)

                if sol_images_hi:
                    q["explanationImagesHi"] = sol_images_hi
                elif sol_images:
                    q["explanationImagesHi"] = list(sol_images)

        # Set-based propagation: share common passage chart and summary table across questions in each set
        if is_set_based:
            if no_diagrams:
                # Text-only passage propagation: ensure common passage/directions are prepended to all questions in set
                common_passage_en = None
                common_passage_hi = None
                for item in questions:
                    if not isinstance(item, dict):
                        continue
                    q_text = item.get("questionText", "").strip()
                    q_text_hi = item.get("questionTextHi", "").strip()
                    if ("directions" in q_text.lower() or "read the following" in q_text.lower() or "study the following" in q_text.lower()) and "\n\n" in q_text:
                        common_passage_en = q_text.split("\n\n", 1)[0].strip()
                    if ("निर्देश" in q_text_hi or "निम्नलिखित" in q_text_hi) and "\n\n" in q_text_hi:
                        common_passage_hi = q_text_hi.split("\n\n", 1)[0].strip()
                    if common_passage_en and common_passage_hi:
                        break

                if common_passage_en:
                    for item in questions:
                        if not isinstance(item, dict):
                            continue
                        q_text = item.get("questionText", "").strip()
                        if common_passage_en not in q_text:
                            item["questionText"] = common_passage_en + "\n\n" + q_text

                if common_passage_hi:
                    for item in questions:
                        if not isinstance(item, dict):
                            continue
                        q_text_hi = item.get("questionTextHi", "").strip()
                        if common_passage_hi not in q_text_hi:
                            item["questionTextHi"] = common_passage_hi + "\n\n" + q_text_hi

                # Ensure zero diagrams
                for item in questions:
                    if isinstance(item, dict):
                        item["questionImages"] = []
                        item["questionImagesHi"] = []
                        item["explanationImages"] = []
                        item["explanationImagesHi"] = []
                        item["questionImageDriveLink"] = None
                        item["explanationImageDriveLink"] = None
                        item["questionText"] = re.sub(r'\[img\d+\]\s*', '', item.get("questionText", "")).strip()
                        item["questionTextHi"] = re.sub(r'\[img\d+\]\s*', '', item.get("questionTextHi", "")).strip()
                        item["explanation"] = re.sub(r'\[img\d+\]\s*', '', item.get("explanation", "")).strip()
                        item["explanationHi"] = re.sub(r'\[img\d+\]\s*', '', item.get("explanationHi", "")).strip()
            else:
                common_q_img = None

                common_q_img_hi = None
                common_passage_prefix = None
                common_passage_prefix_hi = None
                common_sol_img = None
                common_sol_img_hi = None

                # Pass 1: Find common diagrams anywhere in the set
                for item in questions:
                    if not isinstance(item, dict):
                        continue
                    if not common_q_img and item.get("questionImages"):
                        common_q_img = item["questionImages"]
                        common_q_img_hi = item.get("questionImagesHi") or common_q_img
                        q_text = item.get("questionText", "")
                        if "[img1]" in q_text:
                            common_passage_prefix = q_text.split("[img1]", 1)[0].strip()
                        q_text_hi = item.get("questionTextHi", "")
                        if "[img1]" in q_text_hi:
                            common_passage_prefix_hi = q_text_hi.split("[img1]", 1)[0].strip()

                    if not common_sol_img and item.get("explanationImages"):
                        common_sol_img = item["explanationImages"]
                        common_sol_img_hi = item.get("explanationImagesHi") or common_sol_img

                # Pass 2: Apply common diagrams to all questions in the set
                for item in questions:
                    if not isinstance(item, dict):
                        continue
                    if not item.get("questionImages") and common_q_img:
                        item["questionImages"] = list(common_q_img)
                        item["questionImageDriveLink"] = common_q_img[0]
                        if common_q_img_hi:
                            item["questionImagesHi"] = list(common_q_img_hi)

                        if item.get("questionText") and "[img1]" not in item["questionText"]:
                            item["questionText"] = insert_diagram_tag_intelligently(
                                item["questionText"],
                                "[img1]",
                                is_explanation=False,
                                reference_prefix=common_passage_prefix
                            )
                        if item.get("questionTextHi") and "[img1]" not in item["questionTextHi"]:
                            item["questionTextHi"] = insert_diagram_tag_intelligently(
                                item["questionTextHi"],
                                "[img1]",
                                is_explanation=False,
                                reference_prefix=common_passage_prefix_hi
                            )

                    if not item.get("explanationImages") and common_sol_img:
                        item["explanationImages"] = list(common_sol_img)
                        item["explanationImageDriveLink"] = common_sol_img[0]
                        if common_sol_img_hi:
                            item["explanationImagesHi"] = list(common_sol_img_hi)

                        if item.get("explanation") and "[img1]" not in item["explanation"]:
                            item["explanation"] = insert_diagram_tag_intelligently(
                                item["explanation"],
                                "[img1]",
                                is_explanation=True
                            )
                        if item.get("explanationHi") and "[img1]" not in item["explanationHi"]:
                            item["explanationHi"] = insert_diagram_tag_intelligently(
                                item["explanationHi"],
                                "[img1]",
                                is_explanation=True
                            )

            # Post-process: strip numbers & normalize Devanagari numerals, normalize newlines, synchronize diagram tags
            for q in questions:
                if not isinstance(q, dict):
                    continue
                if q.get("questionText"):
                    q["questionText"] = normalize_text_newlines(strip_question_numbers(q["questionText"]))
                if q.get("questionTextHi"):
                    q["questionTextHi"] = normalize_text_newlines(strip_question_numbers(normalize_devanagari_numerals(q["questionTextHi"])))
                if q.get("options") and isinstance(q["options"], list):
                    q["options"] = [normalize_text_newlines(str(opt)) for opt in q["options"]]
                if q.get("optionsHi") and isinstance(q["optionsHi"], list):
                    q["optionsHi"] = [normalize_text_newlines(normalize_devanagari_numerals(str(opt))) for opt in q["optionsHi"]]
                if q.get("explanation"):
                    q["explanation"] = normalize_text_newlines(q["explanation"])
                if q.get("explanationHi"):
                    q["explanationHi"] = normalize_text_newlines(normalize_devanagari_numerals(q["explanationHi"]))

                # Synchronize tags with images
                q_img_count = len(q.get("questionImages") or [])
                if q_img_count > 0:
                    q["questionText"] = sync_diagram_tags_in_text(q.get("questionText", ""), q_img_count, is_explanation=False)
                    if q.get("questionTextHi"):
                        q_hi_count = len(q.get("questionImagesHi") or []) or q_img_count
                        q["questionTextHi"] = sync_diagram_tags_in_text(q.get("questionTextHi", ""), q_hi_count, is_explanation=False)
                else:
                    # Remove orphan tags
                    if q.get("questionText"):
                        q["questionText"] = re.sub(r'\[img\d+\]\s*', '', q["questionText"]).strip()
                    if q.get("questionTextHi"):
                        q["questionTextHi"] = re.sub(r'\[img\d+\]\s*', '', q["questionTextHi"]).strip()

                exp_img_count = len(q.get("explanationImages") or [])
                if exp_img_count > 0:
                    q["explanation"] = sync_diagram_tags_in_text(q.get("explanation", ""), exp_img_count, is_explanation=True)
                    if q.get("explanationHi"):
                        exp_hi_count = len(q.get("explanationImagesHi") or []) or exp_img_count
                        q["explanationHi"] = sync_diagram_tags_in_text(q.get("explanationHi", ""), exp_hi_count, is_explanation=True)
                else:
                    # Remove orphan tags
                    if q.get("explanation"):
                        q["explanation"] = re.sub(r'\[img\d+\]\s*', '', q["explanation"]).strip()
                    if q.get("explanationHi"):
                        q["explanationHi"] = re.sub(r'\[img\d+\]\s*', '', q["explanationHi"]).strip()

                q.pop("diagrams", None)
                q.pop("diagramsHi", None)
                q.pop("diagram", None)
                q.pop("diagramHi", None)
                q.pop("questionDiagrams", None)
                q.pop("question_diagrams", None)
                q.pop("questionDiagram", None)
                q.pop("explanationDiagrams", None)
                q.pop("explanation_diagrams", None)
                q.pop("explanationDiagram", None)
                q.pop("solution_diagrams", None)
                q.pop("solutionDiagrams", None)
                q.pop("solution_diagram", None)
                q.pop("solutionDiagram", None)
                q.pop("answerDiagrams", None)
                q.pop("answer_diagrams", None)
                q.pop("solution_box", None)
                q.pop("solutionBox", None)

        # Auto-repair any LaTeX artifacts
        for item in questions:
            if isinstance(item, dict):
                item['questionText'] = auto_repair_latex(item.get('questionText', ''))
                item['questionTextHi'] = auto_repair_latex(item.get('questionTextHi', ''))
                item['explanation'] = auto_repair_latex(item.get('explanation', ''))
                item['explanationHi'] = auto_repair_latex(item.get('explanationHi', ''))

        return jsonify({
            "status": "ok",
            "count": len(questions),
            "questions": questions,
            "message": f"Successfully extracted {len(questions)} question(s) with diagrams and bilingual content!"
        })

    except Exception as e:
        print("Extract PDF error:", e)
        return jsonify({"status": "error", "message": str(e)}), 500

# Cache for decrypted HTML tests: md5_hash -> (en_list, hi_list, metadata)
_HTML_DECRYPT_CACHE = {}

def split_bilingual_html(raw_html):
    """
    Separates bilingual HTML content (e.g. English passage / question / solution followed by Hindi)
    into (english_html, hindi_html).
    """
    if not raw_html:
        return "", ""
    t = str(raw_html).strip()

    # 1. Separated by <hr> (standard Mickey format)
    if "<hr" in t.lower():
        parts = re.split(r'<hr[^>]*>', t, maxsplit=1, flags=re.IGNORECASE)
        en_part = parts[0].strip()
        hi_part = parts[1].strip() if len(parts) > 1 else ""
        return en_part, hi_part

    # 2. Check for Hindi marker or Devnagari characters [\u0900-\u097F]
    has_devanagari = bool(re.search(r'[\u0900-\u097F]', t))
    if not has_devanagari:
        return t, ""

    # Split by <br> or <p> tags
    br_parts = re.split(r'<br\s*/?>', t, flags=re.IGNORECASE)
    en_parts = []
    hi_parts = []
    found_hi = False

    for p in br_parts:
        p_clean = p.strip()
        if not p_clean:
            continue
        if re.search(r'[\u0900-\u097F]', p_clean):
            found_hi = True
        if found_hi:
            hi_parts.append(p_clean)
        else:
            en_parts.append(p_clean)

    if en_parts and hi_parts:
        return '<br>'.join(en_parts), '<br>'.join(hi_parts)

    return t, t

def split_bilingual_option(opt_html):
    """
    Separates a single option string containing both English and Hindi into (english, hindi).
    """
    if not opt_html:
        return "", ""
    t = str(opt_html).strip()

    # 1. Check for <span style='color:#0b4085...'> (Mickey style)
    span_match = re.search(r'<span[^>]*style=[^>]*color:\s*#0b4085[^>]*>(.*?)</span>', t, re.DOTALL | re.IGNORECASE)
    if span_match:
        hi_part = span_match.group(1).strip()
        en_part = t[:span_match.start()].strip()
        en_part = re.sub(r'<br\s*/?>\s*$', '', en_part, flags=re.IGNORECASE).strip()
        return en_part, hi_part

    # 2. Check for <br> separation
    if "<br" in t.lower():
        parts = re.split(r'<br\s*/?>', t, maxsplit=1, flags=re.IGNORECASE)
        en_part = parts[0].strip()
        hi_part = parts[1].strip() if len(parts) > 1 else ""
        hi_part = re.sub(r'^(?:&emsp;|&nbsp;|\s)+', '', hi_part)
        return en_part, hi_part

    return t, t

def universal_decrypt_html_test(html_content):
    """
    Universally decrypts any Mickey Mock Test HTML file:
    - Generation 1: const ENCRYPTED_PAYLOAD XOR cipher
    - Generation 2: v4.x obfuscated multi-meta tag with math byte-scramble
    - Generation 3: v5.x obfuscated span elements with string XOR cipher
    - Future generations: Universal Playwright sandbox evaluator

    Returns: (en_list, hi_list, metadata)
    """
    if not html_content or not isinstance(html_content, str):
        return [], [], {}

    # Decode base64 if sent as data URI or raw base64 string
    if html_content.startswith("data:") and ";base64," in html_content:
        try:
            html_content = base64.b64decode(html_content.split(";base64,", 1)[1]).decode("utf-8", errors="ignore")
        except Exception as b64_err:
            print("Base64 decode warning in universal_decrypt:", b64_err)
    elif len(html_content) > 100 and not ("<html" in html_content.lower() or "<script" in html_content.lower()):
        try:
            decoded = base64.b64decode(html_content).decode("utf-8", errors="ignore")
            if "<html" in decoded.lower() or "<script" in decoded.lower() or "const ENCRYPTED" in decoded:
                html_content = decoded
        except Exception:
            pass

    cache_key = hashlib.md5(html_content.encode("utf-8", errors="ignore")).hexdigest()
    if cache_key in _HTML_DECRYPT_CACHE:
        return _HTML_DECRYPT_CACHE[cache_key]

    # Engine 1: Gen 1 XOR Decryptor (Mickey_PureSoul222)
    payload_match = re.search(r'const\s+ENCRYPTED_PAYLOAD\s*=\s*["\']([^"\']+)["\']', html_content)
    if payload_match:
        key_match = re.search(r'const\s+(?:SECRET_KEY|KEY|CIPHER_KEY)\s*=\s*["\']([^"\']+)["\']', html_content)
        key_str = key_match.group(1) if key_match else "Mickey_PureSoul222"
        try:
            secret_key = key_str.encode("utf-8")
            raw_bytes = base64.b64decode(payload_match.group(1))
            decrypted_bytes = bytearray(len(raw_bytes))
            for i in range(len(raw_bytes)):
                decrypted_bytes[i] = raw_bytes[i] ^ secret_key[i % len(secret_key)]
            decrypted_str = decrypted_bytes.decode("utf-8", errors="ignore")
            test_data = json.loads(decrypted_str)
            en_list = test_data.get("en", []) if isinstance(test_data, dict) else []
            hi_list = test_data.get("hi", []) if isinstance(test_data, dict) else []
            if not en_list and isinstance(test_data, list):
                en_list = test_data
            elif not en_list and isinstance(test_data, dict) and "questions" in test_data:
                en_list = test_data["questions"]
            if en_list:
                result = (en_list, hi_list, {"format": "gen1", "key": key_str})
                _HTML_DECRYPT_CACHE[cache_key] = result
                return result
        except Exception as e:
            print("Gen 1 XOR decrypt error:", e)

    # Engine 2: Plain JSON variables
    json_match = re.search(r'(?:QUESTIONS_BY_LANGUAGE|questions_data|test_questions)\s*=\s*(\{.*?\}|\[.*?\]);', html_content, re.DOTALL)
    if json_match:
        try:
            test_data = json.loads(json_match.group(1))
            en_list = test_data.get("en", []) if isinstance(test_data, dict) else []
            hi_list = test_data.get("hi", []) if isinstance(test_data, dict) else []
            if not en_list and isinstance(test_data, list):
                en_list = test_data
            if en_list:
                result = (en_list, hi_list, {"format": "json_var"})
                _HTML_DECRYPT_CACHE[cache_key] = result
                return result
        except Exception:
            pass

    # Engine 3: Universal Headless Chromium Evaluator (Handles Gen 2 v4.x, Gen 3 v5.x, Gen 4 v8.x, and ALL future Mickey versions)
    if sync_playwright:
        try:
            # Dynamically extract answer formula and question keys via regex from the HTML test file
            ans_m = re.search(r'function\s+getActualAnswer\b.*?\{.*?\((?:[a-zA-Z0-9_]+\.)?([a-zA-Z0-9_]+)\s*\^\s*(\d+)\)\s*([+-])\s*(\d+)', html_content, re.DOTALL)
            pas_m = re.search(r'commonDiv\.innerHTML\s*=.*?q\.([a-zA-Z0-9_]+)', html_content)
            q_m = re.search(r'specificQDiv\.innerHTML\s*=.*?q\.([a-zA-Z0-9_]+)', html_content)
            opt_m = re.search(r'optionsArray\s*=\s*\(?q\.([a-zA-Z0-9_]+)', html_content)
            sol_m = re.search(r'solBox\.innerHTML\s*=.*?q\.([a-zA-Z0-9_]+)', html_content)

            ans_key = ans_m.group(1) if ans_m else None
            xor_val = int(ans_m.group(2)) if ans_m else 0
            ans_op = ans_m.group(3) if ans_m else '-'
            sub_val = int(ans_m.group(4)) if ans_m else 0

            pas_key = pas_m.group(1) if pas_m else None
            q_key = q_m.group(1) if q_m else None
            opt_key = opt_m.group(1) if opt_m else None
            sol_key = sol_m.group(1) if sol_m else None

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 800}
                )
                context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', { get: () => false });
                    window._bot_detected = false;
                    delete window.callPhantom;
                    delete window._phantom;
                    delete window.__nightmare;
                    delete window.domAutomation;

                    function isMickeyPayload(obj) {
                        if (!obj || typeof obj !== 'object') return false;
                        if (Array.isArray(obj.en) || Array.isArray(obj.questions)) return true;
                        for (let k of Object.keys(obj)) {
                            let val = obj[k];
                            if (Array.isArray(val) && val.length > 0) {
                                let first = val[0];
                                if (first && typeof first === 'object') {
                                    for (let ik of Object.keys(first)) {
                                        if (Array.isArray(first[ik]) && first[ik].length > 0) {
                                            return true;
                                        }
                                    }
                                }
                            }
                        }
                        return false;
                    }

                    function hookParse(targetObj) {
                        if (!targetObj || !targetObj.JSON || targetObj.JSON.__hooked) return;
                        const orig = targetObj.JSON.parse;
                        targetObj.JSON.parse = function(text, reviver) {
                            const res = orig.call(this, text, reviver);
                            try {
                                if (isMickeyPayload(res)) {
                                    try { window.__CAPTURED_PAYLOAD__ = res; } catch(e) {}
                                    try { window.top.__CAPTURED_PAYLOAD__ = res; } catch(e) {}
                                }
                            } catch(e) {}
                            return res;
                        };
                        targetObj.JSON.__hooked = true;
                    }
                    hookParse(window);

                    try {
                        const origDesc = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'contentWindow');
                        if (origDesc && origDesc.get) {
                            Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
                                get() {
                                    const win = origDesc.get.call(this);
                                    if (win) {
                                        try { hookParse(win); } catch(e) {}
                                    }
                                    return win;
                                }
                            });
                        }
                    } catch(e) {}

                    const origAppend = Element.prototype.appendChild;
                    Element.prototype.appendChild = function(child) {
                        const res = origAppend.call(this, child);
                        if (child && (child.tagName === 'IFRAME' || child.nodeName === 'IFRAME')) {
                            try { if (child.contentWindow) hookParse(child.contentWindow); } catch(e) {}
                        }
                        return res;
                    };
                """)
                page = context.new_page()
                page.set_content(html_content, wait_until="load")
                for x, y in [(50, 50), (150, 200), (300, 350)]:
                    page.mouse.move(x, y)
                page.wait_for_timeout(200)

                # Trigger proceed / start test button
                btn = page.locator("#kqwYjMfxP, #nLIFylBTw, #lHa6Fv7nc, button:has-text('Proceed'), .btn-next, .proceed-btn")
                if btn.count() > 0:
                    btn.first.click()
                    page.wait_for_timeout(500)

                # Fallback: trigger any documentElement start functions if payload not yet captured
                page.evaluate("""() => {
                    if (!window.__CAPTURED_PAYLOAD__ && !(window.top && window.top.__CAPTURED_PAYLOAD__)) {
                        for (let k of Object.keys(document.documentElement)) {
                            if (k.startsWith('_') && typeof document.documentElement[k] === 'function') {
                                try { document.documentElement[k](); } catch(e) {}
                            }
                        }
                    }
                }""")
                page.wait_for_timeout(400)

                raw_sections = page.evaluate("""(params) => {
                    const payload = window.__CAPTURED_PAYLOAD__ || (window.top && window.top.__CAPTURED_PAYLOAD__);
                    if (!payload) return null;

                    function universalDecodeStr(str) {
                        if (!str || typeof str !== 'string') return str || '';
                        if (str.startsWith('<') || str.includes('</') || str.includes('class=')) return str;
                        const _w = document.getElementById('srweNqAnE');
                        const _m = document.getElementById('fG9dnQb0b');
                        if (!_w || !_m) return str;
                        try {
                            const x7iqG = document.title.substring(document.title.length - (55 ^ 45)) + _w.textContent + _m.textContent;
                            let rApy5 = 623;
                            for (let i = 0; i < x7iqG.length; i++) {
                                const _c = x7iqG.charCodeAt(i);
                                if (_c >= 33 && _c <= 126) {
                                    rApy5 = ((Math.imul(rApy5, 37) ^ _c) & 65535);
                                }
                            }
                            if (rApy5 === 0) rApy5 = 137;
                            const rSAAZ = (rApy5 & 255) || 57;
                            const oN70k = ((rApy5 >> 8) & 255) || 91;
                            const out = [];
                            for (let i = 0; i < str.length; i++) {
                                const _msk = ((rSAAZ + (i * 7)) ^ oN70k) & 127;
                                out.push(String.fromCharCode(str.charCodeAt(i) ^ _msk));
                            }
                            return out.join('');
                        } catch(e) {
                            return str;
                        }
                    }

                    let sections = [];
                    if (Array.isArray(payload)) {
                        sections = payload;
                    } else {
                        for (let k of Object.keys(payload)) {
                            let val = payload[k];
                            if (Array.isArray(val) && val.length > 0 && typeof val[0] === 'object') {
                                let hasInnerQ = Object.keys(val[0]).some(ik => Array.isArray(val[0][ik]) && val[0][ik].length > 0);
                                if (hasInnerQ) {
                                    sections = val;
                                    break;
                                }
                            }
                        }
                    }

                    const extracted = [];
                    sections.forEach((sec, sIdx) => {
                        let secName = `Section ${sIdx + 1}`;
                        for (let k of Object.keys(sec)) {
                            if (typeof sec[k] === 'string' && sec[k].length > 1 && !sec[k].startsWith('<')) {
                                secName = sec[k];
                                break;
                            }
                        }

                        let qList = [];
                        for (let k of Object.keys(sec)) {
                            if (Array.isArray(sec[k]) && sec[k].length > 0 && typeof sec[k][0] === 'object') {
                                qList = sec[k];
                                break;
                            }
                        }

                        qList.forEach((q, qIdx) => {
                            // 1. Options: find array of options in q
                            let rawOpts = [];
                            if (params.opt_key && Array.isArray(q[params.opt_key])) {
                                rawOpts = q[params.opt_key];
                            } else {
                                let optK = Object.keys(q).find(k => Array.isArray(q[k]) && q[k].length >= 2);
                                if (optK) rawOpts = q[optK];
                            }
                            let options = rawOpts.map(opt => universalDecodeStr(opt));

                            // 2. Answer: calculate via formula or direct key
                            let answerIdx = 0;
                            let rawAns = params.ans_key ? q[params.ans_key] : undefined;
                            if (rawAns !== undefined && params.xor_val) {
                                let calc = (rawAns ^ params.xor_val);
                                answerIdx = (params.ans_op === '+') ? (calc + params.sub_val) : (calc - params.sub_val);
                            } else if (q.answer !== undefined) {
                                answerIdx = q.answer;
                            }

                            // 3. Passage
                            let passage = '';
                            if (params.pas_key && q[params.pas_key] !== undefined) {
                                passage = universalDecodeStr(q[params.pas_key]);
                            } else if (q.passage || q.common_data) {
                                passage = universalDecodeStr(q.passage || q.common_data);
                            }

                            // 4. Question
                            let question = '';
                            if (params.q_key && q[params.q_key] !== undefined) {
                                question = universalDecodeStr(q[params.q_key]);
                            } else if (q.question || q.questionText) {
                                question = universalDecodeStr(q.question || q.questionText);
                            }

                            // 5. Solution
                            let solution = '';
                            if (params.sol_key && q[params.sol_key] !== undefined) {
                                solution = universalDecodeStr(q[params.sol_key]);
                            } else if (q.solution || q.explanation) {
                                solution = universalDecodeStr(q.solution || q.explanation);
                            }

                            extracted.push({
                                section: secName,
                                qNum: extracted.length + 1,
                                passage: passage,
                                question: question,
                                options: options,
                                answer: answerIdx,
                                solution: solution
                            });
                        });
                    });

                    return extracted;
                }""", {
                    "ans_key": ans_key,
                    "xor_val": xor_val,
                    "ans_op": ans_op,
                    "sub_val": sub_val,
                    "pas_key": pas_key,
                    "q_key": q_key,
                    "opt_key": opt_key,
                    "sol_key": sol_key
                })
                browser.close()

                if raw_sections:
                    en_list = []
                    hi_list = []

                    for item in raw_sections:
                        p_en, p_hi = split_bilingual_html(item.get("passage", ""))
                        q_en, q_hi = split_bilingual_html(item.get("question", ""))
                        s_en, s_hi = split_bilingual_html(item.get("solution", ""))

                        raw_opts = item.get("options") or []
                        opts_en = []
                        opts_hi = []
                        for opt in raw_opts:
                            o_en, o_hi = split_bilingual_option(opt)
                            opts_en.append(o_en)
                            opts_hi.append(o_hi)

                        ans_val = item.get("answer", 0)

                        en_obj = {
                            "common_data": p_en,
                            "question": q_en,
                            "options": opts_en,
                            "answer": ans_val,
                            "explanation": s_en,
                            "section": item.get("section", "")
                        }
                        hi_obj = {
                            "common_data": p_hi if p_hi else p_en,
                            "question": q_hi if q_hi else q_en,
                            "options": opts_hi if any(opts_hi) else opts_en,
                            "answer": ans_val,
                            "explanation": s_hi if s_hi else s_en,
                            "section": item.get("section", "")
                        }
                        en_list.append(en_obj)
                        hi_list.append(hi_obj)

                    result = (en_list, hi_list, {"format": "universal_headless", "count": len(en_list)})
                    _HTML_DECRYPT_CACHE[cache_key] = result
                    return result
        except Exception as headless_err:
            print("Universal headless extraction error in admin_tool:", headless_err)

    return [], [], {}

@app.route("/api/html-info", methods=["POST"])
def get_html_info():
    """
    Returns metadata about an uploaded HTML test file (question count, sections, format)
    without rendering or uploading images. Used for instant UI feedback upon file drop.
    """
    try:
        data = request.get_json() or {}
        html_content = data.get("html_content", "") or ""
        if not html_content:
            return jsonify({"status": "error", "message": "No HTML content provided"}), 400

        en_list, hi_list, meta = universal_decrypt_html_test(html_content)
        total_q = len(en_list)
        sections = list(dict.fromkeys(q.get("section") for q in en_list if q.get("section")))

        return jsonify({
            "status": "ok",
            "total_questions": total_q,
            "sections": sections,
            "format": meta.get("format", "unknown")
        })
    except Exception as e:
        print("get_html_info error:", e)
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/extract-html", methods=["POST"])
def extract_html():
    try:
        data = request.get_json() or {}
        html_content = data.get("html_content", "") or ""
        question_range_str = str(data.get("question_range", "1-5")).strip()
        exam_id = data.get("exam_id", "sbi_clerk")
        is_set_based = bool(data.get("is_set_based", False))
        no_diagrams = bool(data.get("no_diagrams", False) or data.get("is_passage_only", False) or data.get("is_text_passage_only", False))
        instructions = data.get("instructions", "").strip()

        if not html_content:
            return jsonify({"status": "error", "message": "No HTML content provided. Please upload an HTML test file."}), 400

        # Decrypt HTML test payload using Universal Decryption Engine
        en_list, hi_list, meta_info = universal_decrypt_html_test(html_content)

        if not en_list:
            return jsonify({"status": "error", "message": "Could not decrypt or find question payload in the uploaded HTML test file."}), 400

        total_q = len(en_list)
        if total_q == 0:
            return jsonify({"status": "error", "message": "No questions found in decrypted HTML test payload."}), 400

        def extract_field(obj, keys):
            if not isinstance(obj, dict):
                return None
            for k in keys:
                if k in obj and obj[k] is not None and obj[k] != "":
                    return obj[k]
            return None

        # Flexible question range parsing (e.g. "1-5", "1 to 5", "1..5", "1,2,5", "all", "4")
        def parse_target_q_nums(range_str, total_count):
            if not range_str or not str(range_str).strip():
                return list(range(1, min(6, total_count + 1)))
            clean_str = str(range_str).strip().lower()
            if clean_str == "all":
                return list(range(1, total_count + 1))
            range_match = re.search(r'(\d+)\s*(?:[-–—]|\bto\b|\.\.)\s*(\d+)', clean_str)
            if range_match:
                sq = int(range_match.group(1))
                eq = int(range_match.group(2))
                if sq > total_count:
                    sq = max(1, total_count - 4)
                else:
                    sq = max(1, sq)
                eq = min(total_count, max(1, eq))
                if sq <= eq:
                    return list(range(sq, eq + 1))
                else:
                    return list(range(eq, sq + 1))
            if "," in clean_str:
                nums = []
                for part in clean_str.split(","):
                    digits = re.findall(r'\d+', part)
                    if digits:
                        val = int(digits[0])
                        if 1 <= val <= total_count and val not in nums:
                            nums.append(val)
                if nums:
                    return sorted(nums)
            digits = re.findall(r'\d+', clean_str)
            if digits:
                val = int(digits[0])
                if 1 <= val <= total_count:
                    return [val]
            return list(range(1, min(6, total_count + 1)))

        target_q_nums = parse_target_q_nums(question_range_str, total_q)

        def clean_html(text):
            if not text:
                return ""
            t = str(text)
            t = re.sub(r'<br\s*/?>', '\n', t, flags=re.IGNORECASE)
            t = re.sub(r'</p>', '\n\n', t, flags=re.IGNORECASE)
            t = re.sub(r'</pre>', '\n\n', t, flags=re.IGNORECASE)
            t = re.sub(r'</div>', '\n', t, flags=re.IGNORECASE)
            t = re.sub(r'</li>', '\n', t, flags=re.IGNORECASE)
            t = re.sub(r'<li>', '• ', t, flags=re.IGNORECASE)
            t = re.sub(r'<strong[^>]*>(.*?)</strong>', r'**\1**', t, flags=re.IGNORECASE | re.DOTALL)
            t = re.sub(r'<b[^>]*>(.*?)</b>', r'**\1**', t, flags=re.IGNORECASE | re.DOTALL)
            t = re.sub(r'<em[^>]*>(.*?)</em>', r'*\1*', t, flags=re.IGNORECASE | re.DOTALL)
            t = re.sub(r'<i[^>]*>(.*?)</i>', r'*\1*', t, flags=re.IGNORECASE | re.DOTALL)
            t = re.sub(r'<sup[^>]*>(.*?)</sup>', r'^{\1}', t, flags=re.IGNORECASE | re.DOTALL)
            t = re.sub(r'<sub[^>]*>(.*?)</sub>', r'_{\1}', t, flags=re.IGNORECASE | re.DOTALL)
            t = re.sub(r'<[^>]+>', '', t)
            t = html.unescape(t)
            lines = [line.strip() for line in t.split('\n')]
            result = []
            prev_blank = False
            for line in lines:
                if line:
                    result.append(line)
                    prev_blank = False
                elif not prev_blank:
                    result.append('')
                    prev_blank = True
            return '\n'.join(result).strip()

        def parse_answer_index(ans, opt_len=5):
            if ans is None:
                return 0
            if isinstance(ans, int):
                if 0 <= ans < opt_len:
                    return ans
                elif 1 <= ans <= opt_len:
                    return ans - 1
                return 0
            if isinstance(ans, str):
                ans = ans.strip().upper()
                mapping = {'A': 0, 'B': 1, 'C': 2, 'D': 3, 'E': 4}
                if ans in mapping:
                    return mapping[ans]
                digits = re.findall(r'\d+', ans)
                if digits:
                    num = int(digits[0])
                    if 0 <= num < opt_len:
                        return num
                    elif 1 <= num <= opt_len:
                        return num - 1
            return 0

        # In-memory deduplication cache for images across questions in this batch
        upload_cache = {}
        drive_active = [True]

        def get_or_upload_image(src, q_num, tag_idx, role, lang):
            if not src:
                return None
            if src in upload_cache:
                return upload_cache[src]

            cdn_url = src

            if drive_active[0] and (src.startswith("http://") or src.startswith("https://") or src.startswith("data:image/")):
                img_bytes = None
                ext = "png"
                mime_type = "image/png"

                if src.startswith("data:image/") and ";base64," in src:
                    try:
                        header, b64_data = src.split(";base64,", 1)
                        img_bytes = base64.b64decode(b64_data)
                        if "jpeg" in header or "jpg" in header:
                            ext = "jpg"
                            mime_type = "image/jpeg"
                        elif "webp" in header:
                            ext = "webp"
                            mime_type = "image/webp"
                    except Exception as e:
                        print("Data URI decode error:", e)
                elif requests:
                    try:
                        resp = requests.get(src, headers={"User-Agent": "Mozilla/5.0"}, timeout=4)
                        if resp.status_code == 200:
                            img_bytes = resp.content
                            c_type = resp.headers.get("content-type", "").lower()
                            if "jpeg" in c_type or "jpg" in c_type or src.lower().endswith(".jpg") or src.lower().endswith(".jpeg"):
                                ext = "jpg"
                                mime_type = "image/jpeg"
                            elif "webp" in c_type or src.lower().endswith(".webp"):
                                ext = "webp"
                                mime_type = "image/webp"
                    except Exception as e:
                        print(f"Could not download image {src}: {e}")

                if img_bytes:
                    clean_tag = f"img{tag_idx}"
                    label_prefix = f"HTML_Q{q_num}_{clean_tag}" if lang == "en" else f"HTML_HI_Q{q_num}_{clean_tag}"
                    try:
                        upload_res, err = upload_bytes_to_drive(
                            file_bytes=img_bytes,
                            exam_id=exam_id,
                            image_type=role,
                            label=label_prefix,
                            ext=ext,
                            mime_type=mime_type
                        )
                        if upload_res and upload_res.get("directUrl"):
                            cdn_url = upload_res["directUrl"]
                        elif err and ("invalid_grant" in str(err) or "not connected" in str(err)):
                            drive_active[0] = False  # Skip slow Drive calls for remaining images
                    except Exception:
                        drive_active[0] = False

            upload_cache[src] = cdn_url
            return cdn_url

        def screenshot_html_table(table_html):
            if not sync_playwright:
                return None
            try:
                full_html = f"""
                <!DOCTYPE html>
                <html>
                <head>
                  <meta charset="utf-8">
                  <style>
                    body {{
                      background: #ffffff;
                      padding: 16px;
                      margin: 0;
                      display: inline-block;
                      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    }}
                  </style>
                </head>
                <body>
                  {table_html}
                </body>
                </html>
                """
                with sync_playwright() as p:
                    browser = p.chromium.launch()
                    page = browser.new_page(viewport={"width": 800, "height": 600}, device_scale_factor=2)
                    page.set_content(full_html)
                    loc = page.locator("body")
                    png_bytes = loc.screenshot()
                    browser.close()
                    return png_bytes
            except Exception as e:
                print("Table screenshot error:", e)
                return None

        def process_content_images(raw_text, role="question", lang="en", q_num=1):
            if not raw_text:
                return "", []

            extracted_images = []

            if no_diagrams:
                # Strip all images and table screenshots for pure text mode
                text_no_img = re.sub(r'<img[^>]*>', '', raw_text, flags=re.IGNORECASE)
                return clean_html(text_no_img), []

            # 1. Process <img> tags
            def img_replacer(m):
                src = m.group(1).strip()
                if not src:
                    return ""
                tag_idx = len(extracted_images) + 1
                cdn_url = get_or_upload_image(src, q_num=q_num, tag_idx=tag_idx, role=role, lang=lang)
                if cdn_url:
                    extracted_images.append(cdn_url)
                    return f"\n\n[img{tag_idx}]\n\n"
                return ""

            tagged_html = re.sub(r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>', img_replacer, raw_text, flags=re.IGNORECASE)

            # 2. Check for <table> tags if Playwright is available and no <img> in DI
            if "<table" in tagged_html.lower() and not no_diagrams:
                def table_replacer(m):
                    table_code = m.group(0)
                    table_png = screenshot_html_table(table_code)
                    if table_png:
                        tag_idx = len(extracted_images) + 1
                        cdn_url = f"data:image/png;base64,{base64.b64encode(table_png).decode('utf-8')}"
                        if drive_active[0]:
                            try:
                                upload_res, err = upload_bytes_to_drive(
                                    file_bytes=table_png,
                                    exam_id=exam_id,
                                    image_type=role,
                                    label=f"HTML_TABLE_Q{q_num}_img{tag_idx}",
                                    ext="png",
                                    mime_type="image/png"
                                )
                                if upload_res and upload_res.get("directUrl"):
                                    cdn_url = upload_res["directUrl"]
                                elif err and ("invalid_grant" in str(err) or "not connected" in str(err)):
                                    drive_active[0] = False
                            except Exception:
                                drive_active[0] = False
                        extracted_images.append(cdn_url)
                        return f"\n\n[img{tag_idx}]\n\n"
                    return table_code

                tagged_html = re.sub(r'<table[^>]*>.*?</table>', table_replacer, tagged_html, flags=re.IGNORECASE | re.DOTALL)

            cleaned_text = clean_html(tagged_html)
            return cleaned_text, extracted_images

        questions = []

        for q_num in target_q_nums:
            idx = q_num - 1
            if idx < 0 or idx >= total_q:
                continue

            raw_item = en_list[idx]
            raw_item_hi = hi_list[idx] if idx < len(hi_list) else None

            # Resolve sub-objects if { en: {...}, hi: {...} }
            item_en = raw_item
            item_hi = raw_item_hi if raw_item_hi is not None else raw_item

            if isinstance(raw_item, dict):
                if 'en' in raw_item and isinstance(raw_item['en'], dict):
                    item_en = raw_item['en']
                if 'hi' in raw_item and isinstance(raw_item['hi'], dict):
                    item_hi = raw_item['hi']

            # Extract fields flexibly
            q_keys_en = ['question', 'question_en', 'questionText', 'ques', 'q_text', 'title', 'text', 'content']
            q_keys_hi = ['question_hi', 'ques_hi', 'q_hi', 'questionTextHi'] + q_keys_en
            comm_keys_en = ['common_data', 'common_en', 'passage', 'direction', 'directions', 'info', 'notes']
            comm_keys_hi = ['common_hi', 'passage_hi', 'direction_hi'] + comm_keys_en

            comm_en_raw = extract_field(item_en, comm_keys_en) or extract_field(raw_item, comm_keys_en) or ""
            q_en_raw = extract_field(item_en, q_keys_en) or extract_field(raw_item, q_keys_en) or ""

            comm_hi_raw = extract_field(item_hi, comm_keys_hi) or extract_field(raw_item, comm_keys_hi) or ""
            q_hi_raw = extract_field(item_hi, q_keys_hi) or extract_field(raw_item, q_keys_hi) or ""

            comm_en_txt, comm_en_imgs = process_content_images(comm_en_raw, role="question", lang="en", q_num=q_num)
            q_en_txt, q_en_imgs = process_content_images(q_en_raw, role="question", lang="en", q_num=q_num)

            q_images_en = comm_en_imgs + q_en_imgs
            full_q_en = (comm_en_txt + "\n\n" + q_en_txt).strip() if comm_en_txt else q_en_txt.strip()

            comm_hi_txt, comm_hi_imgs = process_content_images(comm_hi_raw, role="question", lang="hi", q_num=q_num)
            q_hi_txt, q_hi_imgs = process_content_images(q_hi_raw, role="question", lang="hi", q_num=q_num)

            q_images_hi = comm_hi_imgs + q_hi_imgs
            if not q_images_hi:
                q_images_hi = list(q_images_en)
            full_q_hi = (comm_hi_txt + "\n\n" + q_hi_txt).strip() if comm_hi_txt else q_hi_txt.strip()

            # Options
            opt_keys_en = ['options', 'choices', 'answers', 'opts', 'options_en']
            opt_keys_hi = ['options_hi', 'choices_hi', 'answers_hi'] + opt_keys_en

            raw_opts_en = extract_field(item_en, opt_keys_en) or extract_field(raw_item, opt_keys_en) or []
            if isinstance(raw_opts_en, dict):
                raw_opts_en = list(raw_opts_en.values())
            opts_en = [clean_html(o) for o in raw_opts_en] if isinstance(raw_opts_en, list) else []
            while len(opts_en) < 5:
                opts_en.append("")

            raw_opts_hi = extract_field(item_hi, opt_keys_hi) or extract_field(raw_item, opt_keys_hi) or []
            if isinstance(raw_opts_hi, dict):
                raw_opts_hi = list(raw_opts_hi.values())
            opts_hi = [clean_html(o) for o in raw_opts_hi] if isinstance(raw_opts_hi, list) else []
            while len(opts_hi) < 5:
                opts_hi.append(opts_en[len(opts_hi)] if len(opts_hi) < len(opts_en) else "")

            # Correct Answer Index
            ans_keys = ['correctIndex', 'correct', 'answer', 'ans', 'correctIndex_hi', 'correct_hi', 'answer_hi', 'ans_hi']
            raw_ans = extract_field(item_en, ans_keys)
            if raw_ans is None:
                raw_ans = extract_field(raw_item, ans_keys)
            correct_idx = parse_answer_index(raw_ans, len(opts_en))

            # Explanations
            sol_keys_en = ['explanation', 'solution', 'exp', 'ans_explanation', 'sol', 'explanation_en', 'solution_en']
            sol_keys_hi = ['explanation_hi', 'solution_hi', 'exp_hi'] + sol_keys_en

            exp_en_raw = extract_field(item_en, sol_keys_en) or extract_field(raw_item, sol_keys_en) or ""
            exp_hi_raw = extract_field(item_hi, sol_keys_hi) or extract_field(raw_item, sol_keys_hi) or ""

            exp_en_txt, exp_en_imgs = process_content_images(exp_en_raw, role="explanation", lang="en", q_num=q_num)
            exp_hi_txt, exp_hi_imgs = process_content_images(exp_hi_raw, role="explanation", lang="hi", q_num=q_num)

            exp_images_en = exp_en_imgs
            exp_images_hi = exp_hi_imgs if exp_hi_imgs else list(exp_images_en)

            if not full_q_hi and full_q_en:
                full_q_hi = full_q_en
            if not any(opts_hi) and any(opts_en):
                opts_hi = list(opts_en)
            if not exp_hi_txt and exp_en_txt:
                exp_hi_txt = exp_en_txt

            q_obj = {
                "questionText": full_q_en,
                "questionTextHi": full_q_hi,
                "options": opts_en[:5],
                "optionsHi": opts_hi[:5],
                "correctIndex": correct_idx,
                "explanation": exp_en_txt,
                "explanationHi": exp_hi_txt,
                "difficulty": "Medium",
                "questionImages": q_images_en,
                "questionImagesHi": q_images_hi,
                "explanationImages": exp_images_en,
                "explanationImagesHi": exp_images_hi,
                "questionImageDriveLink": q_images_en[0] if q_images_en else "",
                "explanationImageDriveLink": exp_images_en[0] if exp_images_en else ""
            }
            questions.append(q_obj)

        # Post-process questions: strip numbers & normalize Devanagari numerals, normalize newlines, synchronize diagram tags
        for q in questions:
            if not isinstance(q, dict):
                continue
            if q.get("questionText"):
                q["questionText"] = normalize_text_newlines(strip_question_numbers(q["questionText"]))
            if q.get("questionTextHi"):
                q["questionTextHi"] = normalize_text_newlines(strip_question_numbers(normalize_devanagari_numerals(q["questionTextHi"])))
            if q.get("options") and isinstance(q["options"], list):
                q["options"] = [normalize_text_newlines(str(opt)) for opt in q["options"]]
            if q.get("optionsHi") and isinstance(q["optionsHi"], list):
                q["optionsHi"] = [normalize_text_newlines(normalize_devanagari_numerals(str(opt))) for opt in q["optionsHi"]]
            if q.get("explanation"):
                q["explanation"] = normalize_text_newlines(q["explanation"])
            if q.get("explanationHi"):
                q["explanationHi"] = normalize_text_newlines(normalize_devanagari_numerals(q["explanationHi"]))

            # Synchronize tags with images
            q_img_count = len(q.get("questionImages") or [])
            if q_img_count > 0:
                q["questionText"] = sync_diagram_tags_in_text(q.get("questionText", ""), q_img_count, is_explanation=False)
                if q.get("questionTextHi"):
                    q_hi_count = len(q.get("questionImagesHi") or []) or q_img_count
                    q["questionTextHi"] = sync_diagram_tags_in_text(q.get("questionTextHi", ""), q_hi_count, is_explanation=False)
            else:
                if q.get("questionText"):
                    q["questionText"] = re.sub(r'\[img\d+\]\s*', '', q["questionText"]).strip()
                if q.get("questionTextHi"):
                    q["questionTextHi"] = re.sub(r'\[img\d+\]\s*', '', q["questionTextHi"]).strip()

            exp_img_count = len(q.get("explanationImages") or [])
            if exp_img_count > 0:
                q["explanation"] = sync_diagram_tags_in_text(q.get("explanation", ""), exp_img_count, is_explanation=True)
                if q.get("explanationHi"):
                    exp_hi_count = len(q.get("explanationImagesHi") or []) or exp_img_count
                    q["explanationHi"] = sync_diagram_tags_in_text(q.get("explanationHi", ""), exp_hi_count, is_explanation=True)
            else:
                if q.get("explanation"):
                    q["explanation"] = re.sub(r'\[img\d+\]\s*', '', q["explanation"]).strip()
                if q.get("explanationHi"):
                    q["explanationHi"] = re.sub(r'\[img\d+\]\s*', '', q["explanationHi"]).strip()

            # Auto-repair LaTeX
            q['questionText'] = auto_repair_latex(q.get('questionText', ''))
            q['questionTextHi'] = auto_repair_latex(q.get('questionTextHi', ''))
            q['explanation'] = auto_repair_latex(q.get('explanation', ''))
            q['explanationHi'] = auto_repair_latex(q.get('explanationHi', ''))

        return jsonify({
            "status": "ok",
            "count": len(questions),
            "questions": questions,
            "message": f"Successfully extracted {len(questions)} question(s) & official solution(s) from HTML file!"
        })

    except Exception as e:
        print("Extract HTML error:", e)
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/save-questions", methods=["POST"])
def save_questions():
    try:
        payload = request.get_json() or {}
        exam_id = payload.get("examId")
        mode = payload.get("mode", "dpp") # "dpp" or "topicwise"
        questions_to_add = payload.get("questions", [])

        if not exam_id:
            return jsonify({"status": "error", "message": "examId is required"}), 400
        if not questions_to_add:
            return jsonify({"status": "error", "message": "No questions to save"}), 400

        for q in questions_to_add:
            if q.get("questionText"):
                q["questionText"] = normalize_text_newlines(q["questionText"])
            if q.get("questionTextHi"):
                q["questionTextHi"] = normalize_text_newlines(q["questionTextHi"])
            if q.get("options") and isinstance(q["options"], list):
                q["options"] = [normalize_text_newlines(str(opt)) for opt in q["options"]]
            if q.get("optionsHi") and isinstance(q["optionsHi"], list):
                q["optionsHi"] = [normalize_text_newlines(str(opt)) for opt in q["optionsHi"]]
            if q.get("explanation"):
                q["explanation"] = normalize_text_newlines(q["explanation"])
            if q.get("explanationHi"):
                q["explanationHi"] = normalize_text_newlines(q["explanationHi"])

        target_file = DATA_DIR / f"{exam_id}.json"
        if not target_file.exists():
            return jsonify({"status": "error", "message": f"Exam file {exam_id}.json not found"}), 404

        with open(target_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Create backup
        bak_file = DATA_DIR / f"{exam_id}.bak"
        with open(bak_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        existing_questions = data.get("questions", [])
        timestamp = int(time.time())

        if mode == "dpp":
            dpp_day = int(payload.get("dppDay", 1))
            timer_minutes = int(payload.get("timerMinutes", 15))
            stage_id = payload.get("stageId", "prelims")
            section_id = payload.get("sectionId", "quant")
            topic_id = payload.get("topicId", "dpp_mixed")

            # Update or add dppMeta (Day number based, unlock handled on device per install date)
            dpp_meta = data.setdefault("dppMeta", [])
            meta_found = False
            for m in dpp_meta:
                if m.get("day") == dpp_day:
                    m["timerMinutes"] = timer_minutes
                    meta_found = True
                    break
            if not meta_found:
                dpp_meta.append({
                    "examId": exam_id,
                    "day": dpp_day,
                    "timerMinutes": timer_minutes
                })
            # Sort dppMeta by day
            dpp_meta.sort(key=lambda x: x.get("day", 0))

            # Format and append questions
            for i, q in enumerate(questions_to_add):
                orig_id = str(q.get("id") or "")
                if orig_id and orig_id.startswith(f"{exam_id}_dpp_d{dpp_day}_"):
                    qid = orig_id
                else:
                    qid = f"{exam_id}_dpp_d{dpp_day}_{timestamp}_{i+1}"
                img_payload = extract_question_images_payload(q)
                new_q = {
                    "id": qid,
                    "examId": exam_id,
                    "stageId": q.get("stageId") or stage_id,
                    "sectionId": q.get("sectionId") or section_id,
                    "topicId": q.get("topicId") or topic_id,
                    "type": "dpp",
                    "dppDay": dpp_day,
                    "questionText": strip_question_numbers(q.get("questionText", "").strip()),
                    "questionTextHi": strip_question_numbers(normalize_devanagari_numerals(q.get("questionTextHi", "").strip())) if q.get("questionTextHi") else None,
                    **img_payload,
                    "options": [str(opt).strip() for opt in q.get("options", [])],
                    "optionsHi": [normalize_devanagari_numerals(str(opt).strip()) for opt in q.get("optionsHi", [])] if q.get("optionsHi") else None,
                    "correctIndex": int(q.get("correctIndex", 0)),
                    "explanation": q.get("explanation", "").strip(),
                    "explanationHi": normalize_devanagari_numerals(q.get("explanationHi", "").strip()) if q.get("explanationHi") else None,
                    "difficulty": q.get("difficulty", "Medium"),
                    "isActive": True
                }
                existing_questions.append(new_q)

        elif mode == "sectional":
            stage_id = payload.get("stageId", "prelims")
            section_id = payload.get("sectionId", "quant")
            test_number = int(payload.get("testNumber", 1))
            timer_minutes = int(payload.get("timerMinutes", 20))

            for i, q in enumerate(questions_to_add):
                qid = q.get("id") or f"{exam_id}_sec_{stage_id}_{section_id}_t{test_number}_{timestamp}_{i+1}"
                img_payload = extract_question_images_payload(q)
                new_q = {
                    "id": qid,
                    "examId": exam_id,
                    "stageId": stage_id,
                    "sectionId": section_id,
                    "topicId": f"sectional_{section_id}_t{test_number}",
                    "type": "sectional",
                    "testNumber": test_number,
                    "timerMinutes": timer_minutes,
                    "questionText": strip_question_numbers(q.get("questionText", "").strip()),
                    "questionTextHi": strip_question_numbers(normalize_devanagari_numerals(q.get("questionTextHi", "").strip())) if q.get("questionTextHi") else None,
                    **img_payload,
                    "options": [str(opt).strip() for opt in q.get("options", [])],
                    "optionsHi": [normalize_devanagari_numerals(str(opt).strip()) for opt in q.get("optionsHi", [])] if q.get("optionsHi") else None,
                    "correctIndex": int(q.get("correctIndex", 0)),
                    "explanation": q.get("explanation", "").strip(),
                    "explanationHi": normalize_devanagari_numerals(q.get("explanationHi", "").strip()) if q.get("explanationHi") else None,
                    "difficulty": q.get("difficulty", "Medium"),
                    "isActive": True
                }
                existing_questions.append(new_q)

        elif mode == "memory_based":
            year = int(payload.get("year", 2023))
            stage_id = payload.get("stageId", "prelims")
            exam_name = data.get("exam", {}).get("name", exam_id.upper().replace("_", " "))
            paper_id = payload.get("paperId") or f"{exam_id}_pyq_{year}"
            paper_title = payload.get("paperTitle") or f"{exam_name} {stage_id.title()} {year} Memory Based Paper"
            duration_minutes = int(payload.get("durationMinutes", 60))
            section_id = payload.get("sectionId", "quant")

            # Register or update in memoryBasedPapers
            mb_papers = data.setdefault("memoryBasedPapers", [])
            existing_paper = next((p for p in mb_papers if p.get("id") == paper_id or p.get("year") == year), None)
            if existing_paper:
                existing_paper["title"] = paper_title
                existing_paper["durationMinutes"] = duration_minutes
                existing_paper["year"] = year
                existing_paper["stageId"] = stage_id
                existing_paper["questionsCount"] = existing_paper.get("questionsCount", 0) + len(questions_to_add)
            else:
                mb_papers.append({
                    "id": paper_id,
                    "year": year,
                    "title": paper_title,
                    "stageId": stage_id,
                    "durationMinutes": duration_minutes,
                    "questionsCount": len(questions_to_add),
                    "difficulty": payload.get("difficulty", "Moderate")
                })

            for i, q in enumerate(questions_to_add):
                qid = q.get("id") or f"{exam_id}_pyq_{year}_{timestamp}_{i+1}"
                img_payload = extract_question_images_payload(q)
                new_q = {
                    "id": qid,
                    "examId": exam_id,
                    "stageId": stage_id,
                    "sectionId": q.get("sectionId") or section_id,
                    "topicId": f"pyq_{year}",
                    "type": "pyq",
                    "year": year,
                    "paperId": paper_id,
                    "questionText": strip_question_numbers(q.get("questionText", "").strip()),
                    "questionTextHi": strip_question_numbers(normalize_devanagari_numerals(q.get("questionTextHi", "").strip())) if q.get("questionTextHi") else None,
                    **img_payload,
                    "options": [str(opt).strip() for opt in q.get("options", [])],
                    "optionsHi": [normalize_devanagari_numerals(str(opt).strip()) for opt in q.get("optionsHi", [])] if q.get("optionsHi") else None,
                    "correctIndex": int(q.get("correctIndex", 0)),
                    "explanation": q.get("explanation", "").strip(),
                    "explanationHi": normalize_devanagari_numerals(q.get("explanationHi", "").strip()) if q.get("explanationHi") else None,
                    "difficulty": q.get("difficulty", "Medium"),
                    "isActive": True
                }
                existing_questions.append(new_q)

        else: # topicwise
            stage_id = payload.get("stageId", "prelims")
            section_id = payload.get("sectionId", "quant")
            topic_id = payload.get("topicId", "topic")
            topic_name = payload.get("topicName") or topic_id.replace("_", " ").title()
            test_number = int(payload.get("testNumber", 1))
            timer_minutes = int(payload.get("timerMinutes", 10))

            # Ensure topic exists in stages structure
            if topic_name:
                stages = data.setdefault("stages", [])
                stage_obj = next((s for s in stages if s.get("id") == stage_id), None)
                if not stage_obj:
                    stage_obj = {"id": stage_id, "name": stage_id.title(), "sections": []}
                    stages.append(stage_obj)
                sections = stage_obj.setdefault("sections", [])
                sec_obj = next((sec for sec in sections if sec.get("id") == section_id), None)
                if not sec_obj:
                    sec_obj = {"id": section_id, "name": section_id.title(), "topics": []}
                    sections.append(sec_obj)
                topics = sec_obj.setdefault("topics", [])
                if not any(t.get("id") == topic_id for t in topics):
                    topics.append({
                        "id": topic_id,
                        "name": topic_name,
                        "timerMinutes": timer_minutes
                    })

            for i, q in enumerate(questions_to_add):
                qid = q.get("id") or f"{exam_id}_{topic_id}_t{test_number}_{timestamp}_{i+1}"
                img_payload = extract_question_images_payload(q)
                new_q = {
                    "id": qid,
                    "examId": exam_id,
                    "stageId": stage_id,
                    "sectionId": section_id,
                    "topicId": topic_id,
                    "type": "topicwise",
                    "testNumber": test_number,
                    "timerMinutes": timer_minutes,
                    "questionText": strip_question_numbers(q.get("questionText", "").strip()),
                    "questionTextHi": strip_question_numbers(normalize_devanagari_numerals(q.get("questionTextHi", "").strip())) if q.get("questionTextHi") else None,
                    **img_payload,
                    "options": [str(opt).strip() for opt in q.get("options", [])],
                    "optionsHi": [normalize_devanagari_numerals(str(opt).strip()) for opt in q.get("optionsHi", [])] if q.get("optionsHi") else None,
                    "correctIndex": int(q.get("correctIndex", 0)),
                    "explanation": q.get("explanation", "").strip(),
                    "explanationHi": normalize_devanagari_numerals(q.get("explanationHi", "").strip()) if q.get("explanationHi") else None,
                    "difficulty": q.get("difficulty", "Medium"),
                    "isActive": True
                }
                existing_questions.append(new_q)

        data["questions"] = existing_questions
        save_exam_data(exam_id, data)

        return jsonify({
            "status": "ok",
            "message": f"Successfully saved {len(questions_to_add)} question(s) to {target_file.name}!",
            "totalQuestions": len(existing_questions)
        })

    except Exception as e:
        print("Save questions error:", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/add-topic", methods=["POST"])
def add_topic():
    try:
        payload = request.get_json() or {}
        exam_id = payload.get("examId")
        stage_id = payload.get("stageId", "prelims")
        section_id = payload.get("sectionId", "quant")
        topic_name = (payload.get("topicName") or "").strip()
        timer_minutes = int(payload.get("timerMinutes", 10))
        topic_id = (payload.get("topicId") or "").strip()
        
        if not exam_id or not topic_name:
            return jsonify({"status": "error", "message": "examId and topicName are required"}), 400
        
        if not topic_id:
            topic_id = re.sub(r'[^a-z0-9]+', '_', topic_name.lower()).strip('_')
            
        target_file = DATA_DIR / f"{exam_id}.json"
        if not target_file.exists():
            return jsonify({"status": "error", "message": "Exam file not found"}), 404
            
        with open(target_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        stages = data.setdefault("stages", [])
        stage_obj = next((s for s in stages if s.get("id") == stage_id), None)
        if not stage_obj:
            stage_obj = {"id": stage_id, "name": stage_id.title(), "sections": []}
            stages.append(stage_obj)
        sections = stage_obj.setdefault("sections", [])
        sec_obj = next((sec for sec in sections if sec.get("id") == section_id), None)
        if not sec_obj:
            sec_obj = {"id": section_id, "name": section_id.title(), "topics": []}
            sections.append(sec_obj)
        topics = sec_obj.setdefault("topics", [])
        
        existing_topic = next((t for t in topics if t.get("id") == topic_id), None)
        if existing_topic:
            existing_topic["name"] = topic_name
            existing_topic["timerMinutes"] = timer_minutes
        else:
            topics.append({
                "id": topic_id,
                "name": topic_name,
                "timerMinutes": timer_minutes
            })
            
        save_exam_data(exam_id, data)
        return jsonify({
            "status": "ok",
            "message": f"Topic '{topic_name}' added successfully!",
            "topic": {"id": topic_id, "name": topic_name, "timerMinutes": timer_minutes}
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/delete-topic", methods=["POST"])
def delete_topic():
    try:
        payload = request.get_json() or {}
        exam_id = payload.get("examId")
        stage_id = payload.get("stageId", "prelims")
        section_id = payload.get("sectionId", "quant")
        topic_id = payload.get("topicId")
        
        if not exam_id or not topic_id:
            return jsonify({"status": "error", "message": "examId and topicId are required"}), 400
            
        target_file = DATA_DIR / f"{exam_id}.json"
        if not target_file.exists():
            return jsonify({"status": "error", "message": "Exam file not found"}), 404
            
        with open(target_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        # 1. Remove topic from stages
        stages = data.get("stages", [])
        stage_obj = next((s for s in stages if s.get("id") == stage_id), None)
        if stage_obj:
            sec_obj = next((sec for sec in stage_obj.get("sections", []) if sec.get("id") == section_id), None)
            if sec_obj:
                sec_obj["topics"] = [t for t in sec_obj.get("topics", []) if t.get("id") != topic_id]
                
        # 2. Delete all questions in this topic
        all_q = data.get("questions", [])
        before_count = len(all_q)
        remaining_q = [q for q in all_q if not (q.get("type") == "topicwise" and q.get("topicId") == topic_id)]
        deleted_count = before_count - len(remaining_q)
        data["questions"] = remaining_q
        
        save_exam_data(exam_id, data)
        return jsonify({
            "status": "ok",
            "message": f"Topic deleted successfully! Removed {deleted_count} question(s).",
            "deletedQuestions": deleted_count
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/exam-questions", methods=["GET"])
def get_exam_questions():
    try:
        exam_id = request.args.get("examId")
        mode = request.args.get("mode", "dpp")
        if not exam_id:
            return jsonify({"status": "error", "message": "examId required"}), 400

        target_file = DATA_DIR / f"{exam_id}.json"
        if not target_file.exists():
            return jsonify({"status": "error", "message": f"{exam_id}.json not found"}), 404

        with open(target_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        all_q = data.get("questions", [])
        matched = []
        if mode == "dpp":
            day = int(request.args.get("dppDay", 1))
            matched = [q for q in all_q if q.get("type") == "dpp" and int(q.get("dppDay", 0)) == day]
        elif mode == "sectional":
            stage_id = request.args.get("stageId")
            section_id = request.args.get("sectionId")
            test_num = request.args.get("testNumber")
            matched = [
                q for q in all_q
                if q.get("type") in ("sectional", "sectional_test") and
                (not stage_id or q.get("stageId") == stage_id) and
                (not section_id or q.get("sectionId") == section_id) and
                (not test_num or str(q.get("testNumber", 1)) == str(test_num))
            ]
        elif mode == "memory_based":
            year_val = request.args.get("year")
            paper_id_val = request.args.get("paperId")
            matched = [
                q for q in all_q
                if (q.get("type") in ("pyq", "memory_based") or (year_val and str(q.get("year", "")) == str(year_val))) and
                (not year_val or str(q.get("year", "")) == str(year_val)) and
                (not paper_id_val or q.get("paperId") == paper_id_val)
            ]
        else:
            stage_id = request.args.get("stageId")
            section_id = request.args.get("sectionId")
            topic_id = request.args.get("topicId")
            test_num = request.args.get("testNumber")
            matched = [
                q for q in all_q
                if q.get("type") not in ("dpp", "sectional", "sectional_test", "pyq", "memory_based") and
                (not stage_id or q.get("stageId") == stage_id) and
                (not section_id or q.get("sectionId") == section_id) and
                (not topic_id or q.get("topicId") == topic_id) and
                (not test_num or str(q.get("testNumber") or q.get("setNumber") or 1) == str(test_num))
            ]

        return jsonify({
            "status": "ok",
            "count": len(matched),
            "questions": matched
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/reorder-questions", methods=["POST"])
def reorder_questions():
    try:
        payload = request.get_json() or {}
        exam_id = payload.get("examId")
        ordered_ids = payload.get("orderedIds", [])

        if not exam_id or not ordered_ids:
            return jsonify({"status": "error", "message": "examId and orderedIds required"}), 400

        target_file = DATA_DIR / f"{exam_id}.json"
        if not target_file.exists():
            return jsonify({"status": "error", "message": "Exam not found"}), 404

        with open(target_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Backup
        bak_file = DATA_DIR / f"{exam_id}.bak"
        with open(bak_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        all_q = data.get("questions", [])
        q_map = {q["id"]: q for q in all_q}

        # Keep non-target questions in their places, reorder targeted questions
        ordered_set = set(ordered_ids)
        target_indices = [i for i, q in enumerate(all_q) if q.get("id") in ordered_set]

        # Put items from ordered_ids sequentially into target_indices
        for idx, qid in zip(target_indices, ordered_ids):
            if qid in q_map:
                all_q[idx] = q_map[qid]

        data["questions"] = all_q
        save_exam_data(exam_id, data)

        return jsonify({"status": "ok", "message": "Questions successfully reordered!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/update-question", methods=["POST"])
def update_question():
    try:
        payload = request.get_json() or {}
        exam_id = payload.get("examId")
        updated_q = payload.get("question")

        if not exam_id or not updated_q or not updated_q.get("id"):
            return jsonify({"status": "error", "message": "examId and valid question required"}), 400

        target_file = DATA_DIR / f"{exam_id}.json"
        if not target_file.exists():
            return jsonify({"status": "error", "message": "Exam not found"}), 404

        with open(target_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Backup
        bak_file = DATA_DIR / f"{exam_id}.bak"
        with open(bak_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        all_q = data.get("questions", [])
        found = False
        for i, q in enumerate(all_q):
            if q.get("id") == updated_q.get("id"):
                img_payload = extract_question_images_payload(updated_q)
                all_q[i] = {
                    **q,
                    "questionText": strip_question_numbers(updated_q.get("questionText", "").strip()),
                    "questionTextHi": strip_question_numbers(normalize_devanagari_numerals(updated_q.get("questionTextHi", "").strip())) if updated_q.get("questionTextHi") is not None else q.get("questionTextHi"),
                    "options": [str(opt).strip() for opt in updated_q.get("options", [])],
                    "optionsHi": [normalize_devanagari_numerals(str(opt).strip()) for opt in updated_q.get("optionsHi", [])] if updated_q.get("optionsHi") is not None else q.get("optionsHi"),
                    "correctIndex": int(updated_q.get("correctIndex", 0)),
                    "explanation": updated_q.get("explanation", "").strip(),
                    "explanationHi": normalize_devanagari_numerals(updated_q.get("explanationHi", "").strip()) if updated_q.get("explanationHi") is not None else q.get("explanationHi"),
                    **img_payload,
                    "difficulty": updated_q.get("difficulty", "Medium"),
                }
                found = True
                break

        if not found:
            return jsonify({"status": "error", "message": "Question not found"}), 404

        data["questions"] = all_q
        save_exam_data(exam_id, data)

        return jsonify({"status": "ok", "message": "Question updated successfully!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/delete-question", methods=["POST"])
def delete_question():
    try:
        payload = request.get_json() or {}
        exam_id = payload.get("examId")
        question_id = payload.get("questionId")

        if not exam_id or not question_id:
            return jsonify({"status": "error", "message": "examId and questionId required"}), 400

        target_file = DATA_DIR / f"{exam_id}.json"
        if not target_file.exists():
            return jsonify({"status": "error", "message": "Exam not found"}), 404

        with open(target_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Backup
        bak_file = DATA_DIR / f"{exam_id}.bak"
        with open(bak_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        all_q = data.get("questions", [])
        new_q = [q for q in all_q if q.get("id") != question_id]

        if len(new_q) == len(all_q):
            return jsonify({"status": "error", "message": "Question not found"}), 404

        data["questions"] = new_q
        save_exam_data(exam_id, data)

        return jsonify({
            "status": "ok",
            "message": "Question deleted successfully!",
            "totalQuestions": len(new_q)
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/git-push-web", methods=["POST"])
def git_push_web():
    try:
        repo_dir = BASE_DIR / "pc_exam_web"
        if not (repo_dir / ".git").exists():
            return jsonify({"status": "error", "message": "pc_exam_web is not a git repository"}), 400
        
        # 1. Ensure all json files are synced from assets/data to pc_exam_web/data
        if DATA_DIR.exists() and PC_WEB_DATA_DIR.exists():
            for src_file in DATA_DIR.glob("*.json"):
                shutil.copy2(src_file, PC_WEB_DATA_DIR / src_file.name)
        
        # 2. Stage, commit, and push
        subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True, text=True)
        res_commit = subprocess.run(["git", "commit", "-m", "Auto-sync DPP questions and web portal updates"], cwd=repo_dir, capture_output=True, text=True)
        res_push = subprocess.run(["git", "push", "origin", "main"], cwd=repo_dir, capture_output=True, text=True)
        
        return jsonify({
            "status": "ok",
            "message": "Successfully synchronized and pushed to GitHub Web Portal!",
            "commitOutput": res_commit.stdout or res_commit.stderr,
            "pushOutput": res_push.stdout or res_push.stderr
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

PORTAL_PENDING_FILE = PC_WEB_DATA_DIR / "portal_pending_questions.json"

@app.route("/api/portal-pending", methods=["GET"])
def get_portal_pending():
    """Checks for questions added via the GitHub Web Portal."""
    try:
        repo_dir = BASE_DIR / "pc_exam_web"
        # Attempt git pull to get latest commits from mobile portal if git is installed
        if (repo_dir / ".git").exists():
            try:
                subprocess.run(["git", "pull", "--quiet"], cwd=repo_dir, capture_output=True, text=True, timeout=5)
            except Exception:
                pass

        if PORTAL_PENDING_FILE.exists():
            with open(PORTAL_PENDING_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    items = json.loads(content)
                    if isinstance(items, list):
                        return jsonify({"status": "ok", "count": len(items), "questions": items})
        return jsonify({"status": "ok", "count": 0, "questions": []})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e), "count": 0, "questions": []}), 500

@app.route("/api/portal-pending/clear", methods=["POST"])
def clear_portal_pending():
    """Clears pending questions from the portal file once merged into APK data."""
    try:
        if PORTAL_PENDING_FILE.exists():
            with open(PORTAL_PENDING_FILE, "w", encoding="utf-8") as f:
                f.write("[]\n")
        return jsonify({"status": "ok", "message": "Portal pending questions cleared"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/portal-pending/import", methods=["POST"])
def import_portal_pending():
    """Imports pending questions (e.g. from clipboard or exported JSON)."""
    try:
        payload = request.get_json() or {}
        incoming = payload.get("questions", [])
        if not incoming and isinstance(payload, list):
            incoming = payload
        
        current = []
        if PORTAL_PENDING_FILE.exists():
            try:
                with open(PORTAL_PENDING_FILE, "r", encoding="utf-8") as f:
                    c = f.read().strip()
                    if c:
                        current = json.loads(c)
            except Exception:
                current = []
        
        if not isinstance(current, list):
            current = []
        
        current.extend(incoming)
        with open(PORTAL_PENDING_FILE, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2, ensure_ascii=False)
            
        return jsonify({"status": "ok", "count": len(current), "message": f"Successfully imported {len(incoming)} questions"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def open_browser():
    time.sleep(1.2)
    webbrowser.open("http://127.0.0.1:5000")

if __name__ == "__main__":
    print("=" * 60)
    print("  Target Bank Exam — Content Creator Studio")
    print("  Server starting on http://127.0.0.1:5000")
    print("=" * 60)
    threading.Thread(target=open_browser, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, debug=False)
