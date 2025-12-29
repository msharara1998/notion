"""Notion equation fixer automation script.

This script automates the process of converting LaTeX equations in Notion pages
from plain text ($$...$$) format to proper Notion equation blocks using Selenium
WebDriver. It handles login, expands toggle blocks, finds all equation patterns,
and converts them using keyboard shortcuts.
"""

import argparse
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import List, Dict, Any

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# -----------------------------
# Configuration / Utilities
# -----------------------------

@dataclass
class MatchRef:
    """A reference to a single $$...$$ match inside the DOM.
    
    Describes the location of a LaTeX equation match at the text-node level
    within the DOM tree, allowing precise selection and manipulation.
    
    Attributes:
        xpath: XPath expression to locate the containing element.
        node_index: Index of the text node within the element.
        start: Starting character offset within the text node.
        end: Ending character offset within the text node.
    """
    xpath: str
    node_index: int
    start: int
    end: int


DOLLAR_RE = re.compile(r"\$\$(.+?)\$\$|\$(.+?)\$", re.DOTALL)


def is_mac() -> bool:
    """Check if the current operating system is macOS.
    
    Returns:
        True if running on macOS, False otherwise.
    """
    return sys.platform == "darwin"


def build_driver(headless: bool = False) -> webdriver.Chrome:
    """Build and configure a Chrome WebDriver instance.
    
    Creates a Chrome WebDriver with options optimized for Notion automation,
    including disabled infobars, notifications, and optional headless mode.
    
    Args:
        headless: If True, run Chrome in headless mode. Not recommended for
            workflows requiring manual code entry. Defaults to False.
    
    Returns:
        Configured Chrome WebDriver instance.
    """
    options = webdriver.ChromeOptions()
    options.add_argument("--disable-infobars")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    # options.add_argument("--disable-blink-features=AutomationControlled")  # optional; may or may not help

    if headless:
        # Not recommended for manual code entry
        options.add_argument("--headless=new")

    return webdriver.Chrome(options=options)


# -----------------------------
# Core JS helpers (page-safe)
# -----------------------------

JS_EXPAND_TOGGLES = r"""
(function(){
  const root = document.querySelector('.notion-page-content');
  if (!root) return;

  // Expand only collapsed toggles inside the page content (avoid sidebar/topbar clutter)
  const buttons = Array.from(root.querySelectorAll('[role="button"][aria-expanded="false"]'));
  buttons.forEach(b => { try { b.click(); } catch(e) {} });
})();
"""

JS_FIND_MATCHES = r"""
return (function(){
  // STRICT: only search inside the actual page canvas (avoid scanning the whole Notion UI)
  const root = document.querySelector('.notion-page-content');
  if (!root) return [];

  // Only scan Notion leaf text blocks, not all div/span/etc (prevents "clutter")
  const candidates = Array.from(root.querySelectorAll('[data-content-editable-leaf="true"]'))
    .filter(el => el && el.offsetParent !== null); // visible only

  function getXPath(el){
    if (el.id) return '//*[@id="' + el.id + '"]';
    const parts = [];
    while (el && el.nodeType === Node.ELEMENT_NODE) {
      let nb = 0;
      let idx = 0;
      const sibs = el.parentNode ? el.parentNode.childNodes : [];
      for (let i=0; i<sibs.length; i++) {
        const sib = sibs[i];
        if (sib.nodeType === Node.ELEMENT_NODE && sib.nodeName === el.nodeName) {
          nb++;
          if (sib === el) idx = nb;
        }
      }
      const tagName = el.nodeName.toLowerCase();
      const part = nb > 1 ? tagName + '[' + idx + ']' : tagName;
      parts.unshift(part);
      el = el.parentNode;
    }
    return '/' + parts.join('/');
  }

  // Capture nested text nodes (toggle content is often nested under spans)
  function getTextNodes(el){
    const out = [];
    const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null);
    let n;
    while ((n = w.nextNode())) out.push(n);
    return out;
  }

  const results = [];
  const re = /\$\$(.+?)\$\$|\$(.+?)\$/gs;

  for (const el of candidates) {
    // Quick skip to avoid expensive walking when block doesn't include $ or $$
    const t = el.innerText || "";
    if (t.indexOf('$') === -1) continue;

    const textNodes = getTextNodes(el);
    if (!textNodes.length) continue;

    for (let ti = 0; ti < textNodes.length; ti++) {
      const tn = textNodes[ti];
      const s = tn.nodeValue || '';
      if (s.indexOf('$') === -1) continue;

      re.lastIndex = 0;
      let m;
      while ((m = re.exec(s)) !== null) {
        const start = m.index;
        const end = start + m[0].length;
        results.push({
          xpath: getXPath(el),
          nodeIndex: ti,
          start,
          end,
          preview: s.slice(Math.max(0, start-10), Math.min(s.length, end+10))
        });
      }
    }
  }

  return results;
})();
"""

JS_SELECT_MATCH = r"""
return (function(args){
  const xpath = args.xpath;
  const nodeIndex = args.nodeIndex;
  const start = args.start;
  const end = args.end;

  function elementByXPath(path){
    const res = document.evaluate(path, document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null);
    return res.singleNodeValue;
  }

  const el = elementByXPath(xpath);
  if (!el) return {ok:false, error:"Element not found for XPath"};

  try { el.scrollIntoView({block:'center', inline:'nearest'}); } catch(e) {}

  // Must match JS_FIND_MATCHES text node collection (TreeWalker)
  const textNodes = [];
  const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null);
  let n;
  while ((n = w.nextNode())) textNodes.push(n);

  if (nodeIndex < 0 || nodeIndex >= textNodes.length) {
    return {ok:false, error:"Text node index out of range"};
  }

  const tn = textNodes[nodeIndex];
  const val = tn.nodeValue || "";
  if (start < 0 || end > val.length || start >= end) {
    return {ok:false, error:"Offsets invalid for text node"};
  }

  const range = document.createRange();
  range.setStart(tn, start);
  range.setEnd(tn, end);

  const sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);

  // Focus closest contenteditable ancestor so shortcuts apply
  let focusEl = el;
  while (focusEl && focusEl.nodeType === Node.ELEMENT_NODE) {
    const ce = focusEl.getAttribute && focusEl.getAttribute('contenteditable');
    if (ce === "true") break;
    focusEl = focusEl.parentElement;
  }
  if (focusEl) focusEl.focus();

  return {ok:true};
})(arguments[0]);
"""


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
    manually enter the verification code sent to their email.
    
    Args:
        driver: Chrome WebDriver instance.
        email: Email address to use for Notion login.
        timeout_total: Maximum seconds to wait for manual code entry and
            sign-in completion. Defaults to 600 (10 minutes).
    
    Raises:
        ValueError: If email is empty or None.
        TimeoutError: If sign-in doesn't complete within timeout_total.
    """
    if not email:
        raise ValueError("Email is required for enhanced sign-in. Provide --email or NOTION_EMAIL.")

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

    # Fill + submit
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
