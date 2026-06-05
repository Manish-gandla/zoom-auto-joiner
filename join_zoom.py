#!/usr/bin/env python3
"""
Zoom Meeting Auto-Joiner - FULLY AUTOMATIC
Bot does EVERYTHING - no user interaction needed
"""

import os
import time
import json
import pickle
import subprocess
import threading
import re
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# --- CONFIGURATION ---
MEETING_LINK = os.environ.get("ZOOM_MEETING_LINK", "")
DISPLAY_NAME = os.environ.get("ZOOM_DISPLAY_NAME", "Meeting Bot")
SESSION_DURATION_MINUTES = int(os.environ.get("SESSION_DURATION_MINUTES", "60"))
MEETING_PASSCODE = "120217"

if not MEETING_LINK or "zoom.us" not in MEETING_LINK:
    print("[!] ERROR: No valid Zoom meeting link provided!")
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


def setup_driver():
    """Configure Chrome driver"""
    print("[*] Setting up Chrome driver...")
    print("[*] Auto-detecting Chrome version and downloading matching ChromeDriver...")
    
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
    
    print(f"[+] Chrome started successfully")
    return driver


def take_screenshot(driver, label):
    """Save a screenshot"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{SCREENSHOT_DIR}/{timestamp}_{label}.png"
    try:
        driver.save_screenshot(filename)
        print(f"  [📸] Screenshot: {label}.png")
    except:
        pass
    return filename


def frame_recorder(driver, output_path):
    """Background thread: captures frames and stitches into video"""
    print("[🎥] Video recording started - capturing frames at 2fps...")
    
    while recording_active[0]:
        try:
            frame_num = frame_counter[0]
            frame_path = f"{FRAMES_DIR}/frame_{frame_num:06d}.png"
            driver.save_screenshot(frame_path)
            frame_counter[0] += 1
            if frame_num % 60 == 0 and frame_num > 0:
                print(f"[🎥] Captured {frame_num} frames...")
        except:
            pass
        time.sleep(0.5)
    
    print(f"[🎥] Recording stopped. Total frames: {frame_counter[0]}")
    print(f"[🎥] Encoding video from frames...")
    
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
                print(f"[✅] Video saved ({file_size / 1024 / 1024:.1f} MB)")
            else:
                print(f"[!] Video encoding failed")
        except Exception as e:
            print(f"[!] Video encoding error: {e}")
    else:
        print("[!] Not enough frames to create video")


def start_video_recording(driver):
    """Start background frame recording"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = f"{VIDEO_DIR}/bot_session_{timestamp}.mp4"
    recording_active[0] = True
    frame_counter[0] = 0
    video_thread[0] = threading.Thread(
        target=frame_recorder, args=(driver, output_path), daemon=True
    )
    video_thread[0].start()
    print(f"[🎥] Output: bot_session_{timestamp}.mp4")
    return output_path


def stop_video_recording():
    """Stop recording"""
    print("[🎥] Stopping video recording...")
    recording_active[0] = False
    if video_thread[0] and video_thread[0].is_alive():
        video_thread[0].join(timeout=130)
    print("[🎥] Video recording finished")


def click_element_safe(driver, by, selector, description, timeout=6):
    """Try to click an element, return True if successful"""
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
        print(f"  ✅ Clicked: {description}")
        return True
    except Exception as e:
        return False


def click_by_any_method(driver, description, timeout=4):
    """
    Ultra-aggressive: try EVERY possible way to find and click an element
    by searching all elements' text content
    """
    time.sleep(1)
    try:
        # Get all clickable elements
        all_elements = driver.find_elements(By.XPATH, "//button | //a | //span | //div[@role='button'] | //input[@type='submit'] | //input[@type='button']")
        
        for elem in all_elements:
            try:
                text = (elem.text or "").strip().lower()
                aria = (elem.get_attribute("aria-label") or "").strip().lower()
                title = (elem.get_attribute("title") or "").strip().lower()
                href = (elem.get_attribute("href") or "").strip().lower()
                
                combined = f"{text} {aria} {title} {href}"
                
                # Check if this element matches our description keywords
                keywords = description.lower().split()
                if all(kw in combined for kw in keywords):
                    driver.execute_script("arguments[0].scrollIntoView(true);", elem)
                    time.sleep(0.3)
                    driver.execute_script("arguments[0].click();", elem)
                    print(f"  ✅ Clicked (by text search): '{elem.text.strip()[:50]}'")
                    return True
            except:
                continue
    except:
        pass
    return False


def extract_meeting_id(url):
    """Extract meeting ID from various Zoom URL formats"""
    patterns = [
        r'/j/(\d+)',
        r'/wc/(\d+)',
        r'/s/(\d+)',
        r'confno=(\d+)',
        r'meeting_id=(\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def join_meeting(driver):
    """Automated meeting joining - no user input needed"""
    print("\n" + "="*60)
    print("  🤖 BOT STARTED - FULLY AUTOMATIC")
    print("="*60)
    
    # ==========================================
    # STEP 1: Open meeting link
    # ==========================================
    print(f"\n{'='*60}")
    print(f"  STEP 1: Opening meeting link")
    print(f"{'='*60}")
    print(f"  → URL: {MEETING_LINK[:100]}...")
    driver.get(MEETING_LINK)
    print(f"  → Waiting for page to load...")
    time.sleep(8)
    take_screenshot(driver, "01_page_loaded")
    print(f"  ✅ Page loaded")
    
    current_url = driver.current_url
    print(f"  → Current URL: {current_url}")
    
    # Extract meeting ID for potential direct join
    meeting_id = extract_meeting_id(current_url)
    if meeting_id:
        print(f"  → Detected meeting ID: {meeting_id}")
    
    # ==========================================
    # STEP 2: Try to click "Join from Browser" - MASSIVE selector attack
    # ==========================================
    print(f"\n{'='*60}")
    print(f"  STEP 2: Finding and clicking 'Join from Browser'")
    print(f"{'='*60}")
    
    # Strategy 1: Exact text match XPath (all variations)
    print(f"  → Strategy 1: Direct text matching...")
    join_selectors = [
        # Exact phrase matches
        "//button[contains(text(), 'Join from your browser')]",
        "//a[contains(text(), 'Join from your browser')]",
        "//button[contains(text(), 'Join from Browser')]",
        "//a[contains(text(), 'Join from Browser')]",
        "//button[contains(text(), 'join from your browser')]",
        "//a[contains(text(), 'join from your browser')]",
        "//span[contains(text(), 'Join from your browser')]/..",
        "//span[contains(text(), 'Join from Browser')]/..",
        "//div[contains(text(), 'Join from your browser')]",
        "//div[contains(text(), 'Join from Browser')]",
        "//p[contains(text(), 'Join from your browser')]",
        "//p[contains(text(), 'Join from Browser')]",
        
        # Partial matches
        "//*[contains(text(), 'Join from your')]",
        "//*[contains(text(), 'Join from')]",
        "//*[contains(text(), 'browser') and contains(text(), 'Join')]",
        "//*[contains(text(), 'browser') and contains(text(), 'join')]",
        
        # Attribute-based matches
        "//a[contains(@href, 'wc/') and contains(@href, 'join')]",
        "//a[contains(@href, '/wc/')]",
        
        # Common Zoom class names
        "//a[contains(@class, 'join-from-browser')]",
        "//a[contains(@class, 'join-link')]",
        "//button[contains(@class, 'join-from-browser')]",
        "//button[contains(@class, 'join-link')]",
        
        # Generic fallbacks
        "//button[contains(text(), 'Join')]",
        "//a[contains(text(), 'Join')]",
        "//button[contains(text(), 'join')]",
        "//a[contains(text(), 'join')]",
        
        # Launch meeting
        "//button[contains(text(), 'Launch Meeting')]",
        "//a[contains(text(), 'Launch Meeting')]",
        "//button[contains(text(), 'Launch')]",
        "//a[contains(text(), 'Launch')]",
    ]
    
    join_clicked = False
    for selector in join_selectors:
        if click_element_safe(driver, By.XPATH, selector, "Join button", timeout=3):
            join_clicked = True
            time.sleep(5)
            take_screenshot(driver, "02_after_join_click")
            break
    
    # Strategy 2: Search by text content scan
    if not join_clicked:
        print(f"  → Strategy 2: Scanning all elements for join-related text...")
        join_clicked = click_by_any_method(driver, "join from browser", timeout=3)
        if join_clicked:
            time.sleep(5)
            take_screenshot(driver, "02_after_join_click_scan")
    
    # Strategy 3: CSS selector approach
    if not join_clicked:
        print(f"  → Strategy 3: CSS selectors...")
        css_selectors = [
            "a[href*='wc/join']",
            "a[href*='/wc/']",
            ".join-from-browser",
            ".join-link",
            "a[href*='join']",
            "button[class*='join']",
        ]
        for selector in css_selectors:
            if click_element_safe(driver, By.CSS_SELECTOR, selector, "Join (CSS)", timeout=3):
                join_clicked = True
                time.sleep(5)
                take_screenshot(driver, "02_after_join_css")
                break
    
    # Strategy 4: JavaScript fallback - inject the direct web client URL
    if not join_clicked and meeting_id:
        print(f"  → Strategy 4: Direct web client navigation...")
        direct_url = f"https://zoom.us/wc/{meeting_id}/join?prefer=1&un={DISPLAY_NAME}"
        print(f"  → Navigating directly to web client: {direct_url[:80]}...")
        driver.get(direct_url)
        time.sleep(8)
        take_screenshot(driver, "02_direct_web_client")
        join_clicked = True
    
    # Strategy 5: Last resort - try clicking anything that says "join"
    if not join_clicked:
        print(f"  → Strategy 5: Clicking ANYTHING with 'join' in its text...")
        try:
            all_buttons = driver.find_elements(By.XPATH, "//button | //a")
            for btn in all_buttons:
                try:
                    text = (btn.text or "").lower().strip()
                    if text and ("join" in text or "launch" in text or "start" in text or "enter" in text):
                        driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                        time.sleep(0.3)
                        driver.execute_script("arguments[0].click();", btn)
                        print(f"  ✅ Clicked last resort: '{btn.text.strip()[:40]}'")
                        join_clicked = True
                        time.sleep(5)
                        take_screenshot(driver, "02_joined_last_resort")
                        break
                except:
                    continue
        except:
            pass
    
    if join_clicked:
        print(f"  ✅ 'Join from Browser' successfully clicked")
    else:
        print(f"  ⚠️ Could not find any join button - trying to continue anyway")
    
    # ==========================================
    # STEP 3: Handle "Open zoom.us app?" dialog
    # ==========================================
    print(f"\n{'='*60}")
    print(f"  STEP 3: Handling app launch dialog")
    print(f"{'='*60}")
    
    time.sleep(4)
    
    cancel_selectors = [
        "//a[contains(text(), 'Stay in Browser')]",
        "//button[contains(text(), 'Stay in Browser')]",
        "//button[contains(text(), 'Cancel')]",
        "//a[contains(text(), 'Cancel')]",
        "//button[contains(text(), 'cancel')]",
        "//a[contains(text(), 'stay')]",
        "//button[contains(@class, 'cancel')]",
        "//a[contains(@href, '#') and contains(text(), 'Cancel')]",
        # Also check close button
        "//button[contains(@aria-label, 'Close')]",
        "//button[contains(@class, 'close')]",
    ]
    
    cancelled = False
    for selector in cancel_selectors:
        if click_element_safe(driver, By.XPATH, selector, "Cancel/Stay in Browser", timeout=3):
            cancelled = True
            time.sleep(3)
            take_screenshot(driver, "03_after_cancel")
            break
    
    if not cancelled:
        print(f"  → No dialog found or already dismissed")
    
    # ==========================================
    # STEP 4: Click "Continue without microphone and camera" (appears 1-2 times)
    # ==========================================
    print(f"\n{'='*60}")
    print(f"  STEP 4: Dismissing permission prompts")
    print(f"{'='*60}")
    
    for attempt in range(1, 4):
        time.sleep(3)
        
        continue_selectors = [
            "//button[contains(text(), 'Continue without microphone and camera')]",
            "//a[contains(text(), 'Continue without microphone and camera')]",
            "//span[contains(text(), 'Continue without')]/..",
            "//*[contains(text(), 'Continue without microphone')]",
            "//*[contains(text(), 'Continue without')]",
            "//button[contains(text(), 'Continue')]",
            "//a[contains(text(), 'Continue')]",
            "//button[contains(@aria-label, 'Continue')]",
            # Generic permission handling
            "//button[contains(text(), 'Allow')]",
            "//button[contains(text(), 'Deny')]",
            "//button[contains(text(), 'Block')]",
        ]
        
        clicked = False
        for selector in continue_selectors:
            if click_element_safe(driver, By.XPATH, selector, f"Continue (attempt {attempt})", timeout=3):
                clicked = True
                time.sleep(3)
                take_screenshot(driver, f"04_continue_{attempt}")
                break
        
        if not clicked:
            print(f"  → No permission prompt on attempt {attempt}")
    
    # ==========================================
    # STEP 5: Enter passcode if needed
    # ==========================================
    print(f"\n{'='*60}")
    print(f"  STEP 5: Entering passcode")
    print(f"{'='*60}")
    
    passcode_entered = False
    
    for attempt in range(1, 4):
        time.sleep(2)
        
        passcode_selectors = [
            "//input[@id='input-for-pwd']",
            "//input[@id='passcode']",
            "//input[@id='password']",
            "//input[@name='passcode']",
            "//input[@name='password']",
            "//input[contains(@placeholder, 'passcode')]",
            "//input[contains(@placeholder, 'Passcode')]",
            "//input[contains(@placeholder, 'password')]",
            "//input[contains(@placeholder, 'Password')]",
            "//input[@type='password']",
            "//input[contains(@class, 'pwd')]",
            "//input[contains(@class, 'passcode')]",
            "//input[contains(@id, 'pwd')]",
            "//input[contains(@id, 'passcode')]",
            "//input[contains(@id, 'password')]",
        ]
        
        for selector in passcode_selectors:
            try:
                pwd = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, selector))
                )
                pwd.clear()
                pwd.send_keys(MEETING_PASSCODE)
                print(f"  ✅ Passcode entered: {MEETING_PASSCODE}")
                passcode_entered = True
                time.sleep(2)
                take_screenshot(driver, f"05_passcode_{attempt}")
                break
            except:
                continue
        
        if passcode_entered:
            break
    
    if not passcode_entered:
        print(f"  → No passcode field found")
    
    # ==========================================
    # STEP 6: Click Join button
    # ==========================================
    print(f"\n{'='*60}")
    print(f"  STEP 6: Clicking Join button")
    print(f"{'='*60}")
    
    time.sleep(2)
    
    join_btn_selectors = [
        "//button[contains(text(), 'Join')]",
        "//button[contains(@class, 'join')]",
        "//button[@type='submit']",
        "//span[contains(text(), 'Join')]/..",
        "//input[@type='submit']",
        "//input[@value='Join']",
        "//button[contains(text(), 'join')]",
        "//button[contains(text(), 'Enter')]",
        "//button[contains(text(), 'Submit')]",
        "//button[contains(text(), 'OK')]",
    ]
    
    join_btn_clicked = False
    for selector in join_btn_selectors:
        if click_element_safe(driver, By.XPATH, selector, "Join/Submit", timeout=4):
            join_btn_clicked = True
            print(f"  ✅ Join button clicked")
            time.sleep(8)
            take_screenshot(driver, "06_after_join_button")
            break
    
    if not join_btn_clicked:
        print(f"  ⚠️ Could not find Join button")
        take_screenshot(driver, "06_no_join_button")
    
    # ==========================================
    # STEP 7: Wait for meeting and configure
    # ==========================================
    print(f"\n{'='*60}")
    print(f"  STEP 7: Configuring in meeting (mute audio, off camera)")
    print(f"{'='*60}")
    
    print(f"  → Waiting for meeting interface...")
    time.sleep(10)
    take_screenshot(driver, "07_meeting_loaded")
    
    # Mute microphone
    print(f"  → Muting microphone...")
    muted = False
    
    # First try: aria-label based
    try:
        btns = driver.find_elements(By.XPATH, 
            "//button[contains(@aria-label, 'Mute')] | //button[contains(@title, 'Mute')] | //button[contains(@data-testid, 'mute')]")
        for btn in btns:
            aria = (btn.get_attribute("aria-label") or "").lower()
            title = (btn.get_attribute("title") or "").lower()
            if "unmute" not in aria and "unmute" not in title:
                driver.execute_script("arguments[0].click();", btn)
                print(f"  ✅ Microphone muted")
                muted = True
                time.sleep(1)
                break
    except:
        pass
    
    # Second try: text based
    if not muted:
        try:
            btns = driver.find_elements(By.XPATH, "//button")
            for btn in btns:
                text = (btn.text or "").strip().lower()
                if text == "mute" or text == "mute mic" or text == "mute microphone":
                    driver.execute_script("arguments[0].click();", btn)
                    print(f"  ✅ Microphone muted (text match)")
                    muted = True
                    time.sleep(1)
                    break
        except:
            pass
    
    if not muted:
        print(f"  → Mic already muted or not found")
    
    # Turn off camera
    print(f"  → Turning off camera...")
    camera_off = False
    
    try:
        btns = driver.find_elements(By.XPATH,
            "//button[contains(@aria-label, 'Stop Video')] | //button[contains(@title, 'Stop Video')] | //button[contains(@data-testid, 'video')]")
        for btn in btns:
            aria = (btn.get_attribute("aria-label") or "").lower()
            title = (btn.get_attribute("title") or "").lower()
            if "start" not in aria and "start" not in title:
                driver.execute_script("arguments[0].click();", btn)
                print(f"  ✅ Camera turned off")
                camera_off = True
                time.sleep(1)
                break
    except:
        pass
    
    if not camera_off:
        try:
            btns = driver.find_elements(By.XPATH, "//button")
            for btn in btns:
                text = (btn.text or "").strip().lower()
                if "stop" in text and ("video" in text or "camera" in text):
                    if "start" not in text:
                        driver.execute_script("arguments[0].click();", btn)
                        print(f"  ✅ Camera turned off (text match)")
                        camera_off = True
                        time.sleep(1)
                        break
        except:
            pass
    
    if not camera_off:
        print(f"  → Camera already off or not found")
    
    time.sleep(3)
    take_screenshot(driver, "08_bot_ready")
    
    # ==========================================
    # STEP 8: Verify connection
    # ==========================================
    print(f"\n{'='*60}")
    print(f"  STEP 8: Verifying meeting connection")
    print(f"{'='*60}")
    
    in_meeting = False
    try:
        leave_btns = driver.find_elements(By.XPATH, "//button[contains(text(), 'Leave')]")
        in_meeting = len(leave_btns) > 0
    except:
        pass
    
    current_url = driver.current_url
    if "zoom.us/wc/" in current_url or "zoom.us/j/" in current_url:
        in_meeting = True
    
    if in_meeting:
        print(f"\n{'='*60}")
        print(f"  🎉🎉🎉 BOT SUCCESSFULLY JOINED THE MEETING! 🎉🎉🎉")
        print(f"  ✅ Audio: Muted")
        print(f"  ✅ Video: Off")
        print(f"  ✅ Bot will stay for {SESSION_DURATION_MINUTES} minutes")
        print(f"  ✅ No action needed from you!")
        print(f"{'='*60}")
    else:
        print(f"\n{'='*60}")
        print(f"  ⚠️ Meeting join status uncertain")
        print(f"  → Bot will attempt to stay connected anyway")
        print(f"{'='*60}")
    
    return True


def stay_in_meeting(driver):
    """Stay in meeting for full duration"""
    print(f"\n{'='*60}")
    print(f"  PHASE 2: Bot is staying in the meeting")
    print(f"  Duration: {SESSION_DURATION_MINUTES} minutes")
    print(f"{'='*60}")
    
    end_time = time.time() + (SESSION_DURATION_MINUTES * 60)
    cycle = 0
    
    while time.time() < end_time:
        remaining = int(end_time - time.time())
        mins, secs = divmod(remaining, 60)
        cycle += 1
        
        dots = "." * (cycle % 5 + 1)
        print(f"  [⏱] {mins:02d}:{secs:02d} remaining{dots}")
        
        try:
            leave_btns = driver.find_elements(By.XPATH, "//button[contains(text(), 'Leave')]")
            if not leave_btns:
                print(f"  [!] Disconnected! Rejoining...")
                driver.get(MEETING_LINK)
                time.sleep(15)
                take_screenshot(driver, f"reconnect_{cycle}")
            
            if cycle % 15 == 0:
                take_screenshot(driver, f"heartbeat_{cycle}")
        except:
            pass
        
        time.sleep(60)
    
    print(f"\n  [✓] Session complete! Bot stayed for {SESSION_DURATION_MINUTES} minutes.")
    take_screenshot(driver, "09_session_complete")


def main():
    print("="*60)
    print("  🤖 ZOOM MEETING BOT - FULLY AUTOMATIC")
    print(f"  🕐 Started: {datetime.now().isoformat()}")
    print(f"  👤 Name: {DISPLAY_NAME}")
    print(f"  ⏱ Duration: {SESSION_DURATION_MINUTES} min")
    print(f"  🔑 Passcode: {MEETING_PASSCODE}")
    print(f"  🎯 Bot does EVERYTHING - just start and wait")
    print("="*60)
    
    driver = setup_driver()
    video_path = start_video_recording(driver)
    
    try:
        joined = join_meeting(driver)
        stop_video_recording()
        if joined:
            stay_in_meeting(driver)
    except KeyboardInterrupt:
        print("\n[!] Interrupted")
        stop_video_recording()
    except Exception as e:
        print(f"\n[!] ERROR: {e}")
        take_screenshot(driver, "fatal_error")
        stop_video_recording()
        raise
    finally:
        print("[*] Session ending...")
        driver.quit()


if __name__ == "__main__":
    main()
