const API_BASE = '';

async function api<T>(
  path: string,
  options?: RequestInit & { json?: unknown },
): Promise<T> {
  const headers: Record<string, string> = {};
  if (options?.json !== undefined) {
    headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(options.json);
  }
  if (options?.headers) {
    Object.assign(headers, options.headers);
  }
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    credentials: 'include',
  });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // ignore parse error
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export interface PublicUser {
  id: string;
  name: string;
  email: string;
  username: string | null;
  phone: string | null;
  email_verified: boolean;
  is_admin: boolean;
  referral_code: string | null;
  created_at: string;
}

export interface WalletData {
  balance: number;
  total_earned: number;
  total_withdrawn: number;
}

export interface CreditsData {
  balance: number;
  total_earned: number;
}

export interface ReferralStats {
  total_referrals: number;
  activated_referrals: number;
  pending_referrals: number;
  total_bonus_earned: number;
  referral_code: string;
  referral_link: string;
}

export interface TrendPoint {
  month: string;
  amount?: number;
  count?: number;
}

export interface OverviewData {
  user: PublicUser;
  wallet: WalletData;
  credits: CreditsData;
  referrals: ReferralStats;
  earnings_trend: TrendPoint[];
  referral_trend: TrendPoint[];
  this_month_earned: number;
  this_month_withdrawn: number;
}

export interface Task {
  id: string;
  type: string;
  title: string;
  description: string | null;
  reward_credits: number;
  content_url: string | null;
  question: string | null;
  options: string[] | null;
  completed: boolean;
}

export const apiClient = {
  // Auth
  signup: (data: { name: string; email: string; password: string; username?: string; phone?: string; referral_code?: string }) =>
    api<{ message: string; user: PublicUser }>('/api/signup', { json: data, method: 'POST' }),
  login: (data: { identifier: string; password: string }) =>
    api<{ message: string; user: PublicUser }>('/api/login', { json: data, method: 'POST' }),
  logout: () => api<{ message: string }>('/api/logout', { method: 'POST' }),
  me: () => api<{ user: PublicUser }>('/api/me'),

  // Dashboard
  overview: () => api<OverviewData>('/api/overview'),

  // Wallet
  wallet: () => api<WalletData>('/api/wallet'),
  withdraw: (amount: number, phone: string) =>
    api('/api/wallet/withdraw', { json: { amount, phone }, method: 'POST' }),
  transactions: () => api<Array<{ id: string; type: string; amount: number; reference: string; status: string; created_at: string; description: string | null }>>('/api/wallet/transactions'),

  // Credits
  credits: () => api<CreditsData>('/api/credits'),
  convertCredits: (credits: number) =>
    api<{ credits_converted: number; ksh_amount: number; new_balance: number; new_wallet_balance: number }>('/api/credits/convert', { json: { credits }, method: 'POST' }),

  // Tasks
  tasks: () => api<Task[]>('/api/tasks'),
  completeTask: (taskId: string, answer?: string) =>
    api<{ task_id: string; credits_earned: number; total_credits: number; message: string }>(`/api/tasks/${taskId}/complete`, { json: { answer }, method: 'POST' }),

  // Referrals
  referralStats: () => api<ReferralStats>('/api/referrals/stats'),

  // Admin
  adminStats: () => api<{ total_users: number; total_revenue: number; total_withdrawals: number; pending_withdrawals: number; total_credits_earned: number }>('/api/admin/stats'),
  adminUsers: () => api<PublicUser[]>('/api/admin/users'),
  adminWithdrawals: (status?: string) =>
    api<Array<{ id: string; user_id: string; amount: number; phone: string; status: string; created_at: string; processed_at: string | null; admin_note: string | null }>>(`/api/admin/withdrawals${status ? `?status=${status}` : ''}`),
  approveWithdrawal: (id: string, note?: string) =>
    api(`/api/admin/withdrawals/${id}/approve`, { json: { note }, method: 'POST' }),
  rejectWithdrawal: (id: string, note?: string) =>
    api(`/api/admin/withdrawals/${id}/reject`, { json: { note }, method: 'POST' }),
};