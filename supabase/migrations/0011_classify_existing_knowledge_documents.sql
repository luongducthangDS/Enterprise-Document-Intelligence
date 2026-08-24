-- Classify the existing HR knowledge corpus by intended audience.
-- COMPANY_WIDE: employee-facing policies and public laws.
-- DEPARTMENT: HR operating procedures, templates, and reference material.
-- RESTRICTED: rejected or effectively empty sources that must not enter answers.

update public.documents
set access_scope = 'COMPANY_WIDE',
    authorized_role = null,
    owner_user_id = null,
    updated_at = now()
where source_file in (
  '06_chinh-sach-dao-tao-phat-trien.md',
  '05_chinh-sach-lam-viec-tu-xa.md',
  '08_chinh-sach-bao-hiem-suc-khoe-tu-nguyen.md',
  '01_chinh-sach-lam-them-gio-OT.md',
  'bộ luật lao động.pdf',
  'luat51.pdf',
  'luat_an_toan_ve_sinh_lao_dong_84_2015_qh13.pdf',
  'luat_bao_hiem_xa_hoi_41_2024_qh15.pdf',
  '161-ndcp.signed.pdf',
  'nghi_dinh_145_2020_nd_cp.pdf',
  'nghi_dinh_158_2025_nd_cp_bhxh_bat_buoc.pdf',
  'nghi_dinh_293_2025_nd_cp_luong_toi_thieu.pdf',
  'thong-tu-60-2025-TT-BHYT-2026.pdf',
  '112-vbhn-vpqh_luat_thue_tncn.pdf',
  '07_chinh-sach-nghi-phep.md'
);

update public.documents
set access_scope = 'DEPARTMENT',
    department = 'HR',
    authorized_role = null,
    owner_user_id = null,
    updated_at = now()
where source_file in (
  'leanh_mau-noi-quy-lao-dong.docx',
  'mau_quy-che-danh-gia-hieu-suat-kpi.md',
  'mau_quy-che-dao-tao-va-cam-ket-boi-hoan.md',
  'mau_quy-trinh-ky-luat-lao-dong-va-khieu-nai.md',
  '1050517962-VF-I-4-1-001-V5-Quy-định-nội-bộ-Cong-ty-VinFast-08-08-2019.pdf',
  'base_mau-quy-che-luong-thuong-phu-cap-xu-phat.docx',
  'base_quy-che-cong-tac-phi-va-phu-cap.md',
  '04_quy-trinh-offboarding.md',
  '03_quy-trinh-onboarding.md',
  'talentnet_quy-trinh-cham-dut-hop-dong-lao-dong.md',
  '842059170-18-Nguyễn-Đinh-Hải-Lam-Quy-Trinh-Tuyển-Dụng-Chung-Của-Vingroup.pdf',
  '02_quy-trinh-tuyen-dung.md'
);

update public.documents
set access_scope = 'RESTRICTED',
    authorized_role = null,
    owner_user_id = null,
    updated_at = now()
where source_file in (
  'amis_mau-thong-bao-quy-dinh-nghi-phep.docx',
  '[Base.vn] Mẫu sơ đồ quy trình tuyển dụng nhân sự.docx.pdf',
  '73-cp.signed_KHONG-PHAI-ND161_NĐ73-2024-het-hieu-luc.pdf'
);
