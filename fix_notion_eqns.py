"""Notion equation fixer automation script.

This script automates the process of converting LaTeX equations in Notion pages
from plain text ($$...$$) format to proper Notion equation blocks using Selenium
WebDriver. It handles login, expands toggle blocks, finds all equation patterns,
and converts them using keyboard shortcuts.
"""

import argparse
import os
import time
from typing import List, Dict, Any

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from utils import is_mac
from constants import (
    JS_FIND_MATCHES,
    JS_SELECT_MATCH,
    JS_EXPAND_TOGGLES
)


def build_driver(headless: bool = False) -> webdriver.Chrome:
    """Build and configure a Chrome WebDriver instance.
    
    Creates a Chrome WebDriver with options optimized for Notion automation,
    including disabled infobars, notifications, and optional headless mode.
    Uses a temporary browser session for clean automation.
    
    Args:
        headless: If True, run Chrome in headless mode. Not recommended for
            workflows requiring manual code entry. Defaults to False.
    
    Returns:
        Configured Chrome WebDriver instance.
    """
    opts = webdriver.ChromeOptions()
    opts.add_argument("--disable-infobars")
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-notifications")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-extensions")

    # Make browser appear non-automated (helps with Google OAuth)
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option('useAutomationExtension', False)

    if headless:
        # Not recommended for manual code entry
        opts.add_argument("--headless=new")

    driver = webdriver.Chrome(options=opts)

    # Hide webdriver property to avoid detection
    try:
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": driver.execute_script("return navigator.userAgent").replace('HeadlessChrome', 'Chrome')
        })
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    except Exception:
        # Non-fatal; continue without stealth tweaks if CDP not available
        pass

    return driver




# -----------------------------
# Notion automation flow
# -----------------------------

def wait_for_page_canvas(driver: webdriver.Chrome, timeout: int = 60) -> None:
    """Wait until the Notion page canvas is present and ready.
    
    Waits for the page to finish loading and for the Notion page content
    element to be present in the DOM, indicating successful page load.
    
    Args:
        driver: Chrome WebDriver instance.
        timeout: Maximum seconds to wait for the page canvas. Defaults to 60.
    
    Raises:
        TimeoutException: If the page canvas doesn't appear within timeout.
    """
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
    WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".notion-page-content"))
    )


def on_login_gate(driver: webdriver.Chrome) -> bool:
    """Check if the current page is the Notion login gate.
    
    Uses heuristics to determine if we're on the 'Sign in to see this page'
    screen by checking for email input fields and absence of page content.
    
    Args:
        driver: Chrome WebDriver instance.
    
    Returns:
        True if on the login gate, False otherwise.
    """
    try:
        # The login gate usually has an email input and does NOT have notion-page-content
        has_canvas = len(driver.find_elements(By.CSS_SELECTOR, ".notion-page-content")) > 0
        if has_canvas:
            return False

        email_inputs = driver.find_elements(
            By.CSS_SELECTOR,
            'input[type="email"], input[name="email"], input[autocomplete="email"], input[placeholder*="email" i]'
        )
        return len(email_inputs) > 0
    except Exception:
        return False


def enter_email_and_wait_for_manual_code(driver: webdriver.Chrome, email: str, timeout_total: int = 600) -> None:
    """Enter email into Notion login and wait for manual code entry.
    
    Automates the first step of Notion's email-based authentication by entering
    the email address and submitting the form. Then waits for the user to
    manually enter the verification code sent to their email. If no email is
    provided, waits for manual email entry as well.
    
    Args:
        driver: Chrome WebDriver instance.
        email: Email address to use for Notion login. If empty, waits for
            manual email entry.
        timeout_total: Maximum seconds to wait for manual code entry and
            sign-in completion. Defaults to 600 (10 minutes).
    
    Raises:
        TimeoutError: If sign-in doesn't complete within timeout_total.
    """
    # Try to find the email input (Notion sometimes uses type=text with an email placeholder)
    email_sel = (
        'input[type="email"], input[name="email"], input[autocomplete="email"], '
        'input[placeholder*="email" i], input[aria-label*="email" i]'
    )

    try:
        email_box = WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, email_sel))
        )
    except Exception:
        # If we can't see it, maybe already logged in or different auth flow
        return

    if email:
        # Auto-fill email if provided
        try:
            email_box.click()
            email_box.clear()
        except Exception:
            pass

        email_box.send_keys(email)
        email_box.send_keys(Keys.ENTER)

        print("\n✅ Email entered. Notion should send you a login code.")
        print("➡️  Please enter the code manually in the opened browser window.")
        print("   As soon as you're signed in and the page loads, Selenium will continue.\n")
    else:
        # Wait for manual email entry
        print("\n➡️  Please enter your email manually in the opened browser window.")
        print("   After submitting, Notion will send you a login code to enter.")
        print("   As soon as you're signed in and the page loads, Selenium will continue.\n")

    # Wait until the page canvas appears (meaning login is complete and we're in the page)
    end_time = time.time() + timeout_total
    last_hint_time = 0.0

    while time.time() < end_time:
        # Success condition
        if len(driver.find_elements(By.CSS_SELECTOR, ".notion-page-content")) > 0:
            return

        # Print occasional hints so it doesn't feel stuck
        if time.time() - last_hint_time > 60:
            last_hint_time = time.time()
            # If we still see an email box, user might not have proceeded
            if len(driver.find_elements(By.CSS_SELECTOR, email_sel)) > 0:
                print("Still on email screen—if needed, press Enter after typing the email / choose the email field.")
            else:
                print("Waiting for you to enter the emailed code and complete sign-in...")

        time.sleep(0.5)

    raise TimeoutError("Timed out waiting for Notion sign-in to complete (no page canvas detected).")


def ensure_logged_in(driver: webdriver.Chrome, email: str, timeout_total: int = 600) -> None:
    """Ensure the user is logged into Notion.
    
    Checks if the current page is the login gate. If so, automates email entry
    and waits for manual verification code entry. If already logged in, proceeds
    immediately after confirming the page canvas is loaded.
    
    Args:
        driver: Chrome WebDriver instance.
        email: Email address to use for Notion login if needed.
        timeout_total: Maximum seconds to wait for manual sign-in completion.
            Defaults to 600 (10 minutes).
    
    Raises:
        TimeoutError: If login doesn't complete within timeout_total.
    """
    # Give the initial view a moment to settle
    time.sleep(1.0)

    if on_login_gate(driver):
        enter_email_and_wait_for_manual_code(driver, email=email, timeout_total=timeout_total)

    # Final wait for the page canvas
    wait_for_page_canvas(driver, timeout=120)


def send_shortcut_and_enter(driver: webdriver.Chrome) -> None:
    """Send the equation shortcut and Enter key to Notion.
    
    Sends Ctrl+Shift+E (or Cmd+Shift+E on macOS) followed by Enter to convert
    selected text into a Notion equation block. Includes short delays to allow
    Notion to process the commands.
    
    Args:
        driver: Chrome WebDriver instance.
    """
    actions = ActionChains(driver)
    mod = Keys.COMMAND if is_mac() else Keys.CONTROL
    actions.key_down(mod).key_down(Keys.SHIFT).send_keys("e").key_up(Keys.SHIFT).key_up(mod).perform()
    time.sleep(0.25)
    ActionChains(driver).send_keys(Keys.ENTER).perform()
    time.sleep(0.35)


def process_all_matches(driver: webdriver.Chrome, max_passes: int = 2000) -> int:
    """Process all LaTeX equation matches on the page.
    
    Iteratively finds and converts all $$...$$ and $...$ patterns in the
    Notion page to proper equation blocks. Expands toggle blocks to ensure
    hidden content is processed. Processes one match at a time to avoid
    DOM shifting issues.
    
    Args:
        driver: Chrome WebDriver instance.
        max_passes: Maximum number of iterations to prevent infinite loops.
            Defaults to 2000.
    
    Returns:
        Total number of equation matches successfully processed.
    """
    processed = 0

    for _pass in range(max_passes):
        # Expand toggles inside the page (prevents missing toggle bodies)
        driver.execute_script(JS_EXPAND_TOGGLES)
        time.sleep(0.15)

        matches: List[Dict[str, Any]] = driver.execute_script(JS_FIND_MATCHES)
        if not matches:
            break

        # Process only the first match each iteration to avoid DOM shifting issues
        m = matches[0]
        sel_res = driver.execute_script(JS_SELECT_MATCH, {
            "xpath": m["xpath"],
            "nodeIndex": m["nodeIndex"],
            "start": m["start"],
            "end": m["end"],
        })

        if not sel_res or not sel_res.get("ok"):
            time.sleep(0.2)
            continue

        send_shortcut_and_enter(driver)
        processed += 1

        # Let Notion apply updates
        time.sleep(0.6)

    return processed


def main() -> None:
    """Main entry point for the Notion equation fixer script.
    
    Parses command-line arguments, initializes the WebDriver, handles login,
    processes all equation matches, and cleans up resources.
    
    Raises:
        Various exceptions from Selenium WebDriver or the helper functions.
    """
    ap = argparse.ArgumentParser(description="Notion $$...$$ selector + Ctrl+Shift+E + Enter automation.")
    ap.add_argument("--url", required=True, help="Notion page URL")
    ap.add_argument("--headless", action="store_true", help="Run headless (not recommended for manual code entry)")
    ap.add_argument("--email", default=os.environ.get("NOTION_EMAIL", ""), help="Email to enter on Notion login gate")
    ap.add_argument("--login-timeout", type=int, default=600, help="Seconds to wait for manual code entry/sign-in")
    args = ap.parse_args()

    driver = build_driver(headless=args.headless)
    try:
        driver.get(args.url)

        # Enhanced sign-in: enter email automatically, user enters the emailed code manually, then continue
        ensure_logged_in(driver, email=args.email, timeout_total=args.login_timeout)

        count = process_all_matches(driver)
        print(f"\nDone. Processed {count} $$...$$ occurrence(s).")

        print("Browser will remain open for 10 seconds...")
        time.sleep(10)

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
