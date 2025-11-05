// Application constants

export const ITEMS_PER_PAGE = 15;
export const MAX_PAGE_SIZE = 50;
export const OTP_BUFFER_MULTIPLIER = 3; // For OTP filter, load more items to account for filtering

export const POKEMON_FILTER_EMAIL = "info@pokemoncenter-online.com";

export const MESSAGES = {
  LOADING: "Đang tải...",
  LOADING_MORE: "Đang tải thêm email...",
  LOADING_EMAILS: "Đang tải email...",
  SUCCESS_COPY: "Đã copy OTP vào clipboard",
  ERROR_COPY: "Không copy được OTP",
  NO_DATA: "Chưa có dữ liệu. Nhấn \"Đọc mail\" để tải.",
  NO_OTP_EMAILS: "Không có email nào có OTP.",
  ERROR_SERVER: "Không thể kết nối máy chủ",
  ERROR_UNKNOWN: "Đã xảy ra lỗi không xác định",
} as const;

