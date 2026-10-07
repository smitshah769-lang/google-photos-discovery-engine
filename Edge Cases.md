# AI Discovery Engine — Edge Cases

**Document type**: Implementation and research edge cases  
**Aligned to**: [System Architecture.md](./System%20Architecture.md) v1.2, [Problem Statement .md](./Problem%20Statement%20.md) v2.2  
**Scope**: One-time four-source discovery snapshot (Play Store, App Store, Reddit, Google Photos Help Community)

This file lists cases the pipeline, models, and UI must handle without silent data loss, invented evidence, or overstated claims. Expected handling is the contract; if a case is skipped, record it on the `SourceRun` receipt and the How the Engine Works tab.

---

## 1. How to use this document

| Column | Meaning |
|--------|---------|
| **Case** | What goes wrong or is unusual |
| **Handling** | What the engine must do |
| **Surface** | Where researchers see it (pipeline log, methodology, dashboard, RAG, evidence drawer) |

Severity for implementation:

- **Blocker**: Can corrupt the snapshot or invent evidence; fail the run or omit the item with an explicit reason
- **Must**: Correctness of counts, labels, or citations
- **Should**: Coverage, UX, or methodology honesty

---

## 2. Collection — Apple App Store RSS

| Case | Handling | Sev |
|------|----------|-----|
| First `feed.entry` is app metadata, not a review | Skip entries without `im:rating` and a review id | Must |
| Empty body / title-only / star rating with no text | Do not count as analysis corpus; keep in raw store if desired | Must |
| Page 11+ or empty page after page 10 | Stop; receipt notes ~500/storefront cap | Must |
| Same review id on `us` and `gb` (or other storefronts) | Dedupe by native review id; keep one canonical item, record storefronts seen | Must |
| Storefront returns 404 / unknown country code | Skip that country; do not abort the whole App Store run | Must |
| Feed switches XML vs JSON or field names | Fail that `SourceRun` with parse error; do not guess fields | Blocker |
| `updated` date is missing or unparseable | `authored_at = null`; still ingest if text exists | Should |
| Non-English review in a non-US storefront | Keep; set `locale` from storefront; do not drop solely for language | Must |
| Rate limit / HTTP 429 | Back off, resume; if still failing, partial receipt with last successful page | Must |

**Research caveat**: RSS is recency-biased. Dashboard must not imply historical App Store incidence. Old incomplete-memory complaints may be invisible on this channel.

---

## 3. Collection — Google Play `batchexecute`

| Case | Handling | Sev |
|------|----------|-----|
| Response prefixed with `)]}'` or nested JSON-as-string | Parser must unwrap; fixture-test this path | Blocker |
| Payload shape changes (unlabeled arrays shift) | Fail `SourceRun` clearly; do not map by “best guess” index | Blocker |
| Continuation token null / repeats / loops | Stop when token missing, unchanged, or already seen | Must |
| HTTP 200 with empty review list for a locale | Treat as empty locale, not as app-not-found, unless a details check proves otherwise | Must |
| Wrong package name vs `com.google.android.apps.photos` | Fail fast; do not silently collect another app | Blocker |
| Developer reply included with review | Store reply separately; do not classify Google’s reply as user pain | Must |
| Review is only a rating or sticker-like short text | Relevance filter likely `unrelated` or `ambiguous` | Should |
| `hl`/`gl` mix duplicates the same review | Dedupe by Play review id | Must |
| Throttling / CAPTCHA / HTML interstitial instead of RPC JSON | Fail run; do not parse HTML as reviews | Blocker |

**Research caveat**: Undocumented RPC. Methodology must state parsers can break and coverage is not an official census.

---

## 4. Collection — Reddit (Arctic Shift)

| Case | Handling | Sev |
|------|----------|-----|
| Arctic Shift down, slow, or 5xx | Do not switch to a paid Reddit API; freeze Reddit as a documented gap | Must |
| Keyword search without `subreddit` (unsupported / weak) | Always scope to configured subs (`googlephotos` + run-spec list) | Must |
| Post `[deleted]` / `[removed]` / empty selftext | Keep title if present; mark body missing; still attach comments if they exist | Must |
| Comment whose parent post was not fetched | Fetch parent for `thread_context` or mark context incomplete | Must |
| Crosspost / same story in two subs | Dedupe by post id; optional “also seen in” metadata | Should |
| Keyword hit is about Google Photos backup/storage, not retrieval | Let relevance classifier drop from analysis corpus; keep raw | Must |
| `limit=auto` returns huge pages | Cap per request; paginate with `after`/`before` | Should |
| `created_utc` outside configured window | Exclude from analysis; do not silently widen the snapshot | Must |
| NSFW / spam / meme-only thread | Relevance + optional denylist; do not let it dominate clusters | Should |

---

## 5. Collection — Google Photos Help Community

| Case | Handling | Sev |
|------|----------|-----|
| Custom Search daily quota (100) exhausted mid-run | Stop CSE; fall back to public threads listing or resume next day; receipt records both | Must |
| CSE returns Reddit/Play URLs despite `site:` restrict | Discard anything not under `support.google.com/photos/thread` | Blocker |
| Duplicate URLs (http/https, `hl=`, trailing slug) | Canonicalize thread id; one `RawRecord` per thread | Must |
| Thread is “restore deleted photos” / account recovery, not search | Relevance `unrelated`; common on this forum—expect high noise | Must |
| Locked, missing, or 404 thread after discovery | Skip; count as discovery-without-fetch in receipt | Must |
| JS-rendered page; HTTP GET has no post body | Retry with Playwright/Firefox on the **same public URL**; never Community Console | Must |
| Recommended vs relevant vs ordinary replies | Preserve flags; classify question + user replies, not Product Expert boilerplate as user memory | Must |
| Very long thread (dozens of replies) | Chunk by post; keep thread id on every chunk | Must |
| Login wall / consent interstitial | Abort that URL; do not authenticate | Blocker |
| Browse-page crawl is newest-first and recovery-dominated | Document recency and topic bias; do not claim forum-wide frequency | Must |

---

## 6. Cross-source ingest and freeze

| Case | Handling | Sev |
|------|----------|-----|
| One adapter fails, others succeed | Partial snapshot allowed only if receipts show which source is missing; dashboard banner: incomplete source mix | Must |
| Total **relevant** items &lt; 500 | Do not hide the miss; methodology + dashboard show count vs success bar; optional: widen keywords/storefronts in a **new** run, never mutate a freeze | Must |
| Same person / same story on Play and Reddit | Do not merge identities. Optional near-dup clustering for “theme,” not user stitching | Blocker (identity join) |
| Re-run after freeze | New `run_id` / snapshot; never overwrite frozen aggregates in place | Blocker |
| Clock skew / `captured_at` vs `authored_at` | Both stored; filters and trends use `authored_at` when present | Must |
| Raw payload too large for SQLite row | Spill to `data/` file; store path on `RawRecord` | Should |

---

## 7. Normalization and relevance

| Case | Handling | Sev |
|------|----------|-----|
| Encoding / mojibake / emoji-only | Normalize UTF-8; keep emoji; do not drop | Should |
| Mixed language in one item | Classify on full text; `locale` may be storefront not language | Should |
| HTML, markdown, `&nbsp;`, Reddit quotes | Strip to readable text; keep original in raw | Must |
| Keyword “search” about searching *settings* or *people to share with* | Ambiguous → human or second-pass; default exclude from high-confidence counts | Must |
| Backup, sync, storage quota, “missing photos” after device change | Often **not** incomplete-memory retrieval; label as other or unrelated unless text is about finding known items in the library | Must |
| “Can’t find photos” after they were deleted / locked album / partner sharing | Distinct taxonomy nodes—not incomplete memory | Must |
| Ambiguous relevance | `relevance_label = ambiguous`; exclude from headline frequency unless a human accepts it | Must |
| Empty `source_url` | Synthesize from source + native id when possible; else item cannot be cited in RAG | Must |

Problem-statement confusion to watch: **library value degradation** and **deleted/trashed photos** look similar in complaints but are different product problems. Only the former maps to incomplete-memory retrieval.

---

## 8. Domain / taxonomy (problem space)

These are research edge cases from the problem statement, not only engineering bugs.

| Case | Handling | Sev |
|------|----------|-----|
| User had **complete** info (exact date) and search still failed | Taxonomy: query/product failure, not incomplete memory | Must |
| Partial memory matches examples (café + Goa, no date; sibling + holiday; screenshot + “months ago”; medicine + “last year”) | Prefer incomplete-memory nodes; snippet must include the vague cue | Must |
| Multiple problems in one review (sync **and** search) | Multi-label; frequency counts use multi-label rules documented in methodology (item can increment more than one category) | Must |
| Workaround that **worked** (manual browse, years view, partner’s phone) | Workaround category; not counted as unsolved failure only | Must |
| Abandonment after 2–3 tries with no problem type | Label abandonment; do not invent incomplete memory | Must |
| Health / legal / intimate content in public text | Keep for analysis if public; redaction flag for shared exports | Must |
| Hypothesis **contradicted** (users say search is fine; problem is upload) | `hypothesis overlay = contradict`; dashboard must not bury this | Must |
| Category appears in only one source | May exist on dashboard but **cannot** be claimed “consistent across sources” | Must |
| Segment (library size, photo age, geo) not in text | `unknown`; segment charts must show unknown share, not impute 3,000+ libraries | Blocker |
| Model infers “India” from “Goa” in an example-like anecdote | Only tag geo if the **user** states it; do not geo-tag from the problem-statement examples leaking into prompts | Must |

---

## 9. Classification, clustering, scoring

| Case | Handling | Sev |
|------|----------|-----|
| Local LLM returns invalid JSON / extra prose | Retry once; else mark unclassified; do not regex-guess labels | Must |
| Confidence high but rationale empty | Treat as low trust; queue for gold-set / human | Should |
| Tiny cluster (n=1–2) | Do not promote to a new taxonomy root without human review | Must |
| Giant “other” / catch-all cluster | Split or leave unlabeled; do not report as a ranked opportunity | Must |
| Severity driven only by 1-star rants about billing | Scoring must not equal star rating; retrieval-related filter first | Must |
| Public volume ≠ prevalence | Copy on dashboard: ranking is **within this snapshot**, not user-base incidence | Blocker |
| Prompt contains problem-statement examples | Risk of the model parroting Goa/café; gold set should include non-example phrasings | Must |
| Embedding model at query time ≠ index time | Forbidden; freeze model id on `MethodologySnapshot` | Blocker |
| CPU OOM / Ollama not running | Fail analysis stage; do not fall back to a paid API | Must |

---

## 10. RAG search

| Case | Handling | Sev |
|------|----------|-----|
| Empty query / whitespace | No search; UI hint | Must |
| Query **outside Google Photos search/retrieval** (e.g. “how do I train the model?”, “write a Python scraper”, “what is RAG?”, billing, backup-only, general world knowledge) | **Return no hits and no summary.** Show an out-of-scope explanation. Do not vector-search, do not rank low-relevance chunks, do not answer from parametric knowledge | Blocker |
| In-scope retrieval query with zero matching evidence | Empty results with “no matching feedback in this snapshot,” not the out-of-scope message | Must |
| Reviewer **aggregate** query (sentiment, pain points, key themes) | In scope; may answer from dashboard metrics; ≤2 quotes chosen by sentiment/taxonomy fit, not only vector rank | Must |
| UI shows long ranked hit list | Reviewer UX is summary + ≤2 illustrative quotes; not a full search results page | Should |
| Query asks for a **quote that is not in the corpus** | Snippets only from index; synthesis must not fabricate | Blocker |
| Filters exclude every hit (source + date + min_confidence) | Empty state: “0 items match filters,” not a guessed answer | Must |
| Hit snippet truncated mid-sentence, changing meaning | Expand to sentence/item boundary in evidence drawer | Must |
| Rank by cosine only, ignoring impact | Apply documented rerank (relevance × impact); show both scores in drawer | Should |
| Related themes empty | Hide the module; do not invent themes | Must |
| User pastes PII into the search box | Query is local; do not log full query to external services | Must |
| Cited summary lists wrong `item_id` | Blocker if synthesis enabled; prefer extractive snippets as default | Blocker |
| Corpus has 500+ items but k is tiny | k and filters documented; “no results” ≠ “problem does not exist” | Should |

**Scope gate (required before retrieval):** classify the query as in-scope if it is about **Google Photos photo search/retrieval**—finding photos, incomplete memory, metadata/people/date/place search, search abandonment, user workarounds—or **snapshot review** wording (sentiment, pain points, themes) tied to search/photos/feedback. Everything else is out of scope.

Example queries from the problem statement must work even when users use synonyms (“old pictures,” “can’t remember when,” “workaround,” “metadata / date / location wrong”).

---

## 11. Dashboard and How the Engine Works

| Case | Handling | Sev |
|------|----------|-----|
| Zero categories after filter | Empty chart + “filters exclude all items,” not a blank white page | Must |
| Trend chart with one-time snapshot | If shown, only within `authored_at` window; subtitle: not live post-analysis trends | Must |
| High-impact highlight with n&lt;5 or single source | Badge “low support”; do not lead the default view | Must |
| Clicking a metric opens evidence that does not sum to the number | Every count is a query over stored items; mismatch is a bug | Blocker |
| `unknown` segments dominate | Show unknown; do not drop it so bars look like complete geo coverage | Must |
| Source pie with a failed adapter | Slice missing + warning, not 100% split across remaining three | Must |
| Methodology omits CSE quota, RSS cap, or RPC brittleness | Incomplete artifact; those limits are required copy | Must |
| Frozen snapshot served while someone starts a new collect | Read path uses freeze id; writers cannot mutate it | Must |

---

## 12. Privacy, ToS, and exports

| Case | Handling | Sev |
|------|----------|-----|
| Public display name / handle | Optional on `FeedbackItem`; strip on redacted export | Must |
| Request to join handle → Google account | Never | Blocker |
| Export shared outside the research team | Redaction mode (names, URLs still ok if public) | Should |
| Scraping login-gated or Console APIs | Out of architecture; treat as a security incident if attempted | Blocker |
| Health or minors mentioned in a public review | Do not extra-scrape; minimize fields; consider omitting from screenshots | Should |

---

## 13. Serving and artifact

| Case | Handling | Sev |
|------|----------|-----|
| Missing vector index file next to SQLite | RAG tab error with rebuild instruction; dashboard aggregates can still load | Must |
| Stale UI cached against new snapshot | UI shows `run_id` and freeze date in chrome | Should |
| Concurrent local Ollama while collecting | Fine; do not mix embedding models across snapshots | Must |
| Basic auth off and bound to 0.0.0.0 | Default bind localhost; warn in README | Should |

---

## 14. Acceptance checks (minimum)

A snapshot is not “done” if any of these fail:

1. Each of the four sources has a receipt (success, partial, or explicit gap)—never a silent skip.
2. Analysis corpus count and **relevant ≥ 500** (or a visible miss) are on the dashboard.
3. No RAG citation exists without a stored `FeedbackItem` whose text contains the quote.
4. No category is labeled “consistent across sources” unless ≥2 sources contribute.
5. Segment charts include `unknown`.
6. Hypothesis overlay can be `support`, `contradict`, or `insufficient`—not support-only.
7. Freeze is immutable; a second collect creates a new run id.
8. Out-of-scope RAG queries return zero hits plus an out-of-scope explanation, never parametric answers or weak neighbors.

---

**Document version**: 1.1  
**Date**: 21 September 2026  
**Status**: Edge-case contract for implementation and QA
