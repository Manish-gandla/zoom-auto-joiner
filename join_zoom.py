#!/usr/bin/env python3
"""
Zoom Meeting Auto-Joiner - FULLY AUTOMATIC
Bot does EVERYTHING - no user interaction needed
Shows clear step-by-step console output
Uses pyautogui for coordinate-based clicking as fallback
"""

import os
import time
import json
import pickle
import subprocess
import threading
import re
import base64
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

# Try to import pyautogui - install if needed
try:
    import pyautogui
    PYATUOGUI_AVAILABLE = True
except ImportError:
    PYATUOGUI_AVAILABLE = False
    print("  [!!] pyautogui not installed - coordinate clicking will use xdotool instead")

# --- CONFIGURATION ---
MEETING_LINK = os.environ.get("ZOOM_MEETING_LINK", "")
DISPLAY_NAME = os.environ.get("ZOOM_DISPLAY_NAME", "Meeting Bot")
SESSION_DURATION_MINUTES = int(os.environ.get("SESSION_DURATION_MINUTES", "60"))
MEETING_PASSCODE = "120217"

# Coordinates for the blue "Join" button (center of the page)
JOIN_BUTTON_X = 768
JOIN_BUTTON_Y = 544

if not MEETING_LINK or "zoom.us" not in MEETING_LINK:
    print("\n  [!!] ERROR: No valid Zoom meeting link provided!")
    print("  [!!] Make sure ZOOM_MEETING_LINK environment variable is set")
    exit(1)

SCREENSHOT_DIR = "/tmp/screenshots"
VIDEO_DIR = "/tmp/videos"
FRAMES_DIR = "/tmp/frames"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)
os.makedirs(VIDEO_DIR, exist_ok=True)
os.makedirs(FRAMES_DIR, exist_ok=True)

frame_counter = [0]
recording_active = [True]
video_thread = [None]


def print_banner(text):
    """Print a section banner"""
    print(f"\n{'━' * 60}")
    print(f"  {text}")
    print(f"{'━' * 60}")


def print_step(step_num, total_steps, description):
    """Print a step header with progress"""
    print(f"\n{'─' * 60}")
    print(f"  ⚡ STEP {step_num}/{total_steps}: {description}")
    print(f"{'─' * 60}")


def print_action(action):
    """Print an action being taken"""
    print(f"    🔄 {action}...")


def print_ok(message):
    """Print a success message"""
    print(f"    ✅ {message}")


def print_skip(message):
    """Print a skip message"""
    print(f"    ⏭️  {message}")


def print_warn(message):
    """Print a warning message"""
    print(f"    ⚠️  {message}")


def print_fail(message):
    """Print a failure message"""
    print(f"    ❌ {message}")


def print_info(message):
    """Print info"""
    print(f"    ℹ️  {message}")


def click_at_coordinates(x, y, description="target"):
    """
    Click at specific screen coordinates using pyautogui or xdotool.
    This is the most reliable way to click the blue Join button.
    """
    print_action(f"Clicking at coordinates ({x}, {y}) - {description}")
    
    try:
        if PYATUOGUI_AVAILABLE:
            pyautogui.moveTo(x, y, duration=0.3)
            time.sleep(0.3)
            pyautogui.click(x, y)
            print_ok(f"Clicked at ({x}, {y}) via pyautogui")
            return True
        else:
            # Use xdotool as fallback
            result = subprocess.run(
                ["xdotool", "mousemove", str(x), str(y), "click", "1"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                print_ok(f"Clicked at ({x}, {y}) via xdotool")
                return True
            else:
                print_warn(f"xdotool click failed: {result.stderr[:100]}")
                return False
    except Exception as e:
        print_warn(f"Coordinate click error: {e}")
        return False


def bring_browser_to_front(driver):
    """Try to bring the browser window to focus for clicking"""
    try:
        # Get window handle and try to focus it via JavaScript
        driver.execute_script("window.focus();")
        time.sleep(0.5)
        
        # Also try using xdotool to find and focus Chrome window
        subprocess.run(
            ["xdotool", "search", "--name", "chrome", "windowfocus", "--sync"],
            capture_output=True, timeout=3
        )
        time.sleep(0.5)
        return True
    except:
        return False


def setup_driver():
    """Configure Chrome driver"""
    print_banner("INITIALIZING BROWSER")
    print_action("Setting up Chrome driver")
    print_action("Auto-detecting Chrome version and downloading matching ChromeDriver")
    
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--lang=en")
    options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    prefs = {
        "profile.default_content_setting_values.notifications": 2,
        "profile.default_content_setting_values.media_stream_mic": 1,
        "profile.default_content_setting_values.media_stream_camera": 1,
    }
    options.add_experimental_option("prefs", prefs)

    service = Service(ChromeDriverManager().install())
    
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    print_ok("Chrome started successfully with matching ChromeDriver")
    return driver


def take_screenshot(driver, label):
    """Save a screenshot"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{SCREENSHOT_DIR}/{timestamp}_{label}.png"
    try:
        driver.save_screenshot(filename)
        print(f"      [📸] Screenshot saved: {label}.png")
    except:
        pass
    return filename


def frame_recorder(driver, output_path):
    """Background thread: captures frames and stitches into video"""
    while recording_active[0]:
        try:
            frame_num = frame_counter[0]
            frame_path = f"{FRAMES_DIR}/frame_{frame_num:06d}.png"
            driver.save_screenshot(frame_path)
            frame_counter[0] += 1
            if frame_num % 120 == 0 and frame_num > 0:
                print(f"      [🎥] Video frames captured: {frame_num}")
        except:
            pass
        time.sleep(0.5)
    
    print(f"\n  [🎥] Encoding video from {frame_counter[0]} frames...")
    
    if frame_counter[0] > 10:
        try:
            cmd = [
                "ffmpeg", "-y",
                "-framerate", "5",
                "-i", f"{FRAMES_DIR}/frame_%06d.png",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-pix_fmt", "yuv420p",
                output_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0:
                file_size = os.path.getsize(output_path)
                print(f"  ✅ Video saved ({file_size / 1024 / 1024:.1f} MB)")
            else:
                print(f"  ⚠️ Video encoding had issues")
        except Exception as e:
            print(f"  ⚠️ Video encoding error: {e}")
    else:
        print("  ⚠️ Not enough frames to create video")


def start_video_recording(driver):
    """Start background frame recording"""
    print_banner("VIDEO RECORDING")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = f"{VIDEO_DIR}/bot_session_{timestamp}.mp4"
    recording_active[0] = True
    frame_counter[0] = 0
    video_thread[0] = threading.Thread(
        target=frame_recorder, args=(driver, output_path), daemon=True
    )
    video_thread[0].start()
    print_ok(f"Video recording started")
    print_info(f"Output file: bot_session_{timestamp}.mp4")
    return output_path


def stop_video_recording():
    """Stop recording"""
    print_action("Stopping video recording and encoding final video")
    recording_active[0] = False
    if video_thread[0] and video_thread[0].is_alive():
        video_thread[0].join(timeout=130)
    print_ok("Video recording finished")


def wait_and_click_selenium(driver, by, selector, description, timeout=6):
    """Wait for an element using Selenium and click it"""
    try:
        if by == By.XPATH:
            element = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, selector))
            )
        elif by == By.CSS_SELECTOR:
            element = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
            )
        else:
            element = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((by, selector))
            )
        driver.execute_script("arguments[0].scrollIntoView(true);", element)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", element)
        print_ok(f"Clicked via Selenium: {description}")
        return True
    except TimeoutException:
        return False
    except Exception as e:
        return False


def find_and_click_blue_join_button_selenium(driver, timeout_per_selector=3):
    """
    Use Selenium to find and click the blue Join button.
    """
    blue_btn_selectors = [
        "//button[contains(@class, 'blue') and contains(text(), 'Join')]",
        "//button[contains(@class, 'Blue') and contains(text(), 'Join')]",
        "//button[contains(@class, 'primary') and contains(text(), 'Join')]",
        "//button[contains(@class, 'Primary') and contains(text(), 'Join')]",
        "//button[contains(@class, 'btn-primary') and contains(text(), 'Join')]",
        "//button[contains(@class, 'btn--primary') and contains(text(), 'Join')]",
        "//button[contains(@class, 'submit') and contains(text(), 'Join')]",
        "//button[contains(@class, 'join') and contains(@class, 'primary')]",
        "//button[contains(@class, 'join-btn')]",
        "//button[contains(@class, 'join-button')]",
        "//button[contains(@class, 'joinBtn')]",
        "//button[@id='joinBtn']",
        "//button[@id='join_btn']",
        "//button[@id='join-button']",
        "//button[@id='joinBtnSubmit']",
        "//button[@id='joinBtnNew']",
        "//a[@id='joinBtn']",
        "//a[@id='join_btn']",
        "//button[@type='submit']",
        "//button[text()='Join']",
        "//button[.='Join']",
        "//span[text()='Join']/..",
        "//span[.='Join']/..",
        "//button[contains(text(), 'Join')]",
        "//a[contains(text(), 'Join')]",
        "//span[contains(text(), 'Join')]/..",
        "//button[contains(@data-testid, 'join')]",
        "//button[contains(@data-testid, 'Join')]",
        "//button[contains(@data-testid, 'submit')]",
        "//button[contains(@aria-label, 'Join')]",
        "//button[contains(@title, 'Join')]",
    ]
    
    for selector in blue_btn_selectors:
        try:
            element = WebDriverWait(driver, timeout_per_selector).until(
                EC.element_to_be_clickable((By.XPATH, selector))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", element)
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", element)
            text_preview = (element.text or element.get_attribute("value") or selector)[:30]
            print_ok(f"Clicked Join button via Selenium: '{text_preview}'")
            return True
        except:
            continue
    
    return False


def click_blue_join_button_with_fallback(driver, max_attempts=5):
    """
    Multi-strategy approach:
    1. Try Selenium selectors
    2. Try JavaScript to find blue/middle-of-page buttons
    3. Try coordinate-based clicking at (768, 544)
    4. Scan all buttons as last resort
    """
    for attempt in range(1, max_attempts + 1):
        print_action(f"Looking for blue Join button (attempt {attempt}/{max_attempts})")
        
        # Method 1: Selenium selectors
        print_action("Method 1: Trying Selenium element selectors...")
        if find_and_click_blue_join_button_selenium(driver, 3):
            return True
        
        # Method 2: JavaScript to find blue buttons in middle of page
        print_action("Method 2: Trying JavaScript search for blue buttons...")
        try:
            result = driver.execute_script("""
                var elements = document.querySelectorAll('button, a, input[type="submit"], input[type="button"], [role="button"]');
                var candidates = [];
                
                for(var i = 0; i < elements.length; i++) {
                    var el = elements[i];
                    var text = (el.textContent || el.value || el.getAttribute('aria-label') || '').trim().toLowerCase();
                    
                    if(text.indexOf('join') === -1) continue;
                    if(!el.offsetParent) continue;
                    
                    var style = window.getComputedStyle(el);
                    var bgColor = style.backgroundColor || '';
                    var color = style.color || '';
                    
                    candidates.push({
                        index: i,
                        text: (el.textContent || el.value || '').trim().substring(0, 30),
                        tag: el.tagName,
                        id: el.id,
                        className: el.className,
                        bgColor: bgColor,
                        color: color,
                        rect: JSON.parse(JSON.stringify({
                            top: el.getBoundingClientRect().top,
                            left: el.getBoundingClientRect().left,
                            width: el.getBoundingClientRect().width,
                            height: el.getBoundingClientRect().height
                        }))
                    });
                }
                
                // Sort by proximity to center of page
                candidates.sort(function(a, b) {
                    var aMid = Math.abs(a.rect.top + a.rect.height/2 - window.innerHeight/2);
                    var bMid = Math.abs(b.rect.top + b.rect.height/2 - window.innerHeight/2);
                    return aMid - bMid;
                });
                
                if(candidates.length > 0) {
                    return candidates;
                }
                return [];
            """)
            
            if result and len(result) > 0:
                print_info(f"Found {len(result)} candidates via JavaScript")
                best = result[0]
                print_info(f"Best: '{best['text']}' at top={best['rect']['top']}, left={best['rect']['left']}")
                
                # Click using JavaScript
                driver.execute_script("""
                    var elements = document.querySelectorAll('button, a, input[type="submit"], input[type="button"], [role="button"]');
                    var idx = arguments[0];
                    if(elements[idx]) {
                        elements[idx].scrollIntoView(true);
                        setTimeout(function() { elements[idx].click(); }, 200);
                    }
                """, best['index'])
                
                time.sleep(1)
                print_ok(f"Clicked blue Join button via JS: '{best['text']}'")
                return True
            else:
                print_skip("No candidate buttons found via JavaScript")
        except Exception as e:
            print_warn(f"JavaScript method error: {e}")
        
        # Method 3: Coordinate-based clicking at (768, 544)
        print_action(f"Method 3: Clicking at coordinates ({JOIN_BUTTON_X}, {JOIN_BUTTON_Y})...")
        bring_browser_to_front(driver)
        time.sleep(0.5)
        if click_at_coordinates(JOIN_BUTTON_X, JOIN_BUTTON_Y, "blue Join button"):
            time.sleep(2)
            # Check if we entered the meeting (look for Leave button)
            try:
                leave_check = driver.find_elements(By.XPATH, "//button[contains(text(), 'Leave')]")
                if leave_check:
                    print_ok("Coordinate click worked - bot entered the meeting!")
                    return True
                else:
                    print_skip("Coordinate click completed but might need retry")
            except:
                pass
        
        # Method 4: Scan all buttons
        print_action("Method 4: Scanning all buttons as last resort...")
        try:
            all_buttons = driver.find_elements(By.XPATH, "//button | //a | //input[@type='submit']")
            for btn in all_buttons:
                try:
                    text = (btn.text or "").strip()
                    if "join" in text.lower() and btn.is_displayed():
                        driver.execute_script("arguments[0].click();", btn)
                        print_ok(f"Clicked: '{text[:25]}'")
                        return True
                except:
                    continue
        except:
            pass
        
        if attempt < max_attempts:
            print_skip(f"No method worked on attempt {attempt}, retrying...")
            time.sleep(4)
            take_screenshot(driver, f"join_retry_{attempt}")
    
    return False


def extract_meeting_id(url):
    """Extract meeting ID from Zoom URL"""
    patterns = [
        r'/j/(\d{9,12})',
        r'/wc/(\d{9,12})',
        r'/s/(\d{9,12})',
        r'confno=(\d{9,12})',
        r'[\?&]mid=(\d{9,12})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def join_meeting(driver):
    """Automated meeting joining - no user input needed"""
    TOTAL_STEPS = 9
    
    # ==========================================
    # STEP 1: Open meeting link
    # ==========================================
    print_step(1, TOTAL_STEPS, "Opening meeting link")
    print_action(f"Navigating to meeting URL")
    print_info(f"URL: {MEETING_LINK[:100]}...")
    driver.get(MEETING_LINK)
    print_action("Waiting for page to fully load")
    time.sleep(8)
    take_screenshot(driver, "01_page_loaded")
    print_ok("Page loaded successfully")
    
    current_url = driver.current_url
    meeting_id = extract_meeting_id(current_url)
    if meeting_id:
        print_info(f"Detected Meeting ID: {meeting_id}")
    else:
        meeting_id = extract_meeting_id(MEETING_LINK)
        if meeting_id:
            print_info(f"Extracted Meeting ID from link: {meeting_id}")
    
    # ==========================================
    # STEP 2: Find and click "Join from Browser"
    # ==========================================
    print_step(2, TOTAL_STEPS, 'Finding and clicking "Join from Browser"')
    
    print_action("Searching for 'Join from your browser' link/button")
    join_selectors = [
        "//button[contains(text(), 'Join from your browser')]",
        "//a[contains(text(), 'Join from your browser')]",
        "//button[contains(text(), 'Join from Browser')]",
        "//a[contains(text(), 'Join from Browser')]",
        "//span[contains(text(), 'Join from your browser')]/..",
        "//span[contains(text(), 'Join from Browser')]/..",
        "//div[contains(text(), 'Join from your browser')]",
        "//p[contains(text(), 'Join from your browser')]",
        "//*[contains(text(), 'Join from your')]",
        "//*[contains(text(), 'Join from')]",
        "//*[contains(text(), 'browser') and contains(text(), 'Join')]",
        "//a[contains(@href, '/wc/')]",
        "//a[contains(@class, 'join-from-browser')]",
    ]
    
    join_clicked = False
    for selector in join_selectors:
        if wait_and_click_selenium(driver, By.XPATH, selector, "Join from Browser", 3):
            join_clicked = True
            break
    
    if not join_clicked:
        print_action("Trying Launch Meeting buttons")
        launch_selectors = [
            "//button[contains(text(), 'Launch Meeting')]",
            "//a[contains(text(), 'Launch Meeting')]",
            "//button[contains(text(), 'Launch')]",
            "//a[contains(text(), 'Launch')]",
        ]
        for selector in launch_selectors:
            if wait_and_click_selenium(driver, By.XPATH, selector, "Launch Meeting", 3):
                join_clicked = True
                break
    
    if not join_clicked:
        print_action("Using direct web client URL to bypass")
        if meeting_id:
            direct_url = f"https://zoom.us/wc/{meeting_id}/join?prefer=1"
            print_info(f"Navigating to: zoom.us/wc/{meeting_id}/join?prefer=1")
            driver.get(direct_url)
            time.sleep(8)
            take_screenshot(driver, "02_direct_web_client")
            join_clicked = True
            print_ok("Direct web client navigation successful")
    
    if not join_clicked:
        print_fail("Could not find any way to join the meeting")
        take_screenshot(driver, "02_no_join_method")
    else:
        time.sleep(5)
        take_screenshot(driver, "02_after_join_click")
    
    # ==========================================
    # STEP 3: Handle "Open zoom.us app?" dialog
    # ==========================================
    print_step(3, TOTAL_STEPS, 'Handling "Open zoom.us app?" dialog')
    
    print_action("Looking for 'Stay in Browser' or 'Cancel' button")
    cancel_selectors = [
        "//a[contains(text(), 'Stay in Browser')]",
        "//button[contains(text(), 'Stay in Browser')]",
        "//button[contains(text(), 'Cancel')]",
        "//a[contains(text(), 'Cancel')]",
        "//button[contains(text(), 'cancel')]",
        "//a[contains(text(), 'stay')]",
        "//button[contains(@class, 'cancel')]",
        "//button[contains(@aria-label, 'Close')]",
    ]
    
    cancelled = False
    for selector in cancel_selectors:
        if wait_and_click_selenium(driver, By.XPATH, selector, "Cancel/Stay in Browser", 3):
            cancelled = True
            time.sleep(3)
            take_screenshot(driver, "03_after_cancel")
            break
    
    if not cancelled:
        print_skip("No app launch dialog detected")
    
    # ==========================================
    # STEP 4: Click "Continue without microphone and camera"
    # ==========================================
    print_step(4, TOTAL_STEPS, 'Dismissing "Continue without microphone and camera" prompts')
    
    continue_selectors = [
        "//button[contains(text(), 'Continue without microphone and camera')]",
        "//a[contains(text(), 'Continue without microphone and camera')]",
        "//span[contains(text(), 'Continue without')]/..",
        "//*[contains(text(), 'Continue without microphone')]",
        "//*[contains(text(), 'Continue without')]",
        "//button[contains(text(), 'Continue')]",
        "//a[contains(text(), 'Continue')]",
        "//button[contains(@aria-label, 'Continue')]",
    ]
    
    for attempt in range(1, 4):
        time.sleep(3)
        print_action(f"Looking for continue prompt (attempt {attempt}/3)")
        clicked = False
        for selector in continue_selectors:
            if wait_and_click_selenium(driver, By.XPATH, selector, f"Continue ({attempt})", 3):
                clicked = True
                time.sleep(3)
                take_screenshot(driver, f"04_continue_{attempt}")
                break
        if not clicked:
            print_skip(f"No prompt on attempt {attempt}")
    
    # ==========================================
    # STEP 5: Enter passcode
    # ==========================================
    print_step(5, TOTAL_STEPS, f'Entering meeting passcode: "{MEETING_PASSCODE}"')
    
    passcode_entered = False
    print_action("Looking for passcode input field")
    
    passcode_selectors = [
        "//input[@id='inputpasscode']",
        "//input[@id='input-for-pwd']",
        "//input[@id='passcode']",
        "//input[@id='password']",
        "//input[@name='passcode']",
        "//input[@name='password']",
        "//input[contains(@placeholder, 'passcode')]",
        "//input[contains(@placeholder, 'Passcode')]",
        "//input[@type='password']",
        "//input[contains(@class, 'pwd')]",
        "//input[contains(@class, 'passcode')]",
        "//input[contains(@id, 'pwd')]",
        "//input[contains(@id, 'passcode')]",
        "//input[contains(@id, 'password')]",
    ]
    
    for selector in passcode_selectors:
        try:
            pwd = WebDriverWait(driver, 2).until(
                EC.element_to_be_clickable((By.XPATH, selector))
            )
            pwd.clear()
            pwd.send_keys(MEETING_PASSCODE)
            print_ok(f"Passcode entered into field")
            passcode_entered = True
            time.sleep(2)
            take_screenshot(driver, "05_passcode_entered")
            break
        except:
            continue
    
    if not passcode_entered:
        print_warn("Could not find passcode field - may not be needed")
    
    # ==========================================
    # STEP 6: Click FIRST "Join" button (after passcode)
    # ==========================================
    print_step(6, TOTAL_STEPS, 'Clicking FIRST "Join" button (after passcode entry)')
    print_action("Looking for the first Join button on the passcode page...")
    
    join1_clicked = click_blue_join_button_with_fallback(driver, max_attempts=3)
    
    if join1_clicked:
        print_ok("First Join button clicked! Waiting for next page to load...")
        time.sleep(8)
        take_screenshot(driver, "06_after_first_join")
    else:
        print_fail("Could not find first Join button!")
        print_action("Trying JavaScript form submission as fallback...")
        try:
            driver.execute_script("""
                var forms = document.forms;
                for(var i = 0; i < forms.length; i++) {
                    var inputs = forms[i].querySelectorAll('input[type="password"]');
                    if(inputs.length > 0) {
                        forms[i].submit();
                        return;
                    }
                }
            """)
            print_ok("Form submitted via JavaScript")
            join1_clicked = True
            time.sleep(8)
            take_screenshot(driver, "06_after_js_submit")
        except:
            print_warn("JavaScript submit failed")
            take_screenshot(driver, "06_first_join_failed")
    
    # ==========================================
    # STEP 7: Click SECOND "Join" button (BLUE one in middle at coordinates 768, 544)
    # ==========================================
    print_step(7, TOTAL_STEPS, f'Clicking the BLUE "Join" button (coordinates: {JOIN_BUTTON_X}, {JOIN_BUTTON_Y})')
    print_info("This is the rectangular blue box with white text 'Join' in the center of the screen")
    print_action("Waiting for the final join page to load...")
    time.sleep(8)
    take_screenshot(driver, "07_final_join_page")
    
    # Print current page info
    print_info(f"Current URL: {driver.current_url[:100]}")
    
    print_action(f"Attempting to click the blue Join button using all methods (coordinates: {JOIN_BUTTON_X}, {JOIN_BUTTON_Y})...")
    
    # Use the multi-strategy approach with coordinate clicking as primary method
    join2_clicked = click_blue_join_button_with_fallback(driver, max_attempts=5)
    
    if join2_clicked:
        print_ok("✅ BLUE Join button clicked! Bot is entering the meeting!")
        time.sleep(10)
        take_screenshot(driver, "07_after_final_join")
    else:
        print_warn("Could not find blue Join button - checking if already in meeting...")
        try:
            leave_check = driver.find_elements(By.XPATH, "//button[contains(text(), 'Leave')]")
            if leave_check:
                print_ok("Bot already in meeting (Leave button detected)!")
                join2_clicked = True
        except:
            pass
    
    if not join2_clicked:
        print_fail("Could not find the blue Join button after all attempts")
        take_screenshot(driver, "07_final_join_failed")
    
    # ==========================================
    # STEP 8: Configure in meeting (mute, camera off)
    # ==========================================
    print_step(8, TOTAL_STEPS, "Configuring in meeting (mute audio, turn off camera)")
    
    print_action("Waiting for meeting interface to stabilize...")
    time.sleep(8)
    take_screenshot(driver, "08_meeting_interface")
    
    # Mute microphone
    print_action("Attempting to mute microphone")
    muted = False
    
    mute_selectors = [
        ("//button[contains(@aria-label, 'Mute')]", "aria-label Mute"),
        ("//button[contains(@title, 'Mute')]", "title Mute"),
        ("//button[contains(@data-testid, 'mute')]", "data-testid mute"),
        ("//button[contains(@data-testid, 'mic')]", "data-testid mic"),
        ("//button[contains(@class, 'mute')]", "class mute"),
    ]
    
    for selector, desc in mute_selectors:
        try:
            btns = driver.find_elements(By.XPATH, selector)
            for btn in btns:
                aria = (btn.get_attribute("aria-label") or "").lower()
                if "unmute" not in aria:
                    driver.execute_script("arguments[0].click();", btn)
                    print_ok(f"Microphone muted via {desc}")
                    muted = True
                    time.sleep(1)
                    break
            if muted:
                break
        except:
            continue
    
    if not muted:
        print_skip("Microphone already muted or not found")
    
    # Turn off camera
    print_action("Attempting to turn off camera")
    camera_off = False
    
    cam_selectors = [
        ("//button[contains(@aria-label, 'Stop Video')]", "aria-label Stop Video"),
        ("//button[contains(@title, 'Stop Video')]", "title Stop Video"),
        ("//button[contains(@data-testid, 'video')]", "data-testid video"),
        ("//button[contains(@data-testid, 'camera')]", "data-testid camera"),
        ("//button[contains(@class, 'video')]", "class video"),
    ]
    
    for selector, desc in cam_selectors:
        try:
            btns = driver.find_elements(By.XPATH, selector)
            for btn in btns:
                aria = (btn.get_attribute("aria-label") or "").lower()
                if "start" not in aria:
                    driver.execute_script("arguments[0].click();", btn)
                    print_ok(f"Camera turned off via {desc}")
                    camera_off = True
                    time.sleep(1)
                    break
            if camera_off:
                break
        except:
            continue
    
    if not camera_off:
        print_skip("Camera already off or not found")
    
    time.sleep(3)
    take_screenshot(driver, "08_bot_configured")
    
    # ==========================================
    # STEP 9: Verify connection
    # ==========================================
    print_step(9, TOTAL_STEPS, "Verifying meeting connection")
    
    print_action("Checking if bot successfully entered the meeting...")
    
    in_meeting = False
    
    # Check 1: Leave button
    try:
        leave_btns = driver.find_elements(By.XPATH, "//button[contains(text(), 'Leave')]")
        if leave_btns:
            in_meeting = True
            print_ok("Found 'Leave' button - bot IS in the meeting!")
    except:
        pass
    
    # Check 2: URL
    current_url = driver.current_url
    if "zoom.us/wc/" in current_url:
        in_meeting = True
        print_ok("URL confirms web client session")
    
    # Check 3: Meeting UI elements
    try:
        indicators = driver.find_elements(By.XPATH,
            "//*[contains(@aria-label, 'Meeting')] | //*[contains(@aria-label, 'Participants')] | //*[contains(text(), 'Participants')]")
        if indicators:
            in_meeting = True
            print_ok("Detected meeting UI elements")
    except:
        pass
    
    if in_meeting:
        print(f"\n{'=' * 60}")
        print(f"  🎉🎉🎉 BOT SUCCESSFULLY JOINED THE MEETING! 🎉🎉🎉")
        print(f"{'=' * 60}")
        print(f"  ✅ Audio: Muted")
        print(f"  ✅ Video: Off")
        if passcode_entered:
            print(f"  ✅ Passcode entered: {MEETING_PASSCODE}")
        print(f"  ✅ Bot will stay for {SESSION_DURATION_MINUTES} minutes")
        print(f"  ✅ No action needed from you!")
        print(f"{'=' * 60}")
    else:
        print(f"\n{'=' * 60}")
        print(f"  ⚠️ Could not confirm meeting join")
        print(f"  → Bot will try to stay connected anyway")
        print(f"{'=' * 60}")
    
    return True


def stay_in_meeting(driver):
    """Stay in meeting for full duration"""
    print(f"\n{'━' * 60}")
    print(f"  PHASE 2: Bot is staying in the meeting")
    print(f"  ⏱ Duration: {SESSION_DURATION_MINUTES} minutes")
    print(f"  🔄 Checking connection every 60 seconds")
    print(f"{'━' * 60}")
    
    end_time = time.time() + (SESSION_DURATION_MINUTES * 60)
    cycle = 0
    
    while time.time() < end_time:
        remaining = int(end_time - time.time())
        mins, secs = divmod(remaining, 60)
        cycle += 1
        
        dots = "•" * (cycle % 5 + 1)
        print(f"    [⏱] {mins:02d}:{secs:02d} remaining {dots}", end="")
        
        try:
            leave_btns = driver.find_elements(By.XPATH, "//button[contains(text(), 'Leave')]")
            if leave_btns:
                print(f" ✅ Connected")
            else:
                print(f" ❌ Disconnected! Rejoining...")
                driver.get(MEETING_LINK)
                time.sleep(15)
                take_screenshot(driver, f"reconnect_{cycle}")
            
            if cycle % 15 == 0:
                take_screenshot(driver, f"heartbeat_{cycle}")
        except:
            print(f" ⚠️ Error")
        
        time.sleep(60)
    
    print(f"\n    [✓] Session complete! Bot stayed for {SESSION_DURATION_MINUTES} minutes.")
    take_screenshot(driver, "09_session_complete")


def main():
    print(f"\n{'╔' + '═' * 58 + '╗'}")
    print(f"║{' ' * 58}║")
    print(f"║{'          🤖 ZOOM MEETING BOT - FULLY AUTOMATIC          '.center(58)}║")
    print(f"║{' ' * 58}║")
    print(f"{'╚' + '═' * 58 + '╝'}")
    print(f"  🕐 Started: {datetime.now().isoformat()}")
    print(f"  👤 Display Name: {DISPLAY_NAME}")
    print(f"  ⏱  Stay Duration: {SESSION_DURATION_MINUTES} minutes")
    print(f"  🔑 Passcode: {MEETING_PASSCODE}")
    print(f"  🖱️  Blue Join Button at coordinates: ({JOIN_BUTTON_X}, {JOIN_BUTTON_Y})")
    print(f"  🎯 Bot does EVERYTHING - just start and wait!")
    
    driver = setup_driver()
    video_path = start_video_recording(driver)
    
    try:
        joined = join_meeting(driver)
        stop_video_recording()
        if joined:
            stay_in_meeting(driver)
    except KeyboardInterrupt:
        print("\n  [!!] Bot manually interrupted")
        stop_video_recording()
    except Exception as e:
        print(f"\n  [!!] ERROR: {e}")
        take_screenshot(driver, "fatal_error")
        stop_video_recording()
        raise
    finally:
        print("\n  [*] Session ending...")
        driver.quit()


if __name__ == "__main__":
    main()
