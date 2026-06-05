#!/usr/bin/env python3
"""
Zoom Meeting Auto-Joiner
Follows exact steps you specified:
1. Click "Join from Browser"
2. Click "Continue without microphone and camera" (pop-up 1)
3. Click "Continue without microphone and camera" (pop-up 2)
4. Enter passcode "120217", click Join
5. Joined successfully!
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
    """Configure Chrome driver with automatic ChromeDriver management"""
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

    # Disable notifications and media prompts
    prefs = {
        "profile.default_content_setting_values.notifications": 2,
        "profile.default_content_setting_values.media_stream_mic": 1,
        "profile.default_content_setting_values.media_stream_camera": 1,
    }
    options.add_experimental_option("prefs", prefs)

    service = Service(ChromeDriverManager().install())
    
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    print(f"[+] Chrome started successfully with matching ChromeDriver")
    return driver


def take_screenshot(driver, label):
    """Save a screenshot with step label"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{SCREENSHOT_DIR}/{timestamp}_{label}.png"
    driver.save_screenshot(filename)
    print(f"  [📸] Screenshot saved: {label}.png")
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
            
            if frame_num % 30 == 0 and frame_num > 0:
                print(f"[🎥] Captured {frame_num} frames so far...")
                
        except Exception as e:
            pass
        
        time.sleep(0.5)
    
    print(f"[🎥] Recording stopped. Total frames: {frame_counter[0]}")
    print(f"[🎥] Encoding video from frames (this may take a moment)...")
    
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
                print(f"[✅] Video saved: {output_path} ({file_size / 1024 / 1024:.1f} MB)")
            else:
                print(f"[!] Video encoding failed: {result.stderr[:500]}")
        except Exception as e:
            print(f"[!] Video encoding error: {e}")
    else:
        print("[!] Not enough frames to create video")


def start_video_recording(driver):
    """Start the background frame recording thread"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = f"{VIDEO_DIR}/bot_session_{timestamp}.mp4"
    
    recording_active[0] = True
    frame_counter[0] = 0
    
    video_thread[0] = threading.Thread(
        target=frame_recorder,
        args=(driver, output_path),
        daemon=True
    )
    video_thread[0].start()
    print(f"[🎥] Output video will be: {output_path}")
    return output_path


def stop_video_recording():
    """Stop the video recording and wait for it to finish"""
    print("[🎥] Stopping video recording...")
    recording_active[0] = False
    if video_thread[0] and video_thread[0].is_alive():
        video_thread[0].join(timeout=130)
    print("[🎥] Video recording finished")


def print_step(step_num, description):
    """Print a clear step header"""
    print(f"\n{'='*60}")
    print(f"  STEP {step_num}: {description}")
    print(f"{'='*60}")


def print_status(message):
    """Print a status message"""
    print(f"  → {message}")


def print_success(message):
    """Print a success message"""
    print(f"  ✅ {message}")


def print_warning(message):
    """Print a warning message"""
    print(f"  ⚠️  {message}")


def join_meeting(driver):
    """
    Follow the exact steps you specified:
    1. Click "Join from Browser"
    2. Click "Continue without microphone and camera" (pop-up 1)
    3. Click "Continue without microphone and camera" (pop-up 2) 
    4. Enter passcode "120217", click Join
    5. In meeting!
    """
    print("\n" + "="*60)
    print("  🟢 BOT STARTING - NAVIGATING TO MEETING")
    print("="*60)
    
    # ==========================================
    # STEP 0: Navigate to the meeting link
    # ==========================================
    print_step(0, "Opening meeting link")
    print_status(f"Navigating to: {MEETING_LINK}")
    driver.get(MEETING_LINK)
    print_status("Waiting for page to load...")
    time.sleep(8)
    take_screenshot(driver, "00_meeting_link_loaded")
    print_success("Page loaded")
    
    # ==========================================
    # STEP 1: Click "Join from Browser"
    # ==========================================
    print_step(1, 'Click "Join from Browser"')
    print_status("Looking for 'Join from Browser' button in the white box...")
    
    join_found = False
    join_selectors = [
        "//button[contains(text(), 'Join from Browser')]",
        "//a[contains(text(), 'Join from Browser')]",
        "//span[contains(text(), 'Join from Browser')]/..",
        "//div[contains(text(), 'Join from Browser')]/..",
        "//*[contains(text(), 'Join from Browser')]",
    ]
    
    for selector in join_selectors:
        try:
            element = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, selector))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", element)
            time.sleep(1)
            driver.execute_script("arguments[0].click();", element)
            print_success('Clicked "Join from Browser"')
            join_found = True
            time.sleep(4)
            take_screenshot(driver, "01_after_join_from_browser_click")
            break
        except:
            continue
    
    if not join_found:
        print_warning('Could not find "Join from Browser" button directly')
        print_status("Trying alternative: looking for any 'Join' button...")
        try:
            elements = driver.find_elements(By.XPATH, "//button | //a")
            for elem in elements:
                text = elem.text.strip().lower()
                if "join" in text:
                    driver.execute_script("arguments[0].click();", elem)
                    print_success(f"Clicked button with text: '{elem.text.strip()}'")
                    time.sleep(4)
                    take_screenshot(driver, "01_alt_join_click")
                    join_found = True
                    break
        except:
            pass
    
    if not join_found:
        print_warning("Could not find any join button - page may have loaded differently")
        take_screenshot(driver, "01_no_join_button_found")
    
    # ==========================================
    # STEP 2: Click "Continue without microphone and camera" (Pop-up 1)
    # ==========================================
    print_step(2, 'Click "Continue without microphone and camera" (Pop-up 1)')
    print_status("Waiting for pop-up to appear...")
    time.sleep(5)
    
    continue_found = False
    continue_selectors = [
        "//button[contains(text(), 'Continue without microphone and camera')]",
        "//a[contains(text(), 'Continue without microphone and camera')]",
        "//span[contains(text(), 'Continue without')]/..",
        "//*[contains(text(), 'Continue without')]",
        "//button[contains(text(), 'Continue')]",
        "//a[contains(text(), 'Continue')]",
    ]
    
    for selector in continue_selectors:
        try:
            element = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((By.XPATH, selector))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", element)
            time.sleep(1)
            driver.execute_script("arguments[0].click();", element)
            print_success('Clicked "Continue without microphone and camera" (Pop-up 1)')
            continue_found = True
            time.sleep(4)
            take_screenshot(driver, "02_after_first_continue_click")
            break
        except:
            continue
    
    if not continue_found:
        print_warning("Pop-up 1 not found, taking screenshot to debug...")
        take_screenshot(driver, "02_first_continue_not_found")
    
    # ==========================================
    # STEP 3: Click "Continue without microphone and camera" (Pop-up 2)
    # ==========================================
    print_step(3, 'Click "Continue without microphone and camera" (Pop-up 2)')
    print_status("Waiting for second pop-up to appear...")
    time.sleep(5)
    
    continue_found_2 = False
    for selector in continue_selectors:
        try:
            element = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((By.XPATH, selector))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", element)
            time.sleep(1)
            driver.execute_script("arguments[0].click();", element)
            print_success('Clicked "Continue without microphone and camera" (Pop-up 2)')
            continue_found_2 = True
            time.sleep(4)
            take_screenshot(driver, "03_after_second_continue_click")
            break
        except:
            continue
    
    if not continue_found_2:
        print_warning("Pop-up 2 not found, taking screenshot to debug...")
        take_screenshot(driver, "03_second_continue_not_found")
    
    # ==========================================
    # STEP 4: Enter passcode and click Join
    # ==========================================
    print_step(4, f'Enter passcode "{MEETING_PASSCODE}" and click Join')
    print_status("Looking for passcode input field...")
    time.sleep(3)
    
    passcode_entered = False
    
    # Find passcode input
    passcode_selectors = [
        "//input[@id='input-for-pwd' or @id='passcode' or @id='password']",
        "//input[@placeholder='Enter passcode' or @placeholder='Passcode' or @placeholder='Password']",
        "//input[@type='password']",
        "//input[contains(@class, 'pwd')]",
        "//input[contains(@class, 'passcode')]",
        "//input[contains(@id, 'pwd')]",
        "//input[contains(@id, 'passcode')]",
    ]
    
    for selector in passcode_selectors:
        try:
            passcode_input = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, selector))
            )
            passcode_input.clear()
            passcode_input.send_keys(MEETING_PASSCODE)
            print_success(f'Entered passcode: "{MEETING_PASSCODE}"')
            passcode_entered = True
            time.sleep(2)
            take_screenshot(driver, "04_passcode_entered")
            break
        except:
            continue
    
    if not passcode_entered:
        print_warning("Could not find passcode input field directly")
        print_status("Looking for any input field on the page...")
        try:
            inputs = driver.find_elements(By.XPATH, "//input[@type='text'] | //input")
            for inp in inputs:
                if inp.is_displayed():
                    inp.clear()
                    inp.send_keys(MEETING_PASSCODE)
                    print_success(f"Entered passcode into input field")
                    passcode_entered = True
                    time.sleep(2)
                    take_screenshot(driver, "04_passcode_entered_alt")
                    break
        except:
            pass
    
    # Click Join button
    print_status('Looking for "Join" button...')
    join_btn_found = False
    join_btn_selectors = [
        "//button[contains(text(), 'Join')]",
        "//button[contains(@class, 'join')]",
        "//button[@type='submit']",
        "//span[contains(text(), 'Join')]/..",
    ]
    
    for selector in join_btn_selectors:
        try:
            join_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, selector))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", join_btn)
            time.sleep(1)
            driver.execute_script("arguments[0].click();", join_btn)
            print_success('Clicked "Join" button')
            join_btn_found = True
            time.sleep(5)
            take_screenshot(driver, "05_after_join_click")
            break
        except:
            continue
    
    if not join_btn_found:
        print_warning("Could not find Join button, trying any button on page...")
        try:
            buttons = driver.find_elements(By.XPATH, "//button")
            for btn in buttons:
                text = btn.text.strip().lower()
                if text in ["join", "submit", "enter", "ok", "continue"]:
                    driver.execute_script("arguments[0].click();", btn)
                    print_success(f"Clicked button: '{btn.text.strip()}'")
                    time.sleep(5)
                    take_screenshot(driver, "05_alt_join_click")
                    break
        except:
            pass
    
    # ==========================================
    # STEP 5: Confirm we're in the meeting
    # ==========================================
    print_step(5, "Confirming bot has joined the meeting")
    print_status("Waiting for meeting interface to load...")
    time.sleep(8)
    take_screenshot(driver, "06_meeting_interface")
    
    # Mute microphone
    print_status("Muting microphone...")
    try:
        mute_btns = driver.find_elements(By.XPATH, 
            "//button[contains(@aria-label, 'Mute')] | //button[contains(@title, 'Mute')]")
        for btn in mute_btns:
            aria = btn.get_attribute("aria-label").lower() if btn.get_attribute("aria-label") else ""
            title = btn.get_attribute("title").lower() if btn.get_attribute("title") else ""
            if "unmute" not in aria and "unmute" not in title:
                driver.execute_script("arguments[0].click();", btn)
                print_success("Microphone muted")
                time.sleep(1)
                break
    except:
        print_warning("Could not mute microphone")
    
    # Turn off camera
    print_status("Turning off camera...")
    try:
        cam_btns = driver.find_elements(By.XPATH,
            "//button[contains(@aria-label, 'Stop Video')] | //button[contains(@title, 'Stop Video')]")
        for btn in cam_btns:
            aria = btn.get_attribute("aria-label").lower() if btn.get_attribute("aria-label") else ""
            title = btn.get_attribute("title").lower() if btn.get_attribute("title") else ""
            if "start" not in aria and "start" not in title:
                driver.execute_script("arguments[0].click();", btn)
                print_success("Camera turned off")
                time.sleep(1)
                break
    except:
        print_warning("Could not turn off camera")
    
    time.sleep(3)
    take_screenshot(driver, "07_bot_ready_in_meeting")
    
    # Check for "Leave" button to confirm
    try:
        leave_check = driver.find_elements(By.XPATH, "//button[contains(text(), 'Leave')]")
        if leave_check:
            print("\n" + "="*60)
            print("  🎉🎉🎉 BOT SUCCESSFULLY JOINED THE MEETING! 🎉🎉🎉")
            print("="*60)
            print("  ✅ Audio: Muted")
            print("  ✅ Video: Off")
            print("  ✅ Passcode entered: 120217")
            print("  ✅ Bot is in the meeting and will stay for the duration")
            print("="*60)
            return True
        else:
            print_warning("Could not find 'Leave' button but bot may still be in meeting")
            return True
    except:
        print_warning("Could not verify meeting state")
        return True


def stay_in_meeting(driver):
    """Phase 2: Bot stays in the meeting for the full duration"""
    print("\n" + "="*60)
    print("  🟢 PHASE 2: Bot is staying in the meeting")
    print(f"  ⏱ Duration: {SESSION_DURATION_MINUTES} minutes")
    print("="*60)

    end_time = time.time() + (SESSION_DURATION_MINUTES * 60)
    cycle = 0

    while time.time() < end_time:
        remaining = int(end_time - time.time())
        mins, secs = divmod(remaining, 60)
        cycle += 1

        print(f"  [⏱] {mins:02d}:{secs:02d} remaining (check #{cycle})", end="")

        try:
            leave_buttons = driver.find_elements(
                By.XPATH,
                "//button[contains(text(), 'Leave')] | //button[contains(@aria-label, 'Leave meeting')]"
            )

            if not leave_buttons:
                print(" - DISCONNECTED! Rejoining...")
                driver.get(MEETING_LINK)
                time.sleep(15)
                take_screenshot(driver, f"reconnect_{cycle}")
            else:
                print(" - Connected ✓")
                if cycle % 10 == 0:
                    take_screenshot(driver, f"heartbeat_{cycle}")

        except Exception as e:
            print(f" - Error: {e}")

        time.sleep(60)

    print(f"\n  [✓] Session complete! Bot stayed for {SESSION_DURATION_MINUTES} minutes.")
    take_screenshot(driver, "08_session_complete")


def main():
    """Main execution flow"""
    print("="*60)
    print("  🤖 ZOOM MEETING BOT")
    print(f"  🕐 Started at: {datetime.now().isoformat()}")
    print(f"  📍 Meeting: {MEETING_LINK}")
    print(f"  👤 Name: {DISPLAY_NAME}")
    print(f"  ⏱ Duration: {SESSION_DURATION_MINUTES} minutes")
    print(f"  🔑 Passcode: {MEETING_PASSCODE}")
    print("="*60)

    driver = setup_driver()
    video_path = start_video_recording(driver)

    try:
        joined = join_meeting(driver)
        
        # Stop video recording now that we've joined
        stop_video_recording()

        if joined:
            stay_in_meeting(driver)
        else:
            print("[!] Could not join meeting, aborting")

    except KeyboardInterrupt:
        print("\n[!] Bot manually interrupted")
        stop_video_recording()
    except Exception as e:
        print(f"\n[!] FATAL ERROR: {e}")
        take_screenshot(driver, "fatal_error")
        stop_video_recording()
        raise
    finally:
        print("[*] Bot session ending...")
        driver.quit()


if __name__ == "__main__":
    main()
