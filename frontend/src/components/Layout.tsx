import { type ReactNode } from 'react';
import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../auth/AuthContext';

export default function Layout({ children }: { children: ReactNode }) {
  const { me, logout } = useAuth();
  const { t, i18n } = useTranslation();

  const links: { to: string; label: string }[] = [];
  if (me?.role !== 'super_admin') {
    links.push({ to: '/documents', label: t('nav.documents') });
    links.push({ to: '/corrections', label: t('nav.corrections') });
  }
  if (me?.role === 'company_admin') {
    links.push({ to: '/company/users', label: t('nav.users') });
    links.push({ to: '/company/devices', label: t('nav.devices') });
    links.push({ to: '/company/training', label: t('nav.training') });
  }
  if (me?.role === 'super_admin') {
    links.push({ to: '/admin/companies', label: t('nav.companies') });
    links.push({ to: '/admin/stats', label: t('nav.stats') });
  }

  function toggleLanguage() {
    const next = i18n.language === 'ja' ? 'en' : 'ja';
    i18n.changeLanguage(next);
    localStorage.setItem('docuengine-lang', next);
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-slate-900 text-white">
        <div className="mx-auto flex max-w-7xl items-center gap-6 px-4 py-3">
          <span className="text-lg font-bold tracking-wide">{t('appName')}</span>
          <nav className="flex gap-4 text-sm">
            {links.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                className={({ isActive }) =>
                  `rounded px-2 py-1 hover:bg-slate-700 ${isActive ? 'bg-slate-700' : ''}`
                }
              >
                {link.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm">
            <button onClick={toggleLanguage} className="rounded px-2 py-1 hover:bg-slate-700">
              {t('common.language')}
            </button>
            <span className="text-slate-300">{me?.display_name}</span>
            <button onClick={logout} className="rounded bg-slate-700 px-3 py-1 hover:bg-slate-600">
              {t('nav.logout')}
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
    </div>
  );
}
