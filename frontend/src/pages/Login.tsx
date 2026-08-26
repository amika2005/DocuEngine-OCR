import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Languages } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';

export default function Login() {
  const { login } = useAuth();
  const { t, i18n } = useTranslation();
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

  function toggleLanguage() {
    const next = i18n.language === 'ja' ? 'en' : 'ja';
    i18n.changeLanguage(next);
    localStorage.setItem('docuengine-lang', next);
  }

  return (
    <div className="login-page flex min-h-screen flex-col lg:flex-row">
      <section className="login-hero relative flex min-h-[42vh] flex-1 flex-col justify-between overflow-hidden px-8 py-10 lg:min-h-screen lg:px-14 lg:py-12">
        <div className="login-grid" aria-hidden />
        <p className="relative z-10 text-[11px] font-medium tracking-[0.28em] text-cyan-200/80 uppercase">
          {t('login.scanning')} · OCR
        </p>
        <div className="relative z-10 max-w-md">
          <h1 className="login-title text-4xl font-semibold tracking-tight text-white sm:text-5xl">
            DocuEngine
          </h1>
          <p className="mt-3 text-lg text-cyan-100/90">{t('login.tagline')}</p>
          <p className="mt-4 max-w-sm text-sm leading-relaxed text-slate-300">{t('login.heroBody')}</p>
        </div>

        <div className="login-stage relative z-10 mx-auto mt-8 w-full max-w-sm lg:mx-0">
          <div className="login-sheet">
            <div className="mb-3 flex items-center justify-between text-[10px] tracking-widest text-slate-400">
              <span>納品書</span>
              <span className="rounded-sm bg-slate-800/80 px-1.5 py-0.5 text-cyan-200">
                {t('login.processing')}
              </span>
            </div>
            <div className="space-y-1.5 text-[11px] text-slate-600">
              <div className="login-row">
                <span>品目</span>
                <span>数量</span>
                <span>金額</span>
              </div>
              <div className="login-row login-row-hit">
                <span>マスター管理</span>
                <span>1</span>
                <span>45,000</span>
              </div>
              <div className="login-row">
                <span>保守契約</span>
                <span>12</span>
                <span>1,710,000</span>
              </div>
              <div className="login-row">
                <span>合計</span>
                <span />
                <span>1,755,000</span>
              </div>
            </div>
            <div className="login-scan" aria-hidden />
            <span className="login-box login-box-a" aria-hidden />
            <span className="login-box login-box-b" aria-hidden />
          </div>
        </div>
      </section>

      <section className="flex flex-1 items-center justify-center bg-[#F3F5F8] px-6 py-12">
        <form onSubmit={onSubmit} className="w-full max-w-sm">
          <div className="mb-8 flex items-start justify-between gap-4">
            <div>
              <h2 className="text-2xl font-semibold text-slate-900">{t('login.title')}</h2>
              <p className="mt-1 text-sm text-slate-500">{t('appName')}</p>
            </div>
            <button
              type="button"
              onClick={toggleLanguage}
              className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
            >
              <Languages className="h-3.5 w-3.5" strokeWidth={1.8} />
              {t('common.language')}
            </button>
          </div>
          <label className="mb-1 block text-sm text-slate-600">{t('login.email')}</label>
          <input
            type="email"
            required
            autoComplete="username"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="mb-4 w-full rounded-md border border-slate-300 bg-white px-3 py-2.5 text-slate-900 outline-none ring-cyan-600/30 focus:border-slate-400 focus:ring-2"
          />
          <label className="mb-1 block text-sm text-slate-600">{t('login.password')}</label>
          <input
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="mb-4 w-full rounded-md border border-slate-300 bg-white px-3 py-2.5 text-slate-900 outline-none ring-cyan-600/30 focus:border-slate-400 focus:ring-2"
          />
          {error && <p className="mb-3 text-sm text-red-600">{t('login.error')}</p>}
          <button
            type="submit"
            disabled={busy}
            className="w-full cursor-pointer rounded-md bg-[#0B1F3A] py-2.5 font-medium text-white hover:bg-[#163154] disabled:opacity-50"
          >
            {t('login.submit')}
          </button>
        </form>
      </section>
    </div>
  );
}
