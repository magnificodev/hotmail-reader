// Centralized API configuration and utilities

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const API_ENDPOINTS = {
  MESSAGES: `${API_BASE_URL}/messages`,
  MESSAGE: `${API_BASE_URL}/message`,
  OTP: `${API_BASE_URL}/otp`,
  DEV_CRED: `${API_BASE_URL}/dev/cred`,
} as const;

export async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const response = await fetch(endpoint, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  if (!response.ok) {
    const text = await response.text();
    throw { status: response.status, text };
  }

  return response.json();
}

