/**
 * API endpoint functions for FreshCart.
 *
 * Each function returns a promise from the shared Axios client.
 * Organized by domain: auth, products, stores, orders, cart, payments.
 */

import apiClient from "./client";

// ── Authentication ───────────────────────────────────

export const authApi = {
  login: (credentials) => apiClient.post("/auth/login/", credentials),

  register: (data) => apiClient.post("/auth/register/", data),

  refreshToken: (refresh) =>
    apiClient.post("/auth/token/refresh/", { refresh }),

  getProfile: () => apiClient.get("/auth/profile/"),

  updateProfile: (data) => apiClient.patch("/auth/profile/", data),

  changePassword: (data) =>
    apiClient.post("/auth/profile/change-password/", data),

  getAddresses: () => apiClient.get("/auth/addresses/"),

  addAddress: (data) => apiClient.post("/auth/addresses/", data),

  updateAddress: (id, data) => apiClient.patch(`/auth/addresses/${id}/`, data),

  deleteAddress: (id) => apiClient.delete(`/auth/addresses/${id}/`),
};

// ── Products ─────────────────────────────────────────

export const productsApi = {
  list: (params) => apiClient.get("/products/", { params }),

  detail: (id) => apiClient.get(`/products/${id}/`),

  search: (params) => apiClient.get("/products/search/", { params }),

  featured: () => apiClient.get("/products/featured/"),

  onSale: () => apiClient.get("/products/on_sale/"),

  byStore: (storeId, params) =>
    apiClient.get(`/products/store/${storeId}/`, { params }),

  categories: () => apiClient.get("/products/categories/"),

  categoryDetail: (id) => apiClient.get(`/products/categories/${id}/`),

  reviews: (productId) => apiClient.get(`/products/${productId}/reviews/`),

  addReview: (productId, data) =>
    apiClient.post(`/products/${productId}/reviews/`, data),
};

// ── Stores ───────────────────────────────────────────

export const storesApi = {
  list: (params) => apiClient.get("/stores/", { params }),

  detail: (id) => apiClient.get(`/stores/${id}/`),

  nearby: (params) => apiClient.get("/stores/nearby/", { params }),

  categories: () => apiClient.get("/stores/categories/"),

  operatingHours: (id) => apiClient.get(`/stores/${id}/operating_hours/`),

  myStores: () => apiClient.get("/stores/my-stores/"),

  create: (data) => apiClient.post("/stores/", data),

  update: (id, data) => apiClient.patch(`/stores/${id}/`, data),

  analytics: (id) => apiClient.get(`/stores/${id}/analytics/`),
};

// ── Orders ───────────────────────────────────────────

export const ordersApi = {
  list: (params) => apiClient.get("/orders/", { params }),

  detail: (id) => apiClient.get(`/orders/${id}/`),

  create: (data) => apiClient.post("/orders/", data),

  active: () => apiClient.get("/orders/active/"),

  cancel: (id, data) => apiClient.post(`/orders/${id}/cancel/`, data),

  rate: (id, data) => apiClient.post(`/orders/${id}/rate/`, data),

  tracking: (id) => apiClient.get(`/orders/${id}/tracking/`),

  accept: (id) => apiClient.post(`/orders/${id}/accept/`),

  reject: (id, data) => apiClient.post(`/orders/${id}/reject/`, data),

  updateStatus: (id, data) =>
    apiClient.post(`/orders/${id}/update-status/`, data),

  storeOrders: (params) =>
    apiClient.get("/orders/store-orders/", { params }),
};

// ── Payments ─────────────────────────────────────────

export const paymentsApi = {
  list: (params) => apiClient.get("/payments/", { params }),

  createIntent: (data) =>
    apiClient.post("/payments/create-intent/", data),

  refund: (data) => apiClient.post("/payments/refund/", data),

  applyPromo: (data) =>
    apiClient.post("/payments/promo-codes/apply/", data),
};

// ── Delivery ─────────────────────────────────────────

export const deliveryApi = {
  checkZone: (data) => apiClient.post("/delivery/zones/check/", data),

  updateLocation: (data) =>
    apiClient.post("/delivery/location/update/", data),

  activeDelivery: () => apiClient.get("/delivery/active/"),

  acceptDelivery: (orderId) =>
    apiClient.post(`/delivery/assignment/${orderId}/`),

  declineDelivery: (orderId) =>
    apiClient.delete(`/delivery/assignment/${orderId}/`),

  history: (params) => apiClient.get("/delivery/history/", { params }),

  earnings: () => apiClient.get("/delivery/earnings/"),
};
