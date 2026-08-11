/**
 * HR Document Intelligence Agent - Enterprise Application Logic (Vietnamese Edition)
 */

let currentUserRole = "Employee";
let activeView = "ai-assistant";
let isSolarPolicyIndexed = false;
let currentTickets = [...window.MOCK_DATA.tickets];
let currentDocs = [];
let activeConversationId = null;
let activeConversationState = "CREATING";
let activeChatRequestId = null;
let latestMonitoringRequestId = null;
let chatRequestInFlight = false;

function refreshIcons() {
  if (window.lucide && typeof window.lucide.createIcons === "function") {
    window.lucide.createIcons();
  }
}

document.addEventListener("DOMContentLoaded", () => {
  renderMyTickets();
  renderAdminTickets();
  renderAdminDocs();
  startNewConversation(false);

  document.getElementById("chat-messages-container")?.addEventListener("click", event => {
    const citation = event.target.closest("[data-citation-id]");
    if (citation) inspectCitationSource(citation.dataset.citationId);

    const feedbackButton = event.target.closest("[data-feedback-rating]");
    if (feedbackButton) handleFeedback(feedbackButton.dataset.messageId, feedbackButton.dataset.feedbackRating);

    const clarificationButton = event.target.closest("[data-clarification-option]");
    if (clarificationButton) submitClarification(clarificationButton.dataset.clarificationOption);

    const retryButton = event.target.closest("[data-retry-request]");
    if (retryButton) retryChatRequest(retryButton.dataset.retryRequest);
  });

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
    showToast("✅ Xác thực thành công! Bạn đã đăng nhập với quyền " + (currentUserRole === "HR Admin" ? "Quản trị viên HR" : "Nhân viên"), "success");
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
  showToast("✅ Đăng nhập Đơn điểm SSO thành công!", "success");
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
  document.getElementById("sidebar-user-role").textContent = newRole === "HR Admin" ? "Quản trị viên HR" : "Nhân viên";
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

  // Update Header Title Map in Vietnamese
  const titleMap = {
    "ai-assistant": "Không gian Trợ lý AI HR",
    "my-tickets": "Danh sách Ticket Hỗ trợ của Tôi",
    "saved-answers": "Câu trả lời đã lưu",
    "help-support": "Trung tâm Trợ giúp & Hỗ trợ",
    "admin-overview": "Tổng quan Vận hành HR",
    "admin-tickets": "Hàng đợi Ticket Cần Xử lý",
    "admin-docs": "Kho Tài liệu Chính sách HR",
    "admin-indexing": "Kho Tri thức RAG & Sức khỏe Index",
    "admin-evaluation": "Đánh giá Chất lượng RAG",
    "admin-monitoring": "Giám sát Truy vấn",
    "admin-activity": "Nhật ký Hoạt động Hệ thống",
    "access-denied": "Truy cập bị Hạn chế (403)"
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
  if (type === "hybrid") input.value = "Quy định làm việc hybrid của công ty như thế nào?";
  else if (type === "leave") input.value = "Tôi có bao nhiêu ngày phép năm có hưởng lương?";
  else if (type === "probation") input.value = "Quy trình đánh giá thời gian thử việc ra sao?";
  else if (type === "solar") input.value = "Công ty có hỗ trợ chi phí lắp pin năng lượng mặt trời không?";

  updateQuestionCount();
  submitEmployeeQuestion();
}

async function startNewConversation(showNotice = true) {
  if (chatRequestInFlight) return;
  const response = await window.HR_API.createConversation(null);
  if (!handleApiResponse(response)) return;

  activeConversationId = response.data.conversation_id;
  activeConversationState = response.data.state;
  activeChatRequestId = null;
  const container = document.getElementById("chat-messages-container");
  container.innerHTML = buildChatEmptyState();
  updateConversationHeader();
  setComposerEnabled(true);
  closeSourceDrawer();
  if (showNotice) showToast("Đã bắt đầu cuộc trò chuyện mới.", "success");
  refreshIcons();
}

async function reloadConversation() {
  if (!activeConversationId) return;
  const response = await window.HR_API.getConversationMessages(activeConversationId);
  if (!handleApiResponse(response)) return;

  const container = document.getElementById("chat-messages-container");
  container.innerHTML = "";
  if (!response.data.messages.length) {
    container.innerHTML = buildChatEmptyState();
  } else {
    response.data.messages.forEach(message => {
      if (message.role === "USER") appendChatMessage("user", message.content);
      else renderChatResult({
        chat_request_id: message.chat_request_id,
        assistant_message_id: message.message_id,
        state: message.state || "COMPLETED",
        answer_status: message.answer_status,
        answer: message.answer_status === "CLARIFICATION_REQUIRED" ? null : message.content,
        citations: message.citations || [],
        warnings: message.warnings || [],
        clarification: message.clarification || null,
        failure: message.failure || null,
        latency_ms: null
      });
    });
  }
  showToast("Đã tải lại lịch sử cuộc trò chuyện.", "info");
  refreshIcons();
}

async function endCurrentConversation() {
  if (!activeConversationId || activeConversationState === "ENDED") return;
  const response = await window.HR_API.endConversation(activeConversationId);
  if (!handleApiResponse(response)) return;
  activeConversationState = response.data.state;
  updateConversationHeader();
  setComposerEnabled(false);
  showToast("Cuộc trò chuyện đã kết thúc. Nhấn 'Chat mới' để tiếp tục.", "info");
}

function updateConversationHeader() {
  const state = document.getElementById("conversation-state");
  state.textContent = activeConversationState === "ACTIVE" ? "ĐANG HOẠT ĐỘNG" : "ĐÃ KẾT THÚC";
  state.className = `badge ${activeConversationState === "ACTIVE" ? "badge-verified" : "badge-neutral"}`;
  document.getElementById("conversation-id").textContent = activeConversationId || "Đang tạo…";
}

function setComposerEnabled(enabled) {
  document.getElementById("chat-composer-input").disabled = !enabled;
  document.getElementById("chat-send-button").disabled = !enabled;
}

function updateQuestionCount() {
  const length = document.getElementById("chat-composer-input").value.length;
  document.getElementById("question-count").textContent = `${length.toLocaleString()} / 2,000`;
}

async function submitEmployeeQuestion(questionOverride = null) {
  const input = document.getElementById("chat-composer-input");
  const query = String(questionOverride || input.value).trim();
  if (!query || chatRequestInFlight) return;
  if (!activeConversationId || activeConversationState !== "ACTIVE") {
    showToast("Vui lòng bắt đầu cuộc trò chuyện mới trước khi đặt câu hỏi.", "danger");
    return;
  }

  input.value = "";
  updateQuestionCount();
  chatRequestInFlight = true;
  setComposerEnabled(false);

  const emptyState = document.getElementById("chat-empty-state");
  if (emptyState) emptyState.style.display = "none";
  appendChatMessage("user", query);

  const thinkingId = "thinking-" + Date.now();
  showThinkingIndicator(thinkingId);

  const createResponse = await window.HR_API.createChatRequest(activeConversationId, query);
  if (!handleApiResponse(createResponse)) {
    removeThinkingIndicator(thinkingId);
    chatRequestInFlight = false;
    setComposerEnabled(true);
    return;
  }

  activeChatRequestId = createResponse.data.chat_request_id;
  await pollChatRequest(activeChatRequestId, thinkingId);
  chatRequestInFlight = false;
  setComposerEnabled(activeConversationState === "ACTIVE");
}

function showThinkingIndicator(id) {
  const container = document.getElementById("chat-messages-container");
  const div = document.createElement("div");
  div.id = id;
  div.className = "chat-msg";
  div.innerHTML = `
    <div class="user-avatar" style="background: var(--primary-blue);"><i data-lucide="bot"></i></div>
    <div class="thinking-box">
      <div class="thinking-step active" id="${id}-step1"><i data-lucide="loader-2" class="spin"></i> 1. Đang phân tích yêu cầu & ý định</div>
      <div class="thinking-step" id="${id}-step2">2. Tìm kiếm trong các văn bản chính sách HR</div>
      <div class="thinking-step" id="${id}-step3">3. Phân tích & so sánh các phiên bản quy định</div>
      <div class="thinking-step" id="${id}-step4">4. Kiểm chứng bằng chứng đối soát</div>
      <div class="thinking-step" id="${id}-step5">5. Tổng hợp câu trả lời có căn cứ</div>
    </div>
  `;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  refreshIcons();
}

async function pollChatRequest(chatRequestId, thinkingId) {
  let complete = false;
  while (!complete) {
    await delay(350);
    const response = await window.HR_API.getChatRequest(chatRequestId);
    if (!handleApiResponse(response)) {
      removeThinkingIndicator(thinkingId);
      return;
    }

    updateThinkingIndicator(thinkingId, response.data.state);
    complete = ["COMPLETED", "REFUSED", "CLARIFICATION_REQUIRED", "FAILED"].includes(response.data.state);
    if (complete) {
      removeThinkingIndicator(thinkingId);
      latestMonitoringRequestId = response.request_id;
      renderChatResult(response.data);
    }
  }
}

function updateThinkingIndicator(id, state) {
  const stateToStep = { QUEUED: 1, RETRIEVING: 2, GENERATING: 5 };
  const activeStep = stateToStep[state] || 5;
  for (let index = 1; index <= 5; index += 1) {
    const step = document.getElementById(`${id}-step${index}`);
    if (!step) continue;
    step.classList.toggle("done", index < activeStep);
    step.classList.toggle("active", index === activeStep);
  }
}

function removeThinkingIndicator(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

function appendChatMessage(sender, text) {
  const container = document.getElementById("chat-messages-container");
  const msgDiv = document.createElement("div");
  msgDiv.className = `chat-msg ${sender}`;

  if (sender === "user") {
    msgDiv.innerHTML = `
      <div class="user-avatar">AR</div>
      <div class="msg-bubble">${escapeHTML(text)}</div>
    `;
  }

  container.appendChild(msgDiv);
  container.scrollTop = container.scrollHeight;
  refreshIcons();
}

function renderChatResult(result) {
  const container = document.getElementById("chat-messages-container");
  const msgDiv = document.createElement("div");
  msgDiv.className = "chat-msg bot";

  const warnings = (result.warnings || []).map(warning => `
    <div class="answer-warning ${warning.severity === "BLOCKING" ? "blocking" : ""}">
      <i data-lucide="triangle-alert"></i><div><strong>${escapeHTML(warning.type.replaceAll("_", " "))}</strong><span>${escapeHTML(warning.message)}</span></div>
    </div>
  `).join("");

  let content = "";
  if (result.state === "COMPLETED") {
    const citations = (result.citations || []).map(citation => `
      <button type="button" class="citation-card" data-citation-id="${escapeHTML(citation.citation_id)}">
        <div><strong>${escapeHTML(citation.title)}</strong><span>${escapeHTML(citation.section || "Không rõ phần")} · ${citation.page ? `Trang ${citation.page}` : "Trang —"} · v${escapeHTML(citation.version || "—")} · ${escapeHTML(citation.effective_date || "Chưa có ngày hiệu lực")}</span></div>
        <span class="btn btn-secondary btn-compact">Đối soát nguồn <i data-lucide="arrow-right"></i></span>
      </button>
    `).join("");
    const statusText = result.answer_status === "ANSWERED" ? "Đã đối soát" : escapeHTML(result.answer_status);
    content = `
      <div class="answer-heading"><span class="badge badge-verified"><i data-lucide="badge-check"></i> ${statusText}</span><span>${result.latency_ms ? `${result.latency_ms} ms` : "Đã khôi phục"}</span></div>
      <div class="answer-copy">${formatAnswerText(result.answer)}</div>
      ${warnings}${citations}
      <div class="answer-actions">
        <button class="btn btn-secondary btn-compact" data-feedback-rating="UP" data-message-id="${escapeHTML(result.assistant_message_id)}"><i data-lucide="thumbs-up"></i> Hữu ích</button>
        <button class="btn btn-secondary btn-compact" data-feedback-rating="DOWN" data-message-id="${escapeHTML(result.assistant_message_id)}"><i data-lucide="thumbs-down"></i> Chưa hài lòng</button>
      </div>`;
  } else if (result.state === "REFUSED") {
    const statusText = "Chưa thể xác minh";
    content = `<div class="answer-heading"><span class="badge badge-warning"><i data-lucide="shield-alert"></i> ${statusText}</span></div><div class="answer-copy">${formatAnswerText(result.answer)}</div>${warnings}<div class="answer-actions"><button class="btn btn-primary btn-compact" onclick="openEscalationModal()"><i data-lucide="ticket"></i> Gửi Chuyên viên HR</button></div>`;
  } else if (result.state === "CLARIFICATION_REQUIRED") {
    const options = result.clarification.options.map(option => `<button class="btn btn-secondary" data-clarification-option="${escapeHTML(option)}">${escapeHTML(option)}</button>`).join("");
    content = `<div class="answer-heading"><span class="badge badge-warning"><i data-lucide="message-circle-question"></i> Cần làm rõ thêm</span></div><div class="answer-copy">${escapeHTML(result.clarification.question)}</div><div class="clarification-options">${options}</div>`;
  } else {
    const canRetry = Boolean(result.failure?.retryable);
    content = `<div class="answer-heading"><span class="badge badge-danger"><i data-lucide="circle-x"></i> Yêu cầu thất bại</span></div><div class="answer-copy">${escapeHTML(result.failure?.message || "Đã xảy ra lỗi không xác định.")}</div>${canRetry ? `<div class="answer-actions"><button class="btn btn-primary btn-compact" data-retry-request="${escapeHTML(result.chat_request_id)}"><i data-lucide="rotate-ccw"></i> Thử lại</button></div>` : ""}`;
  }

  msgDiv.innerHTML = `<div class="user-avatar bot-avatar"><i data-lucide="bot"></i></div><div class="msg-bubble">${content}</div>`;
  container.appendChild(msgDiv);
  container.scrollTop = container.scrollHeight;
  refreshIcons();
}

async function retryChatRequest(chatRequestId) {
  if (chatRequestInFlight) return;
  chatRequestInFlight = true;
  setComposerEnabled(false);
  const thinkingId = "thinking-" + Date.now();
  showThinkingIndicator(thinkingId);
  const response = await window.HR_API.retryChatRequest(chatRequestId);
  if (!handleApiResponse(response)) {
    removeThinkingIndicator(thinkingId);
    chatRequestInFlight = false;
    setComposerEnabled(true);
    return;
  }
  activeChatRequestId = response.data.chat_request_id;
  await pollChatRequest(activeChatRequestId, thinkingId);
  chatRequestInFlight = false;
  setComposerEnabled(true);
}

function submitClarification(option) {
  submitEmployeeQuestion(`Quy trình đánh giá thử việc — ${option}`);
}

async function inspectCitationSource(citationId) {
  const response = await window.HR_API.getCitation(citationId);
  if (!handleApiResponse(response)) return;
  const citation = response.data;
  const body = document.getElementById("source-drawer-body");
  body.innerHTML = `
    <div style="display: flex; justify-content: space-between; align-items: center;">
      <span class="badge ${citation.document.status === "ACTIVE" ? "badge-verified" : "badge-warning"}">${citation.document.status === "ACTIVE" ? "Hoạt động" : escapeHTML(citation.document.status)}</span>
      <span style="font-size: 0.75rem; color: var(--text-muted);">v${escapeHTML(citation.document.version || "—")}</span>
    </div>

    <h4 style="font-size: 1rem; font-weight: 700; color: var(--primary-blue); margin-top: 8px;">${escapeHTML(citation.document.title)}</h4>

    <div style="font-size: 0.8rem; color: var(--text-muted); display: flex; flex-direction: column; gap: 4px; margin-top: 8px;">
      <span><strong>Mục/Phần:</strong> ${escapeHTML(citation.location.section || "Không có")}</span>
      <span><strong>Trang:</strong> ${citation.location.page ? `Trang ${citation.location.page}` : "Không có"}</span>
      <span><strong>Ngày hiệu lực:</strong> ${escapeHTML(citation.document.effective_date || "Không có")}</span>
      <span><strong>Mã Chunk:</strong> <code>${escapeHTML(citation.location.chunk_id)}</code></span>
    </div>

    <div style="margin-top: 14px;">
      <label style="font-size: 0.75rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">Đoạn văn bản trích dẫn nguồn:</label>
      <div class="highlight-excerpt" style="margin-top: 6px;">“${escapeHTML(citation.excerpt)}”</div>
    </div>
    ${citation.conflict_warning ? `<div class="answer-warning"><i data-lucide="triangle-alert"></i><div><strong>Cảnh báo mâu thuẫn</strong><span>Nguồn tài liệu này có xung đột với một tài liệu quy định khác.</span></div></div>` : ""}
  `;
  document.getElementById("source-drawer").classList.add("source-open");
  refreshIcons();
}

function closeSourceDrawer() {
  document.getElementById("source-drawer").classList.remove("source-open");
  document.getElementById("source-drawer-body").innerHTML = `
    <p style="color: var(--text-muted); font-size: 0.85rem; text-align: center; margin-top: 40px;">
      Chọn một thẻ trích dẫn trong ô chat để xem chi tiết đoạn văn bản nguồn đã đối soát.
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

  const statusTextMap = { "New": "Mới", "In review": "Đang xử lý", "Resolved": "Đã hoàn thành" };
  tbody.innerHTML = currentTickets.map(t => `
    <tr>
      <td style="font-weight: 700; color: var(--primary-blue);">${t.id}</td>
      <td style="max-width: 280px; font-weight: 500;">${escapeHTML(t.question)}</td>
      <td>${t.category}</td>
      <td>${t.createdDate}</td>
      <td><span class="badge ${t.status === 'Resolved' ? 'badge-verified' : 'badge-warning'}">${statusTextMap[t.status] || t.status}</span></td>
      <td>${t.expectedResponse}</td>
      <td>
        <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 0.78rem;" onclick="openTicketDetailModal('${t.id}')">
          Xem chi tiết
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

  const statusTextMap = { "New": "Mới", "In review": "Đang xử lý", "Resolved": "Đã hoàn thành" };
  tbody.innerHTML = currentTickets.map(t => `
    <tr>
      <td style="font-weight: 700; color: var(--primary-blue);">${t.id}</td>
      <td>${t.employee}</td>
      <td style="max-width: 220px;">${escapeHTML(t.question)}</td>
      <td>${t.category}</td>
      <td><span class="badge ${t.confidence >= 80 ? 'badge-verified' : 'badge-danger'}">${t.confidence}%</span></td>
      <td><span style="color: ${t.priority === 'High' || t.priority === 'Cao' ? 'var(--rose-danger)' : 'var(--amber-warning)'}; font-weight: 700;">${t.priority}</span></td>
      <td>${t.assignee}</td>
      <td><span style="font-family: monospace; color: var(--amber-warning); font-weight: 600;">${t.sla}</span></td>
      <td><span class="badge ${t.status === 'Resolved' ? 'badge-verified' : 'badge-warning'}">${statusTextMap[t.status] || t.status}</span></td>
      <td>
        <button class="btn btn-primary" style="padding: 4px 10px; font-size: 0.78rem;" onclick="openTicketDetailModal('${t.id}')">
          ${t.status === 'Resolved' ? 'Xem' : 'Xử lý'}
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

  showToast("✅ Ticket HR-2048 Đã giải quyết! Thông báo đã gửi tới Alex Rivera.", "success");

  renderChatResult({
    chat_request_id: "ticket_HR_2048",
    assistant_message_id: "ticket_message_HR_2048",
    state: "COMPLETED",
    answer_status: "ANSWERED",
    answer: `**Phản hồi từ Chuyên viên HR · Ticket HR-2048**\n${document.getElementById("hr-reply-text").value}`,
    latency_ms: null,
    citations: [],
    warnings: []
  });
}

async function renderAdminDocs() {
  const tbody = document.getElementById("admin-docs-table-body");
  if (!tbody) return;
  const category = document.getElementById("document-category-filter")?.value || "";
  const status = document.getElementById("document-status-filter")?.value || "";
  const indexed = document.getElementById("document-index-filter")?.value || "";
  const response = await window.HR_API.listDocuments({ category, status, indexed });
  if (!handleApiResponse(response, false)) return;
  currentDocs = response.data.documents;

  tbody.innerHTML = currentDocs.length ? currentDocs.map(d => `
    <tr>
      <td><strong>${escapeHTML(d.title)}</strong><small class="table-subtext">${escapeHTML(d.source_file)}</small></td>
      <td>${escapeHTML(d.category || "—")}</td>
      <td>v${escapeHTML(d.version || "—")}</td>
      <td>${escapeHTML(d.effective_date || "—")}</td>
      <td><span class="badge ${d.ingestion.state === "COMPLETED" ? "badge-verified" : d.ingestion.state === "FAILED" ? "badge-danger" : "badge-warning"}">${d.ingestion.state === "COMPLETED" ? "ĐÀ HOÀN TẤT" : escapeHTML(d.ingestion.state)}</span></td>
      <td><span class="badge ${d.index.indexed ? "badge-verified" : "badge-warning"}">${d.index.indexed ? "ĐÃ INDEX" : "CHƯA INDEX"}</span></td>
      <td><span class="badge ${d.status === "ACTIVE" ? "badge-verified" : "badge-neutral"}">${d.status === "ACTIVE" ? "HOẠT ĐỘNG" : escapeHTML(d.status)}</span></td>
      <td><button class="btn btn-secondary btn-compact" onclick="openDocumentDetail('${escapeHTML(d.document_id)}')">Xem / sửa</button></td>
    </tr>
  `).join("") : `<tr><td colspan="8"><div class="table-empty">Không có tài liệu nào phù hợp với bộ lọc.</div></td></tr>`;
  refreshIcons();
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

function syncUploadTitle() {
  const file = document.getElementById("upload-doc-file").files[0];
  if (!file) return;
  document.getElementById("upload-doc-title").value = file.name.replace(/\.[^.]+$/, "").replaceAll("_", " ");
}

async function startUploadPipeline() {
  const file = document.getElementById("upload-doc-file").files[0];
  const box = document.getElementById("indexing-pipeline-box");
  const bar = document.getElementById("pipeline-progress-bar");
  const text = document.getElementById("pipeline-status-text");
  const button = document.getElementById("upload-submit-button");
  const metadata = {
    title: document.getElementById("upload-doc-title").value.trim(),
    category: document.getElementById("upload-doc-category").value.trim(),
    version: document.getElementById("upload-doc-version").value.trim(),
    effective_date: document.getElementById("upload-doc-effective-date").value || null,
    status: document.getElementById("upload-doc-status").value,
    language: document.getElementById("upload-doc-language").value,
    confidentiality: document.getElementById("upload-doc-confidentiality").value
  };

  button.disabled = true;
  const response = await window.HR_API.uploadDocument(file, metadata);
  if (!handleApiResponse(response)) {
    button.disabled = false;
    return;
  }

  box.style.display = "block";
  bar.style.width = "10%";
  text.textContent = `ĐANG XẾP HÀNG · ${response.data.ingestion_job_id}`;
  let complete = false;
  while (!complete) {
    await delay(350);
    const jobResponse = await window.HR_API.getIngestionJob(response.data.ingestion_job_id);
    if (!handleApiResponse(jobResponse)) break;
    const job = jobResponse.data;
    bar.style.width = `${job.progress_percent}%`;
    text.textContent = `Tiến trình: ${job.stage} · ${job.progress_percent}%`;
    complete = ["COMPLETED", "FAILED"].includes(job.state);
  }

  button.disabled = false;
  await renderAdminDocs();
  if (complete) {
    showToast("Tải lên tài liệu và chạy Index thành công.", "success");
    setTimeout(() => closeModal("upload-modal"), 700);
  }
}

async function triggerReindexModal() {
  const log = document.getElementById("indexing-activity-log");
  const statusCard = document.getElementById("index-job-status");
  const progress = document.getElementById("index-job-progress");
  const label = document.getElementById("index-job-label");
  const button = document.getElementById("reindex-button");
  const strategy = document.getElementById("index-strategy").value;
  button.disabled = true;

  const response = await window.HR_API.startIndexRebuild([], strategy);
  if (!handleApiResponse(response)) {
    button.disabled = false;
    return;
  }
  statusCard.style.display = "block";
  document.getElementById("index-job-id").textContent = response.data.job_id;
  progress.style.width = "0%";
  label.textContent = "Đã đưa tiến trình Re-index vào hàng đợi";
  log.innerHTML += `<br>[${new Date().toLocaleTimeString()}] ${escapeHTML(response.data.job_id)} · ĐANG XẾP HÀNG · ${escapeHTML(strategy)}`;

  let complete = false;
  while (!complete) {
    await delay(400);
    const jobResponse = await window.HR_API.getIndexRebuild(response.data.job_id);
    if (!handleApiResponse(jobResponse)) break;
    const job = jobResponse.data;
    progress.style.width = `${job.progress_percent}%`;
    label.textContent = `Tiến trình Re-index · ${job.progress_percent}%`;
    complete = ["COMPLETED", "FAILED"].includes(job.state);
  }
  button.disabled = false;
  if (complete) {
    log.innerHTML += `<br>[${new Date().toLocaleTimeString()}] ${escapeHTML(response.data.job_id)} · ĐÃ HOÀN TẤT`;
    showToast("Đã xây dựng lại Index Kho Tri thức thành công.", "success");
    renderAdminDocs();
  }
}

async function openDocumentDetail(documentId) {
  const response = await window.HR_API.getDocument(documentId);
  if (!handleApiResponse(response)) return;
  const item = response.data;
  document.getElementById("document-detail-id").value = item.document_id;
  document.getElementById("document-detail-heading").textContent = item.title;
  document.getElementById("document-detail-title").value = item.title || "";
  document.getElementById("document-detail-category").value = item.category || "";
  document.getElementById("document-detail-version").value = item.version || "";
  document.getElementById("document-detail-effective-date").value = item.effective_date || "";
  document.getElementById("document-detail-status").value = item.status;
  document.getElementById("document-detail-language").value = item.language || "vi";
  document.getElementById("document-detail-confidentiality").value = item.confidentiality || "INTERNAL";
  document.getElementById("document-archive-button").disabled = item.status === "ARCHIVED";
  document.getElementById("document-processing-summary").innerHTML = `
    <div><span>Tệp nguồn</span><strong>${escapeHTML(item.source_file)}</strong></div>
    <div><span>Tiến trình nạp</span><strong>${escapeHTML(item.ingestion.state)} · ${item.ingestion.chunk_count} đoạn</strong></div>
    <div><span>Index</span><strong>${item.index.indexed ? escapeHTML(item.index.index_version) : "Cần Re-index"}</strong></div>
    <div><span>Mã Checksum</span><code>${escapeHTML(item.checksum)}</code></div>`;
  document.getElementById("document-detail-modal").classList.add("active");
  refreshIcons();
}

async function saveDocumentMetadata() {
  const documentId = document.getElementById("document-detail-id").value;
  const metadata = {
    title: document.getElementById("document-detail-title").value.trim(),
    category: document.getElementById("document-detail-category").value.trim(),
    version: document.getElementById("document-detail-version").value.trim() || null,
    effective_date: document.getElementById("document-detail-effective-date").value || null,
    status: document.getElementById("document-detail-status").value,
    language: document.getElementById("document-detail-language").value,
    confidentiality: document.getElementById("document-detail-confidentiality").value
  };
  const response = await window.HR_API.updateDocumentMetadata(documentId, metadata);
  if (!handleApiResponse(response)) return;
  closeModal("document-detail-modal");
  await renderAdminDocs();
  showToast("Thông tin tài liệu đã cập nhật. Cần chạy Re-index.", "success");
}

async function archiveCurrentDocument() {
  const documentId = document.getElementById("document-detail-id").value;
  if (!window.confirm("Lưu trữ tài liệu này? Tài liệu sẽ bị loại khỏi kho index mặc định.")) return;
  const response = await window.HR_API.archiveDocument(documentId);
  if (!handleApiResponse(response)) return;
  closeModal("document-detail-modal");
  await renderAdminDocs();
  showToast("Đã lưu trữ tài liệu. Cần chạy Re-index.", "info");
}

async function startEvaluationRun() {
  const button = document.getElementById("evaluation-run-button");
  const result = document.getElementById("evaluation-result");
  button.disabled = true;
  const response = await window.HR_API.startEvaluation(
    document.getElementById("evaluation-dataset").value.trim(),
    document.getElementById("evaluation-index").value.trim(),
    document.getElementById("evaluation-model").value.trim()
  );
  if (!handleApiResponse(response)) {
    button.disabled = false;
    return;
  }

  result.innerHTML = `<div class="api-loading"><i data-lucide="loader-2" class="spin"></i><div><strong>Đã xếp hàng phiên đánh giá</strong><span>${escapeHTML(response.data.run_id)}</span></div></div><div class="progress-track"><div class="progress-value" id="evaluation-progress"></div></div>`;
  refreshIcons();
  let complete = false;
  while (!complete) {
    await delay(450);
    const runResponse = await window.HR_API.getEvaluation(response.data.run_id);
    if (!handleApiResponse(runResponse)) break;
    const run = runResponse.data;
    const progress = document.getElementById("evaluation-progress");
    if (progress) progress.style.width = `${run.progress_percent || 0}%`;
    complete = ["COMPLETED", "FAILED"].includes(run.state);
    if (run.state === "COMPLETED") renderEvaluationResult(run);
  }
  button.disabled = false;
}

function renderEvaluationResult(run) {
  const metrics = run.metrics;
  document.getElementById("evaluation-result").innerHTML = `
    <div class="result-heading"><div><span class="eyebrow">${escapeHTML(run.run_id)}</span><h3>Đã hoàn thành đánh giá</h3></div><span class="badge ${run.quality_gate === "PASSED" ? "badge-verified" : "badge-danger"}">${run.quality_gate === "PASSED" ? "ĐẠT CHUẨN" : "KHÔNG ĐẠT"}</span></div>
    <div class="metric-result-grid">
      ${renderMetric("Tỷ lệ Recall@5", metrics.recall_at_5, "percent")}
      ${renderMetric("Độ chính xác câu trả lời", metrics.answer_correctness, "percent")}
      ${renderMetric("Tỷ lệ bao phủ trích dẫn", metrics.citation_coverage, "percent")}
      ${renderMetric("Độ chuẩn xác trích dẫn", metrics.citation_correctness, "percent")}
      ${renderMetric("Độ trễ P95", metrics.p95_latency_ms, "latency")}
    </div>`;
}

function renderMetric(label, value, format) {
  const display = format === "percent" ? `${Math.round(value * 100)}%` : `${value.toLocaleString()} ms`;
  return `<div class="metric-result"><span>${escapeHTML(label)}</span><strong>${display}</strong></div>`;
}

function useLatestMonitoringRequest() {
  if (!latestMonitoringRequestId) {
    showToast("Vui lòng hoàn thành một truy vấn chat trước.", "info");
    return;
  }
  document.getElementById("monitoring-request-id").value = latestMonitoringRequestId;
  loadMonitoringRequest();
}

async function loadMonitoringRequest() {
  const requestId = document.getElementById("monitoring-request-id").value.trim();
  if (!requestId) return;
  const response = await window.HR_API.getMonitoring(requestId);
  if (!handleApiResponse(response)) return;
  const item = response.data;
  document.getElementById("monitoring-result").innerHTML = `
    <div class="result-heading"><div><span class="eyebrow">${escapeHTML(item.observed_request_id)}</span><h3>Nhật ký truy vết request</h3></div><span class="badge ${item.pii_logged ? "badge-danger" : "badge-verified"}">Ghi log PII: ${item.pii_logged ? "CÓ" : "KHÔNG"}</span></div>
    <div class="monitoring-summary"><div><span>Tổng độ trễ</span><strong>${item.total_latency_ms?.toLocaleString() || "—"} ms</strong></div><div><span>Trạng thái phản hồi</span><strong>${escapeHTML(item.answer_status || "—")}</strong></div><div><span>Số đoạn truy xuất</span><strong>${item.retrieval.length}</strong></div></div>
    <div class="retrieval-list">${item.retrieval.length ? item.retrieval.map(chunk => `<div><code>${escapeHTML(chunk.chunk_id || "—")}</code><span>${escapeHTML(chunk.document_id || "—")}</span><strong>${Number(chunk.score).toFixed(2)}</strong></div>`).join("") : `<div class="table-empty">Không có đoạn tri thức nào được trả về cho request này.</div>`}</div>`;
}

async function handleFeedback(messageId, rating) {
  if (rating === "DOWN") {
    document.getElementById("feedback-message-id").value = messageId;
    document.getElementById("feedback-comment").value = "";
    document.getElementById("feedback-modal").classList.add("active");
    return;
  }
  const response = await window.HR_API.submitFeedback(messageId, "UP");
  if (handleApiResponse(response)) showToast("Cảm ơn bạn đã phản hồi đánh giá.", "success");
}

async function submitNegativeFeedback() {
  const response = await window.HR_API.submitFeedback(
    document.getElementById("feedback-message-id").value,
    "DOWN",
    document.getElementById("feedback-reason").value,
    document.getElementById("feedback-comment").value.trim() || null
  );
  if (!handleApiResponse(response)) return;
  closeModal("feedback-modal");
  showToast("Đã gửi phản hồi góp ý. Cảm ơn bạn!", "success");
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

function handleApiResponse(response, showError = true) {
  if (response?.success) return true;
  if (showError) {
    const error = response?.error;
    const detail = error?.details?.[0]?.message;
    showToast(detail || error?.message || "Không thể hoàn tất thao tác này.", "danger");
  }
  return false;
}

function delay(milliseconds) {
  return new Promise(resolve => setTimeout(resolve, milliseconds));
}

function buildChatEmptyState() {
  return `
    <div class="empty-state" id="chat-empty-state">
      <div class="assistant-orb"><i data-lucide="sparkles"></i></div>
      <span class="eyebrow">Trợ lý chính sách HR</span>
      <h1>Tôi có thể giúp gì cho bạn hôm nay?</h1>
      <p>Đặt câu hỏi bằng ngôn ngữ tự nhiên. Tôi sẽ tìm kiếm trong quy định công ty và dẫn nguồn trích dẫn chuẩn xác.</p>

      <div class="trust-strip" aria-label="Trạng thái kho tri thức">
        <span><i data-lucide="files"></i><strong>42</strong> chính sách active</span>
        <span><i data-lucide="shield-check"></i><strong>99.8%</strong> độ tin cậy index</span>
        <span><i data-lucide="clock-3"></i><strong>&lt; 2 phút</strong> tiết kiệm/câu hỏi</span>
      </div>

      <div class="suggested-grid">
        <div class="suggest-card" onclick="askPresetQuestion('hybrid')">
          <div class="suggest-icon"><i data-lucide="home"></i></div>
          <h4>"Quy định làm việc hybrid của công ty như thế nào?"</h4>
          <span>Chính sách làm việc</span><i class="suggest-arrow" data-lucide="arrow-up-right"></i>
        </div>
        <div class="suggest-card" onclick="askPresetQuestion('leave')">
          <div class="suggest-icon"><i data-lucide="calendar-days"></i></div>
          <h4>"Tôi có bao nhiêu ngày phép năm có hưởng lương?"</h4>
          <span>Phúc lợi & Nghỉ phép</span><i class="suggest-arrow" data-lucide="arrow-up-right"></i>
        </div>
        <div class="suggest-card" onclick="askPresetQuestion('probation')">
          <div class="suggest-icon"><i data-lucide="clipboard-check"></i></div>
          <h4>"Quy trình đánh giá thời gian thử việc ra sao?"</h4>
          <span>Onboarding SOP</span><i class="suggest-arrow" data-lucide="arrow-up-right"></i>
        </div>
        <div class="suggest-card" onclick="askPresetQuestion('solar')">
          <div class="suggest-icon"><i data-lucide="sun"></i></div>
          <h4>"Công ty có hỗ trợ chi phí lắp pin năng lượng mặt trời không?"</h4>
          <span>Thử luồng chuyển Ticket</span><i class="suggest-arrow" data-lucide="arrow-up-right"></i>
        </div>
      </div>
    </div>`;
}

function escapeHTML(str) {
  return str.replace(/[&<>'"]/g,
    tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag)
  );
}

function formatAnswerText(text) {
  return escapeHTML(String(text || ""))
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\n/g, "<br>");
}
