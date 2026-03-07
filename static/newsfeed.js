'use strict';

/**
 * newsfeed.js — S1 外野 daily newsfeed page logic
 *
 * Fetches status and latest data from the server and renders
 * summarised posts as cards. Polls every 10 seconds while a job
 * is in progress, then switches to a 5-minute idle poll.
 */

const POLL_ACTIVE_MS = 10_000;   // poll every 10 s while running
const POLL_IDLE_MS = 300_000;  // poll every 5 min otherwise

let pollTimer = null;

// ---------------------------------------------------------------------------
// DOM helpers
// ---------------------------------------------------------------------------

/**
 * Show exactly one state section; hide the rest.
 * The progress-banner is controlled separately via updateProgressBanner.
 * @param {'loading'|'empty'|'running'|'posts'} state
 */
function showState(state) {
    try {
        const sections = {
            loading: document.getElementById('loading-state'),
            empty: document.getElementById('empty-state'),
            running: document.getElementById('running-state'),
            posts: document.getElementById('posts-grid'),
        };
        Object.entries(sections).forEach(([key, el]) => {
            if (el) el.style.display = key === state ? '' : 'none';
        });
        // Hide progress banner when not on the posts state
        if (state !== 'posts') hideProgressBanner();
    } catch (error) {
        console.error('showState error:', error);
    }
}

/**
 * Show or hide the progress banner with current progress.
 * @param {object|null} progress  - {done, total} or null to hide
 */
function updateProgressBanner(progress) {
    try {
        const banner = document.getElementById('progress-banner');
        const fill = document.getElementById('progress-fill');
        const label = document.getElementById('progress-label');
        if (!banner) return;
        if (!progress) {
            banner.style.display = 'none';
            return;
        }
        const pct = progress.total > 0 ? Math.round((progress.done / progress.total) * 100) : 0;
        if (fill) fill.style.width = `${pct}%`;
        if (label) label.textContent = `摘要进度：${progress.done} / ${progress.total} 篇`;
        banner.style.display = '';
    } catch (error) {
        console.error('updateProgressBanner error:', error);
    }
}

/** Hide the progress banner. */
function hideProgressBanner() {
    const banner = document.getElementById('progress-banner');
    if (banner) banner.style.display = 'none';
}

/**
 * Parse and sanitize markdown text using marked.js.
 * @param {string} text
 * @returns {string} HTML string
 */
function renderMarkdown(text) {
    try {
        if (typeof marked !== 'undefined') {
            return marked.parse(String(text));
        }
    } catch (e) {
        console.error('renderMarkdown error:', e);
    }
    // Fallback: plain text with escaped HTML
    return escapeHtml(text).replace(/\n/g, '<br>');
}

/**
 * Update the header meta line with date and status badge.
 * @param {object} status  - API /api/newsfeed/status response
 */
function updateMeta(status) {
    try {
        const metaDate = document.getElementById('meta-date');
        const metaStatus = document.getElementById('meta-status');
        const actionHint = document.getElementById('action-hint');

        if (status.last_date) {
            metaDate.textContent = `数据日期：${status.last_date}`;
        } else {
            metaDate.textContent = '暂无历史数据';
        }

        if (status.is_running) {
            metaStatus.textContent = '⚙️ 生成中…';
            metaStatus.className = 'meta-status status-running';
            actionHint.textContent = '正在后台摘要，请稍等…';
        } else if (status.ready) {
            metaStatus.textContent = `✅ 已就绪（${status.post_count} 篇）`;
            metaStatus.className = 'meta-status status-ready';
            actionHint.textContent = '';
        } else {
            metaStatus.textContent = '📭 尚未生成';
            metaStatus.className = 'meta-status status-empty';
            actionHint.textContent = '';
        }
    } catch (error) {
        console.error('updateMeta error:', error);
    }
}

/**
 * Escape HTML special characters to prevent XSS.
 * @param {string} str
 * @returns {string}
 */
function escapeHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

/**
 * Render the list of post summaries into the posts grid.
 * @param {Array} posts
 */
/**
 * Dismiss a post card with animation, then scroll to the next card.
 * @param {HTMLElement} card - the article.post-card element
 */
function dismissPost(card) {
    const next = card.nextElementSibling;
    card.classList.add('dismissed');
    card.addEventListener('animationend', () => {
        card.style.display = 'none';
        if (next) {
            const nav = document.querySelector('.navigation');
            const navHeight = nav ? nav.getBoundingClientRect().height : 0;
            const top = next.getBoundingClientRect().top + window.scrollY - navHeight - 12;
            window.scrollTo({ top, behavior: 'smooth' });
        }
    }, { once: true });
}

/**
 * Render the list of post summaries into the posts grid.
 * @param {Array} posts
 */
function renderPosts(posts) {
    try {
        const grid = document.getElementById('posts-grid');
        if (!grid) return;

        if (!posts || posts.length === 0) {
            showState('empty');
            return;
        }

        grid.innerHTML = posts.map((post, index) => {
            return `
            <article class="post-card" onclick="dismissPost(this)" title="点击关闭">
                <div class="post-rank">${index + 1}</div>
                <div class="post-body">
                    <div class="post-header">
                        <a class="post-title"
                           href="${escapeHtml(post.url)}"
                           target="_blank"
                           rel="noopener noreferrer"
                           onclick="event.stopPropagation()">
                            ${escapeHtml(post.title)}
                        </a>
                        <span class="post-badge">+${escapeHtml(String(post.reply_count))} 回复</span>
                    </div>
                    <div class="post-summary markdown-body">${renderMarkdown(post.summary || '暂无摘要')}</div>
                </div>
            </article>`;
        }).join('');


        showState('posts');
    } catch (error) {
        console.error('renderPosts error:', error);
    }
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

/**
 * Fetch current status and latest data, then update the UI.
 */
async function refresh() {
    try {
        const [statusRes, latestRes] = await Promise.all([
            fetch('/api/newsfeed/status'),
            fetch('/api/newsfeed/latest'),
        ]);

        if (!statusRes.ok || !latestRes.ok) {
            console.error('API error', statusRes.status, latestRes.status);
            return;
        }

        const status = await statusRes.json();
        const latest = await latestRes.json();

        updateMeta(status);

        const hasPosts = latest.posts && latest.posts.length > 0;
        const isPartial = latest.partial === true;

        if (hasPosts) {
            // Show whatever cards we have — partial or complete
            renderPosts(latest.posts);
            if (isPartial || status.is_running) {
                updateProgressBanner(latest.progress || null);
                schedulePoll(POLL_ACTIVE_MS);
            } else {
                hideProgressBanner();
                schedulePoll(POLL_IDLE_MS);
            }
        } else if (status.is_running) {
            showState('running');
            schedulePoll(POLL_ACTIVE_MS);
        } else {
            showState('empty');
            schedulePoll(POLL_IDLE_MS);
        }
    } catch (error) {
        console.error('refresh error:', error);
    }
}

/**
 * Trigger a manual refresh job on the server.
 */
async function triggerManualRun() {
    try {
        const btn = document.getElementById('btn-refresh');
        const icon = document.getElementById('refresh-icon');
        if (btn) btn.disabled = true;
        if (icon) icon.textContent = '⏳';

        const res = await fetch('/api/newsfeed/run', { method: 'POST' });
        const data = await res.json();
        console.log('Manual run:', data);

        // Switch to active polling immediately
        schedulePoll(POLL_ACTIVE_MS);
        await refresh();
    } catch (error) {
        console.error('triggerManualRun error:', error);
    } finally {
        const btn = document.getElementById('btn-refresh');
        const icon = document.getElementById('refresh-icon');
        if (btn) btn.disabled = false;
        if (icon) icon.textContent = '🔄';
    }
}

// ---------------------------------------------------------------------------
// Polling
// ---------------------------------------------------------------------------

/**
 * Schedule the next poll, cancelling any previous timer.
 * @param {number} delayMs
 */
function schedulePoll(delayMs) {
    if (pollTimer) clearTimeout(pollTimer);
    pollTimer = setTimeout(refresh, delayMs);
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('btn-refresh').addEventListener('click', triggerManualRun);
    refresh();
});
