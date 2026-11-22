const state = {
  users: [],
  currentUser: null,
  page: 1,
  perPage: 10,
  totalPages: 1,
  includeHidden: false,
};

const currentUserSelect = document.getElementById("currentUserSelect");
const roleBadge = document.getElementById("roleBadge");
const recipientSelect = document.getElementById("recipientSelect");
const messageInput = document.getElementById("messageInput");
const charCount = document.getElementById("charCount");
const kudosForm = document.getElementById("kudosForm");
const formFeedback = document.getElementById("formFeedback");
const kudosFeed = document.getElementById("kudosFeed");
const adminToggleWrapper = document.getElementById("adminToggleWrapper");
const showHiddenToggle = document.getElementById("showHiddenToggle");
const prevPageBtn = document.getElementById("prevPageBtn");
const nextPageBtn = document.getElementById("nextPageBtn");
const pageInfo = document.getElementById("pageInfo");

function apiHeaders() {
  const headers = { "Content-Type": "application/json" };
  if (state.currentUser) {
    headers["X-User-Id"] = String(state.currentUser.id);
  }
  return headers;
}

function showFeedback(text, type) {
  formFeedback.textContent = text;
  formFeedback.className = `feedback ${type}`;
  formFeedback.hidden = false;
}

function hideFeedback() {
  formFeedback.hidden = true;
}

function populateRecipientDropdown() {
  recipientSelect.innerHTML = '<option value="">Select a colleague...</option>';
  state.users.forEach((u) => {
    if (!state.currentUser || u.id !== state.currentUser.id) {
      const opt = document.createElement("option");
      opt.value = u.id;
      opt.textContent = `${u.name} (${u.department})`;
      recipientSelect.appendChild(opt);
    }
  });
}

function updateRoleUI() {
  const isAdmin = state.currentUser && state.currentUser.role === "admin";
  roleBadge.textContent = isAdmin ? "Admin" : "Employee";
  roleBadge.className = isAdmin ? "badge admin" : "badge";
  adminToggleWrapper.hidden = !isAdmin;
  if (!isAdmin) {
    state.includeHidden = false;
    showHiddenToggle.checked = false;
  }
}

async function loadUsers() {
  const res = await fetch("/api/users");
  const data = await res.json();
  state.users = data.users || [];

  currentUserSelect.innerHTML = "";
  state.users.forEach((u) => {
    const opt = document.createElement("option");
    opt.value = u.id;
    opt.textContent = `${u.name} — ${u.role}`;
    currentUserSelect.appendChild(opt);
  });

  if (state.users.length > 0) {
    state.currentUser = state.users[0];
    currentUserSelect.value = state.currentUser.id;
    updateRoleUI();
    populateRecipientDropdown();
  }
}

function renderFeed(items) {
  kudosFeed.innerHTML = "";
  if (!items.length) {
    kudosFeed.innerHTML = '<p style="color:#6b7280;">No kudos yet. Be the first to recognize a colleague!</p>';
    return;
  }

  const isAdmin = state.currentUser && state.currentUser.role === "admin";

  items.forEach((item) => {
    const card = document.createElement("article");
    card.className = `kudos-item${item.is_visible ? "" : " hidden-item"}`;

    const dateStr = new Date(item.created_at).toLocaleString();

    const meta = document.createElement("div");
    meta.className = "kudos-meta";
    meta.innerHTML = `<span><strong>${item.sender_name}</strong> → <strong>${item.recipient_name}</strong> (${item.recipient_department})</span><span>${dateStr}</span>`;
    card.appendChild(meta);

    const msg = document.createElement("p");
    msg.className = "kudos-message";
    // Message is already HTML-escaped by backend; render safely via textContent
    const decoded = new DOMParser().parseFromString(item.message, "text/html").documentElement.textContent;
    msg.textContent = decoded;
    card.appendChild(msg);

    if (!item.is_visible) {
      const note = document.createElement("div");
      note.className = "moderation-note";
      note.textContent = `Hidden by ${item.moderated_by_name || "Admin"} — Reason: ${item.reason_for_moderation || "N/A"}`;
      card.appendChild(note);
    }

    if (isAdmin) {
      const actions = document.createElement("div");
      actions.className = "admin-actions";

      const toggleBtn = document.createElement("button");
      toggleBtn.className = "btn btn-secondary btn-sm";
      toggleBtn.textContent = item.is_visible ? "Hide" : "Restore";
      toggleBtn.addEventListener("click", () => handleModerate(item.id, !item.is_visible));

      const delBtn = document.createElement("button");
      delBtn.className = "btn btn-danger btn-sm";
      delBtn.textContent = "Delete";
      delBtn.addEventListener("click", () => handleDelete(item.id));

      actions.appendChild(toggleBtn);
      actions.appendChild(delBtn);
      card.appendChild(actions);
    }

    kudosFeed.appendChild(card);
  });
}

async function loadFeed() {
  const params = new URLSearchParams({
    page: String(state.page),
    per_page: String(state.perPage),
    include_hidden: String(state.includeHidden),
  });
  const res = await fetch(`/api/kudos?${params}`, { headers: apiHeaders() });
  const data = await res.json();

  state.totalPages = data.total_pages || 1;
  renderFeed(data.items || []);

  pageInfo.textContent = `Page ${data.page} of ${state.totalPages}`;
  prevPageBtn.disabled = data.page <= 1;
  nextPageBtn.disabled = data.page >= state.totalPages;
}

async function handleModerate(kudosId, makeVisible) {
  let reason = "";
  if (!makeVisible) {
    reason = window.prompt("Enter reason for hiding this kudos message:");
    if (!reason || !reason.trim()) return;
  }

  const res = await fetch(`/api/kudos/${kudosId}/moderate`, {
    method: "PATCH",
    headers: apiHeaders(),
    body: JSON.stringify({ is_visible: makeVisible, reason_for_moderation: reason }),
  });
  const data = await res.json();
  if (!res.ok) {
    alert(data.error || "Moderation failed.");
    return;
  }
  await loadFeed();
}

async function handleDelete(kudosId) {
  if (!window.confirm("Permanently delete this kudos message?")) return;
  const res = await fetch(`/api/kudos/${kudosId}`, {
    method: "DELETE",
    headers: apiHeaders(),
  });
  const data = await res.json();
  if (!res.ok) {
    alert(data.error || "Delete failed.");
    return;
  }
  await loadFeed();
}

kudosForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  hideFeedback();

  const recipientId = Number(recipientSelect.value);
  const message = messageInput.value;

  const res = await fetch("/api/kudos", {
    method: "POST",
    headers: apiHeaders(),
    body: JSON.stringify({ recipient_id: recipientId, message }),
  });
  const data = await res.json();

  if (!res.ok) {
    showFeedback(data.error || "Could not submit kudos.", "error");
    return;
  }

  showFeedback("Kudos sent!", "success");
  messageInput.value = "";
  charCount.textContent = "0";
  state.page = 1;
  await loadFeed();
});

messageInput.addEventListener("input", () => {
  charCount.textContent = String(messageInput.value.length);
});

currentUserSelect.addEventListener("change", async () => {
  const selectedId = Number(currentUserSelect.value);
  state.currentUser = state.users.find((u) => u.id === selectedId) || null;
  updateRoleUI();
  populateRecipientDropdown();
  hideFeedback();
  state.page = 1;
  await loadFeed();
});

showHiddenToggle.addEventListener("change", async () => {
  state.includeHidden = showHiddenToggle.checked;
  state.page = 1;
  await loadFeed();
});

prevPageBtn.addEventListener("click", async () => {
  if (state.page > 1) {
    state.page -= 1;
    await loadFeed();
  }
});

nextPageBtn.addEventListener("click", async () => {
  if (state.page < state.totalPages) {
    state.page += 1;
    await loadFeed();
  }
});

(async function init() {
  await loadUsers();
  await loadFeed();
})();
