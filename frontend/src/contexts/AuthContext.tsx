import { createContext, useContext, ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { authApi } from '../services/api'
import type { User } from '../types'

interface AuthContextType {
  user: User | null
  isLoading: boolean
  isAuthenticated: boolean
  login: () => void
  logout: () => Promise<void>
  checkAuth: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()

  const { data: user, isLoading } = useQuery({
    queryKey: ['currentUser'],
    queryFn: authApi.getCurrentUser,
    retry: false,
    refetchOnWindowFocus: false,
  })

  const isAuthenticated = !!user

  const login = () => {
    window.location.href = authApi.getGoogleAuthUrl()
  }

  const logout = async () => {
    try {
      await authApi.logout()

      // Clear user data from cache
      queryClient.setQueryData(['currentUser'], null)

      // Redirect to login page
      window.location.href = '/login'
    } catch (error) {
      console.error('Error logging out:', error)
      throw error
    }
  }

  const checkAuth = async () => {
    await queryClient.refetchQueries({ queryKey: ['currentUser'] })
  }

  return (
    <AuthContext.Provider value={{ user: user || null, isLoading, isAuthenticated, login, logout, checkAuth }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return context
}
