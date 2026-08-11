# GIT FLOW – ROLE & QUY CHUẨN

Quy trình hợp tác & phát triển phần mềm chuyên nghiệp với Git Flow.

> ⭐ **QUY TẮC VÀNG:** Mỗi lần commit và trước khi PR/merge phải rebase về 1 commit duy nhất. Nếu có merge vào nhánh bản thân, commit của bản thân luôn ở đầu tiên (mới nhất).

---

## 1. ROLES – Vai trò & Trách nhiệm

### Product Owner (PO)
- Xác định yêu cầu, ưu tiên tính năng
- Quản lý Product Backlog
- Nghiệm thu sản phẩm

### Developer (DEV)
- Phát triển tính năng/BUG
- Tạo branch theo quy định
- Commit code & Push
- Tạo Pull Request

### Code Reviewer (REVIEWER)
- Review code
- Đảm bảo code quality
- Kiểm tra theo tiêu chuẩn
- Approve / Request change

### QA / Tester (QA)
- Kiểm thử tính năng
- Kiểm thử trên môi trường staging
- Báo cáo BUG

### Release Manager (RELEASE)
- Tạo release / quản lý version
- Deploy production
- Quản lý hotfix

---

## 2. GIT FLOW – Mô hình nhánh

| Nhánh | Vai trò |
|---|---|
| `main` | Nhánh chính – Production (ổn định nhất) |
| `develop` | Nhánh phát triển (tích hợp tính năng) |
| `feature/*` | Nhánh tính năng (từ develop) |
| `release/*` | Nhánh release (chuẩn bị phát hành) |
| `hotfix/*` | Nhánh sửa lỗi khẩn cấp (từ main) |

---

## 3. WORKFLOW – Quy trình

1. **Tạo feature branch** – từ develop: `git checkout -b feature/ten-tinh-nang`
2. **Phát triển & Commit** – code theo quy chuẩn, commit thường xuyên
3. **Rebase branch cá nhân (BẮT BUỘC)** – trước khi tạo PR: rebase develop, squash 1 commit
4. **Tạo Pull Request** – push branch lên remote và tạo PR lên develop
5. **Review Code** – reviewer kiểm tra và Approve / Request changes
6. **Merge vào develop** – sau khi Approved, merge PR vào develop
7. **Tạo Release** – tạo release/* từ develop, QA kiểm thử
8. **Release lên Production** – merge release/* vào main và develop, tag version
9. **Hotfix (nếu có)** – tạo hotfix/* từ main, fix và merge lại main & develop

---

## 4. REBASE & SQUASH – Quy tắc bắt buộc

- ✅ Mỗi lần commit và trước khi PR/merge, phải rebase về 1 commit duy nhất.
- ✅ Nếu có merge vào nhánh bản thân, commit của bản thân luôn ở đầu tiên (commit mới nhất).
- ✅ Không merge develop vào feature. Chỉ rebase develop.

### Ví dụ thực tế

Trước rebase (nhiều commit trên `feature/login`): `A - B - C - D - E`

Sau rebase + squash (trước khi PR/merge): `E (squash)`

### Lệnh tham khảo

```bash
git checkout feature/login
# Cập nhật develop mới nhất
git fetch origin
git rebase origin/develop
# Squash tất cả commit thành 1 commit
git rebase -i HEAD~N
# (giữ lại 1 commit, squash các commit còn lại)
# Push lại branch (bắt buộc force-with-lease)
git push --force-with-lease
```

---

## 5. GIT HISTORY & REBASE POLICY – Quy chuẩn lịch sử Git

### Nguyên tắc
- ✅ Mỗi task chỉ có 1 commit cuối cùng trước khi merge.
- ✅ Trước khi tạo PR:
  - Rebase về branch đích mới nhất
  - Squash toàn bộ commit
- ✅ Không merge develop vào feature (không tạo merge commit).
- ✅ Ưu tiên Linear History.

### Ví dụ lịch sử
1. Lịch sử khi làm việc: `feature/login: A - B - C - D - E`
2. Sau rebase + squash: `feature/login: E (squash)`

> **Commit của bạn luôn ở đầu tiên (mới nhất):**
> - Commit của develop ở bên dưới (lịch sử cũ)
> - Commit của feature luôn là commit mới nhất
> - Không được tạo merge commit

### KHÔNG LÀM
- ❌ git merge develop
- ❌ Tạo merge commit không cần thiết
- ❌ Để PR có quá nhiều commit lộn xộn
- ❌ Push PR khi chưa rebase & squash

Ví dụ commit xấu: `fix - update - fix bug - fix again - update - test`

### Quy tắc khi có merge vào nhánh bản thân

Giả sử `develop` có thêm commit B, C trong lúc bạn đang làm A:

**Trước rebase:**
```
develop:        ... — B — C
feature/login:  A
```

**Sau rebase:**
```
develop:        ... — B — C
feature/login:  C — A (mới nhất)
```

Kết quả: A luôn ở đầu tiên (trên cùng).

---

## 6. QUY CHUẨN & TIÊU CHUẨN

### 6.1 Tên nhánh
- `feature/ten-tinh-nang`
- `bugfix/ten-bug`
- `release/x.y.z`
- `hotfix/ten-bug`
- `chore/ten-cong-viec`

Quy tắc đặt tên:
- Tất cả chữ thường, dùng dấu `-`
- Không dùng khoảng trắng
- Ngắn gọn, rõ ràng

### 6.2 Quy ước commit

Format: `<type>(<scope>): <subject>`
- `<body>` (nếu cần)
- `<footer>` (nếu cần)

Type:
- `feat`: Tính năng mới
- `fix`: Sửa lỗi
- `docs`: Tài liệu
- `style`: Format code (không thay đổi logic)
- `refactor`: Refactor code
- `test`: Thêm/sửa test
- `chore`: Công việc khác

### 6.3 Ví dụ commit

```
feat(auth): add login with google
fix(user): fix bug update profile
docs(readme): update installation guide
refactor(cart): optimize calculate total
test(order): add unit test for payment
chore(deps): update dependency
```

### 6.4 Pull Request
- Tiêu đề rõ ràng, ngắn gọn
- Mô tả chi tiết:
  - Mục đích thay đổi
  - Những thay đổi chính
  - Ảnh hưởng (nếu có)
  - Screenshots (nếu cần)
- Link issue liên quan (Jira, Trello, ...)
- Đảm bảo CI pass
- Được ít nhất 1 reviewer approve

### 6.5 Code Review
- ✅ Đúng yêu cầu
- ✅ Code dễ đọc, dễ hiểu
- ✅ Tuân thủ coding convention
- ✅ Không code trùng lặp
- ✅ Xử lý lỗi hợp lý
- ✅ Hiệu năng & bảo mật
- ✅ Có test (nếu cần)

---

## 7. NHỮNG ĐIỀU NÊN LÀM (DO)

- ✅ Rebase branch hàng ngày
- ✅ Squash commit trước khi tạo PR
- ✅ Dùng `git push --force-with-lease`
- ✅ Viết commit message rõ ràng
- ✅ Review kỹ trước khi merge
- ✅ Giữ lịch sử git sạch (Linear History)

## 8. NHỮNG ĐIỀU KHÔNG NÊN LÀM (DON'T)

- ❌ Merge develop vào feature branch
- ❌ Để PR có quá nhiều commit kiểu fix, update, test...
- ❌ Tạo merge commit không cần thiết
- ❌ Push PR khi chưa rebase & squash
- ❌ Commit message chung chung, không rõ ràng

---

## 📌 GHI CHÚ QUAN TRỌNG

Tuân thủ quy chuẩn này giúp chúng ta có lịch sử git sạch, dễ đọc, dễ review, dễ rollback và dễ bảo trì hệ thống.
