# Notion Equation Fixer

## Problem

Learning technical topics (AI, math, engineering) is most effective when you spend time practicing and applying concepts, not formatting notes. When you use AI to generate explanations and save them to Notion, manually converting LaTeX equations to Notion's equation blocks is tedious and wastes time you could spend actually learning.

## Solution

This script automates the conversion. Paste AI-generated content with `$...$` or `$$...$$` equations into Notion, run the script, and all equations are converted to proper Notion equation blocks instantly. More time for practice, less time on formatting.

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
python notion_eqn_fix.py --url "https://notion.so/your-page-url" --email your@email.com
```

### Options

- `--url` (required): Notion page URL
- `--email`: Your Notion email for login (or set NOTION_EMAIL env var)
- `--login-timeout`: Seconds to wait for manual login (default: 600)
- `--headless`: Run headless (not recommended, you need to enter login code)

## How login works

1. Script opens the page and enters your email
2. Notion sends you a login code
3. You enter the code in the browser window
4. Script continues once you're logged in

## Notes

- Processes one equation at a time to avoid DOM issues
- Browser stays open for 10 seconds after completion
- Mac uses Cmd+Shift+E, Windows uses Ctrl+Shift+E

## AI Prompt for Generating Notion-Ready Content

Use this prompt with your AI to generate explanations that work perfectly with this script:

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
