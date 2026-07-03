import { type ReactNode } from 'react';
import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../auth/AuthContext';

interface NavItem {
  to: string;
  label: string;
  icon: string;
}

export default function Layout({ children }: { children: ReactNode }) {
  const { me, logout } = useAuth();
  const { t, i18n } = useTranslation();

  const links: NavItem[] = [{ to: '/dashboard', label: t('nav.dashboard'), icon: '🏠' }];
  if (me?.role !== 'super_admin') {
    links.push({ to: '/scan', label: t('nav.scan'), icon: '📥' });
    links.push({ to: '/documents', label: t('nav.documents'), icon: '📄' });
    links.push({ to: '/corrections', label: t('nav.corrections'), icon: '✏️' });
  }
  if (me?.role === 'company_admin') {
    links.push({ to: '/company/users', label: t('nav.users'), icon: '👥' });
    links.push({ to: '/company/devices', label: t('nav.devices'), icon: '🖨️' });
    links.push({ to: '/company/training', label: t('nav.training'), icon: '🧠' });
  }
  if (me?.role === 'super_admin') {
    links.push({ to: '/admin/companies', label: t('nav.companies'), icon: '🏢' });
  }

  function toggleLanguage() {
    const next = i18n.language === 'ja' ? 'en' : 'ja';
    i18n.changeLanguage(next);
    localStorage.setItem('docuengine-lang', next);
  }

  return (
    <div className="flex min-h-screen bg-slate-50">
      <aside className="flex w-60 shrink-0 flex-col bg-slate-900 text-white">
        <div className="px-5 py-5 text-lg font-bold tracking-wide">{t('appName')}</div>
        <nav className="flex-1 space-y-1 px-3">
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors ${
                  isActive
                    ? 'bg-slate-700 font-medium text-white'
                    : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                }`
              }
            >
              <span aria-hidden>{link.icon}</span>
              {link.label}
            </NavLink>
          ))}
        </nav>
        <div className="space-y-2 border-t border-slate-800 p-4 text-sm">
          <p className="truncate text-slate-300" title={me?.email}>
            {me?.display_name}
          </p>
          <div className="flex gap-2">
            <button
              onClick={toggleLanguage}
              className="flex-1 rounded bg-slate-800 px-2 py-1.5 text-xs hover:bg-slate-700"
            >
              {t('common.language')}
            </button>
            <button
              onClick={logout}
              className="flex-1 rounded bg-slate-800 px-2 py-1.5 text-xs hover:bg-slate-700"
            >
              {t('nav.logout')}
            </button>
          </div>
        </div>
      </aside>
      <main className="min-w-0 flex-1 px-6 py-6">{children}</main>
    </div>
  );
}
