import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../auth/AuthContext';

export default function Login() {
  const { login } = useAuth();
  const { t } = useTranslation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(false);
    try {
      await login(email, password);
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100">
      <form onSubmit={onSubmit} className="w-full max-w-sm rounded-lg bg-white p-8 shadow">
        <h1 className="mb-1 text-center text-2xl font-bold text-slate-900">DocuEngine</h1>
        <p className="mb-6 text-center text-sm text-slate-500">{t('login.title')}</p>
        <label className="mb-1 block text-sm text-slate-600">{t('login.email')}</label>
        <input
          type="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          className="mb-4 w-full rounded border border-slate-300 px-3 py-2"
        />
        <label className="mb-1 block text-sm text-slate-600">{t('login.password')}</label>
        <input
          type="password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          className="mb-4 w-full rounded border border-slate-300 px-3 py-2"
        />
        {error && <p className="mb-3 text-sm text-red-600">{t('login.error')}</p>}
        <button
          type="submit"
          disabled={busy}
          className="w-full rounded bg-slate-900 py-2 font-medium text-white hover:bg-slate-700 disabled:opacity-50"
        >
          {t('login.submit')}
        </button>
      </form>
    </div>
  );
}
