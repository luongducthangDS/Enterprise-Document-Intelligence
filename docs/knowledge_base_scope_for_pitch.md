# Knowledge Base Scope for Pitch

## Product Positioning

San pham nen duoc pitch la **HR Policy Copilot / HR Helpdesk Assistant** cho mot khoa hoc, tap trung vao viec tra loi cau hoi nhan su lap lai, tra cuu chinh sach chung va escalate dung bo phan khi cau hoi vuot pham vi.

Khong nen pitch nhu mot **HR system day du** hoac mot assistant co kha nang tra loi tat ca van de nhan su cua mot cong ty cu the.

Thong diep chinh:

> Knowledge base cua he thong duoc gioi han co chu dich o cac chinh sach HR pho bien va van ban phap luat tham khao. Voi cau hoi can du lieu ca nhan, can xac minh HR, hoac co rui ro phap ly, agent khong tu suy doan ma tao ticket/escalate den dung bo phan HR.

## Pitch-Safe Naming

De tranh rui ro thuong hieu, trong slide/demo khong nen noi "day la chinh sach cua VinGroup/VinFast" hoac gan dataset voi mot cong ty cu the.

Nen dung cach goi an toan hon:

- "tai lieu tham khao tu mot tap doan lon tai Viet Nam"
- "internal policy reference document"
- "enterprise HR reference material"
- "sample corporate policy corpus"

Neu can noi ve nguon, chi nen noi:

> Mot phan knowledge base gom tai lieu tham khao dang corporate policy cua mot tap doan lon tai Viet Nam; he thong khong khang dinh day la chinh sach dang ap dung cua bat ky cong ty cu the nao.

## What The Current Knowledge Base Contains

Bo du lieu trong `data/` bao gom cac nhom tai lieu chinh:

- Chinh sach nghi phep.
- Chinh sach lam them gio/OT.
- Chinh sach lam viec tu xa/hybrid.
- Quy trinh tuyen dung.
- Quy trinh onboarding.
- Quy trinh offboarding/cham dut hop dong lao dong.
- Chinh sach dao tao va phat trien.
- Chinh sach bao hiem suc khoe tu nguyen.
- Quy che luong, thuong, phu cap, cong tac phi.
- Quy che KPI/danh gia hieu suat.
- Quy trinh ky luat lao dong va khieu nai.
- Van ban phap luat ve lao dong, BHXH, BHYT, thue TNCN, luong toi thieu.
- Cau hinh routing ticket sang cac bo phan HR nhu C&B, ER, TA, L&D, HRBP.

## Important Data Caveats

Day la diem can noi ro trong pitch de tranh pham vi bi mo ho:

- Nhieu tai lieu noi bo trong dataset la **synthetic/template**, khong phai chinh sach that cua mot doanh nghiep cu the.
- Mot so tai lieu la template cong khai, chi nen dung de minh hoa cau truc quy trinh/chinh sach.
- Cac van ban phap luat la nguon tham khao tot hon, nhung khi dung trong production van can quy trinh cap nhat va xac minh hieu luc.
- Mot so tai lieu co nguon/tham chieu tu mot tap doan lon tai Viet Nam nen duoc trinh bay la **tai lieu tham khao dang corporate policy**, khong gan thanh chinh sach dang ap dung cho mot cong ty cu the.
- Cac tai lieu tham khao nay co the la ban cu hoac khong ro thoi hieu, can xac minh ban cap nhat truoc khi dung cho cau hoi hien tai.
- Knowledge base khong chua du lieu HRIS/payroll ca nhan, vi vay khong the tra loi cac cau hoi ve so du phep, trang thai don, bang luong, thuong hoac bao hiem cua mot ca nhan cu the.

## In Scope

He thong co the xu ly tot cac nhom cau hoi sau trong demo/MVP:

| Capability | Mo ta |
|---|---|
| Policy Q&A | Tra loi cau hoi chung ve nghi phep, OT, WFH, onboarding, offboarding, tuyen dung, dao tao, bao hiem suc khoe. |
| Legal reference | Tra cuu va tom tat cac quy dinh phap luat lao dong/BHXH/BHYT/thue o muc tham khao. |
| Procedure guidance | Huong dan cac buoc dang ky nghi phep, dang ky OT, WFH, claim bao hiem, nghi viec, onboarding. |
| Role-based answers | Dieu chinh cach tra loi cho employee, manager, HR admin neu co context vai tro. |
| Source-aware answers | Dua caveat khi nguon la synthetic, template, public article, hoac chinh sach cu can xac minh. |
| Ticket routing | Phan loai cau hoi va escalate sang C&B, ER, TA, L&D hoac HRBP. |
| Low-confidence handling | Neu khong tim thay cau tra loi chac chan trong KB, agent nen thua nhan gioi han va tao ticket. |
| MVP evaluation | Do accuracy, refusal quality va routing accuracy tren bo test nho truoc demo. |

## Agentic Behavior In MVP

De tranh bi judge nhin nhu "chatbot RAG + router", can pitch ro cac hanh vi agentic dang co trong MVP:

| Agentic capability | Cach the hien trong demo |
|---|---|
| Intent analysis | Agent tu phan loai greeting, HR question, ambiguous, personal/out-of-scope. |
| Retrieval planning | Agent chi retrieve khi cau hoi du ro va co the tra loi bang policy chung. |
| Source-grounded generation | Agent chi tra loi dua tren doan trich, kem citation va caveat nguon. |
| Self-check | Agent co hallucination check/confidence check truoc khi finalize. |
| Escalation decision | Agent quyet dinh khi nao khong nen tra loi va can tao ticket draft. |
| Ticket routing | Agent chon bo phan xu ly phu hop: C&B, ER, TA, L&D, HRBP. |
| Clarification | Agent hoi lai khi cau hoi mo ho thay vi doan y user. |

Nen noi thang gioi han:

> In this MVP, the agent does not yet execute live HR transactions. Its agentic behavior is decision-making around retrieval, grounding, clarification, refusal, and ticket routing. Live ticket creation and status tracking are the next integration step.

Ban tieng Viet:

> Trong MVP nay, agent chua thuc hien giao dich HR truc tiep tren HRIS/payroll. Tinh agentic nam o viec tu quyet dinh retrieve hay hoi lai, tu kiem tra grounding/confidence, tu choi khi vuot pham vi, va tao ticket draft den dung bo phan. Ket noi ticket system/HRIS that la buoc tich hop tiep theo.

## Out Of Scope

He thong khong nen tu tra loi cac truong hop sau:

| Out of scope | Ly do |
|---|---|
| So du phep cua mot nhan vien cu the | Can du lieu HRIS ca nhan. |
| Trang thai don nghi phep/OT/WFH/claim bao hiem | Can ket noi workflow/system that. |
| Luong, thuong, khau tru, thue TNCN ca nhan | Can payroll va du lieu thu nhap ca nhan. |
| Ket qua phong van/offer cua ung vien cu the | Can ATS hoac du lieu tuyen dung noi bo. |
| Quyet dinh ky luat/cham dut hop dong cu the | Rui ro phap ly, can HR/Legal xac minh. |
| Tu van phap ly cuoi cung cho tranh chap lao dong | Agent chi nen cung cap tham khao va escalate. |
| Khẳng định chinh sach dang ap dung cho mot cong ty cu the | Dataset co nhieu synthetic/template, tai lieu tham khao va tai lieu cu. |
| Cap nhat phap ly moi nhat neu KB chua duoc refresh | Can quy trinh update/verify nguon phap ly. |

## Recommended User Stories For Demo

### Employee

- La nhan vien, toi muon hoi minh duoc bao nhieu ngay phep nam, de biet quyen nghi phep theo tham nien va loai cong viec.
- La nhan vien, toi muon biet quy trinh xin nghi phep tren HRIS, de nop don dung han.
- La nhan vien, toi muon hoi nghi cuoi, nghi tang, nghi khong luong co duoc huong luong khong.
- La nhan vien, toi muon biet lam OT vao ngay thuong, cuoi tuan, ngay le duoc tinh nhu the nao.
- La nhan vien, toi muon biet minh co du dieu kien WFH/hybrid khong.
- La nhan vien, toi muon biet WFH dot xuat can thong bao truoc khi nao.
- La nhan vien, toi muon biet goi bao hiem suc khoe tu nguyen co ap dung cho minh khong.
- La nhan vien, toi muon biet thu tuc claim bao hiem khi da ung tien vien phi.
- La nhan vien, toi muon biet neu nghi viec thi phai bao truoc bao lau.
- La nhan vien, toi muon biet sau khi nghi viec bao lau duoc thanh toan cac che do con lai.
- La nhan vien, toi muon biet neu nghi sau khoa hoc chi phi cao thi co phai boi hoan khong.

### Manager

- La quan ly, toi muon biet quy trinh phe duyet OT, de dam bao nhan vien khong vuot gio theo quy dinh.
- La quan ly, toi muon biet checklist onboarding 30-60-90 ngay, de ho tro nhan vien moi.
- La quan ly, toi muon biet khi nao co the thu hoi quyen WFH cua nhan vien.
- La hiring manager, toi muon tao yeu cau tuyen dung va biet luong phe duyet headcount.
- La quan ly, toi muon biet vai tro cua minh trong offboarding va ban giao tai san/cong viec.

### HR / Admin

- La HR, toi muon agent tra loi cac cau hoi chinh sach lap lai, de giam tai cho HR helpdesk.
- La HR, toi muon agent tu dong phan loai ticket sang C&B, ER, TA, L&D hoac HRBP.
- La HR, toi muon agent escalate khi cau hoi can du lieu ca nhan hoac co rui ro phap ly.
- La HR admin, toi muon cau tra loi co source/caveat, de tranh nham lan giua chinh sach noi bo, tai lieu tham khao, template va synthetic data.
- La HR admin, toi muon theo doi cac cau hoi low-confidence, de biet can bo sung knowledge base nao.

## Escalation Rules

Agent nen escalate thay vi tu tra loi khi:

- Cau hoi can du lieu ca nhan: so du phep, bang luong, thue, trang thai don, trang thai claim, offer ca nhan.
- Cau hoi lien quan tranh chap, khieu nai, quay roi, ky luat, cham dut hop dong.
- Cau hoi co anh huong truc tiep den thu nhap da nhan hoac quyen loi phap ly.
- Cau hoi nam ngoai tai lieu hien co.
- Cau hoi co nguon tai lieu cu, synthetic/template, hoac chua ro hieu luc.
- User yeu cau gap nguoi that.

Routing goi y:

| Category | Department |
|---|---|
| Luong, thue, OT, phu cap, BHXH/BHYT, cham cong | C&B |
| Nghi phep, so du phep, trang thai don | C&B |
| Khieu nai, mau thuan, ky luat, quay roi, tranh chap | ER |
| Tuyen dung, phong van, offer, gioi thieu ung vien | TA |
| Onboarding/offboarding, nghi viec, ban giao | ER hoac HRBP tuy tinh huong |
| Dao tao, cam ket boi hoan, lo trinh phat trien | L&D |
| Cau hoi khong khop ro | HRBP |

## Demo Boundary Statement

Co the dua nguyen van nay vao slide pitch:

> In this MVP, the HR AI Assistant focuses on policy Q&A and routing, not personal HR transactions. It answers common questions using a curated HR knowledge base, cites or caveats its source, and escalates to the right HR team when the request requires personal data, legal judgment, or system access.

Ban tieng Viet:

> Trong MVP nay, HR AI Assistant tap trung vao hoi dap chinh sach va dieu phoi yeu cau, khong thay the he thong HRIS/payroll. Agent tra loi cac cau hoi HR pho bien dua tren knowledge base da curate, neu ro gioi han cua nguon, va escalate den dung bo phan khi cau hoi can du lieu ca nhan, can danh gia phap ly, hoac can truy cap he thong noi bo.

## MVP Evaluation

Eval khong nen de o roadmap. Nen co mot bo test nho ngay trong MVP de chung minh he thong dang duoc kiem soat.

Bo test de pitch co the gom 30-50 cau:

| Metric | Muc tieu demo | Vi du test |
|---|---|---|
| Policy answer accuracy | Cau tra loi dung theo nguon va co citation | "OT Chu nhat tinh bao nhieu phan tram?" |
| Refusal quality | Tu choi/escalate dung khi can du lieu ca nhan | "Luong thang nay cua toi bi tru bao nhieu?" |
| Routing accuracy | Ticket draft di dung bo phan | Luong/OT -> C&B, khieu nai -> ER, dao tao -> L&D |
| Clarification quality | Hoi lai khi cau hoi mo ho | "Khi nao toi duoc nhan thuong?" |
| Source caveat quality | Canh bao dung khi nguon la template/synthetic/reference | "Chinh sach KPI nhu the nao?" |

Thong diep voi judge:

> Because this is an enterprise HR use case, we evaluate not only answer correctness, but also refusal quality, escalation routing, and source caveat behavior.

## Suggested Pitch Framing

Nen noi san pham giai quyet 3 van de:

1. Giam tai cho HR bang cach tu dong tra loi cau hoi lap lai.
2. Tang tinh nhat quan cua cau tra loi vi dua tren knowledge base co cau truc.
3. Kiem soat rui ro bang co che caveat va escalation.

Khong nen noi san pham:

- Thay the HR.
- Tra loi moi cau hoi phap ly/nhan su.
- Co du lieu ca nhan that.
- La chinh sach chinh thuc/dang ap dung cua mot cong ty cu the.

## Roadmap After MVP

Neu muon mo rong sau pitch:

- Ket noi HRIS de xem so du phep, trang thai don, lich su cham cong.
- Ket noi payroll de giai thich bang luong ca nhan co kiem soat quyen truy cap.
- Them admin dashboard de quan ly nguon tai lieu, version, ngay hieu luc.
- Them approval workflow cho ticket va human-in-the-loop.
- Them co che cap nhat van ban phap luat dinh ky.
