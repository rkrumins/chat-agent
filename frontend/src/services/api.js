import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Collections API
export const collectionsAPI = {
  list: async () => {
    const response = await api.get('/collections');
    return response.data;
  },

  create: async (collectionData) => {
    const response = await api.post('/collections', collectionData);
    return response.data;
  },

  delete: async (collectionName) => {
    const response = await api.delete(`/collections/${collectionName}`);
    return response.data;
  },
};

// Documents API
export const documentsAPI = {
  list: async (collectionName, skip = 0, limit = 100) => {
    const response = await api.get(
      `/collections/${collectionName}/documents`,
      { params: { skip, limit } }
    );
    return response.data;
  },

  get: async (collectionName, documentId) => {
    const response = await api.get(
      `/collections/${collectionName}/documents/${documentId}`
    );
    return response.data;
  },

  create: async (collectionName, documentData) => {
    const response = await api.post(
      `/collections/${collectionName}/documents`,
      documentData
    );
    return response.data;
  },

  uploadFile: async (collectionName, formData) => {
    const response = await api.post(
      `/collections/${collectionName}/documents/upload`,
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    );
    return response.data;
  },

  update: async (collectionName, documentId, updateData) => {
    const response = await api.put(
      `/collections/${collectionName}/documents/${documentId}`,
      updateData
    );
    return response.data;
  },

  delete: async (collectionName, documentId) => {
    const response = await api.delete(
      `/collections/${collectionName}/documents/${documentId}`
    );
    return response.data;
  },

  search: async (collectionName, query, nResults = 5) => {
    const response = await api.post(
      `/collections/${collectionName}/search`,
      null,
      { params: { query, n_results: nResults } }
    );
    return response.data;
  },
};

// Tasks API
export const tasksAPI = {
  getStatus: async (taskId) => {
    const response = await api.get(`/tasks/${taskId}/status`);
    return response.data;
  },

  list: async (status = null) => {
    const params = status ? { status } : {};
    const response = await api.get('/tasks', { params });
    return response.data;
  },
};

// Health check
export const healthCheck = async () => {
  const response = await api.get('/health');
  return response.data;
};

export default api;

