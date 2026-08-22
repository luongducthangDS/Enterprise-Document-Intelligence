from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "AI20K Agent"
    # Tên persona nội bộ dùng cho demo. Không đưa tên doanh nghiệp thật vào đây:
    # các tài liệu corporate policy thật chỉ là nguồn tham khảo, không phải chính
    # sách đang áp dụng cho một công ty cụ thể. "NexaTech" là công ty giả định
    # (NexaTech HR Policy Copilot / NexaBot — baseline v3.1.0) trong bộ chính
    # sách synthetic; thiếu nó thì router từ chối luôn các câu hỏi về chính sách
    # nội bộ của persona demo.
    internal_company_names: list[str] = Field(
        default_factory=lambda: ["nexatech", "nexabot"]
    )
    app_env: Literal["development", "production", "test"] = "development"
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_host: str = "0.0.0.0"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: str = "http://localhost:3000"
    agent_service_token: str = ""

    # Database (dữ liệu quan hệ: user/RBAC, chat history, ticket, document metadata)
    # URL Supabase PostgreSQL — đọc từ .env; không có default SQLite nữa.
    database_url: str = ""
    knowledge_database_url: str = ""  # Optional override riêng cho lới thức layer
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    # Môi trường dữ liệu.
    #   demo       — NexaTech là tenant giả lập; bộ policy synthetic của nó ĐƯỢC
    #                dùng như chính sách nội bộ chính thức, nhưng agent luôn nói
    #                rõ đây là dữ liệu mô phỏng.
    #   production — chỉ chính sách thật do doanh nghiệp khách hàng cung cấp mới
    #                được dùng; mọi tài liệu provenance=synthetic_demo bị loại
    #                ngay từ tầng truy vấn vector, không phụ thuộc LLM tuân thủ.
    # Tách khỏi vector_db_backend có chủ đích: cùng một Chroma Cloud có thể phục
    # vụ cả demo lẫn production, khác nhau ở tập tài liệu được phép đọc.
    data_mode: Literal["demo", "production"] = "demo"
    # Tenant mà assistant đang phục vụ — quyết định tài liệu nào được coi là
    # "chính sách của doanh nghiệp mình".
    active_tenant: str = "nexatech"

    # Vector Store — "cloud" (Chroma Cloud, dùng chung cho cả team + server) hay
    # "local" (PersistentClient trên đĩa, chỉ dùng dev/test offline — KHÔNG sống
    # được trên Render vì free/standard tier không có persistent disk).
    vector_db_backend: Literal["cloud", "local"] = "cloud"
    chroma_persist_dir: str = "./storage/vector_db"
    chroma_collection_name: str = "tenant_nexatech_knowledge"

    chroma_cloud_api_key: str = ""
    chroma_cloud_tenant: str = ""
    chroma_cloud_database: str = ""

    # FPT.AI Marketplace (embedding/VLM/rerank/chat gateway)
    fpt_api_key: str = ""
    fpt_base_url: str = "https://mkp-api.fptcloud.com"
    embedding_model: str = "multilingual-e5-large"
    embedding_batch_size: int = 32
    llm_model: str = "GLM-5.2"
    # Model riêng cho 2 tác vụ PHÂN LOẠI (router: 1 từ trong 4; hallucination
    # check: PASS/FAIL) — không cần model reasoning to như generate. Rỗng =
    # dùng llm_model.
    #
    # router_model: DeepSeek-V4-Flash được chọn từ A/B MODEL, đo với thinking
    # ON — 95.7% (134/140, ngưỡng >=94%) và nhanh hơn GLM-5.2 3.3x (p50 1.8s vs
    # 6.0s). Đó là con số của phép chọn model, KHÔNG phải accuracy production.
    #
    # LƯU Ý (đọc kèm `thinking_router` phía dưới): production hiện chạy
    # thinking_router=False. Eval riêng cho đúng cấu hình đang chạy:
    #   fast router (raw)              87.9%
    #   fast router + escalation guard 92.1%
    # Hai quyết định tách bạch, đừng trộn khi đọc:
    #   chọn model         -> DeepSeek-V4-Flash
    #   chiến lược reasoning -> thinking OFF + escalation guard
    #
    # hallucination_model: A/B bằng replay offline 60 câu
    # (eval/results/hallucination_model_ab.json) — DeepSeek-V4-Flash chỉ đồng
    # thuận 76.7% với GLM-5.2 (ngưỡng >=95%), dù nhanh hơn (p50 4.2s vs 8.1s).
    # KHÔNG đạt ngưỡng — sai lệch verdict PASS/FAIL trên tác vụ an toàn
    # (chống hallucination) rủi ro hơn nhiều so với latency tiết kiệm được.
    # Giữ rỗng (dùng GLM-5.2) cho tới khi có model khác đạt ngưỡng.
    router_model: str = "DeepSeek-V4-Flash"
    hallucination_model: str = ""
    # Model viết lại câu hỏi hiện tại thành câu hỏi độc lập dựa trên lịch sử hội
    # thoại (condense_node) — cùng dạng tác vụ rewrite như router, không cần
    # model reasoning to. Rỗng = dùng llm_model.
    condense_model: str = ""
    # Số lượt hội thoại gần nhất đưa vào prompt condense — chặn phình token khi
    # hội thoại dài, các lượt cũ hơn không còn cần thiết để viết lại câu hỏi.
    max_history_turns: int = 8
    max_history_content_chars: int = 2000
    # Chain-of-thought của reasoning model (gửi
    # chat_template_kwargs.enable_thinking xuống gateway). Tách cờ theo từng
    # node vì mỗi node có bộ eval và ngưỡng chấp nhận riêng — giống cách
    # `router_model`/`hallucination_model` được A/B tách bạch.
    #
    # BỐI CẢNH (đo trực tiếp 2026-08-12): cả GLM-5.2 lẫn DeepSeek-V4-Flash đều
    # sinh reasoning cho MỌI request, kể cả tác vụ trả về đúng 1 từ — router tốn
    # 265-467 completion token (~1.000 ký tự reasoning) để in ra "hr_question",
    # hallucination check tốn 581 token để in ra "PASS". Latency tỷ lệ với token
    # SINH RA, gần như không phụ thuộc độ dài context (generate với prompt 1.670
    # token chỉ 3,7s, trong khi "ping" prompt 22 token mất 5,5s). Tắt thinking
    # nhanh hơn 6-14x, nên đây là đòn giảm latency lớn nhất — NẾU chất lượng giữ
    # được. Lưu ý `reasoning_effort` KHÔNG dùng được: gateway trả 200 nhưng vẫn
    # sinh đủ 265-270 token reasoning.
    #
    # thinking_router=False: ĐÁNH ĐỔI CÓ CHỦ ĐÍCH, Ted quyết 2026-08-12 sau khi
    # xem số A/B đầy đủ — chấp nhận mất accuracy để lấy tốc độ, KHÔNG phải vì
    # tưởng chất lượng không đổi.
    #
    # A/B trên 140 câu qa_eval_set (eval/results/router_thinking_ab.json), chấm
    # theo bộ nhãn hiện tại — CHỈ router, chưa có escalation guard:
    #   accuracy  95.7% -> 87.9%   [-7.8 điểm]
    #   p50       4.845ms -> 345ms [14x nhanh hơn]
    # Ngưỡng lịch sử của router là >= 94% (xem `router_model` phía trên), nên
    # riêng con số này KHÔNG đạt ngưỡng — đây là ngoại lệ được chấp nhận, không
    # phải tiền lệ mới. Bất kỳ ai xem lại quyết định này cần biết:
    #
    # - Mọi câu đổi verdict đều đổi theo hướng xấu đi, không câu nào được sửa
    #   đúng: suy giảm hệ thống, không phải nhiễu hai chiều.
    # - Lỗi rơi đúng chỗ khó chịu nhất với người dùng: hr_question bị đẩy nhầm
    #   sang ambiguous 9 câu (bật: 1) và sang out_of_scope_or_personal 4 câu
    #   (bật: 1) — câu hỏi HR hợp lệ bị hỏi lại một lượt thừa hoặc bị đẩy sang
    #   HRBP thay vì được trả lời ngay.
    # - Không có câu out_of_scope nào lọt thành hr_question, nên đánh đổi này
    #   KHÔNG làm agent trả lời liều những câu lẽ ra phải từ chối — rủi ro nằm ở
    #   phía phiền người dùng, không phải phía an toàn. Đó là điều kiện tiên
    #   quyết để chấp nhận đánh đổi ở đây mà KHÔNG chấp nhận ở
    #   `thinking_hallucination`.
    #
    # QUAN TRỌNG: 87.9% là con số của RIÊNG fast router. Cấu hình đang chạy có
    # thêm `escalation_guard_enabled` phía dưới, đạt 92.1% với nhánh "câu HR bị
    # từ chối oan" = 0 (baseline thinking ON: 1). Đừng đọc 87.9% như chất lượng
    # production.
    #
    # Đổi lại `True` là cách rollback duy nhất cần làm nếu tỷ lệ hỏi lại/escalate
    # trên production vượt mức chịu được.
    #
    # thinking_condense=True: ĐÃ A/B trên 16 case multi-turn 4 nhóm
    # (eval/results/condense_thinking_ab.json, spec ở eval/CONDENSE_EVAL_SPEC.md).
    # Giữ bật vì KHÔNG chứng minh được lợi ích, chứ KHÔNG phải vì tắt gây hỏng:
    #
    #   answer correct   15/16 -> 15/16   (hoà)
    #   retrieval hit    16/16 -> 16/16   (hoà)
    #   wrong escalation   1   ->   1     (hoà, và cả hai đều là nhiễu sinh)
    #   failure mode       0   ->   0     (không reference_loss/misresolution/
    #                                      topic_contamination nào)
    #   condense p50    1.926ms -> 588ms  (3.3x)
    #   E2E paired delta  median -329ms (p25 -5.497ms / p75 +2.268ms), 8/16
    #                     case mỗi bên. Hiệu của hai median là -4.484ms nhưng
    #                     đó là con số gây hiểu nhầm: với A/B cùng case phải
    #                     đọc median of PAIRED differences, và nó gần 0.
    #
    # Kết luận chính xác KHÔNG phải "tắt thinking không có lợi ích", mà là:
    # CHƯA ĐỦ BẰNG CHỨNG rằng lợi ích latency của OFF ổn định ở mức E2E để đáng
    # đổi default. Tiết kiệm ở riêng node là thật và nhất quán (paired delta của
    # condense có cả p25 lẫn p75 đều âm), nhưng condense chỉ chiếm ~10% pipeline
    # nên phần tiết kiệm đó chìm trong biên dao động của gateway (một case OFF
    # dính 80,9s). Ba tiêu chí chất lượng đều hoà.
    #
    # Giữ bật cho tới khi một benchmark multi-turn LỚN HƠN và KHÓ HƠN chứng minh
    # được E2E gain đáng tin cậy. Rủi ro của việc tắt (dù benchmark này chưa
    # quan sát thấy) là loại lỗi âm thầm nhất: condense sai không bị lớp nào phía
    # sau bắt, vì hallucination check chỉ kiểm tra câu trả lời có bám context —
    # mà context thì đã sai từ đầu.
    #
    # ĐÍNH CHÍNH: comment trước ở đây viện dẫn một quan sát đơn lẻ (lượt "Vậy
    # ngày thường thì sao?" rơi xuống escalate khi tắt thinking) làm lý do giữ
    # bật. Benchmark 16 case KHÔNG tái hiện được điều đó — chính case ellipsis
    # đó nay đúng ở cả hai nhánh. Nhiều khả năng quan sát cũ là generation
    # variance, không phải hệ quả của condense.
    #
    # thinking_hallucination=True: đã A/B, KHÔNG đánh đổi được — replay offline
    # 60 câu (eval/results/hallucination_thinking_ab.json) cho agreement chỉ
    # 78.3% (47/60) so với ngưỡng >= 95%, dù p50 giảm 8.085ms -> 609ms (13x).
    #
    # Con số chỉ là một nửa lý do; nửa quan trọng hơn là HƯỚNG sai: 10/13 bất
    # đồng là bản tắt thinking nói PASS trong khi bản bật nói FAIL (pass rate
    # 43/60 -> 50/60). Tức tắt thinking làm lớp chống bịa đặt DỄ DÃI hơn — nó bỏ
    # lọt đúng thứ nó sinh ra để chặn. Khác hẳn `thinking_router`: ở đó tắt
    # thinking sai theo hướng an toàn (chỉ làm phiền người dùng, không có câu
    # out_of_scope nào lọt thành hr_question), nên đánh đổi được. Ở đây thì
    # không: nhanh hơn 13s cũng không bù được một câu trả lời bịa lọt ra ngoài.
    #
    # thinking_generation=True: chưa A/B (cần eval_agent.py với LLM judge).

    # Chốt chặn trước khi đẩy một câu sang nhánh escalate/HRBP
    # (src/agents/nodes/router.py::_guard_escalation).
    #
    # Lý do tồn tại: fast router (thinking_router=False) mua tốc độ 14x bằng
    # 7.9 điểm accuracy, và phần lớn thiệt hại rơi đúng vào chỗ đắt nhất về UX —
    # câu hỏi HR hợp lệ bị xếp nhầm `out_of_scope_or_personal` rồi bị TỪ CHỐI.
    # Thay vì bật lại thinking cho 100% traffic, guard chỉ dùng verifier CÓ
    # thinking ở các case escalation có dấu hiệu vừa mang ngữ cảnh cá nhân vừa
    # hỏi policy chung ("cuối năm mình còn 8 ngày phép thì xử lý thế nào?").
    # Câu personal thật và câu ngoài phạm vi dừng lại ở heuristic, không tốn gì.
    #
    # Trên eval hiện tại, guard đã loại TOÀN BỘ regression escalation phát sinh
    # do tắt thinking; các false escalation còn lại đều đến từ competitor rule
    # và tồn tại cả khi thinking ON.
    #
    # Đo trên 140 câu, TẤT CẢ chấm theo cùng một bộ nhãn
    # (eval/results/router_escalation_guard_ab.json):
    #   thinking ON               95.7% | cost 18 | HR bị từ chối oan 1 | p50 4.845ms
    #   fast router, chưa guard   87.9% | cost 49 | HR bị từ chối oan 4 | p50 345ms
    #   fast + guard              89.3% | cost 36 | HR bị từ chối oan 1 | p50 378ms
    #   fast + guard + rule fix   92.1% | cost 25 | HR bị từ chối oan 0 | p50 373ms
    # (cost = confusion matrix có trọng số theo hậu quả: hr->personal = 5,
    # personal->hr = 4, hr->ambiguous = 2, ...)
    #
    # Cấu hình đang chạy là dòng cuối. Nhánh nguy hiểm nhất — câu hỏi HR hợp lệ
    # bị TỪ CHỐI — đã về 0, tức còn TỐT HƠN baseline thinking ON (1 câu), trong
    # khi vẫn nhanh 13x. Phần chênh accuracy còn lại (92.1% vs 95.7%) nằm gọn ở
    # hr_question -> ambiguous (7 câu): hậu quả nhẹ nhất, chỉ tốn một lượt hỏi
    # lại, và guard cố tình không chạm nhánh đó.
    #
    # Hai thay đổi ngoài guard đã đóng góp vào con số trên, cả hai đều KHÔNG
    # phải hệ quả của việc tắt thinking:
    # - `_mentions_competitor_company` xét quan hệ ngữ cảnh thay vì substring
    #   (qa_006 "dùng taxi hoặc Grab" từng bị chặn oan — Grab là phương tiện,
    #   không phải công ty bị hỏi chính sách).
    # - qa_051/052/053 (hỏi văn hoá/slogan/quy định Vingroup-VinFast) đổi nhãn
    #   in_scope -> competitor_comparison sau khi chốt phạm vi sản phẩm: bot
    #   phục vụ persona V-NOVA nên đây là công ty khác. Xác nhận chéo cho thấy
    #   đây là sửa ĐÚNG hệ đo chứ không phải nới lỏng: baseline thinking ON chấm
    #   theo nhãn mới ra đúng 95.7%, trùng khít con số A/B chọn model lịch sử
    #   (134/140) vốn được đo trước khi 3 câu này bị gán nhãn sai.
    #
    # CẤU HÌNH ĐANG CHẠY đạt 94.9% trên bộ 137 câu
    # (eval/results/router_prompt_dimension_ab.json). Con số đó là kết quả CỘNG
    # DỒN của BỐN thứ, không phải của riêng `thinking_router=False`:
    #   1. fast router (thinking_router=False)                      -> 87.9%
    #   2. + escalation guard (cờ ngay dưới đây)                    -> 92.1%
    #   3. + `_mentions_competitor_company` xét ngữ cảnh thay
    #        substring, và sửa nhãn qa_051/052/053                  -> 92.7%
    #   4. + rule "chiều hỏi" trong prompt router                   -> 94.9%
    # Đừng đọc thành "tắt thinking là tự có 94.9%".
    #
    # LƯU Ý VỀ HỆ ĐO: sau P2, qa_eval_set là ROUTER DEVELOPMENT/REGRESSION SET,
    # không còn là held-out sạch — prompt hiện tại được sửa dựa trên chính các
    # lỗi soi ra từ bộ đó (test-informed tuning). 94.9% đủ để chọn cấu hình này
    # hơn phương án khác, nhưng KHÔNG phải ước lượng accuracy production không
    # thiên lệch. Cần một fresh holdout chưa từng dùng để tune mới claim được.
    #
    # ROLLBACK nếu tỷ lệ hỏi lại/escalate trên production tăng bất thường:
    # revert khối "PHÂN ĐỊNH ... CHIỀU HỎI" trong _get_router_system() về
    # revision trước. KHÔNG bật `thinking_router=True` cho toàn bộ traffic ngay
    # — đó là đòn cuối (đắt 14x latency), không phải phản xạ đầu tiên.
    escalation_guard_enabled: bool = True
    thinking_router: bool = False
    thinking_condense: bool = True
    thinking_generation: bool = True
    thinking_hallucination: bool = True

    # P4A — hai nhánh "rẻ" (direct/clarify): tác vụ chỉ sinh MỘT câu ngắn nhưng
    # đang chạy GLM-5.2 thinking bật. Đo ở P3 (eval/results/e2e_profile_baseline.json):
    # direct p50 5,5s · clarify p50 9,2s — trong khi đây đúng là hai nhánh người
    # dùng kỳ vọng phản hồi nhanh nhất (chào hỏi, hỏi lại một câu).
    #
    # Mỗi nhánh có cờ RIÊNG, cố ý không dùng chung `llm_model`: nếu một nhánh
    # regression thì rollback đúng nhánh đó, không kéo theo generate/hallucination.
    #
    # direct_mode:
    #   "default_llm" — hành vi cũ (GLM-5.2, thinking bật)
    #   "fast_llm"    — router_model + thinking tắt  <- ĐANG DÙNG
    #   "template"    — không gọi LLM, trả câu chào cố định
    #
    # ĐÃ A/B và MERGE "fast_llm" (P4A, eval/results/p4a_direct_blind_result.json).
    # Quyết định dựa trên CHẤM MÙ bởi người, không dựa trên evaluator tự động:
    #   context appropriate   A 17/17  vs  C 17/17
    #   tự bịa số liệu HR     A  0/17  vs  C  0/17
    #   p50                   4.969ms  ->  955ms   (5.2x)
    #   p95                  11.523ms  -> 5.199ms
    #   max                 183.841ms  -> 16.707ms
    # Hoà chất lượng -> merge theo decision rule freeze trước, vì latency là
    # bằng chứng độc lập. Riêng con số max đáng nhớ: một câu chào từng mất 183
    # GIÂY ở nhánh GLM.
    #
    # KHÔNG chọn "template" dù nó 0ms: benchmark cho thấy trả một câu cố định
    # cho mọi input làm sai ngữ cảnh ở nhóm cảm ơn/tạm biệt (user nói "cảm ơn"
    # nhận lại lời chào giới thiệu). "greeting" là tên intent của router, nhưng
    # bên trong nó có ít nhất 7 speech act (opening/thanks/acknowledgement/
    # goodbye/thanks_goodbye/capability/casual_social) — xem
    # eval/datasets/p4a_cheap_path_set.json. Template hoá nhóm này sẽ đẻ ra một
    # mini-router bằng từ khoá, đúng thứ vừa bỏ công loại bỏ ở tầng trên.
    #
    # Rollback: đặt lại "default_llm". Cờ này chỉ ảnh hưởng direct_node.
    direct_mode: Literal["template", "fast_llm", "default_llm"] = "fast_llm"
    # clarify: ĐÃ A/B và MERGE (P4A, eval/results/p4a_cheap_paths_ab.json).
    # DeepSeek-V4-Flash + thinking tắt vs GLM-5.2 + thinking bật, 12 câu ambiguous:
    #   pass       11/12 -> 11/12   (hoà)
    #   p50        5.49s -> 1.43s   (3.8x)
    #   6/6 check giống hệt nhau: is_question, no_invented_number, on_topic,
    #   offers_options, concise, non_empty
    # Câu trượt duy nhất (cl_10) trượt ở CẢ HAI variant vì cùng một lý do — suy
    # ra "thử việc" từ "ngày thứ 60" — tức là prompt defect, không phải model.
    # Ghi backlog riêng, cố ý KHÔNG sửa chung commit này để giữ attribution sạch.
    #
    # Rollback: đặt lại clarify_model="" và thinking_clarify=True. Hai cờ này
    # chỉ ảnh hưởng clarify_node, không đụng router/generate/hallucination.
    clarify_model: str = "DeepSeek-V4-Flash"
    thinking_clarify: bool = False

    # Model chấm điểm trong eval — PHẢI khác họ với `llm_model`. Nếu để cùng
    # model vừa sinh dữ liệu, vừa trả lời, vừa chấm thì phần lớn thứ đo được là
    # độ nhất quán của model với chính nó, không phải chất lượng hệ thống
    # (circular evaluation). Llama-3.3-70B khác họ với GLM và phản hồi nhanh.
    judge_model: str = "Llama-3.3-70B-Instruct"
    # Có thể tách credential/quota của judge khỏi traffic chat production.
    # Để trống thì tương thích ngược: dùng FPT_API_KEY/FPT_BASE_URL như trước.
    judge_api_key: str = ""
    judge_base_url: str = ""

    # Agent RAG
    retrieval_top_k: int = 25
    rerank_top_k: int = 10
    use_reranker: bool = True
    # Tên model trên FPT.AI Marketplace (endpoint /rerank) — KHÔNG phải repo id
    # HuggingFace: reranker chạy qua gateway, không tải model về máy.
    reranker_model: str = "bge-reranker-v2-m3"
    # Ngưỡng lọc trên relevance_score 0-1 của reranker (dùng ở grade_node).
    # Đo trên 140 câu eval (eval/results/rerank_score_distribution.json): top-1
    # score của in_scope có median 0.975 / p10 0.490, còn out_of_scope median
    # 0.010 và competitor 0.034 — tách bạch tốt hơn hẳn khoảng cách cosine.
    # 0.05 giữ lại 99% câu in_scope mà vẫn loại 67% câu out_of_scope.
    rerank_min_score: float = 0.05
    # Chỉ dùng khi reranker tắt/lỗi — ngưỡng khoảng cách cosine.
    retrieval_max_distance: float = 0.18
    # Neo cho confidence tính từ distance (nhánh fallback khi không có rerank
    # score) — lấy theo phân phối distance đo thực tế trên bộ eval.
    distance_confidence_near: float = 0.10
    distance_confidence_far: float = 0.22
    # Hybrid retrieval — trộn dense (Chroma) với BM25 local qua RRF trước khi
    # đưa vào reranker. Tắt mặc định để A/B: bật `use_hybrid=True` rồi so
    # Multi-chunk Recall@10 với baseline dense-only (69.1%). Không thêm lệnh
    # gọi mạng nào (BM25 chạy local) nên không đổi latency.
    use_hybrid: bool = False
    bm25_top_k: int = 25
    rrf_k: int = 60

    # Ghi breakdown latency (từng node + từng lệnh gọi mạng) vào dòng `[audit]`
    # của mỗi request. Mặc định TẮT: khi tắt, llm_trace là no-op nên không tốn
    # gì ngoài một lần đọc ContextVar. Bật khi cần điều tra latency trên môi
    # trường thật, nơi không chạy được scripts/profile_agent_latency.py.
    # Chỉ ghi số đo (thời lượng, token đếm được, số lần thử) — không ghi prompt,
    # câu hỏi hay nội dung câu trả lời.
    profile_latency: bool = False

    max_rewrite_retries: int = 1
    max_hallucination_retries: int = 2
    # Escalate khi confidence (= relevance_score của đoạn tốt nhất) dưới ngưỡng.
    # Hạ 0.5 -> 0.2 sau khi bóc tách 29 câu in_scope fail: 7 câu bị escalate oan
    # dù chunk ĐÚNG đã qua được grade, confidence chỉ 0.18-0.49. Theo phân phối
    # score thực đo (eval/results/rerank_score_distribution.json) chỉ 5/100 câu
    # in_scope có top-1 score < 0.2, so với 11/100 ở ngưỡng 0.5.
    #
    # Giá phải trả: out_of_scope lọt qua tăng 2/15 -> 3/15. Chấp nhận được vì
    # (a) router đã chặn nhóm đó trước với recall 0.96, (b) `answerable` ở
    # generate_node (sentinel [KHÔNG_ĐỦ_THÔNG_TIN]) kéo score xuống 0.1 khi
    # context không thực sự trả lời được câu hỏi — đó mới là lớp chặn chính cho
    # nhóm "reranker tự tin vào đoạn sai", vốn có score 0.78-1.00 nên ngưỡng
    # này dù cao tới đâu cũng không bắt được.
    low_confidence_threshold: float = 0.2

    # Guardrail kỹ thuật (src/agents/guardrails.py) — deterministic, không gọi
    # LLM. Toggle riêng cho từng lớp để có thể tắt nhanh nếu đo được false
    # positive trong production, không cần deploy lại code.
    guardrail_injection_enabled: bool = True
    guardrail_pii_redaction_enabled: bool = True

    # Chunking
    chunk_target_chars: int = 1200
    chunk_max_chars: int = 1500
    chunk_min_chars: int = 200

    # Worker (job runner phía Agent — ingestion/index rebuild/evaluation).
    # Contract với Backend: docs/rag-pipeline/AGENT_WORKERS.md.
    #
    # agent_jobs_dir nằm trên đĩa chứ không giữ trong RAM: agent restart giữa
    # chừng thì job đang chạy được đánh dấu FAILED lúc startup, để Backend poll
    # ra trạng thái kết thúc thay vì kẹt QUEUED/PROCESSING vĩnh viễn.
    agent_jobs_dir: str = "./storage/agent_jobs"
    data_dir: str = "./data"
    # Nhãn phiên bản index trả về cho Backend (active_index_version).
    index_version: str = "v1.0"

    # Evaluation worker
    eval_concurrency: int = 3
    eval_datasets_dir: str = "./eval/datasets"
    # Ngưỡng quality gate — vượt hết thì PASSED, thiếu bất kỳ chỉ số nào thì
    # FAILED. Lấy theo mức đang đo được của pipeline hiện tại, hạ biên an toàn.
    eval_gate_recall_at_k: float = 0.80
    eval_gate_answer_correctness: float = 0.70
    eval_gate_citation_coverage: float = 0.90


@lru_cache
def get_settings() -> Settings:
    return Settings()
