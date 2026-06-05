#!/usr/bin/env python3
"""
Zoom Meeting Auto-Joiner
You register manually -> get join link -> paste into bot
Bot joins, turns off audio/video, stays for duration
Records video of everything the bot does
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
    """Save a screenshot"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{SCREENSHOT_DIR}/{timestamp}_{label}.png"
    driver.save_screenshot(filename)
    print(f"[+] Screenshot: {filename}")
    return filename


def frame_recorder(driver, output_path):
    """
    Background thread: continuously captures screenshots as video frames
    at ~2 fps while the bot is running. Stitches them into a video at the end.
    """
    print("[🎥] Video recording thread started - capturing frames...")
    
    while recording_active[0]:
        try:
            frame_num = frame_counter[0]
            frame_path = f"{FRAMES_DIR}/frame_{frame_num:06d}.png"
            driver.save_screenshot(frame_path)
            frame_counter[0] += 1
            
            # Print progress every 30 frames
            if frame_num % 30 == 0 and frame_num > 0:
                print(f"[🎥] Captured {frame_num} frames so far...")
                
        except Exception as e:
            print(f"[!] Frame capture error: {e}")
        
        # ~2 frames per second
        time.sleep(0.5)
    
    print(f"[🎥] Recording stopped. Total frames captured: {frame_counter[0]}")
    print(f"[🎥] Encoding video from frames (this may take a moment)...")
    
    # Stitch frames into video using ffmpeg
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
    print(f"[🎥] Video recording started -> {output_path}")
    return output_path


def stop_video_recording():
    """Stop the video recording and wait for it to finish"""
    print("[🎥] Stopping video recording...")
    recording_active[0] = False
    if video_thread[0] and video_thread[0].is_alive():
        video_thread[0].join(timeout=130)
    print("[🎥] Video recording finished")


def join_meeting(driver):
    """
    Phase 1: Navigate to the meeting join link that YOU registered for.
    Bot joins via browser, turns off audio/video.
    """
    print("\n" + "="*60)
    print("🟢 Bot is navigating to the meeting join link...")
    print(f"📍 Link: {MEETING_LINK}")
    print("="*60)

    # Navigate to the actual meeting join link
    print(f"[*] Opening join link...")
    driver.get(MEETING_LINK)
    time.sleep(5)
    take_screenshot(driver, "1_landing_page")

    # Check what page we're on
    current_url = driver.current_url
    print(f"[*] Current URL: {current_url}")

    # Wait for page to fully load
    time.sleep(3)

    # --- Handle different Zoom page states ---

    # 1. Check if there's a "Launch Meeting" or "Join from Browser" button
    print("[*] Looking for join/launch button in browser...")
    join_selectors = [
        "//button[contains(text(), 'Join from Browser')]",
        "//button[contains(text(), 'Launch Meeting')]",
        "//button[contains(text(), 'Join Meeting')]",
        "//button[contains(text(), 'Join')]",
        "//a[contains(text(), 'Join from Browser')]",
        "//a[contains(text(), 'Launch Meeting')]",
        "//button[contains(@class, 'join-btn')]",
        "//button[contains(@class, 'launch-button')]",
        "//a[contains(text(), 'click here')]",
        "//button[contains(text(), 'Open Zoom')]",
    ]

    joined = False
    for selector in join_selectors:
        try:
            element = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, selector))
            )
            driver.execute_script("arguments[0].click();", element)
            print(f"[+] Clicked join button: {selector}")
            joined = True
            time.sleep(5)
            take_screenshot(driver, "2_after_join_click")
            break
        except:
            continue

    # 2. If we're already on the meeting page (no button needed)
    if not joined:
        print("[*] No join button found - checking if already in meeting room...")
        if "zoom.us/j/" in current_url or "zoom.us/wc/" in current_url:
            print("[+] Already navigated to meeting room")
            joined = True
        else:
            # Try to detect if page needs a name entry first
            print("[*] Trying name entry form...")
            try:
                name_input = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, "//input[@id='name' or @name='name' or @placeholder='Enter your name' or @placeholder='Your Name']"))
                )
                name_input.clear()
                name_input.send_keys(DISPLAY_NAME)
                print(f"[*] Entered name: {DISPLAY_NAME}")
                time.sleep(1)
                
                # Find and click submit/join button near the name field
                submit_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Join')] | //button[@type='submit']")
                driver.execute_script("arguments[0].click();", submit_btn)
                print("[+] Submitted name form")
                time.sleep(5)
                take_screenshot(driver, "2_after_name_submit")
                joined = True
            except:
                print("[!] Could not find any way to join the meeting")

    # 3. Handle "Open zoom.us app?" dialog
    if joined:
        time.sleep(5)
        try:
            stay_in_browser = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Stay in Browser')] | //button[contains(text(), 'Stay in Browser')] | //button[contains(text(), 'Cancel')]"))
            )
            stay_in_browser.click()
            print("[+] Stayed in browser (dismissed app launch)")
            time.sleep(3)
        except:
            print("[*] No app launch dialog")

        # 4. Wait for meeting interface to fully load
        print("[*] Waiting for meeting interface...")
        time.sleep(10)
        take_screenshot(driver, "3_meeting_interface_loading")

    # 5. Join Computer Audio (required to stay in meeting)
    print("[*] Looking for audio join prompt...")
    audio_selectors = [
        "//button[contains(text(), 'Join Audio')]",
        "//button[contains(text(), 'Join with Computer Audio')]",
        "//button[contains(text(), 'Computer Audio')]",
        "//button[contains(@aria-label, 'Join Audio')]",
        "//button[contains(@aria-label, 'Join Computer Audio')]",
        "//button[contains(text(), 'Use Computer Audio')]",
    ]

    audio_joined = False
    for selector in audio_selectors:
        try:
            element = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, selector))
            )
            driver.execute_script("arguments[0].click();", element)
            print(f"[+] Clicked audio: {selector}")
            audio_joined = True
            time.sleep(2)
            break
        except:
            continue

    if not audio_joined:
        print("[*] No audio prompt found - may already be connected")

    # 6. Mute microphone
    print("[*] Muting microphone...")
    mute_selectors = [
        "//button[contains(@aria-label, 'Mute')]",
        "//button[contains(@aria-label, 'Mute my microphone')]",
        "//button[contains(@title, 'Mute')]",
        "//button[contains(@data-testid, 'mute')]",
    ]

    for selector in mute_selectors:
        try:
            element = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.XPATH, selector))
            )
            aria = element.get_attribute("aria-label").lower()
            title = element.get_attribute("title").lower() if element.get_attribute("title") else ""
            # Only click if it says "Mute" (not already muted/"Unmute")
            if "unmute" not in aria and "unmute" not in title:
                driver.execute_script("arguments[0].click();", element)
                print(f"[+] Microphone muted")
                time.sleep(1)
                break
            else:
                print("[*] Microphone already muted")
                break
        except:
            continue

    # 7. Turn off camera
    print("[*] Turning off camera...")
    camera_selectors = [
        "//button[contains(@aria-label, 'Stop Video')]",
        "//button[contains(@aria-label, 'Turn off my video')]",
        "//button[contains(@title, 'Stop Video')]",
        "//button[contains(@data-testid, 'video')]",
        "//button[contains(@aria-label, 'Stop my video')]",
    ]

    for selector in camera_selectors:
        try:
            element = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.XPATH, selector))
            )
            aria = element.get_attribute("aria-label").lower()
            title = element.get_attribute("title").lower() if element.get_attribute("title") else ""
            # Only click if video is currently on ("Stop" vs "Start")
            if "start" not in aria and "start" not in title:
                driver.execute_script("arguments[0].click();", element)
                print(f"[+] Camera turned off")
                time.sleep(1)
                break
            else:
                print("[*] Camera already off")
                break
        except:
            continue

    # 8. Final confirmation screenshot
    time.sleep(3)
    take_screenshot(driver, "4_bot_ready_in_meeting")

    # Verify we're actually in the meeting by checking for leave button
    try:
        leave_check = driver.find_elements(By.XPATH, "//button[contains(text(), 'Leave')]")
        if leave_check:
            print("\n" + "="*60)
            print("✅ BOT SUCCESSFULLY JOINED THE MEETING!")
            print("   Audio: Muted")
            print("   Video: Off")
            print("   Bot will stay for the full duration")
            print("="*60)
            return True
        else:
            print("\n[!] WARNING: Could not confirm bot is in meeting (no Leave button)")
            print("[*] Bot will still attempt to stay connected")
            return True
    except:
        print("\n[!] WARNING: Could not verify meeting state")
        return True


def stay_in_meeting(driver):
    """
    Phase 2: Bot stays in the meeting for the full duration.
    Periodically checks connection and reconnects if needed.
    """
    print("\n" + "="*60)
    print("🟢 Bot is now staying in the meeting")
    print(f"📅 Duration: {SESSION_DURATION_MINUTES} minutes")
    print("="*60)

    end_time = time.time() + (SESSION_DURATION_MINUTES * 60)
    cycle = 0

    while time.time() < end_time:
        remaining = int(end_time - time.time())
        mins, secs = divmod(remaining, 60)
        cycle += 1

        # Simple compact status
        print(f"[⏱] {mins:02d}:{secs:02d} remaining (check #{cycle})")

        try:
            # Check if "Leave" button exists = we're still connected
            leave_buttons = driver.find_elements(
                By.XPATH,
                "//button[contains(text(), 'Leave')] | //button[contains(@aria-label, 'Leave meeting')]"
            )

            if not leave_buttons:
                print("[!] Disconnected! Attempting to rejoin...")
                driver.get(MEETING_LINK)
                time.sleep(15)
                take_screenshot(driver, f"reconnect_{cycle}")
                
                # Re-mute and re-turn-off camera if needed
                try:
                    mute_btn = driver.find_element(By.XPATH, "//button[contains(@aria-label, 'Mute')]")
                    mute_btn.click()
                except:
                    pass
                try:
                    cam_btn = driver.find_element(By.XPATH, "//button[contains(@aria-label, 'Stop Video')]")
                    cam_btn.click()
                except:
                    pass
            else:
                # Still connected - take periodic screenshot for artifact
                if cycle % 10 == 0:
                    take_screenshot(driver, f"heartbeat_{cycle}")

        except Exception as e:
            print(f"[!] Connection check error: {e}")

        # Wait 60 seconds between checks
        time.sleep(60)

    print(f"\n[✓] Session complete! Bot stayed for {SESSION_DURATION_MINUTES} minutes.")
    take_screenshot(driver, "5_session_complete")


def main():
    """Main execution flow"""
    print("="*60)
    print(f"🤖 ZOOM MEETING BOT")
    print(f"🕐 Started at: {datetime.now().isoformat()}")
    print(f"📍 Meeting: {MEETING_LINK}")
    print(f"👤 Name: {DISPLAY_NAME}")
    print(f"⏱ Duration: {SESSION_DURATION_MINUTES} minutes")
    print("="*60)

    # Initialize driver
    driver = setup_driver()

    # Start video recording
    video_path = start_video_recording(driver)

    try:
        # Phase 1: Join the meeting
        joined = join_meeting(driver)

        # Stop video recording (the interesting part is done)
        stop_video_recording()

        if joined:
            # Phase 2: Stay for duration
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
