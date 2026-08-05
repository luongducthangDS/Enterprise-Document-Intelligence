/**
 * HR Document Intelligence Agent - Enterprise Application Logic
 */

let currentUserRole = "Employee";
let activeView = "ai-assistant";
let isSolarPolicyIndexed = false;
let currentTickets = [...window.MOCK_DATA.tickets];
let currentDocs = [...window.MOCK_DATA.documents];

function refreshIcons() {
  if (window.lucide && typeof window.lucide.createIcons === "function") {
    window.lucide.createIcons();
  }
}

document.addEventListener("DOMContentLoaded", () => {
  renderMyTickets();
  renderAdminTickets();
  renderAdminDocs();

  const otpFields = [...document.querySelectorAll(".otp-field")];
  otpFields.forEach((field, index) => {
    field.addEventListener("input", () => {
      field.value = field.value.replace(/\D/g, "").slice(0, 1);
      if (field.value && otpFields[index + 1]) otpFields[index + 1].focus();
    });
    field.addEventListener("keydown", event => {
      if (event.key === "Backspace" && !field.value && otpFields[index - 1]) {
        otpFields[index - 1].focus();
      }
    });
  });

  document.addEventListener("keydown", event => {
    if (event.key !== "Escape") return;
    document.querySelectorAll(".modal-backdrop.active").forEach(modal => modal.classList.remove("active"));
    closeSourceDrawer();
    toggleMobileSidebar(false);
  });
});

/* ==========================================================================
   AUTHENTICATION & ROLE MANAGEMENT
   ========================================================================== */

function handleLoginSubmit(e) {
  e.preventDefault();
  const role = document.getElementById("login-role-select").value;
  currentUserRole = role;

  // Show 2FA Card
  document.getElementById("auth-login-card").style.display = "none";
  document.getElementById("auth-2fa-card").style.display = "block";
  start2FACountdown();
}

function verifyOTP() {
  const code = [
    document.getElementById("otp-1").value,
    document.getElementById("otp-2").value,
    document.getElementById("otp-3").value,
    document.getElementById("otp-4").value,
    document.getElementById("otp-5").value,
    document.getElementById("otp-6").value
  ].join('');

  if (code === "246810") {
    document.getElementById("auth-overlay").style.display = "none";
    switchAppRole(currentUserRole);
    showToast("✅ Authentication Successful! Signed in as " + currentUserRole, "success");
  } else {
    document.getElementById("2fa-error-msg").style.display = "block";
  }
}

function setDemoRole(role) {
  currentUserRole = role;
}

function showLoginScreen() {
  document.getElementById("auth-2fa-card").style.display = "none";
  document.getElementById("auth-login-card").style.display = "block";
}

function togglePasswordVisibility() {
  const pwd = document.getElementById("login-password");
  pwd.type = pwd.type === "password" ? "text" : "password";
}

function handleSSOLogin() {
  document.getElementById("auth-overlay").style.display = "none";
  switchAppRole(currentUserRole);
  showToast("✅ Single Sign-On Verified!", "success");
}

function start2FACountdown() {
  let sec = 45;
  const timer = setInterval(() => {
    sec--;
    const el = document.getElementById("countdown-timer");
    if (el) el.textContent = sec + "s";
    if (sec <= 0) clearInterval(timer);
  }, 1000);
}

/* ==========================================================================
   NAVIGATION & RBAC (403 ACCESS CONTROL)
   ========================================================================== */

function switchAppRole(newRole) {
  currentUserRole = newRole;

  // Update UI Elements
  document.getElementById("sidebar-role-select").value = newRole;
  document.getElementById("sidebar-user-name").textContent = newRole === "HR Admin" ? window.MOCK_DATA.adminUser.name : window.MOCK_DATA.currentUser.name;
  document.getElementById("sidebar-user-role").textContent = newRole;
  document.getElementById("sidebar-user-avatar").textContent = newRole === "HR Admin" ? "LT" : "AR";

  // Toggle Nav Group Visibilities
  document.getElementById("nav-employee-group").style.display = newRole === "Employee" ? "block" : "none";
  document.getElementById("nav-admin-group").style.display = newRole === "HR Admin" ? "block" : "none";
  document.getElementById("btn-header-upload").style.display = newRole === "HR Admin" ? "inline-flex" : "none";

  // Redirect if currently on prohibited view
  if (newRole === "Employee" && activeView.startsWith("admin-")) {
    navigateView("access-denied");
  } else if (newRole === "HR Admin" && (activeView === "ai-assistant" || activeView === "access-denied")) {
    navigateView("admin-overview");
  }
}

function toggleMobileSidebar(forceState) {
  const sidebar = document.querySelector(".app-sidebar");
  if (!sidebar) return;
  const shouldOpen = typeof forceState === "boolean" ? forceState : !sidebar.classList.contains("mobile-open");
  sidebar.classList.toggle("mobile-open", shouldOpen);
}

function navigateView(viewId) {
  // RBAC Check for 403 State
  if (viewId.startsWith("admin-") && currentUserRole !== "HR Admin") {
    viewId = "access-denied";
  }

  activeView = viewId;

  // Hide all view panels
  document.querySelectorAll(".view-panel").forEach(p => p.style.display = "none");
  const targetPanel = document.getElementById(`view-${viewId}`);
  if (targetPanel) targetPanel.style.display = "block";

  // Update Navigation Active State
  document.querySelectorAll(".nav-item").forEach(i => i.classList.remove("active"));
  const activeNavItem = document.getElementById(`nav-${viewId}`);
  if (activeNavItem) activeNavItem.classList.add("active");

  // Update Header Title
  const titleMap = {
    "ai-assistant": "AI Assistant Workspace",
    "my-tickets": "My Support Tickets",
    "saved-answers": "Saved Policy Answers",
    "help-support": "Help & Support Center",
    "admin-overview": "HR Operations Overview",
    "admin-tickets": "Escalation Ticket Queue",
    "admin-docs": "HR Approved Document Library",
    "admin-indexing": "RAG Knowledge Base & Index Health",
    "admin-activity": "System Activity Log",
    "access-denied": "Restricted Access (403)"
  };
  document.getElementById("active-view-title").textContent = titleMap[viewId] || "HR Knowledge";
  toggleMobileSidebar(false);
  refreshIcons();
}

/* ==========================================================================
   SCREEN 2: EMPLOYEE AI ASSISTANT CHAT & RAG ENGINE
   ========================================================================== */

function askPresetQuestion(type) {
  const input = document.getElementById("chat-composer-input");
  if (type === "hybrid") input.value = "What is our hybrid work policy?";
  else if (type === "leave") input.value = "How many annual leave days do I have?";
  else if (type === "probation") input.value = "What is the probation review process?";
  else if (type === "solar") input.value = "Does the company reimburse home solar panel installation?";

  submitEmployeeQuestion();
}

function submitEmployeeQuestion() {
  const input = document.getElementById("chat-composer-input");
  const query = input.value.trim();
  if (!query) return;

  input.value = "";

  // Hide Empty State
  const emptyState = document.getElementById("chat-empty-state");
  if (emptyState) emptyState.style.display = "none";

  // Append User Bubble
  appendChatMessage("user", query);

  // Show Multi-Step Thinking Indicator
  const thinkingId = "thinking-" + Date.now();
  showThinkingIndicator(thinkingId);

  // Simulate RAG Engine Latency & Thinking Steps
  simulateThinkingSteps(thinkingId, () => {
    removeThinkingIndicator(thinkingId);
    processRAGAnswer(query);
  });
}

function showThinkingIndicator(id) {
  const container = document.getElementById("chat-messages-container");
  const div = document.createElement("div");
  div.id = id;
  div.className = "chat-msg";
  div.innerHTML = `
    <div class="user-avatar" style="background: var(--primary-blue);"><i data-lucide="bot"></i></div>
    <div class="thinking-box">
      <div class="thinking-step active" id="${id}-step1"><i data-lucide="loader-2" class="spin"></i> 1. Understanding your question</div>
      <div class="thinking-step" id="${id}-step2">2. Searching approved HR documents</div>
      <div class="thinking-step" id="${id}-step3">3. Comparing policy versions</div>
      <div class="thinking-step" id="${id}-step4">4. Verifying evidence</div>
      <div class="thinking-step" id="${id}-step5">5. Preparing grounded answer</div>
    </div>
  `;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  refreshIcons();
}

function simulateThinkingSteps(id, callback) {
  setTimeout(() => {
    const s1 = document.getElementById(`${id}-step1`);
    if (s1) { s1.classList.remove("active"); s1.classList.add("done"); }
    const s2 = document.getElementById(`${id}-step2`);
    if (s2) s2.classList.add("active");
  }, 400);

  setTimeout(() => {
    const s2 = document.getElementById(`${id}-step2`);
    if (s2) { s2.classList.remove("active"); s2.classList.add("done"); }
    const s3 = document.getElementById(`${id}-step3`);
    if (s3) s3.classList.add("active");
  }, 800);

  setTimeout(() => {
    const s3 = document.getElementById(`${id}-step3`);
    if (s3) { s3.classList.remove("active"); s3.classList.add("done"); }
    const s4 = document.getElementById(`${id}-step4`);
    if (s4) s4.classList.add("active");
  }, 1200);

  setTimeout(() => {
    const s4 = document.getElementById(`${id}-step4`);
    if (s4) { s4.classList.remove("active"); s4.classList.add("done"); }
    const s5 = document.getElementById(`${id}-step5`);
    if (s5) s5.classList.add("active");
  }, 1600);

  setTimeout(callback, 2000);
}

function removeThinkingIndicator(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

function appendChatMessage(sender, text, confidenceData = null) {
  const container = document.getElementById("chat-messages-container");
  const msgDiv = document.createElement("div");
  msgDiv.className = `chat-msg ${sender}`;

  if (sender === "user") {
    msgDiv.innerHTML = `
      <div class="user-avatar">AR</div>
      <div class="msg-bubble">${escapeHTML(text)}</div>
    `;
  } else {
    // AI Response Card
    let contentHTML = "";

    if (confidenceData && confidenceData.confidence >= 80) {
      // High Confidence Verified Answer State
      contentHTML = `
        <div style="display: flex; gap: 8px; margin-bottom: 8px; align-items: center;">
          <span class="badge badge-verified"><i data-lucide="check-circle-2"></i> Verified answer</span>
          <span class="badge badge-verified">${confidenceData.confidence}% — High confidence</span>
        </div>

        <div class="answer-copy">${formatAnswerText(confidenceData.answer)}</div>

        <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 10px; display: flex; gap: 14px;">
          <span>Response time: ${confidenceData.responseTime}</span>
          <span>Request ID: ${confidenceData.requestId}</span>
        </div>

        ${confidenceData.citations.map(c => `
          <div class="citation-card" onclick="inspectCitationSource('${c.title}', '${c.section}', '${c.page}', '${c.version}', '${c.effectiveDate}', '${escapeHTML(c.excerpt)}')">
            <div>
              <strong style="color: var(--primary-blue); font-size: 0.85rem;">${c.title}</strong>
              <div style="font-size: 0.78rem; color: var(--text-muted);">${c.section} • ${c.page} • v${c.version} (Effective: ${c.effectiveDate})</div>
            </div>
            <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 0.78rem;">View source ➔</button>
          </div>
        `).join('')}

        <div style="margin-top: 12px; display: flex; gap: 8px; border-top: 1px solid var(--border-subtle); padding-top: 10px;">
          <button class="btn btn-secondary" style="padding: 4px 8px; font-size: 0.75rem;" onclick="showToast('Feedback submitted: Helpful', 'success')"><i data-lucide="thumbs-up"></i> Helpful</button>
          <button class="btn btn-secondary" style="padding: 4px 8px; font-size: 0.75rem;" onclick="showToast('Feedback submitted.', 'info')"><i data-lucide="thumbs-down"></i> Not helpful</button>
          <button class="btn btn-secondary" style="padding: 4px 8px; font-size: 0.75rem;" onclick="showToast('Copied to clipboard.', 'info')"><i data-lucide="copy"></i> Copy</button>
          <button class="btn btn-secondary" style="padding: 4px 8px; font-size: 0.75rem;" onclick="showToast('Answer saved to your library.', 'success')"><i data-lucide="bookmark"></i> Save</button>
        </div>
      `;
    } else {
      // Low Confidence Warning & Escalation Card State
      contentHTML = `
        <div style="display: flex; gap: 8px; margin-bottom: 8px; align-items: center;">
          <span class="badge badge-warning"><i data-lucide="alert-triangle"></i> I couldn't verify this confidently</span>
          <span class="badge badge-warning">${confidenceData.confidence}% — Low confidence</span>
        </div>

        <div style="color: var(--text-body); margin-bottom: 12px;">${confidenceData.explanation}</div>

        <div style="background: var(--amber-bg); border: 1px solid var(--amber-border); padding: 12px; border-radius: var(--radius-md); font-size: 0.82rem; color: #78350F; margin-bottom: 14px;">
          <strong>What would you like to do?</strong><br>
          You can automatically escalate this query into an HR support ticket for manual review by our HR Operations team.
        </div>

        <div style="display: flex; gap: 10px;">
          <button class="btn btn-primary" onclick="openEscalationModal()"><i data-lucide="ticket"></i> Create HR support ticket</button>
          <button class="btn btn-secondary" onclick="askPresetQuestion('hybrid')">Try another question</button>
        </div>
      `;
    }

    msgDiv.innerHTML = `
      <div class="user-avatar" style="background: var(--primary-blue);"><i data-lucide="bot"></i></div>
      <div class="msg-bubble">${contentHTML}</div>
    `;
  }

  container.appendChild(msgDiv);
  container.scrollTop = container.scrollHeight;
  refreshIcons();
}

function processRAGAnswer(query) {
  const qLower = query.toLowerCase();

  if (qLower.includes("hybrid")) {
    const res = window.MOCK_DATA.ragResponses["hybrid"];
    appendChatMessage("bot", null, res);
    inspectCitationSource(res.citations[0].title, res.citations[0].section, res.citations[0].page, res.citations[0].version, res.citations[0].effectiveDate, res.citations[0].excerpt);
  } else if (qLower.includes("solar")) {
    if (isSolarPolicyIndexed) {
      const res = window.MOCK_DATA.ragResponses["solar_reindexed"];
      appendChatMessage("bot", null, res);
      inspectCitationSource(res.citations[0].title, res.citations[0].section, res.citations[0].page, res.citations[0].version, res.citations[0].effectiveDate, res.citations[0].excerpt);
    } else {
      const res = window.MOCK_DATA.ragResponses["solar_low"];
      appendChatMessage("bot", null, res);
    }
  } else {
    // Default Fallback Response
    appendChatMessage("bot", null, {
      confidence: 91,
      answer: `Dựa trên tài liệu HR được phê duyệt năm 2026, câu hỏi "${escapeHTML(query)}" đã được xác minh thành công với độ tin cậy 91%.`,
      responseTime: "1.1s",
      requestId: "REQ-89412",
      citations: [
        {
          title: "[1] General HR Guidelines 2026",
          section: "Section 1.1",
          page: "Page 2",
          version: "2.0",
          effectiveDate: "01 Jan 2026",
          excerpt: "General guidelines apply across all full-time employees."
        }
      ]
    });
  }
}

/* Right Source Inspection Drawer */
function inspectCitationSource(title, section, page, version, effDate, excerpt) {
  const body = document.getElementById("source-drawer-body");
  body.innerHTML = `
    <div style="display: flex; justify-content: space-between; align-items: center;">
      <span class="badge badge-verified">Active Policy</span>
      <span style="font-size: 0.75rem; color: var(--text-muted);">v${version}</span>
    </div>

    <h4 style="font-size: 1rem; font-weight: 700; color: var(--primary-blue); margin-top: 6px;">${title}</h4>

    <div style="font-size: 0.8rem; color: var(--text-muted); display: flex; flex-direction: column; gap: 4px;">
      <span><strong>Section:</strong> ${section}</span>
      <span><strong>Location:</strong> ${page}</span>
      <span><strong>Effective Date:</strong> ${effDate}</span>
    </div>

    <div style="margin-top: 10px;">
      <label style="font-size: 0.75rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">Supporting Excerpt:</label>
      <div class="highlight-excerpt" style="margin-top: 4px;">
        "${excerpt}"
      </div>
    </div>

    <div style="display: flex; gap: 8px; margin-top: 14px;">
      <button class="btn btn-secondary" style="flex: 1; padding: 6px; font-size: 0.78rem;"><i data-lucide="chevron-left"></i> Prev source</button>
      <button class="btn btn-secondary" style="flex: 1; padding: 6px; font-size: 0.78rem;">Next source <i data-lucide="chevron-right"></i></button>
    </div>

    <button class="btn btn-primary" style="margin-top: 12px; width: 100%; font-size: 0.82rem;" onclick="showToast('Opening original PDF in new viewer...', 'info')">
      <i data-lucide="external-link"></i> Open original document
    </button>
  `;
  document.getElementById("source-drawer").classList.add("source-open");
  refreshIcons();
}

function closeSourceDrawer() {
  document.getElementById("source-drawer").classList.remove("source-open");
  document.getElementById("source-drawer-body").innerHTML = `
    <p style="color: var(--text-muted); font-size: 0.85rem; text-align: center; margin-top: 40px;">
      Select a citation card in the chat to view the verified original document source excerpt.
    </p>
  `;
}

function openEscalationModal() {
  document.getElementById("escalation-modal").classList.add("active");
}

/* ==========================================================================
   EMPLOYEE MY TICKETS SCREEN
   ========================================================================== */

function renderMyTickets() {
  const tbody = document.getElementById("my-tickets-table-body");
  if (!tbody) return;

  tbody.innerHTML = currentTickets.map(t => `
    <tr>
      <td style="font-weight: 700; color: var(--primary-blue);">${t.id}</td>
      <td style="max-width: 280px; font-weight: 500;">${escapeHTML(t.question)}</td>
      <td>${t.category}</td>
      <td>${t.createdDate}</td>
      <td><span class="badge ${t.status === 'Resolved' ? 'badge-verified' : 'badge-warning'}">${t.status}</span></td>
      <td>${t.expectedResponse}</td>
      <td>
        <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 0.78rem;" onclick="openTicketDetailModal('${t.id}')">
          View Detail
        </button>
      </td>
    </tr>
  `).join('');
}

/* ==========================================================================
   HR ADMIN DASHBOARD & TICKET RESOLUTION
   ========================================================================== */

function renderAdminTickets() {
  const tbody = document.getElementById("admin-tickets-table-body");
  if (!tbody) return;

  tbody.innerHTML = currentTickets.map(t => `
    <tr>
      <td style="font-weight: 700; color: var(--primary-blue);">${t.id}</td>
      <td>${t.employee}</td>
      <td style="max-width: 220px;">${escapeHTML(t.question)}</td>
      <td>${t.category}</td>
      <td><span class="badge ${t.confidence >= 80 ? 'badge-verified' : 'badge-danger'}">${t.confidence}%</span></td>
      <td><span style="color: ${t.priority === 'High' ? 'var(--rose-danger)' : 'var(--amber-warning)'}; font-weight: 700;">${t.priority}</span></td>
      <td>${t.assignee}</td>
      <td><span style="font-family: monospace; color: var(--amber-warning); font-weight: 600;">${t.sla}</span></td>
      <td><span class="badge ${t.status === 'Resolved' ? 'badge-verified' : 'badge-warning'}">${t.status}</span></td>
      <td>
        <button class="btn btn-primary" style="padding: 4px 10px; font-size: 0.78rem;" onclick="openTicketDetailModal('${t.id}')">
          ${t.status === 'Resolved' ? 'View' : 'Resolve'}
        </button>
      </td>
    </tr>
  `).join('');
}

function openTicketDetailModal(ticketId) {
  document.getElementById("ticket-detail-modal").classList.add("active");
}

function confirmResolveTicket() {
  closeModal("ticket-detail-modal");

  const ticket = currentTickets.find(t => t.id === "HR-2048");
  if (ticket) {
    ticket.status = "Resolved";
    ticket.response = document.getElementById("hr-reply-text").value;
  }

  renderMyTickets();
  renderAdminTickets();

  showToast("✅ Ticket HR-2048 Resolved! Notification sent to Alex Rivera.", "success");

  // Sync resolution to Employee Chat
  appendChatMessage("bot", null, {
    confidence: 100,
    status: "HR Specialist Verified Answer",
    answer: `**HR Specialist response · Ticket HR-2048**<br>${escapeHTML(document.getElementById("hr-reply-text").value)}`,
    responseTime: "Manual",
    requestId: "TICKET-HR-2048",
    citations: []
  });
}

function renderAdminDocs() {
  const tbody = document.getElementById("admin-docs-table-body");
  if (!tbody) return;

  tbody.innerHTML = currentDocs.map(d => `
    <tr>
      <td style="font-weight: 700;">📄 ${d.name}</td>
      <td>${d.category}</td>
      <td>v${d.version}</td>
      <td>${d.effectiveDate}</td>
      <td>${d.owner}</td>
      <td><span class="badge badge-neutral">${d.fileType}</span></td>
      <td><span class="badge ${d.indexStatus === 'Indexed' ? 'badge-verified' : 'badge-warning'}">${d.indexStatus}</span></td>
      <td><span class="badge badge-verified">${d.status}</span></td>
    </tr>
  `).join('');
}

function filterAdminTickets(status) {
  if (status === "All") {
    currentTickets = [...window.MOCK_DATA.tickets];
  } else {
    currentTickets = window.MOCK_DATA.tickets.filter(t => t.status === status);
  }
  renderAdminTickets();
}

/* ==========================================================================
   DOCUMENT UPLOAD & KNOWLEDGE INDEXING PIPELINE
   ========================================================================== */

function openUploadModal() {
  document.getElementById("upload-modal").classList.add("active");
}

function startUploadPipeline() {
  const box = document.getElementById("indexing-pipeline-box");
  const bar = document.getElementById("pipeline-progress-bar");
  const text = document.getElementById("pipeline-status-text");

  box.style.display = "block";
  bar.style.width = "20%";
  text.textContent = "Pipeline: Uploading Home_Workplace_Solar_Reimbursement_Policy_2026.pdf (20%)...";

  setTimeout(() => {
    bar.style.width = "55%";
    text.textContent = "Pipeline: Extracting text & Splitting into chunks (55%)...";
  }, 1000);

  setTimeout(() => {
    bar.style.width = "85%";
    text.textContent = "Pipeline: Creating vector embeddings & Quality check (85%)...";
  }, 2000);

  setTimeout(() => {
    bar.style.width = "100%";
    text.textContent = "Pipeline: Fully Indexed & Stored in Vector Database (100%)!";

    const newDoc = {
      id: "doc-5",
      name: "Home_Workplace_Solar_Reimbursement_Policy_2026.pdf",
      category: "Benefits & Perks",
      version: "1.0",
      effectiveDate: "05 August 2026",
      owner: "HR Benefits Team",
      fileType: "PDF",
      size: "2.8 MB",
      indexStatus: "Indexed",
      lastIndexed: "Just now",
      status: "Active",
      chunks: 110
    };

    currentDocs.unshift(newDoc);
    renderAdminDocs();
    isSolarPolicyIndexed = true;

    showToast("🎉 Document uploaded & indexed into RAG Knowledge Base!", "success");

    setTimeout(() => {
      closeModal("upload-modal");
    }, 1200);
  }, 3000);
}

function triggerReindexModal() {
  const log = document.getElementById("indexing-activity-log");
  log.innerHTML += `<br>[${new Date().toLocaleTimeString()}] REINDEX_TRIGGERED: Initiating full RAG knowledge base rebuild...`;
  log.innerHTML += `<br>[${new Date().toLocaleTimeString()}] REINDEX_PROGRESS: Processing 43 documents (3,230 vector chunks)...`;

  showToast("⏳ Re-indexing Knowledge Base...", "info");

  setTimeout(() => {
    log.innerHTML += `<br>[${new Date().toLocaleTimeString()}] REINDEX_SUCCESS: Active index version updated to v4.9.0-prod (100% Healthy).`;
    isSolarPolicyIndexed = true;
    showToast("🎉 Knowledge Base Re-indexed Successfully! Retest queries on AI Assistant.", "success");
  }, 2000);
}

/* ==========================================================================
   UTILITY FUNCTIONS
   ========================================================================== */

function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) modal.classList.remove("active");
}

function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = "toast-item";
  if (type === "success") toast.style.borderLeft = "4px solid var(--emerald-verified)";
  if (type === "danger") toast.style.borderLeft = "4px solid var(--rose-danger)";
  if (type === "info") toast.style.borderLeft = "4px solid var(--primary-blue)";

  toast.innerHTML = `<span>${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transition = "opacity 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

function escapeHTML(str) {
  return str.replace(/[&<>'"]/g, 
    tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag)
  );
}

function formatAnswerText(text) {
  return String(text || "").replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
}
