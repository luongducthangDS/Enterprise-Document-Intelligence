"""
Script to synchronize document titles from Chroma collections and registries
into the PostgreSQL / Supabase `documents` table to eliminate "Tài liệu không tên".
"""

import asyncio
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure backend and root are in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.domain.models.documents import DocumentDB
from src.config import get_settings
from src.ingestion.indexer import get_chroma_client

# Canonical dictionary for well-known source files to guarantee beautiful Vietnamese titles
KNOWN_TITLES: dict[str, str] = {
    "01_chinh-sach-lam-them-gio-OT.md": "Chính sách Làm thêm giờ (Overtime - OT)",
    "02_quy-trinh-tuyen-dung.md": "Quy trình Tuyển dụng Nhân sự",
    "03_quy-trinh-onboarding.md": "Quy trình Tiếp nhận Nhân sự mới (Onboarding)",
    "04_quy-trinh-offboarding.md": "Quy trình Bàn giao và Thôi việc (Offboarding)",
    "05_chinh-sach-lam-viec-tu-xa.md": "Chính sách Làm việc từ xa (Work From Home / Remote)",
    "06_chinh-sach-dao-tao-phat-trien.md": "Chính sách Đào tạo và Phát triển Năng lực",
    "07_chinh-sach-nghi-phep.md": "Chính sách Nghỉ phép và Nghỉ lễ",
    "08_chinh-sach-bao-hiem-suc-khoe-tu-nguyen.md": "Chính sách Bảo hiểm Sức khỏe Tự nguyện",
    "09_chinh-sach-bao-hiem-xa-hoi-bat-buoc.md": "Chính sách Bảo hiểm Xã hội Bắt buộc",
    "10_chinh-sach-an-toan-ve-sinh-lao-dong.md": "Chính sách An toàn và Vệ sinh Lao động",
    "11_chinh-sach-danh-gia-hieu-suat-kpi.md": "Chính sách Đánh giá Hiệu suất và KPI",
    "12_quy-che-cong-tac-phi.md": "Quy chế Công tác phí và Tiếp khách",
    "13_noi-quy-lao-dong-va-ky-luat.md": "Nội quy Lao động và Kỷ luật",
    "bod_mm_01_hop-giao-ban-ban-giam-doc-082026.md": "Biên bản Họp Giao ban Ban Giám đốc (08/2026)",
    "eng_sop_01_quy-trinh-oncall-xu-ly-su-co.md": "Quy trình Trực On-call và Xử lý Sự cố Kỹ thuật",
    "fin_mm_01_hop-kiem-toan-noi-bo-cong-tac-phi.md": "Biên bản Họp Kiểm toán Nội bộ về Công tác phí",
    "fin_sop_01_tam-ung-quyet-toan-cong-tac-phi.md": "Quy trình Tạm ứng và Quyết toán Công tác phí",
    "hr_mm_01_hop-hoi-dong-tuyen-dung-dai-ngo-q3.md": "Biên bản Họp Hội đồng Tuyển dụng & Đãi ngộ Q3",
    "it_sop_01_cap-phat-thu-hoi-tai-khoan-thiet-bi.md": "Quy trình Cấp phát và Thu hồi Tài khoản, Thiết bị IT",
    "luat51.pdf": "Bộ luật Lao động số 45/2019/QH14 & Quy định liên quan",
    "13-QD-ABC_Quy-Che-Chi-Tieu-Noi-Bo-Han-Muc-Duyet-Chi.docx": "Quy chế Chi tiêu Nội bộ và Hạn mức Duyệt chi",
    "BBGN-01-2026_Bien-Ban-Giao-Nhan-TSCD.jpg": "Biên bản Giao nhận Tài sản Cố định",
    "BC-QTCP-Q3-2026_CongtyABC.docx": "Báo cáo Quyết toán Chi phí Q3/2026",
    "DNTT-2026-08-015_Giay-De-Nghi-Thanh-Toan.png": "Giấy Đề nghị Thanh toán",
    "HDDT-GTGT-00000089_Hoa-Don-Gia-Tri-Gia-Tang.png": "Hóa đơn Giá trị Gia tăng (VAT)",
    "PO-2026-0810_Don-Dat-Hang.pdf": "Đơn Đặt hàng (Purchase Order)",
    "PR-2026-0801_Phieu-De-Nghi-Mua-Hang_v2.pdf": "Phiếu Đề nghị Mua hàng (Purchase Request)",
    "QC-LTK-01_Quy-che-Luong-Thuong-KPI-HoaHong.docx": "Quy chế Lương thưởng, KPI và Hoa hồng",
    "SOP-MS-01_Quy-Trinh-Mua-Sam-Va-Lua-Chon-NCC.pdf": "Quy trình Mua sắm và Lựa chọn Nhà cung cấp",
    "SOP-TCKT-01_Quy-Trinh-Tam-Ung-Va-Thanh-Toan.pdf": "Quy trình Tạm ứng và Thanh toán",
}


def clean_slug_to_title(name: str) -> str:
    stem = os.path.splitext(name)[0]
    clean = re.sub(r"^\d+[\-_]?", "", stem)
    clean = clean.replace("-", " ").replace("_", " ").strip()
    return clean.title() if clean else stem


async def sync_titles():
    print("=== STARTING DOCUMENT TITLE SYNCHRONIZATION ===")
    settings = get_settings()
    chroma_client = get_chroma_client(settings)
    
    # 1. Harvest titles from Chroma metadata
    chroma_titles: dict[str, str] = {}
    for col in chroma_client.list_collections():
        try:
            count = col.count()
            if count == 0:
                continue
            data = col.get(include=["metadatas"])
            for meta in data.get("metadatas") or []:
                sf = meta.get("source_file")
                t = meta.get("title")
                if sf and t and sf not in chroma_titles:
                    if not re.match(r"^[0-9a-zA-Z\-_]+$", str(t)):
                        chroma_titles[sf] = str(t)
        except Exception as e:
            print(f"Warning reading collection {col.name}: {e}")

    print(f"Extracted {len(chroma_titles)} meaningful titles from Chroma metadata.")

    # 2. Update Database Documents
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(DocumentDB))
        docs = result.scalars().all()
        print(f"Found {len(docs)} documents in database.")
        
        updated_count = 0
        for doc in docs:
            sf = doc.source_file
            current_title = doc.title
            
            new_title = None
            if sf in KNOWN_TITLES:
                new_title = KNOWN_TITLES[sf]
            elif sf in chroma_titles:
                new_title = chroma_titles[sf]
            elif current_title in (None, "", "Tài liệu không tên"):
                new_title = clean_slug_to_title(sf)
                
            if new_title and (current_title in (None, "", "Tài liệu không tên") or current_title != new_title):
                doc.title = new_title
                updated_count += 1
                safe_t = new_title.encode("ascii", "replace").decode("ascii")
                print(f"  [UPDATED] {sf} -> {safe_t}")

        await session.commit()
        print(f"Successfully updated {updated_count} documents in PostgreSQL database.")
    print("=== SYNC COMPLETED SUCCESSFULLY ===")


if __name__ == "__main__":
    asyncio.run(sync_titles())
