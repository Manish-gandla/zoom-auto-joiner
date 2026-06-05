#!/usr/bin/env python3
"""
Zoom Meeting Auto-Joiner for GitHub Actions
Uses Selenium with undetected-chromedriver to bypass Zoom's bot detection
"""

import os
import time
import json
import pickle
import subprocess
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains

# --- CONFIGURATION ---
MEETING_LINK = os.environ.get("ZOOM_MEETING_LINK", "https://bytexl-in.zoom.us/meeting/register/PW9oV6oCQ7mG4d1zmLyR7w")
MEETING_PASSWORD = os.environ.get("ZOOM_MEETING_PASSWORD", "")
DISPLAY_NAME = os.environ.get("ZOOM_DISPLAY_NAME", "Meeting Bot")
SESSION_DURATION_MINUTES = int(os.environ.get("SESSION_DURATION_MINUTES", "60"))

# Paths for persistence
COOKIE_FILE = "/tmp/zoom_cookies.pkl"
SESSION_FILE = "/tmp/zoom_session.json"
SCREENSHOT_DIR = "/tmp/screenshots"

os.makedirs(SCREENSHOT_DIR, exist_ok=True)


def setup_driver():
    """Configure Chrome driver with anti-detection measures"""
    print("[*] Setting up Chrome driver...")
    
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
    
    # Remove automation flags
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    
    driver = webdriver.Chrome(options=options)
    
    # Override navigator.webdriver property
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    return driver


def take_screenshot(driver, label):
    """Save a screenshot for debugging"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{SCREENSHOT_DIR}/{timestamp}_{label}.png"
    driver.save_screenshot(filename)
    print(f"[+] Screenshot saved: {filename}")
    return filename


def save_session(driver):
    """Save cookies and session info for persistence"""
    try:
        with open(COOKIE_FILE, "wb") as f:
            pickle.dump(driver.get_cookies(), f)
        
        session_info = {
            "last_connected": datetime.now().isoformat(),
            "meeting_url": MEETING_LINK,
        }
        with open(SESSION_FILE, "w") as f:
            json.dump(session_info, f)
        print("[+] Session saved successfully")
    except Exception as e:
        print(f"[!] Could not save session: {e}")


def load_session(driver):
    """Load previously saved cookies if they exist"""
    if os.path.exists(COOKIE_FILE):
        try:
            with open(COOKIE_FILE, "rb") as f:
                cookies = pickle.load(f)
            for cookie in cookies:
                try:
                    driver.add_cookie(cookie)
                except:
                    pass
            print("[+] Session loaded from cookies")
            return True
        except Exception as e:
            print(f"[!] Could not load session: {e}")
    return False


def join_meeting():
    """Main function to join Zoom meeting"""
    print(f"[*] Starting Zoom meeting joiner at {datetime.now().isoformat()}")
    print(f"[*] Target meeting: {MEETING_LINK}")
    
    driver = setup_driver()
    
    try:
        # Step 1: Navigate to the meeting registration/join page
        print("[*] Navigating to meeting link...")
        driver.get(MEETING_LINK)
        take_screenshot(driver, "1_landing_page")
        
        # Wait for page to load
        time.sleep(5)
        
        # Step 2: Handle registration page if present
        # Check for "Register" button or form
        try:
            register_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Register')]"))
            )
            print("[*] Registration page detected, filling form...")
            register_btn.click()
            time.sleep(3)
            take_screenshot(driver, "2_registration_clicked")
        except:
            print("[*] No registration button found, proceeding...")
        
        # Step 3: Fill in name if prompted
        try:
            name_input = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, "//input[@id='name' or @name='name' or @placeholder='Name']"))
            )
            name_input.clear()
            name_input.send_keys(DISPLAY_NAME)
            print(f"[*] Entered display name: {DISPLAY_NAME}")
        except:
            print("[*] No name input found")
        
        # Step 4: Handle "Join from Browser" / "Launch Meeting" button
        print("[*] Looking for join/launch button...")
        join_selectors = [
            "//button[contains(text(), 'Join from Browser')]",
            "//button[contains(text(), 'Launch Meeting')]",
            "//button[contains(text(), 'Join Meeting')]",
            "//a[contains(text(), 'Join from Browser')]",
            "//a[contains(text(), 'Launch Meeting')]",
            "//button[contains(@class, 'join-btn')]",
            "//button[contains(@class, 'launch-meeting')]",
            "//button[contains(text(), 'Join')]",
            # Try clicking the meeting link directly
            "//a[contains(@href, 'zoom.us/j/')]",
        ]
        
        join_clicked = False
        for selector in join_selectors:
            try:
                element = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, selector))
                )
                driver.execute_script("arguments[0].click();", element)
                print(f"[+] Clicked join button: {selector}")
                join_clicked = True
                time.sleep(5)
                take_screenshot(driver, "3_after_join_click")
                break
            except:
                continue
        
        if not join_clicked:
            print("[*] Could not find join button, checking current URL for zoom meeting ID...")
            current_url = driver.current_url
            if "zoom.us/j/" in current_url or "zoom.us/wc/" in current_url:
                print("[+] Already navigated to meeting room")
                join_clicked = True
        
        # Step 5: Handle "Open zoom.us app?" dialog - click "Cancel" to stay in browser
        if join_clicked:
            time.sleep(5)
            take_screenshot(driver, "4_before_app_dialog")
            
            try:
                # Try to cancel the app launch prompt
                cancel_btn = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Cancel')] | //button[contains(text(), 'Stay in Browser')] | //a[contains(text(), 'Cancel')]"))
                )
                cancel_btn.click()
                print("[+] Canceled app launch, staying in browser")
                time.sleep(3)
            except:
                print("[*] No cancel dialog detected, or already in browser view")
        
        # Step 6: Wait for the meeting web interface to load
        print("[*] Waiting for meeting interface to load...")
        time.sleep(10)
        take_screenshot(driver, "5_meeting_interface")
        
        # Step 7: Dismiss any "Join Audio" or "Computer Audio" prompts
        audio_selectors = [
            "//button[contains(text(), 'Computer Audio')]",
            "//button[contains(text(), 'Join with Computer Audio')]",
            "//button[contains(text(), 'Join Audio')]",
            "//button[contains(@aria-label, 'Join Audio')]",
            "//button[contains(text(), 'Mute')]",
            "//button[contains(@title, 'Mute')]",
        ]
        
        for selector in audio_selectors:
            try:
                element = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, selector))
                )
                driver.execute_script("arguments[0].click();", element)
                print(f"[+] Clicked audio button: {selector}")
                time.sleep(2)
            except:
                continue
        
        # Step 8: Mute microphone if unmuted
        try:
            mute_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(@aria-label, 'Mute') or contains(@title, 'Mute')]"))
            )
            if "unmute" not in mute_btn.get_attribute("aria-label").lower():
                driver.execute_script("arguments[0].click();", mute_btn)
                print("[+] Microphone muted")
                time.sleep(1)
        except:
            print("[*] Could not find mute button")
        
        # Step 9: Turn off video/camera
        video_selectors = [
            "//button[contains(@aria-label, 'Stop Video')]",
            "//button[contains(@title, 'Stop Video')]",
            "//button[contains(@aria-label, 'Turn Off Camera')]",
        ]
        for selector in video_selectors:
            try:
                element = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, selector))
                )
                driver.execute_script("arguments[0].click();", element)
                print(f"[+] Video turned off: {selector}")
                time.sleep(1)
                break
            except:
                continue
        
        # Step 10: Take final screenshot confirming we're in the meeting
        time.sleep(5)
        take_screenshot(driver, "6_in_meeting")
        
        # Save session for potential reconnection
        save_session(driver)
        
        print(f"[+] SUCCESS: Bot has joined the meeting!")
        print(f"[*] Bot will stay in meeting for {SESSION_DURATION_MINUTES} minutes...")
        
        # Step 11: Keep the bot in the meeting by keeping the driver alive
        # The page refresh and periodic screenshots keep the session active
        end_time = time.time() + (SESSION_DURATION_MINUTES * 60)
        cycle_count = 0
        
        while time.time() < end_time:
            remaining = int(end_time - time.time())
            mins, secs = divmod(remaining, 60)
            cycle_count += 1
            
            print(f"[*] Staying in meeting... {mins:02d}:{secs:02d} remaining (cycle {cycle_count})")
            
            # Periodically check if we're still connected
            try:
                # Check for "Leave Meeting" button - if found, we're connected
                leave_btn = driver.find_elements(By.XPATH, "//button[contains(text(), 'Leave') or contains(@aria-label, 'Leave')]")
                if not leave_btn:
                    print("[!] Leave button not found, attempting reconnection...")
                    # Try to re-enter
                    driver.get(MEETING_LINK)
                    time.sleep(10)
                
                # Take periodic screenshot to verify connection
                if cycle_count % 3 == 0:
                    take_screenshot(driver, f"heartbeat_{cycle_count}")
                    
            except Exception as e:
                print(f"[!] Connection check failed: {e}")
            
            # Sleep 60 seconds between checks
            time.sleep(60)
        
        print(f"[*] Session duration of {SESSION_DURATION_MINUTES} minutes completed.")
        take_screenshot(driver, "7_session_end")
        
    except Exception as e:
        print(f"[!] Fatal error: {e}")
        take_screenshot(driver, "error_state")
        raise
    finally:
        # Keep the browser open - don't quit
        # The actual quit will happen when GitHub Actions stops the job
        print("[*] Bot session active. Waiting for GitHub timeout or manual stop...")
        # Keep process alive indefinitely
        while True:
            time.sleep(300)


if __name__ == "__main__":
    join_meeting()
