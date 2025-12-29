# Notion Equation Fixer

## Problem

Learning technical topics (AI, math, engineering) is most effective when you spend time practicing and applying concepts, not formatting notes. When you paste AI-generated content with LaTeX equations into Notion, the LaTeX code (`$...$` or `$$...$$`) doesn't render automatically—it appears as plain text. You must manually select each equation and convert it to a Notion equation block, which is tedious and wastes time you could spend actually learning. Moreover, as of the time of making this tool, any of the available public solutions (mostly chrome extensions) do not work as expected.

## Solution

This script automates the conversion. Paste AI-generated content with `$...$` or `$$...$$` equations into Notion, run the script, and all equations are converted to proper Notion equation blocks automatically. More time for practice, less time on formatting.

## What it does

- Opens a Notion page in Chrome
- Finds all `$...$` and `$$...$$` patterns in the page
- Selects each one and converts it to a Notion equation block using Ctrl+Shift+E + Enter
- Handles Notion login (you enter the emailed code manually)
- Expands toggle blocks to process nested content

## Setup

```bash
pip install -r requirements.txt
```

You'll need Chrome installed and chromedriver in your PATH.

## Usage

```bash
python fix_notion_eqns.py --url "https://notion.so/your-page-url"
```

### Options

- `--url` (required): Notion page URL
- `--email`: Your Notion email for auto-login (optional; or set NOTION_EMAIL env var)
- `--login-timeout`: Seconds to wait for manual login (default: 600)
- `--headless`: Run headless (not recommended, you need to enter login code)

## How login works

**By default:**
1. Script opens the page in a dedicated Chrome profile
2. If you're already logged into Notion via Google, it just works
3. If not, you can sign in with Google using your account and password
4. Script continues once you're logged in

**With `--email` provided (email/code login):**
1. Script opens the page and automatically enters your email
2. Notion sends you a login code
3. You enter the code in the browser window
4. Script continues once you're logged in

**Without `--email` (manual email/code login):**
1. Script opens the page and waits
2. You manually enter your email in the browser
3. Notion sends you a login code
4. You enter the code in the browser window
5. Script continues once you're logged in


## Notes

- Processes one equation at a time to avoid DOM issues
- Browser stays open for 10 seconds after completion
- Mac uses Cmd+Shift+E, Windows uses Ctrl+Shift+E

⚠️ **Warning:** If you attempt to log in too many times via normal email and temporary Notion login code in a short period, Notion may temporarily block you from logging in (just in the new chrome profile, all logged in sessions outside this profile will remain active). If this happens, you'll need to wait before trying again. Otherwise, login via Google account.

## AI Prompt for Generating Notion-Ready Content

Use this prompt (or similar prompts) with your AI to generate explanations that work perfectly with this script:

```
Subject: <INSERT TOPIC HERE>

Act as an expert AI research scientist with an explanation style similar to Andrew Ng: clear, structured, and intuitive.

Explain **Subject** to a junior AI software engineer with a Computer and Communications Engineering background.

Cover:
- The full conceptual and mathematical flow from input to output (where applicable)
- All key equations involved
- The role, intuition, and significance of each component and equation
- Design choices and tradeoffs

**Math formatting (critical):**
- Wrap ALL mathematical expressions with double dollar signs: $$ ... $$
- This includes variables, symbols, simple expressions, and full equations
- Example: "the loss is $$L = -\sum_i y_i \log \hat{y}_i$$", not "the loss is L = ..."
- Do not use single dollar signs, LaTeX delimiters, or Unicode math characters
- Ensure exactly one opening $$ and one closing $$ per math segment

Include small numeric examples only when they genuinely help understanding.

Keep it concise but complete, and format with headings and equations for direct pasting into Notion.
```
