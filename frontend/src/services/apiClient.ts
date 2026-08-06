import axios, { AxiosError } from "axios";

export interface ApiError {
  status?: number;
  message: string;
  details?: unknown;
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

const API_KEY = import.meta.env.VITE_API_KEY;

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: API_KEY ? { "X-API-Key": API_KEY } : {},
});

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    const normalized = normalizeApiError(error);
    return Promise.reject(normalized);
  }
);

export function normalizeApiError(error: unknown): ApiError {
  if (axios.isAxiosError(error)) {
    const status = error.response?.status;
    const data = error.response?.data as any;
    const message =
      data?.detail ||
      data?.message ||
      error.message ||
      "Request failed";

    return { status, message, details: data };
  }

  if (error instanceof Error) {
    return { message: error.message };
  }

  return { message: "Unexpected error" };
}
