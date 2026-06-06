#!/usr/bin/env python3
"""
Zoom Meeting Auto-Join Bot
Complete flow:
1. Open join link (which user provided after registering)
2. Click "Join from your browser" link
3. Click "Continue without microphone and camera" (×2)
4. Enter passcode
5. Click first Join button
6. Click second BLUE Join button
7. Stay in meeting for specified duration
8. Record video of everything via screenshots (handled by workflow)
"""

import os
import time
import sys
import re
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    ElementClickInterceptedException,
    StaleElementReferenceException
)
from webdriver_manager.chrome import ChromeDriverManager

# =============================================================================
# Configuration
# =============================================================================
ZOOM_JOIN_LINK = os.environ.get('ZOOM_JOIN_LINK', '').strip()
MEETING_PASSCODE = os.environ.get('MEETING_PASSCODE', '120217')
DURATION_SECONDS = int(os.environ.get('DURATION_SECONDS', '300'))
PARTICIPANT_NAME = os.environ.get('PARTICIPANT_NAME', 'HackerAI Bot')
DISPLAY = os.environ.get('DISPLAY', ':99')

# =============================================================================
# Logging
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger(__name__)

# =============================================================================
# Validation
# =============================================================================
if not ZOOM_JOIN_LINK:
    log.error("ZOOM_JOIN_LINK environment variable not set!")
    sys.exit(1)

log.info("=" * 60)
log.info("ZOOM BOT STARTING")
log.info(f"Join link: {ZOOM_JOIN_LINK}")
log.info(f"Passcode: {'******' if MEETING_PASSCODE else '(none)'}")
log.info(f"Duration: {DURATION_SECONDS}s")
log.info(f"Name: {PARTICIPANT_NAME}")
log.info(f"Display: {DISPLAY}")
log.info("=" * 60)

# =============================================================================
# Chrome Options
# =============================================================================
chrome_options = Options()
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')
chrome_options.add_argument('--disable-gpu')
chrome_options.add_argument('--window-size=1920,1080')
chrome_options.add_argument('--disable-blink-features=AutomationControlled')
chrome_options.add_argument(f'--display={DISPLAY}')

# Pretend to be a real user
chrome_options.add_argument(
    '--user-agent=Mozilla/5.0 (X11; Linux x86_64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/120.0.0.0 Safari/537.36'
)

prefs = {
    'profile.default_content_setting_values.notifications': 2,
    'credentials_enable_service': False,
    'profile.password_manager_enabled': False,
    'download.prompt_for_download': False,
}
chrome_options.add_experimental_option('prefs', prefs)
chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
chrome_options.add_experimental_option('useAutomationExtension', False)

# =============================================================================
# Helper Functions
# =============================================================================
def log_page_state(driver, label="Current state"):
    """Log what's visible on the page for debugging."""
    try:
        page_text = driver.find_element(By.TAG_NAME, 'body').text[:500]
        log.info(f"[{label}] Page text preview: {repr(page_text[:200])}")
    except Exception:
        log.info(f"[{label}] Could not read page text")

    try:
        url = driver.current_url
        log.info(f"[{label}] URL: {url}")
    except Exception:
        pass

    try:
        title = driver.title
        log.info(f"[{label}] Title: {title}")
    except Exception:
        pass


def find_and_click_text(driver, text, element_type='*', timeout=5, retries=3):
    """Find an element containing specific text and click it."""
    xpath = f"//{element_type}[contains(text(), '{text}')]"
    for attempt in range(retries):
        try:
            elem = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", elem)
            time.sleep(0.5)
            elem.click()
            log.info(f"✓ Clicked element containing text: '{text}'")
            return True
        except (TimeoutException, NoSuchElementException) as e:
            if attempt < retries - 1:
                log.info(f"  Retry {attempt+1}/{retries} for '{text}': {str(e)[:60]}")
                time.sleep(2)
            else:
                log.warning(f"✗ Could not find/click text: '{text}'")
    return False


def find_and_click_by_selector(driver, selector_type, selector_value, timeout=10, retries=3):
    """Find element by CSS/XPath selector and click."""
    by = By.CSS_SELECTOR if selector_type == 'css' else By.XPATH
    for attempt in range(retries):
        try:
            elem = WebDriverWait(driver, timeout).until(
                EC.element_to_be_clickable((by, selector_value))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", elem)
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", elem)
            log.info(f"✓ Clicked via {selector_type} selector: {selector_value[:80]}")
            return True
        except (TimeoutException, NoSuchElementException, ElementClickInterceptedException) as e:
            if attempt < retries - 1:
                log.info(f"  Retry {attempt+1}/{retries} for selector: {str(e)[:60]}")
                time.sleep(2)
            else:
                log.warning(f"✗ Could not click selector: {selector_value[:80]}")
    return False


def smart_click_join_button(driver, timeout=15):
    """
    Multi-method approach to find and click the blue 'Join' button
    that appears after passcode entry (the final join button).
    """
    strategies = [
        # Strategy 1: Blue button specific selectors
        lambda: find_and_click_by_selector(
            driver, 'xpath',
            "//button[contains(@class, 'join') and contains(@class, 'primary')]//span[contains(text(), 'Join')]/..",
            timeout=5
        ),
        # Strategy 2: Any primary/blue button with "Join"
        lambda: find_and_click_by_selector(
            driver, 'xpath',
            "//button[contains(@class, 'btn--primary') and contains(text(), 'Join')]",
            timeout=5
        ),
        # Strategy 3: Button with join-link class
        lambda: find_and_click_by_selector(
            driver, 'xpath',
            "//a[contains(@class, 'join-link')]",
            timeout=5
        ),
        # Strategy 4: Just any element with Join text
        lambda: find_and_click_text(driver, 'Join', 'button', timeout=5),
        lambda: find_and_click_text(driver, 'Join', 'a', timeout=5),
        lambda: find_and_click_text(driver, 'Join', 'span', timeout=5),
        # Strategy 5: JavaScript - find buttons by proximity to center
        lambda: js_find_and_click_join(driver),
        # Strategy 6: Scan all buttons/anchors for Join-like text
        lambda: scan_and_click_join(driver),
    ]

    for idx, strategy in enumerate(strategies, 1):
        log.info(f"  Join button strategy {idx}/{len(strategies)}...")
        try:
            if strategy():
                log.info(f"  ✓ Strategy {idx} succeeded!")
                return True
        except Exception as e:
            log.info(f"  Strategy {idx} failed: {str(e)[:60]}")
    return False


def js_find_and_click_join(driver):
    """JavaScript approach - find buttons closest to viewport center."""
    js_code = """
    const buttons = document.querySelectorAll('button, a, span, div');
    const centerX = window.innerWidth / 2;
    const centerY = window.innerHeight / 2;
    
    let best = null;
    let bestDist = Infinity;
    let bestText = '';
    
    buttons.forEach(el => {
        const text = (el.textContent || '').trim().toLowerCase();
        // Check if the element (or its children) contain join-related text
        const hasJoinText = /^join$/i.test(text) || /join/i.test(text) && text.length < 20;
        if (!hasJoinText) return;
        
        const rect = el.getBoundingClientRect();
        const elCenterX = rect.left + rect.width / 2;
        const elCenterY = rect.top + rect.height / 2;
        const dist = Math.sqrt((elCenterX - centerX)**2 + (elCenterY - centerY)**2);
        
        // Prefer elements that look like buttons (reasonable size)
        const isReasonableSize = rect.width > 40 && rect.height > 20 && rect.width < 600;
        const isVisible = rect.width > 0 && rect.height > 0;
        
        if (dist < bestDist && isVisible && isReasonableSize) {
            best = el;
            bestDist = dist;
            bestText = text;
        }
    });
    
    if (best) {
        best.scrollIntoView({behavior: 'instant', block: 'center'});
        best.click();
        return bestText;
    }
    return null;
    """
    try:
        result = driver.execute_script(js_code)
        if result:
            log.info(f"✓ JS strategy clicked element with text: '{result}'")
            return True
        log.info("  JS strategy found no matching element")
        return False
    except Exception as e:
        log.info(f"  JS strategy error: {str(e)[:60]}")
        return False


def scan_and_click_join(driver):
    """Scan all clickable elements for Join text."""
    log.info("  Scanning all buttons/anchors for 'Join'...")
    try:
        all_clickables = driver.find_elements(By.XPATH, "//button | //a | //span[@role='button'] | //input[@type='button']")
        for el in all_clickables:
            try:
                text = (el.text or '').strip().lower()
                aria = (el.get_attribute('aria-label') or '').strip().lower()
                if text in ('join',) or 'join' in text or aria in ('join', 'join meeting'):
                    driver.execute_script("arguments[0].scrollIntoView(true);", el)
                    time.sleep(0.3)
                    driver.execute_script("arguments[0].click();", el)
                    log.info(f"✓ Scanned and clicked: '{el.text[:40]}'")
                    return True
            except StaleElementReferenceException:
                continue
    except Exception as e:
        log.info(f"  Scan error: {str(e)[:60]}")
    return False


def is_meeting_active(driver):
    """Check if we've successfully joined the meeting."""
    try:
        # Look for meeting indicators
        indicators = [
            "//div[contains(@class, 'meeting')]",
            "//div[@id='wc-footer']",
            "//div[contains(@class, 'footer')]",
            "//button[contains(@aria-label, 'Leave')]",
            "//button[contains(@aria-label, 'leave')]",
            "//button[contains(text(), 'Leave')]",
            "//div[contains(@id, 'monitor-')]",
            "//canvas[contains(@class, 'video')]",
            "//video",
        ]
        for xpath in indicators:
            elems = driver.find_elements(By.XPATH, xpath)
            if elems:
                return True
        
        # Also check URL for meeting indicators
        url = driver.current_url
        if '/wc/' in url or '/w/' in url:
            return True
            
        return False
    except Exception:
        return False


def wait_for_page_load(driver, timeout=30):
    """Wait for page to fully load."""
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script('return document.readyState') == 'complete'
        )
    except:
        pass
    time.sleep(1)


# =============================================================================
# Main Flow
# =============================================================================
def main():
    driver = None
    try:
        # ---- Initialize Driver ----
        log.info("Initializing Chrome driver...")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(60)
        wait = WebDriverWait(driver, 20)
        log.info("✓ Chrome driver initialized successfully")

        # =========================================================================
        # STEP 1: Navigate to the join link
        # =========================================================================
        log.info("\n" + "=" * 60)
        log.info("STEP 1: Navigating to join link...")
        log.info("=" * 60)
        driver.get(ZOOM_JOIN_LINK)
        wait_for_page_load(driver)
        time.sleep(3)
        log_page_state(driver, "After navigating to join link")

        # =========================================================================
        # STEP 2: Click "Join from your browser" link
        # =========================================================================
        log.info("\n" + "=" * 60)
        log.info("STEP 2: Clicking 'Join from your browser' link...")
        log.info("=" * 60)

        join_from_browser_found = False

        # Method A: Look for the exact text link
        strategies_fb = [
            ("//a[contains(text(), 'Join from your browser')]", "exact text 'Join from your browser'"),
            ("//a[contains(text(), 'join from your browser')]", "lowercase text"),
            ("//a[contains(@href, 'browser')]", "href contains browser"),
            ("//*[contains(text(), 'Join from your browser')]", "any element with text"),
            ("//a[contains(text(), 'join from browser')]", "slight variant"),
            ("//*[contains(@class, 'join-from-browser')]", "class name"),
            ("//*[contains(@class, 'join-from')]", "partial class"),
            ("//a[contains(@id, 'browser')]", "ID contains browser"),
        ]

        for xpath, desc in strategies_fb:
            try:
                elem = driver.find_element(By.XPATH, xpath)
                if elem.is_displayed():
                    driver.execute_script("arguments[0].scrollIntoView(true);", elem)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", elem)
                    log.info(f"✓ Clicked 'Join from your browser' using strategy: {desc}")
                    join_from_browser_found = True
                    break
            except (NoSuchElementException, ElementClickInterceptedException) as e:
                continue

        if not join_from_browser_found:
            log.warning("⚠ Could not find 'Join from your browser' link with standard selectors")
            log.info("  Trying link text search on page...")
            try:
                body_text = driver.find_element(By.TAG_NAME, 'body').text
                if 'browser' in body_text.lower() and 'join' in body_text.lower():
                    log.info("  Page contains 'browser' and 'join' text - trying JS click")
                    success = js_find_and_click_join(driver)
                    if not success:
                        # Try xpath with 'browser' in link
                        links = driver.find_elements(By.XPATH, "//a")
                        for link in links:
                            text = (link.text or '').lower()
                            if 'browser' in text and 'join' in text:
                                driver.execute_script("arguments[0].click();", link)
                                log.info(f"✓ Clicked link: '{link.text}'")
                                join_from_browser_found = True
                                break
            except Exception as e:
                log.warning(f"  Fallback failed: {str(e)[:60]}")

        if not join_from_browser_found:
            log.error("✗ CRITICAL: Could not find 'Join from your browser' link!")
            log.info("  Page HTML (first 2000 chars):")
            log.info(driver.page_source[:2000])
            log.info("  Saving screenshot...")
            driver.save_screenshot('/tmp/zoom_bot_output/error_join_from_browser.png')
            sys.exit(1)

        time.sleep(3)
        log_page_state(driver, "After clicking Join from browser")

        # =========================================================================
        # STEP 3: Click "Continue without microphone and camera" (may appear twice)
        # =========================================================================
        log.info("\n" + "=" * 60)
        log.info("STEP 3: Handling 'Continue without microphone and camera'...")
        log.info("=" * 60)

        for attempt in range(3):
            try:
                # Try to find the continue without mic/camera text
                xpaths_cw = [
                    "//*[contains(text(), 'Continue without microphone')]",
                    "//*[contains(text(), 'continue without microphone')]",
                    "//*[contains(text(), 'Continue without')]",
                    "//*[contains(text(), 'without microphone')]",
                    "//button[contains(text(), 'Continue')]",
                    "//a[contains(text(), 'Continue')]",
                    "//*[@role='button'][contains(text(), 'Continue')]",
                    "//input[@value='Continue']",
                ]
                clicked = False
                for xpath in xpaths_cw:
                    elems = driver.find_elements(By.XPATH, xpath)
                    for elem in elems:
                        if elem.is_displayed():
                            driver.execute_script("arguments[0].scrollIntoView(true);", elem)
                            time.sleep(0.3)
                            driver.execute_script("arguments[0].click();", elem)
                            log.info(f"✓ Clicked 'Continue without microphone and camera' (attempt {attempt+1})")
                            clicked = True
                            time.sleep(1.5)
                            break
                    if clicked:
                        break
                
                if not clicked:
                    log.info(f"  No 'Continue' button found on attempt {attempt+1}, proceeding...")
                    break
            except Exception as e:
                log.info(f"  Continue button attempt {attempt+1}: {str(e)[:60]}")
                time.sleep(1)

        time.sleep(2)
        log_page_state(driver, "After continue without mic/camera")

        # =========================================================================
        # STEP 4: Enter the meeting passcode
        # =========================================================================
        log.info("\n" + "=" * 60)
        log.info("STEP 4: Entering meeting passcode...")
        log.info("=" * 60)

        passcode_entered = False

        # Method A: Find passcode input field
        passcode_xpaths = [
            "//input[@id='input-for-pwd']",
            "//input[@id='passcode']",
            "//input[@id='input-passcode']",
            "//input[@type='password']",
            "//input[contains(@id, 'passcode')]",
            "//input[contains(@id, 'pwd')]",
            "//input[contains(@name, 'passcode')]",
            "//input[contains(@name, 'pwd')]",
            "//input[contains(@placeholder, 'passcode')]",
            "//input[contains(@placeholder, 'Passcode')]",
            "//input[contains(@placeholder, 'password')]",
            "//input[contains(@placeholder, 'Password')]",
        ]

        for xpath in passcode_xpaths:
            try:
                pwd_input = driver.find_element(By.XPATH, xpath)
                if pwd_input.is_displayed():
                    driver.execute_script("arguments[0].scrollIntoView(true);", pwd_input)
                    time.sleep(0.5)
                    pwd_input.clear()
                    pwd_input.send_keys(MEETING_PASSCODE)
                    log.info(f"✓ Entered passcode into: {xpath}")
                    passcode_entered = True
                    break
            except (NoSuchElementException, ElementClickInterceptedException):
                continue

        if not passcode_entered:
            log.warning("⚠ Could not find passcode input with standard selectors")
            log.info("  Trying JavaScript approach...")
            js_pwd = """
            const inputs = document.querySelectorAll('input[type="password"], input[id*="passcode"], input[id*="pwd"]');
            for (const inp of inputs) {
                if (inp.offsetParent !== null) {
                    inp.focus();
                    inp.value = arguments[0];
                    inp.dispatchEvent(new Event('input', {bubbles: true}));
                    inp.dispatchEvent(new Event('change', {bubbles: true}));
                    return true;
                }
            }
            return false;
            """
            try:
                result = driver.execute_script(js_pwd, MEETING_PASSCODE)
                if result:
                    log.info("✓ Entered passcode via JavaScript")
                    passcode_entered = True
            except Exception as e:
                log.warning(f"  JS passcode entry failed: {str(e)[:60]}")

        if not passcode_entered:
            log.error("✗ Could not enter passcode!")
            driver.save_screenshot('/tmp/zoom_bot_output/error_passcode.png')
            sys.exit(1)

        time.sleep(2)

        # =========================================================================
        # STEP 5: Click first "Join" button (after passcode entry)
        # =========================================================================
        log.info("\n" + "=" * 60)
        log.info("STEP 5: Clicking first 'Join' button (after passcode)...")
        log.info("=" * 60)

        first_join_clicked = smart_click_join_button(driver, timeout=15)
        if not first_join_clicked:
            log.warning("⚠ First Join button click uncertain - checking page state...")
        
        time.sleep(4)
        log_page_state(driver, "After first Join click")

        # =========================================================================
        # STEP 6: Click second BLUE "Join" button in the middle of the page
        # =========================================================================
        log.info("\n" + "=" * 60)
        log.info("STEP 6: Clicking second BLUE 'Join' button (in middle of page)...")
        log.info("=" * 60)

        second_join_clicked = smart_click_join_button(driver, timeout=20)
        if not second_join_clicked:
            log.warning("⚠ Second Join button click uncertain - trying extended methods...")
            # Extended: try all possible variants
            time.sleep(3)
            all_strategies = [
                lambda: find_and_click_by_selector(driver, 'xpath', "//button[contains(@class, 'primary')]", timeout=5),
                lambda: find_and_click_by_selector(driver, 'xpath', "//button[contains(@class, 'blue')]", timeout=5),
                lambda: find_and_click_by_selector(driver, 'xpath', "//*[contains(@class, 'primary') and (contains(text(), 'Join') or contains(@aria-label, 'Join'))]", timeout=5),
                lambda: find_and_click_text(driver, 'Join the Meeting', '*', timeout=5),
                lambda: find_and_click_text(driver, 'Join Meeting', '*', timeout=5),
                lambda: find_and_click_text(driver, 'join', 'button', timeout=5),
            ]
            for strat in all_strategies:
                try:
                    if strat():
                        second_join_clicked = True
                        break
                except:
                    continue

        if not second_join_clicked:
            log.warning("⚠ Second Join button click may not have worked. Checking if we're in meeting...")

        time.sleep(5)

        # =========================================================================
        # STEP 7: Verify we're in the meeting
        # =========================================================================
        log.info("\n" + "=" * 60)
        log.info("STEP 7: Verifying meeting entry...")
        log.info("=" * 60)

        in_meeting = False
        for check in range(10):
            if is_meeting_active(driver):
                in_meeting = True
                break
            log.info(f"  Waiting for meeting to load... ({check+1}/10)")
            time.sleep(3)
            log_page_state(driver, f"Meeting check {check+1}")

        if in_meeting:
            log.info("✓ SUCCESS: Bot has joined the meeting!")
        else:
            log.warning("⚠ Could not confirm meeting entry. Continuing anyway...")
            log.info("  Saving diagnostic screenshot...")
            driver.save_screenshot('/tmp/zoom_bot_output/diagnostic_meeting_check.png')
            log.info("  Page source (first 3000 chars):")
            log.info(driver.page_source[:3000])

        # =========================================================================
        # STEP 8: Stay in meeting for specified duration
        # =========================================================================
        log.info("\n" + "=" * 60)
        log.info(f"STEP 8: Staying in meeting for {DURATION_SECONDS} seconds...")
        log.info("=" * 60)

        remaining = DURATION_SECONDS
        while remaining > 0:
            mins, secs = divmod(remaining, 60)
            log.info(f"  ⏱ {mins:02d}:{secs:02d} remaining...")
            
            # Check every 30s if we're still in the meeting
            for _ in range(min(30, remaining)):
                time.sleep(1)
            remaining -= 30
            
            # Periodic check
            if not is_meeting_active(driver) and remaining > 0:
                log.warning("  Bot may have been disconnected from meeting, but continuing...")
                driver.save_screenshot(f'/tmp/zoom_bot_output/check_{int(time.time())}.png')

        # =========================================================================
        # Done
        # =========================================================================
        log.info("\n" + "=" * 60)
        log.info("✓ BOT COMPLETED SUCCESSFULLY")
        log.info(f"  Total time: {DURATION_SECONDS} seconds")
        log.info(f"  Bot name: {PARTICIPANT_NAME}")
        log.info("=" * 60)

    except Exception as e:
        log.error(f"FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        try:
            driver.save_screenshot('/tmp/zoom_bot_output/fatal_error.png')
        except:
            pass
        sys.exit(1)

    finally:
        if driver:
            log.info("Closing browser...")
            try:
                driver.quit()
            except:
                pass


if __name__ == '__main__':
    main()
