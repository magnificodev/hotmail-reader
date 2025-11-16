// TypeScript types for API responses

export interface EmailMessage {
  id: string;
  from_: string;
  to: string[];
  subject: string;
  content: string;
  html?: string;
  date: string;
  otp?: string | null;
}

export interface PageResult {
  items: EmailMessage[];
  next_page_token: string | null;
  total: number | null;
}

export interface MessageBodyResponse {
  id: string;
  subject: string;
  date: string;
  from: string;
  to: string;
  text: string;
  html: string;
}

export interface OtpResponse {
  otp: string | null;
  emailId?: string;
  subject?: string;
  date?: string;
}

export interface DevCredResponse {
  credString: string | null;
}

