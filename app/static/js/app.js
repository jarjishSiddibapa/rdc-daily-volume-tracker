/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   Daily Volume Tracker — Main Client-Side JavaScript
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */

// ── Utility ────────────────────────────────────────────────────────────────────

function fmt(num) {
    if (num === null || num === undefined) return '0';
    return Number(num).toLocaleString('en-IN', { maximumFractionDigits: 2 });
}

function fmtDec(num) {
    if (num === null || num === undefined) return '0';
    return Number(num).toLocaleString('en-IN', { maximumFractionDigits: 2 });
}

function pctClass(pctStr) {
    if (!pctStr) return '';
    const val = parseInt(pctStr);
    if (isNaN(val)) return '';
    if (val > 0) return 'positive';
    if (val < 0) return 'negative';
    return '';
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    const icons = { success: 'check_circle', error: 'error', info: 'info', warning: 'warning' };
    // Use escHtml for message to prevent HTML injection from server error strings
    const iconEl = document.createElement('span');
    iconEl.className = 'material-icons-round';
    iconEl.textContent = icons[type] || 'info';
    toast.appendChild(iconEl);
    const msgEl = document.createElement('span');
    msgEl.textContent = message;
    toast.appendChild(msgEl);
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        toast.style.transition = '0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// ── Premium confirm dialog ─────────────────────────────────────────────────────
window._dvtConfirmResolve = null;

/**
 * Async confirm dialog — replaces window.confirm().
 * @param {string} message   - Body text
 * @param {string} [title]   - Dialog title
 * @param {string} [okLabel] - OK button label
 * @returns {Promise<boolean>}
 */
function showConfirm(message, title = 'Confirm Action', okLabel = 'Delete') {
    return new Promise(resolve => {
        const overlay = document.getElementById('confirmOverlay');
        const msgEl   = document.getElementById('confirmMessage');
        const titleEl = document.getElementById('confirmTitle');
        const okBtn   = document.getElementById('confirmOkBtn');
        if (!overlay) { resolve(window.confirm(message)); return; }

        msgEl.textContent   = message;
        titleEl.textContent = title;
        okBtn.textContent   = okLabel;

        window._dvtConfirmResolve = (result) => {
            overlay.classList.remove('show');
            window._dvtConfirmResolve = null;
            resolve(result);
        };
        overlay.classList.add('show');
        // Focus Cancel button by default (safer UX)
        setTimeout(() => document.getElementById('confirmCancelBtn')?.focus(), 50);
    });
}

function _confirmOverlayClick(e) {
    if (e.target === document.getElementById('confirmOverlay')) {
        window._dvtConfirmResolve && window._dvtConfirmResolve(false);
    }
}

document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && window._dvtConfirmResolve) window._dvtConfirmResolve(false);
});

// ── Lightweight loading feedback ─────────────────────────────────────────────
// One composited progress line replaces continuous scroll/card animation. It
// starts on the same event frame as a click and costs nothing while the UI is idle.
const DVTLoading = (() => {
    let pending = 0;
    let hideTimer = null;
    const buttonState = new WeakMap();
    const busyButtons = new Set();

    function setProgress(visible) {
        const progress = document.getElementById('pageProgress');
        if (!progress) return;
        document.documentElement.classList.toggle('is-loading', visible);
        progress.setAttribute('aria-hidden', visible ? 'false' : 'true');
    }

    function setButton(button, busy) {
        if (!(button instanceof HTMLButtonElement)) return;
        const current = buttonState.get(button) || { count: 0, wasDisabled: button.disabled };
        current.count += busy ? 1 : -1;
        current.count = Math.max(0, current.count);
        buttonState.set(button, current);
        button.classList.toggle('is-busy', current.count > 0);
        button.setAttribute('aria-busy', current.count > 0 ? 'true' : 'false');
        button.disabled = current.count > 0 ? true : current.wasDisabled;
        if (current.count > 0) {
            busyButtons.add(button);
        } else {
            busyButtons.delete(button);
            buttonState.delete(button);
        }
    }

    return {
        start(button) {
            clearTimeout(hideTimer);
            pending += 1;
            setProgress(true);
            setButton(button, true);
        },
        stop(button) {
            pending = Math.max(0, pending - 1);
            setButton(button, false);
            if (pending === 0) {
                hideTimer = setTimeout(() => setProgress(false), 140);
            }
        },
        reset() {
            clearTimeout(hideTimer);
            pending = 0;
            busyButtons.forEach((button) => {
                const state = buttonState.get(button);
                button.classList.remove('is-busy');
                button.setAttribute('aria-busy', 'false');
                button.disabled = state ? state.wasDisabled : false;
                buttonState.delete(button);
            });
            busyButtons.clear();
            setProgress(false);
        },
    };
})();

window.addEventListener('pageshow', () => DVTLoading.reset());

let _lastAction = null;
document.addEventListener('pointerdown', (event) => {
    const button = event.target.closest && event.target.closest('button');
    _lastAction = button ? { button, at: performance.now() } : null;
}, true);

// Give full-page navigation immediate visual acknowledgement. Modified clicks,
// downloads, external links, and new-tab actions keep their normal behavior.
document.addEventListener('click', (event) => {
    const link = event.target.closest && event.target.closest('a[href]');
    if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey ||
        event.ctrlKey || event.shiftKey || event.altKey || link.target || link.download) return;
    const target = new URL(link.href, window.location.href);
    if (target.origin !== window.location.origin ||
        (target.pathname === window.location.pathname && target.search === window.location.search)) return;
    DVTLoading.start();
}, true);

document.addEventListener('submit', (event) => {
    if (event.defaultPrevented) return;
    const submitter = event.submitter instanceof HTMLButtonElement ? event.submitter : null;
    DVTLoading.start(submitter);
});

const _inflightGets = new Map();
const _memoryGetCache = new Map();

async function apiCall(url, options = {}) {
    // Prepend URL prefix for obfuscated routing
    const prefix = window.URL_PREFIX || '';
    const fullUrl = url.startsWith('http') ? url : prefix + url;
    const {
        dvtCacheMs = 0,
        dvtForce = false,
        dvtButton = null,
        ...fetchOptions
    } = options;
    const method = (fetchOptions.method || 'GET').toUpperCase();
    const cacheKey = method === 'GET' ? fullUrl : null;

    if (cacheKey && !dvtForce) {
        const cached = _memoryGetCache.get(cacheKey);
        if (cached && cached.expiresAt > Date.now()) return cached.data;
        if (_inflightGets.has(cacheKey)) return _inflightGets.get(cacheKey);
    }

    const recentButton = _lastAction && performance.now() - _lastAction.at < 800
        ? _lastAction.button
        : null;
    const loadingButton = dvtButton || recentButton;
    _lastAction = null;
    DVTLoading.start(loadingButton);

    const headers = new Headers(fetchOptions.headers || {});
    if (!headers.has('Accept')) headers.set('Accept', 'application/json');
    fetchOptions.headers = headers;

    let timeoutId = null;
    if (!fetchOptions.signal) {
        const controller = new AbortController();
        fetchOptions.signal = controller.signal;
        timeoutId = setTimeout(() => controller.abort(), 30000);
    }

    const requestPromise = (async () => {
    try {
        const resp = await fetch(fullUrl, fetchOptions);

        // Redirect to login if session expired
        if (resp.status === 401 || (resp.redirected && resp.url.includes('/login'))) {
            window.location.href = prefix + '/login';
            return;
        }

        const contentType = resp.headers.get('content-type') || '';
        const data = contentType.includes('application/json')
            ? await resp.json()
            : { error: await resp.text() || `HTTP ${resp.status}` };
        if (!resp.ok) {
            throw new Error(data.error || `HTTP ${resp.status}`);
        }
        if (cacheKey && dvtCacheMs > 0) {
            _memoryGetCache.set(cacheKey, { data, expiresAt: Date.now() + dvtCacheMs });
        }
        return data;
    } catch (err) {
        const message = err.name === 'AbortError'
            ? 'The server took too long to respond. Please try again.'
            : err.message;
        showToast(message, 'error');
        throw err;
    } finally {
        if (timeoutId) clearTimeout(timeoutId);
        DVTLoading.stop(loadingButton);
        if (cacheKey) _inflightGets.delete(cacheKey);
    }
    })();

    if (cacheKey) _inflightGets.set(cacheKey, requestPromise);
    return requestPromise;
}

// ── Sidebar Toggle ─────────────────────────────────────────────────────────────

function closeSidebar() {
    const sidebar  = document.getElementById('sidebar');
    const backdrop = document.getElementById('sidebarBackdrop');
    if (sidebar)  sidebar.classList.remove('open');
    if (backdrop) backdrop.classList.remove('show');
}

document.addEventListener('DOMContentLoaded', () => {
    const menuToggle = document.getElementById('menuToggle');
    const sidebar    = document.getElementById('sidebar');
    const backdrop   = document.getElementById('sidebarBackdrop');

    if (menuToggle && sidebar) {
        menuToggle.addEventListener('click', () => {
            const isOpen = sidebar.classList.toggle('open');
            if (backdrop) backdrop.classList.toggle('show', isOpen);
        });

        // Close when a nav link is tapped on mobile
        sidebar.querySelectorAll('.nav-item').forEach(link => {
            link.addEventListener('click', () => {
                if (window.innerWidth <= 1024) closeSidebar();
            });
        });

        // Close when backdrop is tapped
        if (backdrop) backdrop.addEventListener('click', closeSidebar);

        // Close on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') closeSidebar();
        });
    }

    // ERP Sync button in sidebar
    const syncBtn = document.getElementById('syncStatus');
    if (syncBtn) {
        syncBtn.addEventListener('click', syncERP);
    }

    // ── Theme Toggle ────────────────────────────────────────────────────
    const themeToggle = document.getElementById('themeToggle');
    const themeIcon = document.getElementById('themeIcon');
    if (themeToggle && themeIcon) {
        // Set icon based on current theme
        const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
        themeIcon.textContent = currentTheme === 'dark' ? 'light_mode' : 'dark_mode';

        themeToggle.addEventListener('click', () => {
            const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
            const newTheme = isDark ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('dvt-theme', newTheme);
            themeIcon.textContent = newTheme === 'dark' ? 'light_mode' : 'dark_mode';

            // Swap flatpickr theme stylesheet
            const fpThemeLink = document.getElementById('fpThemeLink');
            if (fpThemeLink) {
                fpThemeLink.href = newTheme === 'dark'
                    ? 'https://cdn.jsdelivr.net/npm/flatpickr/dist/themes/dark.css'
                    : 'https://cdn.jsdelivr.net/npm/flatpickr/dist/themes/light.css';
            }
        });
    }

    // ── Auto-logout on tab close (without affecting in-app navigation) ─────────
    if (window.CURRENT_USER_ROLE) {
        let isInternalNav = false;

        const markInternalNav = (targetUrl) => {
            try {
                const url = new URL(targetUrl, window.location.href);
                if (url.origin === window.location.origin) {
                    isInternalNav = true;
                    // Reset shortly after navigation starts
                    setTimeout(() => { isInternalNav = false; }, 1000);
                }
            } catch {
                // Ignore malformed URLs
            }
        };

        // Mark internal navigation for links
        document.addEventListener('click', (e) => {
            const link = e.target.closest && e.target.closest('a[href]');
            if (link && !link.target) {
                markInternalNav(link.href);
            }
        }, true);

        // Mark internal navigation for form submissions
        document.addEventListener('submit', (e) => {
            const form = e.target;
            if (form && form.action) {
                markInternalNav(form.action);
            }
        }, true);

        // On tab close / navigation away, log out unless it's an internal nav
        window.addEventListener('beforeunload', () => {
            if (!window.CURRENT_USER_ROLE) return;
            if (isInternalNav) return;
            // MUST include URL_PREFIX — sendBeacon does not follow 302 redirects,
            // so '/logout' without the prefix silently fails every time.
            const url = (window.URL_PREFIX || '') + '/logout';
            try {
                if (navigator.sendBeacon) {
                    const blob = new Blob([], { type: 'text/plain' });
                    navigator.sendBeacon(url, blob);
                } else {
                    fetch(url, { method: 'POST', keepalive: true }).catch(() => { });
                }
            } catch {
                // Best-effort only
            }
        });
    }

    // ── Auto-refresh for dashboard / report ─────────────────────────────
    // Refresh every 5 minutes while the page is open
    const AUTO_REFRESH_MS = 5 * 60 * 1000;
    if (document.getElementById('dashboardBody') && typeof loadDashboard === 'function') {
        setInterval(() => {
            try {
                loadDashboard();
            } catch { }
        }, AUTO_REFRESH_MS);
    }
    if (document.getElementById('reportBody') && typeof loadReport === 'function') {
        setInterval(() => {
            try {
                loadReport();
            } catch { }
        }, AUTO_REFRESH_MS);
    }

    // ── Flatpickr Calendar Pickers ──────────────────────────────────────
    if (typeof flatpickr !== 'undefined') {
        const fpTheme = {
            disableMobile: true,
        };

        // Date picker for reportDate (used on both dashboard and report pages)
        const reportDate = document.getElementById('reportDate');
        if (reportDate) {
            flatpickr(reportDate, {
                ...fpTheme,
                dateFormat: 'Y-m-d',
                defaultDate: new Date(),
                onChange: function () {
                    if (typeof loadDashboard === 'function' && document.getElementById('dashboardBody')) {
                        loadDashboard();
                    } else if (typeof loadReport === 'function' && document.getElementById('reportBody')) {
                        loadReport();
                    }
                },
            });
        }

        // Targets month picker — restricted to current month + the next 12 months.
        // This lets an admin set an entire year's budget in one sitting, rather
        // than waiting month-by-month (previously capped at current + next month).
        const targetMonth = document.getElementById('targetMonth');
        if (targetMonth) {
            const _now = new Date();
            // First day of current month
            const _minDate = new Date(_now.getFullYear(), _now.getMonth(), 1);
            // Last day of the 12th month ahead (day=0 of month+13 rolls back to last day of month+12)
            const _maxDate = new Date(_now.getFullYear(), _now.getMonth() + 13, 0);
            flatpickr(targetMonth, {
                ...fpTheme,
                plugins: [new monthSelectPlugin({ shorthand: false, dateFormat: 'Y-m', altFormat: 'F Y' })],
                defaultDate: _now,
                minDate: _minDate,
                maxDate: _maxDate,
                onChange: function () { loadTargets(); },
            });
        }
    }
});

// ── ERP Sync ───────────────────────────────────────────────────────────────────

async function syncERP() {
    const syncBtn = document.getElementById('syncStatus');
    if (syncBtn) {
        syncBtn.classList.add('syncing');
    }
    showToast('Syncing with ERP...', 'info');
    try {
        const result = await apiCall('/api/sync-erp', { method: 'POST' });
        showToast(`ERP Sync complete: ${result.synced_daily} daily entries, ${result.synced_monthly} monthly - ${(result.months || []).join(', ')}`, 'success');
        // Reload dashboard if on that page
        if (typeof loadDashboard === 'function' && document.getElementById('dashboardBody')) {
            loadDashboard({ force: true });
        }
    } catch (err) {
        showToast('ERP Sync failed. Oracle may be unreachable.', 'error');
    } finally {
        if (syncBtn) syncBtn.classList.remove('syncing');
    }
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// DASHBOARD
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

function beginTableLoad(body, colspan, label) {
    if (!body) return;
    const card = body.closest('.card');
    if (card) {
        card.classList.add('is-updating');
        card.setAttribute('aria-busy', 'true');
    }
    if (body.dataset.loaded === 'true') return;
    body.innerHTML = `<tr><td colspan="${colspan}" class="loading">
        <div class="table-skeleton" aria-hidden="true">
            <span></span><span></span><span></span>
        </div>
        <span>${escHtml(label)}</span>
    </td></tr>`;
}

function endTableLoad(body) {
    const card = body && body.closest('.card');
    if (!card) return;
    card.classList.remove('is-updating');
    card.setAttribute('aria-busy', 'false');
}

async function loadDashboard({ force = false } = {}) {
    const dateInput = document.getElementById('reportDate');
    if (!dateInput) return;
    const dateVal = dateInput.value;
    const params = new URLSearchParams();
    if (dateVal) params.set('date', dateVal);
    if (force) params.set('refresh', '1');
    const query = params.toString();
    const url = `/api/dashboard${query ? `?${query}` : ''}`;

    const body = document.getElementById('dashboardBody');
    beginTableLoad(body, 14, 'Loading dashboard');

    try {
        const data = await apiCall(url, { dvtCacheMs: 15000, dvtForce: force });
        renderDashboard(data);
    } catch (err) {
        if (body.dataset.loaded !== 'true') {
            body.innerHTML = '<tr><td colspan="14" style="text-align:center;padding:40px;color:var(--accent-red)">Failed to load data</td></tr>';
        }
    } finally {
        endTableLoad(body);
    }
}

function renderDashboard(data) {
    const meta = data.meta;
    const ct = data.company_total;

    // KPI cards
    const el = (id) => document.getElementById(id);
    el('kpiDaily').textContent = fmt(ct.daily_volume);
    el('kpiInvoiced').textContent = fmt(ct.invoiced_qty);
    el('kpiMTD').textContent = fmt(ct.mtd_volume);
    el('kpiExtrap').textContent = fmt(ct.extrapolated);
    el('kpiTarget').textContent = fmt(ct.target);
    el('kpiBudget').textContent = ct.pct_extrap_vs_budget;
    el('kpiBudgetSub').textContent = `Extrap. vs Target`;
    el('kpiPlants').textContent = meta.active_plants;
    el('kpiVolPlant').textContent = `Vol/Plant: ${fmt(meta.vol_per_plant)}`;

    // Summary banner
    el('summaryBanner').textContent = meta.summary;

    // Date header
    if (meta.yesterday) {
        const d = new Date(meta.yesterday);
        const day = d.getDate();
        const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        const dateLabel = `${day}-${monthNames[d.getMonth()]}`;
        el('thDate').innerHTML = `Produced Quantity<br>${dateLabel}`;
        el('thInvDate').innerHTML = `Invoiced Quantity<br>${dateLabel}`;
    }

    // Table
    renderReportTable('dashboardBody', data);
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// REPORT
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async function loadReport({ force = false } = {}) {
    const dateInput = document.getElementById('reportDate');
    if (!dateInput) return;
    const dateVal = dateInput.value;
    const params = new URLSearchParams();
    if (dateVal) params.set('date', dateVal);
    if (force) params.set('refresh', '1');
    const query = params.toString();
    const url = `/api/report${query ? `?${query}` : ''}`;

    const body = document.getElementById('reportBody');
    beginTableLoad(body, 14, 'Loading report');

    try {
        const data = await apiCall(url, { dvtCacheMs: 15000, dvtForce: force });
        renderReportPage(data);
    } catch (err) {
        if (body && body.dataset.loaded !== 'true') {
            body.innerHTML = '<tr><td colspan="14" style="text-align:center;padding:40px;color:var(--accent-red)">Failed to load report</td></tr>';
        }
    } finally {
        endTableLoad(body);
    }
}

function renderReportPage(data) {
    const meta = data.meta;
    const ct = data.company_total;

    // Summary
    const summary = document.getElementById('reportSummary');
    if (summary) summary.textContent = meta.summary;

    // KPI
    const kpiGrid = document.getElementById('reportKPI');
    if (kpiGrid) {
        kpiGrid.style.display = '';
        const el = (id) => document.getElementById(id);
        el('rptMtdDays').textContent = meta.mtd_days;
        el('rptBalDays').textContent = meta.balance_days;
        el('rptTotalDays').textContent = meta.days_in_month;
        el('rptVolPlant').textContent = fmt(meta.vol_per_plant);
    }

    // Date header
    const thDate = document.getElementById('rptThDate');
    if (thDate && meta.yesterday) {
        const d = new Date(meta.yesterday);
        const day = d.getDate();
        const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        const dateLabel = `${day}-${monthNames[d.getMonth()]}`;
        thDate.innerHTML = `Produced Quantity<br>${dateLabel}`;
        document.getElementById('rptThInvDate').innerHTML = `Invoiced Quantity<br>${dateLabel}`;
    }

    // Table
    renderReportTable('reportBody', data);
}

// ── Shared report table renderer ──────────────────────────────────────────────

function renderReportTable(targetId, data) {
    const body = document.getElementById(targetId);
    if (!body) return;

    let html = '';
    let sr = 1;

    for (const region of data.regions) {
        // Plant rows
        for (const p of region.plants) {
            const invShort = p.daily_volume > 0 && p.invoiced_qty < p.daily_volume;
            html += `<tr>
                <td>${sr++}</td>
                <td>${escHtml(p.plant_name)}</td>
                <td class="text-right">${fmtDec(p.daily_volume)}</td>
                <td class="text-right${invShort ? ' inv-short' : ''}">${fmtDec(p.invoiced_qty)}</td>
                <td class="text-right">${fmtDec(p.daily_avg)}</td>
                <td class="text-right">${fmtDec(p.req_vol_day)}</td>
                <td class="text-right">${fmt(p.mtd_volume)}</td>
                <td class="text-right">${fmt(p.extrapolated)}</td>
                <td class="text-right">${fmt(p.target)}</td>
                <td class="text-center ${budgetPctClass(p.pct_extrap_vs_budget)}">${p.pct_extrap_vs_budget}</td>
                <td class="text-right">${fmt(p.last_month)}</td>
                <td class="text-center ${pctClass(p.pct_vs_last_month)}">${p.pct_vs_last_month}</td>
                <td class="text-right">${fmt(p.last_year)}</td>
                <td class="text-center ${pctClass(p.pct_vs_last_year)}">${p.pct_vs_last_year}</td>
            </tr>`;
        }

        // Region subtotal row — skip if null (e.g. Unassigned region)
        const s = region.subtotal;
        if (s) {
            html += `<tr class="region-row">
                <td>${s.label}</td>
                <td>${escHtml(s.region_name)}</td>
                <td class="text-right">${fmt(s.daily_volume)}</td>
                <td class="text-right">${fmt(s.invoiced_qty)}</td>
                <td class="text-right">${fmt(s.daily_avg)}</td>
                <td class="text-right">${fmt(s.req_vol_day)}</td>
                <td class="text-right">${fmt(s.mtd_volume)}</td>
                <td class="text-right">${fmt(s.extrapolated)}</td>
                <td class="text-right">${fmt(s.target)}</td>
                <td class="text-center">${s.pct_extrap_vs_budget}</td>
                <td class="text-right">${fmt(s.last_month)}</td>
                <td class="text-center">${s.pct_vs_last_month}</td>
                <td class="text-right">${fmt(s.last_year)}</td>
                <td class="text-center">${s.pct_vs_last_year}</td>
            </tr>`;
        }
    }

    // Company total
    const ct = data.company_total;
    html += `<tr class="total-row">
        <td>${ct.label}</td>
        <td>${escHtml(ct.region_name)}</td>
        <td class="text-right">${fmt(ct.daily_volume)}</td>
        <td class="text-right">${fmt(ct.invoiced_qty)}</td>
        <td class="text-right">${fmt(ct.daily_avg)}</td>
        <td class="text-right">${fmt(ct.req_vol_day)}</td>
        <td class="text-right">${fmt(ct.mtd_volume)}</td>
        <td class="text-right">${fmt(ct.extrapolated)}</td>
        <td class="text-right">${fmt(ct.target)}</td>
        <td class="text-center">${ct.pct_extrap_vs_budget}</td>
        <td class="text-right">${fmt(ct.last_month)}</td>
        <td class="text-center">${ct.pct_vs_last_month}</td>
        <td class="text-right">${fmt(ct.last_year)}</td>
        <td class="text-center">${ct.pct_vs_last_year}</td>
    </tr>`;

    body.innerHTML = html;
    body.dataset.loaded = 'true';
}

function budgetPctClass(pctStr) {
    if (!pctStr) return '';
    const val = parseInt(pctStr);
    if (isNaN(val)) return '';
    if (val >= 90) return 'positive';
    if (val >= 60) return '';
    return 'negative';
}

function escHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// ── Export ─────────────────────────────────────────────────────────────────────

function exportReport() {
    const dateInput = document.getElementById('reportDate');
    const dateVal = dateInput ? dateInput.value : '';
    const url = dateVal ? `/api/report/export?date=${dateVal}` : '/api/report/export';
    window.open((window.URL_PREFIX || '') + url, '_blank');
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// MANUAL ENTRY
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// MANUAL ENTRY
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

const _ME_MONTH_NAMES = ['January','February','March','April','May','June','July','August','September','October','November','December'];
const _ME_DAY_NAMES   = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
const _ME_DAY_SHORT   = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];

async function loadManualPlants() {
    const body = document.getElementById('manualEntryBody');
    if (!body) return;

    body.innerHTML = '<tr><td colspan="4" class="loading"><div class="spinner"></div><span>Loading plants…</span></td></tr>';

    try {
        const data = await apiCall('/api/manual-plants');
        let plants = data.plants;

        const countEl = document.getElementById('manualCount');
        if (countEl) countEl.textContent = `${plants.length} plant${plants.length !== 1 ? 's' : ''}`;

        // Populate region filter once
        const regionFilter = document.getElementById('meRegionFilter');
        if (regionFilter && regionFilter.options.length <= 1) {
            const regions = [...new Set(plants.map(p => p.region).filter(Boolean))].sort();
            for (const r of regions) {
                const opt = document.createElement('option');
                opt.value = r; opt.textContent = r;
                regionFilter.appendChild(opt);
            }
        }
        const selectedRegion = regionFilter ? regionFilter.value : '';
        if (selectedRegion) plants = plants.filter(p => p.region === selectedRegion);

        if (plants.length === 0) {
            body.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:40px;color:var(--text-muted);">No plants assigned. Contact your administrator.</td></tr>';
            return;
        }

        let html = '';
        for (const p of plants) {
            const name = escHtml(p.daily_tracker_name || p.erp_name || p.plant_code);
            html += `<tr class="plant-row" onclick='openPlantEntry(${JSON.stringify(p.plant_code)}, ${JSON.stringify(p.daily_tracker_name || p.erp_name || p.plant_code)}, ${JSON.stringify(p.region || '')})'>
                <td><span class="badge badge-blue">${escHtml(p.plant_code)}</span></td>
                <td style="font-weight:500;">${name}</td>
                <td>${escHtml(p.region || '-')}</td>
                <td class="text-center">
                    <button class="btn btn-outline btn-sm btn-icon open-entry-btn" title="Enter data">
                        <span class="material-icons-round">edit_calendar</span>
                    </button>
                </td>
            </tr>`;
        }
        body.innerHTML = html;

    } catch (err) {
        body.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:40px;color:var(--accent-red)">Failed to load plants</td></tr>';
    }
}

// ── Plant Entry Pane ──────────────────────────────────────────────────────────

let _entryCurrentPlant = null;

async function openPlantEntry(plantCode, plantName, region) {
    _entryCurrentPlant = plantCode;

    document.getElementById('plantEntryTitle').textContent   = plantName || plantCode;
    document.getElementById('plantEntrySubtitle').textContent = `${plantCode}${region ? '  ·  ' + region : ''}`;
    document.getElementById('plantEntryModal').classList.add('show');

    const isAdmin   = window.CURRENT_USER_ROLE === 'admin';
    const daysToLoad = isAdmin ? 30 : 3;
    const body = document.getElementById('plantEntryBody');
    body.innerHTML = '<div class="loading" style="padding:32px 0;"><div class="spinner"></div></div>';

    try {
        // Fetch daysToLoad+1 so volMap covers yesterday through N days back (today excluded from display)
        const data = await apiCall(`/api/daily-volume/${plantCode}?days=${daysToLoad + 1}`);
        const volMap = {};
        for (const v of data.volumes) volMap[v.entry_date] = v.volume;

        if (isAdmin) {
            _renderAdminDays(plantCode, daysToLoad, volMap);
        } else {
            _renderManualEntryDays(plantCode, daysToLoad, volMap);
        }
    } catch (err) {
        body.innerHTML = '<div style="padding:32px;text-align:center;color:var(--accent-red);">Failed to load data</div>';
    }
}

function closePlantEntryModal() {
    document.getElementById('plantEntryModal').classList.remove('show');
    _entryCurrentPlant = null;
}

// ── Local date helper — avoids toISOString() UTC shift (e.g. IST midnight bug) ─
function _localDateStr(d) {
    const pad = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

// ── 3-day card view (manual entry users) ─────────────────────────────────────

function _renderManualEntryDays(plantCode, days, volMap) {
    const body  = document.getElementById('plantEntryBody');
    const today = new Date();
    const labels = ['YESTERDAY', '2 DAYS AGO', '3 DAYS AGO'];
    let html = '';

    for (let i = 1; i <= days; i++) {
        const d = new Date(today);
        d.setDate(d.getDate() - i);
        const dateStr    = _localDateStr(d);
        const dow        = d.getDay();
        const dayName    = _ME_DAY_NAMES[dow];
        const dateLabel  = `${dayName}, ${String(d.getDate()).padStart(2,'0')} ${_ME_MONTH_NAMES[d.getMonth()]} ${d.getFullYear()}`;
        const vol        = volMap[dateStr];
        const hasData    = vol !== undefined && vol > 0;
        const inputId    = `day-inp-${dateStr}`;
        const flashId    = `day-flash-${dateStr}`;

        html += `
        <div class="day-card">
            <div class="day-card-tag">
                <span class="material-icons-round" style="font-size:13px;">calendar_today</span>
                ${labels[i - 1]}
            </div>
            <div class="day-card-date">${dateLabel}</div>
            <div class="day-card-row">
                <input type="number" id="${inputId}" class="day-card-input"
                       value="${hasData ? vol : ''}" placeholder="0.00"
                       step="0.01" min="0"
                       onkeydown='if(event.key==="Enter") saveDayEntry(${JSON.stringify(plantCode)},${JSON.stringify(dateStr)},${JSON.stringify(inputId)},${JSON.stringify(flashId)})'>
                <span class="day-card-unit">CUM</span>
                <button class="btn btn-primary btn-sm day-card-save-btn"
                        onclick='saveDayEntry(${JSON.stringify(plantCode)},${JSON.stringify(dateStr)},${JSON.stringify(inputId)},${JSON.stringify(flashId)})'>
                    <span class="material-icons-round" style="font-size:15px;">check</span> Save
                </button>
            </div>
            <div class="day-saved-flash" id="${flashId}">
                <span class="material-icons-round" style="font-size:15px;">check_circle</span> Saved
            </div>
        </div>`;
    }

    body.innerHTML = html;
    // Auto-focus today's input
    const first = body.querySelector('.day-card-input');
    if (first) { first.focus(); first.select(); }
}

async function saveDayEntry(plantCode, dateStr, inputId, flashId) {
    const inp    = document.getElementById(inputId);
    const volume = parseFloat(inp.value);

    if (isNaN(volume) || volume < 0) {
        showToast('Please enter a valid positive number', 'error');
        return;
    }

    // Disable the save button while the request is in-flight (prevent double-submit)
    const saveBtn = inp.closest('.day-card-row')?.querySelector('.day-card-save-btn');
    if (saveBtn) { saveBtn.disabled = true; saveBtn.style.opacity = '0.5'; }

    try {
        const result = await apiCall('/api/daily-volume', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ entries: [{ plant_code: plantCode, entry_date: dateStr, volume }] }),
        });

        // Only show "Saved" when the server confirms the entry was actually persisted
        if (result && result.saved > 0) {
            const flash = document.getElementById(flashId);
            if (flash) {
                flash.textContent = '';
                flash.innerHTML   = `<span class="material-icons-round" style="font-size:15px;">check_circle</span> Saved: ${fmtDec(volume)} CUM`;
                flash.classList.add('visible');
                setTimeout(() => flash.classList.remove('visible'), 2500);
            }
        } else {
            // Server returned 200 but nothing was saved (validation error, access issue, etc.)
            const reason = result?.errors?.[0] || 'Entry could not be saved. Please try again.';
            showToast(reason, 'error');
        }
    } catch (err) {
        // Network error or HTTP 4xx/5xx — already displayed by apiCall
    } finally {
        if (saveBtn) { saveBtn.disabled = false; saveBtn.style.opacity = ''; }
    }
}

// ── 30-day table (admin) ─────────────────────────────────────────────────────

function _renderAdminDays(plantCode, days, volMap) {
    const body  = document.getElementById('plantEntryBody');
    const today = new Date();
    let html = `
    <table class="data-table" style="table-layout:fixed;">
        <colgroup>
            <col style="width:52px;">
            <col>
            <col style="width:160px;">
        </colgroup>
        <thead>
            <tr>
                <th class="text-center" style="font-size:0.78rem;">#</th>
                <th style="font-size:0.78rem;">Date</th>
                <th class="text-right" style="font-size:0.78rem;">Volume (CUM)</th>
            </tr>
        </thead>
        <tbody>`;

    let dataCount = 0;
    for (let i = 1; i <= days; i++) {
        const d = new Date(today);
        d.setDate(d.getDate() - i);
        const dateStr     = _localDateStr(d);
        const dow         = d.getDay();
        const isYesterday = i === 1;
        const isWeekend   = dow === 0 || dow === 6;
        const vol         = volMap[dateStr];
        const hasData     = vol !== undefined && vol > 0;
        if (hasData) dataCount++;

        const dayLabel  = `${_ME_DAY_SHORT[dow]}, ${String(d.getDate()).padStart(2,'0')} ${_ME_MONTH_NAMES[d.getMonth()].slice(0,3)} ${d.getFullYear()}`;
        const rowClass  = [
            isYesterday ? 'is-today-row'   : '',
            isWeekend   ? 'is-weekend-row' : '',
            hasData     ? 'has-data-row'   : '',
        ].filter(Boolean).join(' ');

        html += `<tr class="${rowClass}">
            <td class="text-center" style="font-weight:600;color:var(--text-muted);font-size:0.8rem;">${i}</td>
            <td class="day-date-cell" style="font-size:0.88rem;${isYesterday ? 'color:var(--accent-blue);font-weight:700;' : ''}">
                ${dayLabel}${isYesterday ? ' <span style="font-size:0.7rem;opacity:0.75;">(yesterday)</span>' : ''}
            </td>
            <td class="text-right">
                <input type="number" class="editable-input day-vol-input"
                       data-date="${dateStr}"
                       value="${hasData ? vol : ''}"
                       placeholder="0.00" step="0.01" min="0">
            </td>
        </tr>`;
    }

    html += '</tbody></table>';
    body.innerHTML = html;

    const infoEl = document.getElementById('plantEntryInfo');
    if (infoEl) infoEl.textContent = `${dataCount} of ${days} days have data`;

    // Auto-focus today's input
    const first = body.querySelector('.day-vol-input');
    if (first) { first.focus(); first.select(); }
}

async function saveAllDayEntries() {
    if (!_entryCurrentPlant) return;
    const inputs  = document.querySelectorAll('.day-vol-input');
    const entries = [];
    inputs.forEach(inp => {
        const vol = parseFloat(inp.value);
        entries.push({
            plant_code: _entryCurrentPlant,
            entry_date: inp.dataset.date,
            volume:     isNaN(vol) || vol < 0 ? 0 : vol,
        });
    });
    if (!entries.length) { showToast('No entries to save', 'warning'); return; }

    try {
        const result = await apiCall('/api/daily-volume', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ entries }),
        });
        const errCount = result.errors && result.errors.length;
        if (result.saved === 0) {
            // Nothing saved at all — show the first error reason
            const reason = errCount ? result.errors[0] : 'No entries were saved.';
            showToast(reason, 'error');
        } else if (errCount) {
            showToast(`Saved ${result.saved} entr${result.saved === 1 ? 'y' : 'ies'}, ${errCount} skipped`, 'warning');
        } else {
            showToast(`Saved ${result.saved} entr${result.saved === 1 ? 'y' : 'ies'} successfully`, 'success');
        }
        // Refresh data counts
        openPlantEntry(
            _entryCurrentPlant,
            document.getElementById('plantEntryTitle').textContent,
            ''
        );
    } catch (err) { /* shown by apiCall */ }
}


// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// TARGETS
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async function loadTargets() {
    const monthInput = document.getElementById('targetMonth');
    if (!monthInput || !monthInput.value) return;

    const month = monthInput.value;
    const body = document.getElementById('targetsBody');
    body.innerHTML = '<tr><td colspan="4" class="loading"><div class="spinner"></div><span>Loading...</span></td></tr>';

    try {
        const data = await apiCall(`/api/targets/${month}`);
        const regions = data.regions || [];

        const info = document.getElementById('targetInfo');
        if (info) info.textContent = `${data.targets.length} plants`;

        // ── Prominent month banner ────────────────────────────────────────
        const banner   = document.getElementById('activeMonthBanner');
        const label    = document.getElementById('activeMonthLabel');
        const sublabel = document.getElementById('activeMonthSublabel');
        const icon     = document.getElementById('activeMonthIcon');
        const tag      = document.getElementById('activeMonthTag');
        if (banner && label) {
            // Parse selected month and compare to current month
            const [selYear, selMon] = month.split('-').map(Number);
            const now = new Date();
            const curYear = now.getFullYear(), curMon = now.getMonth() + 1;
            const isNextMonth = (selYear === curYear && selMon === curMon + 1) ||
                                (selMon === 1 && curMon === 12 && selYear === curYear + 1);

            // Format month name: "June 2026"
            const monthName = new Date(selYear, selMon - 1, 1)
                .toLocaleString('en-IN', { month: 'long', year: 'numeric' });
            label.textContent = monthName;

            if (isNextMonth) {
                // Amber — next month, draw extra attention
                banner.style.background    = '#FFFBEB';
                banner.style.borderColor   = '#FCD34D';
                icon.style.color           = '#B45309';
                label.style.color          = '#92400E';
                sublabel.style.color       = '#92400E';
                tag.textContent            = 'Next Month';
                tag.style.background       = '#FEF3C7';
                tag.style.color            = '#B45309';
                tag.style.border           = '1px solid #FCD34D';
                tag.style.display          = 'inline-block';
            } else {
                // Blue — current month, normal
                banner.style.background    = '#EFF6FF';
                banner.style.borderColor   = '#BFDBFE';
                icon.style.color           = '#2563EB';
                label.style.color          = '#1E40AF';
                sublabel.style.color       = '#1E40AF';
                tag.style.display          = 'none';
            }

            banner.style.display = 'flex';
        }

        let html = '';
        const canEdit = window.CURRENT_USER_CAN_UPDATE_TARGETS === true;
        let sr = 0;

        for (const region of regions) {
            html += `<tr class="region-row">
                <td colspan="4" style="font-weight:700;font-size:0.9rem;">
                    ${escHtml(region.region)}
                </td>
            </tr>`;

            for (const t of region.plants) {
                sr++;
                const val = t.target_volume || 0;
                const fmtVal = Number(val).toLocaleString('en-IN', {maximumFractionDigits: 0});
                html += `<tr>
                    <td><span class="badge badge-blue">${escHtml(t.plant_code)}</span></td>
                    <td>${escHtml(t.plant_name)}</td>
                    <td>${escHtml(t.region)}</td>
                    <td class="text-right">
                        <span class="target-display" id="disp-${t.plant_code}">${fmtVal}</span>
                        <input type="number" class="editable-input target-vol target-hidden"
                               id="inp-${t.plant_code}"
                               data-plant="${t.plant_code}"
                               value="${val}"
                               step="1" min="0"
                               style="display:none;"
                               onblur='hideEdit(${JSON.stringify(t.plant_code)})'>
                        ${canEdit ? `<button class="edit-icon-btn" onclick='enableEdit(${JSON.stringify(t.plant_code)})' title="Edit">
                            <span class="material-icons-round" style="font-size:16px;">edit</span>
                        </button>` : ''}
                    </td>
                </tr>`;
            }
        }
        body.innerHTML = html;
    } catch (err) {
        body.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:40px;color:var(--accent-red)">Failed to load targets</td></tr>';
    }
}

function enableEdit(plantCode) {
    const disp = document.getElementById(`disp-${plantCode}`);
    const inp = document.getElementById(`inp-${plantCode}`);
    if (disp) disp.style.display = 'none';
    if (inp) { inp.style.display = 'inline-block'; inp.focus(); inp.select(); }
    // hide the edit button
    const btn = inp?.parentElement?.querySelector('.edit-icon-btn');
    if (btn) btn.style.display = 'none';
}

function hideEdit(plantCode) {
    const disp = document.getElementById(`disp-${plantCode}`);
    const inp = document.getElementById(`inp-${plantCode}`);
    const val = parseFloat(inp?.value) || 0;
    if (disp) {
        disp.textContent = Number(val).toLocaleString('en-IN', {maximumFractionDigits: 0});
        disp.style.display = '';
    }
    if (inp) inp.style.display = 'none';
    const btn = inp?.parentElement?.querySelector('.edit-icon-btn');
    if (btn) btn.style.display = '';
}

function downloadTemplate() {
    const monthInput = document.getElementById('targetMonth');
    if (!monthInput || !monthInput.value) { showToast('Select a month first', 'warning'); return; }
    window.location.href = (window.URL_PREFIX || '') + `/api/targets/${monthInput.value}/template`;
}

async function saveAllTargets() {
    const monthInput = document.getElementById('targetMonth');
    if (!monthInput || !monthInput.value) {
        showToast('Please select a month', 'warning');
        return;
    }
    const month = monthInput.value;
    const inputs = document.querySelectorAll('.target-vol');
    const targets = [];

    inputs.forEach(input => {
        targets.push({
            plant_code: input.dataset.plant,
            target_volume: parseFloat(input.value) || 0,
        });
    });

    try {
        const result = await apiCall('/api/targets', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ month, targets }),
        });
        const errCount = result.errors && result.errors.length;
        if (errCount) {
            showToast(`Saved ${result.saved} target${result.saved === 1 ? '' : 's'}, ${errCount} skipped`, 'warning');
        } else {
            showToast(`Saved ${result.saved} target${result.saved === 1 ? '' : 's'} successfully`, 'success');
        }
    } catch (err) {
        // Error already shown by apiCall
    }
}

async function uploadTargets() {
    const fileInput = document.getElementById('targetFile');
    const monthInput = document.getElementById('targetMonth');

    if (!fileInput.files.length) return;
    if (!monthInput || !monthInput.value) {
        showToast('Please select a month first', 'warning');
        return;
    }

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    formData.append('month', monthInput.value);

    const resultDiv = document.getElementById('uploadResult');
    resultDiv.classList.remove('hidden');
    resultDiv.innerHTML = '<div class="loading"><div class="spinner"></div><span>Uploading...</span></div>';

    try {
        const result = await apiCall('/api/targets/upload', {
            method: 'POST',
            body: formData,
        });

        resultDiv.innerHTML = `
            <div class="summary-banner">
                <strong>Upload complete:</strong> ${result.saved} targets saved.
                ${result.errors.length ? '<br>Errors: ' + result.errors.join(', ') : ''}
            </div>`;
        showToast('Targets uploaded successfully', 'success');
        loadTargets();  // Refresh table
    } catch (err) {
        resultDiv.innerHTML = '<div style="color:var(--accent-red)">Upload failed</div>';
    }

    fileInput.value = '';  // Reset file input
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// DVTPaginator — premium client-side & server-side pagination
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class DVTPaginator {
    /**
     * Client-side paginator with animated row transitions.
     * @param {Object} opts
     * @param {string}   opts.tbodyId       — ID of <tbody> element
     * @param {string}   opts.paginationId  — ID of pagination container
     * @param {Array}    opts.items         — Initial data array
     * @param {number}   [opts.perPage=25]  — Default rows per page
     * @param {number}   [opts.colSpan=5]   — colspan for empty rows
     * @param {string}   [opts.emptyMsg]    — Message when no items
     * @param {Function} opts.renderItem    — (item, localIdx, globalIdx, prevItem) => HTML string
     * @param {Function} [opts.onPageChange] — Called after render with (page, totalPages)
     */
    constructor(opts) {
        this.tbodyId      = opts.tbodyId;
        this.paginationId = opts.paginationId;
        this.items        = opts.items || [];
        this.perPage      = opts.perPage || 25;
        this.colSpan      = opts.colSpan || 5;
        this.emptyMsg     = opts.emptyMsg || 'No data found';
        this.renderItem   = opts.renderItem;
        this.onPageChange = opts.onPageChange || null;
        this.page         = 1;
        this._dir         = 'fade';
        // Register instance globally so inline onclick handlers can reach it
        DVTPaginator._reg[this.tbodyId] = this;
    }

    /** Replace data and re-render from page 1 */
    setItems(items, resetPage = true) {
        this.items = items;
        if (resetPage) { this._dir = 'fade'; this.page = 1; }
        this._render();
    }

    /** Jump to page n (1-based) */
    goTo(page) {
        const total = this._totalPages();
        if (page < 1 || page > total || page === this.page) return;
        this._dir = page > this.page ? 'forward' : 'backward';
        this.page = page;
        this._render();
    }

    /** Change rows-per-page, reset to page 1 */
    setPerPage(n) {
        this.perPage = n;
        this._dir = 'fade';
        this.page = 1;
        this._render();
    }

    _totalPages() { return Math.max(1, Math.ceil(this.items.length / this.perPage)); }

    _render() {
        this._renderRows();
        this._renderPager();
        if (this.onPageChange) this.onPageChange(this.page, this._totalPages());
    }

    _renderRows() {
        const tbody = document.getElementById(this.tbodyId);
        if (!tbody) return;

        if (this.items.length === 0) {
            tbody.innerHTML = `<tr><td colspan="${this.colSpan}" style="text-align:center;padding:40px;color:var(--text-muted)">${this.emptyMsg}</td></tr>`;
            return;
        }

        const start     = (this.page - 1) * this.perPage;
        const slice     = this.items.slice(start, start + this.perPage);
        const animClass = `pg-anim-${this._dir}`;
        const id        = this.tbodyId;

        let html = '';
        for (let i = 0; i < slice.length; i++) {
            const globalIdx = start + i;
            const prevItem  = globalIdx > 0 ? this.items[globalIdx - 1] : null;
            const delay     = Math.min(i * 16, 160);
            const rowHtml   = this.renderItem(slice[i], i, globalIdx, prevItem);
            // Inject animation class + stagger delay on the first <tr>
            html += rowHtml.replace(/^(\s*)<tr/, `$1<tr class="${animClass}" style="animation-delay:${delay}ms"`);
        }
        tbody.innerHTML = html;
    }

    _renderPager() {
        const container = document.getElementById(this.paginationId);
        if (!container) return;

        const total  = this._totalPages();
        const page   = this.page;
        const count  = this.items.length;
        const id     = this.tbodyId;

        if (count === 0) { container.innerHTML = ''; return; }

        const start = (page - 1) * this.perPage + 1;
        const end   = Math.min(page * this.perPage, count);
        const perPageOptions = [10, 25, 50, 100];

        let pagesHtml = '';
        for (const p of DVTPaginator._pageNums(page, total)) {
            if (p === '…') {
                pagesHtml += `<span class="pg-ellipsis">…</span>`;
            } else {
                pagesHtml += `<button class="pg-btn${p === page ? ' active' : ''}" onclick="DVTPaginator._reg['${id}']&&DVTPaginator._reg['${id}'].goTo(${p})">${p}</button>`;
            }
        }

        const ppOpts = perPageOptions.map(n =>
            `<option value="${n}"${n === this.perPage ? ' selected' : ''}>${n}</option>`
        ).join('');

        container.innerHTML = `<div class="pg-wrapper">
  <div class="pg-info">${start}-${end} of ${count}</div>
  <nav class="pg-nav">
    <button class="pg-btn" onclick="DVTPaginator._reg['${id}']&&DVTPaginator._reg['${id}'].goTo(1)" ${page===1?'disabled':''} title="First page">«</button>
    <button class="pg-btn" onclick="DVTPaginator._reg['${id}']&&DVTPaginator._reg['${id}'].goTo(${page-1})" ${page===1?'disabled':''} title="Previous">‹</button>
    ${pagesHtml}
    <button class="pg-btn" onclick="DVTPaginator._reg['${id}']&&DVTPaginator._reg['${id}'].goTo(${page+1})" ${page===total?'disabled':''} title="Next">›</button>
    <button class="pg-btn" onclick="DVTPaginator._reg['${id}']&&DVTPaginator._reg['${id}'].goTo(${total})" ${page===total?'disabled':''} title="Last page">»</button>
  </nav>
  <div class="pg-goto">
    <span>Go to</span>
    <input type="number" min="1" max="${total}" placeholder="${page}"
      onkeydown="if(event.key==='Enter'){var v=parseInt(this.value);if(v>=1&&v<=${total}){DVTPaginator._reg['${id}']&&DVTPaginator._reg['${id}'].goTo(v);}this.value='';}"/>
  </div>
  <div class="pg-perpage">
    <span>Rows</span>
    <select onchange="DVTPaginator._reg['${id}']&&DVTPaginator._reg['${id}'].setPerPage(+this.value)">${ppOpts}</select>
  </div>
</div>`;
    }

    /** Smart page numbers with ellipsis: always show first, last, ±2 of current */
    static _pageNums(page, total) {
        if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
        const out   = [];
        const delta = 2;
        const left  = Math.max(2, page - delta);
        const right = Math.min(total - 1, page + delta);
        out.push(1);
        if (left > 2) out.push('…');
        for (let i = left; i <= right; i++) out.push(i);
        if (right < total - 1) out.push('…');
        out.push(total);
        return out;
    }

    /**
     * Render server-side pagination controls (for audit log etc.)
     * @param {string}   containerId
     * @param {number}   page         — current page
     * @param {number}   total        — total items
     * @param {number}   pages        — total pages
     * @param {string}   callbackName — global function name to call with new page number
     */
    static renderExternal(containerId, page, total, pages, callbackName) {
        const container = document.getElementById(containerId);
        if (!container) return;
        if (pages <= 1) { container.innerHTML = ''; return; }

        const start = (page - 1) * 50 + 1; // assumes per_page=50
        const end   = Math.min(page * 50, total);

        let pagesHtml = '';
        for (const p of DVTPaginator._pageNums(page, pages)) {
            if (p === '…') {
                pagesHtml += `<span class="pg-ellipsis">…</span>`;
            } else {
                pagesHtml += `<button class="pg-btn${p === page ? ' active' : ''}" onclick="${callbackName}(${p})">${p}</button>`;
            }
        }

        container.innerHTML = `<div class="pg-wrapper">
  <div class="pg-info">${start}-${end} of ${total}</div>
  <nav class="pg-nav">
    <button class="pg-btn" onclick="${callbackName}(1)" ${page===1?'disabled':''}>«</button>
    <button class="pg-btn" onclick="${callbackName}(${page-1})" ${page===1?'disabled':''}>‹</button>
    ${pagesHtml}
    <button class="pg-btn" onclick="${callbackName}(${page+1})" ${page===pages?'disabled':''}>›</button>
    <button class="pg-btn" onclick="${callbackName}(${pages})" ${page===pages?'disabled':''}>»</button>
  </nav>
  <div class="pg-goto">
    <span>Go to</span>
    <input type="number" min="1" max="${pages}" placeholder="${page}"
      onkeydown="if(event.key==='Enter'){var v=parseInt(this.value);if(v>=1&&v<=${pages}){${callbackName}(v);}this.value='';}"/>
  </div>
</div>`;
    }
}
// Global instance registry (accessed by inline onclick handlers)
DVTPaginator._reg = {};

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// PLANTS
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

let _plantsAllData = []; // cached full dataset for client-side filter+paginate

function _applyPlantsFilter() {
    const region = document.getElementById('regionFilter')?.value || '';
    const search = (document.getElementById('plantSearch')?.value || '').trim().toLowerCase();

    let filtered = _plantsAllData;
    if (region) filtered = filtered.filter(p => p.region === region);
    if (search) filtered = filtered.filter(p =>
        (p.plant_code || '').toLowerCase().includes(search) ||
        (p.daily_tracker_name || '').toLowerCase().includes(search) ||
        (p.erp_name || '').toLowerCase().includes(search) ||
        (p.region || '').toLowerCase().includes(search)
    );

    const countEl = document.getElementById('plantCount');
    if (countEl) countEl.textContent = filtered.length === _plantsAllData.length
        ? `${filtered.length} plants`
        : `${filtered.length} of ${_plantsAllData.length} plants`;

    DVTPaginator._reg['plantsBody']?.setItems(filtered);
}

async function loadPlants() {
    const body = document.getElementById('plantsBody');
    if (!body) return;

    body.innerHTML = '<tr><td colspan="6" class="loading"><div class="spinner"></div><span>Loading plants...</span></td></tr>';

    try {
        const data = await apiCall('/api/plants');
        _plantsAllData = data.plants;

        // Populate region filter (only once)
        const regionFilter = document.getElementById('regionFilter');
        if (regionFilter && regionFilter.options.length <= 1 && data.regions) {
            for (const r of data.regions) {
                const opt = document.createElement('option');
                opt.value = r; opt.textContent = r;
                regionFilter.appendChild(opt);
            }
        }

        // (Re-)create paginator
        new DVTPaginator({
            tbodyId:      'plantsBody',
            paginationId: 'plantsPagination',
            perPage:      25,
            colSpan:      6,
            emptyMsg:     'No plants found',
            renderItem:   (p) => `<tr>
                <td><span class="badge badge-blue">${escHtml(p.plant_code)}</span></td>
                <td>${escHtml(p.daily_tracker_name || '')}</td>
                <td>${escHtml(p.erp_name || '')}</td>
                <td>${escHtml(p.region || '-')}</td>
                <td class="text-center">
                    <span class="badge ${p.is_active ? 'badge-green' : 'badge-red'}">${p.is_active ? 'Yes' : 'No'}</span>
                </td>
                <td class="text-center">
                    <button class="btn btn-outline btn-sm btn-icon" onclick='editPlant(${JSON.stringify(p.plant_code)})' title="Edit">
                        <span class="material-icons-round">edit</span>
                    </button>
                    <button class="btn btn-outline btn-sm btn-icon" onclick='deletePlant(${JSON.stringify(p.plant_code)})' title="Delete" style="color:var(--accent-red)">
                        <span class="material-icons-round">delete</span>
                    </button>
                </td>
            </tr>`,
        });

        _applyPlantsFilter();
    } catch (err) {
        body.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:40px;color:var(--accent-red)">Failed to load plants</td></tr>';
    }
}

async function _loadRegionDropdown(selectedValue) {
    const sel = document.getElementById('modalRegion');
    sel.innerHTML = '<option value="">(No Area)</option>';
    try {
        const data = await apiCall('/api/regions/names');
        for (const name of data.regions) {
            const opt = document.createElement('option');
            opt.value = name;
            opt.textContent = name;
            sel.appendChild(opt);
        }
    } catch {}
    sel.value = selectedValue || '';
}

async function showAddPlantModal() {
    document.getElementById('plantModalTitle').textContent = 'Add Plant';
    document.getElementById('editingPlantCode').value = '';
    document.getElementById('modalPlantCode').value = '';
    document.getElementById('modalPlantCode').disabled = false;
    document.getElementById('modalTrackerName').value = '';
    document.getElementById('modalErpName').value = '';
    document.getElementById('modalActive').checked = true;
    await _loadRegionDropdown('');
    document.getElementById('plantModal').classList.add('show');
}

async function editPlant(plantCode) {
    try {
        // Use cached data; re-fetch only if cache is stale/empty
        let plant = _plantsAllData.find(p => p.plant_code === plantCode);
        if (!plant) {
            const data = await apiCall('/api/plants');
            _plantsAllData = data.plants;
            plant = _plantsAllData.find(p => p.plant_code === plantCode);
        }
        if (!plant) {
            showToast('Plant not found', 'error');
            return;
        }

        document.getElementById('plantModalTitle').textContent = `Edit Plant: ${plantCode}`;
        document.getElementById('editingPlantCode').value = plantCode;
        document.getElementById('modalPlantCode').value = plantCode;
        document.getElementById('modalPlantCode').disabled = true;
        document.getElementById('modalTrackerName').value = plant.daily_tracker_name || '';
        document.getElementById('modalErpName').value = plant.erp_name || '';
        document.getElementById('modalActive').checked = plant.is_active;
        await _loadRegionDropdown(plant.region || '');
        document.getElementById('plantModal').classList.add('show');
    } catch (err) {
        // Error shown by apiCall
    }
}

function closePlantModal() {
    document.getElementById('plantModal').classList.remove('show');
}

async function savePlant() {
    const editingCode = document.getElementById('editingPlantCode').value;
    const plantCode = document.getElementById('modalPlantCode').value.trim().toUpperCase();
    const body = {
        plant_code: plantCode,
        daily_tracker_name: document.getElementById('modalTrackerName').value.trim(),
        erp_name: document.getElementById('modalErpName').value.trim(),
        region: document.getElementById('modalRegion').value.trim(),
        is_active: document.getElementById('modalActive').checked,
    };

    if (!plantCode) {
        showToast('Plant code is required', 'warning');
        return;
    }

    try {
        if (editingCode) {
            // Update
            await apiCall(`/api/plants/${editingCode}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            showToast(`Plant ${editingCode} updated`, 'success');
        } else {
            // Create
            await apiCall('/api/plants', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            showToast(`Plant ${plantCode} added`, 'success');
        }
        closePlantModal();
        loadPlants();
    } catch (err) {
        // Error shown by apiCall
    }
}

async function deletePlant(plantCode) {
    const ok = await showConfirm(
        `Delete plant ${plantCode}? This will permanently remove all its volume and target data.`,
        'Delete Plant'
    );
    if (!ok) return;

    try {
        await apiCall(`/api/plants/${plantCode}`, { method: 'DELETE' });
        showToast(`Plant ${plantCode} deleted`, 'success');
        loadPlants();
    } catch (err) {
        // Error shown by apiCall
    }
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// ── Plant Reorder Modal ────────────────────────────────────────────────────

let _roHasChanges      = false;
let _roDragGhost       = null;
let _roDragItem        = null;
let _roDragOffsetY     = 0;
let _roDragInsertTarget = null;
let _roDragInsertBefore = true;

async function showPlantReorderModal() {
    const sel = document.getElementById('reorderRegionSel');
    if (!sel) return;
    sel.innerHTML = '<option value="">Pick an area</option>';
    _roHasChanges = false;
    _roUpdateSaveBtn();
    document.getElementById('reorderSubtitle').textContent = 'Select an area to start';
    document.getElementById('reorderList').innerHTML = '';
    try {
        const data = await apiCall('/api/regions/names');
        for (const name of data.regions) {
            const opt = document.createElement('option');
            opt.value = name; opt.textContent = name;
            sel.appendChild(opt);
        }
    } catch {}
    document.getElementById('plantReorderModal').classList.add('show');
}

function closePlantReorderModal() {
    document.getElementById('plantReorderModal').classList.remove('show');
    _roCleanupDrag();
}

async function loadReorderList() {
    const region    = document.getElementById('reorderRegionSel').value;
    const container = document.getElementById('reorderList');
    _roHasChanges   = false;
    _roUpdateSaveBtn();

    if (!region) {
        container.innerHTML = '';
        document.getElementById('reorderSubtitle').textContent = 'Select an area to start';
        return;
    }
    document.getElementById('reorderSubtitle').textContent = region;
    container.innerHTML = '<div class="loading"><div class="spinner"></div><span>Loading…</span></div>';

    try {
        const data   = await apiCall('/api/plants?region=' + encodeURIComponent(region));
        const plants = (data.plants || []).filter(p => p.is_active);

        if (!plants.length) {
            container.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:24px 0;">No active plants in this area.</p>';
            return;
        }

        container.innerHTML = '';
        const list = document.createElement('div');
        list.className = 'ro-list';
        plants.forEach((p, i) => list.appendChild(_roMakeItem(p, i + 1, plants.length)));
        container.appendChild(list);
        _roInitDrag(list);

    } catch {
        container.innerHTML = '<p style="color:var(--accent-red);text-align:center;padding:24px 0;">Failed to load plants.</p>';
    }
}

function _roMakeItem(plant, num, total) {
    const item = document.createElement('div');
    item.className = 'ro-item';
    item.dataset.code = plant.plant_code;
    item.innerHTML = `
        <span class="ro-num">${num}</span>
        <span class="material-icons-round ro-handle" title="Drag to reorder">drag_indicator</span>
        <span class="ro-name">${escHtml(plant.daily_tracker_name || plant.plant_code)}</span>
        <span class="ro-code">${escHtml(plant.plant_code)}</span>
        <div class="ro-arrows">
            <button class="ro-arrow" title="Move up" ${num === 1 ? 'disabled' : ''}
                    onclick="_roArrow(this,-1)">
                <span class="material-icons-round" style="font-size:13px">keyboard_arrow_up</span>
            </button>
            <button class="ro-arrow" title="Move down" ${num === total ? 'disabled' : ''}
                    onclick="_roArrow(this,1)">
                <span class="material-icons-round" style="font-size:13px">keyboard_arrow_down</span>
            </button>
        </div>`;
    return item;
}

// ── Arrow button swap ────────────────────────────────────────────────────────

function _roArrow(btn, dir) {
    const item    = btn.closest('.ro-item');
    const list    = item.parentNode;
    const sibling = dir === -1 ? item.previousElementSibling : item.nextElementSibling;
    if (!sibling) return;

    const gap      = 6;
    const itemH    = item.getBoundingClientRect().height + gap;
    const siblingH = sibling.getBoundingClientRect().height + gap;
    const dur      = 190;

    item.style.transition    = `transform ${dur}ms cubic-bezier(0.34,1.2,0.64,1)`;
    sibling.style.transition = `transform ${dur}ms cubic-bezier(0.34,1.2,0.64,1)`;
    item.style.transform     = dir === -1 ? `translateY(-${siblingH}px)` : `translateY(${siblingH}px)`;
    sibling.style.transform  = dir === -1 ? `translateY(${itemH}px)`     : `translateY(-${itemH}px)`;

    setTimeout(() => {
        item.style.transition = item.style.transform = '';
        sibling.style.transition = sibling.style.transform = '';
        if (dir === -1) list.insertBefore(item, sibling);
        else            list.insertBefore(sibling, item);
        _roRenumber(list);
        _roMarkChanged();
    }, dur);
}

function _roRenumber(list) {
    const items = [...list.querySelectorAll('.ro-item')];
    items.forEach((item, i) => {
        item.querySelector('.ro-num').textContent = i + 1;
        const [up, dn] = item.querySelectorAll('.ro-arrow');
        up.disabled = i === 0;
        dn.disabled = i === items.length - 1;
    });
}

function _roMarkChanged() {
    _roHasChanges = true;
    _roUpdateSaveBtn();
}

function _roUpdateSaveBtn() {
    const btn = document.getElementById('saveReorderBtn');
    if (!btn) return;
    if (_roHasChanges) {
        btn.disabled = false;
        btn.innerHTML = `<span class="material-icons-round">check</span> Save Order <span class="ro-unsaved-dot"></span>`;
    } else {
        btn.disabled = true;
        btn.innerHTML = `<span class="material-icons-round">check</span> Save Order`;
    }
}

// ── Pointer drag ─────────────────────────────────────────────────────────────

function _roInitDrag(list) {
    list.querySelectorAll('.ro-handle').forEach(handle => {
        handle.addEventListener('pointerdown', e => _roStartDrag(e, handle.closest('.ro-item'), list));
    });
}

function _roStartDrag(e, item, list) {
    e.preventDefault();
    _roDragItem = item;
    const rect = item.getBoundingClientRect();
    _roDragOffsetY = e.clientY - rect.top;

    // Clone as floating ghost
    _roDragGhost = item.cloneNode(true);
    _roDragGhost.className = 'ro-ghost';
    _roDragGhost.style.cssText =
        `width:${rect.width}px;top:${rect.top}px;left:${rect.left}px;`;
    document.body.appendChild(_roDragGhost);

    item.classList.add('ro-lifted');
    document.addEventListener('pointermove', _roDrag);
    document.addEventListener('pointerup',   _roEndDrag);
}

function _roDrag(e) {
    if (!_roDragGhost || !_roDragItem) return;
    _roDragGhost.style.top = (e.clientY - _roDragOffsetY) + 'px';

    const list  = _roDragItem.parentNode;
    const items = [...list.querySelectorAll('.ro-item:not(.ro-lifted)')];
    items.forEach(it => it.classList.remove('ro-drop-before', 'ro-drop-after'));

    _roDragInsertTarget = null;
    _roDragInsertBefore = true;
    for (const it of items) {
        const r   = it.getBoundingClientRect();
        const mid = r.top + r.height / 2;
        if (e.clientY < mid) { _roDragInsertTarget = it; _roDragInsertBefore = true;  break; }
        _roDragInsertTarget = it; _roDragInsertBefore = false;
    }
    if (_roDragInsertTarget) {
        _roDragInsertTarget.classList.add(_roDragInsertBefore ? 'ro-drop-before' : 'ro-drop-after');
    }
}

function _roEndDrag() {
    document.removeEventListener('pointermove', _roDrag);
    document.removeEventListener('pointerup',   _roEndDrag);
    if (!_roDragItem) return;

    const list = _roDragItem.parentNode;
    list.querySelectorAll('.ro-item').forEach(it =>
        it.classList.remove('ro-drop-before', 'ro-drop-after')
    );

    const moved = _roDragInsertTarget && _roDragInsertTarget !== _roDragItem;
    if (moved) {
        if (_roDragInsertBefore) _roDragInsertTarget.before(_roDragItem);
        else                     _roDragInsertTarget.after(_roDragItem);
        _roRenumber(list);
        _roMarkChanged();
    }

    _roDragItem.classList.remove('ro-lifted');

    // Pop-in spring on drop
    const landed = _roDragItem;
    landed.style.transition = 'transform 0.22s cubic-bezier(0.34,1.5,0.64,1)';
    landed.style.transform  = 'scale(1.04)';
    setTimeout(() => { landed.style.transform = ''; setTimeout(() => { landed.style.transition = ''; }, 220); }, 10);

    _roCleanupDrag();
}

function _roCleanupDrag() {
    if (_roDragGhost) { _roDragGhost.remove(); _roDragGhost = null; }
    _roDragItem = _roDragInsertTarget = null;
}

// ── Save ─────────────────────────────────────────────────────────────────────

async function saveReorderPlants() {
    const region = document.getElementById('reorderRegionSel').value;
    if (!region) { showToast('Select an area first', 'warning'); return; }

    const list  = document.querySelector('#reorderList .ro-list');
    if (!list)  return;
    const order = [...list.querySelectorAll('.ro-item')].map(r => r.dataset.code);
    if (!order.length) return;

    const btn = document.getElementById('saveReorderBtn');
    btn.disabled = true;
    btn.innerHTML = '<div class="spinner" style="width:14px;height:14px;display:inline-block;vertical-align:middle;margin-right:6px"></div> Saving…';

    try {
        await apiCall('/api/plants/reorder', {
            method:  'PUT',
            headers: {'Content-Type': 'application/json'},
            body:    JSON.stringify({ region, order }),
        });
        _roHasChanges = false;
        btn.innerHTML = '<span class="material-icons-round">check_circle</span> Saved!';
        btn.style.background   = 'var(--accent-green)';
        btn.style.borderColor  = 'var(--accent-green)';
        setTimeout(() => {
            btn.style.background = btn.style.borderColor = '';
            closePlantReorderModal();
            loadPlants();
        }, 900);
    } catch {
        _roUpdateSaveBtn();
    }
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// ── Show/hide password toggle ──────────────────────────────────────────────
function togglePwVisibility(inputId, iconId) {
    const input = document.getElementById(inputId);
    const icon  = document.getElementById(iconId);
    if (!input) return;
    input.type = input.type === 'password' ? 'text' : 'password';
    if (icon) icon.textContent = input.type === 'password' ? 'visibility' : 'visibility_off';
}

// USER MANAGEMENT
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

// ── Password strength ──────────────────────────────────────────────────────
const _PW_LEVELS = [
    { label: '',          color: '',          pct:   0 },
    { label: 'Too short', color: '#ef4444',   pct:  20 },
    { label: 'Weak',      color: '#f97316',   pct:  40 },
    { label: 'Fair',      color: '#eab308',   pct:  60 },
    { label: 'Good',      color: '#3b82f6',   pct:  80 },
    { label: 'Strong',    color: '#22c55e',   pct: 100 },
];

function calcPasswordStrength(pw) {
    const checks = {
        len:     pw.length >= 8,
        upper:   /[A-Z]/.test(pw),
        lower:   /[a-z]/.test(pw),
        num:     /[0-9]/.test(pw),
        special: /[^A-Za-z0-9]/.test(pw),
    };
    const score = pw.length === 0 ? 0 : Object.values(checks).filter(Boolean).length;
    return { checks, score };
}

// Render the strength bar + checklist. Pass element IDs as strings.
function renderPasswordStrength(pw, ids) {
    const wrap = document.getElementById(ids.wrap);
    if (!wrap) return;
    if (!pw.length) { wrap.style.display = 'none'; return; }
    wrap.style.display = 'block';

    const { checks, score } = calcPasswordStrength(pw);
    const level = _PW_LEVELS[score];

    const fill = document.getElementById(ids.fill);
    if (fill) { fill.style.width = level.pct + '%'; fill.style.background = level.color; }

    const lbl = document.getElementById(ids.label);
    if (lbl) { lbl.textContent = level.label; lbl.style.color = level.color; }

    const map = { len: ids.rLen, upper: ids.rUpper, lower: ids.rLower, num: ids.rNum, special: ids.rSpecial };
    for (const [key, elId] of Object.entries(map)) {
        const el = document.getElementById(elId);
        if (el) el.classList.toggle('pw-req-met', checks[key]);
    }
}

// IDs for the modal password strength widgets
const _MODAL_PW_IDS = {
    wrap: 'modalPwStrengthWrap', fill: 'modalPwStrengthFill', label: 'modalPwStrengthLabel',
    rLen: 'modal-req-len', rUpper: 'modal-req-upper', rLower: 'modal-req-lower',
    rNum: 'modal-req-num', rSpecial: 'modal-req-special',
};

let _pwCreateMode = true;

function _resetModalPwStrength() {
    const wrap = document.getElementById(_MODAL_PW_IDS.wrap);
    if (wrap) wrap.style.display = 'none';
    ['modal-req-len','modal-req-upper','modal-req-lower','modal-req-num','modal-req-special']
        .forEach(id => { const el = document.getElementById(id); if (el) el.classList.remove('pw-req-met'); });
}

function _updateModalSaveBtn(pw) {
    const btn = document.getElementById('saveUserBtn');
    if (!btn) return;
    const { checks } = calcPasswordStrength(pw);
    if (_pwCreateMode) {
        btn.disabled = !checks.len;
    } else {
        // optional on edit — only block if they started typing but it's too short
        btn.disabled = pw.length > 0 && !checks.len;
    }
}

let _usersAllData = []; // full dataset for filter+paginate

const _roleLabels = {
    admin:        '<span class="badge badge-red">Admin</span>',
    manual_entry: '<span class="badge badge-blue">Manual Entry</span>',
    viewer:       '<span class="badge badge-default">Viewer</span>',
};

let _activeUserTab = 'active';

function switchUserTab(tab) {
    _activeUserTab = tab;
    document.getElementById('activeUsersPane').style.display   = tab === 'active'   ? 'block' : 'none';
    document.getElementById('inactiveUsersPane').style.display = tab === 'inactive' ? 'block' : 'none';
    document.getElementById('tabActiveUsers').classList.toggle('user-tab-active',   tab === 'active');
    document.getElementById('tabInactiveUsers').classList.toggle('user-tab-active', tab === 'inactive');
}

function _applyUsersFilter() {
    const search = (document.getElementById('userSearch')?.value || '').trim().toLowerCase();
    const role   = document.getElementById('userRoleFilter')?.value || '';

    let filtered = _usersAllData;
    if (search) filtered = filtered.filter(u =>
        (u.username || '').toLowerCase().includes(search) ||
        (u.display_name || '').toLowerCase().includes(search) ||
        (u.email || '').toLowerCase().includes(search)
    );
    if (role) filtered = filtered.filter(u => u.role === role);

    const active   = filtered.filter(u =>  u.is_active);
    const inactive = filtered.filter(u => !u.is_active);

    // Update tab counts
    const activeCountEl   = document.getElementById('activeUsersCount');
    const inactiveCountEl = document.getElementById('inactiveUsersCount');
    if (activeCountEl)   activeCountEl.textContent   = active.length;
    if (inactiveCountEl) inactiveCountEl.textContent = inactive.length;

    DVTPaginator._reg['activeUsersBody']?.setItems(active);
    DVTPaginator._reg['inactiveUsersBody']?.setItems(inactive);
}

async function loadUsers() {
    const activeBody   = document.getElementById('activeUsersBody');
    const inactiveBody = document.getElementById('inactiveUsersBody');
    if (!activeBody) return;

    const loadingRow = '<tr><td colspan="5" class="loading"><div class="spinner"></div><span>Loading...</span></td></tr>';
    activeBody.innerHTML   = loadingRow;
    inactiveBody.innerHTML = loadingRow;

    try {
        const data = await apiCall('/api/users');
        _usersAllData = data.users;

        const renderUser = (u) => `<tr>
            <td><strong>${escHtml(u.username)}</strong></td>
            <td>${escHtml(u.email || '-')}</td>
            <td>${escHtml(u.display_name)}</td>
            <td>${_roleLabels[u.role] || escHtml(u.role)}</td>
            <td class="text-center">
                <button class="btn btn-outline btn-sm btn-icon" onclick="editUserModal(${u.id})" title="Edit">
                    <span class="material-icons-round">edit</span>
                </button>
                <button class="btn btn-outline btn-sm btn-icon" onclick='deleteUser(${u.id},${JSON.stringify(u.username)})' title="Delete" style="color:var(--accent-red)">
                    <span class="material-icons-round">delete</span>
                </button>
            </td>
        </tr>`;

        new DVTPaginator({
            tbodyId:      'activeUsersBody',
            paginationId: 'activeUsersPagination',
            perPage:      25,
            colSpan:      5,
            emptyMsg:     'No active users',
            renderItem:   renderUser,
        });

        new DVTPaginator({
            tbodyId:      'inactiveUsersBody',
            paginationId: 'inactiveUsersPagination',
            perPage:      25,
            colSpan:      5,
            emptyMsg:     'No inactive users',
            renderItem:   renderUser,
        });

        _applyUsersFilter();
    } catch (err) {
        const errRow = '<tr><td colspan="5" style="text-align:center;padding:40px;color:var(--accent-red)">Failed to load users</td></tr>';
        if (activeBody)   activeBody.innerHTML   = errRow;
        if (inactiveBody) inactiveBody.innerHTML = errRow;
    }
}

// Keep _usersCache as alias so editUserModal still works
let _usersCache = [];

function showAddUserModal() {
    _pwCreateMode = true;
    document.getElementById('userModalTitle').textContent = 'Add User';
    document.getElementById('editingUserId').value = '';
    document.getElementById('modalUsername').value = '';
    document.getElementById('modalUsername').disabled = false;
    document.getElementById('modalEmail').value = '';
    document.getElementById('modalEmail').disabled = false;
    document.getElementById('modalDisplayName').value = '';
    document.getElementById('modalRole').value = 'viewer';
    document.getElementById('modalPassword').value = '';
    document.getElementById('passwordLabel').textContent = 'Password';
    document.getElementById('passwordHint').textContent = '';
    document.getElementById('activeGroup').style.display = 'none';
    document.getElementById('plantAccessGroup').style.display = 'none';
    document.getElementById('targetsPermGroup').style.display = 'none';
    document.getElementById('modalCanUpdateTargets').checked = false;
    document.getElementById('empDetailsGroup').style.display = 'none';
    document.getElementById('modalCanEditEmp').checked = false;
    setAccessScope('all');
    _allPlantsCache = [];
    _resetModalPwStrength();
    const btn = document.getElementById('saveUserBtn');
    if (btn) btn.disabled = true;
    document.getElementById('userModal').classList.add('show');
}

async function editUserModal(userId) {
    // Use cached data; re-fetch only if empty
    if (_usersAllData.length === 0) {
        try {
            const data = await apiCall('/api/users');
            _usersAllData = data.users;
        } catch { return; }
    }
    _usersCache = _usersAllData; // keep alias in sync

    const user = _usersAllData.find(u => u.id === userId);
    if (!user) return;

    _pwCreateMode = false;
    document.getElementById('userModalTitle').textContent = 'Edit User';
    document.getElementById('editingUserId').value = user.id;
    document.getElementById('modalUsername').value = user.username;
    document.getElementById('modalUsername').disabled = true;
    document.getElementById('modalEmail').value = user.email || '';
    document.getElementById('modalEmail').disabled = false;
    document.getElementById('modalDisplayName').value = user.display_name;
    document.getElementById('modalRole').value = user.role;
    document.getElementById('modalPassword').value = '';
    document.getElementById('passwordLabel').textContent = 'New Password (optional)';
    document.getElementById('passwordHint').textContent = 'Leave blank to keep current password';
    document.getElementById('activeGroup').style.display = 'block';
    document.getElementById('modalActive').checked = user.is_active;
    const isManualEntry = user.role === 'manual_entry';
    document.getElementById('plantAccessGroup').style.display = isManualEntry ? 'block' : 'none';
    if (isManualEntry) _loadUserPlantAccess(user.id);
    // Employee details permission toggle — visible for non-admin users
    document.getElementById('empDetailsGroup').style.display = user.role !== 'admin' ? 'block' : 'none';
    document.getElementById('modalCanEditEmp').checked = user.can_edit_employee_details || false;
    // Targets permission toggle — manual_entry only
    document.getElementById('targetsPermGroup').style.display = isManualEntry ? 'block' : 'none';
    document.getElementById('modalCanUpdateTargets').checked = isManualEntry && (user.can_update_targets || false);
    _resetModalPwStrength();
    const btn = document.getElementById('saveUserBtn');
    if (btn) btn.disabled = false;
    document.getElementById('userModal').classList.add('show');
}

function closeUserModal() {
    document.getElementById('userModal').classList.remove('show');
}

async function saveUser() {
    const userId = document.getElementById('editingUserId').value;
    const username = document.getElementById('modalUsername').value.trim();
    const email = document.getElementById('modalEmail').value.trim();
    const displayName = document.getElementById('modalDisplayName').value.trim();
    const role = document.getElementById('modalRole').value;
    const password = document.getElementById('modalPassword').value;

    if (!userId && !username) {
        showToast('Username is required', 'error');
        return;
    }
    if (!email) {
        showToast('Email is required', 'error');
        return;
    }

    try {
        let targetUserId = userId;
        if (userId) {
            const body = {
                email,
                display_name: displayName,
                role,
                is_active: document.getElementById('modalActive').checked,
                can_edit_employee_details: document.getElementById('modalCanEditEmp').checked,
                can_update_targets: role === 'manual_entry' && document.getElementById('modalCanUpdateTargets').checked,
            };
            if (password) body.password = password;

            await apiCall(`/api/users/${userId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            showToast('User updated', 'success');
        } else {
            if (!password || password.length < 8) {
                showToast('Password must be at least 8 characters', 'error');
                return;
            }
            const result = await apiCall('/api/users', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, email, display_name: displayName, role, password }),
            });
            targetUserId = result.user.id;
            showToast('User created', 'success');
        }

        // Save plant access if role is manual_entry
        if (role === 'manual_entry' && targetUserId) {
            const allPlants = document.getElementById('btnAllPlants').classList.contains('scope-active');
            const plantCodes = allPlants ? [] : _getSelectedPlantCodes();
            await apiCall(`/api/users/${targetUserId}/plant-access`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ manual_entry_all_plants: allPlants, plant_codes: plantCodes }),
            });
        }

        closeUserModal();
        loadUsers();
    } catch (err) {
        // Error shown by apiCall
    }
}

async function deleteUser(userId, username) {
    const ok = await showConfirm(
        `Delete user "${username}"? This action cannot be undone.`,
        'Delete User'
    );
    if (!ok) return;

    try {
        await apiCall(`/api/users/${userId}`, { method: 'DELETE' });
        showToast(`User ${username} deleted`, 'success');
        loadUsers();
    } catch (err) {
        // Error shown by apiCall
    }
}

// ── Plant Access (user modal) ──────────────────────────────────────────────────

let _allPlantsCache = [];

function setAccessScope(scope) {
    const allBtn      = document.getElementById('btnAllPlants');
    const specificBtn = document.getElementById('btnSpecificPlants');
    const listWrap    = document.getElementById('plantAccessListWrap');
    if (!allBtn) return;
    if (scope === 'all') {
        allBtn.classList.add('scope-active');
        specificBtn.classList.remove('scope-active');
        listWrap.style.display = 'none';
    } else {
        specificBtn.classList.add('scope-active');
        allBtn.classList.remove('scope-active');
        listWrap.style.display = 'block';
    }
}

async function _loadUserPlantAccess(userId) {
    const itemsEl = document.getElementById('plantAccessItems');
    if (!itemsEl) return;
    itemsEl.innerHTML = '<div style="padding:14px;text-align:center;color:var(--text-muted);font-size:0.85rem;">Loading plants…</div>';

    try {
        const [plantsData, accessData] = await Promise.all([
            apiCall('/api/plants'),
            userId
                ? apiCall(`/api/users/${userId}/plant-access`)
                : Promise.resolve({ manual_entry_all_plants: true, plant_codes: [] }),
        ]);

        _allPlantsCache = plantsData.plants.filter(p => p.is_active);
        setAccessScope(accessData.manual_entry_all_plants ? 'all' : 'specific');
        _renderPlantAccessItems(_allPlantsCache, accessData.plant_codes || []);
        _updatePlantSelectionCount();
    } catch (err) {
        itemsEl.innerHTML = '<div style="padding:14px;text-align:center;color:var(--accent-red);font-size:0.85rem;">Failed to load plants</div>';
    }
}

function _renderPlantAccessItems(plants, selectedCodes) {
    const itemsEl = document.getElementById('plantAccessItems');
    if (!itemsEl) return;

    if (plants.length === 0) {
        itemsEl.innerHTML = '<div style="padding:16px;text-align:center;color:var(--text-muted);font-size:0.85rem;">No plants match your search</div>';
        return;
    }

    const selectedSet = new Set(selectedCodes);
    let html = '';
    for (const p of plants) {
        const checked = selectedSet.has(p.plant_code);
        const name = escHtml(p.daily_tracker_name || p.erp_name || p.plant_code);
        html += `<label class="plant-access-item ${checked ? 'is-checked' : ''}"
                        onchange="this.classList.toggle('is-checked', this.querySelector('input').checked); _updatePlantSelectionCount();">
            <input type="checkbox" ${checked ? 'checked' : ''} value="${escHtml(p.plant_code)}">
            <span class="badge badge-blue pa-code">${escHtml(p.plant_code)}</span>
            <span class="pa-name">${name}</span>
            ${p.region ? `<span class="pa-region">${escHtml(p.region)}</span>` : ''}
        </label>`;
    }
    itemsEl.innerHTML = html;
}

function _updatePlantSelectionCount() {
    const countEl = document.getElementById('plantSelectionCount');
    if (!countEl) return;
    const total    = _allPlantsCache.length;
    const selected = _getSelectedPlantCodes().length;
    countEl.textContent = selected === 0
        ? 'None selected'
        : `${selected} of ${total} plant${total !== 1 ? 's' : ''} selected`;
}

function filterPlantAccessList() {
    const search = (document.getElementById('plantAccessSearch').value || '').toLowerCase();
    const selectedCodes = _getSelectedPlantCodes();
    const filtered = _allPlantsCache.filter(p =>
        !search ||
        (p.plant_code || '').toLowerCase().includes(search) ||
        (p.daily_tracker_name || '').toLowerCase().includes(search) ||
        (p.region || '').toLowerCase().includes(search)
    );
    _renderPlantAccessItems(filtered, selectedCodes);
    _updatePlantSelectionCount();
}

function selectAllPlants(select) {
    document.querySelectorAll('#plantAccessItems input[type="checkbox"]').forEach(cb => {
        cb.checked = select;
        cb.closest('.plant-access-item').classList.toggle('is-checked', select);
    });
    _updatePlantSelectionCount();
}

function _getSelectedPlantCodes() {
    return Array.from(
        document.querySelectorAll('#plantAccessItems input[type="checkbox"]:checked')
    ).map(cb => cb.value);
}
