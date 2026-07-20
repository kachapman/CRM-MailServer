**ISSUE-002 — CRM Mail: mark read/unread, account selector, unread badge, and linking**  
**Status:** ✅ Re-enabled in v1.7.0 — server API calls for mark/unread, delete, and link-to-deal now work. Account selector remains disabled (unified inbox only). See  **Root cause** below.  
   
 **Priority:** Medium  
   
 **Area:** Mail inbox modal (public/app.js, public/index.html), mail history linking  
**Summary**  
The mark read/unread toolbar buttons and delete button were viewer-only (no server push). Linking to deals existed but used a fallback history event. The root cause was using message-level endpoints (POST /api/2.0/mail/messages/markread) which returned HTML errors — the native CRM operates on **conversations** (not individual messages). The dashboard list was loaded from /api/2.0/mail/messages which returned message objects without conversationId, making it impossible to use conversation-level APIs.  
The account selector pulldown remains disabled (unified inbox only). The unread badge indicator works but may reflect local state combined with server data.  
**Root cause**  
All mail operations in the native OnlyOffice CRM (mark read/unread, delete, link to CRM) use **conversation-level** endpoints, not message-level:  
| | | |  
|-|-|-|  
| **Operation** | **Endpoint** | **Body** |   
| Mark read/unread | PUT /api/2.0/mail/conversations/mark.json | ids[]=<convId>&status=read\|unread |   
| Delete (move to trash) | PUT /api/2.0/mail/conversations/move.json | ids[]=<convId>&folder=4 |   
| Link to CRM | PUT /api/2.0/mail/conversations/crm/link.json | {"id_message":<convId>,"crm_contact_ids":...} |   
   
The dashboard previously loaded /api/2.0/mail/messages which returned individual message objects without conversationId, so conversation IDs were never available. Additionally, mark/delete handlers attempted POST /api/2.0/mail/messages/markread which returned HTML errors (endpoint does not exist at message level in this Community Server version).  
**Fix (v1.7.0)**  
1. **Switched list endpoint**: loadMailMessagesForModal now loads /api/2.0/mail/conversations.json?folder=1&page_size=...&sort=date&sortorder=descending instead of /api/2.0/mail/messages. Conversation objects have compatible fields (id, subject, from, date, read) so renderMailList works without changes.  
2. **Mark read/unread**: Handlers now PUT /api/2.0/mail/conversations/mark.json with form-urlencoded ids[]=<id>&status=read|unread. Local mailDashboardReadIds Set preserved as fallback if the server call fails.  
3. **Delete**: Button shown (was display:none). Handler now PUT /api/2.0/mail/conversations/move.json with ids[]=<id>&folder=4 (trash). Includes confirmation dialog.  
4. **Link to deal**: Sidebar restored (replaces the viewer-warning sidebar). Uses existing POST /api/2.0/mail/crm/link endpoint with conversation IDs as messageIds + fallback history event. The resetQuickLinkSidebar() function clears state on modal open.  
5. **Expand (View)**: Changed from fetchMailMessage(id) (message-level) to loading conversation detail via /api/2.0/mail/conversation/{convid}.json?loadAll=false and extracting the first message for renderMailEmbedPanel.  
6. **Local persistence**: mailDashboardReadIds Set + localStorage preserved for read status resilience. markMailMessageRead (auto-mark on expand) now also pushes to server (best-effort, non-blocking).  
**Files changed (v1.7.0)**  
| | |  
|-|-|  
| **File** | **Role** |   
| public/index.html | Restored link sidebar HTML (.mail-right-sidebar); removed viewer-warning sidebar; delete button visible |   
| public/app.js | loadMailMessagesForModal → conversations API; mark/unread/delete handlers → server API; expand → conversation detail; resetQuickLinkSidebar() added; viewer-warning references removed; markMailMessageRead pushes to server |   
| ISSUES.md | This update |   
   
**What remains**  
- Account selector pulldown still disabled (unified inbox). Re-enabling would need a working /api/2.0/mail/accounts → folder list → filter by folderId.  
- Badge indicator uses a mix of server folder counts and local overrides; may not perfectly reflect native CRM unread state.  
- Link sidebar searches only opportunities (no contacts or other entity types).  
- Delete moves to trash (folder 4); does not permanently delete.  
**References**  
- Conversations list: GET /api/2.0/mail/conversations.json?folder=1&page_size=...&sort=date&sortorder=descending  
- Conversation detail: GET /api/2.0/mail/conversation/{id}.json?loadAll=false  
- Mark: PUT /api/2.0/mail/conversations/mark.json (form-urlencoded ids[]=<id>&status=read|unread)  
- Delete: PUT /api/2.0/mail/conversations/move.json (form-urlencoded ids[]=<id>&folder=4)  
- Link primary: POST /api/2.0/mail/crm/link (messageIds + crmEntityId + crmEntityType:2); fallback history POST  
- Accounts/folders for badge: /api/2.0/mail/accounts, /api/2.0/mail/folders?accountId=...  
- History mail parse: parseHistoryMailPayload, isMailLinkedHistoryEvent, extractMailMessageIds, crmMailReceivedLine, renderMailHistoryReceivedSummary  
- See also CHANGELOG / RELEASE notes for v1.7.0 context  
   
