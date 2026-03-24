import { Outlet } from 'react-router-dom';
import { Sidebar } from '@/components/Sidebar';

export default function MainLayout() {
  return (
    <div className="flex h-screen w-full overflow-hidden" style={{ background: '#0a0812' }}>
      {/* Sidebar */}
      <div className="hidden md:flex w-[260px] flex-shrink-0">
        <Sidebar className="w-full" />
      </div>

      {/* Main content */}
      <div className="flex-1 overflow-hidden flex flex-col">
        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
