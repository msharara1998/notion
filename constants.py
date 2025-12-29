import re

DOLLAR_RE = re.compile(r"\$\$(.+?)\$\$|\$(.+?)\$", re.DOTALL)


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
