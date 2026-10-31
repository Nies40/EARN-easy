'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';
import { Line, Bar } from 'react-chartjs-2';
import { apiClient, type OverviewData, type Task } from '../lib/api';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  Filler,
);

type Tab = 'overview' | 'tasks' | 'wallet' | 'referrals' | 'admin';

export default function DashboardPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<OverviewData | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [tab, setTab] = useState<Tab>('overview');
  const [showReferralPopup, setShowReferralPopup] = useState(false);
  const [copied, setCopied] = useState(false);

  const loadOverview = useCallback(async () => {
    try {
      const d = await apiClient.overview();
      setData(d);
    } catch {
      router.push('/');
    } finally {
      setLoading(false);
    }
  }, [router]);

  const loadTasks = useCallback(async () => {
    try {
      setTasks(await apiClient.tasks());
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    loadOverview();
    loadTasks();
  }, [loadOverview, loadTasks]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <span className="loader" style={{ width: 32, height: 32 }} />
      </div>
    );
  }

  if (!data) return null;

  const { user, wallet, credits, referrals } = data;

  const earningsChart = {
    labels: data.earnings_trend.map((p) => p.month),
    datasets: [{
      label: 'Earnings (Ksh)',
      data: data.earnings_trend.map((p) => p.amount || 0),
      borderColor: '#ec4899',
      backgroundColor: 'rgba(236, 72, 153, 0.1)',
      fill: true,
      tension: 0.4,
    }],
  };

  const referralsChart = {
    labels: data.referral_trend.map((p) => p.month),
    datasets: [{
      label: 'Referrals',
      data: data.referral_trend.map((p) => p.count || 0),
      backgroundColor: '#3b82f6',
      borderRadius: 6,
    }],
  };

  const copyLink = () => {
    navigator.clipboard.writeText(referrals.referral_link);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="min-h-screen pb-20">
      {/* Header */}
      <header className="sticky top-0 z-40 bg-dark-900/80 backdrop-blur border-b border-dark-600">
        <div className="max-w-5xl mx-auto px-4 py-4 flex items-center justify-between">
          <h1 className="text-xl font-bold gradient-text">Easyearn</h1>
          <div className="flex items-center gap-3">
            <span className="text-sm text-gray-400">{user.name}</span>
            <button
              onClick={async () => { await apiClient.logout(); router.push('/'); }}
              className="text-xs text-gray-500 hover:text-pink transition"
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      <div className="max-w-5xl mx-auto px-4 mt-6">
        {/* Welcome */}
        <div className="mb-6">
          <h2 className="text-2xl font-bold">Hi {user.name.split(' ')[0]}! 👋</h2>
          <p className="text-gray-500 text-sm mt-1">Welcome to your dashboard</p>
        </div>

        {/* Tabs */}
        <div className="flex gap-2 mb-6 overflow-x-auto scrollbar-hide">
          {(['overview', 'tasks', 'wallet', 'referrals', ...(user.is_admin ? ['admin'] : [])] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-2 rounded-lg text-sm font-medium capitalize whitespace-nowrap transition ${tab === t ? 'bg-pink text-white' : 'bg-dark-700 text-gray-400'}`}
            >
              {t}
            </button>
          ))}
        </div>

        {tab === 'overview' && (
          <div className="space-y-6 fade-in">
            {/* New Feature Banner */}
            <div className="card p-4 gradient-bg border-pink/30">
              <p className="text-sm">
                <span className="gradient-text font-bold">✨ Introducing Credits!</span>
                <span className="text-gray-400"> Earn credits for watching videos, liking photos, trivia, and tasks.</span>
              </p>
            </div>

            {/* Wallet Cards */}
            <div className="grid grid-cols-2 gap-4">
              <div className="card p-5 card-hover">
                <p className="text-xs text-gray-500 uppercase tracking-wide">Wallet Balance</p>
                <p className="text-2xl font-bold mt-2">Ksh {wallet.balance.toLocaleString()}</p>
              </div>
              <div className="card p-5 card-hover">
                <p className="text-xs text-gray-500 uppercase tracking-wide">Total Earned</p>
                <p className="text-2xl font-bold mt-2 text-green-400">Ksh {wallet.total_earned.toLocaleString()}</p>
              </div>
              <div className="card p-5 card-hover">
                <p className="text-xs text-gray-500 uppercase tracking-wide">Total Withdrawn</p>
                <p className="text-2xl font-bold mt-2 text-blue-light">Ksh {wallet.total_withdrawn.toLocaleString()}</p>
              </div>
              <div className="card p-5 card-hover">
                <p className="text-xs text-gray-500 uppercase tracking-wide">Credits</p>
                <p className="text-2xl font-bold mt-2 text-pink">{credits.balance.toLocaleString()}</p>
              </div>
            </div>

            {/* This Month */}
            <div className="grid grid-cols-2 gap-4">
              <div className="card p-4">
                <p className="text-xs text-gray-500 uppercase">This Month Earned</p>
                <p className="text-xl font-bold mt-1">Ksh {data.this_month_earned.toLocaleString()}</p>
              </div>
              <div className="card p-4">
                <p className="text-xs text-gray-500 uppercase">This Month Withdrawn</p>
                <p className="text-xl font-bold mt-1">Ksh {data.this_month_withdrawn.toLocaleString()}</p>
              </div>
            </div>

            {/* Earnings Trend Chart */}
            <div className="card p-6">
              <h3 className="font-semibold mb-4">Earnings Trend</h3>
              <Line data={earningsChart} options={{ responsive: true, plugins: { legend: { display: false } }, scales: { x: { grid: { color: '#262633' } }, y: { grid: { color: '#262633' } } } }} />
            </div>

            {/* Referrals Trend Chart */}
            <div className="card p-6">
              <h3 className="font-semibold mb-4">Referrals Trend</h3>
              <Bar data={referralsChart} options={{ responsive: true, plugins: { legend: { display: false } }, scales: { x: { grid: { color: '#262633' } }, y: { grid: { color: '#262633' } } } }} />
            </div>

            {/* Referral Stats */}
            <div className="card p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-semibold">Referral Stats</h3>
                <button onClick={() => setShowReferralPopup(true)} className="text-sm text-pink hover:text-pink-light transition">
                  Get Earning Link →
                </button>
              </div>
              <div className="grid grid-cols-3 gap-4 text-center">
                <div>
                  <p className="text-2xl font-bold text-blue-light">{referrals.total_referrals}</p>
                  <p className="text-xs text-gray-500">Total</p>
                </div>
                <div>
                  <p className="text-2xl font-bold text-green-400">{referrals.activated_referrals}</p>
                  <p className="text-xs text-gray-500">Activated</p>
                </div>
                <div>
                  <p className="text-2xl font-bold text-pink">{referrals.pending_referrals}</p>
                  <p className="text-xs text-gray-500">Pending</p>
                </div>
              </div>
            </div>
          </div>
        )}

        {tab === 'tasks' && <TasksTab tasks={tasks} onComplete={async (t, answer) => { await apiClient.completeTask(t, answer); loadTasks(); loadOverview(); }} />}
        {tab === 'wallet' && <WalletTab wallet={wallet} />}
        {tab === 'referrals' && <ReferralsTab stats={referrals} onCopy={copyLink} copied={copied} />}
        {tab === 'admin' && user.is_admin && <AdminTab />}
      </div>

      {/* Referral Popup */}
      {showReferralPopup && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={() => setShowReferralPopup(false)}>
          <div className="card p-6 max-w-md w-full" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-bold mb-4">Your Earning Link</h3>
            <div className="flex gap-2 mb-4">
              <input value={referrals.referral_link} readOnly className="flex-1 text-sm" />
              <button onClick={copyLink} className="btn-primary text-sm whitespace-nowrap">
                {copied ? 'Copied!' : 'Copy'}
              </button>
            </div>
            <div className="flex gap-2">
              <a href={`https://wa.me/?text=${encodeURIComponent(`Join Easyearn and earn! ${referrals.referral_link}`)}`} target="_blank" className="btn-secondary flex-1 text-center text-sm">
                WhatsApp
              </a>
              <a href={`https://t.me/share/url?url=${encodeURIComponent(referrals.referral_link)}&text=${encodeURIComponent('Join Easyearn and earn!')}`} target="_blank" className="btn-secondary flex-1 text-center text-sm">
                Telegram
              </a>
            </div>
            <button onClick={() => setShowReferralPopup(false)} className="mt-4 text-sm text-gray-500 hover:text-pink w-full text-center transition">Close</button>
          </div>
        </div>
      )}
    </div>
  );
}

function TasksTab({ tasks, onComplete }: { tasks: Task[]; onComplete: (id: string, answer?: string) => Promise<void> }) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState<string | null>(null);
  const [msg, setMsg] = useState('');

  const handleComplete = async (task: Task) => {
    setLoading(task.id);
    try {
      await onComplete(task.id, answers[task.id]);
      setMsg(`Task completed! +${task.reward_credits} credits`);
      setTimeout(() => setMsg(''), 3000);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : 'Failed');
      setTimeout(() => setMsg(''), 3000);
    } finally {
      setLoading(null);
    }
  };

  if (tasks.length === 0) {
    return <div className="card p-12 text-center text-gray-500 fade-in">No tasks available yet. Check back soon!</div>;
  }

  return (
    <div className="space-y-4 fade-in">
      {msg && <div className="p-3 rounded-lg bg-pink/10 border border-pink/30 text-pink-light text-sm">{msg}</div>}
      {tasks.map((t) => (
        <div key={t.id} className="card p-5">
          <div className="flex items-start justify-between mb-3">
            <div>
              <span className="text-xs px-2 py-0.5 rounded-full bg-dark-600 text-gray-400 capitalize">{t.type.replace('_', ' ')}</span>
              <h4 className="font-semibold mt-2">{t.title}</h4>
              {t.description && <p className="text-sm text-gray-500 mt-1">{t.description}</p>}
            </div>
            <span className="text-pink font-bold text-sm whitespace-nowrap">+{t.reward_credits} cr</span>
          </div>
          {t.content_url && (
            <div className="mb-3 rounded-lg overflow-hidden bg-dark-900">
              {t.type === 'video' ? (
                <video src={t.content_url} controls className="w-full rounded-lg" />
              ) : (
                <img src={t.content_url} alt={t.title} className="w-full rounded-lg max-h-48 object-cover" />
              )}
            </div>
          )}
          {t.type === 'trivia' && t.question && (
            <div className="mb-3">
              <p className="text-sm mb-2">{t.question}</p>
              {t.options && (
                <div className="space-y-2">
                  {t.options.map((opt, i) => (
                    <label key={i} className="flex items-center gap-2 p-2 rounded-lg bg-dark-900 cursor-pointer">
                      <input type="radio" name={t.id} value={opt} checked={answers[t.id] === opt} onChange={(e) => setAnswers({ ...answers, [t.id]: e.target.value })} />
                      <span className="text-sm">{opt}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          )}
          {t.completed ? (
            <span className="text-green-400 text-sm">✓ Completed</span>
          ) : (
            <button onClick={() => handleComplete(t)} disabled={loading === t.id} className="btn-primary text-sm flex items-center gap-2">
              {loading === t.id && <span className="loader" />}
              {t.type === 'trivia' ? 'Submit Answer' : 'Complete Task'}
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

function WalletTab({ wallet }: { wallet: { balance: number; total_earned: number; total_withdrawn: number } }) {
  const [amount, setAmount] = useState('');
  const [phone, setPhone] = useState('');
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState('');

  const handleWithdraw = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      await apiClient.withdraw(parseFloat(amount), phone);
      setMsg('Withdrawal requested successfully');
      setAmount('');
    } catch (err) {
      setMsg(err instanceof Error ? err.message : 'Failed');
    } finally {
      setLoading(false);
      setTimeout(() => setMsg(''), 4000);
    }
  };

  return (
    <div className="space-y-4 fade-in">
      <div className="grid grid-cols-3 gap-4">
        <div className="card p-5 text-center">
          <p className="text-xs text-gray-500">Balance</p>
          <p className="text-xl font-bold mt-1">Ksh {wallet.balance.toLocaleString()}</p>
        </div>
        <div className="card p-5 text-center">
          <p className="text-xs text-gray-500">Earned</p>
          <p className="text-xl font-bold mt-1 text-green-400">Ksh {wallet.total_earned.toLocaleString()}</p>
        </div>
        <div className="card p-5 text-center">
          <p className="text-xs text-gray-500">Withdrawn</p>
          <p className="text-xl font-bold mt-1 text-blue-light">Ksh {wallet.total_withdrawn.toLocaleString()}</p>
        </div>
      </div>
      <div className="card p-6">
        <h3 className="font-semibold mb-4">Withdraw to M-Pesa</h3>
        {msg && <div className="mb-4 p-3 rounded-lg bg-pink/10 border border-pink/30 text-sm">{msg}</div>}
        <form onSubmit={handleWithdraw} className="space-y-4">
          <input type="number" placeholder="Amount (Ksh)" value={amount} onChange={(e) => setAmount(e.target.value)} required min="1" />
          <input type="tel" placeholder="M-Pesa phone (e.g. 2547...)" value={phone} onChange={(e) => setPhone(e.target.value)} required />
          <button type="submit" disabled={loading} className="btn-primary w-full flex items-center justify-center gap-2">
            {loading && <span className="loader" />}
            Request Withdrawal
          </button>
        </form>
      </div>
    </div>
  );
}

function ReferralsTab({ stats, onCopy, copied }: { stats: { total_referrals: number; activated_referrals: number; pending_referrals: number; total_bonus_earned: number; referral_link: string }; onCopy: () => void; copied: boolean }) {
  return (
    <div className="space-y-4 fade-in">
      <div className="card p-6">
        <h3 className="font-semibold mb-4">Your Earning Link</h3>
        <div className="flex gap-2 mb-4">
          <input value={stats.referral_link} readOnly className="flex-1 text-sm" />
          <button onClick={onCopy} className="btn-primary text-sm whitespace-nowrap">{copied ? 'Copied!' : 'Copy'}</button>
        </div>
        <div className="flex gap-2">
          <a href={`https://wa.me/?text=${encodeURIComponent(`Join Easyearn and earn! ${stats.referral_link}`)}`} target="_blank" className="btn-secondary flex-1 text-center text-sm">WhatsApp</a>
          <a href={`https://t.me/share/url?url=${encodeURIComponent(stats.referral_link)}&text=${encodeURIComponent('Join Easyearn and earn!')}`} target="_blank" className="btn-secondary flex-1 text-center text-sm">Telegram</a>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="card p-5 text-center">
          <p className="text-3xl font-bold text-blue-light">{stats.total_referrals}</p>
          <p className="text-xs text-gray-500 mt-1">Total Referrals</p>
        </div>
        <div className="card p-5 text-center">
          <p className="text-3xl font-bold text-green-400">{stats.activated_referrals}</p>
          <p className="text-xs text-gray-500 mt-1">Activated</p>
        </div>
      </div>
      <div className="card p-5">
        <div className="flex justify-between items-center">
          <span className="text-gray-500 text-sm">Total Bonus Earned</span>
          <span className="font-bold text-pink">Ksh {stats.total_bonus_earned.toLocaleString()}</span>
        </div>
      </div>
    </div>
  );
}

function AdminTab() {
  const [stats, setStats] = useState<{ total_users: number; total_revenue: number; total_withdrawals: number; pending_withdrawals: number } | null>(null);
  const [withdrawals, setWithdrawals] = useState<Array<{ id: string; amount: number; phone: string; status: string; created_at: string }>>([]);

  useEffect(() => {
    apiClient.adminStats().then(setStats).catch(() => {});
    apiClient.adminWithdrawals('pending').then(setWithdrawals).catch(() => {});
  }, []);

  const refresh = () => {
    apiClient.adminStats().then(setStats);
    apiClient.adminWithdrawals('pending').then(setWithdrawals);
  };

  return (
    <div className="space-y-4 fade-in">
      <div className="grid grid-cols-2 gap-4">
        <div className="card p-5"><p className="text-xs text-gray-500">Total Users</p><p className="text-2xl font-bold mt-1">{stats?.total_users ?? '—'}</p></div>
        <div className="card p-5"><p className="text-xs text-gray-500">Total Revenue</p><p className="text-2xl font-bold mt-1">Ksh {stats?.total_revenue?.toLocaleString() ?? '—'}</p></div>
        <div className="card p-5"><p className="text-xs text-gray-500">Total Withdrawals</p><p className="text-2xl font-bold mt-1">Ksh {stats?.total_withdrawals?.toLocaleString() ?? '—'}</p></div>
        <div className="card p-5"><p className="text-xs text-gray-500">Pending</p><p className="text-2xl font-bold mt-1 text-pink">{stats?.pending_withdrawals ?? '—'}</p></div>
      </div>
      <div className="card p-6">
        <h3 className="font-semibold mb-4">Pending Withdrawals</h3>
        {withdrawals.length === 0 ? (
          <p className="text-gray-500 text-sm">No pending withdrawals</p>
        ) : (
          <div className="space-y-3">
            {withdrawals.map((w) => (
              <div key={w.id} className="flex items-center justify-between p-3 rounded-lg bg-dark-900">
                <div>
                  <p className="font-medium">Ksh {w.amount.toLocaleString()}</p>
                  <p className="text-xs text-gray-500">{w.phone} · {new Date(w.created_at).toLocaleDateString()}</p>
                </div>
                <div className="flex gap-2">
                  <button onClick={async () => { await apiClient.approveWithdrawal(w.id); refresh(); }} className="btn-primary text-xs px-3 py-1">Approve</button>
                  <button onClick={async () => { await apiClient.rejectWithdrawal(w.id); refresh(); }} className="btn-secondary text-xs px-3 py-1">Reject</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}