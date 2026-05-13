const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');

function buildUrl(path, query = {}) {
  const url = new URL(`${API_BASE_URL}${path}`);

  Object.entries(query).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') {
      return;
    }
    url.searchParams.set(key, String(value));
  });

  return url.toString();
}

async function parseResponse(response) {
  const contentType = response.headers.get('content-type') || '';
  const isJson = contentType.includes('application/json');
  const data = isJson ? await response.json() : await response.text();

  if (!response.ok) {
    const detail = isJson && data && typeof data === 'object' && 'detail' in data ? data.detail : data;
    let message = 'Request failed.';

    if (typeof detail === 'string') {
      message = detail;
    } else if (detail && typeof detail === 'object') {
      message = detail.message || JSON.stringify(detail);
    }

    const error = new Error(message);
    error.status = response.status;
    error.data = data;
    error.detail = detail;
    throw error;
  }

  return data;
}

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, options);
  return parseResponse(response);
}

export function getApiBaseUrl() {
  return API_BASE_URL;
}

export function getAnalytics() {
  return request('/analytics');
}

export function getTemplate() {
  return request('/upload/template');
}

export function getUploadDetails(uploadId) {
  return request(`/uploads/${uploadId}`);
}

export function getReports(filters) {
  const url = buildUrl('/reports', filters);
  return fetch(url).then(parseResponse);
}

export function uploadCsv(file) {
  const formData = new FormData();
  formData.append('file', file);

  return request('/upload', {
    method: 'POST',
    body: formData
  });
}
