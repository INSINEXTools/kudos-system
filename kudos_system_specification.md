# Kudos System Specification

> **Repository Link:** `https://github.com/INSINEXTools/kudos-system.git`  
> **Role:** Graduate Developer / AI Architect (Datacom)  
> **Methodology:** Spec-Driven Development  

---

## 1. Overview

The **Kudos System** is an internal employee recognition feature for the company portal. It enables employees to recognize colleagues by selecting a recipient, writing a short message of appreciation, and publishing it to a shared dashboard feed. To maintain a safe and professional workplace environment, the specification incorporates **role-based content moderation**, **anti-spam controls**, and **audit logging** added during the Architect Review phase.

---

## 2. Functional Requirements

### 2.1 User Stories

1. **Authentication & Authorization:** As an employee, I must be authenticated via the internal portal SSO/session system to access the Kudos feature, with my role (`employee` or `admin`) determining my permissions.
2. **Colleague Selection:** As an authenticated user, I can search and select a colleague from an active employee directory dropdown (excluding myself) so that I can direct my appreciation to the right person.
3. **Kudos Creation & Submission:** As an authenticated user, I can write a message of appreciation (10–500 characters) and submit it so that it is persisted in the database and displayed publicly.
4. **Public Dashboard Feed:** As an authenticated user, I can view a paginated, reverse-chronological feed of recently submitted, visible kudos on the main dashboard.
5. **Content Moderation (Architect Addition):** As an administrator, I can hide (soft-delete) or permanently delete inappropriate kudos messages and record a moderation reason so that workplace standards are upheld.
6. **Edge-Case & Abuse Prevention (Architect Addition):** As a system owner, the platform must prevent self-kudos, duplicate submissions within a short window, spam flooding, and malicious script injection.
7. **Responsive Experience:** As an employee, I can submit and view kudos seamlessly across desktop, tablet, and mobile viewports.

### 2.2 Acceptance Criteria

| User Story | Acceptance Criteria |
| :--- | :--- |
| **1. Auth & Roles** | - Unauthenticated requests to any `/api/kudos` endpoint return `401 Unauthorized`.<br>- Non-admin requests to moderation endpoints return `403 Forbidden`. |
| **2. Colleague Selection** | - Dropdown lists only active employees (`is_active = true`).<br>- The currently logged-in user is excluded from the recipient list (also enforced server-side).<br>- Supports type-ahead search by name or department. |
| **3. Kudos Submission** | - Message must be trimmed and between 10 and 500 characters; live character counter displayed.<br>- Empty, whitespace-only, or oversized messages are blocked client-side and return `400 Bad Request` server-side.<br>- On success, a confirmation toast appears and the new kudos immediately prepends to the feed. |
| **4. Public Feed** | - Displays sender name, recipient name, message, and relative timestamp.<br>- Only records where `is_visible = true` and `deleted_at IS NULL` appear to standard users.<br>- Feed loads 20 items per page with "Load More" or pagination controls. |
| **5. Content Moderation** | - Admins see a **Hide** and **Delete** action on each kudos card and can toggle a "Show Hidden" filter.<br>- Hiding a kudos sets `is_visible = false`, records `moderated_by`, `moderated_at`, and `reason_for_moderation` (required, min 5 chars).<br>- Admins can restore a hidden kudos (`is_visible = true`).<br>- Hard-deleting permanently removes or archives the record after a confirmation dialog. |
| **6. Edge Cases & Abuse** | - **Self-kudos:** Rejected with `400 Bad Request` (`"Cannot send kudos to yourself"`).<br>- **Duplicate submission:** Identical `(sender_id, recipient_id, message)` submitted within 5 minutes is rejected with `409 Conflict`.<br>- **Spam / Rate limiting:** Maximum 10 kudos per user per hour; exceeding returns `429 Too Many Requests`. |
| **7. Responsive UI** | - Layout adapts cleanly to mobile (`< 640px`), tablet (`640px–1024px`), and desktop (`> 1024px`) without horizontal overflow. |

---

## 3. Technical Design

### 3.1 Database Schema (Updated for Moderation)

Relational schema designed for PostgreSQL (compatible with SQLite for local development).

#### `users` Table
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | Unique employee identifier |
| `full_name` | `VARCHAR(120)` | `NOT NULL` | Employee display name |
| `email` | `VARCHAR(255)` | `UNIQUE, NOT NULL` | Corporate email |
| `department` | `VARCHAR(100)` | `NULL` | Team or department name |
| `role` | `VARCHAR(20)` | `NOT NULL, DEFAULT 'employee'` | `'employee'` or `'admin'` |
| `is_active` | `BOOLEAN` | `NOT NULL, DEFAULT true` | Whether user is active in directory |
| `created_at` | `TIMESTAMP` | `NOT NULL, DEFAULT CURRENT_TIMESTAMP` | Account creation timestamp |

#### `kudos` Table *(Includes Architect Moderation Fields)*
| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | `PRIMARY KEY` | Unique kudos identifier |
| `sender_id` | `UUID` | `NOT NULL, FOREIGN KEY -> users(id)` | Employee giving kudos |
| `recipient_id` | `UUID` | `NOT NULL, FOREIGN KEY -> users(id)` | Employee receiving kudos (`CHECK (sender_id <> recipient_id)`) |
| `message` | `VARCHAR(500)` | `NOT NULL` | Sanitized appreciation message |
| `is_visible` | `BOOLEAN` | `NOT NULL, DEFAULT true` | Controls visibility in public feed |
| `moderated_by` | `UUID` | `NULL, FOREIGN KEY -> users(id)` | Admin who hid/moderated the message |
| `moderated_at` | `TIMESTAMP` | `NULL` | Timestamp of moderation action |
| `reason_for_moderation` | `VARCHAR(255)` | `NULL` | Mandatory reason when hidden by an admin |
| `created_at` | `TIMESTAMP` | `NOT NULL, DEFAULT CURRENT_TIMESTAMP` | Submission timestamp |

#### Indexes
* `idx_kudos_visible_created`: `(is_visible, created_at DESC)` — optimizes public dashboard feed queries.
* `idx_kudos_recipient_id`: `(recipient_id)` — supports future profile/received-kudos filtering.
* `idx_kudos_duplicate_check`: `(sender_id, recipient_id, created_at DESC)` — speeds up duplicate and rate-limit checks.

---

### 3.2 API Endpoints

All endpoints require a valid Bearer JWT or authenticated session cookie.

| Method | Endpoint | Access | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/users` | Authenticated | Returns list of active colleagues (excluding current user) for dropdown selection. Supports `?search=` query. |
| `GET` | `/api/kudos` | Authenticated | Returns paginated kudos feed (`?page=1&limit=20`). Standard users receive only `is_visible = true`. Admins may pass `?include_hidden=true`. |
| `POST` | `/api/kudos` | Authenticated | Creates a new kudos entry. |
| `PATCH` | `/api/kudos/:id/moderate` | Admin Only | Toggles `is_visible` (hide/restore) and records `moderated_by`, `moderated_at`, and `reason_for_moderation`. |
| `DELETE` | `/api/kudos/:id` | Admin Only | Permanently deletes an inappropriate kudos entry. |

#### Example Payloads

**`POST /api/kudos` Request:**
```json
{
  "recipient_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Huge thanks for staying late to help debug the release pipeline!"
}
```

**`POST /api/kudos` Response (`201 Created`):**
```json
{
  "id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "sender": { "id": "...", "full_name": "Alex Chen" },
  "recipient": { "id": "550e8400-...", "full_name": "Priya Patel" },
  "message": "Huge thanks for staying late to help debug the release pipeline!",
  "is_visible": true,
  "created_at": "2026-11-22T08:15:00Z"
}
```

**`PATCH /api/kudos/:id/moderate` Request:**
```json
{
  "is_visible": false,
  "reason_for_moderation": "Contains unprofessional language violating company code of conduct."
}
```

---

### 3.3 Frontend Component Architecture

```text
KudosDashboardPage
├── KudosHeader (Title, user role badge, Admin "Show Hidden" toggle)
├── KudosFormCard
│   ├── ColleagueSelector (Searchable dropdown populated via GET /api/users)
│   ├── MessageTextarea (500-char limit + live counter + inline validation)
│   └── SubmitButton (Loading state + error/success toast notifications)
└── KudosFeed
    ├── KudosCard (Sender -> Recipient, message, timestamp)
    │   └── AdminModerationControls (Visible only if user.role === 'admin')
    │       ├── HideRestoreButton -> opens ModerationReasonModal
    │       └── DeleteButton -> opens ConfirmDeleteModal
    └── PaginationControls ("Load More" button / page indicator)
```

---

### 3.4 Security, Performance & Reliability

* **Security:**
  * **Authentication & RBAC:** Server-side middleware verifies user identity and enforces `role === 'admin'` on `PATCH /moderate` and `DELETE` routes.
  * **Input Sanitization & XSS Prevention:** Strip HTML tags / encode output on both server and client; use parameterized SQL/ORM queries to prevent SQL injection.
  * **Rate Limiting & Anti-Spam:** Limit `POST /api/kudos` to 10 requests/hour per user and reject duplicate payloads within 5 minutes.
* **Performance:**
  * **Pagination:** Default page size of 20 records with indexed `created_at DESC` ordering.
  * **Caching:** Cache the active colleague list (`GET /api/users`) with a 5-minute TTL to reduce database load.
* **Error Handling & Logging:**
  * Standardized JSON error responses: `{ "error": { "code": "VALIDATION_ERROR", "message": "..." } }`.
  * Structured server logs (JSON format) capturing all moderation actions (`admin_id`, `kudos_id`, `action`, `reason`, `timestamp`) for compliance auditing.

---

## 4. Implementation Plan

### Phase 1: Database & Backend Core
1. **Task 1.1:** Initialize project structure, environment configuration, and database connection.
2. **Task 1.2:** Create database migrations for `users` and `kudos` tables (including `is_visible`, `moderated_by`, `moderated_at`, `reason_for_moderation`, constraints, and indexes). *(Depends on 1.1)*
3. **Task 1.3:** Implement authentication & RBAC middleware (`requireAuth`, `requireAdmin`). *(Depends on 1.2)*
4. **Task 1.4:** Build `GET /api/users`, `GET /api/kudos`, and `POST /api/kudos` with input validation, self-kudos check, duplicate detection, and rate limiting. *(Depends on 1.3)*
5. **Task 1.5:** Build admin moderation endpoints (`PATCH /api/kudos/:id/moderate` and `DELETE /api/kudos/:id`) with audit logging. *(Depends on 1.4)*

### Phase 2: Frontend Implementation
6. **Task 2.1:** Scaffold responsive `KudosDashboardPage` layout and API client service. *(Depends on 1.4)*
7. **Task 2.2:** Implement `KudosFormCard` with searchable `ColleagueSelector`, 500-character counter, and error handling. *(Depends on 2.1)*
8. **Task 2.3:** Implement `KudosFeed` and `KudosCard` with pagination. *(Depends on 2.1)*
9. **Task 2.4:** Implement `AdminModerationControls`, `ModerationReasonModal`, and "Show Hidden" filter for admin users. *(Depends on 1.5, 2.3)*

### Phase 3: Testing & Deployment
10. **Task 3.1 – Unit Tests:** Validate input sanitization, character limits, self-kudos prevention, and duplicate/rate-limit rules.
11. **Task 3.2 – Integration Tests:** Test all API endpoints for `200/201/400/401/403/409/429` responses and verify hidden kudos are excluded from non-admin feed queries.
12. **Task 3.3 – UI/E2E Tests:** Verify full submit-to-feed flow and admin hide/restore/delete flow across desktop and mobile viewports.
13. **Task 3.4 – Deployment:** Run database migrations via CI/CD pipeline, configure environment secrets (`DATABASE_URL`, `JWT_SECRET`), and enable health checks and moderation log alerts.

---

## 5. Architect Reflection

1. **How did the structured approach to specification change your development process compared to traditional coding?**  
   Writing the specification first shifted effort from reactive trial-and-error coding to upfront architectural thinking. Instead of discovering missing features (like moderation or duplicate protection) halfway through implementation, all constraints and data models were aligned before a single line of application code was written.
2. **What was the most challenging part of reviewing and refining the AI-generated specification?**  
   Anticipating non-obvious edge cases and abuse vectors—such as self-kudos, spam rate limiting, auditability of moderation actions (`moderated_by`, `moderated_at`, `reason_for_moderation`), and ensuring hidden records never leak to non-admin API responses.
3. **How did having a complete specification before implementation affect the quality and completeness of the final code?**  
   A clear, unambiguous blueprint prevented scope drift and allowed the AI agent to generate consistent database schemas, API contracts, frontend components, and test cases in one cohesive pass with minimal rework.