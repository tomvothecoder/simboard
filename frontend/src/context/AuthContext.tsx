import axios from 'axios';
import { createContext, ReactNode, useContext, useEffect, useState } from 'react';

import api from '@/api/api';

// -----------------------------
// User model (matches UserRead)
// -----------------------------
export interface User {
  id: string; // UUID
  email: string;
  role: string;

  is_active: boolean;
  is_superuser: boolean;
  is_verified: boolean;

  // Optional fields if your model later includes them
  full_name?: string;
  avatar_url?: string;
}

// -----------------------------
// AuthContext type
// -----------------------------
interface AuthContextType {
  user: User | null;
  loading: boolean;
  isAuthenticated: boolean;
  login: () => void;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

// Create context
const AuthContext = createContext<AuthContextType | undefined>(undefined);

// Always send cookies to backend
axios.defaults.withCredentials = true;

// -----------------------------
// AuthProvider
// -----------------------------
export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // Fetch /users/me to load user from cookie
  const refreshUser = async () => {
    try {
      const res = await api.get<User>('/users/me');
      setUser(res.data);
    } catch {
      setUser(null);
    }
  };

  // Redirect to FastAPI GitHub OAuth entrypoint
  const login = async () => {
    const res = await api.get('/auth/github/authorize');
    window.location.href = res.data.authorization_url;
  };

  // Logout (FastAPI clears cookie)
  const logout = async () => {
    await api.post('/auth/logout', {});
    setUser(null);
  };

  // Load user on initial mount
  useEffect(() => {
    const init = async () => {
      await refreshUser();
      setLoading(false);
    };
    init();
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        isAuthenticated: !!user,
        login,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

// -----------------------------
// Hook
// -----------------------------
export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
};
