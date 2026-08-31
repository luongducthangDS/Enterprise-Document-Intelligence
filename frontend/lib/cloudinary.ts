/**
 * Client-side Cloudinary Upload Helper.
 * Uploads file directly from browser to Cloudinary CDN (without proxying through Backend).
 */

const CLOUDINARY_CLOUD_NAME = process.env.NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME || "";
const CLOUDINARY_UPLOAD_PRESET = process.env.NEXT_PUBLIC_CLOUDINARY_UPLOAD_PRESET || "";
const CLOUDINARY_API_KEY = process.env.NEXT_PUBLIC_CLOUDINARY_API_KEY || "";

export class CloudinaryUploadError extends Error {
  constructor(
    message: string,
    readonly code = "CLOUDINARY_UPLOAD_ERROR",
    readonly status = 0,
  ) {
    super(message);
  }
}

export async function uploadToCloudinary(
  file: File,
  onProgress?: (progressPercent: number) => void,
): Promise<string> {
  if (!CLOUDINARY_CLOUD_NAME) {
    throw new CloudinaryUploadError(
      "Chưa cấu hình NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME trong biến môi trường.",
      "MISSING_CLOUD_NAME",
    );
  }

  const formData = new FormData();
  formData.append("file", file);
  if (CLOUDINARY_UPLOAD_PRESET) {
    formData.append("upload_preset", CLOUDINARY_UPLOAD_PRESET);
  }
  if (CLOUDINARY_API_KEY) {
    formData.append("api_key", CLOUDINARY_API_KEY);
  }

  const uploadUrl = `https://api.cloudinary.com/v1_1/${encodeURIComponent(CLOUDINARY_CLOUD_NAME)}/auto/upload`;

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", uploadUrl);

    if (xhr.upload && onProgress) {
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          const percent = Math.round((event.loaded / event.total) * 100);
          onProgress(percent);
        }
      };
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const res = JSON.parse(xhr.responseText);
          const secureUrl = res.secure_url || res.url;
          if (!secureUrl) {
            reject(new CloudinaryUploadError("Cloudinary không trả về đường dẫn URL hợp lệ."));
            return;
          }
          resolve(secureUrl);
        } catch {
          reject(new CloudinaryUploadError("Dữ liệu phản hồi từ Cloudinary không đúng định dạng."));
        }
      } else {
        let errorMsg = `Upload Cloudinary thất bại (HTTP ${xhr.status})`;
        try {
          const errRes = JSON.parse(xhr.responseText);
          if (errRes.error?.message) {
            errorMsg = `Lỗi Cloudinary: ${errRes.error.message}`;
          }
        } catch {
          // fallback errorMsg
        }
        reject(new CloudinaryUploadError(errorMsg, "UPLOAD_FAILED", xhr.status));
      }
    };

    xhr.onerror = () => {
      reject(new CloudinaryUploadError("Không thể kết nối tới máy chủ Cloudinary. Vui lòng kiểm tra mạng.", "NETWORK_ERROR"));
    };

    xhr.send(formData);
  });
}
