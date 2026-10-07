/**
 * Raw data pull from all four public sources (no relevancy / filtering).
 * Aligned with config/run.yaml and pipeline/adapters/*.
 *
 * Usage:
 *   npm install
 *   # optional: export GOOGLE_CSE_API_KEY=... GOOGLE_CSE_CX=...
 *   npm run fetch-raw
 *
 * Output: photo_retrieval_feedback.json
 */

const fs = require('fs');
const path = require('path');
const yaml = require('js-yaml');

const CONFIG_PATH = path.join(__dirname, 'config', 'run.yaml');
const OUT_FILE = path.join(__dirname, 'photo_retrieval_feedback.json');
const USER_AGENT = 'PhotosDiscoveryEngine/0.1 (research; public data only)';

const ARCTIC_BASE = 'https://arctic-shift.photon-reddit.com';
const THREAD_URL_RE = /https?:\/\/support\.google\.com\/photos\/thread\/([a-zA-Z0-9_-]+)/gi;

function loadConfig() {
  return yaml.load(fs.readFileSync(CONFIG_PATH, 'utf8'));
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchText(url, options = {}) {
  const res = await fetch(url, {
    ...options,
    headers: {
      'User-Agent': USER_AGENT,
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status} for ${url}`);
  }
  return res.text();
}

async function fetchJson(url, options = {}) {
  const text = await fetchText(url, options);
  return JSON.parse(text);
}

// ——— Apple App Store (JSON RSS, pages 1–10, dedupe by review id) ———
function isReviewEntry(entry) {
  return entry && entry.id?.label && entry['im:rating'];
}

function normalizeFeedEntries(feed) {
  const entries = feed?.entry;
  if (entries == null) return [];
  if (Array.isArray(entries)) return entries;
  if (typeof entries === 'object') return [entries];
  throw new Error('App Store feed.entry is not a list or object');
}

function parseAppStoreFeed(data, storefront) {
  const entries = normalizeFeedEntries(data?.feed);
  const reviews = [];
  for (const entry of entries) {
    if (!isReviewEntry(entry)) continue;
    const reviewId = String(entry.id.label);
    const title = entry.title?.label || '';
    const body = entry.content?.label || '';
    const combined = body ? `${title}\n${body}`.trim() : title.trim();
    reviews.push({
      source: 'app_store',
      native_id: reviewId,
      storefront,
      title,
      text: combined,
      rating: entry['im:rating']?.label ?? null,
      authored_at: entry.updated?.label ?? null,
      source_url: entry.link?.attributes?.href ?? null,
      raw_entry: entry,
    });
  }
  return reviews;
}

async function fetchAppleReviews(cfg) {
  const appId = cfg.app_store.app_id;
  const storefronts = cfg.app_store.storefronts || ['us'];
  const maxPages = cfg.app_store.max_pages_per_storefront ?? 10;
  const seen = new Set();
  const items = [];
  const errors = [];

  for (const storefront of storefronts) {
    for (let page = 1; page <= maxPages; page++) {
      const url =
        `https://itunes.apple.com/${storefront}/rss/customerreviews/` +
        `page=${page}/id=${appId}/sortby=mostrecent/json`;
      try {
        const data = await fetchJson(url);
        const pageItems = parseAppStoreFeed(data, storefront);
        if (pageItems.length === 0) break;
        for (const item of pageItems) {
          if (seen.has(item.native_id)) continue;
          seen.add(item.native_id);
          items.push(item);
        }
        await sleep(400);
      } catch (err) {
        errors.push(`${storefront} p${page}: ${err.message}`);
        if (String(err.message).includes('404')) break;
      }
    }
  }

  const status = errors.length && items.length ? 'partial' : errors.length && !items.length ? 'failed' : 'success';
  return {
    items,
    receipt: {
      status,
      item_count: items.length,
      notes: errors.length ? errors.join('; ') : 'RSS JSON collection complete.',
      coverage_limits: [
        '~500 most recent written reviews per storefront (pages 1–10); deduped by review id.',
      ],
    },
  };
}

// ——— Google Play (google-play-scraper) ———
async function fetchGooglePlayReviews(cfg) {
  const appId = cfg.play_store.package_name;
  if (appId !== 'com.google.android.apps.photos') {
    return {
      items: [],
      receipt: {
        status: 'failed',
        item_count: 0,
        notes: `Wrong package ${appId}`,
      },
    };
  }

  try {
    const gplay = require('google-play-scraper');
    const result = await gplay.reviews({
      appId,
      sort: gplay.sort.NEWEST,
      num: 500,
      throttle: 10,
    });
    const rows = Array.isArray(result) ? result : result?.data || [];
    const items = rows.map((review) => ({
      source: 'play_store',
      native_id: String(review.id),
      text: review.text || '',
      rating: review.score ?? null,
      author: review.userName ?? null,
      authored_at: review.date ? new Date(review.date).toISOString() : null,
      source_url: `https://play.google.com/store/apps/details?id=${appId}&reviewId=${review.id}`,
      developer_reply: review.replyText ?? null,
      raw: review,
    }));

    return {
      items,
      receipt: {
        status: items.length ? 'success' : 'partial',
        item_count: items.length,
        notes: 'google-play-scraper (batchexecute).',
        coverage_limits: ['Undocumented RPC; no official history ceiling.'],
      },
    };
  } catch (err) {
    return {
      items: [],
      receipt: {
        status: 'failed',
        item_count: 0,
        notes: `${err.message}. Run: npm install google-play-scraper`,
      },
    };
  }
}

function normalizeArcticList(payload) {
  if (!payload || typeof payload !== 'object') return [];
  if (payload.error) {
    throw new Error(String(payload.error));
  }
  const list = payload.data;
  if (list == null) return [];
  if (Array.isArray(list)) return list;
  if (typeof list === 'object') {
    const nested = list.children || list.items;
    return Array.isArray(nested) ? nested : [];
  }
  return [];
}

function unwrapRedditRow(row) {
  return row?.data && typeof row.data === 'object' ? row.data : row;
}

function inDateWindow(createdUtc, after, before) {
  if (createdUtc == null) return true;
  const ms = typeof createdUtc === 'number' ? createdUtc * 1000 : Date.parse(createdUtc);
  if (Number.isNaN(ms)) return true;
  if (after && ms < Date.parse(after)) return false;
  if (before && ms > Date.parse(before)) return false;
  return true;
}

// ——— Reddit (Arctic Shift API: query= posts, body= comments) ———
// https://github.com/ArthurHeitmann/arctic_shift/tree/master/api
async function fetchReddit(cfg) {
  const subs = cfg.reddit.subreddits || ['googlephotos'];
  const keywords = cfg.reddit.keywords || ['search'];
  const limit = Math.min(cfg.reddit.posts_per_request || 100, 100);
  const includeComments = cfg.reddit.include_comments !== false;
  const after = cfg.date_window?.after;
  const before = cfg.date_window?.before;
  const seen = new Set();
  const items = [];

  try {
    for (const subreddit of subs) {
      for (const q of keywords) {
        const postsUrl = new URL(`${ARCTIC_BASE}/api/posts/search`);
        postsUrl.searchParams.set('subreddit', subreddit);
        postsUrl.searchParams.set('query', q);
        postsUrl.searchParams.set('limit', String(limit));
        postsUrl.searchParams.set('sort', 'asc');
        if (after) postsUrl.searchParams.set('after', after);
        if (before) postsUrl.searchParams.set('before', before);

        const postsPayload = await fetchJson(postsUrl.toString());
        const posts = normalizeArcticList(postsPayload);

        for (const rawPost of posts) {
          const post = unwrapRedditRow(rawPost);
          if (!post?.id) continue;
          if (!inDateWindow(post.created_utc, after, before)) continue;
          const postId = String(post.id);
          if (seen.has(`post:${postId}`)) continue;
          seen.add(`post:${postId}`);

          const title = post.title || '';
          let selftext = post.selftext || '';
          if (selftext === '[deleted]' || selftext === '[removed]') selftext = '';

          items.push({
            source: 'reddit',
            kind: 'post',
            native_id: postId,
            subreddit,
            query: q,
            title,
            text: `${title}\n${selftext}`.trim(),
            authored_at: post.created_utc != null ? String(post.created_utc) : null,
            source_url: post.permalink?.startsWith('http')
              ? post.permalink
              : post.permalink
                ? `https://www.reddit.com${post.permalink}`
                : null,
            raw: post,
          });
        }

        if (includeComments) {
          const commentsUrl = new URL(`${ARCTIC_BASE}/api/comments/search`);
          commentsUrl.searchParams.set('subreddit', subreddit);
          commentsUrl.searchParams.set('body', q);
          commentsUrl.searchParams.set('limit', String(limit));
          commentsUrl.searchParams.set('sort', 'asc');
          if (after) commentsUrl.searchParams.set('after', after);
          if (before) commentsUrl.searchParams.set('before', before);

          const commentsPayload = await fetchJson(commentsUrl.toString());
          const comments = normalizeArcticList(commentsPayload);

          for (const rawComment of comments) {
            const comment = unwrapRedditRow(rawComment);
            if (!comment?.id) continue;
            if (!inDateWindow(comment.created_utc, after, before)) continue;
            const cid = String(comment.id);
            if (seen.has(`comment:${cid}`)) continue;
            seen.add(`comment:${cid}`);

            let body = comment.body || '';
            if (body === '[deleted]' || body === '[removed]') body = '';

            items.push({
              source: 'reddit',
              kind: 'comment',
              native_id: cid,
              subreddit,
              query: q,
              text: body,
              authored_at: comment.created_utc != null ? String(comment.created_utc) : null,
              source_url: comment.permalink?.startsWith('http')
                ? comment.permalink
                : comment.permalink
                  ? `https://www.reddit.com${comment.permalink}`
                  : null,
              thread_context: null,
              raw: comment,
            });
          }
        }

        await sleep(500);
      }
    }

    return {
      items,
      receipt: {
        status: items.length ? 'success' : 'partial',
        item_count: items.length,
        notes: 'Arctic Shift subreddit-scoped keyword search.',
        coverage_limits: ['Not all of Reddit; keyword + sub limits apply.'],
      },
    };
  } catch (err) {
    return {
      items,
      receipt: {
        status: 'gap',
        item_count: items.length,
        notes: `Arctic Shift unavailable: ${err.message}. No paid Reddit API fallback.`,
      },
    };
  }
}

// ——— Help Community (CSE thread URLs + browse seeds; per-thread HTML) ———
function canonicalThreadUrl(url) {
  const m = url.match(/support\.google\.com\/photos\/thread\/[a-zA-Z0-9_-]+/i);
  if (!m) return null;
  return `https://${m[0].replace(/\/$/, '')}`;
}

function filterThreadUrls(urls) {
  const seen = new Set();
  const out = [];
  for (const u of urls) {
    const norm = canonicalThreadUrl(u);
    if (!norm) continue;
    const id = norm.split('/').pop();
    if (seen.has(id)) continue;
    seen.add(id);
    out.push(norm);
  }
  return out;
}

async function discoverHelpThreads(discovery) {
  const notes = [];
  let urls = [];
  const mode = discovery.mode || 'cse_then_browse';
  const siteRestrict = discovery.site_restrict || 'support.google.com/photos/thread';
  const queries =
    discovery.queries || [
      "can't find photos search",
      'find old photos',
      'search photos metadata',
    ];
  const budget = discovery.cse_daily_query_budget ?? 100;

  if (mode === 'cse_only' || mode === 'cse_then_browse') {
    const key = process.env.GOOGLE_CSE_API_KEY;
    const cx = process.env.GOOGLE_CSE_CX;
    if (!key || !cx) {
      notes.push('CSE credentials missing (GOOGLE_CSE_API_KEY, GOOGLE_CSE_CX).');
    } else {
      for (let i = 0; i < Math.min(queries.length, budget); i++) {
        const q = queries[i];
        const u = new URL('https://www.googleapis.com/customsearch/v1');
        u.searchParams.set('key', key);
        u.searchParams.set('cx', cx);
        u.searchParams.set('q', q);
        u.searchParams.set('siteSearch', siteRestrict);
        u.searchParams.set('siteSearchFilter', 'i');
        try {
          const data = await fetchJson(u.toString());
          for (const item of data.items || []) {
            if (item.link) urls.push(item.link);
          }
          await sleep(300);
        } catch (err) {
          notes.push(`CSE failed: ${err.message}`);
          break;
        }
      }
    }
  }

  urls = filterThreadUrls(urls);

  if ((mode === 'browse_only' || mode === 'cse_then_browse') && urls.length === 0) {
    const seeds = discovery.browse_seed_urls || ['https://support.google.com/photos/threads'];
    for (const seed of seeds) {
      try {
        const html = await fetchText(seed);
        let match;
        THREAD_URL_RE.lastIndex = 0;
        while ((match = THREAD_URL_RE.exec(html)) !== null) {
          urls.push(match[0]);
        }
        urls = filterThreadUrls(urls);
        await sleep(500);
      } catch (err) {
        notes.push(`Browse ${seed}: ${err.message}`);
      }
    }
  }

  return { urls: filterThreadUrls(urls), notes };
}

function parseHelpThreadHtml(html, url) {
  if (/accounts\.google\.com/i.test(html) && /signin/i.test(html)) {
    throw new Error('Login wall; aborting thread fetch');
  }

  const cheerio = require('cheerio');
  const $ = cheerio.load(html);
  const title = $('title').first().text().trim();
  const blocks = [];
  $('[data-message-type], .cc-reply, article').each((_, el) => {
    const t = $(el).text().replace(/\s+/g, ' ').trim();
    if (t) blocks.push(t);
  });
  const question = blocks[0] || $('body').text().replace(/\s+/g, ' ').trim().slice(0, 8000);
  const replies = blocks.slice(1, 31);

  const threadId = url.split('/').pop();
  return {
    source: 'help_community',
    native_id: threadId,
    title,
    text: question,
    thread_context: replies.length ? replies.join('\n---\n') : null,
    source_url: url,
    reply_count: replies.length,
  };
}

async function fetchHelpCommunity(cfg) {
  const discovery = cfg.help_community?.discovery || {};
  const { urls, notes: discoveryNotes } = await discoverHelpThreads(discovery);
  const items = [];
  let discoveryWithoutFetch = 0;
  const fetchNotes = [];

  for (const url of urls) {
    try {
      const html = await fetchText(url);
      const item = parseHelpThreadHtml(html, url);
      items.push(item);
      await sleep(400);
    } catch (err) {
      if (String(err.message).includes('404')) {
        discoveryWithoutFetch += 1;
      } else {
        fetchNotes.push(`${url}: ${err.message}`);
      }
    }
  }

  const status = items.length ? 'success' : urls.length ? 'partial' : 'gap';
  const notes = [...discoveryNotes, ...fetchNotes].filter(Boolean).join('; ');
  return {
    items,
    receipt: {
      status,
      item_count: items.length,
      notes:
        (notes || 'Help Community thread fetch complete.') +
        (discoveryWithoutFetch ? ` discovery-without-fetch=${discoveryWithoutFetch}.` : ''),
      coverage_limits: ['CSE/browse discovery is not a complete forum census.'],
      threads_discovered: urls.length,
    },
  };
}

async function main() {
  const cfg = loadConfig();
  console.log('Raw collection (no relevancy). Config:', CONFIG_PATH);
  console.log(`Started: ${new Date().toISOString()}\n`);

  const receipts = {};
  const raw = {};

  console.log('1/4 App Store…');
  const apple = await fetchAppleReviews(cfg);
  raw.app_store = apple.items;
  receipts.app_store = apple.receipt;
  console.log(`   ${apple.receipt.status}: ${apple.items.length} items`);

  console.log('2/4 Reddit…');
  const reddit = await fetchReddit(cfg);
  raw.reddit = reddit.items;
  receipts.reddit = reddit.receipt;
  console.log(`   ${reddit.receipt.status}: ${reddit.items.length} items`);

  console.log('3/4 Play Store…');
  const play = await fetchGooglePlayReviews(cfg);
  raw.play_store = play.items;
  receipts.play_store = play.receipt;
  console.log(`   ${play.receipt.status}: ${play.items.length} items`);

  console.log('4/4 Help Community…');
  const help = await fetchHelpCommunity(cfg);
  raw.help_community = help.items;
  receipts.help_community = help.receipt;
  console.log(`   ${help.receipt.status}: ${help.items.length} items`);

  const total =
    raw.app_store.length +
    raw.play_store.length +
    raw.reddit.length +
    raw.help_community.length;

  const output = {
    schema: 'photos-discovery-raw-v1',
    collection_date: new Date().toISOString(),
    config_path: 'config/run.yaml',
    total_items: total,
    receipts,
    raw,
  };

  fs.writeFileSync(OUT_FILE, JSON.stringify(output, null, 2));

  console.log('\n=== Summary ===');
  console.log(`App Store:        ${raw.app_store.length}`);
  console.log(`Play Store:       ${raw.play_store.length}`);
  console.log(`Reddit:           ${raw.reddit.length}`);
  console.log(`Help Community:   ${raw.help_community.length}`);
  console.log(`Total:            ${total}`);
  console.log(`Written:          ${OUT_FILE}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
