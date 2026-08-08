/**
 * In-memory API adapter that mirrors the contract in APIdoc.docx.
 * Replace this object with a real HTTP client without changing the UI layer.
 */
(function initialiseMockApi() {
  const source = window.MOCK_DATA;
  let sequence = 100;
  let solarPolicyIndexed = false;

  const conversations = new Map();
  const chatRequests = new Map();
  const citations = new Map();
  const ingestionJobs = new Map();
  const indexJobs = new Map();
  const evaluationRuns = new Map();
  const monitoringRequests = new Map();
  const feedback = [];

  const documents = source.documents.map((document, index) => ({
    document_id: document.id.replace("doc-", "doc_"),
    title: document.name.replace(/\.[^.]+$/, "").replaceAll("_", " "),
    category: document.category,
    version: document.version,
    effective_date: toIsoDate(document.effectiveDate),
    status: "ACTIVE",
    language: "en",
    source_file: document.name,
    checksum: `sha256:demo${index + 1}`,
    confidentiality: "INTERNAL",
    ingestion: {
      job_id: `ing_0${index + 1}`,
      state: "COMPLETED",
      chunk_count: document.chunks,
      last_ingested_at: "2026-08-05T08:40:00Z",
      error: null
    },
    index: {
      indexed: true,
      index_version: "idxver_20260805_01"
    },
    created_at: "2026-08-05T08:30:00Z"
  }));

  seedCitations();

  function nextId(prefix) {
    sequence += 1;
    return `${prefix}_${sequence}`;
  }

  function timestamp() {
    return new Date().toISOString();
  }

  function ok(data, meta = {}) {
    return {
      request_id: nextId("req"),
      success: true,
      data,
      error: null,
      meta: { timestamp: timestamp(), api_version: "v1", ...meta }
    };
  }

  function fail(code, message, retryable = false, details = []) {
    return {
      request_id: nextId("req"),
      success: false,
      data: null,
      error: { code, message, details, retryable, retry_after_ms: null },
      meta: { timestamp: timestamp(), api_version: "v1" }
    };
  }

  function toIsoDate(value) {
    const parsed = new Date(value);
    return Number.isNaN(parsed.valueOf()) ? null : parsed.toISOString().slice(0, 10);
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function seedCitations() {
    const hybrid = source.ragResponses.hybrid.citations[0];
    citations.set("cit_hybrid", makeCitation("cit_hybrid", "doc_1", hybrid));

    const leaveDocument = source.documents[1];
    citations.set("cit_leave", {
      citation_id: "cit_leave",
      document: {
        document_id: "doc_2",
        title: "Annual Leave and PTO Guidelines 2026",
        version: leaveDocument.version,
        effective_date: toIsoDate(leaveDocument.effectiveDate),
        status: "ACTIVE"
      },
      location: { page: 3, section: "Section 1.3", chunk_id: "chk_leave_01" },
      excerpt: "Full-time employees receive 18 days of paid annual leave per calendar year. Unused leave up to 5 days can carry over to Q1 of the subsequent year.",
      conflict_warning: false
    });

    const probationDocument = source.documents[2];
    citations.set("cit_probation", {
      citation_id: "cit_probation",
      document: {
        document_id: "doc_3",
        title: "Probation Review and Onboarding SOP",
        version: probationDocument.version,
        effective_date: toIsoDate(probationDocument.effectiveDate),
        status: "ACTIVE"
      },
      location: { page: 6, section: "Section 3.4", chunk_id: "chk_probation_01" },
      excerpt: "The standard probation period is 90 days. Formal 30-day, 60-day, and 90-day check-in reviews are conducted by the line manager.",
      conflict_warning: false
    });
  }

  function makeCitation(citationId, documentId, citation) {
    return {
      citation_id: citationId,
      document: {
        document_id: documentId,
        title: citation.title.replace(/^\[\d+\]\s*/, ""),
        version: citation.version,
        effective_date: toIsoDate(citation.effectiveDate),
        status: "ACTIVE"
      },
      location: {
        page: Number(String(citation.page).replace(/\D/g, "")) || null,
        section: citation.section,
        chunk_id: nextId("chk")
      },
      excerpt: citation.excerpt,
      conflict_warning: false
    };
  }

  function citationSummary(citationId) {
    const citation = citations.get(citationId);
    return {
      citation_id: citation.citation_id,
      title: citation.document.title,
      page: citation.location.page,
      section: citation.location.section,
      version: citation.document.version,
      effective_date: citation.document.effective_date
    };
  }

  function buildFinalResult(question, request) {
    const normalized = question.toLowerCase();
    const common = {
      chat_request_id: request.chat_request_id,
      conversation_id: request.conversation_id,
      user_message_id: request.user_message_id,
      assistant_message_id: nextId("msg_a"),
      warnings: [],
      clarification: null,
      failure: null,
      latency_ms: 1280
    };

    if (normalized.includes("timeout") || normalized.includes("lỗi hệ thống")) {
      return {
        ...common,
        assistant_message_id: null,
        state: "FAILED",
        answer_status: null,
        answer: null,
        citations: [],
        failure: {
          code: "UPSTREAM_TIMEOUT",
          message: "Dịch vụ tạo câu trả lời phản hồi quá thời gian.",
          retryable: true
        }
      };
    }

    if (normalized.includes("probation") && !normalized.includes("full-time") && !normalized.includes("thử việc")) {
      return {
        ...common,
        state: "CLARIFICATION_REQUIRED",
        answer_status: "CLARIFICATION_REQUIRED",
        answer: null,
        citations: [],
        clarification: {
          question: "Bạn muốn hỏi quy trình đánh giá cho nhân viên thử việc hay nhân viên chính thức?",
          options: ["Nhân viên thử việc", "Nhân viên chính thức"]
        }
      };
    }

    if (normalized.includes("probation")) {
      return {
        ...common,
        state: "COMPLETED",
        answer_status: "ANSWERED",
        answer: "Thời gian thử việc tiêu chuẩn là **90 ngày**. Quản lý trực tiếp thực hiện các buổi đánh giá vào ngày 30, 60 và 90.",
        citations: [citationSummary("cit_probation")]
      };
    }

    if (normalized.includes("solar") && !solarPolicyIndexed) {
      return {
        ...common,
        state: "REFUSED",
        answer_status: "INSUFFICIENT_EVIDENCE",
        answer: "Tôi chưa tìm thấy đủ thông tin trong các tài liệu HR đang hoạt động để trả lời câu hỏi này.",
        citations: []
      };
    }

    if (normalized.includes("leave") || normalized.includes("phép")) {
      return {
        ...common,
        state: "COMPLETED",
        answer_status: "ANSWERED",
        answer: "Nhân viên toàn thời gian được hưởng **18 ngày phép năm có lương** trong mỗi năm dương lịch. Tối đa 5 ngày chưa sử dụng có thể được chuyển sang quý I năm tiếp theo.",
        citations: [citationSummary("cit_leave")]
      };
    }

    if (normalized.includes("solar") && solarPolicyIndexed) {
      return {
        ...common,
        state: "COMPLETED",
        answer_status: "ANSWERED",
        answer: "Theo chính sách mới, nhân viên làm việc từ xa đủ điều kiện nhận **hỗ trợ 50% chi phí, tối đa 1.500 USD** cho hệ thống năng lượng mặt trời tại nhà.",
        citations: [citationSummary("cit_solar")]
      };
    }

    const warning = normalized.includes("conflict") || normalized.includes("mâu thuẫn")
      ? [{
          type: "CONFLICTING_SOURCES",
          severity: "WARNING",
          message: "Có nhiều phiên bản chính sách phù hợp; hãy kiểm tra ngày hiệu lực trước khi áp dụng.",
          citation_ids: ["cit_hybrid"],
          recommended_action: "VERIFY_WITH_HR"
        }]
      : [];

    return {
      ...common,
      state: "COMPLETED",
      answer_status: "ANSWERED",
      answer: source.ragResponses.hybrid.answer,
      citations: [citationSummary("cit_hybrid")],
      warnings: warning
    };
  }

  function addAssistantMessage(result) {
    if (!result.assistant_message_id) return;
    const conversation = conversations.get(result.conversation_id);
    if (!conversation) return;
    conversation.messages.push({
      message_id: result.assistant_message_id,
      role: "ASSISTANT",
      content: result.answer || result.clarification?.question || result.failure?.message || "",
      chat_request_id: result.chat_request_id,
      answer_status: result.answer_status,
      citations: result.citations,
      warnings: result.warnings,
      clarification: result.clarification,
      failure: result.failure,
      state: result.state,
      created_at: timestamp()
    });
  }

  const api = {
    async createConversation(title = null) {
      const conversation_id = nextId("conv");
      const conversation = {
        conversation_id,
        title,
        state: "ACTIVE",
        created_at: timestamp(),
        ended_at: null,
        messages: []
      };
      conversations.set(conversation_id, conversation);
      return ok({ conversation_id, state: "ACTIVE", created_at: conversation.created_at });
    },

    async getConversation(conversationId) {
      const conversation = conversations.get(conversationId);
      if (!conversation) return fail("CONVERSATION_NOT_FOUND", "Không tìm thấy cuộc hội thoại.");
      return ok({
        conversation_id: conversation.conversation_id,
        title: conversation.title,
        state: conversation.state,
        created_at: conversation.created_at,
        ended_at: conversation.ended_at,
        message_count: conversation.messages.length,
        last_message_at: conversation.messages.at(-1)?.created_at || null
      });
    },

    async getConversationMessages(conversationId) {
      const conversation = conversations.get(conversationId);
      if (!conversation) return fail("CONVERSATION_NOT_FOUND", "Không tìm thấy cuộc hội thoại.");
      return ok({
        conversation_id: conversationId,
        messages: clone(conversation.messages),
        pagination: { limit: 20, next_cursor: null }
      });
    },

    async endConversation(conversationId) {
      const conversation = conversations.get(conversationId);
      if (!conversation) return fail("CONVERSATION_NOT_FOUND", "Không tìm thấy cuộc hội thoại.");
      if (conversation.state === "ENDED") return fail("CONVERSATION_ENDED", "Cuộc hội thoại đã kết thúc.");
      conversation.state = "ENDED";
      conversation.ended_at = timestamp();
      return ok({ conversation_id: conversationId, state: "ENDED", ended_at: conversation.ended_at });
    },

    async createChatRequest(conversationId, question) {
      const conversation = conversations.get(conversationId);
      if (!conversation) return fail("CONVERSATION_NOT_FOUND", "Không tìm thấy cuộc hội thoại.");
      if (conversation.state !== "ACTIVE") return fail("CONVERSATION_ENDED", "Hãy tạo cuộc hội thoại mới.");
      if (!question.trim()) {
        return fail("VALIDATION_ERROR", "Dữ liệu không hợp lệ.", false, [{ field: "question", message: "Question không được để trống." }]);
      }

      const chat_request_id = nextId("chatreq");
      const user_message_id = nextId("msg_u");
      const request = {
        chat_request_id,
        conversation_id: conversationId,
        question,
        user_message_id,
        state: "QUEUED",
        poll_count: 0,
        final: null
      };
      chatRequests.set(chat_request_id, request);
      conversation.messages.push({
        message_id: user_message_id,
        role: "USER",
        content: question,
        chat_request_id,
        created_at: timestamp()
      });
      return ok({ chat_request_id, conversation_id: conversationId, state: "QUEUED", poll_after_ms: 350 });
    },

    async getChatRequest(chatRequestId) {
      const request = chatRequests.get(chatRequestId);
      if (!request) return fail("CHAT_REQUEST_NOT_FOUND", "Không tìm thấy yêu cầu chat.");
      request.poll_count += 1;
      if (request.poll_count === 1) request.state = "RETRIEVING";
      if (request.poll_count === 2) request.state = "GENERATING";
      if (request.poll_count >= 3 && !request.final) {
        request.final = buildFinalResult(request.question, request);
        request.state = request.final.state;
        addAssistantMessage(request.final);
      }

      const data = request.final || {
        chat_request_id: request.chat_request_id,
        conversation_id: request.conversation_id,
        user_message_id: request.user_message_id,
        assistant_message_id: null,
        state: request.state,
        answer_status: null,
        answer: null,
        citations: [],
        warnings: [],
        clarification: null,
        failure: null,
        latency_ms: null,
        poll_after_ms: 350
      };
      const response = ok(clone(data));
      if (request.final) {
        monitoringRequests.set(response.request_id, {
          observed_request_id: response.request_id,
          total_latency_ms: data.latency_ms,
          retrieval: data.citations.map(item => ({
            chunk_id: citations.get(item.citation_id)?.location.chunk_id || null,
            document_id: citations.get(item.citation_id)?.document.document_id || null,
            score: 0.91
          })),
          answer_status: data.answer_status,
          pii_logged: false
        });
      }
      return response;
    },

    async retryChatRequest(chatRequestId) {
      const parent = chatRequests.get(chatRequestId);
      if (!parent?.final?.failure?.retryable) return fail("REQUEST_NOT_RETRYABLE", "Yêu cầu này không thể thử lại.");
      return this.createChatRequest(parent.conversation_id, parent.question.replace(/timeout|lỗi hệ thống/gi, "chính sách hybrid"));
    },

    async getCitation(citationId) {
      const citation = citations.get(citationId);
      return citation ? ok(clone(citation)) : fail("CITATION_NOT_FOUND", "Không tìm thấy trích dẫn.");
    },

    async listDocuments(filters = {}) {
      const filtered = documents.filter(document => {
        if (filters.status && document.status !== filters.status) return false;
        if (filters.category && !document.category.toLowerCase().includes(filters.category.toLowerCase())) return false;
        if (filters.indexed === "true" && !document.index.indexed) return false;
        if (filters.indexed === "false" && document.index.indexed) return false;
        return true;
      });
      return ok({ documents: clone(filtered) }, { pagination: { limit: 20, next_cursor: null } });
    },

    async getDocument(documentId) {
      const document = documents.find(item => item.document_id === documentId);
      return document ? ok(clone(document)) : fail("DOCUMENT_NOT_FOUND", "Không tìm thấy tài liệu.");
    },

    async updateDocumentMetadata(documentId, metadata) {
      const document = documents.find(item => item.document_id === documentId);
      if (!document) return fail("DOCUMENT_NOT_FOUND", "Không tìm thấy tài liệu.");
      Object.assign(document, metadata);
      document.index.indexed = false;
      return ok({ document_id: documentId, metadata_updated: true, requires_reindex: true, updated_at: timestamp() });
    },

    async archiveDocument(documentId) {
      const document = documents.find(item => item.document_id === documentId);
      if (!document) return fail("DOCUMENT_NOT_FOUND", "Không tìm thấy tài liệu.");
      document.status = "ARCHIVED";
      document.index.indexed = false;
      return ok({ document_id: documentId, status: "ARCHIVED", requires_reindex: true, archived_at: timestamp() });
    },

    async uploadDocument(file, metadata) {
      if (!file) return fail("VALIDATION_ERROR", "Vui lòng chọn file.", false, [{ field: "file", message: "File là bắt buộc." }]);
      const allowed = ["pdf", "docx", "xlsx"];
      const extension = file.name.split(".").pop().toLowerCase();
      if (!allowed.includes(extension)) return fail("UNSUPPORTED_FILE_TYPE", "Chỉ chấp nhận PDF, DOCX hoặc XLSX.");
      if (file.size > 25 * 1024 * 1024) return fail("FILE_TOO_LARGE", "Dung lượng file vượt quá 25 MB.");

      const document_id = nextId("doc");
      const job_id = nextId("ing");
      const document = {
        document_id,
        title: metadata.title || file.name,
        category: metadata.category || "uncategorized",
        version: metadata.version || null,
        effective_date: metadata.effective_date || null,
        status: metadata.status || "ACTIVE",
        language: metadata.language || "vi",
        source_file: file.name,
        checksum: "sha256:pending",
        confidentiality: metadata.confidentiality || "INTERNAL",
        ingestion: { job_id, state: "QUEUED", chunk_count: 0, last_ingested_at: null, error: null },
        index: { indexed: false, index_version: null },
        created_at: timestamp()
      };
      documents.unshift(document);
      ingestionJobs.set(job_id, { job_id, document_id, state: "QUEUED", stage: "UPLOADING", progress_percent: 10, error: null, poll_count: 0 });
      if (file.name.toLowerCase().includes("solar")) {
        const mock = source.ragResponses.solar_reindexed.citations[0];
        citations.set("cit_solar", makeCitation("cit_solar", document_id, mock));
      }
      return ok({ document_id, ingestion_job_id: job_id, status: "UPLOADED" });
    },

    async getIngestionJob(jobId) {
      const job = ingestionJobs.get(jobId);
      if (!job) return fail("INGESTION_JOB_NOT_FOUND", "Không tìm thấy ingestion job.");
      job.poll_count += 1;
      const stages = [
        ["PROCESSING", "EXTRACTING", 35],
        ["PROCESSING", "CHUNKING", 65],
        ["PROCESSING", "EMBEDDING", 85],
        ["COMPLETED", "INDEXED", 100]
      ];
      const [state, stage, progress] = stages[Math.min(job.poll_count - 1, stages.length - 1)];
      Object.assign(job, { state, stage, progress_percent: progress });
      if (state === "COMPLETED") {
        const document = documents.find(item => item.document_id === job.document_id);
        document.ingestion = { job_id: jobId, state, chunk_count: 110, last_ingested_at: timestamp(), error: null };
        document.index = { indexed: true, index_version: "idxver_20260805_02" };
        if (document.source_file.toLowerCase().includes("solar")) solarPolicyIndexed = true;
      }
      return ok({ ...clone(job), poll_after_ms: 350 });
    },

    async startIndexRebuild(documentIds = [], strategy = "REPLACE") {
      const job_id = nextId("idx");
      indexJobs.set(job_id, { job_id, document_ids: documentIds, strategy, state: "QUEUED", progress_percent: 0, poll_count: 0, error: null });
      return ok({ job_id, state: "QUEUED", poll_after_ms: 400 });
    },

    async getIndexRebuild(jobId) {
      const job = indexJobs.get(jobId);
      if (!job) return fail("INDEX_JOB_NOT_FOUND", "Không tìm thấy index job.");
      job.poll_count += 1;
      job.progress_percent = Math.min(job.poll_count * 34, 100);
      job.state = job.progress_percent >= 100 ? "COMPLETED" : "PROCESSING";
      if (job.state === "COMPLETED") {
        documents.filter(item => !job.document_ids.length || job.document_ids.includes(item.document_id)).forEach(item => {
          if (item.status === "ACTIVE" && item.ingestion.state === "COMPLETED") {
            item.index = { indexed: true, index_version: "idxver_20260805_03" };
          }
        });
      }
      return ok({ job_id: jobId, state: job.state, progress_percent: job.progress_percent, active_index_version: job.state === "COMPLETED" ? "idxver_20260805_03" : null, error: null });
    },

    async startEvaluation(datasetId, indexVersion, modelConfigId) {
      if (!datasetId) return fail("VALIDATION_ERROR", "Dataset là bắt buộc.");
      const run_id = nextId("eval");
      evaluationRuns.set(run_id, { run_id, dataset_id: datasetId, index_version: indexVersion, model_config_id: modelConfigId, state: "QUEUED", poll_count: 0 });
      return ok({ run_id, state: "QUEUED", poll_after_ms: 450 });
    },

    async getEvaluation(runId) {
      const run = evaluationRuns.get(runId);
      if (!run) return fail("EVALUATION_RUN_NOT_FOUND", "Không tìm thấy evaluation run.");
      run.poll_count += 1;
      run.state = run.poll_count >= 3 ? "COMPLETED" : "PROCESSING";
      return ok({
        run_id: runId,
        state: run.state,
        progress_percent: run.state === "COMPLETED" ? 100 : run.poll_count * 34,
        metrics: run.state === "COMPLETED" ? {
          recall_at_5: 0.87,
          answer_correctness: 0.82,
          citation_coverage: 0.96,
          citation_correctness: 0.88,
          p95_latency_ms: 7200
        } : null,
        quality_gate: run.state === "COMPLETED" ? "PASSED" : null
      });
    },

    async getMonitoring(requestId) {
      const entry = monitoringRequests.get(requestId);
      return entry ? ok(clone(entry)) : fail("REQUEST_LOG_NOT_FOUND", "Không tìm thấy request log.");
    },

    async submitFeedback(assistantMessageId, rating, reasonCode = null, comment = null) {
      if (!assistantMessageId || !["UP", "DOWN"].includes(rating)) return fail("FEEDBACK_INVALID", "Feedback không hợp lệ.");
      const item = {
        feedback_id: nextId("fb"),
        assistant_message_id: assistantMessageId,
        rating,
        reason_code: reasonCode,
        comment,
        created_at: timestamp()
      };
      feedback.push(item);
      return ok(clone(item));
    }
  };

  window.HR_API = api;
})();
