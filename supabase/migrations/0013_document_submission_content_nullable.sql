-- QA-08: `document_submissions.file_content` bị khai báo NOT NULL ở migration 0012,
-- nhưng luồng nộp tài liệu qua URL (`POST /document-submissions/from-url`) cố ý
-- không lưu bytes: tệp nằm trên storage và chỉ `public_url` được giữ lại.
-- ORM (`DocumentSubmissionDB.file_content`) đã là nullable, nên test chạy trên
-- SQLite vẫn pass trong khi Supabase dựng từ migration sẽ chặn insert.
-- Nới ràng buộc để schema khớp với ORM và với hành vi thật của service.

alter table public.document_submissions
  alter column file_content drop not null;
