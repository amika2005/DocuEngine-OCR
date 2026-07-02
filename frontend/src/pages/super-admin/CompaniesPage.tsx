import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../api/client';
import type { Company } from '../../api/types';

export default function CompaniesPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ name: '', slug: '' });
  const [adminTarget, setAdminTarget] = useState<Company | null>(null);
  const [adminForm, setAdminForm] = useState({ email: '', display_name: '', password: '' });
  const [message, setMessage] = useState('');

  const { data: companies } = useQuery({
    queryKey: ['companies'],
    queryFn: () => api<Company[]>('/admin/companies'),
  });

  async function onCreate(event: FormEvent) {
    event.preventDefault();
    await api('/admin/companies', { method: 'POST', body: JSON.stringify(form) });
    setForm({ name: '', slug: '' });
    queryClient.invalidateQueries({ queryKey: ['companies'] });
  }

  async function onCreateAdmin(event: FormEvent) {
    event.preventDefault();
    if (!adminTarget) return;
    await api(`/admin/companies/${adminTarget.id}/admins`, {
      method: 'POST',
      body: JSON.stringify({ ...adminForm, role: 'company_admin' }),
    });
    setMessage(`${adminForm.email} → ${adminTarget.name}`);
    setAdminTarget(null);
    setAdminForm({ email: '', display_name: '', password: '' });
  }

  return (
    <div>
      <h1 className="mb-4 text-xl font-bold">{t('admin.companies.title')}</h1>

      <form onSubmit={onCreate} className="mb-4 flex gap-2 text-sm">
        <input required placeholder={t('admin.companies.name')} value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          className="w-64 rounded border border-slate-300 px-3 py-1.5" />
        <input required placeholder={t('admin.companies.slug')} pattern="[a-z0-9][a-z0-9-]{1,62}" value={form.slug}
          onChange={(e) => setForm({ ...form, slug: e.target.value })}
          className="w-48 rounded border border-slate-300 px-3 py-1.5" />
        <button type="submit" className="rounded bg-slate-900 px-4 py-1.5 text-white hover:bg-slate-700">
          {t('admin.companies.add')}
        </button>
      </form>

      {message && <p className="mb-3 rounded bg-green-50 p-2 text-sm text-green-700">{message}</p>}

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-100 text-left text-slate-600">
            <tr>
              <th className="px-4 py-2">{t('admin.companies.name')}</th>
              <th className="px-4 py-2">{t('admin.companies.slug')}</th>
              <th className="px-4 py-2">{t('admin.companies.status')}</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody>
            {companies?.map((company) => (
              <tr key={company.id} className="border-t border-slate-100">
                <td className="px-4 py-2">{company.name}</td>
                <td className="px-4 py-2 font-mono text-xs">{company.slug}</td>
                <td className="px-4 py-2">{company.status}</td>
                <td className="px-4 py-2 text-right">
                  <button onClick={() => setAdminTarget(company)} className="text-xs text-blue-700 hover:underline">
                    {t('admin.companies.addAdmin')}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {adminTarget && (
        <form onSubmit={onCreateAdmin} className="mt-4 grid max-w-2xl grid-cols-4 gap-2 rounded-lg border border-slate-200 bg-white p-4 text-sm">
          <p className="col-span-4 font-medium">{adminTarget.name} — {t('admin.companies.addAdmin')}</p>
          <input required placeholder={t('admin.users.name')} value={adminForm.display_name}
            onChange={(e) => setAdminForm({ ...adminForm, display_name: e.target.value })}
            className="rounded border border-slate-300 px-2 py-1.5" />
          <input required type="email" placeholder={t('admin.users.email')} value={adminForm.email}
            onChange={(e) => setAdminForm({ ...adminForm, email: e.target.value })}
            className="rounded border border-slate-300 px-2 py-1.5" />
          <input required type="password" minLength={8} placeholder="Password" value={adminForm.password}
            onChange={(e) => setAdminForm({ ...adminForm, password: e.target.value })}
            className="rounded border border-slate-300 px-2 py-1.5" />
          <button type="submit" className="rounded bg-slate-900 text-white hover:bg-slate-700">
            {t('common.create')}
          </button>
        </form>
      )}
    </div>
  );
}
