import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../api/client';
import type { Device } from '../../api/types';

export default function DevicesPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [name, setName] = useState('');
  const [newToken, setNewToken] = useState<string | null>(null);

  const { data: devices } = useQuery({
    queryKey: ['company-devices'],
    queryFn: () => api<Device[]>('/company/devices'),
  });

  async function onCreate(event: FormEvent) {
    event.preventDefault();
    const device = await api<Device>('/company/devices', {
      method: 'POST',
      body: JSON.stringify({ name }),
    });
    setNewToken(device.token ?? null);
    setName('');
    queryClient.invalidateQueries({ queryKey: ['company-devices'] });
  }

  async function onDelete(id: string) {
    if (!confirm('Delete device?')) return;
    await api(`/company/devices/${id}`, { method: 'DELETE' });
    queryClient.invalidateQueries({ queryKey: ['company-devices'] });
  }

  return (
    <div>
      <h1 className="mb-4 text-xl font-bold">{t('admin.devices.title')}</h1>

      <form onSubmit={onCreate} className="mb-4 flex gap-2">
        <input
          required
          placeholder={t('admin.devices.name')}
          value={name}
          onChange={(event) => setName(event.target.value)}
          className="w-72 rounded border border-slate-300 px-3 py-1.5 text-sm"
        />
        <button type="submit" className="rounded bg-slate-900 px-4 py-1.5 text-sm text-white hover:bg-slate-700">
          {t('admin.devices.add')}
        </button>
      </form>

      {newToken && (
        <div className="mb-4 rounded-lg border border-amber-300 bg-amber-50 p-4">
          <p className="mb-2 text-sm font-medium text-amber-900">{t('admin.devices.tokenNote')}</p>
          <code className="block select-all break-all rounded bg-white p-2 text-sm">{newToken}</code>
        </div>
      )}

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-100 text-left text-slate-600">
            <tr>
              <th className="px-4 py-2">{t('admin.devices.name')}</th>
              <th className="px-4 py-2">{t('admin.devices.lastSeen')}</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody>
            {devices?.map((device) => (
              <tr key={device.id} className="border-t border-slate-100">
                <td className="px-4 py-2">{device.name}</td>
                <td className="px-4 py-2">
                  {device.last_seen_at ? new Date(device.last_seen_at).toLocaleString() : '—'}
                </td>
                <td className="px-4 py-2 text-right">
                  <button onClick={() => onDelete(device.id)} className="text-xs text-red-600 hover:underline">
                    {t('common.delete')}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
