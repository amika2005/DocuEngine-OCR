import { type ReactNode, useState } from 'react';
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
  PanelLeftClose,
  PanelLeftOpen,
  PenLine,
  Printer,
  ScanLine,
  Users,
  type LucideIcon,
} from 'lucide-react';
import { useAuth } from '../auth/AuthContext';

const SIDEBAR_KEY = 'docuengine-sidebar';

interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
}

export default function Layout({ children }: { children: ReactNode }) {
  const { me, logout } = useAuth();
  const { t, i18n } = useTranslation();
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem(SIDEBAR_KEY) === 'collapsed';
    } catch {
      return false;
    }
  });

  const links: NavItem[] = [{ to: '/dashboard', label: t('nav.dashboard'), icon: LayoutDashboard }];
  if (me?.role !== 'super_admin') {
    links.push({ to: '/scan', label: t('nav.scan'), icon: ScanLine });
    links.push({ to: '/documents', label: t('nav.documents'), icon: FileText });
    links.push({ to: '/corrections', label: t('nav.corrections'), icon: PenLine });
    // Masters are read-only for regular users, editable for admins.
    links.push({ to: '/company/masters', label: t('nav.masters'), icon: Database });
  }
  if (me?.role === 'company_admin') {
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

  function toggleCollapsed() {
    setCollapsed((current) => {
      const next = !current;
      localStorage.setItem(SIDEBAR_KEY, next ? 'collapsed' : 'expanded');
      return next;
    });
  }

  return (
    <div className="flex min-h-screen bg-slate-50">
      <aside
        className={`flex shrink-0 flex-col bg-slate-900 text-white transition-[width] duration-200 ease-out ${
          collapsed ? 'w-[72px]' : 'w-64'
        }`}
      >
        <div className={`flex items-center py-4 ${collapsed ? 'justify-center px-2' : 'justify-between px-3'}`}>
          {!collapsed && (
            <div className="px-2 text-xl font-bold tracking-wide">{t('appName')}</div>
          )}
          <button
            type="button"
            onClick={toggleCollapsed}
            aria-expanded={!collapsed}
            aria-label={collapsed ? t('nav.expand') : t('nav.collapse')}
            title={collapsed ? t('nav.expand') : t('nav.collapse')}
            className="cursor-pointer rounded-md p-2 text-slate-300 hover:bg-slate-800 hover:text-white"
          >
            {collapsed ? (
              <PanelLeftOpen className="h-5 w-5" strokeWidth={1.8} />
            ) : (
              <PanelLeftClose className="h-5 w-5" strokeWidth={1.8} />
            )}
          </button>
        </div>
        <nav className={`flex-1 space-y-1 ${collapsed ? 'px-2' : 'px-3'}`}>
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              title={collapsed ? link.label : undefined}
              className={({ isActive }) =>
                `flex items-center rounded-md py-2.5 text-[15px] transition-colors ${
                  collapsed ? 'justify-center px-2' : 'gap-3 px-3'
                } ${
                  isActive
                    ? 'bg-slate-700 font-medium text-white'
                    : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                }`
              }
            >
              <link.icon className="h-[18px] w-[18px] shrink-0" strokeWidth={1.8} />
              <span className={collapsed ? 'sr-only' : ''}>{link.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className={`space-y-2 border-t border-slate-800 ${collapsed ? 'p-2' : 'p-4'}`}>
          {!collapsed && (
            <p className="truncate text-[15px] text-slate-300" title={me?.email}>
              {me?.display_name}
            </p>
          )}
          <div className={`flex gap-2 ${collapsed ? 'flex-col' : ''}`}>
            <button
              type="button"
              onClick={toggleLanguage}
              title={t('common.language')}
              className={`flex cursor-pointer items-center justify-center gap-1.5 rounded bg-slate-800 py-2 text-sm hover:bg-slate-700 ${
                collapsed ? 'px-2' : 'flex-1 px-2'
              }`}
            >
              <Languages className="h-4 w-4 shrink-0" strokeWidth={1.8} />
              {!collapsed && t('common.language')}
            </button>
            <button
              type="button"
              onClick={logout}
              title={t('nav.logout')}
              className={`flex cursor-pointer items-center justify-center gap-1.5 rounded bg-slate-800 py-2 text-sm hover:bg-slate-700 ${
                collapsed ? 'px-2' : 'flex-1 px-2'
              }`}
            >
              <LogOut className="h-4 w-4 shrink-0" strokeWidth={1.8} />
              {!collapsed && t('nav.logout')}
            </button>
          </div>
        </div>
      </aside>
      <main className="min-w-0 flex-1 px-6 py-6">{children}</main>
    </div>
  );
}
