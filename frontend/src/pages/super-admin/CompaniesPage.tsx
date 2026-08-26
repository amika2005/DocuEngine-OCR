import { Fragment, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiError, api } from '../../api/client';
import { useLiveInvalidate } from '../../api/useEvents';
import type { Company, User } from '../../api/types';

function AdminList({ companyId }: { companyId: string }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { data: admins } = useQuery({
    queryKey: ['company-admins', companyId],
    queryFn: () => api<User[]>(`/admin/companies/${companyId}/admins`),
  });
  useLiveInvalidate('company.users.', [['company-admins', companyId]]);

  async function setStatus(user: User, next: 'active' | 'disabled') {
    await api(`/admin/companies/${companyId}/admins/${user.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ status: next }),
    });
    queryClient.invalidateQueries({ queryKey: ['company-admins', companyId] });
    queryClient.invalidateQueries({ queryKey: ['companies'] });
  }

  async function remove(user: User) {
    if (!window.confirm(t('admin.companies.confirmDelete', { email: user.email }))) return;
    await api(`/admin/companies/${companyId}/admins/${user.id}`, { method: 'DELETE' });
    queryClient.invalidateQueries({ queryKey: ['company-admins', companyId] });
    queryClient.invalidateQueries({ queryKey: ['companies'] });
  }

  return (
    <div className="border-t border-slate-100 bg-slate-50/80 px-4 py-3">
      <div className="mb-2 flex items-center gap-2">
        <p className="text-xs font-medium text-slate-500">{t('admin.companies.issuedLogins')}</p>
        <span className="rounded-full bg-slate-200 px-2 py-0.5 text-[11px] font-medium text-slate-700">
          {t('admin.companies.issuedCount', { count: admins?.length ?? 0 })}
        </span>
      </div>
      {(admins?.length ?? 0) === 0 ? (
        <p className="text-xs text-slate-400">{t('admin.companies.noAdmins')}</p>
      ) : (
        <div className="overflow-hidden rounded-md border border-slate-200 bg-white">
          <table className="w-full text-xs">
            <thead className="bg-slate-100 text-left text-slate-600">
              <tr>
                <th className="px-3 py-1.5">{t('admin.users.name')}</th>
                <th className="px-3 py-1.5">{t('admin.users.email')}</th>
                <th className="px-3 py-1.5">{t('admin.users.status')}</th>
                <th className="px-3 py-1.5">{t('admin.companies.lastLogin')}</th>
                <th className="px-3 py-1.5">{t('admin.companies.issuedAt')}</th>
                <th className="px-3 py-1.5" />
              </tr>
            </thead>
            <tbody>
              {admins?.map((user) => (
                <tr key={user.id} className="border-t border-slate-100">
                  <td className="px-3 py-1.5">{user.display_name}</td>
                  <td className="px-3 py-1.5">{user.email}</td>
                  <td className="px-3 py-1.5">
                    <span
                      className={`rounded-full px-2 py-0.5 ${
                        user.status === 'active'
                          ? 'bg-green-100 text-green-800'
                          : 'bg-slate-200 text-slate-600'
                      }`}
                    >
                      {t(`admin.companies.adminStatus.${user.status}`, user.status)}
                    </span>
                  </td>
                  <td className="px-3 py-1.5 text-slate-500">
                    {user.last_login_at ? new Date(user.last_login_at).toLocaleString() : '—'}
                  </td>
                  <td className="px-3 py-1.5 text-slate-500">
                    {user.created_at ? new Date(user.created_at).toLocaleString() : '—'}
                  </td>
                  <td className="px-3 py-1.5 text-right whitespace-nowrap">
                    {user.status === 'active' ? (
                      <button
                        type="button"
                        onClick={() => setStatus(user, 'disabled')}
                        className="cursor-pointer text-amber-700 hover:underline"
                      >
                        {t('admin.companies.deactivate')}
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => setStatus(user, 'active')}
                        className="cursor-pointer text-green-700 hover:underline"
                      >
                        {t('admin.companies.activate')}
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => remove(user)}
                      className="ml-3 cursor-pointer text-red-700 hover:underline"
                    >
                      {t('common.delete')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function CompaniesPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ name: '', slug: '' });
  const [adminTarget, setAdminTarget] = useState<Company | null>(null);
  const [adminForm, setAdminForm] = useState({ email: '', display_name: '', password: '' });
  const [issued, setIssued] = useState<User | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);

  const { data: companies } = useQuery({
    queryKey: ['companies'],
    queryFn: () => api<Company[]>('/admin/companies'),
  });
  useLiveInvalidate('company.', [['companies']]);

  async function onCreate(event: FormEvent) {
    event.preventDefault();
    await api('/admin/companies', { method: 'POST', body: JSON.stringify(form) });
    setForm({ name: '', slug: '' });
    queryClient.invalidateQueries({ queryKey: ['companies'] });
  }

  async function onCreateAdmin(event: FormEvent) {
    event.preventDefault();
    if (!adminTarget) return;
    setError('');
    setBusy(true);
    try {
      const created = await api<User>(`/admin/companies/${adminTarget.id}/admins`, {
        method: 'POST',
        body: JSON.stringify({ ...adminForm, role: 'company_admin' }),
      });
      setIssued(created);
      setOpenId(adminTarget.id);
      setAdminTarget(null);
      setAdminForm({ email: '', display_name: '', password: '' });
      queryClient.invalidateQueries({ queryKey: ['companies'] });
      queryClient.invalidateQueries({ queryKey: ['company-admins', created.company_id ?? adminTarget.id] });
    } catch (err) {
      const detail = err instanceof ApiError ? err.message : String(err);
      setError(detail.includes('already') ? t('admin.companies.emailTaken') : detail);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h1 className="mb-4 text-xl font-bold">{t('admin.companies.title')}</h1>

      <form onSubmit={onCreate} className="mb-4 flex gap-2 text-sm">
        <input
          required
          placeholder={t('admin.companies.name')}
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          className="w-64 rounded border border-slate-300 px-3 py-1.5"
        />
        <input
          required
          placeholder={t('admin.companies.slug')}
          pattern="[a-z0-9][a-z0-9-]{1,62}"
          value={form.slug}
          onChange={(e) => setForm({ ...form, slug: e.target.value })}
          className="w-48 rounded border border-slate-300 px-3 py-1.5"
        />
        <button type="submit" className="rounded bg-slate-900 px-4 py-1.5 text-white hover:bg-slate-700">
          {t('admin.companies.add')}
        </button>
      </form>

      {issued && (
        <div className="mb-3 rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-900">
          <p className="font-medium">{t('admin.companies.justIssued')}</p>
          <p className="mt-1">
            {issued.display_name} · {issued.email} · {t(`admin.users.roles.${issued.role}`, issued.role)}
          </p>
          <p className="mt-1 text-xs text-green-800">{t('admin.companies.passwordNotStored')}</p>
        </div>
      )}

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-100 text-left text-slate-600">
            <tr>
              <th className="px-4 py-2">{t('admin.companies.name')}</th>
              <th className="px-4 py-2">{t('admin.companies.slug')}</th>
              <th className="px-4 py-2">{t('admin.companies.status')}</th>
              <th className="px-4 py-2">{t('admin.companies.admins')}</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody>
            {companies?.map((company) => (
              <Fragment key={company.id}>
                <tr className="border-t border-slate-100">
                  <td className="px-4 py-2">{company.name}</td>
                  <td className="px-4 py-2 font-mono text-xs">{company.slug}</td>
                  <td className="px-4 py-2">{company.status}</td>
                  <td className="px-4 py-2">
                    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">
                      {t('admin.companies.issuedCount', { count: company.admin_count ?? 0 })}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right">
                    <button
                      type="button"
                      onClick={() => setOpenId(openId === company.id ? null : company.id)}
                      className="mr-3 cursor-pointer text-xs text-slate-600 hover:underline"
                    >
                      {openId === company.id ? t('admin.companies.hideAdmins') : t('admin.companies.showAdmins')}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setError('');
                        setIssued(null);
                        setAdminTarget(company);
                        setAdminForm({
                          display_name: '',
                          email: `admin@${company.slug}.co.jp`,
                          password: '',
                        });
                      }}
                      className="cursor-pointer text-xs text-blue-700 hover:underline"
                    >
                      {t('admin.companies.addAdmin')}
                    </button>
                  </td>
                </tr>
                {openId === company.id && (
                  <tr>
                    <td colSpan={5} className="p-0">
                      <AdminList companyId={company.id} />
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {adminTarget && (
        <form
          onSubmit={onCreateAdmin}
          className="mt-4 grid max-w-2xl grid-cols-4 gap-2 rounded-lg border border-slate-200 bg-white p-4 text-sm"
        >
          <p className="col-span-4 font-medium">
            {adminTarget.name} — {t('admin.companies.addAdmin')}
          </p>
          <input
            required
            placeholder={t('admin.users.name')}
            value={adminForm.display_name}
            onChange={(e) => setAdminForm({ ...adminForm, display_name: e.target.value })}
            className="rounded border border-slate-300 px-2 py-1.5"
          />
          <input
            required
            type="email"
            placeholder={t('admin.users.email')}
            value={adminForm.email}
            onChange={(e) => setAdminForm({ ...adminForm, email: e.target.value })}
            className="rounded border border-slate-300 px-2 py-1.5"
          />
          <input
            required
            type="password"
            minLength={8}
            placeholder={t('login.password')}
            value={adminForm.password}
            onChange={(e) => setAdminForm({ ...adminForm, password: e.target.value })}
            className="rounded border border-slate-300 px-2 py-1.5"
          />
          <button
            type="submit"
            disabled={busy}
            className="cursor-pointer rounded bg-slate-900 text-white hover:bg-slate-700 disabled:opacity-50"
          >
            {t('common.create')}
          </button>
          <p className="col-span-4 text-xs text-slate-500">{t('admin.companies.adminEmailHint')}</p>
          {error && <p className="col-span-4 text-red-600">{error}</p>}
        </form>
      )}
    </div>
  );
}
