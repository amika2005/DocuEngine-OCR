import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../api/client';
import { useLiveInvalidate } from '../../api/useEvents';
import type { User } from '../../api/types';

export default function UsersPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ email: '', display_name: '', password: '', role: 'user' });
  const [error, setError] = useState('');

  const { data: users } = useQuery({
    queryKey: ['company-users'],
    queryFn: () => api<User[]>('/company/users'),
  });
  useLiveInvalidate('company.users.', [['company-users']]);

  async function onCreate(event: FormEvent) {
    event.preventDefault();
    setError('');
    try {
      await api('/company/users', { method: 'POST', body: JSON.stringify(form) });
      setShowForm(false);
      setForm({ email: '', display_name: '', password: '', role: 'user' });
      queryClient.invalidateQueries({ queryKey: ['company-users'] });
    } catch (err) {
      setError(String((err as Error).message));
    }
  }

  return (
    <div>
      <div className="mb-4 flex items-center">
        <h1 className="text-xl font-bold">{t('admin.users.title')}</h1>
        <button
          onClick={() => setShowForm((value) => !value)}
          className="ml-auto rounded bg-slate-900 px-4 py-1.5 text-sm text-white hover:bg-slate-700"
        >
          {t('admin.users.add')}
        </button>
      </div>

      {showForm && (
        <form onSubmit={onCreate} className="mb-4 grid grid-cols-5 gap-2 rounded-lg border border-slate-200 bg-white p-4 text-sm">
          <input required placeholder={t('admin.users.name')} value={form.display_name}
            onChange={(e) => setForm({ ...form, display_name: e.target.value })}
            className="rounded border border-slate-300 px-2 py-1.5" />
          <input required type="email" placeholder={t('admin.users.email')} value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
            className="rounded border border-slate-300 px-2 py-1.5" />
          <input required type="password" minLength={8} placeholder="Password" value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            className="rounded border border-slate-300 px-2 py-1.5" />
          <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}
            className="rounded border border-slate-300 px-2 py-1.5">
            <option value="user">{t('admin.users.roles.user')}</option>
            <option value="company_admin">{t('admin.users.roles.company_admin')}</option>
          </select>
          <button type="submit" className="rounded bg-slate-900 text-white hover:bg-slate-700">
            {t('common.create')}
          </button>
          {error && <p className="col-span-5 text-red-600">{error}</p>}
        </form>
      )}

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-100 text-left text-slate-600">
            <tr>
              <th className="px-4 py-2">{t('admin.users.name')}</th>
              <th className="px-4 py-2">{t('admin.users.email')}</th>
              <th className="px-4 py-2">{t('admin.users.role')}</th>
              <th className="px-4 py-2">{t('admin.users.status')}</th>
            </tr>
          </thead>
          <tbody>
            {users?.map((user) => (
              <tr key={user.id} className="border-t border-slate-100">
                <td className="px-4 py-2">{user.display_name}</td>
                <td className="px-4 py-2">{user.email}</td>
                <td className="px-4 py-2">{t(`admin.users.roles.${user.role}`, user.role)}</td>
                <td className="px-4 py-2">{user.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
