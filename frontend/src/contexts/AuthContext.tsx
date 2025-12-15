import { createContext, useContext, ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { authApi, LoginCredentials, SignupCredentials } from '../services/api'
import type { User } from '../types'

interface AuthContextType {
  user: User | null
  isLoading: boolean
  isAuthenticated: boolean
  login: (credentials: LoginCredentials) => Promise<void>
  signup: (credentials: SignupCredentials) => Promise<void>
  logout: () => Promise<void>
  checkAuth: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()

  const { data: user, isLoading, isFetching } = useQuery({
    queryKey: ['currentUser'],
    queryFn: authApi.getCurrentUser,
    retry: false,
    refetchOnWindowFocus: false,
    staleTime: 5 * 60 * 1000, // 5 minutes
  })

  // Only show loading on initial fetch, not on background refetches
  const showLoading = isLoading && isFetching

  const isAuthenticated = !!user

  const login = async (credentials: LoginCredentials) => {
    const response = await authApi.login(credentials)
    // Update the user in cache
    queryClient.setQueryData(['currentUser'], response.user)
  }

  const signup = async (credentials: SignupCredentials) => {
    const response = await authApi.signup(credentials)
    // Update the user in cache
    queryClient.setQueryData(['currentUser'], response.user)
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
    <AuthContext.Provider value={{ user: user || null, isLoading: showLoading, isAuthenticated, login, signup, logout, checkAuth }}>
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
