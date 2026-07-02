import { Navigate, Route, Routes } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from './auth/AuthContext';
import Layout from './components/Layout';
import Login from './pages/Login';
import ScanPage from './pages/user/ScanPage';
import DocumentsPage from './pages/user/DocumentsPage';
import DocumentDetailPage from './pages/user/DocumentDetailPage';
import CorrectionEditorPage from './pages/user/CorrectionEditorPage';
import CorrectionsPage from './pages/user/CorrectionsPage';
import UsersPage from './pages/company-admin/UsersPage';
import DevicesPage from './pages/company-admin/DevicesPage';
import TrainingPage from './pages/company-admin/TrainingPage';
import CompaniesPage from './pages/super-admin/CompaniesPage';
import StatsPage from './pages/super-admin/StatsPage';

export default function App() {
  const { me, loading } = useAuth();
  const { t } = useTranslation();

  if (loading) {
    return <div className="flex h-screen items-center justify-center text-slate-500">{t('common.loading')}</div>;
  }
  if (!me) return <Login />;

  const home = me.role === 'super_admin' ? '/admin/companies' : '/documents';

  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to={home} replace />} />
        {me.role !== 'super_admin' && (
          <>
            <Route path="/scan" element={<ScanPage />} />
            <Route path="/documents" element={<DocumentsPage />} />
            <Route path="/documents/:id" element={<DocumentDetailPage />} />
            <Route path="/pages/:pageId/correct" element={<CorrectionEditorPage />} />
            <Route path="/corrections" element={<CorrectionsPage />} />
          </>
        )}
        {me.role === 'company_admin' && (
          <>
            <Route path="/company/users" element={<UsersPage />} />
            <Route path="/company/devices" element={<DevicesPage />} />
            <Route path="/company/training" element={<TrainingPage />} />
          </>
        )}
        {me.role === 'super_admin' && (
          <>
            <Route path="/admin/companies" element={<CompaniesPage />} />
            <Route path="/admin/stats" element={<StatsPage />} />
          </>
        )}
        <Route path="*" element={<Navigate to={home} replace />} />
      </Routes>
    </Layout>
  );
}
