import { Link, useLocation } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { ScrollArea } from '@/components/ui/scroll-area';
import { PlusCircle, MessageSquare, Files, LogOut, FileText, ChevronRight } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useEffect, useState } from 'react';
import api from '@/lib/api';
import type { Session } from '@/lib/types';

interface SidebarProps extends React.HTMLAttributes<HTMLDivElement> {}

export function Sidebar({ className }: SidebarProps) {
  const { user, logout } = useAuth();
  const location = useLocation();
  const [sessions, setSessions] = useState<Session[]>([]);

  useEffect(() => {
    const fetchSessions = async () => {
      try {
        const response = await api.get('/sessions');
        setSessions(response.data);
      } catch (error) {
        console.error('Failed to fetch sessions', error);
      }
    };
    if (user) fetchSessions();
  }, [user, location.pathname]);

  const isActive = (path: string) => location.pathname === path;

  const NavItem = ({ to, icon: Icon, label }: { to: string; icon: any; label: string }) => {
    const active = isActive(to);
    return (
      <Link to={to} className="block">
        <div className={cn(
          'flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-200',
          active
            ? 'text-white'
            : 'text-white/50 hover:text-white/80 hover:bg-white/5'
        )} style={active ? {
          background: 'linear-gradient(135deg, rgba(244,63,94,0.2) 0%, rgba(225,29,72,0.1) 100%)',
          borderLeft: '2px solid #f43f5e',
          paddingLeft: '10px'
        } : {}}>
          <Icon className={cn('w-4 h-4 flex-shrink-0', active ? 'text-rose-400' : '')} />
          <span>{label}</span>
          {active && <ChevronRight className="w-3 h-3 ml-auto text-rose-400/60" />}
        </div>
      </Link>
    );
  };

  return (
    <div className={cn('flex flex-col h-screen', className)} style={{
      background: 'rgba(10, 8, 18, 0.95)',
      borderRight: '1px solid rgba(244,63,94,0.1)'
    }}>
      {/* Brand */}
      <div className="px-5 py-5 flex-none">
        <Link to="/" className="flex items-center gap-2.5 mb-6 group">
          <div className="p-2 rounded-xl btn-rose transition-transform group-hover:scale-105">
            <FileText className="w-4 h-4 text-white" />
          </div>
          <span className="font-bold text-lg tracking-tight gradient-text">Pinpoint PDF</span>
        </Link>

        <div className="space-y-1">
          <NavItem to="/" icon={PlusCircle} label="New Chat" />
          <NavItem to="/documents" icon={Files} label="Documents" />
        </div>
      </div>

      {/* Divider */}
      <div className="mx-5 mb-3" style={{ height: '1px', background: 'rgba(255,255,255,0.05)' }} />

      {/* Sessions */}
      <div className="px-5 flex-1 overflow-hidden flex flex-col min-h-0">
        <p className="text-[11px] font-semibold uppercase tracking-widest mb-2" style={{ color: 'rgba(255,255,255,0.25)' }}>
          Recent
        </p>
        <ScrollArea className="flex-1 -mx-1">
          <div className="space-y-0.5 px-1">
            {sessions.map((session, i) => {
              const active = location.pathname === `/chat/${session.session_id}`;
              return (
                <Link key={session.session_id} to={`/chat/${session.session_id}`} className="block animate-slide-up" style={{ animationDelay: `${i * 40}ms` }}>
                  <div className={cn(
                    'flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm transition-all duration-200',
                    active ? 'text-white' : 'text-white/40 hover:text-white/70 hover:bg-white/5'
                  )} style={active ? {
                    background: 'rgba(244,63,94,0.12)',
                    color: 'rgba(255,255,255,0.9)'
                  } : {}}>
                    <MessageSquare className={cn('w-3.5 h-3.5 flex-shrink-0', active ? 'text-rose-400' : '')} />
                    <span className="truncate text-xs">{session.preview || `Chat ${session.session_id.substring(0, 6)}...`}</span>
                  </div>
                </Link>
              );
            })}
            {sessions.length === 0 && (
              <p className="text-xs px-3 py-4 text-center" style={{ color: 'rgba(255,255,255,0.2)' }}>No recent chats</p>
            )}
          </div>
        </ScrollArea>
      </div>

      {/* User */}
      <div className="p-4 flex-none" style={{ borderTop: '1px solid rgba(255,255,255,0.05)' }}>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-white/5 transition-all duration-200 text-left group">
              <div className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold text-white flex-shrink-0" style={{
                background: 'linear-gradient(135deg, #fb7185, #e11d48)'
              }}>
                {user?.email?.[0]?.toUpperCase() || 'U'}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium text-white/70 truncate group-hover:text-white/90 transition-colors">{user?.email}</p>
              </div>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent className="w-56 glass-card border-white/10 text-white" align="end" side="top">
            <div className="px-2 py-1.5">
              <p className="text-xs text-white/40 truncate">{user?.email}</p>
            </div>
            <DropdownMenuSeparator className="bg-white/10" />
            <DropdownMenuItem onClick={() => logout()} className="text-rose-400 hover:text-rose-300 cursor-pointer focus:bg-rose-500/10 focus:text-rose-300">
              <LogOut className="mr-2 h-4 w-4" />
              <span>Log out</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}
