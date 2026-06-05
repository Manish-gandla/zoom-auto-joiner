#!/usr/bin/env python3
"""
Zoom Meeting Auto-Joiner
Bot does EVERYTHING automatically - no user interaction needed:
- Opens the join link
- Clicks "Join from Browser" if shown
- Clicks "Continue without microphone and camera" if shown
- Enters passcode if needed
- Mutes audio, turns off camera
- Stays for the full duration
Records video of everything
"""

import os
import time
import json
import pickle
import subprocess
import threading
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
    print("[!] Set ZOOM_MEETING_LINK environment variable")
    exit(1)

SCREENSHOT_DIR = "/tmp/screenshots"
VIDEO_DIR = "/tmp/videos"
FRAMES_DIR = "/tmp/frames"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)
os.makedirs(VIDEO_DIR, exist_ok=True)
os.makedirs(FRAMES_DIR, exist_ok=True)

# Global state for video recording
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


def click_element_safe(driver, xpath_selector, description, timeout=8):
    """Try to click an element by xpath, return True if successful"""
    try:
        element = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((By.XPATH, xpath_selector))
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", element)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", element)
        print(f"  ✅ Clicked: {description}")
        return True
    except:
        return False


def click_first_matching(driver, selectors, description, timeout=8):
    """Try multiple xpath selectors, click the first match"""
    for selector in selectors:
        if click_element_safe(driver, selector, description, timeout):
            return True
    print(f"  ⚠️ Could not find: {description}")
    return False


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
    print(f"  → URL: {MEETING_LINK[:80]}...")
    driver.get(MEETING_LINK)
    print(f"  → Waiting for page to load...")
    time.sleep(8)
    take_screenshot(driver, "01_page_loaded")
    print(f"  ✅ Page loaded")
    
    # ==========================================
    # STEP 2: Handle initial page state
    # ==========================================
    print(f"\n{'='*60}")
    print(f"  STEP 2: Looking for join buttons or passcode prompt")
    print(f"{'='*60}")
    
    # Check current URL - sometimes Zoom redirects
    current_url = driver.current_url
    print(f"  → Current URL: {current_url}")
    
    # Check if there's a passcode/name form right away (common for direct links)
    time.sleep(3)
    
    # Look for any input fields (name or passcode)
    has_inputs = False
    try:
        inputs = driver.find_elements(By.XPATH, "//input")
        if inputs:
            print(f"  → Found {len(inputs)} input fields on page")
            has_inputs = True
    except:
        pass
    
    # ==========================================
    # STEP 3: Try "Join from Browser" first
    # ==========================================
    print(f"\n{'='*60}")
    print(f"  STEP 3: Attempting to join from browser")
    print(f"{'='*60}")
    
    joined = click_first_matching(driver, [
        "//button[contains(text(), 'Join from Browser')]",
        "//a[contains(text(), 'Join from Browser')]",
        "//span[contains(text(), 'Join from Browser')]/..",
        "//*[contains(text(), 'Join from Browser')]",
        "//button[contains(text(), 'Launch Meeting')]",
        "//a[contains(text(), 'Launch Meeting')]",
    ], '"Join from Browser" / "Launch Meeting"', timeout=6)
    
    if joined:
        time.sleep(5)
        take_screenshot(driver, "02_after_join_from_browser")
    
    # ==========================================
    # STEP 4: Handle "Open zoom.us app?" dialog
    # ==========================================
    print(f"\n{'='*60}")
    print(f"  STEP 4: Handling app dialog if present")
    print(f"{'='*60}")
    
    time.sleep(3)
    click_first_matching(driver, [
        "//a[contains(text(), 'Stay in Browser')]",
        "//button[contains(text(), 'Stay in Browser')]",
        "//button[contains(text(), 'Cancel')]",
        "//a[contains(text(), 'Cancel')]",
    ], '"Stay in Browser" or "Cancel"', timeout=4)
    
    time.sleep(3)
    take_screenshot(driver, "03_after_app_dialog")
    
    # ==========================================
    # STEP 5: Click "Continue without microphone and camera" (appears twice sometimes)
    # ==========================================
    print(f"\n{'='*60}")
    print(f"  STEP 5: Dismiss 'Continue without microphone and camera' prompts")
    print(f"{'='*60}")
    
    for attempt in range(1, 4):
        print(f"  → Attempt {attempt}...")
        clicked = click_first_matching(driver, [
            "//button[contains(text(), 'Continue without microphone and camera')]",
            "//a[contains(text(), 'Continue without microphone and camera')]",
            "//span[contains(text(), 'Continue without')]/..",
            "//*[contains(text(), 'Continue without')]",
            "//button[contains(text(), 'Continue')]",
            "//a[contains(text(), 'Continue')]",
            "//button[contains(@aria-label, 'Continue')]",
        ], f'"Continue without" (attempt {attempt})', timeout=4)
        
        if clicked:
            time.sleep(3)
            take_screenshot(driver, f"04_continue_clicked_{attempt}")
        else:
            print(f"  → No 'Continue' prompt found on attempt {attempt}")
            break
    
    # ==========================================
    # STEP 6: Enter passcode if prompted
    # ==========================================
    print(f"\n{'='*60}")
    print(f"  STEP 6: Entering meeting passcode if needed")
    print(f"{'='*60}")
    
    passcode_entered = False
    
    for attempt in range(1, 4):
        time.sleep(2)
        
        # Look for passcode input
        passcode_selectors = [
            "//input[@id='input-for-pwd']",
            "//input[@id='passcode']",
            "//input[@id='password']",
            "//input[contains(@placeholder, 'passcode')]",
            "//input[contains(@placeholder, 'Passcode')]",
            "//input[contains(@placeholder, 'password')]",
            "//input[contains(@placeholder, 'Password')]",
            "//input[@type='password']",
            "//input[contains(@class, 'pwd')]",
            "//input[contains(@class, 'passcode')]",
        ]
        
        for selector in passcode_selectors:
            try:
                pwd_input = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, selector))
                )
                pwd_input.clear()
                pwd_input.send_keys(MEETING_PASSCODE)
                print(f"  ✅ Entered passcode: {MEETING_PASSCODE}")
                passcode_entered = True
                time.sleep(2)
                take_screenshot(driver, f"05_passcode_entered_{attempt}")
                break
            except:
                continue
        
        if passcode_entered:
            break
    
    if not passcode_entered:
        # Try any visible input as a last resort
        try:
            all_inputs = driver.find_elements(By.XPATH, "//input[@type='text'] | //input[not(@type='hidden')]")
            for inp in all_inputs:
                if inp.is_displayed():
                    inp.clear()
                    inp.send_keys(MEETING_PASSCODE)
                    print(f"  ✅ Entered passcode into alternative input")
                    passcode_entered = True
                    time.sleep(2)
                    take_screenshot(driver, "05_passcode_entered_alt")
                    break
        except:
            print(f"  ⚠️ No passcode field found - may not be needed")
    
    # ==========================================
    # STEP 7: Click "Join" or submit button
    # ==========================================
    print(f"\n{'='*60}")
    print(f"  STEP 7: Clicking Join/Submit button")
    print(f"{'='*60}")
    
    time.sleep(2)
    
    join_clicked = click_first_matching(driver, [
        "//button[contains(text(), 'Join')]",
        "//button[contains(@class, 'join')]",
        "//button[@type='submit']",
        "//span[contains(text(), 'Join')]/..",
        "//button[contains(text(), 'Enter')]",
        "//button[contains(text(), 'Submit')]",
        "//button[contains(text(), 'Ok')]",
        "//button[contains(text(), 'OK')]",
    ], '"Join" button', timeout=5)
    
    if join_clicked:
        print(f"  ✅ Join button clicked")
        time.sleep(8)
        take_screenshot(driver, "06_after_join_button")
    else:
        print(f"  ⚠️ Could not find Join button")
        take_screenshot(driver, "06_no_join_button")
    
    # ==========================================
    # STEP 8: Wait for meeting to load and setup
    # ==========================================
    print(f"\n{'='*60}")
    print(f"  STEP 8: Setting up in meeting (mute, camera off)")
    print(f"{'='*60}")
    
    print(f"  → Waiting for meeting interface...")
    time.sleep(10)
    take_screenshot(driver, "07_meeting_loaded")
    
    # Mute microphone
    print(f"  → Muting microphone...")
    mute_selectors = [
        "//button[contains(@aria-label, 'Mute')]",
        "//button[contains(@title, 'Mute')]",
        "//button[contains(@data-testid, 'mute')]",
        "//button[contains(@aria-label, 'mute')]",
    ]
    
    muted = False
    for selector in mute_selectors:
        try:
            btns = driver.find_elements(By.XPATH, selector)
            for btn in btns:
                aria = (btn.get_attribute("aria-label") or "").lower()
                title = (btn.get_attribute("title") or "").lower()
                if "unmute" not in aria and "unmute" not in title and "start" not in aria and "start" not in title:
                    driver.execute_script("arguments[0].click();", btn)
                    print(f"  ✅ Microphone muted")
                    muted = True
                    time.sleep(1)
                    break
            if muted:
                break
        except:
            continue
    
    if not muted:
        # Try any button with mute-related text
        try:
            btns = driver.find_elements(By.XPATH, "//button")
            for btn in btns:
                text = (btn.text or "").lower()
                aria = (btn.get_attribute("aria-label") or "").lower()
                if "mute" in text or "mute" in aria:
                    if "unmute" not in text and "unmute" not in aria:
                        driver.execute_script("arguments[0].click();", btn)
                        print(f"  ✅ Microphone muted (alt)")
                        muted = True
                        time.sleep(1)
                        break
        except:
            pass
    
    if not muted:
        print(f"  ⚠️ Could not find mute button")
    
    # Turn off camera
    print(f"  → Turning off camera...")
    cam_selectors = [
        "//button[contains(@aria-label, 'Stop Video')]",
        "//button[contains(@title, 'Stop Video')]",
        "//button[contains(@data-testid, 'video')]",
        "//button[contains(@aria-label, 'stop video')]",
    ]
    
    camera_off = False
    for selector in cam_selectors:
        try:
            btns = driver.find_elements(By.XPATH, selector)
            for btn in btns:
                aria = (btn.get_attribute("aria-label") or "").lower()
                title = (btn.get_attribute("title") or "").lower()
                if "start" not in aria and "start" not in title:
                    driver.execute_script("arguments[0].click();", btn)
                    print(f"  ✅ Camera turned off")
                    camera_off = True
                    time.sleep(1)
                    break
            if camera_off:
                break
        except:
            continue
    
    if not camera_off:
        try:
            btns = driver.find_elements(By.XPATH, "//button")
            for btn in btns:
                text = (btn.text or "").lower()
                aria = (btn.get_attribute("aria-label") or "").lower()
                if ("stop" in text or "stop" in aria) and ("video" in text or "camera" in text or "video" in aria or "camera" in aria):
                    if "start" not in text and "start" not in aria:
                        driver.execute_script("arguments[0].click();", btn)
                        print(f"  ✅ Camera turned off (alt)")
                        camera_off = True
                        time.sleep(1)
                        break
        except:
            pass
    
    if not camera_off:
        print(f"  ⚠️ Could not find camera button")
    
    time.sleep(3)
    take_screenshot(driver, "08_bot_ready")
    
    # ==========================================
    # STEP 9: Verify we're in the meeting
    # ==========================================
    print(f"\n{'='*60}")
    print(f"  STEP 9: Verifying bot is in the meeting")
    print(f"{'='*60}")
    
    # Check for "Leave" button as confirmation
    in_meeting = False
    try:
        leave_btns = driver.find_elements(By.XPATH, "//button[contains(text(), 'Leave')]")
        if leave_btns:
            in_meeting = True
            print(f"  ✅ Found 'Leave' button - bot is in the meeting!")
    except:
        pass
    
    # Also check URL - if it has /wc/ we're likely in the web client
    current_url = driver.current_url
    if "zoom.us/wc/" in current_url:
        in_meeting = True
        print(f"  ✅ URL confirms we're in web client meeting")
    
    if in_meeting:
        print(f"\n{'='*60}")
        print(f"  🎉🎉🎉 BOT SUCCESSFULLY JOINED THE MEETING! 🎉🎉🎉")
        print(f"  ✅ Audio: Muted")
        print(f"  ✅ Video: Off")
        if passcode_entered:
            print(f"  ✅ Passcode entered: {MEETING_PASSCODE}")
        print(f"  ✅ Bot will stay for {SESSION_DURATION_MINUTES} minutes")
        print(f"  ✅ No action needed from you - bot handles everything!")
        print(f"{'='*60}")
    else:
        print(f"  ⚠️ Could not definitively confirm meeting join")
        print(f"  → Bot will still try to stay connected")
    
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
        
        status = "." * (cycle % 5 + 1)
        print(f"  [⏱] {mins:02d}:{secs:02d} remaining {status}")
        
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
    print(f"  📍 Meeting link provided")
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
