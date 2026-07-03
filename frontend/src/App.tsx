import { Navigate, Route, Routes } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from './auth/AuthContext';
import Layout from './components/Layout';
import Login from './pages/Login';
import DashboardPage from './pages/user/DashboardPage';
import ScanPage from './pages/user/ScanPage';
import DocumentsPage from './pages/user/DocumentsPage';
import DocumentDetailPage from './pages/user/DocumentDetailPage';
import CorrectionEditorPage from './pages/user/CorrectionEditorPage';
import CorrectionsPage from './pages/user/CorrectionsPage';
import CompanyDashboardPage from './pages/company-admin/CompanyDashboardPage';
import MastersPage from './pages/company-admin/MastersPage';
import UsersPage from './pages/company-admin/UsersPage';
import DevicesPage from './pages/company-admin/DevicesPage';
import TrainingPage from './pages/company-admin/TrainingPage';
import AdminDashboardPage from './pages/super-admin/AdminDashboardPage';
import CompaniesPage from './pages/super-admin/CompaniesPage';

export default function App() {
  const { me, loading } = useAuth();
  const { t } = useTranslation();

  if (loading) {
    return <div className="flex h-screen items-center justify-center text-slate-500">{t('common.loading')}</div>;
  }
  if (!me) return <Login />;

  const dashboard =
    me.role === 'super_admin' ? (
      <AdminDashboardPage />
    ) : me.role === 'company_admin' ? (
      <CompanyDashboardPage />
    ) : (
      <DashboardPage />
    );

  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={dashboard} />
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
            <Route path="/company/masters" element={<MastersPage />} />
            <Route path="/company/users" element={<UsersPage />} />
            <Route path="/company/devices" element={<DevicesPage />} />
            <Route path="/company/training" element={<TrainingPage />} />
          </>
        )}
        {me.role === 'super_admin' && (
          <>
            <Route path="/admin/companies" element={<CompaniesPage />} />
            <Route path="/admin/stats" element={<Navigate to="/dashboard" replace />} />
          </>
        )}
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </Layout>
  );
}
