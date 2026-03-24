import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import axios from 'axios';
import { authApi } from '../lib/api';

interface User {
  user_id: string;
  email: string;
}

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
  checkAuth: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

function getApiErrorMessage(err: unknown, fallback: string): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    if (typeof detail === 'string' && detail.trim()) {
      return detail;
    }
  }

  if (err instanceof Error && err.message.trim()) {
    return err.message;
  }

  return fallback;
}

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const checkAuth = useCallback(async () => {
    const token = localStorage.getItem('token');
    if (!token) {
      setUser(null);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    try {
      const response = await authApi.get('/me');
      setUser(response.data);
    } catch {
      localStorage.removeItem('token');
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void checkAuth();
  }, [checkAuth]);

  const login = useCallback(async (email: string, password: string) => {
    try {
      const response = await authApi.post('/login', { email, password });
      const { access_token } = response.data;
      localStorage.setItem('token', access_token);
      const me = await authApi.get('/me');
      setUser(me.data);
    } catch (err: unknown) {
      throw new Error(getApiErrorMessage(err, 'Invalid email or password'));
    }
  }, []);

  const register = useCallback(async (email: string, password: string) => {
    try {
      const response = await authApi.post('/register', { email, password });
      const { access_token } = response.data;
      localStorage.setItem('token', access_token);
      const me = await authApi.get('/me');
      setUser(me.data);
    } catch (err: unknown) {
      throw new Error(getApiErrorMessage(err, 'Failed to register'));
    }
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('token');
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, isLoading, login, register, logout, checkAuth }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
