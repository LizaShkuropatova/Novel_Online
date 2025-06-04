import { useAuthStore } from '@/store/auth';

export default defineNuxtRouteMiddleware(async (to, from) => {
 const auth = useAuthStore();

 // If token is present, but profile is not loaded - fetch profile data
 if (auth.isAuthenticated && !auth.user) {
  await auth.fetchProfile();
 }

 // If is not authenticated - redirect to main page
 if (!auth.isAuthenticated) {
  return navigateTo('/');
 }
});
