#!/usr/bin/env bash
# =============================================================================
# Visual Compliance Gate
# Checks that implemented UI matches the design spec visually
# Run ONCE per phase, after all tasks complete (NOT on every task)
# =============================================================================
#
# Usage:
#   ./visual-compliance-check.sh <dev-server-url> <spec-file> [output-dir] [viewport]
#
# Arguments:
#   dev-server-url   URL of running dev server (e.g. http://localhost:3000)
#   spec-file        Path to design spec markdown file with UI requirements
#   output-dir       Where to save screenshots (default: /tmp/visual-compliance)
#   viewport         "mobile" (390x844) or "desktop" (default: mobile)
#
# Exit codes:
#   0  All checks passed
#   1  One or more checks failed
#   2  Usage error or missing dependencies
#
# Example:
#   ./visual-compliance-check.sh http://localhost:3000 docs/specs/schedule-design.md /tmp/vc-schedule mobile
#
# =============================================================================

set -euo pipefail

# --- Argument Parsing ---------------------------------------------------------

if [ $# -lt 2 ]; then
    echo "Usage: $0 <dev-server-url> <spec-file> [output-dir] [viewport]"
    echo "  viewport: mobile (default) | desktop"
    exit 2
fi

DEV_URL="$1"
SPEC_FILE="$2"
OUTPUT_DIR="${3:-/tmp/visual-compliance}"
VIEWPORT="${4:-mobile}"

# Derive phase name from spec filename (e.g. "schedule-design.md" -> "schedule")
PHASE_NAME=$(basename "$SPEC_FILE" .md | sed 's/-design//g' | sed 's/-spec//g')
PHASE_DIR="$OUTPUT_DIR/$PHASE_NAME"
REPORT_FILE="$OUTPUT_DIR/visual-compliance-report.md"

# --- Dependencies Check -------------------------------------------------------

if ! command -v npx &>/dev/null; then
    echo "ERROR: npx not found. Install Node.js + npm." >&2
    exit 2
fi

if ! npx playwright --version &>/dev/null 2>&1; then
    echo "ERROR: Playwright not found. Install: npm install -D @playwright/test" >&2
    exit 2
fi

if [ ! -f "$SPEC_FILE" ]; then
    echo "ERROR: Spec file not found: $SPEC_FILE" >&2
    exit 2
fi

# --- Setup --------------------------------------------------------------------

mkdir -p "$PHASE_DIR/screenshots"
mkdir -p "$PHASE_DIR/logs"

echo "=================================================================="
echo "  Visual Compliance Gate"
echo "  Phase:    $PHASE_NAME"
echo "  URL:      $DEV_URL"
echo "  Spec:     $SPEC_FILE"
echo "  Output:   $PHASE_DIR"
echo "  Viewport: $VIEWPORT"
echo "=================================================================="

# --- Viewport Config ----------------------------------------------------------

if [ "$VIEWPORT" = "desktop" ]; then
    VIEWPORT_WIDTH=1280
    VIEWPORT_HEIGHT=720
    DEVICE=""
else
    VIEWPORT_WIDTH=390
    VIEWPORT_HEIGHT=844
    DEVICE="iPhone 14"  # Playwright device descriptor for mobile
fi

# --- Extract Checks from Spec -------------------------------------------------
# The spec file should contain a "## Visual Compliance Checks" section
# with bullet points describing UI elements to verify.
#
# Example:
#   ## Visual Compliance Checks
#   - [ ] "Сегодня" tab is visible on main page
#   - [ ] "Завтра" tab is visible on main page
#   - [ ] "Календарь" tab opens date picker overlay
#   - [ ] Filter pills are visible below tabs

echo ""
echo "--- Parsing spec for visual checks..."

# Extract checks from markdown checklist items under the visual compliance section
CHECKS_FILE="$PHASE_DIR/checks.json"

node -e "
const fs = require('fs');
const content = fs.readFileSync('$SPEC_FILE', 'utf8');

// Find ## Visual Compliance Checks or similar section
const sectionRegex = /##\s+(Visual Compliance Checks|UI Verification|Visual Checks)[\s\S]*?(?=##\s+|$)/i;
const section = content.match(sectionRegex);

const checks = [];
if (section) {
    const lines = section[0].split('\n');
    for (const line of lines) {
        const match = line.match(/^\s*[-*]\s*\[?\s*]?\s*(.+)/);
        if (match) {
            checks.push({ description: match[1].trim(), selector: null, status: 'pending' });
        }
    }
}

// If no explicit checks section, try to infer from h3/h4 + bullet patterns
if (checks.length === 0) {
    // Simple heuristic: look for UI element descriptions
    const uiPatterns = [
        /(?:tab|button|card|overlay|modal|pill|input|icon|label|badge|menu|sidebar|header|footer)\s*:?\s*(.+)/gi
    ];
    for (const pattern of uiPatterns) {
        let m;
        while ((m = pattern.exec(content)) !== null) {
            const desc = m[0].trim();
            if (desc.length > 10 && desc.length < 200) {
                checks.push({ description: desc, selector: null, status: 'pending' });
            }
        }
    }
}

// Deduplicate by description
const unique = [];
const seen = new Set();
for (const c of checks) {
    if (!seen.has(c.description)) {
        seen.add(c.description);
        unique.push(c);
    }
}

fs.writeFileSync('$CHECKS_FILE', JSON.stringify(unique, null, 2));
console.log('Parsed ' + unique.length + ' visual checks from spec');
"

if [ ! -f "$CHECKS_FILE" ]; then
    echo "WARNING: No visual checks found in spec. Add a '## Visual Compliance Checks' section." >&2
    # Create empty checks array so the script can still run screenshots
    echo "[]" > "$CHECKS_FILE"
fi

CHECKS_COUNT=$(node -e "console.log(JSON.parse(require('fs').readFileSync('$CHECKS_FILE')).length)")
echo "Found $CHECKS_COUNT visual checks"

# --- Playwright Script --------------------------------------------------------

PLAYWRIGHT_SCRIPT="$PHASE_DIR/run-checks.js"

cat > "$PLAYWRIGHT_SCRIPT" << 'PLAYWRIGHT_EOF'
// Use @playwright/test (installed globally via Dockerfile npm install -g @playwright/test).
// The bare 'playwright' package is nested under @playwright/test/node_modules/ and not
// resolvable via NODE_PATH. @playwright/test re-exports the full Playwright API.
const { chromium } = require('@playwright/test');
const fs = require('fs');

(async () => {
    const args = process.argv.slice(2);
    const devUrl = args[0];
    const checksFile = args[1];
    const phaseDir = args[2];
    const viewportType = args[3] || 'mobile';

    const checks = JSON.parse(fs.readFileSync(checksFile, 'utf8'));
    const results = {
        phase: require('path').basename(phaseDir),
        url: devUrl,
        viewport: viewportType,
        timestamp: new Date().toISOString(),
        screenshots: [],
        checks: [],
        summary: { total: 0, passed: 0, failed: 0, skipped: 0 }
    };

    // Launch browser
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext(
        viewportType === 'mobile'
            ? { viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)' }
            : { viewport: { width: 1280, height: 720 } }
    );
    const page = await context.newPage();

    // Helper: screenshot a state
    async function captureScreenshot(name, fullPage = false) {
        const path = `${phaseDir}/screenshots/${name}.png`;
        await page.screenshot({ path, fullPage });
        results.screenshots.push({ name, path, fullPage });
        console.log(`  Screenshot: ${path}`);
        return path;
    }

    try {
        // 1. Capture initial page load
        console.log('Navigating to ' + devUrl);
        await page.goto(devUrl, { waitUntil: 'networkidle', timeout: 30000 });
        await page.waitForTimeout(1000); // let animations settle
        await captureScreenshot('01-initial-load', true);

        // 2. Run element presence checks
        for (const check of checks) {
            console.log(`\nCheck: ${check.description}`);
            results.summary.total++;

            // Try to infer a selector from description
            let selector = check.selector;
            let inferred = false;

            if (!selector) {
                // Heuristic selector inference
                const desc = check.description.toLowerCase();
                if (desc.includes('tab') || desc.includes('кнопка') || desc.includes('button')) {
                    // Try text-based selector
                    const textMatch = check.description.match(/["'](.+?)["']/);
                    if (textMatch) {
                        selector = `text=${textMatch[1]}`;
                        inferred = true;
                    }
                }
                if (!selector && (desc.includes('input') || desc.includes('поле'))) {
                    selector = 'input, textarea, [contenteditable]';
                    inferred = true;
                }
                if (!selector && (desc.includes('card') || desc.includes('карточка'))) {
                    selector = '[class*="card"], [class*="Card"]';
                    inferred = true;
                }
                if (!selector && (desc.includes('overlay') || desc.includes('модальное'))) {
                    selector = '[role="dialog"], [class*="modal"], [class*="overlay"], [class*="Overlay"]';
                    inferred = true;
                }
                if (!selector) {
                    // Generic fallback: look for any element containing key words
                    const keywords = check.description.split(/\s+/).slice(0, 3);
                    selector = keywords.join(' ');
                    inferred = true;
                }
            }

            let status = 'pending';
            let details = '';
            let screenshotPath = null;

            try {
                if (check.description.toLowerCase().includes('click') ||
                    check.description.toLowerCase().includes('opens') ||
                    check.description.toLowerCase().includes('нажатие')) {
                    // Interaction check: click and verify state change
                    const clickable = await page.locator(selector).first();
                    if (await clickable.count() === 0) {
                        throw new Error(`Element not found: ${selector}`);
                    }
                    await clickable.click();
                    await page.waitForTimeout(500);

                    // Check if something changed (overlay appeared, etc.)
                    const overlaySelector = '[role="dialog"], [class*="modal"], [class*="overlay"], [class*="Overlay"], [class*="popover"]';
                    const overlay = await page.locator(overlaySelector).first();
                    if (await overlay.count() > 0 && await overlay.isVisible()) {
                        status = 'passed';
                        details = 'Overlay/modal appeared after click';
                        screenshotPath = await captureScreenshot(`check-${results.checks.length + 1}-after-click`, true);
                        // Close overlay (try Escape or clicking outside)
                        await page.keyboard.press('Escape');
                        await page.waitForTimeout(300);
                    } else {
                        status = 'failed';
                        details = 'Click did not produce expected overlay/modal';
                        screenshotPath = await captureScreenshot(`check-${results.checks.length + 1}-failed`, true);
                    }
                } else {
                    // Presence check
                    const locator = page.locator(selector);
                    const count = await locator.count();
                    if (count > 0) {
                        const visible = await locator.first().isVisible();
                        if (visible) {
                            status = 'passed';
                            details = `Found ${count} visible element(s)`;
                        } else {
                            status = 'failed';
                            details = `Element exists but not visible`;
                        }
                    } else {
                        status = 'failed';
                        details = `No element found for selector: ${selector}${inferred ? ' (inferred)' : ''}`;
                    }
                    screenshotPath = await captureScreenshot(`check-${results.checks.length + 1}`, false);
                }
            } catch (err) {
                status = 'failed';
                details = `Error: ${err.message}`;
                screenshotPath = await captureScreenshot(`check-${results.checks.length + 1}-error`, false);
            }

            results.checks.push({
                description: check.description,
                selector: selector + (inferred ? ' (inferred)' : ''),
                status,
                details,
                screenshot: screenshotPath
            });

            if (status === 'passed') results.summary.passed++;
            else if (status === 'failed') results.summary.failed++;
            else results.summary.skipped++;

            console.log(`  Result: ${status.toUpperCase()} — ${details}`);
        }

        // 3. Capture final page state
        await captureScreenshot('zz-final-state', true);

    } catch (err) {
        console.error('Fatal error during checks:', err);
        results.fatalError = err.message;
    } finally {
        await browser.close();
    }

    // Save JSON results
    fs.writeFileSync(`${phaseDir}/results.json`, JSON.stringify(results, null, 2));

    // Exit code: 0 if all passed, 1 if any failed
    const exitCode = results.summary.failed > 0 ? 1 : 0;
    process.exit(exitCode);
})();
PLAYWRIGHT_EOF

# --- Run Checks ---------------------------------------------------------------

echo ""
echo "--- Running Playwright checks..."

set +e
npx playwright install chromium 2>/dev/null
set -e

# NODE_PATH makes the globally-installed @playwright/test resolvable by require().
# @playwright/test is installed in /usr/local/lib/node_modules by the Dockerfile,
# and Node's require() does not search global modules unless NODE_PATH is set.
NODE_PATH=/usr/local/lib/node_modules node "$PLAYWRIGHT_SCRIPT" "$DEV_URL" "$CHECKS_FILE" "$PHASE_DIR" "$VIEWPORT"
EXIT_CODE=$?

# --- Generate Markdown Report -------------------------------------------------

echo ""
echo "--- Generating report..."

node -e "
const fs = require('fs');
const results = JSON.parse(fs.readFileSync('$PHASE_DIR/results.json', 'utf8'));

let md = '# Visual Compliance Report\n\n';
md += '**Phase:** ' + results.phase + '  \n';
md += '**URL:** ' + results.url + '  \n';
md += '**Viewport:** ' + results.viewport + '  \n';
md += '**Timestamp:** ' + results.timestamp + '  \n\n';

md += '## Summary\n\n';
md += '| Metric | Count |\n';
md += '|--------|-------|\n';
md += '| Total Checks | ' + results.summary.total + ' |\n';
md += '| Passed | ' + results.summary.passed + ' |\n';
md += '| Failed | ' + results.summary.failed + ' |\n';
md += '| Skipped | ' + results.summary.skipped + ' |\n\n';

if (results.summary.failed === 0) {
    md += '\\u2705 **ALL CHECKS PASSED**\n\n';
} else {
    md += '\\u274c **' + results.summary.failed + ' CHECK(S) FAILED**\n\n';
}

if (results.fatalError) {
    md += '**Fatal Error:** ' + results.fatalError + '\n\n';
}

md += '## Screenshots\n\n';
md += '| Name | File |\n';
md += '|------|------|\n';
for (const ss of results.screenshots) {
    md += '| ' + ss.name + ' | ' + ss.path + ' |\n';
}
md += '\n';

md += '## Element Checks\n\n';
md += '| # | Description | Selector | Status | Details | Screenshot |\n';
md += '|---|-------------|----------|--------|---------|------------|\n';
let i = 1;
for (const check of results.checks) {
    const statusEmoji = check.status === 'passed' ? '\\u2705' : (check.status === 'failed' ? '\\u274c' : '\\u26a0');
    md += '| ' + i + ' | ' + check.description + ' | ' + (check.selector || '-') + ' | ' + statusEmoji + ' ' + check.status + ' | ' + (check.details || '-') + ' | ' + (check.screenshot ? check.screenshot.replace('$PHASE_DIR/', '') : '-') + ' |\n';
    i++;
}
md += '\n';

md += '## Next Steps\n\n';
if (results.summary.failed > 0) {
    md += '**Visual compliance FAILED.**\n\n';
    md += 'Options:\n';
    md += '1. **Fix and re-run:** Address the failing checks, then re-run this gate.\n';
    md += '2. **Override and proceed:** User explicitly approves overriding the failure and continuing to Step 5 (Documentation Commit).\n';
    md += '3. **Abort:** Stop and reassess the implementation plan.\n\n';
    md += '**Screenshots saved to:** \`$PHASE_DIR/screenshots/\`\n';
} else {
    md += '**Visual compliance PASSED.** Proceed to Step 5 (Documentation Commit).\n';
}

fs.writeFileSync('$REPORT_FILE', md);
console.log('Report written to: $REPORT_FILE');
"

# --- Final Output -------------------------------------------------------------

echo ""
echo "=================================================================="
echo "  Visual Compliance Gate Complete"
echo "=================================================================="
echo "  Phase dir:    $PHASE_DIR"
echo "  Screenshots:  $PHASE_DIR/screenshots/"
echo "  Results:      $PHASE_DIR/results.json"
echo "  Report:       $REPORT_FILE"
echo ""

if [ $EXIT_CODE -eq 0 ]; then
    echo "  Result: ALL CHECKS PASSED"
else
    echo "  Result: $CHECKS_COUNT checks, $(node -e "const r=JSON.parse(require('fs').readFileSync('$PHASE_DIR/results.json')); console.log(r.summary.passed+' passed, '+r.summary.failed+' failed')")"
    echo ""
    echo "  SOFT BLOCK: Do NOT proceed to Step 5 until resolved or user overrides."
fi

echo "=================================================================="

exit $EXIT_CODE
