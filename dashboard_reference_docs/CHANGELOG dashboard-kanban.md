# Changelog

All notable changes to the CRM Kanban dashboard are documented here.

## [Unreleased]

### Phase 8: Tag/Feedback Learning System (2026-07-12)

- **Mail tag add/remove UI in CRM Mail Quick View (Inbox tab).** Users can now add or remove mail tags on selected conversations:
  - `fetchMailTags()` caches available tags from `/api/2.0/mail/tags.json`.
  - `addMailTag()` / `removeMailTag()` call the confirmed bot-proxied CRM tag endpoints.
  - Toolbar "Tags ▾" dropdown shows all tags as checkboxes with partial-state indicators when some selected conversations have the tag.
  - Per-row tag chips include an × button to remove that tag.
- **Bot feedback loop.** Emails flagged by the bot (Bot Review mail tag or ML override) are auto-recorded as feedback candidates in `data/mail_scanner/feedback.jsonl`.
  - Inbox rows with the "Bot Review" tag show "✓ Correct" / "✗ Wrong" buttons.
  - "Wrong" opens a correction selector: actionable / ack_suppress / owner_name_title / note_only / other.
  - `POST /api/scanner/feedback` stores the verdict (requires dashboard auth, no scanner admin token).
  - `GET /api/scanner/feedback` lists entries (with local fallback + remote proxy).
- **Learning pipeline.**
  - `train_ml_head.py` gains `--feedback` and `--mock-and-feedback` modes; `load_feedback_entries()` converts verdicts/corrections into labeled ML samples.
  - `retrain_classifier_head()` in `mail_scanner.py` runs `train_ml_head.py` as a subprocess (avoids blocking the scanner thread).
  - `POST /api/scanner/retrain` endpoint (admin-only) with local fallback + remote proxy.
  - Scanner Admin Status tab shows feedback count, current ML head status, and a "Retrain ML Head" button (gated on ≥1 feedback entry); displays sample count and accuracy after retrain.
- **Guaranteed linking policy.** Scanner now ensures every email is either linked to the best available opportunity (including weak matches) or flagged with a Bot Review mail tag for human routing. Added `_ensure_linked_or_flagged()` wrapper around `_process_email_core()`, explicit `_link_email_to_opportunity()` in `supplement_discussion`, and weak-match linking in record-inbox ack/delay paths. Admin log UI shows "linked email" / "flagged for review" instead of "No action".
- **Rules legend in Scanner Admin Status tab.** Collapsible `<details>` section listing all 15 classification rules with human-readable descriptions, what they match, typical actions, record inbox behavior, and assignees.
- **Inbox differentiation (CRM vs REQ).** Mail rows now show a source channel badge (`CRM` or `REQ`) with actions taken and amber suggested action (e.g., "task needed") for record inbox emails where tasks are suppressed by policy. Filter buttons (`All | CRM | REQ`) in the toolbar to filter by source channel.
- **Feedback on ALL mail rows.** Removed `hasBotReview` gate — every email now shows "✓ Correct" / "✗ Wrong" buttons. Structured correction form with: "What was wrong?" dropdown (wrong classification / wrong deal / should notify customer / both / other), "Correct rule" dropdown (all 15 rules), "Correct deal" type-ahead search (reuses `searchOpportunitiesByTitle()`), and notes field.
- **Enhanced feedback schema.** `store_user_feedback()` accepts `correct_classification`, `correct_opp_id`, `correct_opp_title`. `record_feedback_candidate()` stores `linked_opp_id`, `linked_opp_title`, `source_inbox` for full context.
- **Training pipeline relabeling.** `load_feedback_entries()` uses `correct_classification` (preferred over `user_correction`) to relabel samples when the user specifies the correct rule.
- **Skipped actions in log.** Record inbox policy suppressions shown as `(skipped: task: record inbox policy, ...)` in Scanner Admin log.
- **Files changed:** `mail_scanner.py`, `train_ml_head.py`, `scanner/scanner_service.py`, `server.py`, `public/app.js`, `public/index.html`, `public/styles.css`.

### Phase 6: ML Implementation & Override Logic (2026-07-12)

- **ML classifier fully implemented.** `train_ml_head.py` training pipeline with mock data generator for bootstrapping (300 synthetic emails across 4 categories: actionable/record/ack/uncertain). Interactive labeling mode exports CSV for manual labeling. Trains LogisticRegression head on all-MiniLM-L6-v2 embeddings, saves `classifier_head.pkl`.
- **Full ML override logic.** `_apply_ml_override()` function runs after rule engine on every email. Override rules:
  1. `ml_category == "ack"` AND rule created task → suppress task creation (fixes 39978 false positives)
  2. `ml_category == "record"` AND `dedup_reason == "owner_name_title"` → demote to weak (fixes 961/872/1136 collisions)
  3. `ml_category == "actionable"` AND `ml_actionable_score > 0.7` AND classification == "uncertain" → promote to actionable
  4. `ml_actionable_score < 0.2` AND rule would post note → suppress note (reduce noise)
- **ML_ENABLED env var.** Scanner now reads `ML_ENABLED=true/1/yes` from environment to enable ML. Default is false. No code changes needed to toggle.
- **owner_name_title demotion fixed.** Previously a no-op (`pass`). Now `_dedup_opportunity` accepts `is_record` parameter. When `is_record=True`, owner_name_title matches are demoted to weak (not strong). All 10 call sites updated to pass `is_record=is_record`.
- **requirements-ml.txt created.** `sentence-transformers>=2.2.0`, `scikit-learn>=1.2.0`, `numpy>=1.24.0`, `torch>=2.0.0`. Dockerfile updated with `INSTALL_ML=1` build arg.
- **Training pipeline ready.** Run `python3 train_ml_head.py --generate-mock --samples 300` to bootstrap, or `--label-mode` for manual labeling. Once labeled data exists, train head and save to `data/mail_scanner/ml_models/classifier_head.pkl`.

### Architecture & mail scanner plan (2026-07-11)

- **Phase 5 ML scaffolding.** Lazy sentence-transformers/all-MiniLM-L6-v2 loading (`_init_ml`, `_ml_embed`, `_ml_classify`). `ml_*` fields in every log entry. Classifier head pickle support. `INSTALL_ML=1` build arg in scanner Dockerfile. ML returns None until labeled data + head trained.
- **Phase 6 admin UI polish.** Real reprocess endpoint (`reprocess_conversations` in mail_scanner.py + `/reprocess` in scanner_service.py + proxy in server.py). Log viewer enhanced: source_inbox badge, ml_actionable_score badge, normalized_claim, policy, no_deal indicators. Reprocess button in Scanner Admin Log tab with checkboxes per entry. CSS for flex layout + checkboxes.
- **Phase 7 deploy prep.** Scanner service Dockerfile supports INSTALL_ML, docs updated.
- **Phase 2 hygiene + ack/delay complete; Phase 3 tag mirroring + Phase 4 scanner service scaffold done.** All create_task sites now use `_task_title_with_claim` (claim — base — customer (requester?)). Ack/delay review task follows same pattern. Desc = most-recent sanitized request + deep link. Ack/delay/OOO policy wired early in `_process_email`: carrier/record suppress tasks (link/note on strong only); contractor forwards create "Notify customer of delay" review task.
- **Dashboard CRM Mail Quick View (Inbox tab) now unconditionally uses bot credentials.** Every call under `/api/2.0/mail*` (conversations list, messages, accounts, mark, move, link, tag, etc. — GET and mutations) from the dashboard is routed through `_bot_crm_proxy` with `BOT_CRM_EMAIL` / `BOT_CRM_PASSWORD`. All users see the exact same two inboxes + bot mail tags (e.g. "Bot Review"). Personal inboxes are excluded from this modal. (Server enforcement in GET and POST/PUT handlers.)
- **Mail tag mirroring in quick view.** `getMailTags(m)` tolerant reader. `.mail-tags` column + `.mail-tag-chip` (Bot Review highlighted) in `renderMailList`; CSS for chips + header.
- **Scanner service scaffold.** `scanner/scanner_service.py` (status/config/log/reprocess), `scanner/Dockerfile`, `scanner/docker-compose.scanner.example.yml`. Dashboard forwards `/api/scanner/*` to `SCANNER_SERVICE_URL` (with token passthrough) and falls back to local thread.
- **Logging hygiene.** Every log entry gets `normalized_claim` (auto-filled via `_norm_claim` on append); `source_inbox` + `toggles` already present; `log_entry["claim_code"]` set at all sites.
- **Hygiene fix.** Stray indentation in "claim_code_only" block corrected.
- (Prior items retained for context; see earlier changelog for two-droplet, bot inbox, granular toggles, record policy, etc.)

### New features (prior scanner work, still relevant)

- **Tasks tile category filter.** New pill-button row (All, Estimate, Follow-Up, etc.) below the user filter in the tasks tile. Clicking a tab filters `state.tasks` by `categoryId`. Tabs are rebuilt from `state.taskCategories` on each render. CSS styles for `.tasks-cat-filter` and `.tasks-cat-btn` with active/hover states.

- **Scanner admin inside CRM Mail Quick View.** Existing mail modal now has "Inbox" / "Scanner Admin" tabs. Admin tab includes Status (config display), Log viewer (with refresh/limit), editable Assignee Rules (checkboxes per classification type, saved to `contractors.json` via PUT), and Contractors list (read-only). New server endpoint `GET /api/scanner/log?limit=N`.
- **Configurable assignee rules.** Scanner no longer has hardcoded user UUIDs for task/notify assignments. All 12 classification rules read from `assignee_rules` in `contractors.json`, resolving friendly names (ken/rebeca/claudiu) to UUIDs from env vars. Editable via Scanner Admin tab in the mail modal.

### Files changed
- `mail_scanner.py` (new), `server.py`, `public/app.js`, `public/styles.css`, `public/index.html`, `.env`, `config.example.env`, `CHANGELOG.md`, `AGENTS.md`, `docs/MAIL_SCANNER_PLAN.md`

### Scanner hardening (this session)
- Timestamp + content dedup gate: `_poll_inbox` now stores `sigs` alongside IDs; skips re-processing when `receivedDate`/`chainDate` + (claim|from|coarse-date|body-hash) matches a prior forward/resent. ID-only was insufficient for resends.
- +1 day ET deadline on all tasks (was +7). Uses America/New_York when zoneinfo available.
- JN task descriptions now cleaned: strips "-------- Forwarded Message", Subject/From/Date headers, "Automation (Contact) via JobNimbus", and raw send/receive blocks. Appends `Mail: /addons/mail/...#conversation/{id}` deep link.
- Explicit "no deal" logging: `no_deal:true` + `no_deal_reason` set for carrier/uncertain/weak/Accln/other paths (no strong match). Visible in admin log and tmp_force_reprocess.py.
- Preview expand for scanner-linked mail: `fetchMailMessage` now falls back to `/api/2.0/mail/conversation/{id}.json?loadAll=false` and extracts first message when `/messages/{id}` 404s (common when scanner stores convId).
- Delete × now allowed on mail-linked history items (scanner links) in opp preview, not just plain notes.
- Updated docs/AGENTS/CHANGELOG + tmp_force_reprocess verification print.

### Mail scanner policy & two-inbox model (this session)
- **Critical context added**: Two distinct inboxes with different policies.
  - crm@vanguardadj.online (record/BCC inbox): only CC/BCC correspondence. Contractor sending addresses (estimates@baneyconstruction.online, aplus.estimates@..., etc.) appear here for outbound mail. Policy = **link to deal only**. No tasks, no notes (or minimal record notes), no Bot Review tasks.
  - requests@sherwoodestimates.com (action inbox): all real work (Acculynx, JobNimbus, forwarded carrier responses with asks, supplements, etc.). Full classification + actions allowed.
- Early mailbox detection required in classifier. Outbound BCC records from contractor "sending domains" must never create tasks.
- Reformulated inference fixes needed after live run: wrong strong matches via owner_name_title + claim code (e.g. 872 vs 1136), ack/receipt mail misclassified as "adjuster wants", raw subject used as task title, outbound mail from estimates@baney... treated as inbound.
- Dry-run now defaults to all-false in contractors.json + server startup (with auto-create of the key). _is_dry_run() + early return in _poll_inbox + guards on link/tag/mark/note/task/mail-tag.
- Behavior tab + /api/scanner/config remain for live toggles; record-inbox link-only is a hard policy.
- Added plan for lightweight inference: sentence-transformers/all-MiniLM-L6-v2 + logistic regression/kNN (or small head). ~90MB model, <500MB RAM, sub-100ms, trains in seconds on CPU. To be used as a feature for "actionable vs ack vs record" and tie-breaking, not sole decider. Fits easily on the CRM droplet (8GB).
- Strong_custom_field_ids updated to [26,11,12,4,2] + phone [2] (Customer Phone) from live CRM definitions.
- Mail tagging now uses the exact captured payload: PUT /api/2.0/mail/conversations/tag/{tagId}/set.json?__={ms} with body messages[]=... (plus fallbacks + verbose logging).
- Docs updated: MAIL_SCANNER_PLAN.md now leads with the two-inbox section and includes the ML classifier track. AGENTS.md + CHANGELOG updated. Branch kept separate ("email_scanner").

### Prior scanner items (still relevant)
- No more "Review carrier email" tasks for carrier/insurance mail.
- Reconciliation literal first.
- Bot Review mail tag for ambiguous/unlinked (in action inbox only).
- Note safety + truncation.
- Scanner identity UI (restart required).

## [2.2.1] — 2026-07-08

### Bug fixes

- **Server-side tag cache now properly invalidated on per-opp tag mutations.** The cache invalidation condition in `_handle_api_post_put` checked `"/crm/opportunity/tag" in p`, which matches GET paths like `/opportunity/tag/123` but **not** mutation paths like `/opportunity/123/tag`. Added `re.search(r"/crm/opportunity/\d+/tag", p)` so POST/DELETE tag operations correctly invalidate the 10-minute proxy cache. Previously, after adding/removing tags, the preview modal and tile enrichment could serve stale cached tag data for up to 10 minutes.

- **Client-side tag cache bypass on edit and nuke refresh.** Three fixes ensure fresh tags are always fetched after mutations:
  - `enrichOpportunitiesTags` now respects `force=true`: skips the client-side tag cache and always fetches from the server batch endpoint.
  - `submitDealEditForm` and `submitQuickNoteForm` pass `force=true` to `enrichOpportunitiesTags` after saving tag changes.
  - Individual tag fallback requests (when batch endpoint fails) now send `X-Force-Refresh: 1` header when `force=true`, bypassing the server proxy cache.
  - `refreshGroup` clears the entire tag cache on manual Nuke Cache (`_manualGroupTileRefresh`), so all opportunities in the group get fresh tags.

### Improvements

- **Nuke Cache icon and label.** Reverted to original Tabler radioactive (trefoil) icon. Tooltip/aria-label updated to `"Nuke Cache (refresh tile)"`.

### Files changed
- `public/app.js`, `server.py`, `VERSION`, `CHANGELOG.md`, `AGENTS.md`

## [2.2.0] — 2026-07-07

### Bug fixes

- **`/tag` now correctly lists and filters by tag.** Rewrote `_handle_bot_tags` to extract tags from open deals (the CRM-wide tag definitions endpoint doesn't exist). Fixed tag filter in `_handle_bot_deals`: the per-opportunity tag endpoint returns plain strings, not dicts — now handles both formats. Tag selection now correctly finds matching deals.
- **Usage Log now loads.** Fixed routing bug: `GET /api/bot/usage` was defined in `_handle_api_post_put` (unreachable for GET requests). Moved to `_handle_api_get` at the correct routing position.

### Improvements

- **Broadcast message format.** Server-side now prepends `<b>-System Message-</b>\n\n` and appends `\n\n<i>Please do not reply to this message.</i>` to all broadcast messages.
- **HTML sanitization for broadcast.** Added `_TelegramHTMLSanitizer` (same logic as `telegram_bot.py`) to strip non-Telegram-safe HTML tags from broadcast input before sending. Only `<b>`, `<strong>`, `<i>`, `<em>`, `<u>`, `<ins>`, `<s>`, `<strike>`, `<del>`, `<a href="...">`, `<code>`, `<pre>` are allowed.
- **Bold / Italics toolbar in broadcast UI.** Replaced raw HTML hint text with a toolbar of B / I buttons that wrap selected text or insert empty tag pairs at cursor position.

### Files changed
- `server.py`, `public/app.js`, `public/index.html`, `public/styles.css`, `VERSION`, `README.md`, `CHANGELOG.md`, `AGENTS.md`

## [2.1.0] — 2026-07-07

### Telegram bot — inline keyboards, employee note creation, role-aware onboarding

- **Inline keyboard navigation.** Project search results now render as tappable buttons instead of numbered lists (old number-reply fallback preserved). Deal detail screen has "New Search" and "Add Note" (employee) buttons.
- **Employee note creation.** From any deal detail, employee can tap "Add Note" → type text → choose curated category from inline keyboard (Quick Context, Note, Text, Call, Email, Customer Update). Note is posted via dashboard proxy (`POST /api/bot/note`). Category picker uses regex matching with priority ordering; no "Default" button.
- **Role-aware `/start`.** Linked employees see commands + welcome; linked customers see search prompt; unlinked users see invite code prompt.
- **Role-aware `/help`.** Three variants: customer (basic search), employee (commands + notes), unlinked (invite code instructions).
- **`/projects` command (employee only).** Lists all open projects with inline keyboard.
- **`act:note:` uses `reply_text`.** "Add Note" prompt sends a new reply message instead of editing the deal detail, keeping the deal info visible for reference.
- **Fixed `allowed_updates` bug.** Used plural `"messages"` (silently ignored by Telegram — adding any valid type activated the filter and dropped messages). Fixed to `Update.MESSAGE` / `Update.CALLBACK_QUERY` constants.

### Files changed
- `telegram_bot.py`, `server.py`, `AGENTS.md`, `CHANGELOG.md`, `VERSION`

## [2.0.10] — 2026-07-06

### Hotfix — Group tile "Nuke Cache" (universal)

- Per-group tile refresh button ("Refresh deals") is now **universal cache-buster** for all users/browsers. Clicking it forces a live CRM `/filter` call:
  - Browser: `fetch(..., { cache: "reload" })`
  - Dashboard proxy: skips `_proxy_cache` lookup + store via `X-Force-Refresh` header
  - Response includes `Cache-Control: no-cache, no-store, must-revalidate` + `X-Proxy-Cache: BYPASS-FORCE`
- Button label changed to **"Nuke Cache"** (title/aria-label too). Icon is muted Tabler radioactive (trefoil) symbol. Only the group tile refresh button is affected (no impact on header refresh, feed/tasks/calendar tiles, post-edit refreshes, search, etc.).
- Customer Update history notes now use Tabler `eye-check` icon (instead of speech bubble).
- README.md: permanent toaster header added at the very top: "THIS APP WAS CREATED BY A TOASTER. LOOK ON IT YE MIGHTY AND DESPAIR".
- Version: 2.0.10

### Files changed
- `public/app.js`, `server.py`, `VERSION`, `CHANGELOG.md`, `README.md`

## [2.0.9] — 2026-07-05

### Fixed
- **Backdate controls in deal-edit and quick-note.** Plain native `<input type="date" id="*-note-created" class="note-backdate-input">` placed directly after the note editor (no wrapper, icon, or label). Width tuned (max 138px) so full mm/dd/yyyy is visible. Submission already passed `created` to history events.
- **Quick Context items.** Tabler thumbtack (pin) icon + faint blue background (`rgba(37,99,235,0.08)`) matching High Priority tag style.

### Files changed
- `public/index.html`, `public/app.js`, `public/styles.css`, `CHANGELOG.md`, `VERSION`, `AGENTS.md`, `docs/RELEASE_v2.0.9.md`

### Removed / Scrapped
- **WebKit / Apple-friendly cache-busting attempt (July 4).** Full attempt to add `detectAppleWebKit()`, `state.isAppleWebKit`, `bustCache()` helper, and guarded calls on short-TTL paths (filter/history/tag/customfield) plus premature `Cache-Control`/`Pragma`/`Vary`/`Expires` headers before `send_response` in `server.py:_handle_api_get` on cache miss. This produced `net::ERR_INVALID_HTTP_RESPONSE` (400) on direct http LAN testing (127.0.0.1 + local IPs) for history/filter/batch-tags/individual tag calls after login succeeded. User reported multiple times that "local dev used to work great until the edits"; initial diagnosis wrongly focused on auth/reachability. Entire feature scrapped; all `detectAppleWebKit`/`isAppleWebKit`/`bustCache`/`isDynamicShortTtl` + header-before-response blocks removed. Pre-existing server TTL cache (30s filter, 600s tags/stages), `_proxy_cache` invalidations, `newId()` UUID fallbacks, 502/5xx resilience, friendly tile retry links, LAN IP printing, batch-opportunity-tags, and all prior proxy/auth/upload logic preserved. Documented as expensive disaster and waste of tokens with ignored user feedback.

## [2.0.8] — 2026-07-03

### Infrastructure / Upload fix (post-sherwood-toolbox)
- **Host nginx is now the permanent front-end for `dashboard.publicadjustermidwest.com`.** After the sherwood-toolbox deployment, public traffic no longer goes through the Docker `estimate-nginx` container. The active config is `/etc/nginx/sites-enabled/dashboard.publicadjustermidwest.com`.
- **Restored PDF/image attachments in edit/quick-note/side modals.** Added the three required directives to the host site file (matching sherwood-toolbox convention on the host):
  - `client_max_body_size 100m;`
  - `proxy_request_buffering off;`
  - `proxy_read_timeout 120s;`
- These live inside the https server block before `location /`. Without them, `UploadProgress.ashx` multipart uploads failed with 413 "client intended to send too large body".
- All documentation, deploy scripts, and references updated to reflect the new permanent architecture (host nginx directly to `127.0.0.1:8765`). Old `estimate-nginx`/`/opt/estimate-enhancer/nginx.conf` paths are now explicitly marked historical for the dashboard domain.
- `docker-compose.yml` network declaration left unchanged (harmless, keeps future options open).
- Backups of the host site file, full `nginx -T`, container state, certs, and user data volume were taken before the edit.

### Files changed
- Host nginx site file (server), `docs/DASHBOARD_INFRASTRUCTURE.md`, `docs/PRODUCTION_SERVER_NOTES.txt`, `docs/UPDATE_AND_DEPLOY.txt`, `docs/DEPLOY_v1.1_VERIFY_STEPS.md`, `AGENTS.md`, `docs/MIGRATE_DOMAINS.md`, `docs/CUTOVER_RUNBOOK.md`, `romanian_roadtrip.md`, `FUTURE_FEATURES.md`, `CHANGELOG.md`, deploy/ historical script headers (`nginx-dashboard.conf`, `nginx-dashboard-estimate-nginx.snippet`, `dashboard-add-new-domain.sh`, `dashboard-add-new-domain-v2.py`).

## [2.0.7] — 2026-06-30

### Fixed
- **Preview modal: pasted email content now renders for Email-category notes.** Email-category history events were always collapsed to the generic "An email has been received." summary, even when a user pasted real content into the note. The summary is now shown only for genuine linked emails (messageId present / mail payload) or the CRM placeholder text; otherwise the actual content renders normally.
- **Presence/Team tile: no more UUID display names.** When a CRM user record lacks `displayName` and `userName`, the server now falls back through `email`, `firstName`+`lastName` before using the raw user id. The Team tile also uses the same robust label helper as the modal roster.

### Files changed
- `public/app.js`, `server.py`, `VERSION`, `CHANGELOG.md`, `AGENTS.md`, `docs/RELEASE_v2.0.7.md`

## [2.0.6] — 2026-06-29

### Fixed
- **Preview modal: highlighted `<b>` text now readable.** The CRM note editor uses `<b style="background-color: rgb(200, 230, 201);">` for highlighted text. The CSS override now targets `b`/`span`/`mark` elements with `background-color` or `background` inline styles across all preview history body variants (main preview, bookmark preview, search popup), using a darker `rgba(34, 197, 94, 0.65)` background and black text so highlighted content is legible on the dark modal background.
- **Customer Bot modal: deleting one mapping no longer removes multiple mappings.** Delete buttons now use the mapping's unique `chatId`, and the server removes by `chatId` via `remove_mapping_by_chat()`. This fixes the bug where multiple employee mappings (or mappings sharing a `contactId`) were all deleted when removing one.
- **Preview modal: delete button restored for Customer Update and Text/SMS events.** The × button now appears for history categories matching `customer update`, `text message`, `text`, and `sms` (in addition to existing note/comment/activity/meeting/call/task categories). The underlying `DELETE /api/2.0/crm/history/{id}` endpoint already supports these events.
- **Customer Bot: customer mode latest update no longer shows author.** The "Latest customer update" header in non-employee mode now omits the employee name, matching the decision to hide authors from Customer Update events.

### Files changed
- `public/styles.css`, `public/app.js`, `server.py`, `telegram_bot.py`, `VERSION`, `CHANGELOG.md`, `AGENTS.md`, `docs/RELEASE_v2.0.6.md`

## [2.0.5] — 2026-06-29

### Added
- **Customer Bot (employee mode): show event author.** Non-mail history events now display the creator's display name next to the date, e.g. `[Note] — Jun 28, 2026 (Ken Chapman)`. Author is intentionally hidden for `Customer Update` events so customers never see employee names.
- **Customer Bot (employee mode): full mail body fetch.** The dashboard proxy fetches the complete email body from the CRM `filehandler.ashx?action=mailmessage&message_id={id}` endpoint and injects it into employee history events, replacing the truncated CRM history content.

### Changed
- **Customer Bot (employee mode): mail body cap and truncation marker.** Long email bodies are capped at 1200 characters and end with `[truncated]` so users know the full message continues in CRM.
- **Customer Bot: distinct footer.** The closing prompt now has a separator line and is italicized so it doesn't blend into email/note content.
- **Customer Bot: customer update author hidden.** `Customer Update` events no longer show the author name.

### Fixed
- **Customer Bot (employee mode): HTML parse errors from email addresses.** Forward/reply attribution lines like `Grasshopper <notifications@grasshopper.com>` are now HTML-escaped so Telegram doesn't treat the email address as an unsupported tag.
- **Customer Bot: plain-text fallback stripped tags.** If Telegram rejects the HTML message, the fallback now strips HTML tags instead of sending literal `<b>`/`<i>` text to the user.
- **Customer Bot: HTML-safe message truncation.** When a deal detail exceeds Telegram's length limit, truncation now closes open HTML tags and removes partial tags so the message stays valid HTML.
- **Customer Bot (employee mode): tight email formatting.** Raw CRM email HTML is converted to plain text with normalized whitespace so forwarded emails no longer have leading spaces or words broken across lines.
- **Customer Bot (employee mode): forwarded-header parsing.** The bot correctly extracts `From`/`Date` from forwarded email headers and no longer swallows the first paragraph of the body.

### Files changed
- `server.py`, `telegram_bot.py`, `VERSION`, `CHANGELOG.md`, `AGENTS.md`, `ISSUES.md`, `docs/RELEASE_v2.0.5.md`

## [2.0.4] — 2026-06-28

### Added
- **Customer Bot: employee access mode.** Admins can now generate invite codes for employees by checking "Employee access (view all deals)" in the Customer Bot modal. Employees see all open deals across the CRM (no contact filter) and up to 5 recent events per deal, each labeled with its history category.
- **Customer Bot: employee mapping support in backend.** `crm_bot_store.py` persists an `employee` flag on codes and mappings. `server.py` `/api/bot/deals` accepts `employee=true` and returns an `events` array with `categoryName`. Invite code generation, cancellation, unlinking, and nickname changes all support employee mappings.
- **Customer Bot: employee rendering in Telegram bot.** `telegram_bot.py` passes the employee flag through search/selection flows and renders deal detail with `[Category]` labels for employees.
- **Customer Bot: employee UI affordances.** Modal title switches to "Invite Employee", contact picker is hidden, and existing mappings show an "Employee" badge.

### Fixed
- **Customer Bot: number replies no longer re-fetch deals.** The bot now caches the last search results per chat (`_last_deals`) and interprets "1", "2", ... replies from the cache instead of calling the CRM API again.
- **Customer Bot: history API uses correct sort column.** Changed `/api/2.0/crm/history/filter` from `sortBy=date` to `sortBy=created` to match the native CRM field and return the most recent events reliably.
- **Customer Bot: reduced history API timeout.** History calls now use a 10s timeout (down from 30s) so a slow/hanging history endpoint fails fast and does not block the entire response.
- **Customer Bot: CRM HTML sanitized for Telegram.** Added `_sanitize_html()` in `telegram_bot.py` to decode HTML entities, replace `<br>` with actual newlines, strip unsupported tags, balance Telegram-safe tags, and escape bare `&` characters inside tag attributes. This fixes "Something went wrong" crashes on deals with complex note content.

### Files changed
- `crm_bot_store.py`, `server.py`, `telegram_bot.py`, `public/app.js`, `public/index.html`, `public/styles.css`, `VERSION`, `CHANGELOG.md`, `AGENTS.md`

## [2.0.3] — 2026-06-27

### Added
- **Customer Bot: search by project title.** Linked customers now type a project name (or part of it). The bot searches open deals by title: 0 matches → not found; 1 match → full detail; 2+ matches → numbered list, reply with a number for detail. Added `?search=` parameter to `/api/bot/deals` (server-side filtering on already-fetched contact deals).
- **Customer Bot: `/help` command and help trigger words.** Customers can send `/help`, "help", or "?" for instructions.

### Changed
- **Customer Bot modal renamed.** User-visible title and button label changed from "Bot Customers" to "Customer Bot".
- **Customer Bot welcome message simplified.** After linking, customers are told to send a project name instead of receiving a full list.

### Fixed
- **Mobile: bot button actually moves below sign-out.** Previous CSS override was overridden by the desktop `.bot-customers-btn` rule due to source order. Moved mobile header-button overrides to after the desktop rule so the bot button sits at `right: 1rem` (directly under sign-out) and event-log at `right: 3.75rem`.

### Files changed
- `telegram_bot.py`, `server.py`, `public/app.js`, `public/index.html`, `public/styles.css`, `VERSION`, `CHANGELOG.md`, `AGENTS.md`, `docs/RELEASE_v2.0.3.md`

## [2.0.2] — 2026-06-27

### Fixed
- **Presence: stale autoStatus also stripped in Team tile.** The v2.0.1 cleanup only ran in the modal roster; the embedded dashboard tile (`renderPresenceTileCompact`) now clears `autoStatus`/`status`/`inferred` for offline users too.

### Files changed
- `public/app.js`, `VERSION`, `CHANGELOG.md`, `AGENTS.md`, `docs/RELEASE_v2.0.2.md`

## [2.0.1] — 2026-06-27

### Added
- **Nickname field for bot customer mappings.** New text input in the "Invite Customer" form to label each code (e.g. "Office manager"). Nickname shown in the Existing Mappings list with a ✎ edit button (inline prompt). New server endpoint `PUT /api/bot-customers/nickname`. Stored in `crm_bot_store.py` mapping entries and preserved through the verify-code flow. (`FEAT-025`)
- **Rich text (HTML) in bot messages.** All Telegram bot `reply_text` calls now use `parse_mode="HTML"`. CRM note content with `<b>`, `<i>`, etc. renders as formatted text. Plain-text fields (titles, stage names) are HTML-escaped to prevent breakage.
- **Crash banner: 15s grace period after tab resume.** Suppresses the amber banner for 15s when the tab becomes visible, preventing false positives from stale-connection failures due to browser throttle during background.

### Changed
- **Bot project summary cleaned up.** Latest customer note and amount removed from the summary list (only title + status shown). Full details including note and amount still visible in the detail view when customer replies with a number.

### Fixed
- `.gitignore` updated to exclude `romanian_roadtrip.md`.
- **Mobile: bot & event-log buttons no longer overlap header.** Stacked below sign-out on a second row (`@media max-width: 640px`).
- **Mobile: opportunity preview modal fills screen.** Overrode `96vw` width to `100%` inside the modal container to prevent right-side cutoff.
- **Presence: stale autoStatus no longer leaks for offline users.** After merging cache + snapshot, `autoStatus`/`status`/`inferred` are cleared for any entry not currently `online`. Prevents "Reviewing: … · last seen 23h ago" text.
- **Presence: team roster no longer goes blank on poll failure.** `fetchPresenceSnapshot()` catch no longer wipes `state.presenceData` — keeps last good snapshot so the tile/modal stays populated. Amber banner still shown.

### Files changed
- `public/app.js`, `public/styles.css`, `VERSION`, `CHANGELOG.md`, `AGENTS.md`, `docs/RELEASE_v2.0.1.md`

## [2.0.0] — 2026-06-26

### Added
- **Telegram customer bot (`@vanguardupdates_bot`).** New async Python bot (`telegram_bot.py`) using `python-telegram-bot` v22.8. Customers send their invite code to get linked; then they can view open projects and reply with a number for full details.
- **Invite-code-based customer linking.** Admin generates an 8-char code in the dashboard modal, tells the customer, customer types it to the bot. Codes expire after 48 hours. Persisted via `crm_bot_store.py`.
- **Bot Customers admin modal.** Robot SVG trigger button in the header (right: 9.5rem, next to event-log). Searchable contact picker (CRM contact search), note category dropdown for history curation, code generation with Copy + expiry countdown + Cancel, existing mappings list with Linked/Pending badges and × unlink.
- **7 new server endpoints** for bot customer management, code verification, deal queries, and admin check. Bot CRM session managed via dedicated `bot@vanguardadj.com` account (token cached 50 min).
- **Admin detection from CRM `isAdmin` field.** `/api/2.0/people/@self` response checked; falls back to `kenc@vanguardadj.com` email match. Presence admin gating uses `state.currentUserIsAdmin`.
- **Bookmarked deals limit** increased from 15 to 20.

### Changed
- **Customer-facing bot text** uses "projects" instead of "deals".
- **Bot button** moved from `right: 10.5rem` to `right: 9.5rem` for consistent header spacing.
- `.env` and `config.example.env` updated with `TELEGRAM_BOT_TOKEN`, `BOT_CRM_EMAIL`, `BOT_CRM_PASSWORD`.

### Files changed
- `telegram_bot.py` (new), `crm_bot_store.py` (new)
- `server.py`, `public/index.html`, `public/app.js`, `public/styles.css`
- `VERSION`, `CHANGELOG.md`, `AGENTS.md`, `README.md`, `config.example.env`
- `docs/RELEASE_v2.0.0.md`, `docs/GITHUB_RELEASES.md`

## [1.91.3] — 2026-06-26

### Added
- **Editable deal title in deal-edit modal.** Title input added at the top of the form (discreet, transparent background, no border, accent underline on focus). Validates non-empty on save. All entry points covered (card edit button, preview modal, search preview, bookmark sidebar).
- **CRM iframe proxy investigation:** Added `/crm-proxy/` test route to `server.py`. Confirmed `X-Frame-Options` can be stripped, allowing the native CRM to be embedded in an iframe. Documented findings and the recommended subdomain proxy approach in `FUTURE_FEATURES.md` (FEAT-024). Not implemented — parked.

### Fixed
- **Event note line breaks preserved.** Browser contenteditable `<div>` wrapping (Chrome wraps each paragraph in `<div>`) is now normalized to `<br/>` tags before sending to the CRM. Multi-line notes no longer arrive as a single text blob. Fix applies to both deal-edit and quick-note modals (both go through `noteContentToHtml`).
- **Create opportunity modal — tags moved after custom fields.** Tags selector was moved below the dynamic custom fields section (Inspection Photos checkbox area) and before the Private checkbox, matching the requested form order.

### Files changed
- `public/app.js`, `public/index.html`, `public/styles.css`, `server.py`, `VERSION`, `CHANGELOG.md`, `AGENTS.md`, `FUTURE_FEATURES.md`

## [1.91.2] — 2026-06-25

### Fixed
- Dashboard no longer hangs for ~10 seconds after deal edit from bookmark preview / quick note. Removed redundant `refreshAll()` call from `submitDealEditForm` post-edit chain (which re-fetched every API, cleared all caches, and rebuilt all group tile DOM). Now runs preview, board, and bookmark tab refreshes **in parallel** via `Promise.all()` instead of sequentially via `.then()` chaining.
- Post-edit preview refresh now caps history pagination at 2 pages (100 items, down from 10 pages / 500). Full history is still loaded on initial preview open; only the auto-refresh after edit/note uses the fast path.
- Quick-note post-save chain also parallelized for consistency.

### Files changed
- `public/app.js`, `VERSION`, `CHANGELOG.md`, `AGENTS.md`

## [1.91.1] — 2026-06-25

### Fixed
- Event log no longer clears on hard refresh: `loadEventLogFromStorage()` is now called during `init()` so the localStorage backup is applied before the server merge runs.
- GUID validation error ("Guid should contain 32 digits with 4 dashes") when posting an event note with attachments AND notify users: `notifyUserList` is now sent as individual form-urlencoded parameters (`notifyUserList=guid1&notifyUserList=guid2`) instead of a JSON-stringified array, matching ASP.NET MVC's `List<Guid>` model binder convention.
- `validNotifyUserList` now filters with `isGuid()` instead of `filter(Boolean)`, rejecting non-GUID values before they reach the OnlyOffice API (JSON path).
- `validFileIds` now validates numeric format (`/^\d+$/`), rejecting non-numeric file IDs before sending to the upload endpoint.

### Files changed
- `public/app.js`, `VERSION`, `CHANGELOG.md`, `AGENTS.md`

## [1.91.0] — 2026-06-24

### Added
- Server-side event log persistence (`event_log_store.py`): 7-day rolling retention with 1,000-entry cap, per-user per-portal JSON files.
- Admin event-log tab: visible only for kenc@vanguardadj.com; shows user dropdown populated from CRM display names, filtered to users with event logs.
- Discrete CRM health check: `GET /api/health` endpoint; "Check CRM status" button in event log modal (no polling).
- GUID validation on history event creation: `notifyUserList` and attachment `fileIds` are validated client-side with `isGuid()` before sending to OnlyOffice; invalid entries are dropped with a console warning.
- Upload response validation: file IDs returned from the upload handler are checked for valid GUID format.

### Fixed
- Quick Note and Deal Edit modals no longer auto-close after 2.5s on failure; the modal stays open so the user can retry or copy their work.

### Files changed
- `event_log_store.py` (new), `server.py`, `public/app.js`, `public/index.html`, `public/styles.css`, `Dockerfile`, `test-server.py`, `VERSION`, `CHANGELOG.md`, `AGENTS.md`

## [1.90.1] — 2026-06-24

### Fixed
- `server.py` `do_POST` no longer crashes with `AttributeError: 'super' object has no attribute 'do_POST'` on non-API POST requests; now returns HTTP 405.
- Expanded linked emails in deal preview modal and bookmark preview once again fill the full available modal width. The `.opp-preview-mail-embed` panel is now appended directly to `.opp-preview-history-item` instead of inside the flex row shared with attachments.
- DM messages now show a discreet timestamp below each message bubble.
- Team tile popup button (⤢) now uses event delegation so it opens on the first click even after tile re-renders.
- Emoji picker no longer detaches when scrolling: it is fixed to the viewport and repositions on scroll/resize so it stays pinned to the emoji button.
- Mobile emoji picker now opens below the emoji button instead of being anchored to the bottom edge of the screen.

### Changed
- Toast, CRM sync status, and note queue indicators are now stacked vertically in a shared container. By default the stack is on the bottom-right; when a bookmark preview is open it moves to the bottom-left so indicators do not overlap the preview panel.

### Files changed
- `public/app.js`, `public/index.html`, `public/styles.css`, `VERSION`, `CHANGELOG.md`

## [1.90.0] — 2026-06-23

### Domain migration to publicadjustermidwest.com + notification cache rollback

- **Domain migration docs:** Added `docs/MIGRATE_DOMAINS.md` with full cutover guide for CRM droplet (DigitalOcean one-click Docker setup) and dashboard droplet (`estimate-nginx` reverse proxy).
- **Cutover runbook:** Added `docs/CUTOVER_RUNBOOK.md` as a one-page checklist; dashboard side runs first to minimize downtime.
- **Domain fallback updates:** Updated default portal URL fallbacks in `config.example.env`, `server.py`, and `public/app.js` to `https://office.publicadjustermidwest.com`.
- **Production context:** Updated `AGENTS.md` production dashboard URL to `https://dashboard.publicadjustermidwest.com`.
- **Notification cache rollback:** Reverted v1.88.0 server-side CRM mail-based notification cache and the two follow-up mail-parser fixes. Feed returns to using CRM history events directly. `notification_store.py` removed.
- **Files changed:** `AGENTS.md`, `CHANGELOG.md`, `VERSION`, `config.example.env`, `docs/CUTOVER_RUNBOOK.md`, `docs/MIGRATE_DOMAINS.md`, `public/app.js`, `server.py`

## [1.87.6] — 2026-06-23

### Chunked card rendering + initial-load responsiveness

- **Chunked card rendering:** `renderGroupBoard` now renders cards in batches of 20 with `setTimeout(0)` between batches, yielding the main thread so the event loop can service clicks (e.g. changelog modal close button) during initial load. Column shells (headers + empty bodies) are appended to the DOM immediately so the kanban layout is visible before cards populate progressively. Previously, all cards in a group were created in one synchronous loop — with 3 groups × 500 deals this blocked the main thread for seconds, triggering the browser's "page unresponsive" warning.
- **Changelog delay increased:** `maybeShowChangelog` delay raised from 300ms to 1500ms so the modal appears after the worst of the tile rendering is underway, not competing for main thread time during the initial render burst.
- **Files changed:** `public/app.js`, `public/index.html`, `VERSION`, `CHANGELOG.md`

## [1.87.5] — 2026-06-23

### Presence hardening — smart heartbeat + beforeunload + auto-status write-back + stale cleanup

- **Smart heartbeat (visible flag):** Heartbeats now include a `visible` flag — `send()` sends `{visible: true}` when the tab is focused, `sendBeacon()` sends `{visible: false}` on background tab / beforeunload. Server only bumps `lastDashboardActivity` when `visible=True`, so auto-status expires naturally after 5 min of background-tab inactivity instead of staying alive indefinitely.
- **Beforeunload handler:** Tab/window close now sends `navigator.sendBeacon` with `{offline: true}` so the server marks the user offline immediately instead of 10+ min later. Cleaned up in `stopPresenceHeartbeats`.
- **Auto-status write-back:** When the server filters out a stale `autoStatus` (>5 min) from the response, it now also writes the cleared value to disk via `clear_auto_status()`. Prevents stale values from persisting across sessions when the client's 5-min timeout never fires (browser closed unexpectedly).
- **Stale record cleanup:** `clean_stale_presence_records()` iterates all presence files and clears `lastHeartbeat` + `autoStatus` for records with heartbeats >3h old. Called on each presence GET. Handles edge cases from closed browsers that never sent beforeunload.
- **High Priority amber styling on bookmark sidebar tabs:** `.bookmark-tab--high-priority` CSS class with same amber treatment as card tiles — `rgba(240,180,41,0.08)` background, `var(--warn)` border, 3px amber left accent. `renderBookmarkTabs()` detects High Priority tag via `oppHasTag()`, checking deal `_cachedData` then falling back to group opportunities.
- **Files changed:** `presence_store.py`, `public/app.js`, `public/styles.css`, `server.py`, `VERSION`, `CHANGELOG.md`

## [1.87.4] — 2026-06-23

### Event log + indicator stacking + deal-edit optimization + refreshing spinner

- **Event log:** New header button (clipboard-list icon) opens a persistent event log modal showing all recent deal edits, note saves, attachment uploads, and deletes with timestamps. Persisted in localStorage (max 200 entries). Includes clear-all button.
- **Indicator overlap fix:** `#toast` (z-index 2003), `#note-queue-list` (z-index 2002), and `.crm-sync-status` (z-index 2001) now stack vertically without overlapping — sync-status moved to `bottom: 3.5rem` (above toast at 1.5rem), note-queue at `bottom: 5.5rem` (left side). When bookmark sidebar or a modal blocks the right side, toast and sync-status shift to the left; note-queue stays left always. CSS `.bookmark-open` rules handle the sidebar case; JS `repositionRightIndicator()` handles modals.
- **Optimized deal-edit submission:** Replaced 3 separate GET+PUT cycles (due date, stage, custom fields) with a single `updateOpportunityBulk()` call. Attachment uploads now run in parallel (`Promise.all`) instead of sequential. Dynamic close timer: base 2.5s + 0.5s per MB of attachments (prevents premature modal close during large uploads). Tag operations throttled to 150ms between sequential calls.
- **Refreshing indicator:** After deal-edit or quick-note save, the status bar now shows a persistent "Refreshing CRM data..." spinner during deferred board/preview refresh work (instead of going silent). Spinner hides when all deferred operations complete. Sequential promise chains prevent main-thread contention.
- **Improved attachment upload response parsing:** Multiple extraction strategies (raw JSON, HTML-wrapped extraction, field fallbacks) with more robust error messages.
- **Server timeout:** `urllib.request.urlopen` timeout increased to 120s for large file uploads.
- **Files changed:** `public/app.js`, `public/index.html`, `public/styles.css`, `server.py`, `VERSION`, `CHANGELOG.md`

## [1.87.3] — 2026-06-19

### Hotfix: CRM-down resilience + inbox shows all conversations + tag-column/stale-column fixes

- **CRM-down resilience — presence user ID cache:** `_fetch_crm_user_id` called the CRM on every request — when CRM goes down, `_require_auth` fails for all presence endpoints, killing team view and messaging entirely. Added `_crm_user_id_cache` dict (token → user_id) so the first call caches the result; subsequent requests bypass CRM. Logout clears the cache entry.
- **CRM-down resilience — overlay-only users in snapshot:** When the CRM people API is unreachable, the presence snapshot now includes users with heartbeat records in the local store (with `displayName: uid` fallback), so the team view shows active users even without CRM data.
- **Inbox shows all conversations:** `get_recent_dms_for_user` previously returned the 50 most-recent messages globally — a single thread with 50+ messages after "Load earlier" would crowd out every other conversation. Rewritten to return the **latest message per conversation partner**, ensuring each distinct person appears at most once in the inbox regardless of thread depth.
- **DM back button + tab switching:** Back button now renders inbox instantly from cached snapshot then background-refreshes. Messages tab hides the DM thread and clears `presenceSelectedUserId` before rendering inbox, fixing overlap/empty-state issues.
- **Stale tag columns:** `groupOpportunities` auto-detect path filters out tags not in `state.allTags` before creating columns; opps with only stale tags fall to "Untagged".
- **Null-guard in `updateAllCardCopies`:** Added `if (!boardEl) return;` guard to prevent crash when the group tile DOM is not present during targeted card update.
- **Files changed:** `presence_store.py`, `public/app.js`, `server.py`, `VERSION`, `CHANGELOG.md`

## [1.87.2] — 2026-06-18

### Hotfix: Mobile emoji picker + auto-status server expiration + bookmark backdrop + batch tag search + search result enhancements

- **Emoji picker on mobile:** `showPopupEmojiPicker()` and `showInlineEmojiPicker()` now detect narrow viewports (< 480px) and position the picker full-width below the message input area (left+right anchored), so it opens to the left and doesn't block the textarea or get cut off.
- **Auto-status server-side expiration:** Server now strips `autoStatus` from presence responses when the user is not online or `lastDashboardActivity` is older than 5 minutes (client-side timeout may not have fired if the browser was closed). Added `PRESENCE_AUTO_STATUS_TIMEOUT_S = 300` constant. Same check applied to the caller's own `me` record.
- **Bookmark sidebar preview backdrop:** New `.bookmark-preview-backdrop` overlay (rgba black 55%, z-index 1499) shown when a bookmark preview tab is active, matching the dimming behavior of other modals.
- **Batch tag fetching:** New server endpoint `GET /api/batch-opportunity-tags?ids=1,2,3` fetches tags for multiple opportunities in parallel server-side (`ThreadPoolExecutor`). Client's `enrichOpportunitiesTags()` now calls this batch endpoint first, falling back to individual requests if it fails. This eliminates the N+1 bottleneck in tag search.
- **Search result bookmark ribbon:** Each search result row now has a bookmark toggle button (bookmark ribbon SVG) to the left of the "+ Tab" button. `refreshAllBookmarkButtonStates()` updates these buttons alongside existing bookmark buttons.
- **Search result CSV export:** "📋 Export CSV" button at the bottom of search results downloads a CSV with columns: Deal Title, Stage, Due Date, Contact, Bid Value. UTF-8 BOM included for Excel compatibility.
- **Files changed:** `public/app.js`, `public/index.html`, `public/styles.css`, `server.py`, `VERSION`, `CHANGELOG.md`

## [1.87.1] — 2026-06-17

### Hotfix: Cross-user cache contamination + date timezone shift

- **Root cause — proxy cache key missing user identity:** `_cache_key` in `server.py` used only `method:api_path:query:portal`, so one user's CRM filter results were served to other users within the 30-second TTL. This caused users to see wrong deal counts, stale due dates, and other users' personalized data. Fix: added session token to cache key so each user's data is segregated.
- **Date-only parsing for expectedCloseDate:** `new Date(raw)` on the CRM's timezone-qualified ISO string caused a one-day date shift in negative UTC offset timezones. Added `parseCrmDateOnly()` helper that extracts `YYYY-MM-DD` and builds a Date at local midnight. Applied in 6 consumers: `isRedOpportunity`, `formatOppDueLabel`, `dueDateToInputValue`, `formatPreviewDueDate`, `oppDueDateMs`, and bookmark tab due label. No changes to datetime fields (notes, feed, calendars, tasks).
- **Force refresh after mutations:** Changed 4 mutation fallback calls from `refreshGroup(group)` to `refreshGroup(group, { force: true })` so the client-side 30-second cache is bypassed after edits/deletes, ensuring the group UI immediately reflects the change.
- **Files changed:** `server.py`, `public/app.js`, `VERSION`, `CHANGELOG.md`

## [1.87] — 2026-06-17

### Presence auto-status fixes & enhancements
- **Root cause — auto-status not displaying:** `updateInferredStatus` was changed to send `{ autoStatus: text }` only, but the server and rendering expected `{ status, autoStatus, inferred }`. This broke both new-server rendering (no auto-status shown) and old-server compatibility (empty string rejected as 400).
- **Fix — dual-compat payload:** `updateInferredStatus` now sends `{ status: text, autoStatus: text, inferred: true }` — the server stores both fields, new server renders auto-status on the right, old server reads `status` directly. The tile "Online" option value was changed from `""` to `"Online"` so old server accepts it. `syncTileStatusSelect` uses strict `inferred === true` and falls through gracefully for old server (undefined).
- **DND / manual status preservation:** `confirmCustomStatus` for a manual set now sends `{ status, inferred: false, autoStatus: "" }` and sets `state._suppressAutoStatus = true` to block auto-status overwrites. Clearing to "Online" sends `{ status: "Online" }` (no autoStatus) and re-enables auto-status. Auto-status never overwrites a manually-set DND.
- **AFK auto-clear race condition:** `noteDashboardActivity` fires on every mousedown. When it detected AFK and sent `{ status: "Online", autoStatus: "" }`, it could race with `updateInferredStatus` and wipe out the auto-status. Fix: AFK clear now sends `{ status: "Online" }` **without** `autoStatus` so the server preserves whatever `updateInferredStatus` set. Added `_afkClearSent` debounce to only send once per AFK cycle.
- **Auto-status timeout:** New `PRESENCE_AUTO_STATUS_TIMEOUT_MS = 300000` (5 min). When `updateInferredStatus` sets a preview/edit/note auto-status, a timeout is scheduled. If no new activity fires within 5 minutes, the auto-status is cleared (sends `{ autoStatus: "" }`) so it doesn't look like the user is still reviewing the same deal.
- **Bookmark & search preview auto-status:** `updateInferredStatus("preview", title)` now fires when opening a deal from the bookmark sidebar (`activateBookmarkTab`) and when opening/switching search popup preview tabs (`openSearchPreviewTab`).
- **Presence rendering adaptive:** Tile and popup rendering detect `serverHasInferred` per row. New server shows manual `(DND)` in bold next to name, auto-status on the right. Old server falls back to showing all non-"Online" statuses on the right.
- **`set_status` preserves autoStatus:** Server-side `presence_store.set_status` now only writes `autoStatus` when explicitly provided (`autoStatus is not None`), never clobbering it with `None`/default.
- **`_suppressAutoStatus` guard:** New state flag blocks `updateInferredStatus` when a manual status (DND, AFK) is active. Reset on AFK clear or manual clear to "Online".
- **Popup status picker compatibility:** Uses same payload patterns as the tile (`{ status: "Online" }` for clear, `{ status, inferred: false, autoStatus: "" }` for manual). Added `_suppressAutoStatus` integration.
- **Error toast removal:** All `showToast` calls removed from presence fetch error handlers — failures are silent.
- **Files changed:** `public/app.js`, `public/styles.css`, `server.py`, `presence_store.py`, `VERSION`, `CHANGELOG.md`, `AGENTS.md`

### Bookmark tab card styling
- Added `border: 1px solid var(--border)`, `border-radius: 6px`, stronger `box-shadow`, and increased `margin-bottom` to 4px on `.bookmark-tab` so each bookmark card stands out as its own card.
- **Files changed:** `public/styles.css`

### Preview collapse chevron
- Added a right-facing chevron button (matching the bookmark sidebar toggle) to the left of the deal title in the bookmark preview header. Clicking it calls `closeBookmarkPreview()` — same behavior as clicking the active deal name tab.
- **Files changed:** `public/index.html`, `public/app.js`

## [1.85] — 2026-06-16

### Bookmark sidebar — collapsible right sidebar with bookmarked deal previews
- **Feature:** Vertical bookmark trigger tab on right edge (one-letter-per-row "Bookmarks" text). Click opens a sidebar with deal tabs.
- **Bookmark button:** Ribbon icon on every deal card (bottom-right) and search popup preview headers. Filled = bookmarked, outline = not. Click toggles state.
- **Sidebar:** 220px strip with vertical deal tabs showing stage dot, title, stage name, due date. Filled ribbon icon on each tab removes bookmark. Drag-and-drop reordering of tabs. Max 15 bookmarks.
- **Preview panel:** 880px deal detail preview (standard fields, user fields, description, history, documents) using same renderer as modal preview. Refresh button, edit button (opens edit modal to the left), filled ribbon to remove bookmark.
- **Persistence:** Bookmarks survive logout/login via localStorage + server user profile.
- **Edit button:** Opens the deal edit modal positioned to the left of the sidebar preview so both are visible simultaneously.
- **Tab shadows:** Subtle box-shadow + margin on each tab for visual distinction.
- **Sidebar toggle:** Chevron-right arrow (not filled ribbon). Preview panel expands left of the strip.
- **Files changed:** `public/index.html`, `public/app.js`, `public/styles.css`, `VERSION`, `CHANGELOG.md`, `AGENTS.md`

## [1.8.2] — 2026-06-15

### Search popup — large modal with tabbed deal preview
- **Feature:** New search button in the header (magnifying glass icon, `btn-secondary`, left of the existing search field). Opens a large modal with a search bar and results list.
- **Search:** Searches all open deals (`stageType=0`) via `/api/2.0/crm/opportunity/filter?filterValue=...`. Results are enriched with tags. Search triggers on Enter key press.
- **Results list:** Compact single-line rows showing: deal title (bold), stage · due date · contact · bid value. Inline buttons: "Preview" (opens a tab) and "Open in CRM" (new tab).
- **Preview tabs:** Max 5 tabs. Each tab shows the full deal preview (standard fields, user fields, description, history & notes, documents) using the exact same rendering as the existing preview modal. Each tab has a deal title and a × close button.
- **Search tab:** Always present, styled with a left accent border and search icon. Clicking it returns to the search results.
- **Edit button:** Inside each preview tab, top-right. Opens the deal edit modal pinned to the left (same behavior as the existing preview modal).
- **Refactoring:** `renderOpportunityPreviewBody()` now delegates to `renderOpportunityPreviewContent(container, data)` — the same rendering logic works in both the old modal and the new popup tabs.

### Bug fixes
- **Tab content shrinking on switch:** `activateSearchPopupTab()` used a broad selector `[data-tab-content]` that accidentally matched the inner Details/Documents tabs inside the preview body. Switching outer tabs hid both inner tabs, making the preview appear empty/shrunken. Fix: selector narrowed to `.search-popup-tab-content` only.
- **Missing search input on modal open:** Child combinator `>` in the selector fix prevented matching the search tab content (nested inside `.modal-card-search-popup`). Fix: changed to descendant selector `.search-popup-tab-content`.
- **Height instability:** `#search-popup-preview-containers` and the search tab content both had `flex: 1` as siblings, splitting the modal space 50/50. When search tab was active, the empty preview containers ate half the height. Fix: `activateSearchPopupTab` now hides the preview containers when search tab is active.
- **No width scroll on tab bar:** Tab bar uses `overflow-x: hidden` with `flex-shrink: 1` on tabs and `text-overflow: ellipsis` on tab titles.
- **Centered error for max 5 tabs:** Error message now renders as a centered banner in the search results area instead of a background toast.

- **Files changed:** `public/index.html`, `public/app.js`, `public/styles.css`, `VERSION`, `CHANGELOG.md`, `AGENTS.md`

## [1.8.1] — 2026-06-14

### Deal caching — refresh now pulls fresh data
- **Root cause:** `refreshAll()` cleared in-memory caches then immediately rehydrated from IndexedDB before the clear transaction committed, repopulating stale data. Also, server-side proxy cache (30s TTL for single-opp, 600s for tags) returned stale data after tag/note edits.
- **Fix:** `refreshAll()` no longer rehydrates from IndexedDB — hydration only happens once on initial page load via `initCaches()`. `enableCachePersistence()` is now idempotent (guards against double-wrapping). Server-side cache invalidation now covers `DELETE` mutations and invalidates the single-opp `GET:/api/2.0/crm/opportunity/{id}` cache line when tags change. The preview modal refresh button (`⟳`) now appends `?_t=Date.now()` to bypass the proxy cache entirely.
- **Files changed:** `public/app.js`, `server.py`

### Email width — expanded emails now fill available space
- **Root cause:** `.mail-detail` and `.opp-preview-mail-embed` had no explicit `width: 100%`, and the mail inbox modal was using `.mail-expanded-embed` (a class with no CSS rules) instead of `.opp-preview-mail-embed`.
- **Fix:** Added `width: 100%; box-sizing: border-box` to `.mail-detail`, `.opp-preview-mail-embed`, and `.opp-preview-mail-body`. Changed the mail inbox JS to use `.opp-preview-mail-embed` class.
- **Files changed:** `public/styles.css`, `public/app.js`

### UI freeze when returning from background tab
- **Root cause:** When a tab is backgrounded, Chrome throttles timers and defers IntersectionObserver callbacks. Returning to the tab fires all deferred callbacks simultaneously, triggering up to 25+ concurrent `fetchOpportunityCustomFields()` calls (5 per group × 5+ groups).
- **Fix:** Added a 50ms debounced batch collector for intersection callbacks. Added `document.visibilitychange` listener that disconnects all observers when hidden and re-observes after a 500ms delay when returning. `enqueueOpportunityCustomFieldEnrich()` skips work entirely when `document.visibilityState === 'hidden'`.
- **Files changed:** `public/app.js`
- **Issue:** ISSUE-004 — resolved

### Attachment note indicator — queue status now visible
- **Root cause:** `createOpportunityHistoryEvent()` returned `{ queued: true }` on transient CRM errors but callers didn't check the return value, so notes appeared "sent" even when they were only queued for retry.
- **Fix:** `createOpportunityHistoryEvent()` now explicitly returns `{ queued: true }` or `{ success: true }`. `submitDealEditForm()` and `submitQuickNoteForm()` check the return value and show a toast: "Note queued for retry (CRM is temporarily down). Check the header indicator." The note queue indicator in the header was also made more visible (amber background, larger font).
- **Files changed:** `public/app.js`, `public/styles.css`

### Quote font — easier to read at small size
- **Root cause:** The daily quote used "Instrument Serif" (decorative italic serif) at 0.8rem, which was tight and hard to read.
- **Fix:** Changed to `var(--font)` (DM Sans / system-ui sans-serif), increased to 0.85rem, added `font-weight: 500`, increased line-height to 1.45. Reverted to italic style per user request.
- **Files changed:** `public/styles.css`

### Preview modal stale data — manual refresh bypasses cache
- **Root cause:** The preview modal refresh button (`⟳`) re-fetched the same API paths, which were cached by the server-side proxy for 30 seconds (opportunity data, history) or 600 seconds (tags, custom fields).
- **Fix:** Added `bustCache(path)` helper that appends `?_t=Date.now()`. The preview modal refresh button now passes `force=true` through the entire chain: `openOpportunityPreviewModal(…, true)` → `fetchOpportunityPreviewData(…, true)` → each individual fetch function. This guarantees fresh data on manual refresh.
- **Files changed:** `public/app.js`

### Amber border lost after deal edit
- **Root cause:** `fetchOpportunityForUpdate()` returns the core opportunity object but does **not** include tags. The single-opp refresh path in `submitDealEditForm()` and `submitQuickNoteForm()` updated the card with the untagged opportunity, so `renderCard()` couldn't detect "High Priority" and the amber border/background disappeared.
- **Fix:** Added `await enrichOpportunitiesTags([updatedOpp])` immediately after `fetchOpportunityForUpdate()` in both submit paths. This fetches tags for the updated opportunity before rendering the card, preserving the amber styling.
- **Files changed:** `public/app.js`

### Changelog popup — shown once per version on first login
- **New feature:** Modal that displays `CHANGELOG.md` content on first login after a version update. Uses the existing `renderBasicMarkdown()` renderer (headers, lists, bold, italic, links, code). Close button + Escape + backdrop click dismiss the modal. The seen version is persisted in `localStorage` under `changelog_seen_version`, so the modal only reappears when the version changes.
- **Files changed:** `public/index.html`, `public/app.js`, `public/styles.css`, `server.py`
- **Server endpoint:** `GET /api/changelog` returns `CHANGELOG.md` as `text/markdown`

---

## [1.8.0] — 2026-06-12

### Stale Deals Tile — Attempted, debugged, and scrapped
- **Attempt A (activity-based)**: Tried to use `state.feedRawItems` (CRM notifications feed) to find last activity per opportunity. Failed because feed only covers last 30 days (max 150 events), so most opportunities had no activity found.
- **Attempt B (due-date-based)**: Switched to `expectedCloseDate` on opportunity objects. Added threshold dropdown (1 week / 30 days / 90+ days). Still failed to list any deals in any time period during testing.
- **Scrapped**: Tile removed from UI and code entirely. All stale deals functions, constants, CSS, and HTML removed from `public/app.js`, `public/index.html`, `public/styles.css`.
- **Root cause**: `expectedCloseDate` on open deals was not reliably past-due in the test data. The concept of "stale" needs a different data source (e.g., actual last-modified timestamp on opportunities, which the CRM API does not provide directly).
- **Future**: May revisit with a proper CRM-side query or different staleness metric. See ISSUES.md for full post-mortem.

### Fix: Production version display showing "vdev"
- **Root cause**: `Dockerfile` did not copy the `VERSION` file into the container. `server.py` fell back to `APP_VERSION = "dev"`, so the UI showed `vdev`.
- **Fix**: Added `COPY VERSION ./` to `Dockerfile`.
- **Verify**: On next Docker build, `GET /api/config` should return `"version": "1.8.0"`.

## [1.7.6] — 2026-06-12

### Feed: notify auto-inject experiment (tried and reverted)
- Attempted Part A: auto-inject `[Notified: Name1, Name2]` text into event content when creating history events with notify users, so the keyword filter could find them.
- Added `renderFeedNotificationItem` detection of `[Notified: ...]` suffix with `.feed-notified-suffix` CSS (smaller/italic/muted).
- **Reverted**: User reported text was "squished against the note" and same font size. Feature scrapped — manual `@ken` keyword filter works fine.

### Feed: mail events removed
- Removed `fetchFeedMailInitial` call, mail batch branch in `loadMoreNotificationFeed`, and `mailExhausted` from `feedCanLoadMore`. Mail events (CRM. New event added to...) no longer appear in the feed.

### FEED_MAX_EVENTS: 200→150→100→150
- Settled at 150 (mail removal already reduces noise sufficiently).

### UI: Preview modal fields styled as cards
- Each `.opp-preview-field` now has `border`, `border-radius: 8px`, `box-shadow`, and `background: var(--surface-2)` — like edit modal fields.
- Checkbox values ("Yes"/"No") render as small pill `.field-value-tag`.
- Success probability field removed from preview.

### UI: Tasks rendered as cards (not rows)
- `.task-row` now has `border-radius: 8px`, `border: 1px solid var(--border)`, `box-shadow`, and `margin-bottom` instead of `border-bottom`.
- Full-width layout toggle button removed from tasks tile and CRM notifications tile toolbars.

### Server: gzip + caching
- Static files served with `Cache-Control: public, max-age=86400`.
- Gzip compression for all responses (`Content-Encoding: gzip`; app.js 553KB→134KB, 75% reduction).
- Proxy-side response cache: 60s TTL for tag/stage/customfield, 15s for filter/history.

### Other
- `modal-card-deal-edit .modal-form` now has `scroll-padding-bottom: 4rem` so content doesn't hide behind sticky action bar.

## [1.7.5] — 2026-06-11

### Performance: tag cache, custom field cache, filter result cache
- **Tag cache** (`state.oppTagCache`, 5-min TTL): checked in `enrichOpportunitiesTags` before per-opp `tag/{oppId}` API calls; stored on fetch success; cleared on `refreshAll`; invalidated per-opp after tag mutations in `submitDealEditForm`, `submitQuickNoteForm`, and mutation queue handler.
- **Custom field cache** (`state.oppCustomFieldCache`, 5-min TTL): checked in `enqueueOpportunityCustomFieldEnrich` (cached → immediate `updateOpportunityCardDom`, no queue); stored in `fetchOpportunityCustomFields`; cleared on `refreshAll`; invalidated per-opp after `updateOpportunityCustomFieldsViaPut`.
- **Filter result cache** (`state.filterResultCache`, 30-sec TTL): caches raw API response from `/api/2.0/crm/opportunity/filter` before client-side filtering. Keyed by `groupId + baseQs` only (tagTitles/red filters excluded since they're client-side). Moved store *before* client-side filtering so adding/removing tag filters still hits the same cache entry.
- New helpers: `createTtlCache(ttl)` for filter result cache, `createOppCache(ttl)` for opp-specific caches.
- Cache invalidation in mutation handlers, deal edit, quick note.

### UX: tile loading indicator (200ms debounce)
- `refreshGroup` shows "Refreshing deals…" with spinner in tile board area after 200ms debounce; cleared on both success and error paths.

### DM linkify
- New `linkifyUrls(container)` function (TreeWalker pattern) converts bare `https?://` URLs to `<a>` tags inside `.presence-msg-text`; called at end of `renderDMLog`.

### Feed cap reduction
- `FEED_MAX_EVENTS` 200→150, `FEED_DAYS` 90→30 to reduce feed API payload on every refresh.

### Performance: batch tag enrichment
- **Replaced serial 12-at-a-time per-opportunity tag fetches with fully concurrent `Promise.allSettled`.** Previously, `enrichOpportunitiesTags` batched 12 concurrent requests in a `for` loop with `await`, creating N/12 serial rounds of network waterfall (e.g., ~13 rounds for 150 opps). Now all per-opportunity tag requests fire concurrently — the browser manages its 6-per-domain connection pool naturally, and the function returns once all responses settle. Eliminates the serial blocking gap between batches and reduces wall-clock time for tag resolution by ~10x (from 13+ round-trips to 1 effective round-trip).
- No change to `state.allTags` loading (tag definitions are still fetched in one batch via `loadAllTags()`).

### UX: CRM loading indicator
- **Bottom progress bar** now shows "Loading CRM data…" during `refreshAll` and stays visible until ALL CRM tile data (groups, feed, tasks) finishes loading in the background. The dashboard renders immediately; the indicator tracks completion via a promise callback, not by blocking.
- Calendar tiles (3rd‑party Proton Calendar) fire independently and don't affect the indicator.
- **Refresh button spins** while CRM data is loading (CSS animation on the SVG icon), stops when background CRM loads complete.
- `loadExpandedDashboardTiles` separates CRM-origin tiles from calendar tiles; only CRM promises are tracked for the indicator. The function always returns a promise for completion observation without blocking.
- `isCrmOnlyTileId` helper distinguishes CRM-origin tiles (groups, feed, tasks) from non-CRM tiles (calendar).
- `hideCRMSyncStatus` respects `_crmRefreshing` flag: mutation status messages can briefly override the text, but `hideCRMSyncStatus` restores "Loading CRM data…" when a global refresh is in progress.

### Mail inbox fixes and enhancements
- Restored pagination: added `&page=` param back to conversations API (server supports it).
- Added "Mark all loaded as read" toolbar button for bulk marking.
- Restored account selector pulldown: unhidden, functional change listener, filters by `&accountId=`.
- Restored unread badge on mail header button: removed `style="display:none"` and early return guard.
- Link debug: added `console.warn` for primary link failure + `console.warn` for fallback failure so root cause is visible in DevTools.
- Updated link toast to "Linked as note (primary link failed)" when falling back.
- Cache-Control: all static files now served with `no-cache, must-revalidate` (not just favicons).
- Updated button title from "CRM Mail Inbox (viewer only)" to "CRM Mail Inbox".
- Added `console.debug` of conversation object keys on load to diagnose missing read flag fields.

### Mail quick view UX polish
- Made close button larger (removed `btn-small`, added explicit padding/font-size).
- Moved limitations note from footer to right sidebar as a bullet list under "Quick View Limitations".
- Attachments now pre-render "Open in Mail" link immediately when expanding an email (no download attempt cascade).
- Added today counter `N (Today)` in toolbar showing how many of the loaded conversations are from today.
- Search now passes `&search=` param to conversation API so it actually filters server-side.
- Query param `search` added to `loadMailMessagesForModal`.
- Attachment filenames are plain text (no click handler) to avoid noisy 404/403 console errors; only "Open in Mail" link is actionable.

### Bug fixes
- Feed notifications: filtered out raw JSON/mail-metadata dumps (`{from "...", ...}`) that appeared as broken text in the feed.
- Quick edit modal: sticky save/cancel buttons at bottom of card; note editor max-height reduced to 6rem with resize disabled, preventing buttons from being pushed off-screen on smaller screens.
- Deal preview: hid "Actual close" field per request.

### User fields in deal edit
- Added "Show User Fields" toggle button to deal edit modal that reveals editable custom user fields (reuses create-opp field rendering).
- Fields are pre-populated with the deal's current saved values; text, textarea, select, checkbox, and date types supported.
- Changes are submitted via `updateOpportunityCustomFieldsViaPut` on save.
- User fields container has `max-height: 30vh` with internal scroll so it doesn't push save/cancel buttons off-screen.

### Dashboard performance: CRM tile isolation
- CRM-dependent tile loads (groups, feed, tasks, calendars) are now fired as background promises — they no longer block `refreshAll()` or the initial dashboard render.
- `loadExpandedDashboardTiles` no longer `await`s CRM tile data; tiles update asynchronously when their data arrives.
- `refreshGroup` defers DOM rendering via `setTimeout` so deal edits and other mutations don't freeze the UI during group board re-render.
- Status text updates immediately instead of waiting for all CRM tiles to finish.
- Local-only features (notes, calendars from cache, profile, layout) are fully isolated from CRM server latency.

### Other
- Created `docs/DEPLOY.md` with correct production path `/opt/vanguard/onlyoffice-crm-kanban`.
- Updated reference in `UPDATE_AND_DEPLOY.txt` to point to `docs/DEPLOY.md`.

## [1.7.0] — 2026-06-11

### FEAT-002: Custom user fields on opportunity create (ISSUE-001 — FIXED)
- Custom fields on new opportunity create now actually persist in CRM. Root cause: `collectCreateOppCustomFieldValues()` used `[data-custom-field-id]` which matched the wrapper `<div>` (set by `renderCreateOppCustomFields`) instead of the actual `<input>`/`<select>`/`<textarea>`, so `.value` was always `undefined` and every field was silently skipped.
- Fix: finds the wrapper div by data attribute, then queries `input, select, textarea` inside it to get the real user-entered value.
- Also corrected `buildCustomFieldListForApi` to `{key, value}` format (camelCase, no duplicate `Key`/`Value` props) and added `customFieldList` to create body alongside per-field POST fallback.
- `CREATE_OPP_USER_FIELDS_ENABLED=true`. Tested and confirmed end-to-end (dashboard → proxy → CRM).

## [1.6.1] — 2026-06-11

### FEAT-003: Attachments on event notes
- Full support for attaching files (≤25 MB each) when creating event notes from Deal Edit and Quick Note (including side-by-side from preview and prefill from notes tile).
- Native CRM upload flow: client uploads via proxied UploadProgress.ashx (multipart, using current UserID), then history create uses form-urlencoded with repeated `fileId[]`.
- Text is always priority (note sent even if some/all uploads fail; per-fail error toast).
- Pre-submit selected files: plain filename (size) list with × remove (no icons).
- Right-side status list in header (near mutation-sync-status): shows pending + all completed note actions; success = checkmark, fail = ✕; completed items auto-clear after exactly 10 seconds.
- Reuses existing preview attachment rendering, queue resilience (history items), rich note editor, and currentUserId.
- Server proxy updated to correctly forward form-urlencoded (for history) and multipart (for uploads) so attachments work through the deployed dashboard (extra hop).
- Hotfix for production uploads: added `X-OnlyOffice-Portal` header to the direct `UploadProgress.ashx` fetch (was missing, causing attachments to fail on the droplet proxy while local and text notes succeeded). Confirmed working after nginx client_max_body_size + proxy buffering config.

### Additional fixes
- Mobile vertical stacking of deal preview + deal/quick-note editor: improved dynamic measurement, ResizeObserver, and constraints in `layoutSideBySideDealEditAndPreview` to prevent overlap at top when stacked.
- Hanging after deal edits and event notes (prod): deferred the preview re-open in `submitDealEditForm` (was immediate heavy fetch+render); board refreshes already deferred. (Does not happen on local test server.)
- Added version number (v1.6.1) next to "Sign out" button (in header meta, to the right of portal URL, properly spaced).
- Rolled back "show empty stages" checkbox visibility for tag-sorted groups (the change had broken group tiles rendering); now only shown for stage groupBy as before.

See AGENTS.md for implementation details. These (plus proxy support for attachments on server) are released as v1.6.1.

## [1.6.0] — 2026-06-10

### Post-1.4.5 bug fixes (cross-device reliability + no-UI-hang resilience)
- DM "of the day" inbox now correctly shows read/unread cross-device: `renderPresenceInbox` isUnread logic changed to only flag when *latest* message in thread is incoming (from other) and ts > lastReadDms; self-sent responses no longer make threads appear unread on other devices. Added `markPresenceDMRead` immediately after successful DM send.
- Eliminated random UI hangs / "nothing clickable" / browser "page not responding" after quick notes and other pushes: post-submit refreshes (preview + refreshGroup/refreshAll) now always deferred via setTimeout (non-blocking); same for queue processor's refreshAll on stage/due/tag mutations. History notes already skipped from full refresh.
- Status and DM read state (lastReadDms) persistence reinforced across devices and page refreshes/logins (server already persisted in per-user presence json; client now always syncs on snapshot + explicit mark on send/open; no resets except on explicit logout clearing hb).
- Mobile quick-edit from preview no longer overlaps: `layoutSideBySideDealEditAndPreview` now dynamically measures actual side card bottom + 4px gap and repositions preview top (and max-height) on mobile so borders almost touch cleanly (no hard 260px offset).

### Additional fixes
- Quick note prefill from notes tile now correctly renders as rich formatted HTML (markdown converted via `renderBasicMarkdown` into the contenteditable) + explicit clear of the editor on open. (Previously plain text/markdown would appear unformatted.)

See AGENTS.md last-session summary for details. These changes (plus the earlier proxy response handling) are now released as v1.6.0.

## [1.4.5] — 2026-06-09

### Side-by-side preview note editor (quick note / edit from preview)
- Edit note button (or quick note in preview context) now opens as a separate "side popup" to the left of the preview modal on desktop (or fixed to the top of the preview on mobile <700px width).
- Both preview (history/details) and the note editor (rich B/I/U/H formatting, tags, due, notify) remain fully interactive simultaneously (pointer-events:none on side modal container + auto on card; fixed positioning + z; preview backdrop provides dim).
- Auto-refreshes preview on successful note submit (quick note or deal-edit note) so new history event appears immediately.
- Escape in preview closes side editor first (keeps preview open).
- Added manual refresh button (⟳) in preview head (left of ✎ edit) to force re-fetch current opp preview (useful after side note or external changes).
- Delete × button now available on event note history items inside preview (only for note-category non-mail events; uses confirmDialog + DELETE /api/2.0/crm/history/{id}; re-opens preview to refresh list).

### Presence / Team: AFD (away from dashboard) status + accuracy
- "Online" = tab visible + recent heartbeat (<10m).
- "Away from dashboard" (AFD): tab backgrounded but still has active session (stale hb record, not cleared by logout; subtle slate-gray dot + "Away from dashboard (N)" section in roster).
- "Offline": signed out (manual or auto 3h) — server clears lastHeartbeat on /api/logout so immediately offline (or aged >3h).
- Auto-logout aligned to 3h (was 4h); timer + visibility listeners.
- "Last CRM (proxy):" confirmed only from real proxied /crm/ or /people/ calls (touch_crm_activity), not heartbeats.
- Roster splits Online / Away from dashboard / Offline; compact tile respects AFD dots.

### Feed / notifications: today indicator
- All notifications from the current day (local date match on it.date) now get a subtle white left border line (`.feed-item-today` + border-left: 3px solid rgba(255,255,255,0.25); adjusted padding) in the CRM notifications feed.

### Crash / 5xx resilience (CRM unreachable banner)
- On 502/5xx (or transient proxy/CRM down errors) from api() or presence: shows persistent amber crash banner on right side of header meta ("CRM is temporarily unreachable and may have crashed. Refresh again in 30 seconds or contact system administrator.").
- Banner is subtle amber (#f59e0b bg, dark #1f2937 text for readability in dark/light), non-dismissible except by successful CRM response (onCRMSuccess hides) or page reload.
- No raw error toasts for transients during crash; status stays usable.
- All tiles still render (board, feed, tasks, etc.); CRM-pulling tiles/sections show no content (empty state from failed loads) while non-CRM parts (local notes, layout) continue.
- Quick note / side edit from preview still works (local), and preview auto-refreshes on submit even during partial outage.
- 30s guidance in message; throttle via existing transient queue logic.

### Documentation & Housekeeping
- Version bumped to 1.4.5 everywhere (VERSION, AGENTS.md, README, CHANGELOG, new RELEASE_v1.4.5.md, docs/GITHUB_RELEASES.md, docs/UPDATE_AND_DEPLOY.txt, docs/DEPLOY_*.md).
- Added detailed release notes + updated AGENTS.md "Post-v1.2 shipped items" with the new UX (side preview editor + delete + refresh, AFD presence, today lines, crash banner + partial render).
- Session changes from crash sim, side note flow, delete, feed today, presence AFD all documented.
- Local server close + prod deploy checklist followed (see below).

See also [docs/RELEASE_v1.4.5.md](./docs/RELEASE_v1.4.5.md) for the full GitHub release text.

## [1.4.1] — 2026-06-08

Patch release to ensure reliable deployments after v1.4.0.

### Deployment / Docker fix
- Updated Dockerfile to explicitly `COPY presence_store.py` (along with the other .py modules). The v1.4.0 tag's Dockerfile was missing it, causing `server.py` to fail on `from presence_store import ...` at container startup. This resulted in the dashboard container crash-looping (Restarting (1)) and nginx returning 502 Bad Gateway on production deploys.
- Added verification steps and warnings in docs/UPDATE_AND_DEPLOY.txt and docs/DEPLOY notes to always check that the built image contains all required Python modules (presence_store.py is critical for the Team/Presence feature introduced in v1.3+).
- In future, any new .py modules added to server.py must be added to the Dockerfile COPY line to prevent similar post-deploy 502s.

### Documentation & Housekeeping
- Version bumped to 1.4.1.
- CHANGELOG, new RELEASE_v1.4.1.md, README, AGENTS.md, VERSION, docs/GITHUB_RELEASES.md, docs/UPDATE_AND_DEPLOY.txt updated.
- The hotfix was applied on the production droplet via local Dockerfile edit + rebuild (as the tag was already cut), then the source Dockerfile was corrected and released.

See also [docs/RELEASE_v1.4.1.md](./docs/RELEASE_v1.4.1.md) for the full GitHub release text.

## [1.4.0] — 2026-06-08

Focus on stabilizing and polishing the local kanban tile UX and the Team/Presence demo indicators + inbox read/unread cues (from extensive live testing session).

### Local Kanban fixes
- Moved editable board name up into the standard tile title bar (toolbar) like other tiles (notes/groups); removed internal name input/duplicate; now uses dataset.tileLabel + dblclick contentEditable on .tile-toolbar-title with persist + no more .tile-toolbar-title hide.
- Column edit (✎) button now left of × (delete).
- Stage column color picker now visibly updates header via `<span class="column-dot">` (always shown, not just card borders or when populated).
- Fixed "add task" inline input crash: `Uncaught NotFoundError: removeChild` (node no longer child, possibly moved in blur). Used `let submitted`, `setTimeout(0, cleanup)` + guards in blur/keydown paths for +status/+task.
- Scrapped broken column drag/reorder (draggable, 'col:' data, makeReorderDrop, body drop col handling) per request (it never worked reliably, bubbled etc.).
- Edit button for columns now includes ◀ / ▶ slide buttons to move stage left/right (array splice + rebuild + re-open edit UI).

### Presence / Team demo indicator + inbox cues
- Added (and made persistent for every new user/session) client-side demo message with concise team presence/messaging explanation (no admin mention): "Team presence shows online users (green dot + count). Click the Team button to view roster and switch to Messages tab for DMs with replies and read status."
- Blue unread bubble (top-right on Team) now reliably appears/stays on reload (sync force in ensurePresenceOnLogin + re-assert in every badge update) until user explicitly clicks the demo in inbox.
- Introduced `demoMessageReadThisSession` flag (per page load) + `!demoMessageReadThisSession` guard for forcing blue "1" and header update. Decoupled from lastRead/ts to stop on/off flashing.
- On close of team popup: header indicators refreshed so count reflects only un-clicked messages.
- Messages inbox now has clear read/unread indication via dark/light shading: `.unread` gets surface-2 + blue left border accent + blue ● dot; `.read` gets opacity fade + muted text. Demo row specially forced by session flag (always "unread" visually until clicked, with "just now (demo)" label to avoid bad timestamps).
- Demo injection always ensures example msg in inbox list (re-added after server overwrites) but respects the read flag for count + shading.
- All updates to docs, new RELEASE, session chat log.

### Documentation & Housekeeping
- Version bumped to 1.4.0.
- CHANGELOG, new RELEASE_v1.4.md, README, AGENTS.md, VERSION, GITHUB_RELEASES.md, UPDATE_AND_DEPLOY.txt, docs/SESSION_2026-06-07.md (chat history + date stamp) updated.
- Local kanban + presence live fixes from verbatim user reports fully documented.

See also [docs/RELEASE_v1.4.md](./docs/RELEASE_v1.4.md) for the full GitHub release text.

## [1.3.0] — 2026-06-07

Major live-testing follow-up focused on the new Team / Presence feature (user status, basic DMs, inbox, admin tools) plus UI polish for the modal.

### Presence / Team (new feature, completed from user verbatim list)
- Header button (users icon, secondary style, left of New Tile) opens popup instantly (early bind + no blocking await on CRM loadPortalUsers; immediate render from cache + background refresh).
- Roster: users from CRM /people (same list as notify), online (green dot + heartbeat <10m), idle (>2h amber), offline (dark), "last seen X" via formatTimeAgo for offline.
- Status: dropdown (not buttons) with "Online" default + 3 templates ("Estimating - Do Not Disturb", "AFK - Lunch", "AFK - Pesky In-laws") + Custom... (emoji support, 120 char limit). "Status:" label to left of dark-mode select. Persisted server-side.
- DMs: click any user (online or offline) to open thread; send/receive works to offline users (delivered on next login). Basic history shown.
- Inbox / message tracking: "Messages" tab (separate from Team roster) shows recent DMs (from myRecentDms) with snippets, timestamps, click-to-thread, and × clear/archive per conversation. Thread also has Clear button. Backend uses per-convo JSON files under data/presence-messages/.
- Read receipts: "read" indicator appears on your sent messages once recipient opens the thread.
- Reply to message: click any prior message in thread to reply; quoted context shown in smaller font (with "Replying to:") above your text in the bubble (Signal/WhatsApp style). reply_to + reply_text carried in messages.
- Emoji selector: 😊 button in DM input opens compact picker; inserts at cursor. Messages support Unicode emojis.
- Color coding: received messages always green bubble; your sent messages use current accent color. Per-direction (1:1 DMs).
- Self-online indicator on header button: green dot (`.is-online::before`) even when alone (separate from count badge). Red pulsing flash (`.has-waiting-messages::after`) for unread DMs (separate from online count).
- Admin section (kenc@vanguardadj.com only): shows last CRM/dashboard activity minutes. Hidden by default with "Admin" toggle button in actions bar; button only visible on Team tab (not Messages tab); "Admin" text when hidden.
- Popup polish: taller messaging areas (.presence-list and .presence-dm now 480px max), message viewing area (#presence-dm-log) has min-height + larger font for more history visible at once. Entire popup window is now user-resizable (resize: both + min/max on #presence-modal .modal-card; only this modal affected).
- Reliability: direct presenceFetch (with X-OnlyOffice-Portal header) so /api/presence/* routes (users, snapshot, status, dm get/post, heartbeat, clear) are hit instead of proxy fallback. Routing hardened with early startswith checks + explicit 404 for unknown presence paths. No more generic "Failed" / 404s once server restarted.
- (Note: one remaining live bug with reply context not always rendering in sent history bubbles is paused per explicit request; core reply send/receive + preview + embedded text works.)

### Documentation & Housekeeping
- Version bumped to 1.3.0.
- CHANGELOG, new RELEASE_v1.3.md, README, AGENTS.md, VERSION, GITHUB_RELEASES.md updated.
- All presence-related live feedback (instant button, no errors, default Online, Status: label + dark select, online/offline + last seen, full inbox with delete, indicators, admin hidden+tab-only, taller/resizable popup, replies+emojis+colors+reads) documented.
- Reply context display bug in chat history explicitly noted as paused.

Full details in conversation history and source (public/app.js renderPresence* + openPresenceDMThread, presence_store.py, server.py handlers, styles.css presence rules).

See also [docs/RELEASE_v1.3.md](./docs/RELEASE_v1.3.md) for the full GitHub release text.

## [1.2.0] — 2026-06-06

Post-v1.1.0 testing follow-up release. All items from the explicit post-deploy list plus live feedback (collapse behavior, keyword semantics, template UX, tasks list modal, crash banner polish, styling, icon, docs) were implemented, tested, and shipped.

### Presence / Team follow-ups (from live session feedback)
- Presence button now opens instantly (removed blocking CRM `loadPortalUsers` await; immediate render from cache + background refresh).
- DM "click user", send, and status change no longer error ("Could not load messages" / "unable to send" / "could not set status"). Root cause: direct presence fetches now send `X-OnlyOffice-Portal` header (via new `presenceFetch` helper) so server resolves portal the same as profile/proxy calls.
- Default status "Online" (picker pre-selects it; list suppresses the literal "Online" text for roster cleanliness).
- "Status:" label to left of dark-mode `<select>` (uses `--surface-2` etc); sections "Online (n)" / divider / "Offline (n)" + "last seen X" for offline rows already wired.
- Inbox / message tracking: modal now shows "Recent messages" section (from `myRecentDms` in snapshot) with per-convo snippets, timestamps, click-to-open thread (works for offline users), and × clear per row. Thread view also has "Clear" button. Backend: `clear_conversation`, DELETE `/api/presence/dm?with=...` wired + store unlink.
- Self-online indicator: green dot on the header presence button icon (`.is-online::before`) driven by snapshot; visible even when you are the only one (separate from count badge and red "waiting messages" flash).

### Fixes & Polish
- **Tile collapse & minimize (notes, calendar, groups)**: Notes and calendar tiles now properly collapse (body content hidden while toolbar remains); added CSS overrides to defeat tile-specific min-heights. Calendar double-height now scales the month grid vertically (body flex + grid + day min-heights). CRM group tiles support half/quarter width while collapsed (minimized bar stays narrow).
- **Group removal persistence**: Removing a group tile now calls `saveUserProfileToServer({quiet:true})` immediately so the deletion survives quick reloads.
- **Tasks rows**: Description is now shown (`.task-desc`, truncated in compact rows) alongside title, using the same patterns as other task rendering.
- **CRM notifications keyword filter**: Switched from OR to strict **AND** semantics for comma-separated keywords. Input is split on `,`, trimmed; a notification matches only if *every* token is present in the blob (`tokens.every`). Single keyword continues to work. Placeholder text updated to reflect inclusive/AND behavior.
- **Preview modal persistence**: Launching "edit" from the opportunity preview no longer auto-closes the preview; after save the preview data is refreshed in place.
- **Favicon / logos**: Updated to the white ship variant for better contrast and visibility across themes.
- **Linked email errors**: "Message ... wasn't found" cases in opportunity preview now show a friendly message instead of the raw error.
- **Tasks list modal styling**: Light backgrounds (body #ffffff, rows #f8f9fa with hover, done state dimmed + strikethrough), high-contrast text (#212529), muted meta, explicit header contrast for readability. Accent color on checkboxes.
- **CRM backend crash / 5xx banner**: Fully implemented. `api()` wrapper detects `!res.ok && status >= 500` (or JSON parse failure) on paths containing `/crm/` and calls `showCrmCrashNotification()`. Banner uses the exact requested wording: "OnlyOffice CRM backend error (e.g. 502 on history). Dashboard may be out of date. Refresh page now — recommended in ~30 seconds." Includes "Refresh page now" button (location.reload()). Throttled (~15s), role=alert, sticky. Any successful CRM-path response auto-clears it. Testable by DevTools Network throttling or blocking /api/proxy/api/2.0/crm/* .

### Features / Enhancements
- **Full tasks list modal**: New discreet button (minimalistic light file-cabinet SVG icon) placed in the tasks panel header (flex layout, left of the user filter). Opens `#tasks-list-modal`. 
  - Fetches open tasks (`isClosed=false`) + completed (`isClosed=true`) and merges.
  - "Show completed" toggle re-renders the filtered set.
  - Each row: checkbox (close/reopen via POST /close or /reopen with optimistic update + re-render), title (deep link via existing `crmTaskUrl`), due date, responsible person.
  - "New Task" footer button opens the existing create-task modal.
  - Matches existing task row/checkbox/close patterns; reuses profile schedule + api wrapper.
- **Group templates — delete only**: Replaced the prior "manage/edit + delete via prompts" with a clean delete-only experience. New `openTemplateDeleteModal()` lists every saved template across all groups; each entry has an × button. Click → confirm → remove from the group's templates array → `saveUserProfileToServer` → refresh all group template `<select>` elements and the list itself. Toolbar button on groups updated to open the delete modal. No rename/edit paths remain.
- **Tasks list icon**: Final icon is a minimal, light, stroke-based file-cabinet SVG (after iterations from emoji); placed inside the header construction for the new button (`id="tasks-list-btn"`).

### Documentation & Housekeeping
- **AGENTS.md** (new root file): Persistent project context loaded automatically. Covers architecture summary, key reuse patterns (profile, api(), tile renderers, modals, attachTileCollapseButton, etc.), the exact post-1.1 user list, run/test/deploy commands, and instructions to prefer `/load` or welcome picker + `cd` first instead of full context dumps on every session.
- Removed the entire FEAT-009 (CRM CRASH notification) section from FUTURE_FEATURES.md (the banner was already implemented and shipped; kept only the implementation recap in conversation for testing guidance).
- CHANGELOG, RELEASE notes, README, GITHUB_RELEASES.md, AGENTS.md, and VERSION updated for v1.2.0.
- AccuLynx API research (FEAT-008) remains in FUTURE_FEATURES.md under "Other ideas" (added earlier per request; not implemented).

Custom fields (ISSUE-001) research artifacts from pickup remain disabled and are not part of this release. See AGENTS.md and FUTURE_FEATURES.md for current roadmap.

See also [docs/RELEASE_v1.2.md](./docs/RELEASE_v1.2.md) for the full GitHub release text.

## [1.1.0] — 2026-06-05

See also [docs/RELEASE_v1.1.md](./docs/RELEASE_v1.1.md) for the full GitHub release text.

### Fixes
- CRM notifications feed empty after pagination refactor — restored bulk history + mail loading.
- Feed no longer shows “no events” while mail/history is still loading.
- Hidden notifications: server-backed entries with snapshots; restore via toolbar modal.
- Archived notes tiles no longer auto-deleted from server profile.
- Removed non-working archived-notes UI from **Add tile** (moved to notes **File** menu).
- Group profile saves omit embedded opportunity lists (refetch on expand).

### CRM notifications (new / improved)
- **90-day** feed window (was 30).
- **200-event** load cap.
- Loading spinner in feed header; scroll to load more (until cap).
- 5-minute in-session feed cache.
- Hidden-notifications manager (hide per item, review/restore, 30-day retention).

### Notes tiles (new / improved)
- Server persistence per user; archive retained on server.
- **File** menu: `.txt` / `.md` export, archive, duplicate, **restore from archive** (by date → fills current note).
- Presets: **Daily**, **Claim checklist** (CRM checkbox fields).
- Quarter width; Edit/Preview; icon toolbar; save footer (time + stats).
- Removed link-deal from notes; **Daily Standup** renamed to **Daily**.

### Dashboard performance
- Minimized tiles skip CRM fetches until expanded.
- Parallel login bootstrap; deferred per-card custom-field enrichment (`IntersectionObserver`).

### UI
- **Red X** remove icon (groups, calendar, notes).
- **Save template** floppy-disk icon on groups.
- Minimize + icon-based layout controls on all tiles.
- Kanban card **preview** → opportunity preview modal.

---

## [1.0.0] — 2026-06-05

First production-ready release on GitHub.

### Core dashboard
- OnlyOffice CRM kanban with opportunity groups (stage/tag filters, templates, red-deal filter).
- Pinned **CRM notifications** and **Tasks** panels with layout controls.
- Global opportunity search in the header.
- Create opportunity and quick-note modals; deal edit from cards.

### Tiles
- **Add tile**: opportunity groups, calendar (ICS feed), notes.
- Per-user dashboard profile on server (`/api/user-profile`): groups, layout, calendars, notes, feed keyword, hidden feed keys.
- Calendar monthly view with timezone selector and event detail modal.

### Deploy & ops
- Docker Compose deploy to DigitalOcean (`dashboard.vanguardadj.com`).
- GitHub Actions deploy workflow; production server notes and estimate-nginx network in compose.
- Documentation: `DEPLOY.md`, `docs/UPDATE_AND_DEPLOY.txt`, `docs/PRODUCTION_SERVER_NOTES.txt`.## [Unreleased]

### Fixed
- `server.py` `do_POST` no longer crashes with `AttributeError: 'super' object has no attribute 'do_POST'` on non-API POST requests; now returns HTTP 405.

