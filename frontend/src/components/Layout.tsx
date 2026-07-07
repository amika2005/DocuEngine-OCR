import { type ReactNode } from 'react';
import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  BrainCircuit,
  Building2,
  Database,
  FileText,
  Languages,
  LayoutDashboard,
  LayoutTemplate,
  LogOut,
  PenLine,
  Printer,
  ScanLine,
  Users,
  type LucideIcon,
} from 'lucide-react';
import { useAuth } from '../auth/AuthContext';

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
}

export default function Layout({ children }: { children: ReactNode }) {
  const { me, logout } = useAuth();
  const { t, i18n } = useTranslation();

  const links: NavItem[] = [{ to: '/dashboard', label: t('nav.dashboard'), icon: LayoutDashboard }];
  if (me?.role !== 'super_admin') {
    links.push({ to: '/scan', label: t('nav.scan'), icon: ScanLine });
    links.push({ to: '/documents', label: t('nav.documents'), icon: FileText });
    links.push({ to: '/corrections', label: t('nav.corrections'), icon: PenLine });
  }
  if (me?.role === 'company_admin') {
    links.push({ to: '/company/masters', label: t('nav.masters'), icon: Database });
    links.push({ to: '/company/templates', label: t('nav.templates'), icon: LayoutTemplate });
    links.push({ to: '/company/users', label: t('nav.users'), icon: Users });
    links.push({ to: '/company/devices', label: t('nav.devices'), icon: Printer });
    links.push({ to: '/company/training', label: t('nav.training'), icon: BrainCircuit });
  }
  if (me?.role === 'super_admin') {
    links.push({ to: '/admin/companies', label: t('nav.companies'), icon: Building2 });
  }

  function toggleLanguage() {
    const next = i18n.language === 'ja' ? 'en' : 'ja';
    i18n.changeLanguage(next);
    localStorage.setItem('docuengine-lang', next);
  }

  return (
    <div className="flex min-h-screen bg-slate-50">
      <aside className="flex w-64 shrink-0 flex-col bg-slate-900 text-white">
        <div className="px-5 py-5 text-xl font-bold tracking-wide">{t('appName')}</div>
        <nav className="flex-1 space-y-1 px-3">
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-md px-3 py-2.5 text-[15px] transition-colors ${
                  isActive
                    ? 'bg-slate-700 font-medium text-white'
                    : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                }`
              }
            >
              <link.icon className="h-[18px] w-[18px] shrink-0" strokeWidth={1.8} />
              {link.label}
            </NavLink>
          ))}
        </nav>
        <div className="space-y-2 border-t border-slate-800 p-4">
          <p className="truncate text-[15px] text-slate-300" title={me?.email}>
            {me?.display_name}
          </p>
          <div className="flex gap-2">
            <button
              onClick={toggleLanguage}
              className="flex flex-1 items-center justify-center gap-1.5 rounded bg-slate-800 px-2 py-2 text-sm hover:bg-slate-700"
            >
              <Languages className="h-4 w-4" strokeWidth={1.8} />
              {t('common.language')}
            </button>
            <button
              onClick={logout}
              className="flex flex-1 items-center justify-center gap-1.5 rounded bg-slate-800 px-2 py-2 text-sm hover:bg-slate-700"
            >
              <LogOut className="h-4 w-4" strokeWidth={1.8} />
              {t('nav.logout')}
            </button>
          </div>
        </div>
      </aside>
      <main className="min-w-0 flex-1 px-6 py-6">{children}</main>
    </div>
  );
}
