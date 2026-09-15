export interface CheckListResponse {
  latest_webp_url: string;
  history: {
    submitted_at: string;
    title: string;
    hours: string;
  }[];
}

export interface SubmitPreviewResponse {
  url: string;
}

export interface SasResponse {
  url: string;
}

export interface ApiError {
  error: string;
  message: string;
}

