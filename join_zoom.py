#!/usr/bin/env python3
"""
Zoom Meeting Auto-Joiner - You navigate the bot first, then it stays
Uses webdriver-manager for automatic ChromeDriver version matching
"""

import os
import time
import json
import pickle
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# --- CONFIGURATION ---
MEETING_LINK = os.environ.get("ZOOM_MEETING_LINK", "https://bytexl-in.zoom.us/meeting/register/PW9oV6oCQ7mG4d1zmLyR7w")
DISPLAY_NAME = os.environ.get("ZOOM_DISPLAY_NAME", "Meeting Bot")
SESSION_DURATION_MINUTES = int(os.environ.get("SESSION_DURATION_MINUTES", "60"))

SCREENSHOT_DIR = "/tmp/screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


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

    # Use webdriver-manager to get the correct ChromeDriver version
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


def wait_for_user_to_join(driver):
    """
    Phase 1: Bot navigates to meeting but WAITS for YOU to confirm.
    You will see the bot in the participant list. When you're satisfied,
    you exit the meeting. The bot stays.
    """
    print("\n" + "="*60)
    print("🟢 PHASE 1: Bot is navigating to the meeting...")
    print("="*60)

    # Navigate to meeting registration page
    print(f"[*] Opening meeting link...")
    driver.get(MEETING_LINK)
    time.sleep(5)
    take_screenshot(driver, "1_landing_page")

    # Try clicking through registration if present
    try:
        register_btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Register')]"))
        )
        print("[*] Registration page detected, clicking register...")
        register_btn.click()
        time.sleep(3)
    except:
        print("[*] No registration page")

    # Fill in name if needed
    try:
        name_input = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, "//input[@id='name' or @name='name' or @placeholder='Enter your name']"))
        )
        name_input.clear()
        name_input.send_keys(DISPLAY_NAME)
        print(f"[*] Display name set: {DISPLAY_NAME}")
    except:
        print("[*] No name input needed")

    # Click "Join from Browser" / "Launch Meeting"
    print("[*] Looking for join button...")
    join_selectors = [
        "//button[contains(text(), 'Join from Browser')]",
        "//button[contains(text(), 'Launch Meeting')]",
        "//button[contains(text(), 'Join Meeting')]",
        "//button[contains(text(), 'Join')]",
        "//a[contains(text(), 'Join from Browser')]",
        "//a[contains(text(), 'Launch Meeting')]",
        "//button[contains(@class, 'join-btn')]",
        "//button[contains(@class, 'launch-button')]",
    ]

    joined = False
    for selector in join_selectors:
        try:
            element = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, selector))
            )
            driver.execute_script("arguments[0].click();", element)
            print(f"[+] Clicked: {selector}")
            joined = True
            time.sleep(5)
            break
        except:
            continue

    if not joined:
        print("[*] No join button found - trying direct URL navigation...")
        current_url = driver.current_url
        if "zoom.us/j/" in current_url or "zoom.us/wc/" in current_url:
            print("[+] Already navigated to meeting room")
            joined = True

    # Wait for meeting interface to load
    print("[*] Waiting for meeting interface to load...")
    time.sleep(10)
    take_screenshot(driver, "2_meeting_interface")

    # Handle "Open zoom.us app?" dialog - click Cancel/Stay in Browser
    try:
        cancel_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Cancel')] | //button[contains(text(), 'Stay in Browser')]"))
        )
        cancel_btn.click()
        print("[+] Dismissed app launch dialog")
        time.sleep(3)
    except:
        print("[*] No app dialog")

    # Join Computer Audio (needed to stay in meeting)
    try:
        audio_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Join Audio')] | //button[contains(text(), 'Computer Audio')] | //button[contains(@aria-label, 'Join Audio')]"))
        )
        audio_btn.click()
        print("[+] Joined computer audio")
        time.sleep(3)
    except:
        print("[*] No audio prompt or already joined")

    # Mute microphone
    try:
        mute_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(@aria-label, 'Mute')]"))
        )
        aria = mute_btn.get_attribute("aria-label").lower()
        if "unmute" not in aria:
            mute_btn.click()
            print("[+] Microphone muted")
            time.sleep(1)
    except:
        print("[*] Could not find mute button")

    # Turn off camera
    try:
        cam_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(@aria-label, 'Stop Video')]"))
        )
        cam_btn.click()
        print("[+] Camera turned off")
        time.sleep(1)
    except:
        print("[*] No camera button found")

    # Final screenshot showing bot is in meeting
    time.sleep(5)
    take_screenshot(driver, "3_bot_in_meeting")

    print("\n" + "="*60)
    print("✅ BOT HAS JOINED THE MEETING!")
    print("🔔 ACTION REQUIRED FROM YOU:")
    print("   1. Open the meeting link in YOUR browser")
    print("   2. Verify the bot is in the participant list")
    print("   3. When satisfied, you can EXIT the meeting")
    print("   4. The bot will STAY for the full duration\n")

    return True


def stay_in_meeting(driver):
    """
    Phase 2: You've confirmed. Now the bot stays for the duration.
    """
    print("\n" + "="*60)
    print("🟢 PHASE 2: Bot will stay in the meeting")
    print(f"📅 Duration: {SESSION_DURATION_MINUTES} minutes")
    print("="*60)

    end_time = time.time() + (SESSION_DURATION_MINUTES * 60)
    cycle = 0

    while time.time() < end_time:
        remaining = int(end_time - time.time())
        mins, secs = divmod(remaining, 60)
        cycle += 1

        print(f"[⏱] Staying in meeting... {mins:02d}:{secs:02d} remaining (check #{cycle})")

        try:
            # Check we're still in the meeting by looking for the "Leave" button
            leave_buttons = driver.find_elements(
                By.XPATH,
                "//button[contains(text(), 'Leave')] | //button[contains(@aria-label, 'Leave meeting')]"
            )

            if not leave_buttons:
                print("[!] WARNING: Leave button not found - might have disconnected")
                print("[*] Attempting to rejoin...")
                driver.get(MEETING_LINK)
                time.sleep(15)
                take_screenshot(driver, f"reconnect_{cycle}")
            else:
                if cycle % 5 == 0:
                    take_screenshot(driver, f"heartbeat_{cycle}")

        except Exception as e:
            print(f"[!] Connection check error: {e}")

        time.sleep(60)

    print(f"\n[✓] Session complete! Bot stayed for {SESSION_DURATION_MINUTES} minutes.")
    take_screenshot(driver, "4_session_complete")


def main():
    """Main execution flow"""
    print(f"🤖 Zoom Meeting Bot - Started at {datetime.now().isoformat()}")
    print(f"📍 Meeting: {MEETING_LINK}")
    print(f"👤 Name: {DISPLAY_NAME}")

    driver = setup_driver()

    try:
        wait_for_user_to_join(driver)
        stay_in_meeting(driver)

    except KeyboardInterrupt:
        print("\n[!] Bot manually interrupted")
    except Exception as e:
        print(f"\n[!] FATAL ERROR: {e}")
        take_screenshot(driver, "fatal_error")
        raise
    finally:
        print("[*] Bot session ending...")
        driver.quit()


if __name__ == "__main__":
    main()
